"""Zip-slip and archive-bomb hardened Forestry shapefile-family ZIP inspector.

This inspects ZIP metadata only (``ZipInfo`` entries) — it never extracts
any member to disk, and never trusts a member name until it has been proven
safe. Full shapefile/CRS/feature parsing belongs to the Forestry product's
own domain code, not this platform-level intake inspector.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_MEMBERS = 2_000
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MiB
# A highly compressible synthetic payload (e.g. all-zero bytes) can exceed
# 1000x under DEFLATE; a real shapefile family does not approach this ratio,
# so 100x is a comfortable ceiling that still flags pathological archives.
MAX_COMPRESSION_RATIO = 100

_SHAPEFILE_SUFFIXES = {".shp", ".shx", ".dbf", ".prj"}


class ForestryInspectionError(RuntimeError):
    """Raised when a ZIP archive fails safe inspection."""


@dataclass(frozen=True, slots=True)
class ForestryInspectionResult:
    """Safety-checked evidence about a Forestry ZIP archive's members."""

    member_names: tuple[str, ...]
    has_shp: bool
    has_shx: bool
    has_dbf: bool
    has_prj: bool
    total_uncompressed_bytes: int


def _reject_unsafe_member_name(name: str) -> None:
    if not name or name.endswith("/"):
        return  # directory entries carry no content risk here

    parsed = PurePosixPath(name)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ForestryInspectionError(f"Unsafe archive member path: {name!r}.")


def inspect_forestry_zip(path: Path) -> ForestryInspectionResult:
    """Safely inspect a Forestry ZIP archive's member metadata."""

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()

            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise ForestryInspectionError(
                    f"Archive has {len(infos)} members, exceeding the limit of "
                    f"{MAX_ARCHIVE_MEMBERS}."
                )

            total_uncompressed_bytes = 0
            suffixes_present: set[str] = set()

            for info in infos:
                _reject_unsafe_member_name(info.filename)

                total_uncompressed_bytes += info.file_size

                compressed_size = max(info.compress_size, 1)
                if info.file_size / compressed_size > MAX_COMPRESSION_RATIO:
                    raise ForestryInspectionError(
                        f"Archive member {info.filename!r} has a pathological "
                        f"compression ratio ({info.file_size}/{compressed_size})."
                    )

                suffixes_present.add(PurePosixPath(info.filename).suffix.lower())

            if total_uncompressed_bytes > MAX_UNCOMPRESSED_BYTES:
                raise ForestryInspectionError(
                    f"Archive's total uncompressed size {total_uncompressed_bytes} "
                    f"exceeds the limit of {MAX_UNCOMPRESSED_BYTES}."
                )

            member_names = tuple(info.filename for info in infos)
    except zipfile.BadZipFile as exc:
        raise ForestryInspectionError("File is not a valid ZIP archive.") from exc

    return ForestryInspectionResult(
        member_names=member_names,
        has_shp=".shp" in suffixes_present,
        has_shx=".shx" in suffixes_present,
        has_dbf=".dbf" in suffixes_present,
        has_prj=".prj" in suffixes_present,
        total_uncompressed_bytes=total_uncompressed_bytes,
    )
