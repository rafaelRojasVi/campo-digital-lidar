"""Step B of the Transelec ingestion lifecycle: validate and project.

One transaction, ending in COMMIT — **never** in activation. This module
knows nothing about publishing: it creates an immutable
``platform.transelec_import`` row and its ``platform.transelec_resumen_row``
projection, verifies structural invariants against the rows it just wrote,
and returns. Making an import the one the dashboard serves is a separate,
explicit mutation (Step C/D, ``app.transelec_publication``).

The source contract (``xlsx_contract.load_transelec_workbook``, backed by
``resumen_layout``) is treated here as a **hard gate for blocking issues
only**: an ``error`` in the layout report raises, and it raises before any
statement is issued, so a rejected workbook cannot leave a partial write
behind. ``warning`` and ``info`` issues do not block; the full report is
persisted on the import row so the operator can review it before the
separate, explicit publish step. Upload-time inspection
(``app.inspection.transelec_inspector``) keeps its evidence-only behavior —
gating happens at this Transelec-specific step, not by changing the shared
multi-product upload boundary.

Invariant verification is **purely structural**: the aggregates recorded on
the import row are recomputed from the persisted rows themselves and
compared with what the parsed workbook produced. Nothing here compares
against the 729/159/272/164.63 counts observed in the reviewed 14-Aug
snapshot — those are evidence for one snapshot, not acceptance-gate
constants, and a differently sized workbook that satisfies the structural
contract must still pass.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Connection, text

from transelec_ingestion.resumen_layout import FIELD_SPECS
from transelec_ingestion.resumen_layout import PARSER_VERSION as _LAYOUT_PARSER_VERSION
from transelec_ingestion.xlsx_contract import (
    ResumenSourceRow,
    load_transelec_workbook,
)

SCHEMA_CONTRACT_VERSION = "transelec-resumen-v2"

# Bumped whenever parsing/coercion behavior changes in a way that could
# produce different column values from identical bytes. Owned by the layout
# resolver, which is where that behavior now lives.
PARSER_VERSION = _LAYOUT_PARSER_VERSION

# Relative tolerance for comparing a Python float sum against PostgreSQL's
# SUM() of the same double-precision values: both are IEEE 754 doubles, but
# neither guarantees summation order, so bit-exact equality is the wrong
# assertion.
_SURFACE_TOTAL_RELATIVE_TOLERANCE = 1e-9

_ColumnKind = Literal["text", "number", "date"]


class ImportProjectionError(RuntimeError):
    """Base error for the validate-and-project step."""


class ImportInvariantError(ImportProjectionError):
    """Persisted rows disagree with the aggregates computed from the source."""


@dataclass(frozen=True, slots=True)
class ColumnProjection:
    """How one recognized ``Resumen`` field maps onto one persisted column."""

    contract_field: str
    column: str
    kind: _ColumnKind


# One entry per recognized field, in resumen_layout.FIELD_SPECS order. The
# worksheet's two "Carpeta" columns are resolved to distinct fields by the
# layout resolver's explicit neighbour rule before they reach this table, and
# the table is checked against FIELD_SPECS at import time.
RESUMEN_ROW_PROJECTION: tuple[ColumnProjection, ...] = (
    # AEF tracking block (09-Sept-2026 layout, columns A:E). Row-level source
    # values: a value on one row says nothing about the PMF's other rows.
    ColumnProjection("aef", "aef", "text"),
    ColumnProjection("quien_solicita", "quien_solicita", "text"),
    ColumnProjection("fecha_solicitud", "fecha_solicitud", "date"),
    ColumnProjection("fecha_corta", "fecha_corta", "date"),
    ColumnProjection("fecha_termino", "fecha_termino", "date"),
    ColumnProjection("predio_ref", "predio_ref", "text"),
    ColumnProjection("rol_ref", "rol_ref", "text"),
    ColumnProjection("area_ref", "area_ref", "text"),
    ColumnProjection("pmf", "pmf", "text"),
    ColumnProjection("carpeta_source", "carpeta_source", "text"),
    ColumnProjection("pas", "pas", "text"),
    ColumnProjection("estado", "estado", "text"),
    ColumnProjection("estado_resumido", "estado_resumido", "text"),
    ColumnProjection("tipo_rechazo", "tipo_rechazo", "text"),
    ColumnProjection("reingreso_tec", "reingreso_tec", "text"),
    ColumnProjection("reingreso_legal", "reingreso_legal", "text"),
    ColumnProjection("reingreso_recrep", "reingreso_recrep", "text"),
    ColumnProjection("tipo_propietario", "tipo_propietario", "text"),
    ColumnProjection("id_transelec", "id_transelec", "text"),
    ColumnProjection("rol", "rol", "text"),
    ColumnProjection("numero_predio", "numero_predio", "text"),
    ColumnProjection("numero_area_corta", "numero_area_corta", "text"),
    ColumnProjection("superficie_corta", "superficie_corta", "number"),
    ColumnProjection("superficie_total_corta", "superficie_total_corta", "number"),
    ColumnProjection("fecha_ingreso", "fecha_ingreso", "date"),
    ColumnProjection("numero_ingreso", "numero_ingreso", "text"),
    ColumnProjection("fecha_90_dias", "fecha_90_dias", "date"),
    # "Hoy" is stored as the raw source representation (a date OR free text)
    # because the workbook audit found it type-inconsistent. It is never
    # used as ingestion time — observation time belongs to shared source
    # provenance.
    ColumnProjection("hoy", "hoy_raw", "text"),
    ColumnProjection("empresa", "empresa", "text"),
    ColumnProjection("id_predio_unico_ii", "id_predio_unico_ii", "text"),
    ColumnProjection("id_pmf", "id_pmf", "text"),
    ColumnProjection("id_predio_unico", "id_predio_unico", "text"),
    ColumnProjection("tramite", "tramite", "text"),
    ColumnProjection("carpeta_normalizada", "carpeta_normalizada", "text"),
    ColumnProjection("sector", "sector", "text"),
)

# ``source_text_dates``: per date field whose cell held text, that raw text
# and its classification (resumen_layout.TextDateEvidence), or NULL.
_DERIVED_COLUMNS = ("predio_group_key", "source_text_dates")
_JSONB_COLUMNS = frozenset({"source_text_dates"})

_ROW_COLUMNS: tuple[str, ...] = (
    tuple(spec.column for spec in RESUMEN_ROW_PROJECTION) + _DERIVED_COLUMNS
)

if tuple((spec.contract_field, spec.kind) for spec in RESUMEN_ROW_PROJECTION) != tuple(
    (spec.name, spec.kind) for spec in FIELD_SPECS
):  # pragma: no cover - a contract change must break loudly at import time
    raise RuntimeError(
        "RESUMEN_ROW_PROJECTION no longer matches resumen_layout.FIELD_SPECS; "
        "the source contract changed and this projection must be revised."
    )


@dataclass(frozen=True, slots=True)
class ProjectedRow:
    """One persisted-shape row, keyed by destination column name."""

    source_row_number: int
    columns: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ValidatedWorkbook:
    """A contract-valid workbook, projected but not yet persisted."""

    rows: tuple[ProjectedRow, ...]
    business_rows: int
    distinct_pmf: int
    distinct_provisional_predio_ids: int
    surface_total: float
    mapping_report: dict[str, Any]
    warning_count: int


@dataclass(frozen=True, slots=True)
class ImportProjectionResult:
    """Outcome of Step B for one source snapshot."""

    import_id: int
    source_snapshot_id: int
    ingestion_run_id: int
    business_rows: int
    distinct_pmf: int
    distinct_provisional_predio_ids: int
    surface_total: float
    validated_at: dt.datetime
    already_existed: bool
    # None for an import validated before contract V2, which kept no report.
    mapping_report: dict[str, Any] | None
    warning_count: int


def _text(value: Any) -> str | None:
    """Render a source cell as text, or None when it carries no value.

    Excel stores every number as a double, so an integer identifier arrives
    as ``123.0``; rendering that verbatim would corrupt identifiers and the
    derived ``predio_group_key``. An integral float is therefore rendered
    without its decimal part. Dates are rendered ISO-8601 so a date landing
    in a text column (``Hoy``) keeps an unambiguous representation.
    """

    if value is None:
        return None

    if isinstance(value, bool):
        rendered = str(value)
    elif isinstance(value, float):
        rendered = str(int(value)) if value.is_integer() else str(value)
    elif isinstance(value, dt.datetime):
        rendered = value.date().isoformat() if _is_midnight(value) else value.isoformat()
    elif isinstance(value, dt.date):
        rendered = value.isoformat()
    else:
        rendered = str(value)

    rendered = rendered.strip()
    return rendered or None


def _is_midnight(value: dt.datetime) -> bool:
    return (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0)


def _number(value: Any) -> float | None:
    """Coerce a source cell to a float, or None when it is blank/non-numeric.

    Non-numeric content becomes NULL rather than an error: the destination
    columns are nullable by design, and the source contract gates structure
    (columns and their order), not per-cell types. Excluded values are also
    excluded from ``surface_total``, matching the aggregate shape the prior
    Transelec draft established.
    """

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)

    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        return float(candidate)
    except ValueError:
        return None


def _date(value: Any) -> dt.date | None:
    """Coerce a source cell to a date, or None when it is blank/not a date."""

    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


_COERCERS = {"text": _text, "number": _number, "date": _date}


def resolve_predio_group_key(
    *,
    id_predio_unico: str | None,
    pmf: str | None,
    rol: str | None,
    numero_predio: str | None,
) -> str:
    """Return the derived display/grouping key for one row.

    ``id_predio_unico`` (the workbook's own computed value) when non-blank,
    else the evidenced composite fallback ``PMF-rol-numero_predio``. Never
    written back into ``id_predio_unico``: the raw source value stays raw.

    The result is never blank, because the source contract guarantees every
    business row has a non-blank PMF — which matters, since
    ``transelec_resumen_row.predio_group_key`` is NOT NULL with no default.
    """

    if id_predio_unico is not None and id_predio_unico.strip():
        return id_predio_unico.strip()

    return f"{(pmf or '').strip()}-{(rol or '').strip()}-{(numero_predio or '').strip()}"


def _project_row(source_row: ResumenSourceRow) -> ProjectedRow:
    columns: dict[str, Any] = {}

    for spec in RESUMEN_ROW_PROJECTION:
        columns[spec.column] = _COERCERS[spec.kind](source_row.values[spec.contract_field])

    # A date column whose cell held text: the unambiguous single date read
    # from it (if any) becomes the column value, and the raw text is kept
    # verbatim beside it so nothing unresolved is lost.
    for name, evidence in source_row.text_dates.items():
        if evidence.parsed is not None:
            columns[name] = evidence.parsed
    columns["source_text_dates"] = (
        json.dumps(
            {name: evidence.to_dict() for name, evidence in sorted(source_row.text_dates.items())},
            ensure_ascii=False,
        )
        if source_row.text_dates
        else None
    )

    columns["predio_group_key"] = resolve_predio_group_key(
        id_predio_unico=columns["id_predio_unico"],
        pmf=columns["pmf"],
        rol=columns["rol"],
        numero_predio=columns["numero_predio"],
    )

    return ProjectedRow(source_row_number=source_row.source_row_number, columns=columns)


def read_validated_workbook(workbook_path: str | Path) -> ValidatedWorkbook:
    """Resolve the layout, gate on blocking issues, and project every row.

    Raises ``TranselecWorkbookError`` (carrying the full layout report) on
    any blocking issue — no ``Resumen`` worksheet, no recognizable header,
    a missing identity/required column, an ambiguous ``Carpeta``, duplicate
    headers with conflicting values, or no PMF-bearing row. Touches no
    database.
    """

    workbook = load_transelec_workbook(workbook_path)
    rows = tuple(_project_row(source_row) for source_row in workbook.resumen_rows)

    blank_key_rows = [row.source_row_number for row in rows if not row.columns["pmf"]]
    if blank_key_rows:  # pragma: no cover - the contract already excludes these rows
        raise ImportProjectionError(f"Projected rows without a PMF value: rows={blank_key_rows}")

    return ValidatedWorkbook(
        rows=rows,
        business_rows=len(rows),
        distinct_pmf=len({row.columns["pmf"] for row in rows}),
        distinct_provisional_predio_ids=len(
            {
                row.columns["id_predio_unico"]
                for row in rows
                if row.columns["id_predio_unico"] is not None
            }
        ),
        surface_total=math.fsum(
            row.columns["superficie_corta"]
            for row in rows
            if row.columns["superficie_corta"] is not None
        ),
        mapping_report=workbook.layout.to_dict(),
        warning_count=workbook.layout.count("warning"),
    )


def find_existing_import(
    connection: Connection, *, source_snapshot_id: int
) -> ImportProjectionResult | None:
    """Return the already-committed import for a content snapshot, if any.

    ``transelec_import`` is UNIQUE on ``source_snapshot_id`` and
    ``source_snapshot`` is content-addressed by SHA-256, so re-uploading
    byte-identical content resolves here rather than projecting twice.
    """

    row = connection.execute(
        text(
            """
            SELECT id, source_snapshot_id, ingestion_run_id, business_rows,
                   distinct_pmf, distinct_provisional_predio_ids, surface_total,
                   validated_at, mapping_report, warning_count
            FROM platform.transelec_import
            WHERE source_snapshot_id = :source_snapshot_id
            """
        ),
        {"source_snapshot_id": source_snapshot_id},
    ).one_or_none()

    if row is None:
        return None

    return ImportProjectionResult(
        import_id=row.id,
        source_snapshot_id=row.source_snapshot_id,
        ingestion_run_id=row.ingestion_run_id,
        business_rows=row.business_rows,
        distinct_pmf=row.distinct_pmf,
        distinct_provisional_predio_ids=row.distinct_provisional_predio_ids,
        surface_total=float(row.surface_total),
        validated_at=row.validated_at,
        already_existed=True,
        mapping_report=row.mapping_report,
        warning_count=row.warning_count,
    )


def _insert_import(
    connection: Connection,
    *,
    validated: ValidatedWorkbook,
    source_snapshot_id: int,
    ingestion_run_id: int,
    validated_by_app_user_id: int,
    validated_at: dt.datetime,
) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO platform.transelec_import (
                source_snapshot_id, ingestion_run_id, schema_contract_version,
                parser_version, business_rows, distinct_pmf,
                distinct_provisional_predio_ids, surface_total,
                validated_by_app_user_id, validated_at, mapping_report, warning_count
            )
            VALUES (
                :source_snapshot_id, :ingestion_run_id, :schema_contract_version,
                :parser_version, :business_rows, :distinct_pmf,
                :distinct_provisional_predio_ids, :surface_total,
                :validated_by_app_user_id, :validated_at,
                CAST(:mapping_report AS jsonb), :warning_count
            )
            RETURNING id
            """
        ),
        {
            "source_snapshot_id": source_snapshot_id,
            "ingestion_run_id": ingestion_run_id,
            "schema_contract_version": SCHEMA_CONTRACT_VERSION,
            "parser_version": PARSER_VERSION,
            "business_rows": validated.business_rows,
            "distinct_pmf": validated.distinct_pmf,
            "distinct_provisional_predio_ids": validated.distinct_provisional_predio_ids,
            "surface_total": validated.surface_total,
            "validated_by_app_user_id": validated_by_app_user_id,
            "validated_at": validated_at,
            "mapping_report": json.dumps(validated.mapping_report, ensure_ascii=False),
            "warning_count": validated.warning_count,
        },
    ).scalar_one()


