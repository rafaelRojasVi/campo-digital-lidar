"""Establish Transelec field overrides (web edits) and the effective-row view.

Revision ID: 0012
Revises: 0011

Expand-only. Spec:
docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md.

- ``platform.transelec_field_override``: one row per web edit of one cell
  of one source row, keyed by the row's business key (PMF, Rol, N Predio,
  N Area de Corta) plus ``key_ordinal`` — the row's 1-based position among
  rows of the same import sharing that key, by ``source_row_number``.
  Rows are never deleted; an edit ends (``ended_at``/``end_reason``) and
  history stays. At most one active edit per cell (partial unique index).
- ``platform.transelec_norm_text(text)``: the one text comparison rule
  (trim and collapse ASCII whitespace plus U+00A0 NBSP to one space,
  blank → NULL, case kept). Mirrored exactly by
  ``transelec_ingestion.field_overrides.normalize_text``;
  ``apps/api/integration_tests/test_transelec_override_schema.py`` checks
  the two agree.
- ``platform.transelec_keyed_row``: every source row with its ``key_ordinal``.
- ``platform.transelec_override_state``: every active edit against every
  import — ``aplicada``, ``incorporada``, ``en_conflicto`` or ``huerfana``.
- ``platform.transelec_effective_row``: every source row with its applied
  edits — the relation every Transelec read selects from. Same column names
  as ``transelec_resumen_row`` plus ``key_ordinal`` and ``web_fields``.

The field lists below are frozen at this revision on purpose: a migration
must not import application code. ``apps/api/tests/
test_transelec_override_migration.py`` asserts they still equal the
registry and the projection. A later contract column must be added to
``transelec_effective_row`` by a new migration that recreates the views
(``test_transelec_overrides.py`` checks the view exposes every column the
router selects).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEXT_FIELDS: tuple[str, ...] = (
    "estado",
    "estado_resumido",
    "tipo_rechazo",
    "reingreso_tec",
    "reingreso_legal",
    "reingreso_recrep",
    "numero_ingreso",
    "numero_ingreso_2",
)
DATE_FIELDS: tuple[str, ...] = ("fecha_ingreso", "fecha_ingreso_2", "fecha_90_dias")
EDITABLE: tuple[str, ...] = TEXT_FIELDS + DATE_FIELDS

# transelec_resumen_row's contract columns at revision 0011, in contract order.
ROW_COLUMNS: tuple[str, ...] = (
    "aef",
    "quien_solicita",
    "fecha_solicitud",
    "fecha_corta",
    "fecha_termino",
    "predio_ref",
    "rol_ref",
    "area_ref",
    "pmf",
    "carpeta_source",
    "pas",
    "estado",
    "estado_resumido",
    "tipo_rechazo",
    "reingreso_tec",
    "reingreso_legal",
    "reingreso_recrep",
    "tipo_propietario",
    "id_transelec",
    "rol",
    "numero_predio",
    "numero_area_corta",
    "superficie_corta",
    "superficie_total_corta",
    "fecha_ingreso",
    "numero_ingreso",
    "fecha_90_dias",
    "hoy_raw",
    "fecha_ingreso_2",
    "numero_ingreso_2",
    "empresa",
    "id_predio_unico_ii",
    "id_pmf",
    "id_predio_unico",
    "tramite",
    "carpeta_normalizada",
    "sector",
)


def _quoted(names: Sequence[str]) -> str:
    return ", ".join(f"'{name}'" for name in names)


# The whitespace set is normalize_text's: " \t\r\n\f\v" plus U+00A0 (NBSP),
# which planilla cells carry. E'\x0B' is vertical tab (PostgreSQL E-strings
# have no \v escape); E'\u00A0' is NBSP (the database encoding is UTF8).
_NORM_TEXT = r"""
CREATE FUNCTION platform.transelec_norm_text(value text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT NULLIF(
        regexp_replace(
            btrim(value, E' \t\r\n\f\x0B\u00A0'),
            E'[ \t\r\n\f\x0B\u00A0]+',
            ' ',
            'g'
        ),
        ''
    )
$$
"""

_KEYED_ROW = """
CREATE VIEW platform.transelec_keyed_row AS
SELECT
    r.*,
    row_number() OVER (
        PARTITION BY r.import_id, r.pmf, r.rol, r.numero_predio, r.numero_area_corta
        ORDER BY r.source_row_number
    ) AS key_ordinal
FROM platform.transelec_resumen_row AS r
"""


def _override_state_sql() -> str:
    text_cases = "\n".join(f"                WHEN '{name}' THEN k.{name}" for name in TEXT_FIELDS)
    date_cases = "\n".join(f"            WHEN '{name}' THEN k.{name}" for name in DATE_FIELDS)
    return f"""
CREATE VIEW platform.transelec_override_state AS
SELECT
    i.id AS import_id,
    o.id AS override_id,
    o.field,
    k.source_row_number,
    s.source_text,
    s.source_date,
    CASE
        WHEN k.source_row_number IS NULL THEN 'huerfana'
        WHEN (s.source_text, s.source_date) IS NOT DISTINCT FROM
             (platform.transelec_norm_text(o.planilla_value_text), o.planilla_value_date)
            THEN 'aplicada'
        WHEN (s.source_text, s.source_date) IS NOT DISTINCT FROM
             (platform.transelec_norm_text(o.value_text), o.value_date)
            THEN 'incorporada'
        ELSE 'en_conflicto'
    END AS status
FROM platform.transelec_field_override AS o
CROSS JOIN platform.transelec_import AS i
LEFT JOIN platform.transelec_keyed_row AS k
    ON k.import_id = i.id
    AND k.pmf = o.pmf
    AND k.rol IS NOT DISTINCT FROM o.rol
    AND k.numero_predio IS NOT DISTINCT FROM o.numero_predio
    AND k.numero_area_corta IS NOT DISTINCT FROM o.numero_area_corta
    AND k.key_ordinal = o.key_ordinal
LEFT JOIN LATERAL (
    SELECT
        CASE
            WHEN o.field IN ({_quoted(DATE_FIELDS)}) THEN
                CASE WHEN d.value IS NULL
                    THEN platform.transelec_norm_text(k.source_text_dates -> o.field ->> 'raw')
                END
            ELSE platform.transelec_norm_text(CASE o.field
{text_cases}
            END)
        END AS source_text,
        d.value AS source_date
    FROM (
        SELECT CASE o.field
{date_cases}
        END AS value
    ) AS d
) AS s ON true
WHERE o.ended_at IS NULL
"""


def _effective_row_sql() -> str:
    aggregates = [
        "array_agg(s.field ORDER BY s.field) AS web_fields",
        "array_agg(s.field ORDER BY s.field) FILTER "
        f"(WHERE s.field IN ({_quoted(DATE_FIELDS)})) AS web_date_fields",
    ]
    for name in TEXT_FIELDS:
        aggregates.append(f"bool_or(s.field = '{name}') AS has_{name}")
        aggregates.append(f"max(o.value_text) FILTER (WHERE s.field = '{name}') AS web_{name}")
    for name in DATE_FIELDS:
        aggregates.append(f"bool_or(s.field = '{name}') AS has_{name}")
        aggregates.append(f"max(o.value_date) FILTER (WHERE s.field = '{name}') AS web_{name}")

    columns = [
        f"CASE WHEN a.has_{name} THEN a.web_{name} ELSE k.{name} END AS {name}"
        if name in EDITABLE
        else f"k.{name}"
        for name in ROW_COLUMNS
    ]
    aggregate_sql = ",\n        ".join(aggregates)
    column_sql = ",\n    ".join(columns)
    return f"""
CREATE VIEW platform.transelec_effective_row AS
SELECT
    k.import_id,
    k.source_row_number,
    k.key_ordinal,
    {column_sql},
    k.predio_group_key,
    CASE
        WHEN a.web_date_fields IS NULL THEN k.source_text_dates
        ELSE NULLIF(k.source_text_dates - a.web_date_fields, '{{}}'::jsonb)
    END AS source_text_dates,
    COALESCE(a.web_fields, ARRAY[]::text[]) AS web_fields
FROM platform.transelec_keyed_row AS k
LEFT JOIN (
    SELECT
        s.import_id,
        s.source_row_number,
        {aggregate_sql}
    FROM platform.transelec_override_state AS s
    JOIN platform.transelec_field_override AS o ON o.id = s.override_id
    WHERE s.status = 'aplicada'
    GROUP BY s.import_id, s.source_row_number
) AS a
    ON a.import_id = k.import_id AND a.source_row_number = k.source_row_number
"""


def upgrade() -> None:
    """Create the override table, the comparison function and the three views."""

    op.create_table(
        "transelec_field_override",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("pmf", sa.Text(), nullable=False),
        sa.Column("rol", sa.Text(), nullable=True),
        sa.Column("numero_predio", sa.Text(), nullable=True),
        sa.Column("numero_area_corta", sa.Text(), nullable=True),
        sa.Column("key_ordinal", sa.Integer(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("planilla_value_text", sa.Text(), nullable=True),
        sa.Column("planilla_value_date", sa.Date(), nullable=True),
        sa.Column("base_import_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_app_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_transelec_field_override"),
        sa.ForeignKeyConstraint(
            ["base_import_id"],
            ["platform.transelec_import.id"],
            name="fk_transelec_field_override_base_import",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_transelec_field_override_created_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_transelec_field_override_ended_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"field IN ({_quoted(EDITABLE)})", name="ck_transelec_field_override_field"
        ),
        sa.CheckConstraint(
            f"(field IN ({_quoted(DATE_FIELDS)}) AND value_text IS NULL) "
            f"OR (field NOT IN ({_quoted(DATE_FIELDS)}) AND value_date IS NULL "
            "AND planilla_value_date IS NULL)",
            name="ck_transelec_field_override_value_kind",
        ),
        sa.CheckConstraint("key_ordinal >= 1", name="ck_transelec_field_override_key_ordinal"),
        # "end_reason IS NOT NULL" is load-bearing: NULL IN (...) is NULL, and
        # a CHECK that evaluates to NULL passes, so without it an edit could
        # end with no reason.
        sa.CheckConstraint(
            "(ended_at IS NULL AND end_reason IS NULL) "
            "OR (ended_at IS NOT NULL AND end_reason IS NOT NULL AND end_reason IN "
            "('superseded', 'discarded', 'kept', 'incorporated'))",
            name="ck_transelec_field_override_end",
        ),
        schema="platform",
    )
    op.create_index(
        "uq_transelec_field_override_active_cell",
        "transelec_field_override",
        [
            "pmf",
            sa.text("coalesce(rol, '')"),
            sa.text("coalesce(numero_predio, '')"),
            sa.text("coalesce(numero_area_corta, '')"),
            "key_ordinal",
            "field",
        ],
        unique=True,
        schema="platform",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.execute(_NORM_TEXT)
    op.execute(_KEYED_ROW)
    op.execute(_override_state_sql())
    op.execute(_effective_row_sql())


def downgrade() -> None:
    """Drop the views, the function and the table; source rows are untouched."""

    op.execute("DROP VIEW platform.transelec_effective_row")
    op.execute("DROP VIEW platform.transelec_override_state")
    op.execute("DROP VIEW platform.transelec_keyed_row")
    op.execute("DROP FUNCTION platform.transelec_norm_text(text)")
    op.drop_index(
        "uq_transelec_field_override_active_cell",
        table_name="transelec_field_override",
        schema="platform",
    )
    op.drop_table("transelec_field_override", schema="platform")
