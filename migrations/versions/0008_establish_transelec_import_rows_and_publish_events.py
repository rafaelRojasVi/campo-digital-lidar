"""Establish Transelec import, resumen row, and publish-event storage.

Revision ID: 0008
Revises: 0007

Adds the per-row persistence substrate that Task 3 (row projection) and a
later dashboard task will populate and read:

- `platform.transelec_import`: one immutable row per validated Resumen
  workbook import, keyed to the existing `platform.source_snapshot` (content
  identity) and `platform.ingestion_run` (who/when it was ingested).
  `UNIQUE (source_snapshot_id)` makes one-import-per-content-snapshot an
  idempotency guarantee enforced by the database, not just application code.
- `platform.transelec_resumen_row`: one row per original Resumen worksheet
  row for a given import, preserving the full 30-field V1 contract shape as
  typed columns. `predio_group_key` is declared `NOT NULL` here only as a
  column constraint; its value is computed by application code in Task 3,
  never by this migration.
- `platform.transelec_publish_event`: one row per publish/restore activation
  of an import, so an import may be activated more than once over its
  lifetime without losing the actor/timestamp of each activation.

This is an expand-only change to `platform.transelec_dashboard_state`: it
adds a new, nullable `active_import_id` pointer column and its FK. The
existing `active_source_snapshot_id` column and its FK to
`platform.transelec_workbook_snapshot` (from migration 0004) are left in
place, deprecated but untouched — confirmed unused by any router on `main`
today, but that is not proof no already-deployed environment still depends
on it. A later CONTRACT migration removes it only after confirming that.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create Transelec import/row/publish-event tables and expand dashboard_state."""

    op.create_table(
        "transelec_import",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "source_snapshot_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "schema_contract_version",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "parser_version",
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
            "validated_by_app_user_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "validated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "business_rows > 0",
            name="ck_transelec_import_business_rows_positive",
        ),
        sa.CheckConstraint(
            "distinct_pmf > 0",
            name="ck_transelec_import_distinct_pmf_positive",
        ),
        sa.CheckConstraint(
            "distinct_provisional_predio_ids >= 0",
            name="ck_transelec_import_predio_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["platform.source_snapshot.id"],
            name="fk_transelec_import_source_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["platform.ingestion_run.id"],
            name="fk_transelec_import_ingestion_run_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["validated_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_transelec_import_validated_by_app_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_transelec_import",
        ),
        sa.UniqueConstraint(
            "source_snapshot_id",
            name="uq_transelec_import_source_snapshot_id",
        ),
        schema="platform",
    )

    op.create_table(
        "transelec_resumen_row",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "import_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "source_row_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("predio_ref", sa.Text(), nullable=True),
        sa.Column("rol_ref", sa.Text(), nullable=True),
        sa.Column("area_ref", sa.Text(), nullable=True),
        sa.Column("pmf", sa.Text(), nullable=False),
        sa.Column("carpeta_source", sa.Text(), nullable=True),
        sa.Column("carpeta_normalizada", sa.Text(), nullable=True),
        sa.Column("pas", sa.Text(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=True),
        sa.Column("estado_resumido", sa.Text(), nullable=True),
        sa.Column("tipo_rechazo", sa.Text(), nullable=True),
        sa.Column("reingreso_tec", sa.Text(), nullable=True),
        sa.Column("reingreso_legal", sa.Text(), nullable=True),
        sa.Column("reingreso_recrep", sa.Text(), nullable=True),
        sa.Column("tipo_propietario", sa.Text(), nullable=True),
        sa.Column("id_transelec", sa.Text(), nullable=True),
        sa.Column("rol", sa.Text(), nullable=True),
        sa.Column("numero_predio", sa.Text(), nullable=True),
        sa.Column("numero_area_corta", sa.Text(), nullable=True),
        sa.Column("superficie_corta", sa.Float(), nullable=True),
        sa.Column("superficie_total_corta", sa.Float(), nullable=True),
        sa.Column("fecha_ingreso", sa.Date(), nullable=True),
        sa.Column("numero_ingreso", sa.Text(), nullable=True),
        sa.Column("fecha_90_dias", sa.Date(), nullable=True),
        sa.Column("hoy_raw", sa.Text(), nullable=True),
        sa.Column("empresa", sa.Text(), nullable=True),
        sa.Column("id_predio_unico_ii", sa.Text(), nullable=True),
        sa.Column("id_pmf", sa.Text(), nullable=True),
        sa.Column("id_predio_unico", sa.Text(), nullable=True),
        sa.Column("predio_group_key", sa.Text(), nullable=False),
        sa.Column("tramite", sa.Text(), nullable=True),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["platform.transelec_import.id"],
            name="fk_transelec_resumen_row_import_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_transelec_resumen_row",
        ),
        sa.UniqueConstraint(
            "import_id",
            "source_row_number",
            name="uq_transelec_resumen_row_import_source_row_number",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_pmf",
        "transelec_resumen_row",
        ["import_id", "pmf"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_predio",
        "transelec_resumen_row",
        ["import_id", "predio_group_key"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_estado_resumido",
        "transelec_resumen_row",
        ["import_id", "estado_resumido"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_sector",
        "transelec_resumen_row",
        ["import_id", "sector"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_empresa",
        "transelec_resumen_row",
        ["import_id", "empresa"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_pas",
        "transelec_resumen_row",
        ["import_id", "pas"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_tipo_propietario",
        "transelec_resumen_row",
        ["import_id", "tipo_propietario"],
        unique=False,
        schema="platform",
    )

    # Expand-only: add the new active-import pointer. active_source_snapshot_id
    # (and its FK to transelec_workbook_snapshot, from 0004) is untouched.
    op.add_column(
        "transelec_dashboard_state",
        sa.Column("active_import_id", sa.BigInteger(), nullable=True),
        schema="platform",
    )
    op.create_foreign_key(
        "fk_transelec_dashboard_state_active_import",
        "transelec_dashboard_state",
        "transelec_import",
        ["active_import_id"],
        ["id"],
        source_schema="platform",
        referent_schema="platform",
        ondelete="RESTRICT",
    )

    op.create_table(
        "transelec_publish_event",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "import_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('publish', 'restore')",
            name="ck_transelec_publish_event_event_type_known",
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["platform.transelec_import.id"],
            name="fk_transelec_publish_event_import_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["platform.app_user.id"],
            name="fk_transelec_publish_event_actor_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_transelec_publish_event",
        ),
        schema="platform",
    )


def downgrade() -> None:
    """Remove Transelec import/row/publish-event tables and the added column."""

    op.drop_table(
        "transelec_publish_event",
        schema="platform",
    )

    op.drop_constraint(
        "fk_transelec_dashboard_state_active_import",
        "transelec_dashboard_state",
        schema="platform",
        type_="foreignkey",
    )
    op.drop_column(
        "transelec_dashboard_state",
        "active_import_id",
        schema="platform",
    )

    op.drop_index(
        "ix_transelec_resumen_row_import_tipo_propietario",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_index(
        "ix_transelec_resumen_row_import_pas",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_index(
        "ix_transelec_resumen_row_import_empresa",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_index(
        "ix_transelec_resumen_row_import_sector",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_index(
        "ix_transelec_resumen_row_import_estado_resumido",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_index(
        "ix_transelec_resumen_row_import_predio",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_index(
        "ix_transelec_resumen_row_import_pmf",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_table(
        "transelec_resumen_row",
        schema="platform",
    )

    op.drop_table(
        "transelec_import",
        schema="platform",
    )
