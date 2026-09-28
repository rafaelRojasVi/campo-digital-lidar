"""Postgres-backed, hashed-secret session store for real (Entra) identities.

The raw secret is generated the same way app.dev_auth.DevSessionStore
generates its token (secrets.token_urlsafe), but only its SHA-256 hash is
persisted — a database read alone can never mint a session.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection, text


def _hash_secret(raw_secret: str) -> str:
    return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


class PlatformSessionStore:
    """Issues and resolves durable, hashed-secret sessions in `platform.session`."""

    def create_session(self, connection: Connection, *, app_user_id: int, ttl: timedelta) -> str:
        """Issue a new session for `app_user_id`, returning the raw cookie secret."""

        raw_secret = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + ttl

        connection.execute(
            text(
                """
                INSERT INTO platform.session (session_secret_hash, app_user_id, expires_at)
                VALUES (:session_secret_hash, :app_user_id, :expires_at)
                """
            ),
            {
                "session_secret_hash": _hash_secret(raw_secret),
                "app_user_id": app_user_id,
                "expires_at": expires_at,
            },
        )
        return raw_secret

    def resolve_session(self, connection: Connection, raw_secret: str) -> int | None:
        """Return the session's `app_user_id`, or None if unknown/expired."""

        row = connection.execute(
            text(
                """
                UPDATE platform.session
                SET last_seen_at = now()
                WHERE session_secret_hash = :session_secret_hash
                  AND expires_at > now()
                RETURNING app_user_id
                """
            ),
            {"session_secret_hash": _hash_secret(raw_secret)},
        ).one_or_none()

        return row.app_user_id if row is not None else None

    def clear_session(self, connection: Connection, raw_secret: str) -> None:
        """Invalidate a session, if present."""

        connection.execute(
            text("DELETE FROM platform.session WHERE session_secret_hash = :session_secret_hash"),
            {"session_secret_hash": _hash_secret(raw_secret)},
        )
