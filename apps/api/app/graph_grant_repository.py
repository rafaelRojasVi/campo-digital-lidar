"""Persistence adapter for encrypted Microsoft Graph token grants.

Tokens are encrypted by the caller (``app.token_crypto``) before reaching
this module — it only ever handles ciphertext, never a raw token value.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, text


def upsert_graph_grant(
    connection: Connection,
    *,
    app_user_id: int,
    access_token_encrypted: bytes,
    refresh_token_encrypted: bytes,
    scope: str,
    expires_at: datetime,
) -> None:
    """Replace the caller's stored Graph grant, one row per user.

    A fresh sign-in supersedes any prior grant (``platform.ms_graph_grant``
    has a unique constraint on ``app_user_id``) — there is exactly one
    current Graph grant per user, not a history of past ones.
    """

    connection.execute(
        text(
            """
            INSERT INTO platform.ms_graph_grant (
                app_user_id, access_token_encrypted, refresh_token_encrypted, scope, expires_at
            )
            VALUES (
                :app_user_id, :access_token_encrypted, :refresh_token_encrypted,
                :scope, :expires_at
            )
            ON CONFLICT (app_user_id) DO UPDATE SET
                access_token_encrypted = EXCLUDED.access_token_encrypted,
                refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                scope = EXCLUDED.scope,
                expires_at = EXCLUDED.expires_at,
                granted_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "app_user_id": app_user_id,
            "access_token_encrypted": access_token_encrypted,
            "refresh_token_encrypted": refresh_token_encrypted,
            "scope": scope,
            "expires_at": expires_at,
        },
    )
