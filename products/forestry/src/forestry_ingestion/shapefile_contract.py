"""Forestry Source Contract V1: structural validation of the estate shapefile family.

The contract is derived from the observed `Gdb_Degenfeld2026_mv` source snapshot
(see products/forestry/docs/source-evidence-v1.md). It validates source structure
and projects DBF attribute rows. It deliberately does not decode SHP geometry
records, interpret business workflow, or define canonical entities.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

FieldValue = str | int | float | None


class ForestryShapefileError(ValueError):
    """Raised when a shapefile family does not satisfy the established source contract."""


# Sidecar members required by the V1 contract. `.cpg` is required because the
# contract refuses to guess a DBF text encoding; the observed source declares UTF-8.
REQUIRED_MEMBER_SUFFIXES: tuple[str, ...] = (".shp", ".shx", ".dbf", ".prj", ".cpg")

# Present in the observed source; preserved and fingerprinted when present.
OPTIONAL_MEMBER_SUFFIXES: tuple[str, ...] = (".sbn", ".sbx", ".shp.xml")

ACCEPTED_ENCODING_DECLARATIONS: tuple[str, ...] = ("UTF-8", "UTF8")

# Exact declared CRS text of the observed source (ESRI WKT for WGS 84 / UTM 18S).
# A changed declaration is a contract change requiring review, not a data change.
EXPECTED_PRJ_WKT = (
    'PROJCS["WGS_1984_UTM_Zone_18S",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",10000000.0],'
    'PARAMETER["Central_Meridian",-75.0],PARAMETER["Scale_Factor",0.9996],'
    'PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]'
)

SHAPEFILE_MAGIC = 9994
SHAPEFILE_VERSION = 1000
POLYGON_SHAPE_TYPE = 5

# DBF schema of the observed source: (dbf_name, dbf_type, length, decimals, key).
# DBF names are truncated to 10 characters by the format; the keys restore the
# lineage field names recorded in the source metadata (Cod_Predial, CodUso_2026).
DBF_FIELDS: tuple[tuple[str, str, int, int, str], ...] = (
    ("OBJECTID", "N", 10, 0, "objectid"),
    ("Nom_Predio", "C", 50, 0, "nom_predio"),
    ("N_Rodal", "C", 10, 0, "n_rodal"),
    ("Sup_ha", "F", 19, 11, "sup_ha"),
    ("Cod_Uso", "C", 25, 0, "cod_uso"),
    ("Editada", "C", 2, 0, "editada"),
    ("Uso2024", "C", 50, 0, "uso_2024"),
    ("DescUso", "C", 50, 0, "desc_uso"),
    ("Cod_Predia", "C", 10, 0, "cod_predial"),
    ("N_Rodal_te", "C", 3, 0, "n_rodal_te"),
    ("Uso2026", "C", 50, 0, "uso_2026"),
    ("CodUso_202", "C", 10, 0, "cod_uso_2026"),
    ("Shape_Leng", "F", 19, 11, "shape_leng"),
    ("Shape_Area", "F", 19, 11, "shape_area"),
)

EXPECTED_DBF_SCHEMA = tuple(
    (name, dbf_type, length, decimals) for name, dbf_type, length, decimals, _ in DBF_FIELDS
)


@dataclass(frozen=True, slots=True)
class SourceFeatureRow:
    """One DBF attribute record, blank-normalized, with its 1-based record number.

    The record number is per-snapshot ordering evidence only. No source field has
    been established as a stable cross-snapshot feature identity.
    """

    record_number: int
    values: dict[str, FieldValue]

    @property
    def objectid(self) -> int:
        value = self.values["objectid"]
        assert isinstance(value, int)
        return value

    @property
    def nom_predio(self) -> str | None:
        value = self.values["nom_predio"]
        return value if isinstance(value, str) else None

    @property
    def cod_predial(self) -> str | None:
        value = self.values["cod_predial"]
        return value if isinstance(value, str) else None

    @property
    def n_rodal(self) -> str | None:
        value = self.values["n_rodal"]
        return value if isinstance(value, str) else None

    @property
    def sup_ha(self) -> float | None:
        value = self.values["sup_ha"]
        return value if isinstance(value, float) else None


@dataclass(frozen=True, slots=True)
class ForestryShapefileTable:
    source_shp_path: Path
    member_paths: dict[str, Path]
    member_sha256: dict[str, str]
    family_fingerprint: str
    shape_type: int
    bbox: tuple[float, float, float, float]
    prj_wkt: str
    encoding: str
    rows: tuple[SourceFeatureRow, ...]


def _resolve_members(shp_path: Path) -> dict[str, Path]:
    if not shp_path.is_file():
        raise ForestryShapefileError(f"Shapefile does not exist: {shp_path}")

    base = shp_path.with_suffix("")
    members: dict[str, Path] = {}
    missing: list[str] = []

    for suffix in REQUIRED_MEMBER_SUFFIXES:
        candidate = base.parent / (base.name + suffix)
        if candidate.is_file():
            members[suffix] = candidate
        else:
            missing.append(suffix)

    if missing:
        raise ForestryShapefileError(
            f"Shapefile family is incomplete: base={base.name}; missing={missing}"
        )

    for suffix in OPTIONAL_MEMBER_SUFFIXES:
        candidate = base.parent / (base.name + suffix)
        if candidate.is_file():
            members[suffix] = candidate

    return members


def _validate_encoding_declaration(cpg_path: Path) -> str:
    declared = cpg_path.read_text(encoding="ascii", errors="replace").strip()

    if declared.upper() not in ACCEPTED_ENCODING_DECLARATIONS:
        raise ForestryShapefileError(
            f"Unsupported source encoding declaration: {declared!r}; expected UTF-8"
        )

    return "UTF-8"


def _validate_prj(prj_path: Path) -> str:
    declared = prj_path.read_text(encoding="utf-8", errors="replace").strip()

    if declared != EXPECTED_PRJ_WKT:
        raise ForestryShapefileError(
            "Declared CRS does not match the established source contract; "
            "a changed .prj requires review, not silent ingestion"
        )

    return declared


def _read_main_file_header(path: Path, *, label: str) -> tuple[int, tuple[float, ...], int]:
    """Read a .shp/.shx 100-byte header: (shape_type, bbox, declared_length_bytes)."""

    raw = path.read_bytes()

    if len(raw) < 100:
        raise ForestryShapefileError(f"{label} header is truncated: {path.name}")

    magic = struct.unpack_from(">i", raw, 0)[0]
    declared_length_words = struct.unpack_from(">i", raw, 24)[0]
    version, shape_type = struct.unpack_from("<2i", raw, 28)
    bbox = struct.unpack_from("<4d", raw, 36)

    if magic != SHAPEFILE_MAGIC or version != SHAPEFILE_VERSION:
        raise ForestryShapefileError(f"{label} is not a valid shapefile member: {path.name}")

    declared_length_bytes = declared_length_words * 2

    if declared_length_bytes != len(raw):
        raise ForestryShapefileError(
            f"{label} declared length does not match file size: {path.name}; "
            f"declared={declared_length_bytes}; actual={len(raw)}"
        )

    return shape_type, bbox, declared_length_bytes


def _read_shx_record_count(shx_path: Path, *, expected_shape_type: int) -> int:
    shape_type, _, declared_length_bytes = _read_main_file_header(shx_path, label=".shx")

    if shape_type != expected_shape_type:
        raise ForestryShapefileError(
            f".shx shape type {shape_type} disagrees with .shp shape type {expected_shape_type}"
        )

    return (declared_length_bytes - 100) // 8


def _parse_dbf_value(field_key: str, dbf_type: str, decimals: int, text: str) -> FieldValue:
    stripped = text.strip()

    if not stripped:
        return None

    if dbf_type == "C":
        return stripped

    try:
        if dbf_type == "N" and decimals == 0:
            return int(stripped)
        return float(stripped)
    except ValueError as error:
        raise ForestryShapefileError(
            f"Unparseable numeric value in field {field_key!r}: {stripped!r}"
        ) from error


def _read_dbf_rows(dbf_path: Path, *, encoding: str) -> tuple[SourceFeatureRow, ...]:
    raw = dbf_path.read_bytes()

    if len(raw) < 33:
        raise ForestryShapefileError(f".dbf header is truncated: {dbf_path.name}")

    record_count = struct.unpack_from("<I", raw, 4)[0]
    header_size = struct.unpack_from("<H", raw, 8)[0]
    record_size = struct.unpack_from("<H", raw, 10)[0]

    schema: list[tuple[str, str, int, int]] = []
    offset = 32

    while offset < header_size - 1 and raw[offset] != 0x0D:
        descriptor = raw[offset : offset + 32]

        if len(descriptor) < 32:
            raise ForestryShapefileError(f".dbf field descriptors are truncated: {dbf_path.name}")

        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        dbf_type = chr(descriptor[11])
        length = descriptor[16]
        decimals = descriptor[17]
        schema.append((name, dbf_type, length, decimals))
        offset += 32

    if tuple(schema) != EXPECTED_DBF_SCHEMA:
        unexpected = [entry for entry in schema if entry not in EXPECTED_DBF_SCHEMA]
        missing = [entry for entry in EXPECTED_DBF_SCHEMA if entry not in schema]
        raise ForestryShapefileError(
            "DBF schema mismatch against the established source contract: "
            f"unexpected={unexpected}; missing={missing}"
        )

    rows: list[SourceFeatureRow] = []

    for record_number in range(1, record_count + 1):
        start = header_size + (record_number - 1) * record_size
        record = raw[start : start + record_size]

        if len(record) < record_size:
            raise ForestryShapefileError(
                f".dbf record {record_number} is truncated: {dbf_path.name}"
            )

        if record[0] == 0x2A:  # b"*"
            raise ForestryShapefileError(
                f".dbf record {record_number} is soft-deleted; "
                "deleted source records require review"
            )

        values: dict[str, FieldValue] = {}
        cursor = 1

        for _, dbf_type, length, decimals, key in DBF_FIELDS:
            text = record[cursor : cursor + length].decode(encoding, errors="replace")
            values[key] = _parse_dbf_value(key, dbf_type, decimals, text)
            cursor += length

        rows.append(SourceFeatureRow(record_number=record_number, values=values))

    return tuple(rows)


def _fingerprint_members(members: dict[str, Path]) -> tuple[dict[str, str], str]:
    member_sha256 = {
        suffix: hashlib.sha256(path.read_bytes()).hexdigest() for suffix, path in members.items()
    }

    canonical = "".join(f"{suffix}:{member_sha256[suffix]}\n" for suffix in sorted(member_sha256))
    family_fingerprint = hashlib.sha256(canonical.encode("ascii")).hexdigest()

    return member_sha256, family_fingerprint


def load_forestry_shapefile(path: str | Path) -> ForestryShapefileTable:
    """Validate a shapefile family against Source Contract V1 and project its rows."""

    shp_path = Path(path)
    members = _resolve_members(shp_path)

    encoding = _validate_encoding_declaration(members[".cpg"])
    prj_wkt = _validate_prj(members[".prj"])

    shape_type, bbox, _ = _read_main_file_header(members[".shp"], label=".shp")

    if shape_type != POLYGON_SHAPE_TYPE:
        raise ForestryShapefileError(
            f"Unsupported shape type {shape_type}; the contract accepts polygon (5) only"
        )

    shx_record_count = _read_shx_record_count(members[".shx"], expected_shape_type=shape_type)
    rows = _read_dbf_rows(members[".dbf"], encoding=encoding)

    if len(rows) != shx_record_count:
        raise ForestryShapefileError(
            "Attribute and geometry record counts disagree: "
            f"dbf={len(rows)}; shx={shx_record_count}"
        )

    if not rows:
        raise ForestryShapefileError("Shapefile contains no features")

    member_sha256, family_fingerprint = _fingerprint_members(members)

    return ForestryShapefileTable(
        source_shp_path=shp_path,
        member_paths=members,
        member_sha256=member_sha256,
        family_fingerprint=family_fingerprint,
        shape_type=shape_type,
        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
        prj_wkt=prj_wkt,
        encoding=encoding,
        rows=rows,
    )
