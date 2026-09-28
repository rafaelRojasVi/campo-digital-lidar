"""Integration tests for Forestry snapshot ingestion into PostGIS.

All source material is synthetic (shared builders from the Forestry unit
tests); no real Forestry client data is used or reproduced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app import forestry_persistence
from app.forestry_persistence import (
    ForestryIngestionError,
    ingest_forestry_snapshot,
)
from app.forestry_reads import (
    list_shapefile_snapshots,
    predio_distribution,
    snapshot_summary,
    use_distribution,
    use_field_comparison,
)
from sqlalchemy import Connection, text

from forestry_family_fixtures import (
    RecordGeometry,
    source_row,
    square_ring,
    write_family,
    write_family_zip,
)
from forestry_ingestion.shapefile_contract import (
    EXPECTED_PRJ_WKT,
    ForestryShapefileError,
)

SYSTEM_KEY = "integration_source"

BOWTIE = [(0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0), (0.0, 0.0)]


def build_zip(
    source_root: Path,
    rows: list[dict[str, object]],
    *,
    zip_name: str = "snapshot.zip",
    base_name: str = "synthetic",
    geometries: list[RecordGeometry] | None = None,
    prj_text: str = EXPECTED_PRJ_WKT,
    arcname_prefix: str = "",
) -> str:
    """Write a synthetic family ZIP under the source root; return its relative path."""

    family_dir = source_root / f"build-{zip_name}"
    family_dir.mkdir()

    if geometries is None:
        # Distinct geometries per row so the duplicate-geometry evidence rule
        # only fires when a test asks for it explicitly.
        geometries = [[square_ring(20.0 * index, 0.0, 10.0 + index)] for index in range(len(rows))]

    write_family(
        family_dir,
        rows,
        base_name=base_name,
        geometries=geometries,
        prj_text=prj_text,
    )
    write_family_zip(source_root / zip_name, family_dir, arcname_prefix=arcname_prefix)

    for member in family_dir.iterdir():
        member.unlink()

    family_dir.rmdir()
    return zip_name


def ingest(
    connection: Connection,
    source_root: Path,
    zip_relative_path: str,
) -> forestry_persistence.ForestrySnapshotIngestion:
    return ingest_forestry_snapshot(
        connection,
        source_root=source_root,
        zip_relative_path=zip_relative_path,
        system_key=SYSTEM_KEY,
    )


def count_rows(connection: Connection, table: str) -> int:
    allowed = {
        "forestry.shapefile_snapshot",
        "forestry.source_feature",
        "platform.source_snapshot",
        "platform.source_observation",
    }

    if table not in allowed:
        raise ValueError("Unexpected table")

    return connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_ingests_valid_family_zip_and_persists_snapshot_and_features(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    rows = [
        source_row(objectid=10, n_rodal="101", sup_ha=1.0),
        source_row(objectid=11, n_rodal="102", sup_ha=0.5, editada="mv"),
    ]
    zip_relative_path = build_zip(tmp_path, rows)

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    assert result.already_persisted is False
    assert result.feature_count == 2
    assert len(result.family_fingerprint) == 64

    snapshot = integration_connection.execute(
        text(
            """
            SELECT
                source_snapshot_id,
                family_fingerprint,
                layer_name,
                member_sha256,
                prj_wkt,
                storage_srid,
                encoding,
                shape_type,
                feature_count
            FROM forestry.shapefile_snapshot
            WHERE id = :snapshot_id
            """
        ),
        {"snapshot_id": result.shapefile_snapshot_id},
    ).one()

    assert snapshot.source_snapshot_id == result.provenance.source_snapshot_id
    assert snapshot.family_fingerprint == result.family_fingerprint
    assert snapshot.layer_name == "synthetic"
    assert set(snapshot.member_sha256) == {".shp", ".shx", ".dbf", ".prj", ".cpg"}
    assert snapshot.prj_wkt == EXPECTED_PRJ_WKT
    assert snapshot.storage_srid == 32718
    assert snapshot.encoding == "UTF-8"
    assert snapshot.shape_type == 5
    assert snapshot.feature_count == 2

    features = integration_connection.execute(
        text(
            """
            SELECT
                feature_ordinal,
                source_objectid,
                ST_SRID(geometry) AS srid,
                ST_GeometryType(geometry) AS geometry_type,
                geometry_is_valid,
                geometry_invalid_reason,
                geometry_area_source_units,
                n_rodal,
                sup_ha,
                quality_flags
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": result.shapefile_snapshot_id},
    ).all()

    assert [feature.feature_ordinal for feature in features] == [1, 2]
    assert [feature.source_objectid for feature in features] == [10, 11]
    assert all(feature.srid == 32718 for feature in features)
    assert all(feature.geometry_type == "ST_MultiPolygon" for feature in features)
    assert all(feature.geometry_is_valid for feature in features)
    assert all(feature.geometry_invalid_reason is None for feature in features)
    assert features[0].geometry_area_source_units == pytest.approx(100.0)
    assert features[1].geometry_area_source_units == pytest.approx(121.0)
    assert [feature.n_rodal for feature in features] == ["101", "102"]
    assert [feature.sup_ha for feature in features] == [1.0, 0.5]
    assert all(feature.quality_flags == [] for feature in features)


