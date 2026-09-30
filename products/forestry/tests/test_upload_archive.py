"""Strict reading of uploaded Rodales ZIPs (synthetic archives only)."""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path

import pytest

from forestry_family_fixtures import family_members, source_row, zip_bytes
from forestry_ingestion import upload_archive
from forestry_ingestion.upload_archive import (
    EXTRACTED_STEM,
    UploadArchiveError,
    extract_upload_archive,
)


def _members(tmp_path: Path, base_name: str = "Capa_2026") -> dict[str, bytes]:
    return family_members(tmp_path / "family", [source_row()], base_name=base_name)


def _extract(tmp_path: Path, data: bytes) -> upload_archive.ExtractedUploadFamily:
    archive = tmp_path / "upload.zip"
    archive.write_bytes(data)
    out = tmp_path / "out"
    out.mkdir()
    return extract_upload_archive(archive, out)


def _reason(tmp_path: Path, data: bytes) -> str:
    with pytest.raises(UploadArchiveError) as caught:
        _extract(tmp_path, data)
    return caught.value.reason


def test_a_flat_family_is_extracted_under_server_chosen_names(tmp_path: Path) -> None:
    family = _extract(tmp_path, zip_bytes(_members(tmp_path)))

    assert family.layer_name == "Capa_2026"
    assert family.shp_path.name == f"{EXTRACTED_STEM}.shp"
    assert sorted(path.name for path in family.shp_path.parent.iterdir()) == [
        f"{EXTRACTED_STEM}{suffix}" for suffix in (".cpg", ".dbf", ".prj", ".shp", ".shx")
    ]
    assert {member.suffix for member in family.members} == {".cpg", ".dbf", ".prj", ".shp", ".shx"}


def test_a_family_inside_one_folder_is_accepted(tmp_path: Path) -> None:
    members = {f"Entrega/{name}": content for name, content in _members(tmp_path).items()}
    members = {"Entrega/": b"", **members}

    assert _extract(tmp_path, zip_bytes(members)).layer_name == "Capa_2026"


def test_optional_members_and_uppercase_suffixes_are_accepted(tmp_path: Path) -> None:
    members = {name.replace(".shp", ".SHP"): data for name, data in _members(tmp_path).items()}
    members["Capa_2026.shp.xml"] = b"<metadata/>"
    members["Capa_2026.sbn"] = b"\x00" * 10

    family = _extract(tmp_path, zip_bytes(members))

    assert {member.suffix for member in family.members} >= {".shp.xml", ".sbn", ".shp"}


@pytest.mark.parametrize(
    "bad_name",
    [
        "../Capa_2026.shp",
        "/abs/Capa_2026.shp",
        "C:/Capa_2026.shp",
        "a\\Capa_2026.shp",
        "a/b/Capa_2026.shp",
        "./Capa_2026.shp",
    ],
)
def test_unsafe_member_names_are_refused(tmp_path: Path, bad_name: str) -> None:
    members = _members(tmp_path)
    members[bad_name] = members.pop("Capa_2026.shp")

    assert _reason(tmp_path, zip_bytes(members)) == "unsafe_member"
    assert not (tmp_path / "Capa_2026.shp").exists()


