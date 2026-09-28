"""Safe extraction of the Forestry source ZIP into a caller-owned directory.

The observed Forestry source arrives as one ZIP containing one shapefile
family. Extraction never touches the archive itself, refuses member paths
that would escape the destination, and requires exactly one `.shp` so that a
snapshot is never assembled from an ambiguous archive.
"""

from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath


class ForestryArchiveError(ValueError):
    """Raised when a Forestry source archive cannot be extracted safely."""


def extract_family_archive(zip_path: str | Path, destination: str | Path) -> Path:
    """Extract a source ZIP beneath `destination` and return the single `.shp` path."""

    archive_path = Path(zip_path)
    destination_path = Path(destination)

    if not destination_path.is_dir():
        raise ForestryArchiveError(f"Extraction destination is not a directory: {destination_path}")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            targets = {
                member.filename: _safe_member_target(destination_path, member.filename)
                for member in members
            }

            shp_targets = [
                target for target in targets.values() if target.name.lower().endswith(".shp")
            ]

            if len(shp_targets) != 1:
                raise ForestryArchiveError(
                    "Source archive must contain exactly one .shp; "
                    f"found {len(shp_targets)} in {archive_path.name}"
                )

            for member in members:
                target = targets[member.filename]
                target.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as source, target.open("wb") as sink:
                    while chunk := source.read(1024 * 1024):
                        sink.write(chunk)
    except zipfile.BadZipFile as error:
        raise ForestryArchiveError(
            f"Source archive is not a readable ZIP: {archive_path.name}"
        ) from error

    return shp_targets[0]


def _safe_member_target(destination: Path, member_name: str) -> Path:
    parsed = PurePosixPath(member_name)

    if (
        parsed.is_absolute()
        or "\\" in member_name
        or ".." in parsed.parts
        or any(part in {"", "."} for part in parsed.parts)
    ):
        raise ForestryArchiveError(
            f"Source archive contains an unsafe member path: {member_name!r}"
        )

    return destination.joinpath(*parsed.parts)
