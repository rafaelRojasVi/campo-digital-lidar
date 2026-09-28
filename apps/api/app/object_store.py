"""Provider-neutral, content-addressed local object storage.

Domain code must depend only on this module's interface, never on a cloud
SDK. ``LocalObjectStore`` is the V1 (local-dev) implementation; a future
``GCSObjectStore``/``AzureBlobObjectStore``/``S3ObjectStore`` would implement
the same protocol without any product-domain code change.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Protocol

_KEY_PATTERN = re.compile(r"^sha256/[0-9a-f]{2}/[0-9a-f]{62}$")
_READ_CHUNK_SIZE = 1024 * 1024


class ObjectStoreError(RuntimeError):
    """Base error for object store operations."""


class ObjectStoreNotConfiguredError(ObjectStoreError):
    """Raised when production has no explicit, absolute object-store root."""


class ObjectAlreadyExistsWithDifferentContentError(ObjectStoreError):
    """Raised when a content-addressed key already exists with a different size."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Identity and metadata for one immutable stored object."""

    key: str
    sha256: str
    byte_size: int
    media_type: str | None


class ObjectStore(Protocol):
    """Provider-neutral interface for immutable, content-addressed storage."""

    def put(self, data: BinaryIO, *, media_type: str | None) -> StoredObject:
        """Store content, returning its content-addressed identity."""

    def open(self, key: str) -> BinaryIO:
        """Open previously stored content for reading."""

    def stat(self, key: str) -> StoredObject:
        """Return metadata for a previously stored object."""

    def exists(self, key: str) -> bool:
        """Return whether a key is present in the store."""


DEFAULT_LOCAL_OBJECT_STORE_ROOT = ".local/object-store"


def resolve_object_store_root(app_env: str | None, configured: str | None) -> Path:
    """Return the object-store root for ``app_env``, failing closed in production.

    Outside production the relative ``.local/object-store`` default is fine:
    it is a developer's working copy. In production that default resolves
    inside the container's own writable layer, which most hosts (Railway,
    Cloud Run, Render) discard on every redeploy or restart -- uploaded
    workbooks would silently vanish while their database rows survive. So
    production must name an absolute path explicitly, which in practice is
    the mount point of a persistent volume.
    """

    if app_env != "production":
        return Path(configured or DEFAULT_LOCAL_OBJECT_STORE_ROOT)
    if not configured:
        raise ObjectStoreNotConfiguredError(
            "CAMPO_OBJECT_STORE_ROOT must be set in production (a persistent volume path)."
        )
    root = Path(configured)
    if not root.is_absolute():
        raise ObjectStoreNotConfiguredError(
            "CAMPO_OBJECT_STORE_ROOT must be an absolute path in production."
        )
    return root


class ObjectStoreNotPersistentError(ObjectStoreNotConfiguredError):
    """Raised when the production object-store root is not on a mounted volume."""


PROC_SELF_MOUNTINFO = Path("/proc/self/mountinfo")
# Mounted, but held in memory: gone on restart exactly like the container layer.
_EPHEMERAL_FILESYSTEM_TYPES = frozenset({"tmpfs", "ramfs"})
_MOUNTINFO_ESCAPE = re.compile(r"\\([0-7]{3})")


def _unescape_mountinfo_path(field: str) -> str:
    return _MOUNTINFO_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), field)


def _enclosing_mount(path: Path, mountinfo: str) -> tuple[Path, str] | None:
    """Return the mount point and filesystem type that ``path`` lives on.

    ``path`` need not exist: the longest mount point that is ``path`` or one
    of its ancestors is where it would be created.
    """

    best: tuple[Path, str] | None = None
    for line in mountinfo.splitlines():
        pre, separator, post = line.partition(" - ")
        fields = pre.split()
        if not separator or len(fields) < 5 or not post.split():
            continue
        mount_point = Path(_unescape_mountinfo_path(fields[4]))
        if mount_point != path and mount_point not in path.parents:
            continue
        # Later lines are later mounts, which shadow earlier ones at the same point.
        if best is None or len(mount_point.parts) >= len(best[0].parts):
            best = (mount_point, post.split()[0])
    return best


def require_persistent_mount(root: Path, *, mountinfo_path: Path | None = None) -> None:
    """Refuse a production object-store root that is not on its own mounted volume.

    An absolute, writable path proves nothing about persistence: a container
    started as root can ``mkdir -p /data/object-store`` straight onto its own
    writable layer when no volume is attached (the image's entrypoint does
    exactly that), and everything written there vanishes on the next
    redeploy. What a persistent volume adds, and the container layer lacks,
    is a mount. So the root must sit under a mount point other than ``/``,
    and that mount must not be memory-backed.

    This establishes that *something* is mounted there, not that the host
    keeps it across deploys; only the host's volume configuration does that.
    """

    mountinfo_path = mountinfo_path or PROC_SELF_MOUNTINFO
    try:
        mountinfo = mountinfo_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ObjectStoreNotPersistentError(
            f"Cannot read {mountinfo_path} to confirm CAMPO_OBJECT_STORE_ROOT is on a volume."
        ) from exc

    enclosing = _enclosing_mount(Path(os.path.abspath(root)), mountinfo)
    if enclosing is None or enclosing[0] == Path("/"):
        raise ObjectStoreNotPersistentError(
            f"CAMPO_OBJECT_STORE_ROOT ({root}) is on the container's root filesystem, "
            "not on a mounted persistent volume."
        )
    mount_point, filesystem_type = enclosing
    if filesystem_type in _EPHEMERAL_FILESYSTEM_TYPES:
        raise ObjectStoreNotPersistentError(
            f"CAMPO_OBJECT_STORE_ROOT ({root}) is on {filesystem_type} at {mount_point}, "
            "which does not survive a restart."
        )


