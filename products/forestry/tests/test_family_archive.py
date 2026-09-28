"""Safe extraction tests for Forestry source ZIP archives.

No real Forestry client data is used or reproduced here.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from forestry_family_fixtures import source_row, write_family, write_family_zip
from forestry_ingestion.family_archive import (
    ForestryArchiveError,
    extract_family_archive,
)
from forestry_ingestion.shapefile_contract import load_forestry_shapefile


def _build_zip(tmp_path: Path, *, arcname_prefix: str = "") -> Path:
    family_dir = tmp_path / "family"
    family_dir.mkdir()
    write_family(family_dir, [source_row()])
    return write_family_zip(
        tmp_path / "snapshot.zip",
        family_dir,
        arcname_prefix=arcname_prefix,
    )


def test_extracts_family_and_returns_shp_path(tmp_path: Path) -> None:
    zip_path = _build_zip(tmp_path)
    destination = tmp_path / "extracted"
    destination.mkdir()

    shp_path = extract_family_archive(zip_path, destination)

    assert shp_path.name == "synthetic.shp"
    assert shp_path.is_relative_to(destination)

    table = load_forestry_shapefile(shp_path)
    assert len(table.rows) == 1


def test_extracts_family_nested_in_a_folder(tmp_path: Path) -> None:
    zip_path = _build_zip(tmp_path, arcname_prefix="carpeta/interna/")
    destination = tmp_path / "extracted"
    destination.mkdir()

    shp_path = extract_family_archive(zip_path, destination)

    assert shp_path.name == "synthetic.shp"
    assert load_forestry_shapefile(shp_path).rows


def test_rejects_archive_without_a_shapefile(tmp_path: Path) -> None:
    zip_path = tmp_path / "empty.zip"

    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("nota.txt", "sin shapefile")

    destination = tmp_path / "extracted"
    destination.mkdir()

    with pytest.raises(ForestryArchiveError, match="exactly one .shp"):
        extract_family_archive(zip_path, destination)


def test_rejects_archive_with_two_shapefiles(tmp_path: Path) -> None:
    family_dir = tmp_path / "family"
    family_dir.mkdir()
    write_family(family_dir, [source_row()])
    write_family(family_dir, [source_row()], base_name="segunda")
    zip_path = write_family_zip(tmp_path / "snapshot.zip", family_dir)

    destination = tmp_path / "extracted"
    destination.mkdir()

    with pytest.raises(ForestryArchiveError, match="exactly one .shp"):
        extract_family_archive(zip_path, destination)


@pytest.mark.parametrize("evil_name", ["../evil.shp", "/abs/evil.shp", "a/../../evil.shp"])
def test_rejects_unsafe_member_paths(tmp_path: Path, evil_name: str) -> None:
    zip_path = tmp_path / "evil.zip"

    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(evil_name, b"payload")

    destination = tmp_path / "extracted"
    destination.mkdir()

    with pytest.raises(ForestryArchiveError, match="unsafe member path"):
        extract_family_archive(zip_path, destination)

    assert list(destination.iterdir()) == []


def test_rejects_non_zip_input(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "corrupt.zip"
    not_a_zip.write_bytes(b"this is not a zip archive")

    destination = tmp_path / "extracted"
    destination.mkdir()

    with pytest.raises(ForestryArchiveError, match="not a readable ZIP"):
        extract_family_archive(not_a_zip, destination)
