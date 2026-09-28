"""Establish hosted Transelec workbook snapshots.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable Transelec workbook storage and active snapshot state."""

    op.create_table(
        "transelec_workbook_snapshot",
        sa.Column(
            "source_snapshot_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "filename",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "media_type",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "object_storage_key",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "business_rows",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "distinct_pmf",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "distinct_provisional_predio_ids",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "surface_total",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(filename) <> ''",
            name="ck_transelec_workbook_snapshot_filename_nonempty",
        ),
        sa.CheckConstraint(
            "media_type IS NULL OR btrim(media_type) <> ''",
            name="ck_transelec_workbook_snapshot_media_type_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(object_storage_key) <> ''",
            name="ck_transelec_workbook_snapshot_object_storage_key_nonempty",
        ),
        sa.CheckConstraint(
            "business_rows > 0",
            name="ck_transelec_workbook_snapshot_business_rows_positive",
        ),
        sa.CheckConstraint(
            "distinct_pmf > 0",
            name="ck_transelec_workbook_snapshot_distinct_pmf_positive",
        ),
        sa.CheckConstraint(
            "distinct_provisional_predio_ids >= 0",
            name="ck_transelec_workbook_snapshot_predio_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["platform.source_snapshot.id"],
            name="fk_transelec_workbook_snapshot_source_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "source_snapshot_id",
            name="pk_transelec_workbook_snapshot",
        ),
        schema="platform",
    )

    op.create_table(
        "transelec_dashboard_state",
        sa.Column(
            "id",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "active_source_snapshot_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "id = 1",
            name="ck_transelec_dashboard_state_singleton",
        ),
        sa.ForeignKeyConstraint(
            ["active_source_snapshot_id"],
            ["platform.transelec_workbook_snapshot.source_snapshot_id"],
            name="fk_transelec_dashboard_state_active_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_transelec_dashboard_state",
        ),
        schema="platform",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO platform.transelec_dashboard_state (
                id,
                active_source_snapshot_id
            )
            VALUES (1, NULL)
            """
        )
    )


def downgrade() -> None:
    """Remove hosted Transelec snapshot tables."""

    op.drop_table(
        "transelec_dashboard_state",
        schema="platform",
    )
    op.drop_table(
        "transelec_workbook_snapshot",
        schema="platform",
    )
