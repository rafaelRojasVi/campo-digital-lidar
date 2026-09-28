"""Add Transelec AEF tracking fields and the per-import mapping report.

Revision ID: 0009
Revises: 0008

Expand-only. The 09-Sept-2026 ``Resumen`` layout adds five columns ahead of
the V1 business table (``AEF``, ``Quien solicita``, ``Fecha solicitud``,
``Fecha corta``, ``Fecha termino``), and contract V2 recognizes columns by
header rather than by position (``transelec_ingestion.resumen_layout``).

- ``platform.transelec_resumen_row`` gains the five fields as nullable
  columns. They are row-level source values: NULL means the source row had
  no value (or the source layout had no such column), never "not applicable
  to the PMF". Rows of imports made before this revision stay NULL, which is
  exactly what their source said.
- ``platform.transelec_resumen_row.source_text_dates`` (JSONB, nullable)
  keeps, per date field whose cell held text instead of an Excel date, the
  raw text and how it was classified (a single Spanish written-out date that
  was parsed; several dates; ``-``; or unrecognized). NULL when the row had
  no such cell.
- ``platform.transelec_import`` gains ``mapping_report`` (the resolver's
  column decisions, ignored regions and issues with row/column references)
  and ``warning_count``. ``mapping_report`` is NULL for imports validated
  under contract V1, which kept no report; it is never back-filled, because
  the V1 parser made no decisions to record.

Nothing is dropped, renamed or rewritten, so an application still running
the previous revision keeps working against this schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the AEF row columns, their filter indexes and the import report."""

    op.add_column(
        "transelec_resumen_row",
        sa.Column("aef", sa.Text(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "transelec_resumen_row",
        sa.Column("quien_solicita", sa.Text(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "transelec_resumen_row",
        sa.Column("fecha_solicitud", sa.Date(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "transelec_resumen_row",
        sa.Column("fecha_corta", sa.Date(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "transelec_resumen_row",
        sa.Column("fecha_termino", sa.Date(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "transelec_resumen_row",
        sa.Column("source_text_dates", postgresql.JSONB(), nullable=True),
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_aef",
        "transelec_resumen_row",
        ["import_id", "aef"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_transelec_resumen_row_import_quien_solicita",
        "transelec_resumen_row",
        ["import_id", "quien_solicita"],
        unique=False,
        schema="platform",
    )

    op.add_column(
        "transelec_import",
        sa.Column("mapping_report", postgresql.JSONB(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "transelec_import",
        sa.Column(
            "warning_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema="platform",
    )
    op.create_check_constraint(
        "ck_transelec_import_warning_count_nonnegative",
        "transelec_import",
        "warning_count >= 0",
        schema="platform",
    )


def downgrade() -> None:
    """Remove the AEF row columns, their indexes and the import report."""

    op.drop_constraint(
        "ck_transelec_import_warning_count_nonnegative",
        "transelec_import",
        schema="platform",
        type_="check",
    )
    op.drop_column("transelec_import", "warning_count", schema="platform")
    op.drop_column("transelec_import", "mapping_report", schema="platform")

    op.drop_index(
        "ix_transelec_resumen_row_import_quien_solicita",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    op.drop_index(
        "ix_transelec_resumen_row_import_aef",
        table_name="transelec_resumen_row",
        schema="platform",
    )
    for column in (
        "source_text_dates",
        "fecha_termino",
        "fecha_corta",
        "fecha_solicitud",
        "quien_solicita",
        "aef",
    ):
        op.drop_column("transelec_resumen_row", column, schema="platform")