def _insert_rows(connection: Connection, *, import_id: int, validated: ValidatedWorkbook) -> None:
    # The column list is interpolated from a module constant derived from the
    # source contract — never from caller input or workbook content. Every
    # value is a bound parameter.
    columns = ("import_id", "source_row_number", *_ROW_COLUMNS)
    placeholders = ", ".join(
        f"CAST(:{column} AS jsonb)" if column in _JSONB_COLUMNS else f":{column}"
        for column in columns
    )
    statement = text(
        f"INSERT INTO platform.transelec_resumen_row ({', '.join(columns)}) VALUES ({placeholders})"
    )

    connection.execute(
        statement,
        [
            {
                "import_id": import_id,
                "source_row_number": row.source_row_number,
                **row.columns,
            }
            for row in validated.rows
        ],
    )


@dataclass(frozen=True, slots=True)
class _PersistedAggregates:
    business_rows: int
    distinct_pmf: int
    distinct_provisional_predio_ids: int
    surface_total: float
    blank_predio_group_keys: int
    orphaned_rows: int


def read_persisted_aggregates(connection: Connection, *, import_id: int) -> _PersistedAggregates:
    """Recompute the import's aggregates from the rows actually persisted."""

    row = connection.execute(
        text(
            """
            SELECT
                count(*) AS business_rows,
                count(DISTINCT r.pmf) AS distinct_pmf,
                count(DISTINCT r.id_predio_unico) AS distinct_provisional_predio_ids,
                COALESCE(sum(r.superficie_corta), 0) AS surface_total,
                count(*) FILTER (
                    WHERE r.predio_group_key IS NULL OR btrim(r.predio_group_key) = ''
                ) AS blank_predio_group_keys,
                count(*) FILTER (WHERE i.id IS NULL) AS orphaned_rows
            FROM platform.transelec_resumen_row AS r
            LEFT JOIN platform.transelec_import AS i ON i.id = r.import_id
            WHERE r.import_id = :import_id
            """
        ),
        {"import_id": import_id},
    ).one()

    return _PersistedAggregates(
        business_rows=row.business_rows,
        distinct_pmf=row.distinct_pmf,
        distinct_provisional_predio_ids=row.distinct_provisional_predio_ids,
        surface_total=float(row.surface_total),
        blank_predio_group_keys=row.blank_predio_group_keys,
        orphaned_rows=row.orphaned_rows,
    )


