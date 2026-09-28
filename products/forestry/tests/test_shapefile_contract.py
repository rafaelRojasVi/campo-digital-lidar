"""Source Contract V1 tests using fully synthetic shapefile families.

No real Forestry client data is used or reproduced here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forestry_family_fixtures import (
    DEFAULT_FIELD_SPECS,
    source_row,
    write_family,
)
from forestry_ingestion.shapefile_contract import (
    EXPECTED_PRJ_WKT,
    ForestryShapefileError,
    load_forestry_shapefile,
)


def test_loads_valid_family_and_projects_rows(tmp_path: Path) -> None:
    shp_path = write_family(
        tmp_path,
        [
            source_row(),
            source_row(
                objectid=2,
                n_rodal=None,
                editada="mv",
                cod_uso="Xx01",
                cod_uso_2026="Yy26",
                sup_ha=0.25,
            ),
        ],
    )

    table = load_forestry_shapefile(shp_path)

    assert table.shape_type == 5
    assert table.encoding == "UTF-8"
    assert table.prj_wkt == EXPECTED_PRJ_WKT
    assert table.bbox == (0.0, 0.0, 10.0, 10.0)
    assert len(table.rows) == 2

    first, second = table.rows

    assert first.record_number == 1
    assert first.objectid == 1
    assert first.nom_predio == "Predio Sintético"
    assert first.cod_predial == "PS"
    assert first.n_rodal == "12"
    assert first.sup_ha == pytest.approx(1.5)

    assert second.record_number == 2
    assert second.n_rodal is None
    assert second.values["editada"] == "mv"
    assert second.values["cod_uso_2026"] == "Yy26"


def test_fingerprints_are_deterministic_and_content_sensitive(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    shp_path = write_family(tmp_path / "a", [source_row()])
    other_path = write_family(tmp_path / "b", [source_row()])
    changed_path = write_family(
        tmp_path / "b",
        [source_row(desc_uso="Otra descripción")],
        base_name="changed",
    )

    table = load_forestry_shapefile(shp_path)
    same_content = load_forestry_shapefile(other_path)
    changed = load_forestry_shapefile(changed_path)

    assert set(table.member_sha256) == {".shp", ".shx", ".dbf", ".prj", ".cpg"}
    assert all(len(digest) == 64 for digest in table.member_sha256.values())
    assert table.family_fingerprint == same_content.family_fingerprint
    assert table.family_fingerprint != changed.family_fingerprint


def test_rejects_missing_required_member(tmp_path: Path) -> None:
    shp_path = write_family(tmp_path, [source_row()], omit_suffixes=frozenset({".prj"}))

    with pytest.raises(ForestryShapefileError, match="incomplete.*prj"):
        load_forestry_shapefile(shp_path)


def test_rejects_missing_encoding_declaration(tmp_path: Path) -> None:
    shp_path = write_family(tmp_path, [source_row()], omit_suffixes=frozenset({".cpg"}))

    with pytest.raises(ForestryShapefileError, match="incomplete.*cpg"):
        load_forestry_shapefile(shp_path)


def test_rejects_unsupported_encoding_declaration(tmp_path: Path) -> None:
    shp_path = write_family(tmp_path, [source_row()], cpg_text="ISO-8859-1")

    with pytest.raises(ForestryShapefileError, match="Unsupported source encoding"):
        load_forestry_shapefile(shp_path)


def test_rejects_changed_crs_declaration(tmp_path: Path) -> None:
    shp_path = write_family(
        tmp_path,
        [source_row()],
        prj_text=EXPECTED_PRJ_WKT.replace("18S", "19S"),
    )

    with pytest.raises(ForestryShapefileError, match="Declared CRS does not match"):
        load_forestry_shapefile(shp_path)


def test_rejects_renamed_dbf_field(tmp_path: Path) -> None:
    field_specs = list(DEFAULT_FIELD_SPECS)
    field_specs[6] = ("Uso2025", "C", 50, 0)

    shp_path = write_family(tmp_path, [source_row()], field_specs=tuple(field_specs))

    with pytest.raises(ForestryShapefileError, match="DBF schema mismatch.*Uso2025"):
        load_forestry_shapefile(shp_path)


def test_rejects_changed_field_width(tmp_path: Path) -> None:
    field_specs = list(DEFAULT_FIELD_SPECS)
    field_specs[1] = ("Nom_Predio", "C", 60, 0)

    shp_path = write_family(tmp_path, [source_row()], field_specs=tuple(field_specs))

    with pytest.raises(ForestryShapefileError, match="DBF schema mismatch"):
        load_forestry_shapefile(shp_path)


def test_rejects_non_polygon_shape_type(tmp_path: Path) -> None:
    shp_path = write_family(tmp_path, [source_row()], shape_type=3)

    with pytest.raises(ForestryShapefileError, match="Unsupported shape type 3"):
        load_forestry_shapefile(shp_path)


def test_rejects_record_count_disagreement(tmp_path: Path) -> None:
    shp_path = write_family(tmp_path, [source_row()], shx_extra_records=1)

    with pytest.raises(ForestryShapefileError, match="record counts disagree"):
        load_forestry_shapefile(shp_path)


def test_rejects_soft_deleted_records(tmp_path: Path) -> None:
    shp_path = write_family(
        tmp_path,
        [source_row(), source_row(objectid=2)],
        deleted_records=frozenset({1}),
    )

    with pytest.raises(ForestryShapefileError, match="soft-deleted"):
        load_forestry_shapefile(shp_path)


def test_rejects_empty_family(tmp_path: Path) -> None:
    shp_path = write_family(tmp_path, [])

    with pytest.raises(ForestryShapefileError, match="no features"):
        load_forestry_shapefile(shp_path)


def test_rejects_missing_shapefile(tmp_path: Path) -> None:
    with pytest.raises(ForestryShapefileError, match="does not exist"):
        load_forestry_shapefile(tmp_path / "missing.shp")


def test_rejects_unparseable_numeric_value(tmp_path: Path) -> None:
    shp_path = write_family(tmp_path, [source_row(objectid="**")])

    with pytest.raises(ForestryShapefileError, match="Unparseable numeric value"):
        load_forestry_shapefile(shp_path)
