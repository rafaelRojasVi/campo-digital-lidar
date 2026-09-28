"""Product-grant administration router: onboarding a signed-in user.

Covers app.routers.access_admin end-to-end against real PostgreSQL: only a
caller who already holds Action.MANAGE_ACCESS (Role.ADMIN) on the target
product may list or grant that product's roles, granting resolves the
grantee by the email captured at their own first sign-in, and mutations are
CSRF-gated like every other product's mutation routes.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from app.access_repository import grant_product_role, resolve_or_create_app_user
from app.csrf import CSRF_HEADER_NAME
from app.deps import SESSION_COOKIE_NAME
from app.dev_auth import DEFAULT_SEED_GRANTS, DEV_IDENTITY_KIND, SEEDED_DEV_IDENTITIES
from app.main import app
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

_platform_sessions = PlatformSessionStore()
_SAME_ORIGIN = "http://testserver"


@pytest.fixture
def client(integration_engine: Engine) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        test_client.engine = integration_engine
        yield test_client


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.connect() as conn:
        for table in ("session", "audit_event", "product_grant", "app_user"):
            conn.execute(text(f"DELETE FROM platform.{table}"))
        conn.commit()


def _login(client: TestClient, identity_key: str, *, email: str | None = None) -> str:
    """Authenticate as a seeded dev identity; return the raw session secret."""

    engine: Engine = client.engine
    display_name = next(
        (
            identity.display_name
            for identity in SEEDED_DEV_IDENTITIES
            if identity.identity_key == identity_key
        ),
        identity_key,
    )
    with engine.connect() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind=DEV_IDENTITY_KIND,
            identity_key=identity_key,
            display_name=display_name,
            email=email,
        )
        for product_key, role in DEFAULT_SEED_GRANTS.get(identity_key, ()):
            grant_product_role(connection, app_user_id=user.id, product_key=product_key, role=role)
        raw_secret = _platform_sessions.create_session(
            connection, app_user_id=user.id, ttl=timedelta(hours=8)
        )
        connection.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)
    return raw_secret


def _csrf_token(client: TestClient) -> str:
    response = client.get("/auth/csrf")
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def _create_signed_in_user(client: TestClient, *, email: str, display_name: str) -> int:
    engine: Engine = client.engine
    with engine.connect() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind="entra",
            identity_key=f"tenant-x:{email}",
            display_name=display_name,
            email=email,
        )
        connection.commit()
    return user.id


def test_list_requires_authentication(client: TestClient) -> None:
    assert client.get("/auth/admin/product-grants/transelect").status_code == 401


def test_list_requires_manage_access_on_that_product(client: TestClient) -> None:
    _login(client, "dev-viewer")  # DEFAULT_SEED_GRANTS: VIEWER on transelect only

    response = client.get("/auth/admin/product-grants/transelect")

    assert response.status_code == 403


def test_grant_returns_404_for_an_email_that_has_never_signed_in(client: TestClient) -> None:
    _login(client, "dev-admin")

    response = client.post(
        "/auth/admin/product-grants/transelect",
        json={"email": "unknown@example.com", "role": "viewer"},
        headers={CSRF_HEADER_NAME: _csrf_token(client), "Origin": _SAME_ORIGIN},
    )

    assert response.status_code == 404


def test_grant_requires_csrf_token(client: TestClient) -> None:
    _login(client, "dev-admin")
    _create_signed_in_user(client, email="javier@example.com", display_name="Javier")

    response = client.post(
        "/auth/admin/product-grants/transelect",
        json={"email": "javier@example.com", "role": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF verification failed."


def test_admin_grants_viewer_role_to_a_signed_in_user(client: TestClient) -> None:
    _login(client, "dev-admin")
    _create_signed_in_user(client, email="javier@example.com", display_name="Javier")

    response = client.post(
        "/auth/admin/product-grants/transelect",
        json={"email": "javier@example.com", "role": "viewer"},
        headers={CSRF_HEADER_NAME: _csrf_token(client), "Origin": _SAME_ORIGIN},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "javier@example.com"
    assert body["role"] == "viewer"

    listed = client.get("/auth/admin/product-grants/transelect")
    assert listed.status_code == 200
    assert {row["email"]: row["role"] for row in listed.json()}["javier@example.com"] == "viewer"


def test_grant_on_one_product_is_not_visible_when_listing_another(client: TestClient) -> None:
    _login(client, "dev-admin")
    _create_signed_in_user(client, email="javier@example.com", display_name="Javier")

    grant_response = client.post(
        "/auth/admin/product-grants/transelect",
        json={"email": "javier@example.com", "role": "viewer"},
        headers={CSRF_HEADER_NAME: _csrf_token(client), "Origin": _SAME_ORIGIN},
    )
    assert grant_response.status_code == 200, grant_response.text

    lidar_grants = client.get("/auth/admin/product-grants/lidar")
    assert lidar_grants.status_code == 200
    assert "javier@example.com" not in {row["email"] for row in lidar_grants.json()}


def _grant_events(client: TestClient) -> list[dict[str, object]]:
    engine: Engine = client.engine
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT actor_app_user_id, product_key, subject_kind, subject_id, metadata
                FROM platform.audit_event
                WHERE event_type = 'product_grant.changed'
                ORDER BY id
                """
            )
        ).mappings()
        return [dict(row) for row in rows]


def _actor_id(client: TestClient, identity_key: str) -> int:
    engine: Engine = client.engine
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT id FROM platform.app_user WHERE identity_key = :key"),
                {"key": identity_key},
            ).scalar_one()
        )


def test_a_grant_records_who_changed_which_role_to_what(client: TestClient) -> None:
    _login(client, "dev-admin")
    grantee_id = _create_signed_in_user(client, email="javier@example.com", display_name="Javier")

    response = client.post(
        "/auth/admin/product-grants/transelect",
        json={"email": "javier@example.com", "role": "viewer"},
        headers={CSRF_HEADER_NAME: _csrf_token(client), "Origin": _SAME_ORIGIN},
    )

    assert response.status_code == 200, response.text
    assert _grant_events(client) == [
        {
            "actor_app_user_id": _actor_id(client, "dev-admin"),
            "product_key": "transelect",
            "subject_kind": "app_user",
            "subject_id": str(grantee_id),
            "metadata": {"previous_role": None, "role": "viewer", "via": "admin_api"},
        }
    ]


def test_a_role_change_records_the_role_it_replaced(client: TestClient) -> None:
    _login(client, "dev-admin")
    _create_signed_in_user(client, email="javier@example.com", display_name="Javier")
    csrf = _csrf_token(client)

    for role in ("viewer", "admin"):
        response = client.post(
            "/auth/admin/product-grants/transelect",
            json={"email": "javier@example.com", "role": role},
            headers={CSRF_HEADER_NAME: csrf, "Origin": _SAME_ORIGIN},
        )
        assert response.status_code == 200, response.text

    assert [event["metadata"] for event in _grant_events(client)] == [
        {"previous_role": None, "role": "viewer", "via": "admin_api"},
        {"previous_role": "viewer", "role": "admin", "via": "admin_api"},
    ]


def test_a_refused_grant_records_no_role_change(client: TestClient) -> None:
    _login(client, "dev-viewer")
    _create_signed_in_user(client, email="javier@example.com", display_name="Javier")

    response = client.post(
        "/auth/admin/product-grants/transelect",
        json={"email": "javier@example.com", "role": "admin"},
        headers={CSRF_HEADER_NAME: _csrf_token(client), "Origin": _SAME_ORIGIN},
    )

    assert response.status_code == 403
    assert _grant_events(client) == []
