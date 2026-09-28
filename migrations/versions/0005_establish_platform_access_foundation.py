"""Establish platform access foundation.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_KEYS = ("lidar", "forestry", "transelect")
ROLE_KEYS = ("admin", "operator", "viewer")


def upgrade() -> None:
    """Create app_user, product_grant, and audit_event tables."""

    op.create_table(
        "app_user",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "identity_kind",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "identity_key",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "display_name",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(identity_kind) <> ''",
            name="ck_app_user_identity_kind_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(identity_key) <> ''",
            name="ck_app_user_identity_key_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(display_name) <> ''",
            name="ck_app_user_display_name_nonempty",
        ),
        sa.CheckConstraint(
            "email IS NULL OR btrim(email) <> ''",
            name="ck_app_user_email_nonempty",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_app_user",
        ),
        sa.UniqueConstraint(
            "identity_kind",
            "identity_key",
            name="uq_app_user_identity",
        ),
        schema="platform",
    )

    op.create_table(
        "product_grant",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "app_user_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "product_key",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}",
            name="ck_product_grant_product_key_known",
        ),
        sa.CheckConstraint(
            f"role IN {ROLE_KEYS!r}",
            name="ck_product_grant_role_known",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_product_grant_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_product_grant",
        ),
        sa.UniqueConstraint(
            "app_user_id",
            "product_key",
            name="uq_product_grant_user_product",
        ),
        schema="platform",
    )

    op.create_table(
        "audit_event",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "actor_app_user_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "event_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "product_key",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "subject_kind",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "subject_id",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(event_type) <> ''",
            name="ck_audit_event_event_type_nonempty",
        ),
        sa.CheckConstraint(
            "product_key IS NULL OR btrim(product_key) <> ''",
            name="ck_audit_event_product_key_nonempty",
        ),
        sa.CheckConstraint(
            "subject_kind IS NULL OR btrim(subject_kind) <> ''",
            name="ck_audit_event_subject_kind_nonempty",
        ),
        sa.CheckConstraint(
            "subject_id IS NULL OR btrim(subject_id) <> ''",
            name="ck_audit_event_subject_id_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["actor_app_user_id"],
            ["platform.app_user.id"],
            name="fk_audit_event_actor_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_audit_event",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_audit_event_occurred_at",
        "audit_event",
        ["occurred_at"],
        unique=False,
        schema="platform",
    )


def downgrade() -> None:
    """Remove platform access foundation tables in dependency order."""

    op.drop_index(
        "ix_audit_event_occurred_at",
        table_name="audit_event",
        schema="platform",
    )
    op.drop_table(
        "audit_event",
        schema="platform",
    )
    op.drop_table(
        "product_grant",
        schema="platform",
    )
    op.drop_table(
        "app_user",
        schema="platform",
    )
