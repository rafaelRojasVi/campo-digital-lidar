"""Add the second ingreso pair of the 30-Sept-2026 Transelec ``Resumen`` layout.

Revision ID: 0011
Revises: 0010

Expand-only. The 30-Sept-2026 workbook renamed ``Fecha de ingreso`` /
``N Ingreso`` to ``Fecha de ingreso1`` / ``N Ingreso1`` (documented aliases,
no schema change) and added ``Fecha de ingreso2`` / ``N Ingreso2`` for a
plan's re-entry (reingreso) after a rejection.

- ``platform.transelec_resumen_row`` gains ``fecha_ingreso_2`` (DATE) and
  ``numero_ingreso_2`` (TEXT), both nullable. NULL means the source row had
  no value or the source layout had no such column; rows of earlier imports
  stay NULL, which is exactly what their source said. Text in
  ``Fecha de ingreso2`` is classified like every other date column and kept
  in ``source_text_dates``.

No index: neither field is a multi-select filter. Nothing is dropped,
renamed or rewritten, so an application still running the previous revision
keeps working against this schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two nullable second-ingreso columns."""

    op.add_column(
        "transelec_resumen_row",
        sa.Column("fecha_ingreso_2", sa.Date(), nullable=True),
        schema="platform",
    )
    op.add_column(
        "transelec_resumen_row",
        sa.Column("numero_ingreso_2", sa.Text(), nullable=True),
        schema="platform",
    )


def downgrade() -> None:
    """Drop the two columns; the first ingreso pair is untouched."""

    op.drop_column("transelec_resumen_row", "numero_ingreso_2", schema="platform")
    op.drop_column("transelec_resumen_row", "fecha_ingreso_2", schema="platform")
