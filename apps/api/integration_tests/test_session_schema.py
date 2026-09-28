# apps/api/integration_tests/test_session_schema.py

"""platform.session and platform.ms_graph_grant must exist with the shape
Task 4 (session_store.py) and Task 8 (entra_auth.py) depend on.
"""

from __future__ import annotations

from sqlalchemy import Connection, text


def test_session_table_has_expected_columns(integration_connection: Connection) -> None:
    rows = (
        integration_connection.execute(
            text(
                """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'platform' AND table_name = 'session'
            """
            )
        )
        .scalars()
        .all()
    )
    assert set(rows) == {
        "id",
        "session_secret_hash",
        "app_user_id",
        "created_at",
        "last_seen_at",
        "expires_at",
    }


def test_ms_graph_grant_is_one_per_user(integration_connection: Connection) -> None:
    result = integration_connection.execute(
        text(
            """
            SELECT conname FROM pg_constraint
            WHERE conname = 'uq_ms_graph_grant_app_user_id'
            """
        )
    ).scalar_one_or_none()
    assert result == "uq_ms_graph_grant_app_user_id"