def test_a_symbolic_link_member_is_refused(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in _members(tmp_path).items():
            archive.writestr(name, content)
        link = zipfile.ZipInfo("Capa_2026.sbn")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive.writestr(link, "/etc/passwd")

    assert _reason(tmp_path, buffer.getvalue()) == "unsafe_member"


def test_unexpected_members_are_refused_not_skipped(tmp_path: Path) -> None:
    members = _members(tmp_path)
    members["leeme.txt"] = b"hola"

    assert _reason(tmp_path, zip_bytes(members)) == "unexpected_member"


def test_mac_resource_forks_are_refused(tmp_path: Path) -> None:
    members = _members(tmp_path)
    members["__MACOSX/._Capa_2026.shp"] = b"junk"

    # Two folders' worth of members (root and __MACOSX) or a second .shp.
    assert _reason(tmp_path, zip_bytes(members)) in {"multiple_layers", "unexpected_member"}


def test_two_layers_are_refused(tmp_path: Path) -> None:
    members = _members(tmp_path)
    members.update(family_members(tmp_path / "second", [source_row()], base_name="Otra"))

    assert _reason(tmp_path, zip_bytes(members)) == "multiple_layers"


def test_members_split_across_folders_are_refused(tmp_path: Path) -> None:
    members = _members(tmp_path)
    members["otra/Capa_2026.prj"] = members.pop("Capa_2026.prj")

    assert _reason(tmp_path, zip_bytes(members)) == "multiple_layers"


def test_a_missing_required_member_is_named(tmp_path: Path) -> None:
    members = _members(tmp_path)
    del members["Capa_2026.prj"]

    with pytest.raises(UploadArchiveError) as caught:
        _extract(tmp_path, zip_bytes(members))

    assert caught.value.reason == "missing_members"
    assert ".prj" in str(caught.value)


def test_duplicate_members_are_refused(tmp_path: Path) -> None:
    members = _members(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
        with pytest.warns(UserWarning):
            archive.writestr("Capa_2026.shp", members["Capa_2026.shp"])

    assert _reason(tmp_path, buffer.getvalue()) == "duplicate_member"


def test_too_many_entries_are_refused(tmp_path: Path) -> None:
    members = _members(tmp_path)
    for index in range(upload_archive.MAX_ARCHIVE_ENTRIES):
        members[f"Capa_2026.extra{index}"] = b""

    assert _reason(tmp_path, zip_bytes(members)) == "too_many_members"


def test_a_compression_bomb_is_refused_before_extraction(tmp_path: Path) -> None:
    members = _members(tmp_path)
    members["Capa_2026.shp.xml"] = b"\x00" * (8 * 1024 * 1024)

    assert _reason(tmp_path, zip_bytes(members)) == "compression_ratio"
    assert not any((tmp_path / "out").iterdir())


def test_the_declared_total_size_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upload_archive, "MAX_TOTAL_UNCOMPRESSED_BYTES", 100)

    assert _reason(tmp_path, zip_bytes(_members(tmp_path))) == "too_large_uncompressed"


def test_an_under_declared_member_cannot_expand_past_its_declaration(tmp_path: Path) -> None:
    members = _members(tmp_path)
    members["Capa_2026.shp.xml"] = b"A" * 5000
    data = bytearray(zip_bytes(members))

    # Rewrite the .shp.xml uncompressed size (local header and central
    # directory) to 10 bytes: the directory now lies about the expansion.
    name = b"Capa_2026.shp.xml"
    for signature, size_offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        start = 0
        while (index := data.find(signature, start)) != -1:
            name_offset = index + (30 if signature == b"PK\x03\x04" else 46)
            if data[name_offset : name_offset + len(name)] == name:
                struct.pack_into("<I", data, index + size_offset, 10)
            start = index + 4

    assert _reason(tmp_path, bytes(data)) in {"too_large_uncompressed", "not_zip"}


def test_encrypted_members_are_refused(tmp_path: Path) -> None:
    data = bytearray(zip_bytes(_members(tmp_path)))
    index = data.find(b"PK\x01\x02")
    flags = struct.unpack_from("<H", data, index + 8)[0]
    struct.pack_into("<H", data, index + 8, flags | 0x1)

    assert _reason(tmp_path, bytes(data)) == "encrypted"


def test_unsupported_compression_is_refused(tmp_path: Path) -> None:
    data = zip_bytes(_members(tmp_path), compression=zipfile.ZIP_BZIP2)

    assert _reason(tmp_path, data) == "unsupported_compression"


@pytest.mark.parametrize("payload", [b"", b"not a zip at all", b"PK\x03\x04garbage"])
def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path, payload: bytes) -> None:
    assert _reason(tmp_path, payload) == "not_zip"


def test_a_corrupt_member_stream_is_refused(tmp_path: Path) -> None:
    data = bytearray(zip_bytes(_members(tmp_path)))
    # Flip bytes inside the first member's compressed data.
    index = data.find(b"PK\x03\x04")
    name_length, extra_length = struct.unpack_from("<HH", data, index + 26)
    body = index + 30 + name_length + extra_length
    for offset in range(body, body + 8):
        data[offset] ^= 0xFF

    assert _reason(tmp_path, bytes(data)) == "not_zip"
