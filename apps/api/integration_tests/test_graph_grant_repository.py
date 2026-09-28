"""Integration tests for Microsoft Graph token grant persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.access_repository import resolve_or_create_app_user
from app.graph_grant_repository import upsert_graph_grant
from sqlalchemy import Connection, text


def _user(connection: Connection, identity_key: str) -> int:
    return resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key=identity_key,
        display_name="Grant Subject",
        email="grant-subject@example.com",
    ).id


def test_upsert_graph_grant_persists_encrypted_tokens_and_scope(
    integration_connection: Connection,
) -> None:
    app_user_id = _user(integration_connection, "tenant-x:oid-grant-1")
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    upsert_graph_grant(
        integration_connection,
        app_user_id=app_user_id,
        access_token_encrypted=b"encrypted-access",
        refresh_token_encrypted=b"encrypted-refresh",
        scope="openid profile User.Read",
        expires_at=expires_at,
    )

    row = integration_connection.execute(
        text(
            "SELECT access_token_encrypted, refresh_token_encrypted, scope "
            "FROM platform.ms_graph_grant WHERE app_user_id = :app_user_id"
        ),
        {"app_user_id": app_user_id},
    ).one()
    assert bytes(row.access_token_encrypted) == b"encrypted-access"
    assert bytes(row.refresh_token_encrypted) == b"encrypted-refresh"
    assert row.scope == "openid profile User.Read"


def test_upsert_graph_grant_replaces_the_prior_grant_for_the_same_user(
    integration_connection: Connection,
) -> None:
    app_user_id = _user(integration_connection, "tenant-x:oid-grant-2")
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    upsert_graph_grant(
        integration_connection,
        app_user_id=app_user_id,
        access_token_encrypted=b"first-access",
        refresh_token_encrypted=b"first-refresh",
        scope="User.Read",
        expires_at=expires_at,
    )
    upsert_graph_grant(
        integration_connection,
        app_user_id=app_user_id,
        access_token_encrypted=b"second-access",
        refresh_token_encrypted=b"second-refresh",
        scope="User.Read",
        expires_at=expires_at,
    )

    rows = integration_connection.execute(
        text("SELECT access_token_encrypted FROM platform.ms_graph_grant WHERE app_user_id = :id"),
        {"id": app_user_id},
    ).all()
    assert len(rows) == 1
    assert bytes(rows[0].access_token_encrypted) == b"second-access"
