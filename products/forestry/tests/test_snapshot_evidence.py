"""Quality-flag evidence tests over synthetic parsed rows and geometries.

Every rule tested here reproduces an anomaly class already established by
Source Evidence V1. No real Forestry client data is used or reproduced.
"""

from __future__ import annotations

from forestry_ingestion.shapefile_contract import DBF_FIELDS, FieldValue, SourceFeatureRow
from forestry_ingestion.shapefile_geometry import SourceFeatureGeometry
from forestry_ingestion.snapshot_evidence import (
    FLAG_BLANK_RODAL,
    FLAG_DUPLICATE_GEOMETRY,
    FLAG_DUPLICATE_PREDIO_RODAL_KEY,
    FLAG_INVALID_GEOMETRY,
    FLAG_PREDIO_CODE_NAME_ANOMALY,
    FLAG_TRUNCATED_USE_CODE_2026,
    compute_quality_flags,
)


def make_row(record_number: int, **overrides: FieldValue) -> SourceFeatureRow:
    values: dict[str, FieldValue] = {key: None for _, _, _, _, key in DBF_FIELDS}
    values.update(
        {
            "objectid": record_number,
            "nom_predio": "Predio Uno",
            "cod_predial": "P1",
            "n_rodal": str(100 + record_number),
        }
    )
    values.update(overrides)
    return SourceFeatureRow(record_number=record_number, values=values)


def make_geometry(
    record_number: int,
    *,
    wkb: bytes | None = None,
    is_valid: bool = True,
    invalid_reason: str | None = None,
) -> SourceFeatureGeometry:
    return SourceFeatureGeometry(
        record_number=record_number,
        wkb=wkb if wkb is not None else record_number.to_bytes(4, "big"),
        is_valid=is_valid,
        invalid_reason=invalid_reason,
        ring_count=1,
        part_count=1,
        area_source_units=1.0,
    )


def test_clean_snapshot_produces_no_flags() -> None:
    rows = [make_row(1), make_row(2)]
    geometries = [make_geometry(1), make_geometry(2)]

    flags = compute_quality_flags(rows, geometries)

    assert flags == {1: (), 2: ()}


def test_invalid_geometry_is_flagged() -> None:
    rows = [make_row(1)]
    geometries = [make_geometry(1, is_valid=False, invalid_reason="Self-intersection[1 1]")]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == (FLAG_INVALID_GEOMETRY,)


def test_identical_geometry_content_is_flagged_on_every_copy() -> None:
    rows = [make_row(1), make_row(2), make_row(3)]
    geometries = [
        make_geometry(1, wkb=b"same"),
        make_geometry(2, wkb=b"same"),
        make_geometry(3, wkb=b"different"),
    ]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == (FLAG_DUPLICATE_GEOMETRY,)
    assert flags[2] == (FLAG_DUPLICATE_GEOMETRY,)
    assert flags[3] == ()


def test_blank_rodal_is_flagged() -> None:
    rows = [make_row(1, n_rodal=None), make_row(2)]
    geometries = [make_geometry(1), make_geometry(2)]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == (FLAG_BLANK_RODAL,)
    assert flags[2] == ()


def test_duplicate_predio_rodal_key_is_flagged_on_every_holder() -> None:
    rows = [
        make_row(1, n_rodal="856"),
        make_row(2, n_rodal="856"),
        make_row(3, n_rodal="857"),
        make_row(4, cod_predial="P2", nom_predio="Predio Dos", n_rodal="856"),
    ]
    geometries = [make_geometry(number) for number in (1, 2, 3, 4)]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == (FLAG_DUPLICATE_PREDIO_RODAL_KEY,)
    assert flags[2] == (FLAG_DUPLICATE_PREDIO_RODAL_KEY,)
    assert flags[3] == ()
    assert flags[4] == ()


def test_blank_rodal_does_not_participate_in_duplicate_keys() -> None:
    rows = [make_row(1, n_rodal=None), make_row(2, n_rodal=None)]
    geometries = [make_geometry(1), make_geometry(2)]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == (FLAG_BLANK_RODAL,)
    assert flags[2] == (FLAG_BLANK_RODAL,)


def test_minority_predio_code_name_pair_is_flagged() -> None:
    rows = [
        make_row(1, cod_predial="PU2", nom_predio="Purretrun2"),
        make_row(2, cod_predial="PU2", nom_predio="Purretrun2"),
        make_row(3, cod_predial="PU2", nom_predio="Purretrun"),
        make_row(4, cod_predial="PU1", nom_predio="Purretrun"),
        make_row(5, cod_predial="PU1", nom_predio="Purretrun"),
    ]
    geometries = [make_geometry(number) for number in (1, 2, 3, 4, 5)]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == ()
    assert flags[2] == ()
    assert flags[3] == (FLAG_PREDIO_CODE_NAME_ANOMALY,)
    assert flags[4] == ()
    assert flags[5] == ()


def test_truncated_use_code_2026_is_flagged() -> None:
    rows = [make_row(1, cod_uso_2026="RaCoRo01P*"), make_row(2, cod_uso_2026="Pi26")]
    geometries = [make_geometry(1), make_geometry(2)]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == (FLAG_TRUNCATED_USE_CODE_2026,)
    assert flags[2] == ()


def test_flags_combine_and_are_sorted() -> None:
    rows = [make_row(1, n_rodal=None, cod_uso_2026="RaCoRo01P*")]
    geometries = [make_geometry(1, is_valid=False, invalid_reason="Self-intersection[0 0]")]

    flags = compute_quality_flags(rows, geometries)

    assert flags[1] == tuple(
        sorted(
            (
                FLAG_BLANK_RODAL,
                FLAG_INVALID_GEOMETRY,
                FLAG_TRUNCATED_USE_CODE_2026,
            )
        )
    )
