"""Establish platform session and Microsoft Graph grant storage.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the session and Microsoft Graph grant tables."""

    op.create_table(
        "session",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_secret_hash", sa.Text(), nullable=False),
        sa.Column("app_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "btrim(session_secret_hash) <> ''",
            name="ck_session_session_secret_hash_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_session_app_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session"),
        sa.UniqueConstraint("session_secret_hash", name="uq_session_session_secret_hash"),
        schema="platform",
    )
    op.create_index(
        "ix_session_app_user_id",
        "session",
        ["app_user_id"],
        unique=False,
        schema="platform",
    )

    op.create_table(
        "ms_graph_grant",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("app_user_id", sa.BigInteger(), nullable=False),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(scope) <> ''",
            name="ck_ms_graph_grant_scope_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_ms_graph_grant_app_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ms_graph_grant"),
        sa.UniqueConstraint("app_user_id", name="uq_ms_graph_grant_app_user_id"),
        schema="platform",
    )


def downgrade() -> None:
    """Remove the session and Microsoft Graph grant tables."""

    op.drop_table("ms_graph_grant", schema="platform")
    op.drop_index("ix_session_app_user_id", table_name="session", schema="platform")
    op.drop_table("session", schema="platform")
