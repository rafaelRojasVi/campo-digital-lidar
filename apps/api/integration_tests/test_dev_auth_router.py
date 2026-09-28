"""Dev-auth router: session lifecycle and default grant seeding.

The dev-auth router (app.routers.dev_auth) is now mounted only when
APP_ENV == "development" (see app.main and
apps/api/tests/test_main_dev_auth_gate.py). The integration test suite runs
with APP_ENV=test in the whole process, so that
app.db_safety.require_test_database can prove the target database is
disposable before any test touches it — and app.main decides whether to
mount the router from that same process-level APP_ENV, once, at import
time. There is no way for a single process to satisfy both "APP_ENV=test so
the DB-safety check passes" and "APP_ENV=development so the router is
mounted", so these tests can no longer drive the router's behavior through
real HTTP calls (that would 404 under APP_ENV=test).

Instead, each test exercises the router's handler functions directly, with a
locally constructed, non-ambient ``Settings(app_env="development", ...)``
(which legitimately satisfies ``assert_dev_auth_allowed`` without touching
process ``os.environ``). Test intent is preserved; only the transport is not
HTTP.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.access_repository import resolve_or_create_app_user
from app.config import Settings
from app.deps import get_current_app_user
from app.dev_auth import DEV_IDENTITY_KIND, DevSessionStore
from app.routers.dev_auth import DevLoginRequest, dev_login
from app.routers.session import logout
from app.session_store import PlatformSessionStore
from fastapi import HTTPException, Response
from sqlalchemy import Connection, text


def _development_settings() -> Settings:
    # Constructed directly (not read from os.environ), the same way
    # apps/api/tests/test_dev_auth.py's _settings() helper does — this
    # exercises "the router's handler would behave this way if reached in a
    # development process" without needing APP_ENV=development for the
    # whole test process.
    return Settings(app_env="development", postgres_password="x")


def test_me_without_session_returns_401(integration_connection: Connection) -> None:
    """get_current_app_user (what GET /auth/me depends on) rejects a request
    with no session cookie, regardless of which session store would apply."""

    with pytest.raises(HTTPException) as exc_info:
        get_current_app_user(
            _development_settings(),
            integration_connection,
            PlatformSessionStore(),
            DevSessionStore(),
            None,
        )
    assert exc_info.value.status_code == 401


def test_get_current_app_user_falls_back_to_dev_auth_on_platform_session_miss(
    integration_connection: Connection,
) -> None:
    """get_current_app_user must try PlatformSessionStore first, and only
    fall back to DevSessionStore where assert_dev_auth_allowed doesn't
    raise (APP_ENV=development). Here the PlatformSessionStore has no
    session at all, so a hit can only come from the dev-auth fallback path
    (assert_dev_auth_allowed -> DevSessionStore.resolve_session ->
    resolve_or_create_app_user) — proving that branch is actually reached
    and resolves to the expected identity, not just that it doesn't 401."""

    identity_key = "dev-operator"
    dev_sessions = DevSessionStore()
    token = dev_sessions.create_session(identity_key)

    user = get_current_app_user(
        _development_settings(),
        integration_connection,
        PlatformSessionStore(),
        dev_sessions,
        token,
    )

    assert user.identity_key == identity_key


def test_dev_login_unknown_identity_returns_422(integration_connection: Connection) -> None:
    """POST /auth/dev-login's handler rejects an identity_key outside
    SEEDED_DEV_IDENTITIES."""

    with pytest.raises(HTTPException) as exc_info:
        dev_login(
            DevLoginRequest(identity_key="not-a-real-identity"),
            Response(),
            _development_settings(),
            DevSessionStore(),
            integration_connection,
        )
    assert exc_info.value.status_code == 422


def test_dev_login_seeds_grants_sets_cookie_and_audits_session(
    integration_connection: Connection,
) -> None:
    """Calling the real dev_login handler for a first-time dev-admin login
    must: seed DEFAULT_SEED_GRANTS, set a session cookie with the expected
    security flags, and record a session.created audit event — exercising
    the handler itself rather than reimplementing its body, so this test
    would fail if dev_login stopped doing any of the above."""

    identity_key = "dev-admin"
    response = Response()

    result = dev_login(
        DevLoginRequest(identity_key=identity_key),
        response,
        _development_settings(),
        DevSessionStore(),
        integration_connection,
    )

    assert result.identity_key == identity_key
    product_keys = {grant.product_key for grant in result.product_grants}
    assert product_keys == {"lidar", "forestry", "transelect"}

    set_cookie_header = response.headers.get("set-cookie")
    assert set_cookie_header is not None
    assert "HttpOnly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header.lower()

    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind=DEV_IDENTITY_KIND,
        identity_key=identity_key,
        display_name="Dev Admin",
    )
    audit_row = integration_connection.execute(
        text(
            "SELECT event_type FROM platform.audit_event "
            "WHERE actor_app_user_id = :app_user_id AND event_type = 'session.created'"
        ),
        {"app_user_id": user.id},
    ).one_or_none()
    assert audit_row is not None


def test_session_lifecycle_create_resolve_and_logout_clear(
    integration_connection: Connection,
) -> None:
    """DevSessionStore's create_session/resolve_session/clear_session round
    trip (as dev-login/me/logout use it), confirmed against a real
    platform.app_user row rather than the bare string apps/api/tests's
    in-memory DevSessionStore unit tests use."""

    identity_key = "dev-viewer"
    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind=DEV_IDENTITY_KIND,
        identity_key=identity_key,
        display_name="Dev Viewer",
    )

    session_store = DevSessionStore()
    token = session_store.create_session(identity_key)

    resolved_identity_key = session_store.resolve_session(token)
    assert resolved_identity_key == identity_key

    resolved_user = resolve_or_create_app_user(
        integration_connection,
        identity_kind=DEV_IDENTITY_KIND,
        identity_key=resolved_identity_key,
        display_name="Dev Viewer",
    )
    assert resolved_user.id == user.id

    session_store.clear_session(token)
    assert session_store.resolve_session(token) is None


def test_logout_revokes_platform_session(integration_connection: Connection) -> None:
    """POST /auth/logout's handler must invalidate the caller's server-side
    PlatformSessionStore session, not just clear the cookie — otherwise a
    cleared cookie leaves a fully valid platform.session row reachable by
    anyone who still has the raw secret."""

    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind=DEV_IDENTITY_KIND,
        identity_key="dev-logout-subject",
        display_name="Dev Logout Subject",
    )
    platform_sessions = PlatformSessionStore()
    raw_secret = platform_sessions.create_session(
        integration_connection, app_user_id=user.id, ttl=timedelta(hours=1)
    )
    assert platform_sessions.resolve_session(integration_connection, raw_secret) == user.id

    logout(
        Response(),
        DevSessionStore(),
        platform_sessions,
        integration_connection,
        user.identity_key,
        raw_secret,
    )

    assert platform_sessions.resolve_session(integration_connection, raw_secret) is None
