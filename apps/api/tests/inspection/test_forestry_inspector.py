"""Forestry ZIP inspector: safety and expected-member detection."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from app.inspection.forestry_inspector import (
    ForestryInspectionError,
    inspect_forestry_zip,
)


def _make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def test_detects_shapefile_family_members(tmp_path: Path) -> None:
    archive = _make_zip(
        tmp_path / "predio.zip",
        {"predio.shp": b"x", "predio.shx": b"y", "predio.dbf": b"z", "predio.prj": b"w"},
    )
    result = inspect_forestry_zip(archive)
    assert result.has_shp and result.has_shx and result.has_dbf and result.has_prj


def test_missing_members_reported_false(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path / "incomplete.zip", {"predio.shp": b"x"})
    result = inspect_forestry_zip(archive)
    assert result.has_shp is True
    assert result.has_dbf is False


def test_rejects_zip_slip_parent_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("../../etc/passwd")
        archive.writestr(info, b"pwned")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_absolute_member_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil_abs.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("/etc/passwd")
        archive.writestr(info, b"pwned")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_too_many_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "many.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for i in range(2_001):
            archive.writestr(f"file_{i}.txt", b"x")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_pathological_compression_ratio(tmp_path: Path) -> None:
    archive_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", b"0" * (50 * 1024 * 1024))

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(archive_path)


def test_rejects_non_zip_file(tmp_path: Path) -> None:
    fake = tmp_path / "not_a_zip.zip"
    fake.write_bytes(b"not actually a zip file")

    with pytest.raises(ForestryInspectionError):
        inspect_forestry_zip(fake)