def open_configured_object_store(app_env: str | None, configured: str | None) -> LocalObjectStore:
    """Build the process's object store, failing closed in production.

    Production requires an absolute root (``resolve_object_store_root``) on
    a mounted, non-memory filesystem (``require_persistent_mount``), checked
    before the store creates any directory.
    """

    root = resolve_object_store_root(app_env, configured)
    if app_env == "production":
        require_persistent_mount(root)
    return LocalObjectStore(root)


def _sha256_to_key(digest_hex: str) -> str:
    return f"sha256/{digest_hex[:2]}/{digest_hex[2:]}"


class LocalObjectStore:
    """Filesystem-backed content-addressed object store for local development."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "_tmp").mkdir(parents=True, exist_ok=True)

    def check_writable(self) -> None:
        """Write and remove a probe file, raising ``OSError`` if the root is not writable.

        A volume mounted root-owned over a non-root process's path passes
        ``mkdir(exist_ok=True)`` at construction and fails only on the first
        real upload; this surfaces that at readiness time instead.
        """

        probe = self.root / "_tmp" / f"ready-{uuid.uuid4().hex}"
        probe.write_bytes(b"")
        probe.unlink()

    def put(self, data: BinaryIO, *, media_type: str | None) -> StoredObject:
        """Stream ``data`` to a temp file, hash it, then atomically publish it."""

        tmp_path = self.root / "_tmp" / uuid.uuid4().hex
        digest = sha256()
        byte_size = 0

        try:
            with tmp_path.open("wb") as handle:
                while chunk := data.read(_READ_CHUNK_SIZE):
                    digest.update(chunk)
                    byte_size += len(chunk)
                    handle.write(chunk)

            digest_hex = digest.hexdigest()
            key = _sha256_to_key(digest_hex)
            final_path = self._key_to_path(key)
            final_path.parent.mkdir(parents=True, exist_ok=True)

            if final_path.exists():
                existing_size = final_path.stat().st_size
                if existing_size != byte_size:
                    raise ObjectAlreadyExistsWithDifferentContentError(
                        f"Key {key!r} already exists with byte size "
                        f"{existing_size}, but new content has size {byte_size}."
                    )
            else:
                os.replace(tmp_path, final_path)

            meta_path = self._meta_path(final_path)
            meta_path.write_text(
                json.dumps({"media_type": media_type, "byte_size": byte_size}),
                encoding="utf-8",
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        return StoredObject(
            key=key,
            sha256=digest_hex,
            byte_size=byte_size,
            media_type=media_type,
        )

    def open(self, key: str) -> BinaryIO:
        """Open the content file for a previously stored key."""

        path = self._key_to_path(key)
        if not path.is_file():
            raise ObjectStoreError(f"No object stored for key {key!r}.")
        return path.open("rb")

    def stat(self, key: str) -> StoredObject:
        """Return the stored metadata for ``key`` without reading content."""

        path = self._key_to_path(key)
        if not path.is_file():
            raise ObjectStoreError(f"No object stored for key {key!r}.")

        meta = json.loads(self._meta_path(path).read_text(encoding="utf-8"))
        digest_hex = key.split("/", 1)[1].replace("/", "")

        return StoredObject(
            key=key,
            sha256=digest_hex,
            byte_size=int(meta["byte_size"]),
            media_type=meta["media_type"],
        )

    def exists(self, key: str) -> bool:
        """Return whether ``key`` is safely resolvable and present."""

        try:
            path = self._key_to_path(key)
        except ObjectStoreError:
            return False
        return path.is_file()

    def _key_to_path(self, key: str) -> Path:
        """Resolve ``key`` to a real path strictly beneath the store root.

        Mirrors ``app.source_discovery._resolve_source_file``'s approach:
        validate shape first, walk component-by-component rejecting
        symlinks, then confirm the resolved path stays under the root.
        """

        if not _KEY_PATTERN.match(key):
            raise ObjectStoreError(f"Malformed object key: {key!r}.")

        candidate = self.root
        for part in key.split("/"):
            candidate = candidate / part
            if candidate.is_symlink():
                raise ObjectStoreError("Symbolic links are not accepted in object paths.")

        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(self.root)
        except (OSError, ValueError) as exc:
            raise ObjectStoreError(
                "Object key cannot be resolved safely beneath the root."
            ) from exc

        return resolved

    @staticmethod
    def _meta_path(content_path: Path) -> Path:
        return content_path.with_name(content_path.name + ".meta.json")