def test_geometry_stored_faithfully_with_validity_evidence(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    rows = [source_row(objectid=1, n_rodal="1"), source_row(objectid=2, n_rodal="2")]
    zip_relative_path = build_zip(
        tmp_path,
        rows,
        geometries=[[BOWTIE], [square_ring(50.0, 50.0, 10.0)]],
    )

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    features = integration_connection.execute(
        text(
            """
            SELECT
                feature_ordinal,
                geometry_is_valid,
                geometry_invalid_reason,
                ST_IsValid(geometry) AS postgis_is_valid,
                ST_NPoints(geometry) AS point_count,
                quality_flags
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": result.shapefile_snapshot_id},
    ).all()

    invalid, valid = features

    assert invalid.geometry_is_valid is False
    assert invalid.geometry_invalid_reason is not None
    assert "Self-intersection" in invalid.geometry_invalid_reason
    # The invalid source ring is stored as-is: PostGIS agrees it is invalid
    # and the point count matches the source ring exactly.
    assert invalid.postgis_is_valid is False
    assert invalid.point_count == 5
    assert invalid.quality_flags == ["invalid_geometry"]

    assert valid.geometry_is_valid is True
    assert valid.postgis_is_valid is True
    assert valid.quality_flags == []


def test_contract_invalid_source_is_rejected_before_any_persistence(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    zip_relative_path = build_zip(
        tmp_path,
        [source_row()],
        prj_text=EXPECTED_PRJ_WKT.replace("18S", "19S"),
    )

    with pytest.raises(ForestryShapefileError, match="Declared CRS does not match"):
        ingest(integration_connection, tmp_path, zip_relative_path)

    assert count_rows(integration_connection, "platform.source_snapshot") == 0
    assert count_rows(integration_connection, "platform.source_observation") == 0
    assert count_rows(integration_connection, "forestry.shapefile_snapshot") == 0
    assert count_rows(integration_connection, "forestry.source_feature") == 0


def test_reingesting_identical_zip_is_idempotent(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    zip_relative_path = build_zip(tmp_path, [source_row(), source_row(objectid=2)])

    first = ingest(integration_connection, tmp_path, zip_relative_path)
    second = ingest(integration_connection, tmp_path, zip_relative_path)

    assert first.already_persisted is False
    assert second.already_persisted is True
    assert second.shapefile_snapshot_id == first.shapefile_snapshot_id
    assert second.family_fingerprint == first.family_fingerprint
    assert second.feature_count == first.feature_count

    # Identical content resolves to the same platform snapshot while the
    # repeated observation is appended as provenance history.
    assert second.provenance.source_snapshot_id == first.provenance.source_snapshot_id
    assert count_rows(integration_connection, "platform.source_observation") == 2

    assert count_rows(integration_connection, "forestry.shapefile_snapshot") == 1
    assert count_rows(integration_connection, "forestry.source_feature") == 2


def test_same_family_content_in_repackaged_zip_is_idempotent_at_family_level(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    rows = [source_row()]
    first_zip = build_zip(tmp_path, rows)
    repackaged_zip = build_zip(
        tmp_path,
        rows,
        zip_name="repackaged.zip",
        arcname_prefix="carpeta/",
    )

    first = ingest(integration_connection, tmp_path, first_zip)
    second = ingest(integration_connection, tmp_path, repackaged_zip)

    # Different archive bytes: a distinct platform snapshot is recorded.
    assert second.provenance.source_snapshot_id != first.provenance.source_snapshot_id

    # Identical family content: the Forestry snapshot is not duplicated.
    assert second.already_persisted is True
    assert second.shapefile_snapshot_id == first.shapefile_snapshot_id
    assert count_rows(integration_connection, "forestry.shapefile_snapshot") == 1
    assert count_rows(integration_connection, "forestry.source_feature") == 1


def test_injected_failure_leaves_no_partial_snapshot(
    integration_connection: Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zip_relative_path = build_zip(tmp_path, [source_row()])

    def raise_infrastructure_failure(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected infrastructure failure")

    monkeypatch.setattr(
        forestry_persistence,
        "_insert_source_features",
        raise_infrastructure_failure,
    )

    with (
        pytest.raises(RuntimeError, match="injected infrastructure failure"),
        integration_connection.begin_nested(),
    ):
        ingest(integration_connection, tmp_path, zip_relative_path)

    assert count_rows(integration_connection, "forestry.shapefile_snapshot") == 0
    assert count_rows(integration_connection, "forestry.source_feature") == 0


def test_snapshot_local_identity_allows_objectid_reuse_across_snapshots(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    first_zip = build_zip(tmp_path, [source_row(objectid=7), source_row(objectid=8)])
    second_zip = build_zip(
        tmp_path,
        [
            source_row(objectid=7, desc_uso="Otra descripción"),
            source_row(objectid=8, desc_uso="Otra descripción"),
        ],
        zip_name="second.zip",
    )

    first = ingest(integration_connection, tmp_path, first_zip)
    second = ingest(integration_connection, tmp_path, second_zip)

    assert second.already_persisted is False
    assert second.shapefile_snapshot_id != first.shapefile_snapshot_id

    ordinals = integration_connection.execute(
        text(
            """
            SELECT shapefile_snapshot_id, feature_ordinal, source_objectid
            FROM forestry.source_feature
            ORDER BY shapefile_snapshot_id, feature_ordinal
            """
        )
    ).all()

    # Ordinals restart per snapshot and the same source OBJECTID coexists in
    # both snapshots: OBJECTID is evidence, not a durable global identity.
    assert [
        (row.shapefile_snapshot_id, row.feature_ordinal, row.source_objectid) for row in ordinals
    ] == [
        (first.shapefile_snapshot_id, 1, 7),
        (first.shapefile_snapshot_id, 2, 8),
        (second.shapefile_snapshot_id, 1, 7),
        (second.shapefile_snapshot_id, 2, 8),
    ]


def test_duplicate_objectid_within_snapshot_is_persisted_as_evidence(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    zip_relative_path = build_zip(
        tmp_path,
        [source_row(objectid=1, n_rodal="1"), source_row(objectid=1, n_rodal="2")],
    )

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    objectids = integration_connection.execute(
        text(
            """
            SELECT source_objectid
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": result.shapefile_snapshot_id},
    ).scalars()

    assert list(objectids) == [1, 1]


def test_rodal_and_truncation_quality_evidence_is_persisted(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    rows = [
        source_row(objectid=1, n_rodal="856"),
        source_row(objectid=2, n_rodal="856"),
        source_row(objectid=3, n_rodal=None),
        source_row(objectid=4, n_rodal="900", cod_uso_2026="RaCoRo01P*"),
    ]
    zip_relative_path = build_zip(tmp_path, rows)

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    flags = integration_connection.execute(
        text(
            """
            SELECT feature_ordinal, quality_flags
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": result.shapefile_snapshot_id},
    ).all()

    assert [tuple(row.quality_flags) for row in flags] == [
        ("duplicate_predio_rodal_key",),
        ("duplicate_predio_rodal_key",),
        ("blank_rodal",),
        ("truncated_use_code_2026",),
    ]


def test_duplicate_geometry_evidence_is_persisted(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    shared_ring = square_ring(0.0, 0.0, 10.0)
    zip_relative_path = build_zip(
        tmp_path,
        [source_row(objectid=1, n_rodal="1"), source_row(objectid=2, n_rodal="2")],
        geometries=[[shared_ring], [shared_ring]],
    )

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    flags = integration_connection.execute(
        text(
            """
            SELECT quality_flags
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": result.shapefile_snapshot_id},
    ).scalars()

    assert [tuple(row) for row in flags] == [
        ("duplicate_geometry",),
        ("duplicate_geometry",),
    ]


def test_raw_source_attributes_are_faithfully_preserved(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    row = source_row(
        objectid=42,
        editada="mv",
        cod_uso="En11",
        cod_uso_2026="Pi26",
        desc_uso="Descripción con acentos: ñandú",
        shape_leng=123.456,
    )
    zip_relative_path = build_zip(tmp_path, [row])

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    stored = integration_connection.execute(
        text(
            """
            SELECT source_attributes
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            """
        ),
        {"snapshot_id": result.shapefile_snapshot_id},
    ).scalar_one()

    expected = dict(row)
    expected["n_rodal_te"] = None

    assert stored == json.loads(json.dumps(expected))


def test_use_field_comparison_reports_source_field_differences_only(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    rows = [
        # Class change and detail change.
        source_row(
            objectid=1,
            n_rodal="1",
            uso_2024="ENSAYO",
            uso_2026="CLASE A",
            cod_uso="En11",
            cod_uso_2026="Pi26",
        ),
        # Detail change only.
        source_row(objectid=2, n_rodal="2", cod_uso="Eg03", cod_uso_2026="Pi25"),
        # No changes.
        source_row(objectid=3, n_rodal="3"),
        # Blank on both sides is not a change.
        source_row(objectid=4, n_rodal="4", cod_uso=None, cod_uso_2026=None),
        # Blank to value is a change.
        source_row(objectid=5, n_rodal="5", cod_uso=None, cod_uso_2026="Po25"),
    ]
    zip_relative_path = build_zip(tmp_path, rows)

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    comparison = use_field_comparison(
        integration_connection,
        result.shapefile_snapshot_id,
    )

    assert [
        (change.feature_ordinal, change.source_objectid, change.before, change.after)
        for change in comparison.uso_2024_vs_uso_2026
    ] == [(1, 1, "ENSAYO", "CLASE A")]

    assert [
        (change.feature_ordinal, change.before, change.after)
        for change in comparison.cod_uso_vs_cod_uso_2026
    ] == [
        (1, "En11", "Pi26"),
        (2, "Eg03", "Pi25"),
        (5, None, "Po25"),
    ]


def test_snapshot_summary_and_distributions(
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    rows = [
        source_row(
            objectid=1,
            cod_predial="P1",
            nom_predio="Predio Uno",
            n_rodal="1",
            uso_2026="CLASE A",
            sup_ha=1.0,
        ),
        source_row(
            objectid=2,
            cod_predial="P1",
            nom_predio="Predio Uno",
            n_rodal="2",
            uso_2026="CLASE B",
            sup_ha=2.0,
        ),
        source_row(
            objectid=3,
            cod_predial="P2",
            nom_predio="Predio Dos",
            n_rodal=None,
            uso_2026="CLASE A",
            sup_ha=4.0,
        ),
    ]
    zip_relative_path = build_zip(
        tmp_path,
        rows,
        geometries=[
            [square_ring(0.0, 0.0, 10.0)],
            [square_ring(20.0, 0.0, 10.0)],
            [BOWTIE],
        ],
    )

    result = ingest(integration_connection, tmp_path, zip_relative_path)

    summary = snapshot_summary(integration_connection, result.shapefile_snapshot_id)

    assert summary.shapefile_snapshot_id == result.shapefile_snapshot_id
    assert summary.layer_name == "synthetic"
    assert summary.family_fingerprint == result.family_fingerprint
    assert summary.storage_srid == 32718
    assert summary.feature_count == 3
    assert summary.total_geometry_area_source_units == pytest.approx(200.0)
    assert summary.total_sup_ha == pytest.approx(7.0)
    assert summary.geometry_valid_count == 2
    assert summary.geometry_invalid_count == 1
    assert summary.quality_flag_counts == {
        "blank_rodal": 1,
        "invalid_geometry": 1,
    }
    assert summary.n_rodal_te_non_blank_count == 0

    predios = predio_distribution(integration_connection, result.shapefile_snapshot_id)

    assert [
        (entry.cod_predial, entry.nom_predio, entry.feature_count, entry.sup_ha_total)
        for entry in predios
    ] == [
        ("P1", "Predio Uno", 2, 3.0),
        ("P2", "Predio Dos", 1, 4.0),
    ]

    uses = use_distribution(
        integration_connection,
        result.shapefile_snapshot_id,
        field="uso_2026",
    )

    assert [(entry.value, entry.feature_count) for entry in uses] == [
        ("CLASE A", 2),
        ("CLASE B", 1),
    ]

    with pytest.raises(ForestryIngestionError, match="Unsupported use field"):
        use_distribution(
            integration_connection,
            result.shapefile_snapshot_id,
            field="editada",  # not a supported use field; the whitelist must reject it
        )

    snapshots = list_shapefile_snapshots(integration_connection)

    assert [
        (record.shapefile_snapshot_id, record.layer_name, record.feature_count)
        for record in snapshots
    ] == [(result.shapefile_snapshot_id, "synthetic", 3)]
