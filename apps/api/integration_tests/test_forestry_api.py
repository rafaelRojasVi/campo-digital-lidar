"""Integration tests for the read-only Forestry API over real PostGIS.

All source material is synthetic (shared builders from the Forestry unit
tests); no real Forestry client data is used or reproduced. The API is
exercised end-to-end through the FastAPI app with the router's connection
dependency bound to the rolled-back integration transaction.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.main import app
from app.routers.forestry import get_forestry_read_connection
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from test_forestry_ingestion import BOWTIE, build_zip, ingest

from forestry_family_fixtures import source_row, square_ring

SQUARE_RING_COORDINATES = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]
BOWTIE_COORDINATES = [[0, 0], [10, 10], [0, 10], [10, 0], [0, 0]]


@pytest.fixture
def api_client(integration_connection: Connection) -> Iterator[TestClient]:
    """API client reading through the rolled-back integration transaction."""

    app.dependency_overrides[get_forestry_read_connection] = lambda: integration_connection

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_forestry_read_connection, None)


def ingest_main_family(connection: Connection, tmp_path: Path) -> int:
    """Persist one synthetic snapshot exercising every projection dimension."""

    rows = [
        # Class change (ENSAYO -> CLASE A) and detail-code change.
        source_row(
            objectid=1,
            cod_predial="P1",
            nom_predio="Predio Uno",
            n_rodal="1",
            cod_uso="En11",
            uso_2024="ENSAYO",
            uso_2026="CLASE A",
            cod_uso_2026="Pi26",
            sup_ha=1.0,
        ),
        # Detail-code change only.
        source_row(
            objectid=2,
            cod_predial="P1",
            nom_predio="Predio Uno",
            n_rodal="2",
            cod_uso="Eg03",
            cod_uso_2026="Pi25",
            sup_ha=2.0,
        ),
        # Blank rodal, invalid bowtie geometry, class change to CLASE B.
        source_row(
            objectid=3,
            cod_predial="P2",
            nom_predio="Predio Dos",
            n_rodal=None,
            uso_2026="CLASE B",
            sup_ha=4.0,
        ),
        # Truncated 2026 detail code, no source-field difference.
        source_row(
            objectid=4,
            cod_predial="P2",
            nom_predio="Predio Dos",
            n_rodal="9",
            cod_uso="RaCoRo01P*",
            cod_uso_2026="RaCoRo01P*",
        ),
        # Duplicate (predio, rodal) pair.
        source_row(
            objectid=5,
            cod_predial="P1",
            nom_predio="Predio Uno",
            n_rodal="7",
            sup_ha=0.5,
        ),
        source_row(
            objectid=6,
            cod_predial="P1",
            nom_predio="Predio Uno",
            n_rodal="7",
        ),
    ]
    geometries = [
        [square_ring(0.0, 0.0, 10.0)],
        [square_ring(20.0, 0.0, 10.0)],
        [BOWTIE],
        [square_ring(60.0, 0.0, 10.0)],
        [square_ring(80.0, 0.0, 10.0)],
        [square_ring(100.0, 0.0, 10.0)],
    ]

    zip_relative_path = build_zip(tmp_path, rows, geometries=geometries)
    result = ingest(connection, tmp_path, zip_relative_path)

    return result.shapefile_snapshot_id


def listed_ordinals(payload: dict) -> list[int]:
    return [feature["feature_ordinal"] for feature in payload["features"]]


def test_no_persisted_snapshot_behavior(api_client: TestClient) -> None:
    response = api_client.get("/api/forestry/snapshots")

    assert response.status_code == 200
    assert response.json() == []

    latest = api_client.get("/api/forestry/snapshots/latest-ingested")

    assert latest.status_code == 404
    assert latest.json() == {"detail": "no forestry snapshot is persisted"}

    for path in [
        "/api/forestry/snapshots/1",
        "/api/forestry/snapshots/1/predio-distribution",
        "/api/forestry/snapshots/1/use-distribution?field=uso_2026",
        "/api/forestry/snapshots/1/source-field-comparison",
        "/api/forestry/snapshots/1/features",
        "/api/forestry/snapshots/1/features/1",
        "/api/forestry/snapshots/1/feature-collection",
    ]:
        response = api_client.get(path)

        assert response.status_code == 404, path
        assert response.json() == {"detail": "forestry snapshot 1 is not persisted"}


def test_snapshot_list_and_latest_ingested(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    first_id = ingest_main_family(integration_connection, tmp_path)

    # A different family content, so a second distinct snapshot is persisted.
    second_zip = build_zip(
        tmp_path,
        [source_row(objectid=9, desc_uso="Otra descripción")],
        zip_name="second.zip",
    )
    second_id = ingest(integration_connection, tmp_path, second_zip).shapefile_snapshot_id

    assert second_id != first_id

    response = api_client.get("/api/forestry/snapshots")

    assert response.status_code == 200

    payload = response.json()

    assert [entry["shapefile_snapshot_id"] for entry in payload] == sorted([first_id, second_id])
    assert [entry["feature_count"] for entry in payload] == [6, 1]

    for entry in payload:
        assert entry["layer_name"] == "synthetic"
        assert len(entry["family_fingerprint"]) == 64
        assert "created_at" in entry

    latest = api_client.get("/api/forestry/snapshots/latest-ingested")

    assert latest.status_code == 200
    assert latest.json()["shapefile_snapshot_id"] == max(first_id, second_id)


def test_snapshot_summary_reports_quality_evidence(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id}")

    assert response.status_code == 200

    payload = response.json()

    assert payload["shapefile_snapshot_id"] == snapshot_id
    assert payload["layer_name"] == "synthetic"
    assert payload["storage_srid"] == 32718
    assert payload["feature_count"] == 6
    assert payload["total_geometry_area_source_units"] == pytest.approx(500.0)
    assert payload["total_sup_ha"] == pytest.approx(10.5)
    assert payload["geometry_valid_count"] == 5
    assert payload["geometry_invalid_count"] == 1
    assert payload["quality_flag_counts"] == {
        "blank_rodal": 1,
        "duplicate_predio_rodal_key": 2,
        "invalid_geometry": 1,
        "truncated_use_code_2026": 1,
    }
    assert payload["n_rodal_te_non_blank_count"] == 0
    assert payload["bbox"] == [0.0, 0.0, 110.0, 10.0]


def test_unknown_snapshot_returns_404(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id + 1}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"forestry snapshot {snapshot_id + 1} is not persisted"}


def test_predio_distribution(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/predio-distribution")

    assert response.status_code == 200
    assert [
        (
            entry["cod_predial"],
            entry["nom_predio"],
            entry["feature_count"],
            entry["sup_ha_total"],
        )
        for entry in response.json()
    ] == [
        ("P1", "Predio Uno", 4, 5.0),
        ("P2", "Predio Dos", 2, 5.5),
    ]


def test_use_distribution_for_both_year_stamped_fields(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(
        f"/api/forestry/snapshots/{snapshot_id}/use-distribution",
        params={"field": "uso_2026"},
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["field"] == "uso_2026"
    assert [(entry["value"], entry["feature_count"]) for entry in payload["entries"]] == [
        ("CLASE A", 5),
        ("CLASE B", 1),
    ]

    response = api_client.get(
        f"/api/forestry/snapshots/{snapshot_id}/use-distribution",
        params={"field": "uso_2024"},
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["field"] == "uso_2024"
    assert [(entry["value"], entry["feature_count"]) for entry in payload["entries"]] == [
        ("CLASE A", 5),
        ("ENSAYO", 1),
    ]


def test_source_field_comparison_is_literal(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/source-field-comparison")

    assert response.status_code == 200

    payload = response.json()

    assert payload["shapefile_snapshot_id"] == snapshot_id
    assert payload["semantics"] == (
        "literal source-field differences within one snapshot; not workflow transitions"
    )

    class_comparison = payload["uso_2024_vs_uso_2026"]

    assert class_comparison["changed_feature_count"] == 2
    assert [
        (change["feature_ordinal"], change["source_objectid"], change["before"], change["after"])
        for change in class_comparison["changes"]
    ] == [
        (1, 1, "ENSAYO", "CLASE A"),
        (3, 3, "CLASE A", "CLASE B"),
    ]

    detail_comparison = payload["cod_uso_vs_cod_uso_2026"]

    assert detail_comparison["changed_feature_count"] == 2
    assert [
        (change["feature_ordinal"], change["before"], change["after"])
        for change in detail_comparison["changes"]
    ] == [
        (1, "En11", "Pi26"),
        (2, "Eg03", "Pi25"),
    ]


def test_feature_listing_is_paginated_and_deterministic(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)
    base_path = f"/api/forestry/snapshots/{snapshot_id}/features"

    response = api_client.get(base_path)

    assert response.status_code == 200

    payload = response.json()

    assert payload["shapefile_snapshot_id"] == snapshot_id
    assert payload["total_count"] == 6
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert listed_ordinals(payload) == [1, 2, 3, 4, 5, 6]

    first_page = api_client.get(base_path, params={"limit": 2, "offset": 0}).json()

    assert first_page["total_count"] == 6
    assert first_page["limit"] == 2
    assert listed_ordinals(first_page) == [1, 2]

    second_page = api_client.get(base_path, params={"limit": 2, "offset": 2}).json()

    assert listed_ordinals(second_page) == [3, 4]

    beyond_end = api_client.get(base_path, params={"limit": 2, "offset": 6}).json()

    assert beyond_end["total_count"] == 6
    assert beyond_end["features"] == []


def test_feature_listing_row_content(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    payload = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/features").json()
    first = payload["features"][0]

    assert first == {
        "feature_ordinal": 1,
        "source_objectid": 1,
        "cod_predial": "P1",
        "nom_predio": "Predio Uno",
        "n_rodal": "1",
        "cod_uso": "En11",
        "uso_2024": "ENSAYO",
        "desc_uso": "Descripción sintética",
        "uso_2026": "CLASE A",
        "cod_uso_2026": "Pi26",
        "sup_ha": 1.0,
        "geometry_is_valid": True,
        "geometry_area_source_units": 100.0,
        "quality_flags": [],
    }


def test_feature_filtering_is_deterministic(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)
    base_path = f"/api/forestry/snapshots/{snapshot_id}/features"

    cases: list[tuple[dict[str, object], list[int]]] = [
        ({"cod_predial": "P1"}, [1, 2, 5, 6]),
        ({"nom_predio": "Predio Dos"}, [3, 4]),
        ({"n_rodal": "7"}, [5, 6]),
        ({"uso_2026": "CLASE B"}, [3]),
        ({"uso_2024": "ENSAYO"}, [1]),
        ({"cod_uso": "Eg03"}, [2]),
        ({"cod_uso_2026": "Pi26"}, [1]),
        ({"desc_uso": "Descripción sintética"}, [1, 2, 3, 4, 5, 6]),
        ({"quality_flag": "blank_rodal"}, [3]),
        ({"quality_flag": "duplicate_predio_rodal_key"}, [5, 6]),
        ({"quality_flag": "truncated_use_code_2026"}, [4]),
        ({"geometry_valid": "false"}, [3]),
        ({"geometry_valid": "true"}, [1, 2, 4, 5, 6]),
        ({"uso_2024_vs_uso_2026": "changed"}, [1, 3]),
        ({"uso_2024_vs_uso_2026": "unchanged"}, [2, 4, 5, 6]),
        ({"cod_uso_vs_cod_uso_2026": "changed"}, [1, 2]),
        ({"cod_uso_vs_cod_uso_2026": "unchanged"}, [3, 4, 5, 6]),
        ({"cod_predial": "P1", "cod_uso_vs_cod_uso_2026": "changed"}, [1, 2]),
        ({"cod_predial": "does-not-exist"}, []),
    ]

    for params, expected_ordinals in cases:
        response = api_client.get(base_path, params=params)

        assert response.status_code == 200, params

        payload = response.json()

        assert listed_ordinals(payload) == expected_ordinals, params
        assert payload["total_count"] == len(expected_ordinals), params


def test_duplicate_and_blank_rodal_features_are_reported_as_evidence(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    payload = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/features").json()
    by_ordinal = {feature["feature_ordinal"]: feature for feature in payload["features"]}

    assert by_ordinal[3]["n_rodal"] is None
    assert by_ordinal[3]["quality_flags"] == ["blank_rodal", "invalid_geometry"]

    # Both holders of the duplicated (predio, rodal) pair stay listed.
    assert by_ordinal[5]["n_rodal"] == "7"
    assert by_ordinal[6]["n_rodal"] == "7"
    assert by_ordinal[5]["quality_flags"] == ["duplicate_predio_rodal_key"]
    assert by_ordinal[6]["quality_flags"] == ["duplicate_predio_rodal_key"]


def test_feature_detail_returns_source_attributes_and_geometry(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/features/1")

    assert response.status_code == 200

    payload = response.json()

    assert payload["shapefile_snapshot_id"] == snapshot_id
    assert payload["feature_ordinal"] == 1
    assert payload["source_objectid"] == 1
    assert payload["storage_srid"] == 32718
    assert payload["geometry_is_valid"] is True
    assert payload["geometry_invalid_reason"] is None
    assert payload["geometry_area_source_units"] == pytest.approx(100.0)
    assert payload["sup_ha"] == 1.0
    assert payload["shape_area"] == 15000.0
    assert payload["quality_flags"] == []

    # The complete blank-normalized source attribute row is preserved.
    attributes = payload["source_attributes"]

    assert attributes["objectid"] == 1
    assert attributes["cod_predial"] == "P1"
    assert attributes["uso_2024"] == "ENSAYO"
    assert attributes["editada"] is None
    assert attributes["n_rodal_te"] is None

    assert payload["geometry"] == {
        "type": "MultiPolygon",
        "coordinates": [[SQUARE_RING_COORDINATES]],
    }


def test_invalid_geometry_is_preserved_and_labeled(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/features/3")

    assert response.status_code == 200

    payload = response.json()

    assert payload["geometry_is_valid"] is False
    assert "Self-intersection" in payload["geometry_invalid_reason"]
    assert "invalid_geometry" in payload["quality_flags"]

    # The self-intersecting source ring is serialized as-is, never repaired.
    assert payload["geometry"] == {
        "type": "MultiPolygon",
        "coordinates": [[BOWTIE_COORDINATES]],
    }


def test_unknown_feature_ordinal_returns_404(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/features/999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": f"source feature 999 does not exist in forestry snapshot {snapshot_id}"
    }


def test_feature_collection_serializes_geojson_with_source_crs(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(f"/api/forestry/snapshots/{snapshot_id}/feature-collection")

    assert response.status_code == 200

    payload = response.json()

    assert payload["type"] == "FeatureCollection"
    assert payload["shapefile_snapshot_id"] == snapshot_id
    assert payload["storage_srid"] == 32718
    assert payload["feature_count"] == 6
    assert len(payload["features"]) == 6

    first = payload["features"][0]

    assert first["type"] == "Feature"
    assert first["properties"]["feature_ordinal"] == 1
    assert first["properties"]["cod_predial"] == "P1"
    assert first["properties"]["uso_2026"] == "CLASE A"
    assert first["geometry"] == {
        "type": "MultiPolygon",
        "coordinates": [[SQUARE_RING_COORDINATES]],
    }

    bowtie = payload["features"][2]

    assert bowtie["properties"]["geometry_is_valid"] is False
    assert bowtie["geometry"]["coordinates"] == [[BOWTIE_COORDINATES]]


def test_feature_collection_supports_the_listing_filters(
    api_client: TestClient,
    integration_connection: Connection,
    tmp_path: Path,
) -> None:
    snapshot_id = ingest_main_family(integration_connection, tmp_path)

    response = api_client.get(
        f"/api/forestry/snapshots/{snapshot_id}/feature-collection",
        params={"quality_flag": "invalid_geometry"},
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["feature_count"] == 1
    assert [feature["properties"]["feature_ordinal"] for feature in payload["features"]] == [3]
