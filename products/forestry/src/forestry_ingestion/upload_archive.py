"""Strict reading of a shapefile ZIP uploaded from the Rodales dashboard.

`family_archive` extracts the pinned source ZIP from the read-only source
root, where the archive is trusted evidence. An upload is not: anyone with an
operator grant chooses its bytes. So this reader is deliberately narrower:

- The whole archive is checked from its directory before any member is read:
  member count, declared sizes (total and per member), compression ratio,
  compression method, encryption, symbolic links, and names.
- Only the members of exactly one shapefile layer are accepted (`.shp`,
  `.shx`, `.dbf`, `.prj`, `.cpg`, plus the optional `.sbn`, `.sbx`,
  `.shp.xml`), either at the root of the ZIP or inside one folder. Anything
  else, including `__MACOSX/` or a second layer, rejects the upload instead
  of being silently skipped.
- Member names are never used as paths. Each accepted member is written as
  ``family<suffix>`` under the caller's directory, and the layer name is
  returned separately as data.
- Decompression is counted as it happens, so an archive whose directory
  under-declares its sizes is cut off at the declared size instead of
  expanding without bound.

Every rejection is an `UploadArchiveError` carrying a stable ``reason`` code;
its message names structure (suffixes, counts, sizes), never file content.
"""

from __future__ import annotations

import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from forestry_ingestion.shapefile_contract import (
    OPTIONAL_MEMBER_SUFFIXES,
    REQUIRED_MEMBER_SUFFIXES,
)

# The observed Degenfeld 2026 family is 8 members and 5.9 MB uncompressed
# (2.6 MB zipped), with a highest per-member compression ratio of 12.5. These
# limits leave ample room for a larger estate while bounding what one upload
# can make the server hold.
MAX_ARCHIVE_ENTRIES = 16
MAX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
# Small members (a .cpg, a .prj) can legitimately compress far beyond any
# ratio; the ratio only matters where the bytes are large.
RATIO_CHECK_MIN_BYTES = 1024 * 1024
MAX_COMPRESSION_RATIO = 100

ACCEPTED_SUFFIXES: tuple[str, ...] = REQUIRED_MEMBER_SUFFIXES + OPTIONAL_MEMBER_SUFFIXES
MAX_LAYER_NAME_LENGTH = 120

# Server-chosen stem for every extracted member.
EXTRACTED_STEM = "family"

_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_READ_CHUNK = 1024 * 1024


class UploadArchiveError(ValueError):
    """The uploaded ZIP cannot be accepted; ``reason`` is a stable code."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class UploadArchiveMember:
    """One accepted member: its suffix and sizes (never its content)."""

    suffix: str
    compressed_bytes: int
    uncompressed_bytes: int


@dataclass(frozen=True, slots=True)
class ExtractedUploadFamily:
    """The accepted layer, written beneath the caller's directory."""

    layer_name: str
    shp_path: Path
    members: tuple[UploadArchiveMember, ...]
    total_uncompressed_bytes: int


def _member_suffix(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".shp.xml"):
        return ".shp.xml"
    return PurePosixPath(lowered).suffix


def _member_stem(name: str, suffix: str) -> str:
    return name[: len(name) - len(suffix)]


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return info.create_system == 3 and stat.S_ISLNK(mode)


def _split_member_name(name: str) -> tuple[str | None, str]:
    """Return (folder, filename), refusing anything that is not a plain name."""

    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or (len(name) >= 2 and name[1] == ":")
    ):
        raise UploadArchiveError(
            "unsafe_member", "El ZIP contiene una ruta de archivo no permitida."
        )

    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts) or len(parts) > 2:
        raise UploadArchiveError(
            "unsafe_member", "El ZIP contiene una ruta de archivo no permitida."
        )

    if len(parts) == 2:
        return parts[0], parts[1]
    return None, parts[0]


