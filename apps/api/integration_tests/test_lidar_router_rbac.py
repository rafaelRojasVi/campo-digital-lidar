"""LiDAR router RBAC: authenticated + LiDAR VIEW-capable access required.

Mirrors the RBAC pattern already proven for app.routers.ingestion — real
platform sessions and product grants against the disposable integration
database, not a stubbed auth layer.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from pathlib import Path

import pytest
from app.access import Role
from app.access_repository import grant_product_role, resolve_or_create_app_user
from app.deps import SESSION_COOKIE_NAME
from app.dev_auth import DEV_IDENTITY_KIND
from app.main import app
from app.routers.lidar import get_output_root
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from lidar_core.models import MeasurementRun, MeasurementRunStatus
from lidar_io.run_store import write_measurement_run

_platform_sessions = PlatformSessionStore()

RUN_ID = "run-001"


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_output_root] = lambda: tmp_path

    write_measurement_run(
        MeasurementRun(
            run_id=RUN_ID,
            source_path="/private/source/example.las",
            status=MeasurementRunStatus.COMPLETED,
        ),
        tmp_path,
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _login_with_grant(
    client: TestClient, engine: Engine, *, product_key: str, role: Role | None
) -> None:
    """Authenticate `client` as a freshly created user with exactly one
    grant (or none, when `role` is None) — independent of the seeded dev
    identities' default grants, so each test controls its own role
    precisely."""

    with engine.connect() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind=DEV_IDENTITY_KIND,
            identity_key=f"lidar-rbac-test-{product_key}-{role}",
            display_name="LiDAR RBAC Test User",
        )
        if role is not None:
            grant_product_role(connection, app_user_id=user.id, product_key=product_key, role=role)
        raw_secret = _platform_sessions.create_session(
            connection, app_user_id=user.id, ttl=timedelta(hours=8)
        )
        connection.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)


def _cleanup_all_test_data(engine: Engine) -> None:
    with engine.connect() as conn:
        for table in ("audit_event", "product_grant", "session", "app_user"):
            conn.execute(text(f"DELETE FROM platform.{table}"))
        conn.commit()


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    _cleanup_all_test_data(integration_engine)


LIDAR_PATHS = (
    "/runs",
    f"/runs/{RUN_ID}",
    f"/runs/{RUN_ID}/comparisons",
)


@pytest.mark.parametrize("path", LIDAR_PATHS)
def test_unauthenticated_caller_cannot_read(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", LIDAR_PATHS)
def test_authenticated_user_with_no_lidar_grant_cannot_read(
    client: TestClient, integration_engine: Engine, path: str
) -> None:
    _login_with_grant(client, integration_engine, product_key="forestry", role=Role.ADMIN)

    response = client.get(path)
    assert response.status_code == 403


@pytest.mark.parametrize("path", LIDAR_PATHS)
@pytest.mark.parametrize("role", [Role.VIEWER, Role.OPERATOR, Role.ADMIN])
def test_granted_role_can_read(
    client: TestClient, integration_engine: Engine, path: str, role: Role
) -> None:
    _login_with_grant(client, integration_engine, product_key="lidar", role=role)

    response = client.get(path)
    assert response.status_code == 200


def test_unauthenticated_caller_cannot_read_artifact(client: TestClient) -> None:
    response = client.get(f"/runs/{RUN_ID}/artifacts/front_profile.json")
    assert response.status_code == 401


def test_no_grant_caller_cannot_read_artifact(
    client: TestClient, integration_engine: Engine
) -> None:
    _login_with_grant(client, integration_engine, product_key="forestry", role=Role.ADMIN)

    response = client.get(f"/runs/{RUN_ID}/artifacts/front_profile.json")
    assert response.status_code == 403


def test_viewer_can_reach_artifact_route_past_rbac(
    client: TestClient, integration_engine: Engine
) -> None:
    """The artifact route has no registered artifact in this fixture run, so
    a granted VIEWER reaches the existing (unregistered-artifact) 404 —
    proving RBAC lets the request through rather than blocking it."""

    _login_with_grant(client, integration_engine, product_key="lidar", role=Role.VIEWER)

    response = client.get(f"/runs/{RUN_ID}/artifacts/front_profile.json")
    assert response.status_code == 404