def _verify_invariants(validated: ValidatedWorkbook, persisted: _PersistedAggregates) -> None:
    """Compare the persisted projection against the parsed source, structurally.

    Never compares against any snapshot-specific constant: both sides of
    every comparison are derived from the workbook being imported.
    """

    mismatches: list[str] = []

    if persisted.business_rows != validated.business_rows:
        mismatches.append(
            f"business_rows persisted={persisted.business_rows} expected={validated.business_rows}"
        )
    if persisted.distinct_pmf != validated.distinct_pmf:
        mismatches.append(
            f"distinct_pmf persisted={persisted.distinct_pmf} expected={validated.distinct_pmf}"
        )
    if persisted.distinct_provisional_predio_ids != validated.distinct_provisional_predio_ids:
        mismatches.append(
            "distinct_provisional_predio_ids "
            f"persisted={persisted.distinct_provisional_predio_ids} "
            f"expected={validated.distinct_provisional_predio_ids}"
        )
    if not math.isclose(
        persisted.surface_total,
        validated.surface_total,
        rel_tol=_SURFACE_TOTAL_RELATIVE_TOLERANCE,
        abs_tol=_SURFACE_TOTAL_RELATIVE_TOLERANCE,
    ):
        mismatches.append(
            f"surface_total persisted={persisted.surface_total} expected={validated.surface_total}"
        )
    if persisted.blank_predio_group_keys:
        mismatches.append(f"blank predio_group_key rows={persisted.blank_predio_group_keys}")
    if persisted.orphaned_rows:
        mismatches.append(f"orphaned resumen rows={persisted.orphaned_rows}")

    if mismatches:
        raise ImportInvariantError("; ".join(mismatches))