def _check_directory(
    infos: list[zipfile.ZipInfo],
) -> tuple[str, dict[str, zipfile.ZipInfo]]:
    """Validate the archive directory; return the layer name and members by suffix."""

    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise UploadArchiveError(
            "too_many_members",
            f"El ZIP tiene {len(infos)} entradas; se aceptan como máximo {MAX_ARCHIVE_ENTRIES}.",
        )

    folders: set[str | None] = set()
    by_suffix: dict[str, zipfile.ZipInfo] = {}
    stems: set[str] = set()
    unexpected: list[str] = []
    seen_names: set[str] = set()
    total = 0

    for info in infos:
        if info.flag_bits & 0x1:
            raise UploadArchiveError("encrypted", "El ZIP está protegido con contraseña.")
        if _is_symlink(info):
            raise UploadArchiveError("unsafe_member", "El ZIP contiene un enlace simbólico.")

        if info.is_dir():
            folder, rest = _split_member_name(info.filename.rstrip("/"))
            if folder is not None or not rest:
                raise UploadArchiveError(
                    "unsafe_member", "El ZIP contiene carpetas anidadas; se admite como máximo una."
                )
            folders.add(rest)
            continue

        _, filename = _split_member_name(info.filename)

        key = info.filename.lower()
        if key in seen_names:
            raise UploadArchiveError("duplicate_member", "El ZIP contiene archivos repetidos.")
        seen_names.add(key)

        if info.compress_type not in _ALLOWED_COMPRESSION:
            raise UploadArchiveError(
                "unsupported_compression", "El ZIP usa un método de compresión no admitido."
            )

        suffix = _member_suffix(filename)
        if suffix not in ACCEPTED_SUFFIXES:
            unexpected.append(suffix or "(sin extensión)")
            continue
        if suffix in by_suffix:
            raise UploadArchiveError(
                "multiple_layers", "El ZIP contiene más de una capa; cargue una sola capa por ZIP."
            )

        if (
            info.file_size >= RATIO_CHECK_MIN_BYTES
            and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO
        ):
            raise UploadArchiveError(
                "compression_ratio",
                "El ZIP tiene una proporción de compresión anómala y no se procesa.",
            )

        total += info.file_size
        stems.add(_member_stem(filename, suffix))
        by_suffix[suffix] = info

    if unexpected:
        listed = ", ".join(sorted(set(unexpected)))
        raise UploadArchiveError(
            "unexpected_member",
            f"El ZIP contiene archivos que no pertenecen a una capa shapefile ({listed}).",
        )

    member_folders = {_split_member_name(info.filename)[0] for info in by_suffix.values()}
    directory_entries = folders - member_folders - {None}
    if len(member_folders) > 1 or directory_entries:
        raise UploadArchiveError(
            "multiple_layers",
            "Los archivos de la capa deben estar juntos, en la raíz del ZIP o en una carpeta.",
        )

    if len(stems) > 1:
        raise UploadArchiveError(
            "multiple_layers",
            "Los archivos del ZIP no comparten un mismo nombre de capa.",
        )

    missing = [suffix for suffix in REQUIRED_MEMBER_SUFFIXES if suffix not in by_suffix]
    if missing:
        raise UploadArchiveError(
            "missing_members",
            "Faltan archivos obligatorios de la capa: " + ", ".join(missing) + ".",
        )

    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise UploadArchiveError(
            "too_large_uncompressed",
            "El contenido descomprimido del ZIP supera el máximo de "
            f"{MAX_TOTAL_UNCOMPRESSED_BYTES // (1024 * 1024)} MiB.",
        )

    layer_name = stems.pop()
    if not layer_name.strip() or len(layer_name) > MAX_LAYER_NAME_LENGTH:
        raise UploadArchiveError("unsafe_member", "El nombre de la capa no es válido.")

    return layer_name, by_suffix


def extract_upload_archive(zip_path: str | Path, destination: str | Path) -> ExtractedUploadFamily:
    """Validate an uploaded ZIP and write its one layer under ``destination``."""

    destination_path = Path(destination)
    if not destination_path.is_dir():
        raise ValueError(f"Extraction destination is not a directory: {destination_path}")

    try:
        with zipfile.ZipFile(Path(zip_path)) as archive:
            layer_name, by_suffix = _check_directory(archive.infolist())
            written_total = 0
            members: list[UploadArchiveMember] = []

            for suffix, info in sorted(by_suffix.items()):
                target = destination_path / f"{EXTRACTED_STEM}{suffix}"
                written = 0
                with archive.open(info) as source, target.open("wb") as sink:
                    while chunk := source.read(_READ_CHUNK):
                        written += len(chunk)
                        written_total += len(chunk)
                        if written > info.file_size or written_total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                            raise UploadArchiveError(
                                "too_large_uncompressed",
                                "El ZIP se expande más de lo que declara y no se procesa.",
                            )
                        sink.write(chunk)
                members.append(
                    UploadArchiveMember(
                        suffix=suffix,
                        compressed_bytes=info.compress_size,
                        uncompressed_bytes=written,
                    )
                )
    except zipfile.BadZipFile as error:
        raise UploadArchiveError("not_zip", "El archivo no es un ZIP válido.") from error
    except (EOFError, zlib.error, zipfile.LargeZipFile, NotImplementedError) as error:
        raise UploadArchiveError("not_zip", "El ZIP está dañado o no se puede leer.") from error

    return ExtractedUploadFamily(
        layer_name=layer_name,
        shp_path=destination_path / f"{EXTRACTED_STEM}.shp",
        members=tuple(members),
        total_uncompressed_bytes=written_total,
    )
