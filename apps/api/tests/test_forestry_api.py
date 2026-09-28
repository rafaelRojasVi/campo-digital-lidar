"""No-database tests for the read-only Forestry API router.

Behavioral coverage against real PostGIS lives in
`apps/api/integration_tests/test_forestry_api.py`; these tests cover route
registration, the read-only surface, parameter validation, and safe
database-unavailable behavior.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import get_args
from unittest.mock import Mock

import pytest
from app.database import get_database_engine
from app.forestry_reads import KNOWN_QUALITY_FLAGS
from app.main import app
from app.routers.forestry import QualityFlag, get_forestry_read_connection
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

EXPECTED_FORESTRY_PATHS = {
    "/api/forestry/snapshots",
    "/api/forestry/snapshots/latest-ingested",
    "/api/forestry/snapshots/{shapefile_snapshot_id}",
    "/api/forestry/snapshots/{shapefile_snapshot_id}/predio-distribution",
    "/api/forestry/snapshots/{shapefile_snapshot_id}/use-distribution",
    "/api/forestry/snapshots/{shapefile_snapshot_id}/source-field-comparison",
    "/api/forestry/snapshots/{shapefile_snapshot_id}/features",
    "/api/forestry/snapshots/{shapefile_snapshot_id}/features/{feature_ordinal}",
    "/api/forestry/snapshots/{shapefile_snapshot_id}/feature-collection",
}


@pytest.fixture
def client_without_database() -> Iterator[TestClient]:
    """Client whose forestry connection dependency never touches a database.

    The connection dependency is resolved before query/path validation, so it
    is overridden with an inert stub; the endpoints themselves must never run.
    """

    stub_connection = Mock()
    app.dependency_overrides[get_forestry_read_connection] = lambda: stub_connection

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_forestry_read_connection, None)
        assert stub_connection.execute.call_count == 0


def forestry_routes() -> dict[str, set[str]]:
    """Forestry paths with their declared methods, from the OpenAPI contract."""

    return {
        path: {method.upper() for method in operations}
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/forestry")
    }


def test_forestry_routes_are_registered() -> None:
    assert set(forestry_routes()) == EXPECTED_FORESTRY_PATHS


def test_quality_flag_parameter_matches_evidence_vocabulary() -> None:
    assert set(get_args(QualityFlag)) == set(KNOWN_QUALITY_FLAGS)


def test_forestry_exposes_no_mutation_routes() -> None:
    routes = forestry_routes()

    assert routes

    for path, methods in routes.items():
        assert methods == {"GET"}, f"unexpected methods {methods} on {path}"


def test_database_unavailable_returns_503_without_leaking_backend_error() -> None:
    engine = Mock(spec=Engine)
    engine.connect.side_effect = SQLAlchemyError("password=should-never-appear")
    app.dependency_overrides[get_database_engine] = lambda: engine

    try:
        response = TestClient(app).get("/api/forestry/snapshots")
    finally:
        app.dependency_overrides.pop(get_database_engine, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    assert "should-never-appear" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        # Non-integer snapshot id.
        "/api/forestry/snapshots/not-a-number",
        # Snapshot ids are positive.
        "/api/forestry/snapshots/0",
        # The use field is mandatory and whitelisted.
        "/api/forestry/snapshots/1/use-distribution",
        "/api/forestry/snapshots/1/use-distribution?field=editada",
        # Pagination bounds.
        "/api/forestry/snapshots/1/features?limit=0",
        "/api/forestry/snapshots/1/features?limit=501",
        "/api/forestry/snapshots/1/features?offset=-1",
        # Quality flags outside the established evidence vocabulary.
        "/api/forestry/snapshots/1/features?quality_flag=not_a_flag",
        # Source-field comparison filters accept literal difference values only.
        "/api/forestry/snapshots/1/features?uso_2024_vs_uso_2026=progressed",
        "/api/forestry/snapshots/1/features?cod_uso_vs_cod_uso_2026=approved",
        # Feature ordinals are 1-based.
        "/api/forestry/snapshots/1/features/0",
    ],
)
def test_invalid_parameters_are_rejected(
    client_without_database: TestClient,
    path: str,
) -> None:
    response = client_without_database.get(path)

    assert response.status_code == 422
