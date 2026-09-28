"""app.routers.session (GET /auth/me, POST /auth/logout): reachable in every
APP_ENV, unlike app.routers.dev_auth (development-only). This is the
production-integration defect Slice 8 fixes: the frontend
(apps/portal/src/lib/platformApi.ts, products/transelect/dashboard/src/api.ts)
already calls both paths unconditionally, and a real (Entra) session has no
other way to be inspected or ended outside development.

Exercised through real HTTP against the shared app (unlike
test_dev_auth_router.py, which must call handlers directly because
dev_auth_router is conditionally mounted) — this router is mounted
unconditionally, so the integration process's fixed APP_ENV=test does not
change whether it is reachable.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from app.access import Role
from app.access_repository import grant_product_role, resolve_or_create_app_user
from app.deps import SESSION_COOKIE_NAME
from app.main import app
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

_platform_sessions = PlatformSessionStore()


@pytest.fixture
def client(integration_engine: Engine) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        test_client.engine = integration_engine
        yield test_client


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.connect() as conn:
        for table in ("session", "product_grant", "app_user"):
            conn.execute(text(f"DELETE FROM platform.{table}"))
        conn.commit()


def _real_session(client: TestClient) -> str:
    """Establish a real (Entra-shaped, non-dev-auth) session; return its raw secret."""

    engine: Engine = client.engine
    with engine.connect() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind="entra",
            identity_key="tenant-x:oid-session-subject",
            display_name="Javier",
            email="javier@example.com",
        )
        grant_product_role(
            connection, app_user_id=user.id, product_key="transelect", role=Role.VIEWER
        )
        raw_secret = _platform_sessions.create_session(
            connection, app_user_id=user.id, ttl=timedelta(hours=8)
        )
        connection.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)
    return raw_secret


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_returns_identity_and_grants_for_a_real_platform_session(client: TestClient) -> None:
    _real_session(client)

    response = client.get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Javier"
    assert body["product_grants"] == [{"product_key": "transelect", "role": "viewer"}]


def test_logout_without_authentication_is_rejected(client: TestClient) -> None:
    assert client.post("/auth/logout").status_code == 401


def _csrf_headers(client: TestClient) -> dict[str, str]:
    body = client.get("/auth/csrf").json()
    return {body["header_name"]: body["csrf_token"]}


def test_logout_without_a_csrf_token_is_rejected_and_keeps_the_session(
    client: TestClient,
) -> None:
    """Ending a session is a state change: another site must not be able to
    sign a user out, so logout demands the same token every mutation does."""

    raw_secret = _real_session(client)

    response = client.post("/auth/logout")

    assert response.status_code == 403
    assert client.get("/auth/me").status_code == 200
    with client.engine.connect() as connection:
        assert _platform_sessions.resolve_session(connection, raw_secret) is not None


def test_logout_clears_a_real_platform_session(client: TestClient) -> None:
    raw_secret = _real_session(client)

    response = client.post("/auth/logout", headers=_csrf_headers(client))

    assert response.status_code == 204
    assert client.get("/auth/me").status_code == 401
    with client.engine.connect() as connection:
        assert _platform_sessions.resolve_session(connection, raw_secret) is None