def validate_and_project(
    connection: Connection,
    *,
    workbook_path: str | Path,
    source_snapshot_id: int,
    ingestion_run_id: int,
    validated_by_app_user_id: int,
    validated_at: dt.datetime | None = None,
) -> ImportProjectionResult:
    """Validate a workbook and project its rows inside the caller's transaction.

    The caller owns the transaction boundary and must COMMIT on success. On
    any failure this raises, and the caller must roll back — leaving no
    ``transelec_import`` row, no ``transelec_resumen_row`` rows, and
    ``transelec_dashboard_state`` untouched.

    Activation is **not** part of this step. A committed result is a
    validated version that nothing serves yet; making it live is a separate,
    explicit publish mutation.
    """

    # Hard gate first, before any statement is issued: a contract violation
    # can then never leave a partial write behind, even in principle.
    validated = read_validated_workbook(workbook_path)

    existing = find_existing_import(connection, source_snapshot_id=source_snapshot_id)
    if existing is not None:
        return existing

    resolved_validated_at = validated_at or dt.datetime.now(dt.UTC)

    import_id = _insert_import(
        connection,
        validated=validated,
        source_snapshot_id=source_snapshot_id,
        ingestion_run_id=ingestion_run_id,
        validated_by_app_user_id=validated_by_app_user_id,
        validated_at=resolved_validated_at,
    )
    _insert_rows(connection, import_id=import_id, validated=validated)

    _verify_invariants(validated, read_persisted_aggregates(connection, import_id=import_id))

    return ImportProjectionResult(
        import_id=import_id,
        source_snapshot_id=source_snapshot_id,
        ingestion_run_id=ingestion_run_id,
        business_rows=validated.business_rows,
        distinct_pmf=validated.distinct_pmf,
        distinct_provisional_predio_ids=validated.distinct_provisional_predio_ids,
        surface_total=validated.surface_total,
        validated_at=resolved_validated_at,
        already_existed=False,
        mapping_report=validated.mapping_report,
        warning_count=validated.warning_count,
    )
