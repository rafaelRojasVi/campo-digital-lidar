"""Unit tests for the local filesystem-backed object store."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

import pytest
from app.object_store import (
    LocalObjectStore,
    ObjectStoreError,
    ObjectStoreNotConfiguredError,
    ObjectStoreNotPersistentError,
    open_configured_object_store,
    require_persistent_mount,
    resolve_object_store_root,
)


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "object-store")


def test_put_returns_sha256_identity_and_size(store: LocalObjectStore) -> None:
    content = b"hello campo digital"
    result = store.put(io.BytesIO(content), media_type="text/plain")

    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.byte_size == len(content)
    assert result.media_type == "text/plain"


def test_put_is_idempotent_for_identical_content(store: LocalObjectStore) -> None:
    content = b"same bytes"
    first = store.put(io.BytesIO(content), media_type="text/plain")
    second = store.put(io.BytesIO(content), media_type="text/plain")

    assert first.key == second.key


def test_open_returns_original_bytes(store: LocalObjectStore) -> None:
    content = b"round trip content"
    stored = store.put(io.BytesIO(content), media_type=None)

    with store.open(stored.key) as handle:
        assert handle.read() == content


def test_stat_matches_put_result(store: LocalObjectStore) -> None:
    content = b"stat me"
    stored = store.put(io.BytesIO(content), media_type="application/zip")

    stat_result = store.stat(stored.key)
    assert stat_result == stored


def test_exists_false_for_unknown_key(store: LocalObjectStore) -> None:
    assert store.exists("sha256/aa/" + "0" * 62) is False


def test_exists_true_after_put(store: LocalObjectStore) -> None:
    stored = store.put(io.BytesIO(b"exists me"), media_type=None)
    assert store.exists(stored.key) is True


def test_write_is_atomic_no_partial_file_on_crash(
    store: LocalObjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure mid-write must never leave a corrupt object at the final key."""

    original_replace = os.replace

    def failing_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash before atomic rename")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError):
        store.put(io.BytesIO(b"partial content that must not land"), media_type=None)

    monkeypatch.setattr(os, "replace", original_replace)
    stored = store.put(io.BytesIO(b"partial content that must not land"), media_type=None)
    assert store.exists(stored.key)


def test_key_rejects_path_traversal(store: LocalObjectStore) -> None:
    with pytest.raises(ObjectStoreError):
        store.open("../../etc/passwd")


def test_key_rejects_absolute_path(store: LocalObjectStore) -> None:
    with pytest.raises(ObjectStoreError):
        store.open("/etc/passwd")


def test_key_rejects_malformed_scheme(store: LocalObjectStore) -> None:
    with pytest.raises(ObjectStoreError):
        store.open("not-a-valid-key")


