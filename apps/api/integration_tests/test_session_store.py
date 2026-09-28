# apps/api/integration_tests/test_session_store.py

"""PlatformSessionStore: hashed-secret sessions backed by platform.session."""

from __future__ import annotations

from datetime import timedelta

from app.access_repository import resolve_or_create_app_user
from app.session_store import PlatformSessionStore
from sqlalchemy import Connection


def _make_user(connection: Connection) -> int:
    user = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-y",
        display_name="Test User",
    )
    return user.id


def test_create_and_resolve_round_trip(integration_connection: Connection) -> None:
    store = PlatformSessionStore()
    app_user_id = _make_user(integration_connection)

    raw_secret = store.create_session(
        integration_connection, app_user_id=app_user_id, ttl=timedelta(hours=8)
    )

    resolved = store.resolve_session(integration_connection, raw_secret)
    assert resolved == app_user_id


def test_unknown_secret_resolves_to_none(integration_connection: Connection) -> None:
    store = PlatformSessionStore()
    assert store.resolve_session(integration_connection, "not-a-real-secret") is None


def test_expired_session_resolves_to_none(integration_connection: Connection) -> None:
    store = PlatformSessionStore()
    app_user_id = _make_user(integration_connection)

    raw_secret = store.create_session(
        integration_connection, app_user_id=app_user_id, ttl=timedelta(seconds=-1)
    )

    assert store.resolve_session(integration_connection, raw_secret) is None


def test_raw_secret_is_never_stored(integration_connection: Connection) -> None:
    from sqlalchemy import text

    store = PlatformSessionStore()
    app_user_id = _make_user(integration_connection)
    raw_secret = store.create_session(
        integration_connection, app_user_id=app_user_id, ttl=timedelta(hours=8)
    )

    stored_hashes = (
        integration_connection.execute(text("SELECT session_secret_hash FROM platform.session"))
        .scalars()
        .all()
    )
    assert raw_secret not in stored_hashes
