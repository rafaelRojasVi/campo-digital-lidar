"""Forestry route access with real platform sessions, against PostGIS.

Every forestry route, including the geometry (feature-collection) and
feature-detail routes, is requested as: an anonymous caller, a forged
session, a signed-in account holding only a Transelec grant, and forestry
viewer/operator/admin accounts. Only the forestry grants read data.

All data is synthetic; everything runs in the rolled-back integration
transaction.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from app.access import Role
from app.access_repository import grant_product_role, resolve_or_create_app_user
from app.deps import SESSION_COOKIE_NAME, get_db_connection
from app.forestry_publication import publish_initial_if_unpublished
from app.main import app
from app.routers.forestry import get_forestry_read_connection
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from test_forestry_ingestion import build_zip, ingest

from forestry_family_fixtures import source_row, square_ring

_sessions = PlatformSessionStore()


@pytest.fixture
def client(integration_connection: Connection) -> Iterator[TestClient]:
    app.dependency_overrides[get_db_connection] = lambda: integration_connection
    app.dependency_overrides[get_forestry_read_connection] = lambda: integration_connection
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_connection, None)
        app.dependency_overrides.pop(get_forestry_read_connection, None)


@pytest.fixture
def snapshot_id(integration_connection: Connection, tmp_path: Path) -> int:
    rows = [source_row(objectid=1, cod_predial="P1", nom_predio="Predio Uno", n_rodal="1")]
    zip_relative_path = build_zip(tmp_path, rows, geometries=[[square_ring(0.0, 0.0, 10.0)]])
    snapshot_id = ingest(integration_connection, tmp_path, zip_relative_path).shapefile_snapshot_id
    # Published, so a viewer may read it (a pending snapshot is 404 to viewers).
    publish_initial_if_unpublished(integration_connection, shapefile_snapshot_id=snapshot_id)
    return snapshot_id


# Reads that need more than VIEW (the pending-upload review is for uploaders).
_UPLOADER_READS = {"/api/forestry/snapshots/{shapefile_snapshot_id}/review"}


def _forestry_urls(snapshot_id: int, *, include_uploader_reads: bool = True) -> list[str]:
    paths = [
        path
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/forestry")
        and "get" in operations
        and (include_uploader_reads or path not in _UPLOADER_READS)
    ]
    assert len(paths) == (11 if include_uploader_reads else 10)
    urls = []
    for path in paths:
        url = path.replace("{shapefile_snapshot_id}", str(snapshot_id)).replace(
            "{feature_ordinal}", "1"
        )
        if url.endswith("/use-distribution"):
            url += "?field=uso_2024"
        urls.append(url)
    return urls


def _sign_in(
    client: TestClient, connection: Connection, name: str, grants: tuple[tuple[str, Role], ...]
) -> None:
    user = resolve_or_create_app_user(
        connection,
        identity_kind="google",
        identity_key=f"sub-{name}",
        display_name=name,
        email=f"{name}@campodigital.cl",
    )
    for product_key, role in grants:
        grant_product_role(connection, app_user_id=user.id, product_key=product_key, role=role)
    secret = _sessions.create_session(connection, app_user_id=user.id, ttl=timedelta(hours=1))
    client.cookies.set(SESSION_COOKIE_NAME, secret)


def test_anonymous_callers_get_401_on_every_forestry_route(
    client: TestClient, snapshot_id: int
) -> None:
    for url in _forestry_urls(snapshot_id):
        response = client.get(url)
        assert response.status_code == 401, url
        assert response.json() == {"detail": "Not authenticated."}, url


def test_a_forged_session_cookie_gets_401(client: TestClient, snapshot_id: int) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-session")
    for url in _forestry_urls(snapshot_id):
        assert client.get(url).status_code == 401, url


def test_a_transelec_only_account_gets_403_on_every_forestry_route(
    client: TestClient, integration_connection: Connection, snapshot_id: int
) -> None:
    _sign_in(client, integration_connection, "transelec-admin", (("transelect", Role.ADMIN),))

    for url in _forestry_urls(snapshot_id):
        response = client.get(url)
        assert response.status_code == 403, url
        assert response.json() == {"detail": "Not permitted for this product."}, url
        # No rodal data in the refusal.
        assert "Predio Uno" not in response.text, url


def test_an_account_with_no_grant_at_all_gets_403(
    client: TestClient, integration_connection: Connection, snapshot_id: int
) -> None:
    _sign_in(client, integration_connection, "nobody", ())

    for url in _forestry_urls(snapshot_id):
        assert client.get(url).status_code == 403, url


@pytest.mark.parametrize("role", [Role.VIEWER, Role.OPERATOR, Role.ADMIN])
def test_every_forestry_role_reads_every_route(
    client: TestClient, integration_connection: Connection, snapshot_id: int, role: Role
) -> None:
    _sign_in(client, integration_connection, f"forestry-{role.value}", (("forestry", role),))

    for url in _forestry_urls(snapshot_id, include_uploader_reads=False):
        assert client.get(url).status_code == 200, url

    review = client.get(f"/api/forestry/snapshots/{snapshot_id}/review").status_code
    assert review == (403 if role is Role.VIEWER else 200)

    geometry = client.get(f"/api/forestry/snapshots/{snapshot_id}/feature-collection").json()
    assert geometry["feature_count"] == 1


def test_a_viewer_cannot_see_a_pending_snapshot(
    client: TestClient, integration_connection: Connection, snapshot_id: int, tmp_path: Path
) -> None:
    rows = [source_row(objectid=2, cod_predial="P9", nom_predio="Predio Pendiente", n_rodal="1")]
    zip_relative_path = build_zip(
        tmp_path, rows, zip_name="pending.zip", geometries=[[square_ring(50.0, 0.0, 10.0)]]
    )
    pending = ingest(integration_connection, tmp_path, zip_relative_path).shapefile_snapshot_id

    _sign_in(client, integration_connection, "viewer", (("forestry", Role.VIEWER),))

    for url in _forestry_urls(pending, include_uploader_reads=False):
        if url.endswith(("/snapshots", "/snapshots/published", "/versions")):
            continue
        response = client.get(url)
        assert response.status_code == 404, url
        assert "Predio Pendiente" not in response.text, url

    listed = client.get("/api/forestry/snapshots").json()
    assert [entry["shapefile_snapshot_id"] for entry in listed] == [snapshot_id]
    assert client.get("/api/forestry/snapshots/published").json()["shapefile_snapshot_id"] == (
        snapshot_id
    )

    _sign_in(client, integration_connection, "operator", (("forestry", Role.OPERATOR),))
    assert client.get(f"/api/forestry/snapshots/{pending}/feature-collection").status_code == 200