def test_symlink_escape_is_rejected(store: LocalObjectStore, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")

    stored = store.put(io.BytesIO(b"placeholder"), media_type=None)
    real_path = store._key_to_path(stored.key)
    real_path.unlink()
    real_path.symlink_to(outside)

    with pytest.raises(ObjectStoreError):
        store.open(stored.key)


def test_different_content_produces_different_keys(store: LocalObjectStore) -> None:
    first = store.put(io.BytesIO(b"content one"), media_type=None)
    second = store.put(io.BytesIO(b"content two"), media_type=None)
    assert first.key != second.key


@pytest.mark.parametrize("app_env", ["development", "test", "staging", None])
def test_non_production_root_defaults_to_local_working_copy(app_env: str | None) -> None:
    assert resolve_object_store_root(app_env, None) == Path(".local/object-store")
    assert resolve_object_store_root(app_env, "relative/ok") == Path("relative/ok")


def test_production_root_requires_explicit_configuration() -> None:
    with pytest.raises(ObjectStoreNotConfiguredError):
        resolve_object_store_root("production", None)
    with pytest.raises(ObjectStoreNotConfiguredError):
        resolve_object_store_root("production", "")


def test_production_root_rejects_relative_path() -> None:
    # A relative path lands in the container's own layer, erased on redeploy.
    with pytest.raises(ObjectStoreNotConfiguredError):
        resolve_object_store_root("production", ".local/object-store")


def test_production_root_accepts_absolute_volume_path() -> None:
    assert resolve_object_store_root("production", "/data/object-store") == Path(
        "/data/object-store"
    )


def test_check_writable_leaves_no_probe_behind(store: LocalObjectStore) -> None:
    store.check_writable()

    assert list((store.root / "_tmp").iterdir()) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_check_writable_raises_on_read_only_root(store: LocalObjectStore) -> None:
    tmp_dir = store.root / "_tmp"
    tmp_dir.chmod(0o500)
    try:
        with pytest.raises(OSError):
            store.check_writable()
    finally:
        tmp_dir.chmod(0o700)


# /proc/self/mountinfo of a container started with no volume attached: the
# overlay root plus the runtime's usual pseudo-filesystems and bind mounts.
_NO_VOLUME_MOUNTINFO = """\
600 500 0:52 / / rw,relatime master:300 - overlay overlay rw,lowerdir=/l,upperdir=/u,workdir=/w
601 600 0:55 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
602 600 0:56 / /dev rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755
603 600 0:60 / /sys ro,nosuid,nodev,noexec,relatime - sysfs sysfs ro
604 600 8:1 /docker/containers/abc/resolv.conf /etc/resolv.conf rw,relatime - ext4 /dev/sda1 rw
605 600 8:1 /docker/containers/abc/hosts /etc/hosts rw,relatime - ext4 /dev/sda1 rw
606 602 0:51 / /dev/shm rw,nosuid,nodev,noexec,relatime - tmpfs shm rw,size=65536k
"""

_DATA_VOLUME_LINE = "607 600 8:1 /volumes/data/_data /data rw,relatime - ext4 /dev/sda1 rw\n"


def _mountinfo(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "mountinfo"
    path.write_text(text, encoding="utf-8")
    return path


def test_persistent_mount_refuses_a_root_created_on_the_container_layer(
    tmp_path: Path,
) -> None:
    # What the root entrypoint produces with no volume: /data/object-store
    # exists and is writable, but lives on the overlay root.
    mountinfo = _mountinfo(tmp_path, _NO_VOLUME_MOUNTINFO)

    with pytest.raises(ObjectStoreNotPersistentError, match="root filesystem"):
        require_persistent_mount(Path("/data/object-store"), mountinfo_path=mountinfo)


def test_persistent_mount_is_an_object_store_configuration_error(tmp_path: Path) -> None:
    # Subclassing keeps the existing 503 mapping for uploads and readiness.
    assert issubclass(ObjectStoreNotPersistentError, ObjectStoreNotConfiguredError)


def test_persistent_mount_accepts_a_root_under_a_mounted_volume(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path, _NO_VOLUME_MOUNTINFO + _DATA_VOLUME_LINE)

    require_persistent_mount(Path("/data/object-store"), mountinfo_path=mountinfo)
    require_persistent_mount(Path("/data"), mountinfo_path=mountinfo)


def test_persistent_mount_does_not_match_a_sibling_prefix(tmp_path: Path) -> None:
    # /data is mounted; /database is not under it.
    mountinfo = _mountinfo(tmp_path, _NO_VOLUME_MOUNTINFO + _DATA_VOLUME_LINE)

    with pytest.raises(ObjectStoreNotPersistentError):
        require_persistent_mount(Path("/database/object-store"), mountinfo_path=mountinfo)


def test_persistent_mount_refuses_a_memory_backed_mount(tmp_path: Path) -> None:
    mountinfo = _mountinfo(
        tmp_path,
        _NO_VOLUME_MOUNTINFO + "607 600 0:70 / /data rw,relatime - tmpfs tmpfs rw\n",
    )

    with pytest.raises(ObjectStoreNotPersistentError, match="tmpfs"):
        require_persistent_mount(Path("/data/object-store"), mountinfo_path=mountinfo)


def test_persistent_mount_decodes_escaped_mount_points(tmp_path: Path) -> None:
    mountinfo = _mountinfo(
        tmp_path,
        _NO_VOLUME_MOUNTINFO + "607 600 8:1 / /mnt/campo\\040data rw - ext4 /dev/sda1 rw\n",
    )

    require_persistent_mount(Path("/mnt/campo data/object-store"), mountinfo_path=mountinfo)


def test_persistent_mount_fails_closed_when_mountinfo_is_unreadable(tmp_path: Path) -> None:
    with pytest.raises(ObjectStoreNotPersistentError):
        require_persistent_mount(Path("/data/object-store"), mountinfo_path=tmp_path / "missing")


def test_production_store_is_not_opened_off_a_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.object_store as object_store_module

    monkeypatch.setattr(
        object_store_module,
        "PROC_SELF_MOUNTINFO",
        _mountinfo(tmp_path, _NO_VOLUME_MOUNTINFO),
    )
    root = tmp_path / "object-store"

    with pytest.raises(ObjectStoreNotPersistentError):
        open_configured_object_store("production", str(root))
    # Refused before the store created anything.
    assert not root.exists()


def test_non_production_store_skips_the_volume_check(tmp_path: Path) -> None:
    store = open_configured_object_store("staging", str(tmp_path / "object-store"))

    assert store.root == (tmp_path / "object-store").resolve()
