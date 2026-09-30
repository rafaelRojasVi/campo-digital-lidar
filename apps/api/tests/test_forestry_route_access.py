"""Every forestry route requires a session and a ``forestry`` grant.

The rodal data is a client's private estate. These no-database tests prove
the requirement is structural (declared once on the router, so a new route
cannot be added without it) and that an anonymous caller is refused with
``401`` before any route or database work runs. Real sessions, the ``403``
for a Transelec-only account and the ``200`` for a forestry viewer are
covered against PostGIS in
``apps/api/integration_tests/test_forestry_route_access.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from app.config import Settings, get_settings
from app.deps import get_db_connection
from app.main import app
from app.routers.forestry import get_forestry_read_connection, require_forestry_viewer
from app.routers.forestry import router as forestry_router
from app.routers.forestry_workflow import router as forestry_workflow_router
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


def _forestry_routes() -> list[APIRoute]:
    return [
        route
        for router in (forestry_router, forestry_workflow_router)
        for route in router.routes
        if isinstance(route, APIRoute)
    ]


def _mounted_forestry_paths() -> set[str]:
    return {path for path in app.openapi()["paths"] if path.startswith("/api/forestry")}


def concrete_forestry_urls() -> list[tuple[str, str]]:
    """One requestable (method, URL) per forestry route, with valid parameters."""

    urls = []
    for route in _forestry_routes():
        url = route.path.replace("{shapefile_snapshot_id}", "1").replace("{feature_ordinal}", "1")
        if url.endswith("/use-distribution"):
            url += "?field=uso_2024"
        for method in sorted(route.methods or ()):
            urls.append((method, url))
    return urls


def test_the_forestry_router_is_mounted_with_every_route() -> None:
    assert len(_forestry_routes()) == 14
    assert _mounted_forestry_paths() == {route.path for route in _forestry_routes()}


def test_every_forestry_route_depends_on_the_forestry_grant() -> None:
    for route in _forestry_routes():
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert require_forestry_viewer in calls, route.path


@pytest.fixture
def anonymous_client() -> Iterator[tuple[TestClient, Mock, Mock]]:
    session_connection = Mock()
    read_connection = Mock()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, app_env="production", postgres_password="x"
    )
    app.dependency_overrides[get_db_connection] = lambda: session_connection
    app.dependency_overrides[get_forestry_read_connection] = lambda: read_connection
    try:
        yield TestClient(app), session_connection, read_connection
    finally:
        for dependency in (get_settings, get_db_connection, get_forestry_read_connection):
            app.dependency_overrides.pop(dependency, None)


@pytest.mark.parametrize(("method", "url"), concrete_forestry_urls())
def test_anonymous_callers_get_401_and_no_data_is_read(
    anonymous_client: tuple[TestClient, Mock, Mock], method: str, url: str
) -> None:
    client, session_connection, read_connection = anonymous_client

    response = client.request(method, url)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}
    assert read_connection.execute.call_count == 0
    assert session_connection.execute.call_count == 0
