"""Synthetic Forestry shapefile-family builders shared by Forestry tests.

Everything written here is fully synthetic; no real Forestry client data is
used or reproduced. The writers emit the binary shapefile structures the
Source Contract V1 parser and the geometry decoder consume.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

from forestry_ingestion.shapefile_contract import DBF_FIELDS, EXPECTED_PRJ_WKT

FieldSpec = tuple[str, str, int, int]
Ring = list[tuple[float, float]]
RecordGeometry = list[Ring] | None  # None writes a null-shape (type 0) record

DEFAULT_FIELD_SPECS: tuple[FieldSpec, ...] = tuple(
    (name, dbf_type, length, decimals) for name, dbf_type, length, decimals, _ in DBF_FIELDS
)

# Clockwise ring: a valid shapefile exterior per the ESRI winding convention.
SQUARE: Ring = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)]


def square_ring(x0: float, y0: float, size: float, *, clockwise: bool = True) -> Ring:
    counter_clockwise: Ring = [
        (x0, y0),
        (x0 + size, y0),
        (x0 + size, y0 + size),
        (x0, y0 + size),
        (x0, y0),
    ]
    return list(reversed(counter_clockwise)) if clockwise else counter_clockwise


def source_row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {key: None for _, _, _, _, key in DBF_FIELDS}

    values.update(
        {
            "objectid": 1,
            "nom_predio": "Predio Sintético",
            "n_rodal": "12",
            "sup_ha": 1.5,
            "cod_uso": "Xx01",
            "uso_2024": "CLASE A",
            "desc_uso": "Descripción sintética",
            "cod_predial": "PS",
            "uso_2026": "CLASE A",
            "cod_uso_2026": "Xx01",
            "shape_leng": 40.0,
            "shape_area": 15000.0,
        }
    )

    values.update(overrides)
    return values


def write_dbf(
    path: Path,
    rows: list[dict[str, object]],
    *,
    field_specs: tuple[FieldSpec, ...] = DEFAULT_FIELD_SPECS,
    deleted_records: frozenset[int] = frozenset(),
) -> None:
    header_size = 32 + 32 * len(field_specs) + 1
    record_size = 1 + sum(length for _, _, length, _ in field_specs)

    buffer = bytearray()
    buffer += bytes([0x03, 26, 8, 29])
    buffer += struct.pack("<I", len(rows))
    buffer += struct.pack("<HH", header_size, record_size)
    buffer += bytes(20)

    for name, dbf_type, length, decimals in field_specs:
        buffer += name.encode("ascii").ljust(11, b"\x00")
        buffer += dbf_type.encode("ascii")
        buffer += bytes(4)
        buffer += bytes([length, decimals])
        buffer += bytes(14)

    buffer += b"\x0d"

    keys = [key for _, _, _, _, key in DBF_FIELDS]

    for index, row in enumerate(rows):
        buffer += b"*" if index in deleted_records else b" "

        for (name, dbf_type, length, decimals), key in zip(field_specs, keys, strict=True):
            value = row.get(key)

            if value is None:
                text = ""
            elif dbf_type == "C" or isinstance(value, str):
                text = str(value)
            else:
                assert isinstance(value, int | float)
                text = str(value) if dbf_type == "N" and decimals == 0 else f"{value:.{decimals}f}"

            raw = text.encode("utf-8")

            if len(raw) > length:
                raise AssertionError(f"synthetic value too wide for {name}: {text!r}")

            buffer += raw.ljust(length, b" ") if dbf_type == "C" else raw.rjust(length, b" ")

    buffer += b"\x1a"
    path.write_bytes(bytes(buffer))


def _main_header(
    *,
    total_bytes: int,
    shape_type: int,
    bbox: tuple[float, float, float, float],
) -> bytes:
    header = struct.pack(">i", 9994) + bytes(20) + struct.pack(">i", total_bytes // 2)
    header += struct.pack("<2i", 1000, shape_type)
    header += struct.pack("<4d", *bbox)
    header += struct.pack("<4d", 0.0, 0.0, 0.0, 0.0)
    return header


def _polygon_record_content(shape_type: int, rings: list[Ring]) -> bytes:
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]

    content = struct.pack("<i", shape_type)
    content += struct.pack("<4d", min(xs), min(ys), max(xs), max(ys))
    content += struct.pack("<2i", len(rings), sum(len(ring) for ring in rings))

    offset = 0
    for ring in rings:
        content += struct.pack("<i", offset)
        offset += len(ring)

    for ring in rings:
        for x, y in ring:
            content += struct.pack("<2d", x, y)

    return content


def write_shp_and_shx(
    shp_path: Path,
    shx_path: Path,
    geometries: list[RecordGeometry],
    *,
    shape_type: int = 5,
    shx_extra_records: int = 0,
) -> None:
    records = b""
    index_entries = b""
    offset_words = 50

    all_points = [point for rings in geometries if rings for ring in rings for point in ring]
    bbox = (
        (
            min(x for x, _ in all_points),
            min(y for _, y in all_points),
            max(x for x, _ in all_points),
            max(y for _, y in all_points),
        )
        if all_points
        else (0.0, 0.0, 0.0, 0.0)
    )

    for record_number, rings in enumerate(geometries, start=1):
        if rings is None:
            content = struct.pack("<i", 0)
        else:
            content = _polygon_record_content(shape_type, rings)

        content_words = len(content) // 2
        records += struct.pack(">2i", record_number, content_words) + content
        index_entries += struct.pack(">2i", offset_words, content_words)
        offset_words += 4 + content_words

    for _ in range(shx_extra_records):
        index_entries += struct.pack(">2i", offset_words, 0)

    shp_path.write_bytes(
        _main_header(total_bytes=100 + len(records), shape_type=shape_type, bbox=bbox) + records
    )
    shx_path.write_bytes(
        _main_header(
            total_bytes=100 + len(index_entries),
            shape_type=shape_type,
            bbox=bbox,
        )
        + index_entries
    )


def write_family(
    directory: Path,
    rows: list[dict[str, object]],
    *,
    base_name: str = "synthetic",
    geometries: list[RecordGeometry] | None = None,
    field_specs: tuple[FieldSpec, ...] = DEFAULT_FIELD_SPECS,
    shape_type: int = 5,
    prj_text: str = EXPECTED_PRJ_WKT,
    cpg_text: str = "UTF-8",
    omit_suffixes: frozenset[str] = frozenset(),
    shx_extra_records: int = 0,
    deleted_records: frozenset[int] = frozenset(),
) -> Path:
    base = directory / base_name

    if geometries is None:
        geometries = [[SQUARE] for _ in rows]

    write_shp_and_shx(
        base.with_suffix(".shp"),
        base.with_suffix(".shx"),
        geometries,
        shape_type=shape_type,
        shx_extra_records=shx_extra_records,
    )
    write_dbf(
        base.with_suffix(".dbf"),
        rows,
        field_specs=field_specs,
        deleted_records=deleted_records,
    )
    base.with_suffix(".prj").write_text(prj_text, encoding="utf-8")
    base.with_suffix(".cpg").write_text(cpg_text, encoding="ascii")

    for suffix in omit_suffixes:
        base.with_suffix(suffix).unlink()

    return base.with_suffix(".shp")


def write_family_zip(
    zip_path: Path,
    family_directory: Path,
    *,
    arcname_prefix: str = "",
) -> Path:
    """Package an already-written family directory as a source-style ZIP."""

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in sorted(family_directory.iterdir()):
            if member.is_file():
                archive.write(member, arcname=f"{arcname_prefix}{member.name}")

    return zip_path
