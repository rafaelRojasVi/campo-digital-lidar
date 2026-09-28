"""Establish platform ingestion foundation.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_KEYS = ("lidar", "forestry", "transelect")


def upgrade() -> None:
    """Create upload/ingestion/job/artifact tables and extend source_snapshot."""

    op.add_column(
        "source_snapshot",
        sa.Column("object_storage_key", sa.Text(), nullable=True),
        schema="platform",
    )
    op.create_check_constraint(
        "ck_source_snapshot_object_storage_key_nonempty",
        "source_snapshot",
        "object_storage_key IS NULL OR btrim(object_storage_key) <> ''",
        schema="platform",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_source_snapshot_object_storage_key "
        "ON platform.source_snapshot (object_storage_key) "
        "WHERE object_storage_key IS NOT NULL"
    )

    op.create_table(
        "upload_session",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("app_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("declared_media_type", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}",
            name="ck_upload_session_product_key_known",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_upload_session_status_known",
        ),
        sa.CheckConstraint(
            "btrim(original_filename) <> ''",
            name="ck_upload_session_original_filename_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["platform.app_user.id"],
            name="fk_upload_session_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["platform.source_snapshot.id"],
            name="fk_upload_session_source_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_upload_session"),
        schema="platform",
    )

    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("requested_by_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}",
            name="ck_ingestion_run_product_key_known",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["platform.source_snapshot.id"],
            name="fk_ingestion_run_source_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_ingestion_run_requested_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_run"),
        schema="platform",
    )

    op.create_table(
        "processing_job",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ingestion_run_id", sa.BigInteger(), nullable=False),
        sa.Column("product_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("requested_by_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"product_key IN {PRODUCT_KEYS!r}",
            name="ck_processing_job_product_key_known",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_processing_job_status_known",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_processing_job_attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name="ck_processing_job_max_attempts_positive",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["platform.ingestion_run.id"],
            name="fk_processing_job_ingestion_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_processing_job_requested_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_job"),
        schema="platform",
    )
    op.create_index(
        "ix_processing_job_status_created_at",
        "processing_job",
        ["status", "created_at"],
        unique=False,
        schema="platform",
    )

    op.create_table(
        "processing_attempt",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("processing_job_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_processing_attempt_attempt_number_positive",
        ),
        sa.CheckConstraint(
            "btrim(worker_id) <> ''",
            name="ck_processing_attempt_worker_id_nonempty",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_processing_attempt_status_known",
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["platform.processing_job.id"],
            name="fk_processing_attempt_processing_job_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_attempt"),
        sa.UniqueConstraint(
            "processing_job_id",
            "attempt_number",
            name="uq_processing_attempt_job_attempt",
        ),
        schema="platform",
    )

    op.create_table(
        "generated_artifact",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("processing_job_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_kind", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(artifact_kind) <> ''",
            name="ck_generated_artifact_artifact_kind_nonempty",
        ),
        sa.CheckConstraint(
            "btrim(storage_key) <> ''",
            name="ck_generated_artifact_storage_key_nonempty",
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name="ck_generated_artifact_byte_size_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["platform.processing_job.id"],
            name="fk_generated_artifact_processing_job_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generated_artifact"),
        schema="platform",
    )


def downgrade() -> None:
    """Remove platform ingestion foundation tables and the added column."""

    op.drop_table("generated_artifact", schema="platform")
    op.drop_table("processing_attempt", schema="platform")
    op.drop_index(
        "ix_processing_job_status_created_at",
        table_name="processing_job",
        schema="platform",
    )
    op.drop_table("processing_job", schema="platform")
    op.drop_table("ingestion_run", schema="platform")
    op.drop_table("upload_session", schema="platform")
    op.execute("DROP INDEX platform.uq_source_snapshot_object_storage_key")
    op.drop_constraint(
        "ck_source_snapshot_object_storage_key_nonempty",
        "source_snapshot",
        schema="platform",
    )
    op.drop_column("source_snapshot", "object_storage_key", schema="platform")
