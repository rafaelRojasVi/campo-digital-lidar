"""Transelec HTTP adapter: upload, validate/project, publish, restore.

Route paths here are server-side paths (``/transelec/...``). Browsers reach
them at ``/api/transelec/...``: both the portal's dev proxy
(``apps/portal/vite.config.ts``) and the hosted static-site rewrite
(``render.yaml``) strip the ``/api`` prefix before forwarding, exactly as
they already do for ``/ingesta``. Mounting this router at ``/api`` would
therefore produce ``/api/api/transelec``.

This file is organized to grow: the shared pieces (product key, RBAC
dependency factory, response models, error copy) sit above a mutations
section, so a later slice adds read routes as a normal extension rather
than a rewrite.

Every mutation is session-authenticated, product-scoped RBAC-gated, and
CSRF-protected by the shared platform mechanism in ``app.csrf`` — the same
dependency the generic ``/ingesta/upload`` boundary uses, not a
Transelec-specific reimplementation.

Client-facing failures are deliberately generic and Spanish: a stakeholder
never sees a traceback, a file path, or row content. The technical detail
goes to the platform audit ledger and the process log only.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import logging
import tempfile
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import Row
from sqlalchemy.exc import StatementError

from app.access import Action, Role
from app.access_repository import AppUser
from app.audit import record_audit_event
from app.csrf import require_csrf
from app.database import get_database_engine
from app.deps import ensure_can, get_current_app_user, get_db_connection, get_object_store
from app.object_store import ObjectStore, ObjectStoreError
from app.routers.ingestion import UploadResponse
from app.routers.ingestion import upload as generic_upload
from app.transelec_publication import (
    TRANSELEC_PRODUCT_KEY,
    ActivationEventType,
    ImportNotFoundError,
    activate_import,
    read_active_import_id,
)
from transelec_ingestion.aef_view import (
    AefInputRow,
    PmfAefRecord,
    build_aef_summary,
    row_chronology_flags,
)
from transelec_ingestion.csv_export import render_transelec_export_csv
from transelec_ingestion.import_projection import (
    PARSER_VERSION,
    RESUMEN_ROW_PROJECTION,
    SCHEMA_CONTRACT_VERSION,
    ImportProjectionError,
    ImportProjectionResult,
    validate_and_project,
)
from transelec_ingestion.owner_status_view import OwnerStatusInputRow, build_owner_status
from transelec_ingestion.pending_view import PendingInputRow, build_pending
from transelec_ingestion.resumen_layout import AEF_TRACKING_FIELDS, PmfFieldValue
from transelec_ingestion.status_rollups import RolledRow, estado_resumido_first_row
from transelec_ingestion.summary_view import SummaryInputRow, build_summary
from transelec_ingestion.xlsx_contract import RESUMEN_COLUMNS, TranselecWorkbookError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transelec", tags=["transelec"])

_DOWNLOAD_CHUNK_BYTES = 1024 * 1024

# One planilla is a few MB to ~16 MB; the generic boundary's 2 GiB exists
# for LiDAR point clouds, not for spreadsheets. Enforced before the body is
# read by app.http_hardening.RequestBodyLimitMiddleware (see app.main).
TRANSELEC_MAX_UPLOAD_BYTES = 64 * 1024 * 1024

# Stakeholder-safe Spanish copy. Never interpolate exception text, file
# paths, or row content into any of these.
_RUN_NOT_FOUND = "No se encontró la carga solicitada."
_IMPORT_NOT_FOUND = "No se encontró la versión solicitada."
_SOURCE_UNAVAILABLE = "El archivo cargado ya no está disponible. Vuelva a cargarlo."
_CONTRACT_VIOLATION = "La planilla no cumple el contrato de origen esperado. Contacte a soporte."
_LAYOUT_NEEDS_REVIEW = (
    "La planilla necesita revisión antes de importarse. Revise las observaciones indicadas "
    "(filas y columnas). La versión activa no cambió."
)
_PROJECTION_FAILED = "No se pudo verificar la importación. La versión activa no cambió."
_PUBLISH_FAILED = "No se pudo publicar la versión. La versión activa no cambió."
_WARNINGS_NOT_ACKNOWLEDGED = (
    "Esta versión tiene advertencias de importación. Revíselas y confirme que desea publicarla. "
    "La versión activa no cambió."
)
_NO_ACTIVE_IMPORT = "No hay una versión publicada de Transelec."
_PMF_NOT_FOUND = "No se encontró el PMF solicitado en la versión activa."
_INVALID_CURSOR = "Cursor de paginación inválido."

# Exceptions whose str() is known to carry only structural information —
# header names, column positions, row numbers, counts, ids. Everything else
# is reduced to its type name. This is an allowlist on purpose: it must stay
# safe for exception types nobody has audited yet, not just the ones we
# expect today.
_STRUCTURAL_DETAIL_EXCEPTIONS = (
    TranselecWorkbookError,
    ImportProjectionError,
    ImportNotFoundError,
)


def _safe_failure_detail(exc: BaseException) -> str:
    """Reduce an exception to a detail safe for the audit ledger and the log.

    ``app.audit``'s contract is that callers never pass secrets or raw source
    content in ``metadata``. A SQLAlchemy ``StatementError`` violates that if
    passed through verbatim: its ``str()`` appends ``[SQL: ...]`` and
    ``[parameters: ...]``, and for this router those bound parameters are
    every projected column value of the failing rows — real Transelec
    content, written durably to the ledger and the process log.

    So only the audited, structural exception types keep their full message.
    A database error keeps its type and, when the driver exposes one, the
    violated constraint's name — enough to diagnose, nothing of the data.
    """

    if isinstance(exc, _STRUCTURAL_DETAIL_EXCEPTIONS):
        return f"{type(exc).__name__}: {exc}"

    if isinstance(exc, StatementError):
        diagnostic = getattr(getattr(exc, "orig", None), "diag", None)
        constraint = getattr(diagnostic, "constraint_name", None)
        if constraint:
            return f"{type(exc).__name__}: constraint {constraint}"
        return type(exc).__name__

    return type(exc).__name__


def require_transelec_grant(action: Action) -> Callable[..., Role]:
    """Build a dependency requiring a Transelec grant permitting ``action``.

    Mirrors the existing per-product RBAC pattern
    (``app.routers.lidar.require_lidar_view``) and reuses the same
    primitives — ``app.access.can`` via ``app.deps.ensure_can`` — rather
    than introducing a second authorization layer.
    """

    def dependency(
        user: Annotated[AppUser, Depends(get_current_app_user)],
        connection: Annotated[Connection, Depends(get_db_connection)],
    ) -> Role:
        return ensure_can(
            connection,
            app_user_id=user.id,
            product_key=TRANSELEC_PRODUCT_KEY,
            action=action,
        )

    return dependency


class ValidateAndProjectResponse(BaseModel):
    """Outcome of Step B. ``status`` never means "published".

    ``validated`` — this call created the import.
    ``already_imported`` — an import already existed for this content
    snapshot and is not the active version.
    ``already_current`` — an import already existed and is already active,
    so the upload was a no-op.
    """

    status: Literal["validated", "already_imported", "already_current"]
    import_id: int
    source_snapshot_id: int
    ingestion_run_id: int
    schema_contract_version: str
    parser_version: str
    business_rows: int
    distinct_pmf: int
    distinct_provisional_predio_ids: int
    surface_total: float
    validated_at: str
    is_active: bool
    # What the layout resolver matched, ignored and flagged. None only for an
    # import validated under contract V1, which kept no report.
    warning_count: int
    mapping_report: dict[str, Any] | None


class ActivationResponse(BaseModel):
    """Outcome of Step C (publish) or Step D (restore)."""

    status: Literal["published", "restored"]
    event_type: Literal["publish", "restore"]
    import_id: int
    previous_import_id: int | None
    publish_event_id: int
    occurred_at: str
    active_import_id: int


def _projection_response(
    result: ImportProjectionResult, *, active_import_id: int | None
) -> ValidateAndProjectResponse:
    is_active = active_import_id == result.import_id

    if not result.already_existed:
        status: Literal["validated", "already_imported", "already_current"] = "validated"
    elif is_active:
        status = "already_current"
    else:
        status = "already_imported"

    return ValidateAndProjectResponse(
        status=status,
        import_id=result.import_id,
        source_snapshot_id=result.source_snapshot_id,
        ingestion_run_id=result.ingestion_run_id,
        schema_contract_version=SCHEMA_CONTRACT_VERSION,
        parser_version=PARSER_VERSION,
        business_rows=result.business_rows,
        distinct_pmf=result.distinct_pmf,
        distinct_provisional_predio_ids=result.distinct_provisional_predio_ids,
        surface_total=result.surface_total,
        validated_at=result.validated_at.isoformat(),
        is_active=is_active,
        warning_count=result.warning_count,
        mapping_report=result.mapping_report,
    )


def _record_failure_audit(
    engine: Engine,
    *,
    actor_app_user_id: int,
    event_type: str,
    subject_kind: str,
    subject_id: str,
    metadata: dict[str, object],
) -> None:
    """Persist a failure audit event in its own transaction.

    The work transaction has already rolled back by the time this runs, so
    the evidence has to be written separately or it would roll back with it.
    Auditing must never turn a handled failure into an unhandled one, so a
    failure here is logged rather than raised.
    """

    try:
        with engine.begin() as audit_connection:
            record_audit_event(
                audit_connection,
                actor_app_user_id=actor_app_user_id,
                event_type=event_type,
                product_key=TRANSELEC_PRODUCT_KEY,
                subject_kind=subject_kind,
                subject_id=subject_id,
                metadata=metadata,
            )
    except Exception:  # noqa: BLE001 - auditing a failure must not mask it
        logger.exception("Could not record %s audit event for %s", event_type, subject_id)


# ---------------------------------------------------------------------------
# Mutations (OPERATOR/ADMIN, session-authenticated, CSRF-protected)
# ---------------------------------------------------------------------------


@router.post(
    "/uploads",
    response_model=UploadResponse,
    dependencies=[Depends(require_csrf)],
)
async def upload_transelec_workbook(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    file: Annotated[UploadFile, File()],
) -> UploadResponse:
    """Accept one Transelec workbook through the existing generic boundary.

    Delegates to the very handler ``POST /ingesta/upload`` runs — same
    bounded streaming intake, same evidence-only inspection, same
    content-addressed storage, same provenance and job rows — with
    ``product_key`` fixed rather than taken from the caller. The shared
    upload boundary is not modified for Transelec; Transelec-specific
    behavior begins at validate-and-project, below.

    Authorization is the generic boundary's own ``UPLOAD`` check against the
    Transelec grant, so no second RBAC gate is declared here.
    """

    return await generic_upload(
        user=user,
        connection=connection,
        store=store,
        product_key=TRANSELEC_PRODUCT_KEY,
        file=file,
    )


@router.post(
    "/imports/{ingestion_run_id}/validate-and-project",
    response_model=ValidateAndProjectResponse,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.PROCESS))],
)
def validate_and_project_import(
    ingestion_run_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> ValidateAndProjectResponse | JSONResponse:
    """Step B: layout resolution, row projection, invariant check.

    A blocking layout issue answers 422 with the full layout report (every
    matched/ignored column and every issue with row/column references) and
    persists nothing. Warnings do not block: the import is created with its
    report, and the operator reviews it before publishing.

    Commits its own transaction and activates nothing. A committed result is
    a validated version the dashboard does not yet serve; publishing it is a
    separate, explicit call.

    Idempotent per content snapshot: re-running this for a snapshot that
    already has an import returns that import instead of projecting again,
    and never activates it.
    """

    run = connection.execute(
        text(
            """
            SELECT r.id, r.product_key, r.source_snapshot_id, s.object_storage_key
            FROM platform.ingestion_run AS r
            JOIN platform.source_snapshot AS s ON s.id = r.source_snapshot_id
            WHERE r.id = :ingestion_run_id
            """
        ),
        {"ingestion_run_id": ingestion_run_id},
    ).one_or_none()

    # A run belonging to another product is reported as not-found, never as
    # forbidden: this endpoint must not confirm another product's run exists
    # to a caller granted only Transelec.
    if run is None or run.product_key != TRANSELEC_PRODUCT_KEY:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)

    if run.object_storage_key is None:
        raise HTTPException(status_code=409, detail=_SOURCE_UNAVAILABLE)

    temp_path = Path(tempfile.gettempdir()) / f"campo-transelec-{uuid.uuid4().hex}.xlsx"

    try:
        try:
            with store.open(run.object_storage_key) as source, temp_path.open("wb") as sink:
                while chunk := source.read(_DOWNLOAD_CHUNK_BYTES):
                    sink.write(chunk)
        except ObjectStoreError as exc:
            logger.warning(
                "Transelec source object unavailable for ingestion_run_id=%s: %s",
                ingestion_run_id,
                exc,
            )
            raise HTTPException(status_code=409, detail=_SOURCE_UNAVAILABLE) from exc

        try:
            # Step B's own transaction. It ends in COMMIT or ROLLBACK here
            # and nowhere else, and no activation is reachable inside it.
            with engine.begin() as step_b:
                result = validate_and_project(
                    step_b,
                    workbook_path=temp_path,
                    source_snapshot_id=run.source_snapshot_id,
                    ingestion_run_id=ingestion_run_id,
                    validated_by_app_user_id=user.id,
                )
                if not result.already_existed:
                    record_audit_event(
                        step_b,
                        actor_app_user_id=user.id,
                        event_type="import.validated",
                        product_key=TRANSELEC_PRODUCT_KEY,
                        subject_kind="transelec_import",
                        subject_id=str(result.import_id),
                        metadata={
                            "ingestion_run_id": ingestion_run_id,
                            "source_snapshot_id": run.source_snapshot_id,
                            "business_rows": result.business_rows,
                            "distinct_pmf": result.distinct_pmf,
                            "distinct_provisional_predio_ids": (
                                result.distinct_provisional_predio_ids
                            ),
                            "surface_total": result.surface_total,
                            "parser_version": PARSER_VERSION,
                            "warning_count": result.warning_count,
                            "warning_codes": sorted(
                                {
                                    issue["code"]
                                    for issue in (result.mapping_report or {}).get("issues", [])
                                    if issue["severity"] == "warning"
                                }
                            ),
                        },
                    )
        except Exception as exc:
            # Whatever failed, the Step B transaction rolled back: no
            # transelec_import row, no transelec_resumen_row rows, and
            # transelec_dashboard_state untouched.
            is_contract_violation = isinstance(exc, TranselecWorkbookError)
            layout_report = exc.report if isinstance(exc, TranselecWorkbookError) else None
            detail = _safe_failure_detail(exc)
            logger.warning(
                "Transelec validate-and-project failed for ingestion_run_id=%s: %s",
                ingestion_run_id,
                detail,
            )
            _record_failure_audit(
                engine,
                actor_app_user_id=user.id,
                event_type="import.validation.failed",
                subject_kind="ingestion_run",
                subject_id=str(ingestion_run_id),
                metadata={
                    "source_snapshot_id": run.source_snapshot_id,
                    "reason": "contract_violation" if is_contract_violation else "projection_error",
                    "detail": detail,
                    "parser_version": PARSER_VERSION,
                },
            )
            if layout_report is not None:
                # The operator needs every row/column reference to fix the
                # workbook, not only the first. The report is structural by
                # construction (headers, letters, row numbers, counts) and
                # never quotes a business cell value.
                return JSONResponse(
                    status_code=422,
                    content={"detail": _LAYOUT_NEEDS_REVIEW, "report": layout_report.to_dict()},
                )
            raise HTTPException(
                status_code=422 if is_contract_violation else 500,
                detail=_CONTRACT_VIOLATION if is_contract_violation else _PROJECTION_FAILED,
            ) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    return _projection_response(result, active_import_id=read_active_import_id(connection))


def _activate(
    import_id: int,
    *,
    user: AppUser,
    engine: Engine,
    event_type: ActivationEventType,
    audit_event_type: str,
    extra_audit_metadata: dict[str, object] | None = None,
) -> ActivationResponse:
    """Run Step C/D: one short transaction that atomically flips the active version."""

    try:
        with engine.begin() as activation:
            result = activate_import(
                activation,
                import_id=import_id,
                actor_user_id=user.id,
                event_type=event_type,
            )
            record_audit_event(
                activation,
                actor_app_user_id=user.id,
                event_type=audit_event_type,
                product_key=TRANSELEC_PRODUCT_KEY,
                subject_kind="transelec_import",
                subject_id=str(import_id),
                metadata={
                    "event_type": event_type,
                    "previous_import_id": result.previous_import_id,
                    "publish_event_id": result.publish_event_id,
                    **(extra_audit_metadata or {}),
                },
            )
    except Exception as exc:
        not_found = isinstance(exc, ImportNotFoundError)
        detail = _safe_failure_detail(exc)
        logger.warning("Transelec %s failed for import_id=%s: %s", event_type, import_id, detail)
        _record_failure_audit(
            engine,
            actor_app_user_id=user.id,
            event_type="import.publish.failed",
            subject_kind="transelec_import",
            subject_id=str(import_id),
            metadata={
                "event_type": event_type,
                "reason": "import_not_found" if not_found else "activation_error",
                "detail": detail,
            },
        )
        raise HTTPException(
            status_code=404 if not_found else 500,
            detail=_IMPORT_NOT_FOUND if not_found else _PUBLISH_FAILED,
        ) from exc

    return ActivationResponse(
        status="published" if event_type == "publish" else "restored",
        event_type=event_type,
        import_id=result.import_id,
        previous_import_id=result.previous_import_id,
        publish_event_id=result.publish_event_id,
        occurred_at=result.occurred_at.isoformat(),
        active_import_id=result.import_id,
    )


@router.post(
    "/imports/{import_id}/publish",
    response_model=ActivationResponse,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.PUBLISH))],
)
def publish_import(
    import_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    engine: Annotated[Engine, Depends(get_database_engine)],
    acknowledge_warnings: Annotated[bool, Query()] = False,
) -> ActivationResponse:
    """Step C: make an already-validated import the version the dashboard serves.

    Never automatic. A successful validate-and-project does not reach this
    code path; an operator has to call it deliberately.

    An import validated with warnings is published only when the caller
    states it reviewed them (``acknowledge_warnings=true``); otherwise 409.
    The dashboard's acknowledgement checkbox is a convenience, this is the
    control. An unknown import falls through to the activation's own 404.
    """

    warning_count = connection.execute(
        text("SELECT warning_count FROM platform.transelec_import WHERE id = :import_id"),
        {"import_id": import_id},
    ).scalar_one_or_none()

    if warning_count and not acknowledge_warnings:
        raise HTTPException(status_code=409, detail=_WARNINGS_NOT_ACKNOWLEDGED)

    return _activate(
        import_id,
        user=user,
        engine=engine,
        event_type="publish",
        audit_event_type="import.published",
        extra_audit_metadata={
            "warning_count": warning_count or 0,
            "warnings_acknowledged": bool(warning_count) and acknowledge_warnings,
        },
    )


@router.post(
    "/imports/{import_id}/restore",
    response_model=ActivationResponse,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.PUBLISH))],
)
def restore_import(
    import_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> ActivationResponse:
    """Step D: re-activate a previously validated import.

    The same activation primitive as publish, recorded as
    ``event_type='restore'`` so the trail distinguishes "published a new
    version" from "reverted to an old one". No re-validation happens, and
    none is possible to need: Step B never commits an invalid import.
    """

    return _activate(
        import_id,
        user=user,
        engine=engine,
        event_type="restore",
        audit_event_type="import.restored",
    )


# ---------------------------------------------------------------------------
# Reads (VIEWER and above)
#
# Every route below requires only Action.VIEW (granted to VIEWER/OPERATOR/
# ADMIN alike) and none carries app.csrf.require_csrf — GET routes never
# need it (Task 3's own reminder, apps/api/app/routers/transelec.py history).
# All read the active import's transelec_resumen_row projection; none
# invents a canonical PMF/predio status rollup — every status-dependent
# number is computed via one of the three explicitly named, evidenced legacy
# bases in transelec_ingestion.status_rollups (estado_resumido_first_row,
# pending_priority_legacy, owner_stage_legacy). TR-OPEN-01 stays open.
# ---------------------------------------------------------------------------

# The full contract field list, checked against resumen_layout.FIELD_SPECS at
# import time (see import_projection.py) — reused here, never re-declared, so
# a future contract change cannot make the filter/search/export field lists
# silently drift from the schema.
_CONTRACT_FIELDS: tuple[str, ...] = tuple(spec.column for spec in RESUMEN_ROW_PROJECTION)

# Every persisted transelec_resumen_row column this router selects for a
# "full row" read (list/detail/pending/export). Order matches the contract.
_RESUMEN_ROW_COLUMNS: tuple[str, ...] = (
    "source_row_number",
    *_CONTRACT_FIELDS,
    "predio_group_key",
    "source_text_dates",
)

# TR-FUNC-017-022: the 5 AND'd multi-selects, OR'd within each.
_MULTISELECT_FIELDS: tuple[str, ...] = (
    "estado_resumido",
    "empresa",
    "pas",
    "sector",
    "tipo_propietario",
    # Contract V2's AEF tracking block. Same semantics as the five above:
    # OR within one field's values, AND across fields; a row with a blank
    # value never matches a selected value.
    "aef",
    "quien_solicita",
)


class TranselecFilters(BaseModel):
    """The one filter contract shared by every read route (TR-FUNC-017-022).

    AND across the 5 multi-selects; OR within one multi-select's repeated
    values; ``q`` is a case-insensitive substring match OR'd across all 30
    contract fields, AND'd with the multi-selects — confirmed identical in
    both source HTML files.
    """

    estado_resumido: list[str] = Field(default_factory=list)
    empresa: list[str] = Field(default_factory=list)
    pas: list[str] = Field(default_factory=list)
    sector: list[str] = Field(default_factory=list)
    tipo_propietario: list[str] = Field(default_factory=list)
    aef: list[str] = Field(default_factory=list)
    quien_solicita: list[str] = Field(default_factory=list)
    q: str | None = None


def _transelec_filters(
    estado_resumido: Annotated[list[str] | None, Query()] = None,
    empresa: Annotated[list[str] | None, Query()] = None,
    pas: Annotated[list[str] | None, Query()] = None,
    sector: Annotated[list[str] | None, Query()] = None,
    tipo_propietario: Annotated[list[str] | None, Query()] = None,
    aef: Annotated[list[str] | None, Query()] = None,
    quien_solicita: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> TranselecFilters:
    # `None`, not `[]`, as the literal parameter default: an empty list is
    # mutable, and even though it is never mutated here, a `None` default
    # avoids relying on that discipline holding forever.
    return TranselecFilters(
        estado_resumido=estado_resumido or [],
        empresa=empresa or [],
        pas=pas or [],
        sector=sector or [],
        tipo_propietario=tipo_propietario or [],
        aef=aef or [],
        quien_solicita=quien_solicita or [],
        q=q,
    )


def _escape_like(value: str) -> str:
    """Escape LIKE/ILIKE metacharacters so a literal ``%``/``_`` in ``q``
    stays a literal substring match rather than an unintended wildcard."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_filter_where(filters: TranselecFilters) -> tuple[str, dict[str, Any]]:
    """Return a SQL fragment (starting with ``" AND "``, or empty) and its
    bound parameters implementing the shared filter contract above.

    Field names are drawn only from the fixed allow-lists above — never from
    caller input — so interpolating them into the SQL text carries no
    injection risk; every value is still a bound parameter.
    """

    clauses: list[str] = []
    params: dict[str, Any] = {}

    for field_name in _MULTISELECT_FIELDS:
        values = getattr(filters, field_name)
        if values:
            param_name = f"filter_{field_name}"
            clauses.append(f"{field_name} = ANY(:{param_name})")
            params[param_name] = values

    if filters.q:
        or_clauses = " OR ".join(
            f"{column}::text ILIKE :q ESCAPE '\\'" for column in _CONTRACT_FIELDS
        )
        clauses.append(f"({or_clauses})")
        params["q"] = f"%{_escape_like(filters.q)}%"

    where_sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params


def _require_active_import_id(connection: Connection) -> int:
    active_import_id = read_active_import_id(connection)
    if active_import_id is None:
        raise HTTPException(status_code=404, detail=_NO_ACTIVE_IMPORT)
    return active_import_id


def _read_latest_publish_event(connection: Connection, *, import_id: int) -> Row[Any]:
    """The most recent ``transelec_publish_event`` row for ``import_id``.

    Every activation (Step C/D) always inserts exactly one such row in the
    same transaction that sets ``active_import_id``
    (``app.transelec_publication.activate_import``) — so if an import is
    active, at least one publish_event for it must exist.

    Shared by ``/imports/active`` and ``/report`` so "when is this data
    from" has exactly one source of truth, never two independently
    computed dates.
    """

    return connection.execute(
        text(
            """
            SELECT pe.event_type, pe.occurred_at, pe.actor_user_id, u.display_name
            FROM platform.transelec_publish_event AS pe
            JOIN platform.app_user AS u ON u.id = pe.actor_user_id
            WHERE pe.import_id = :import_id
            ORDER BY pe.occurred_at DESC, pe.id DESC
            LIMIT 1
            """
        ),
        {"import_id": import_id},
    ).one()


def _fetch_filtered_rows(
    connection: Connection, *, import_id: int, filters: TranselecFilters
) -> Sequence[Row[Any]]:
    """Fetch every filtered row for ``import_id``, in ``source_row_number``
    order (required for the first-row-wins dedup every status basis uses).

    One query feeds the KPIs, both charts, the status hero, the reforestación
    chips, the quality indicators, the pending section, and the owner-status
    table for a given filter state — the server-side equivalent of both
    source HTML files' single shared in-memory ``view``, which is exactly
    what TR-FUNC-017's filter-consistency acceptance test requires.
    """

    where_sql, params = _build_filter_where(filters)
    params["import_id"] = import_id

    statement = text(
        f"""
        SELECT {", ".join(_RESUMEN_ROW_COLUMNS)}
        FROM platform.transelec_resumen_row
        WHERE import_id = :import_id{where_sql}
        ORDER BY source_row_number ASC
        """
    )
    return connection.execute(statement, params).all()


def _to_rolled_row(row: Row[Any]) -> RolledRow:
    return RolledRow(
        source_row_number=row.source_row_number,
        pmf=row.pmf,
        predio_group_key=row.predio_group_key,
        estado=row.estado,
        estado_resumido=row.estado_resumido,
        numero_ingreso=row.numero_ingreso,
        tipo_propietario=row.tipo_propietario,
    )


def _to_summary_input_row(row: Row[Any]) -> SummaryInputRow:
    return SummaryInputRow(
        source_row_number=row.source_row_number,
        pmf=row.pmf,
        predio_group_key=row.predio_group_key,
        estado=row.estado,
        estado_resumido=row.estado_resumido,
        numero_ingreso=row.numero_ingreso,
        tipo_propietario=row.tipo_propietario,
        predio_ref=row.predio_ref,
        id_predio_unico=row.id_predio_unico,
        superficie_corta=row.superficie_corta,
        rol=row.rol,
        empresa=row.empresa,
        rol_ref=row.rol_ref,
    )


class SourceTextDateView(BaseModel):
    """Raw text found in a date column (see resumen_layout.TextDateEvidence)."""

    raw: str
    resolution: Literal["parsed_spanish_long", "multiple_dates", "placeholder", "unrecognized"]
    parsed: str | None


class ResumenRowView(BaseModel):
    """One full ``transelec_resumen_row`` — every contract field (the 30 V1
    fields plus the five V2 AEF tracking fields), the derived
    ``predio_group_key``, the 1-indexed ``source_row_number``, and the
    row's AEF date-order inconsistencies (``chronology_flags``, reported
    as found and never corrected), and ``source_text_dates``: for each date
    field whose cell held text, that raw text and how it was classified.
    A date field is NULL unless the cell was an Excel date or a single
    unambiguous written-out Spanish date; the raw text is never dropped.

    Deliberately not trimmed to any particular HTML table's column subset:
    neither ratified document enumerates the exact 11/12/7/9-column sets the
    source HTML tables show, so the API exposes every field and leaves
    column selection to the frontend (Slice 5) — a display concern, not a
    data-shape one.
    """

    source_row_number: int
    pmf: str
    predio_ref: str | None
    rol_ref: str | None
    area_ref: str | None
    carpeta_source: str | None
    carpeta_normalizada: str | None
    pas: str | None
    estado: str | None
    estado_resumido: str | None
    tipo_rechazo: str | None
    reingreso_tec: str | None
    reingreso_legal: str | None
    reingreso_recrep: str | None
    tipo_propietario: str | None
    id_transelec: str | None
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    superficie_corta: float | None
    superficie_total_corta: float | None
    fecha_ingreso: str | None
    numero_ingreso: str | None
    fecha_90_dias: str | None
    hoy_raw: str | None
    empresa: str | None
    id_predio_unico_ii: str | None
    id_pmf: str | None
    id_predio_unico: str | None
    predio_group_key: str
    tramite: str | None
    sector: str | None
    aef: str | None
    quien_solicita: str | None
    fecha_solicitud: str | None
    fecha_corta: str | None
    fecha_termino: str | None
    chronology_flags: list[str]
    source_text_dates: dict[str, SourceTextDateView] = Field(default_factory=dict)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _to_aef_input_row(row: Row[Any]) -> AefInputRow:
    return AefInputRow(
        source_row_number=row.source_row_number,
        pmf=row.pmf,
        aef=row.aef,
        quien_solicita=row.quien_solicita,
        fecha_solicitud=row.fecha_solicitud,
        fecha_corta=row.fecha_corta,
        fecha_termino=row.fecha_termino,
        text_dates=row.source_text_dates or {},
    )


def _resumen_row_view(row: Row[Any]) -> ResumenRowView:
    return ResumenRowView(
        source_row_number=row.source_row_number,
        pmf=row.pmf,
        predio_ref=row.predio_ref,
        rol_ref=row.rol_ref,
        area_ref=row.area_ref,
        carpeta_source=row.carpeta_source,
        carpeta_normalizada=row.carpeta_normalizada,
        pas=row.pas,
        estado=row.estado,
        estado_resumido=row.estado_resumido,
        tipo_rechazo=row.tipo_rechazo,
        reingreso_tec=row.reingreso_tec,
        reingreso_legal=row.reingreso_legal,
        reingreso_recrep=row.reingreso_recrep,
        tipo_propietario=row.tipo_propietario,
        id_transelec=row.id_transelec,
        rol=row.rol,
        numero_predio=row.numero_predio,
        numero_area_corta=row.numero_area_corta,
        superficie_corta=row.superficie_corta,
        superficie_total_corta=row.superficie_total_corta,
        fecha_ingreso=row.fecha_ingreso.isoformat() if row.fecha_ingreso else None,
        numero_ingreso=row.numero_ingreso,
        fecha_90_dias=row.fecha_90_dias.isoformat() if row.fecha_90_dias else None,
        hoy_raw=row.hoy_raw,
        empresa=row.empresa,
        id_predio_unico_ii=row.id_predio_unico_ii,
        id_pmf=row.id_pmf,
        id_predio_unico=row.id_predio_unico,
        predio_group_key=row.predio_group_key,
        tramite=row.tramite,
        sector=row.sector,
        aef=row.aef,
        quien_solicita=row.quien_solicita,
        fecha_solicitud=_iso(row.fecha_solicitud),
        fecha_corta=_iso(row.fecha_corta),
        fecha_termino=_iso(row.fecha_termino),
        chronology_flags=list(row_chronology_flags(_to_aef_input_row(row))),
        source_text_dates={
            name: SourceTextDateView(**evidence)
            for name, evidence in (row.source_text_dates or {}).items()
        },
    )


# ---------------------------------------------------------------------------
# GET /summary — TR-FUNC-001-012, 014-016
# ---------------------------------------------------------------------------


class Bucket3WayCountsView(BaseModel):
    aprobado: int
    en_tramite: int
    pendiente_o_tachado: int


class HeroStateCountsView(BaseModel):
    aprobado: int
    en_tramite: int
    pendiente: int
    tachado: int
    sin_estado: int


class LabelledCountView(BaseModel):
    """One state of a breakdown, under the raw spelling the source used."""

    label: str | None
    normalized: str | None
    count: int


class EmpresaBreakdownView(BaseModel):
    empresa: str | None
    pmf_count: int
    estado_resumido: HeroStateCountsView


class EstadoResumidoConflictView(BaseModel):
    """One PMF the source gives more than one ``Estado resumido``.

    Exposed so the conflict is visible rather than reproduced: the headline
    counts this PMF once, under ``canonico``, and this record names every
    value the source actually carried and the row the canonical one came
    from.
    """

    pmf: str
    valores: list[str | None]
    canonico: str | None
    estado_detalle: str | None
    source_row_number: int


class ReforestacionView(BaseModel):
    """Reforestation reference counts, with their definition attached.

    ``propietarios`` is a literal, not a number. The source contract has no
    owner field — ``Tipo de propietario`` is a tenure category, and the
    surnames inside ``Predio Ref`` are free text — so no owner count is
    computed or returned anywhere.
    """

    definicion: str
    predio_ref_labels: list[str]
    predio_ref_count: int
    rol_ref_count: int
    sentinel_label: str
    sentinel_row_count: int
    etiquetas_compuestas: list[str]
    propietarios: str


class TranselecSummaryResponse(BaseModel):
    import_id: int
    row_count: int
    pmf_count: int
    predio_count: int
    rol_count: int
    surface_total: float
    basis_estado_resumido: Literal["estado_resumido_first_row"]
    aprobados_pmf_count: int
    en_tramite_pmf_count: int
    basis_pending_priority: Literal["pending_priority_legacy"]
    pendientes_prioritarios_pmf_count: int
    con_servidumbre_predio_count: int
    avance_por_predio: Bucket3WayCountsView
    avance_por_pmf: Bucket3WayCountsView
    estado_resumido_hero_predio: HeroStateCountsView
    estado_resumido_pmf: HeroStateCountsView
    estado_detalle_pmf: list[LabelledCountView]
    estado_resumido_valores: dict[str, list[str]]
    por_empresa: list[EmpresaBreakdownView]
    reforestacion: ReforestacionView
    predios_reforestacion: list[str]
    calidad_filas_sin_id_predial_unico: int
    calidad_pmf_sin_numero_ingreso: int
    calidad_numero_resolucion: str
    calidad_pmf_estado_resumido_conflictivo: list[EstadoResumidoConflictView]


@router.get(
    "/summary",
    response_model=TranselecSummaryResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_summary(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
) -> TranselecSummaryResponse:
    """TR-FUNC-001-012, 014-016: KPIs, both donut charts, the status hero,
    the reforestación chips, and the data-quality indicators — all from one
    filtered row set, so they can never disagree under a given filter state.
    """

    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)
    summary = build_summary([_to_summary_input_row(row) for row in rows])

    return TranselecSummaryResponse(
        import_id=import_id,
        row_count=summary.row_count,
        pmf_count=summary.pmf_count,
        predio_count=summary.predio_count,
        rol_count=summary.rol_count,
        surface_total=summary.surface_total,
        basis_estado_resumido=summary.basis_estado_resumido,  # type: ignore[arg-type]
        aprobados_pmf_count=summary.aprobados_pmf_count,
        en_tramite_pmf_count=summary.en_tramite_pmf_count,
        basis_pending_priority=summary.basis_pending_priority,  # type: ignore[arg-type]
        pendientes_prioritarios_pmf_count=summary.pendientes_prioritarios_pmf_count,
        con_servidumbre_predio_count=summary.con_servidumbre_predio_count,
        avance_por_predio=Bucket3WayCountsView(**asdict(summary.avance_por_predio)),
        avance_por_pmf=Bucket3WayCountsView(**asdict(summary.avance_por_pmf)),
        estado_resumido_hero_predio=HeroStateCountsView(
            **asdict(summary.estado_resumido_hero_predio)
        ),
        estado_resumido_pmf=HeroStateCountsView(**asdict(summary.estado_resumido_pmf)),
        estado_detalle_pmf=[
            LabelledCountView(**asdict(item)) for item in summary.estado_detalle_pmf
        ],
        estado_resumido_valores=summary.estado_resumido_valores,
        por_empresa=[
            EmpresaBreakdownView(
                empresa=item.empresa,
                pmf_count=item.pmf_count,
                estado_resumido=HeroStateCountsView(**asdict(item.estado_resumido)),
            )
            for item in summary.por_empresa
        ],
        reforestacion=ReforestacionView(**asdict(summary.reforestacion)),
        predios_reforestacion=summary.predios_reforestacion,
        calidad_filas_sin_id_predial_unico=summary.calidad_filas_sin_id_predial_unico,
        calidad_pmf_sin_numero_ingreso=summary.calidad_pmf_sin_numero_ingreso,
        calidad_numero_resolucion=summary.calidad_numero_resolucion,
        calidad_pmf_estado_resumido_conflictivo=[
            EstadoResumidoConflictView(**asdict(item))
            for item in summary.calidad_pmf_estado_resumido_conflictivo
        ],
    )


# ---------------------------------------------------------------------------
# GET /pmfs, GET /pmfs/{pmf} — TR-FUNC-039
# ---------------------------------------------------------------------------

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class TranselecRowsPage(BaseModel):
    items: list[ResumenRowView]
    next_cursor: str | None
    has_more: bool
    total_count: int


def _encode_cursor(source_row_number: int) -> str:
    return base64.urlsafe_b64encode(str(source_row_number).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str) -> int:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
        return int(decoded)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail=_INVALID_CURSOR) from exc


@router.get(
    "/pmfs",
    response_model=TranselecRowsPage,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def list_pmf_rows(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = _DEFAULT_PAGE_SIZE,
) -> TranselecRowsPage:
    """TR-FUNC-039: the row-grain main table, real cursor pagination.

    No hidden cap: ``total_count`` always reflects every matching row under
    the current filter, and a caller can page through all of them via
    ``next_cursor`` — there is no Actualizable-style silent ``slice(0,1000)``
    cliff here.
    """

    import_id = _require_active_import_id(connection)
    where_sql, params = _build_filter_where(filters)
    params["import_id"] = import_id

    total_count = connection.execute(
        text(
            f"SELECT count(*) FROM platform.transelec_resumen_row "
            f"WHERE import_id = :import_id{where_sql}"
        ),
        params,
    ).scalar_one()

    if cursor is not None:
        params["cursor_row_number"] = _decode_cursor(cursor)
        cursor_clause = " AND source_row_number > :cursor_row_number"
    else:
        cursor_clause = ""

    params["fetch_limit"] = limit + 1
    statement = text(
        f"""
        SELECT {", ".join(_RESUMEN_ROW_COLUMNS)}
        FROM platform.transelec_resumen_row
        WHERE import_id = :import_id{where_sql}{cursor_clause}
        ORDER BY source_row_number ASC
        LIMIT :fetch_limit
        """
    )
    fetched = connection.execute(statement, params).all()

    has_more = len(fetched) > limit
    page_rows = fetched[:limit]
    next_cursor = _encode_cursor(page_rows[-1].source_row_number) if has_more else None

    return TranselecRowsPage(
        items=[_resumen_row_view(row) for row in page_rows],
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )


class TranselecPmfDetailResponse(BaseModel):
    pmf: str
    row_count: int
    basis_estado_resumido: Literal["estado_resumido_first_row"]
    estado_resumido: str | None
    rows: list[ResumenRowView]


@router.get(
    "/pmfs/{pmf}",
    response_model=TranselecPmfDetailResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_pmf_detail(
    pmf: str,
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> TranselecPmfDetailResponse:
    """TR-FUNC-039's detail drawer: every row for one PMF in the active
    import, regardless of the list's current filter state (opening a detail
    drawer for a specific PMF is not itself a filtered view)."""

    import_id = _require_active_import_id(connection)
    statement = text(
        f"""
        SELECT {", ".join(_RESUMEN_ROW_COLUMNS)}
        FROM platform.transelec_resumen_row
        WHERE import_id = :import_id AND pmf = :pmf
        ORDER BY source_row_number ASC
        """
    )
    rows = connection.execute(statement, {"import_id": import_id, "pmf": pmf}).all()

    if not rows:
        raise HTTPException(status_code=404, detail=_PMF_NOT_FOUND)

    status = estado_resumido_first_row([_to_rolled_row(row) for row in rows], key="pmf").get(pmf)

    return TranselecPmfDetailResponse(
        pmf=pmf,
        row_count=len(rows),
        basis_estado_resumido="estado_resumido_first_row",
        estado_resumido=status,
        rows=[_resumen_row_view(row) for row in rows],
    )


# ---------------------------------------------------------------------------
# GET /aef — contract V2's AEF tracking block, per PMF with its source rows
# ---------------------------------------------------------------------------


class LabelCountView(BaseModel):
    label: str | None
    count: int


class AefValueVariantView(BaseModel):
    value: str
    source_rows: list[int]


class AefPmfFieldView(BaseModel):
    """One tracking field resolved for a PMF.

    ``status`` "value": every non-blank row agrees, ``value`` came from
    ``source_rows``. "blank": no row has a value. "conflict": rows disagree;
    ``value`` is None and ``variants`` lists each value with its rows.
    ``value_kind`` "raw_text" marks text from a date column that was not
    resolved to a date and is shown as written.
    """

    status: Literal["value", "blank", "conflict"]
    value: str | None
    value_kind: Literal["text", "date", "raw_text"] | None
    source_rows: list[int]
    variants: list[AefValueVariantView]


class AefPmfView(BaseModel):
    pmf: str
    total_rows: int
    rows_with_any_tracking: int
    rows_with_aef: int
    source_row_numbers: list[int]
    has_conflict: bool
    chronology_flags: list[str]
    fields: dict[str, AefPmfFieldView]


class TranselecAefResponse(BaseModel):
    """AEF tracking for the filtered scope of the active version.

    ``basis`` "pmf_from_source_rows": each field is resolved per PMF from
    the rows that carry it, naming those rows; rows are never rewritten and
    a conflict is reported, not decided. PMF shown are those with a row in
    the filtered scope; their values consider all of the PMF's rows in the
    version. The ``rows_*`` counts and ``rows`` are row-level, over the
    filtered scope.

    ``source_fields`` lists which of the five tracking columns the published
    workbook actually had, so "the column did not exist" (an older layout)
    is distinguishable from "the column exists and these rows are blank".
    """

    basis: Literal["pmf_from_source_rows"]
    source_fields: list[str]
    row_count: int
    pmf_count: int
    rows_with_any_tracking: int
    rows_with_aef: int
    rows_with_quien_solicita: int
    rows_with_fecha_solicitud: int
    rows_with_fecha_corta: int
    rows_with_fecha_termino: int
    rows_with_chronology_warning: int
    pmf_with_tracking: int
    pmf_with_aef: int
    pmf_with_conflict: int
    pmf_conflicts_by_field: dict[str, int]
    pmf_with_chronology_warning: int
    por_aef: list[LabelCountView]
    por_solicitante: list[LabelCountView]
    pmf_por_aef: list[LabelCountView]
    pmf_por_solicitante: list[LabelCountView]
    pmfs: list[AefPmfView]
    rows: list[ResumenRowView]


def _aef_value_text(value: Any) -> str:
    return value.isoformat() if isinstance(value, dt.date) else str(value)


def _aef_field_view(name: str, resolved: PmfFieldValue) -> AefPmfFieldView:
    value_kind: Literal["text", "date", "raw_text"] | None = None
    if resolved.status == "value":
        if isinstance(resolved.value, dt.date):
            value_kind = "date"
        elif name.startswith("fecha_"):
            value_kind = "raw_text"
        else:
            value_kind = "text"
    return AefPmfFieldView(
        status=resolved.status,
        value=_aef_value_text(resolved.value) if resolved.status == "value" else None,
        value_kind=value_kind,
        source_rows=list(resolved.source_rows),
        variants=[
            AefValueVariantView(
                value=_aef_value_text(variant.value), source_rows=list(variant.source_rows)
            )
            for variant in resolved.variants
        ],
    )


def _aef_pmf_view(record: PmfAefRecord) -> AefPmfView:
    return AefPmfView(
        pmf=record.pmf,
        total_rows=record.total_rows,
        rows_with_any_tracking=record.rows_with_any_tracking,
        rows_with_aef=record.rows_with_aef,
        source_row_numbers=list(record.source_row_numbers),
        has_conflict=record.has_conflict,
        chronology_flags=list(record.chronology_flags),
        fields={name: _aef_field_view(name, record.fields[name]) for name in AEF_TRACKING_FIELDS},
    )


def _label_views(entries: Any) -> list[LabelCountView]:
    return [LabelCountView(label=entry.label, count=entry.count) for entry in entries]


@router.get(
    "/aef",
    response_model=TranselecAefResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_aef(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
) -> TranselecAefResponse:
    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)
    # PMF-level values use every row of each PMF in scope, not only the rows
    # the filter kept: a PMF's AEF must not change with an unrelated filter.
    pmf_rows = (
        _fetch_filtered_rows(connection, import_id=import_id, filters=TranselecFilters())
        if filters != TranselecFilters()
        else rows
    )
    summary = build_aef_summary(
        [_to_aef_input_row(row) for row in rows],
        pmf_rows=[_to_aef_input_row(row) for row in pmf_rows],
    )

    imp = connection.execute(
        text(
            """
            SELECT schema_contract_version, mapping_report
            FROM platform.transelec_import WHERE id = :import_id
            """
        ),
        {"import_id": import_id},
    ).one()
    present = set(_source_fields(imp.schema_contract_version, imp.mapping_report))

    tracked = set(summary.tracked_row_numbers)
    return TranselecAefResponse(
        basis="pmf_from_source_rows",
        source_fields=[name for name in AEF_TRACKING_FIELDS if name in present],
        row_count=summary.row_count,
        pmf_count=summary.pmf_count,
        rows_with_any_tracking=summary.rows_with_any_tracking,
        rows_with_aef=summary.rows_with_aef,
        rows_with_quien_solicita=summary.rows_with_quien_solicita,
        rows_with_fecha_solicitud=summary.rows_with_fecha_solicitud,
        rows_with_fecha_corta=summary.rows_with_fecha_corta,
        rows_with_fecha_termino=summary.rows_with_fecha_termino,
        rows_with_chronology_warning=summary.rows_with_chronology_warning,
        pmf_with_tracking=summary.pmf_with_tracking,
        pmf_with_aef=summary.pmf_with_aef,
        pmf_with_conflict=summary.pmf_with_conflict,
        pmf_conflicts_by_field=summary.pmf_conflicts_by_field,
        pmf_with_chronology_warning=summary.pmf_with_chronology_warning,
        por_aef=_label_views(summary.por_aef),
        por_solicitante=_label_views(summary.por_solicitante),
        pmf_por_aef=_label_views(summary.pmf_por_aef),
        pmf_por_solicitante=_label_views(summary.pmf_por_solicitante),
        pmfs=[_aef_pmf_view(record) for record in summary.pmfs],
        rows=[_resumen_row_view(row) for row in rows if row.source_row_number in tracked],
    )


# ---------------------------------------------------------------------------
# GET /pending — TR-FUNC-007, 032, 033
# ---------------------------------------------------------------------------


class PendingStageCountsView(BaseModel):
    preparacion: int
    recurso_rechazo: int
    otros: int


class PendingPmfRowView(ResumenRowView):
    pending_stage: Literal["preparacion", "recurso_rechazo", "otros"]


class TranselecPendingResponse(BaseModel):
    basis: Literal["pending_priority_legacy"]
    pending_pmf_count: int
    total_pmf_count: int
    pending_pmf_percentage: float
    stage_basis: Literal["pending_stage_legacy"]
    stages: PendingStageCountsView
    rows: list[PendingPmfRowView]


@router.get(
    "/pending",
    response_model=TranselecPendingResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_pending(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
) -> TranselecPendingResponse:
    """TR-FUNC-007 (count), 032 (stage breakdown + percentage), 033 (detail
    table) — one PMF-deduped row per pending-priority PMF."""

    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)
    rows_by_number = {row.source_row_number: row for row in rows}

    pending_inputs = [
        PendingInputRow(
            source_row_number=row.source_row_number,
            pmf=row.pmf,
            predio_group_key=row.predio_group_key,
            estado=row.estado,
            estado_resumido=row.estado_resumido,
            numero_ingreso=row.numero_ingreso,
        )
        for row in rows
    ]
    result = build_pending(pending_inputs)

    detail_rows = [
        PendingPmfRowView(
            **_resumen_row_view(rows_by_number[summary.source_row_number]).model_dump(),
            pending_stage=summary.pending_stage,  # type: ignore[arg-type]
        )
        for summary in result.rows
    ]

    return TranselecPendingResponse(
        basis=result.basis,  # type: ignore[arg-type]
        pending_pmf_count=result.pending_pmf_count,
        total_pmf_count=result.total_pmf_count,
        pending_pmf_percentage=result.pending_pmf_percentage,
        stage_basis=result.stage_basis,  # type: ignore[arg-type]
        stages=PendingStageCountsView(**asdict(result.stages)),
        rows=detail_rows,
    )


# ---------------------------------------------------------------------------
# GET /owner-status — TR-FUNC-013
# ---------------------------------------------------------------------------


class OwnerStatusRowView(BaseModel):
    tipo_propietario: str | None
    owner_stage: str | None
    predio_count: int


class TranselecOwnerStatusResponse(BaseModel):
    basis: Literal["owner_stage_legacy"]
    total_predio_count: int
    rows: list[OwnerStatusRowView]


@router.get(
    "/owner-status",
    response_model=TranselecOwnerStatusResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_owner_status(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
) -> TranselecOwnerStatusResponse:
    """TR-FUNC-013: predio-grain, grouped by ``Tipo de propietario``, using
    Javier's existing ``ownerStage()`` rule (``owner_stage_legacy``) — named
    explicitly here so the disagreement with ``estado_resumido_first_row``
    and ``pending_priority_legacy`` for the same rows stays visible. Does
    NOT resolve TR-OPEN-01."""

    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)

    inputs = [
        OwnerStatusInputRow(
            source_row_number=row.source_row_number,
            predio_group_key=row.predio_group_key,
            pmf=row.pmf,
            tipo_propietario=row.tipo_propietario,
            estado=row.estado,
            estado_resumido=row.estado_resumido,
            numero_ingreso=row.numero_ingreso,
        )
        for row in rows
    ]
    result = build_owner_status(inputs)

    return TranselecOwnerStatusResponse(
        basis=result.basis,  # type: ignore[arg-type]
        total_predio_count=result.total_predio_count,
        rows=[
            OwnerStatusRowView(
                tipo_propietario=r.tipo_propietario,
                owner_stage=r.owner_stage,
                predio_count=r.predio_count,
            )
            for r in result.rows
        ],
    )


# ---------------------------------------------------------------------------
# GET /report — TR-FUNC-034
# ---------------------------------------------------------------------------

# **Corrected from an earlier draft of this route**: an earlier version
# shipped an invented "good-faith equivalent" narrative here because the
# functional parity matrix's TR-FUNC-034 row claimed the verbatim template
# was already "captured in the source audit" when it was not. The source
# forensic audit now records the real `renderReport()` template (confirmed
# by direct read of both source HTML files) — see that document's "Report
# template — CORRECTION" note. The text below is Actualizable's exact
# wording (near-identical to v0's; only the "pending" sentence differs
# slightly, and Actualizable is the more recent, more-used file).
#
# One deliberate change from the literal source: the real template hardcodes
# `Corte de información: 14-08-2026` — a frozen snapshot date, the same
# defect class as TR-FUNC-031/046's hardcoded "today" bugs. This is replaced
# with the active import's own publish date, read via the same
# `_read_latest_publish_event` lookup `/imports/active` uses, so "when is
# this data from" has exactly one source of truth in this codebase — never
# `datetime.now()` at request time, never the literal.
_REPORT_TEMPLATE = (
    "REPORTE EJECUTIVO · SEGUIMIENTO CONAF\n"
    "Corte de información: {corte}\n"
    "\n"
    "El alcance seleccionado comprende {pmf_count} PMF, {predio_count} predios "
    "identificados y {rol_count} roles, con {surface_total} ha de superficie de corta.\n"
    "\n"
    "Estado resumido: {aprobados} PMF aprobados ({rate}%), {en_tramite} en trámite y "
    "{pendiente_o_tachado} PMF con registros Pendiente o Tachado. Se identifican "
    "{servidumbre} predios con servidumbre firmada.\n"
    "\n"
    "Criterio: los PMF y predios se cuentan sin duplicados; la superficie corresponde "
    "a la suma de las áreas de corta filtradas. El N.º de ingreso se vincula al PMF "
    "correspondiente. Las resoluciones no pueden verificarse porque la fuente no "
    "incluye un campo específico para ellas."
)

_REPORT_DATE_FORMAT = "%d-%m-%Y"  # matches the literal template's own "14-08-2026" shape


def _fmt_es_number(value: float, *, decimals: int = 2) -> str:
    """Render a number the way both source HTML files' `fmt()` helper reads
    in Spanish-locale stakeholder text — comma decimal separator, per the
    source forensic audit's own "164,63 ha" example of this exact KPI.

    Not independently confirmed against `fmt()`'s own source (only its
    *output shape* is evidenced, via that one example) — an INFERENCE, not
    a verbatim reproduction, disclosed the same way the rest of this route
    discloses its remaining gaps.
    """

    return f"{value:.{decimals}f}".replace(".", ",")


class TranselecReportResponse(BaseModel):
    generated_at: str
    basis_estado_resumido: Literal["estado_resumido_first_row"]
    basis_pending_priority: Literal["pending_priority_legacy"]
    text: str


@router.get(
    "/report",
    response_model=TranselecReportResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_report(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
) -> TranselecReportResponse:
    """TR-FUNC-034: the real `renderReport()` template (Actualizable's
    wording), values substituted from the current filtered view. The data's
    own "as of" date comes from the active import's publish event, never
    from request time — see the module-level comment above for the full
    rationale and the one remaining disclosed gap (`fmt()`'s exact number
    format is inferred, not verified against source).
    """

    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)
    summary = build_summary([_to_summary_input_row(row) for row in rows])
    publish_event = _read_latest_publish_event(connection, import_id=import_id)

    rate = (summary.aprobados_pmf_count / summary.pmf_count * 100) if summary.pmf_count else 0.0

    text_body = _REPORT_TEMPLATE.format(
        corte=publish_event.occurred_at.strftime(_REPORT_DATE_FORMAT),
        pmf_count=summary.pmf_count,
        predio_count=summary.predio_count,
        rol_count=summary.rol_count,
        surface_total=_fmt_es_number(summary.surface_total),
        aprobados=summary.aprobados_pmf_count,
        rate=_fmt_es_number(rate),
        en_tramite=summary.en_tramite_pmf_count,
        pendiente_o_tachado=summary.avance_por_pmf.pendiente_o_tachado,
        servidumbre=summary.con_servidumbre_predio_count,
    )

    return TranselecReportResponse(
        generated_at=publish_event.occurred_at.isoformat(),
        basis_estado_resumido=summary.basis_estado_resumido,  # type: ignore[arg-type]
        basis_pending_priority=summary.basis_pending_priority,  # type: ignore[arg-type]
        text=text_body,
    )


# ---------------------------------------------------------------------------
# GET /export.csv — TR-FUNC-037
# ---------------------------------------------------------------------------


@router.get(
    "/export.csv",
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def export_csv(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
) -> Response:
    """TR-FUNC-037: filtered CSV export, the corrected 18-column field set
    (``transelec_ingestion.csv_export.EXPORT_FIELDS_V1`` — Actualizable's
    exact 17 fields, confirmed by direct read, with ``Carpeta`` split into
    its two positional source columns and ``Observación auxiliar`` shipped
    always-empty), with mandatory CSV formula-injection hardening — see
    that module's docstring for the full rationale. The hardening is a
    deliberate, security-motivated divergence from Javier's raw CSV export:
    neither source HTML file neutralizes a leading ``=``/``+``/``-``/``@``
    before writing a cell.
    """

    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)
    csv_bytes = render_transelec_export_csv([dict(row._mapping) for row in rows])

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="transelec_export.csv"'},
    )


# ---------------------------------------------------------------------------
# GET /imports, GET /imports/active — version history and active provenance
# ---------------------------------------------------------------------------


class TranselecImportHistoryRow(BaseModel):
    publish_event_id: int
    import_id: int
    event_type: Literal["publish", "restore"]
    occurred_at: str
    actor_app_user_id: int
    actor_display_name: str
    filename: str | None
    sha256: str
    business_rows: int
    distinct_pmf: int
    distinct_provisional_predio_ids: int
    surface_total: float
    is_active: bool


@router.get(
    "/imports",
    response_model=list[TranselecImportHistoryRow],
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def list_import_history(
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> list[TranselecImportHistoryRow]:
    """Version history (publish/restore audit trail) for the restore UI.

    One row per ``transelec_publish_event`` — an import activated twice
    (published, then later restored) appears twice, each with its own actor
    and timestamp, matching that table's own one-row-per-activation shape.
    """

    active_import_id = read_active_import_id(connection)

    rows = connection.execute(
        text(
            """
            SELECT
                pe.id AS publish_event_id,
                pe.import_id,
                pe.event_type,
                pe.occurred_at,
                pe.actor_user_id,
                u.display_name AS actor_display_name,
                i.business_rows,
                i.distinct_pmf,
                i.distinct_provisional_predio_ids,
                i.surface_total,
                s.content_sha256,
                (
                    SELECT o.filename
                    FROM platform.source_observation AS o
                    WHERE o.source_snapshot_id = s.id
                    ORDER BY o.observed_at DESC
                    LIMIT 1
                ) AS filename
            FROM platform.transelec_publish_event AS pe
            JOIN platform.transelec_import AS i ON i.id = pe.import_id
            JOIN platform.app_user AS u ON u.id = pe.actor_user_id
            JOIN platform.source_snapshot AS s ON s.id = i.source_snapshot_id
            ORDER BY pe.occurred_at DESC, pe.id DESC
            """
        )
    ).all()

    return [
        TranselecImportHistoryRow(
            publish_event_id=row.publish_event_id,
            import_id=row.import_id,
            event_type=row.event_type,
            occurred_at=row.occurred_at.isoformat(),
            actor_app_user_id=row.actor_user_id,
            actor_display_name=row.actor_display_name,
            filename=row.filename,
            sha256=row.content_sha256,
            business_rows=row.business_rows,
            distinct_pmf=row.distinct_pmf,
            distinct_provisional_predio_ids=row.distinct_provisional_predio_ids,
            surface_total=row.surface_total,
            is_active=row.import_id == active_import_id,
        )
        for row in rows
    ]


class TranselecActiveImportResponse(BaseModel):
    import_id: int
    sha256: str
    byte_size: int
    filename: str | None
    schema_contract_version: str
    parser_version: str
    business_rows: int
    distinct_pmf: int
    distinct_provisional_predio_ids: int
    surface_total: float
    validated_at: str
    published_event_type: Literal["publish", "restore"]
    published_at: str
    published_by_app_user_id: int
    published_by_display_name: str
    warning_count: int
    # The contract fields the source layout actually carried. A field absent
    # here had no column in the workbook, which is different from a column
    # whose cells are blank — the dashboard must not present the two alike.
    source_fields: list[str]


def _source_fields(
    schema_contract_version: str, mapping_report: dict[str, Any] | None
) -> list[str]:
    """Fields the source layout carried for one import.

    Contract V1 imports kept no report, but V1 accepted a workbook only if it
    had exactly the 30 legacy columns, so those — and only those — were
    present. A V2 import states its mapped fields in its report.
    """

    if mapping_report is None:
        if schema_contract_version == "transelec-resumen-v1":
            return [name for _, name in RESUMEN_COLUMNS]
        return []
    return [entry["field"] for entry in mapping_report.get("fields", []) if entry.get("column")]


@router.get(
    "/imports/active",
    response_model=TranselecActiveImportResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_active_import(
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> TranselecActiveImportResponse:
    """Current active version's provenance (TR-FUNC-043).

    ``published_*`` fields are read from the most recent
    ``transelec_publish_event`` row for the active import — NOT from
    ``transelec_import``, which only records who/when it was *validated*
    (Step B), a different actor/timestamp than who published or restored it
    (Step C/D). See the design doc §2's corrected schema rationale.
    """

    import_id = _require_active_import_id(connection)

    imp = connection.execute(
        text(
            """
            SELECT i.id, i.source_snapshot_id, i.schema_contract_version, i.parser_version,
                   i.business_rows, i.distinct_pmf, i.distinct_provisional_predio_ids,
                   i.surface_total, i.validated_at, i.warning_count, i.mapping_report,
                   s.content_sha256, s.byte_size
            FROM platform.transelec_import AS i
            JOIN platform.source_snapshot AS s ON s.id = i.source_snapshot_id
            WHERE i.id = :import_id
            """
        ),
        {"import_id": import_id},
    ).one()

    filename = connection.execute(
        text(
            """
            SELECT filename FROM platform.source_observation
            WHERE source_snapshot_id = :snapshot_id
            ORDER BY observed_at DESC LIMIT 1
            """
        ),
        {"snapshot_id": imp.source_snapshot_id},
    ).scalar_one_or_none()

    publish_event = _read_latest_publish_event(connection, import_id=import_id)

    return TranselecActiveImportResponse(
        import_id=imp.id,
        sha256=imp.content_sha256,
        byte_size=imp.byte_size,
        filename=filename,
        schema_contract_version=imp.schema_contract_version,
        parser_version=imp.parser_version,
        business_rows=imp.business_rows,
        distinct_pmf=imp.distinct_pmf,
        distinct_provisional_predio_ids=imp.distinct_provisional_predio_ids,
        surface_total=imp.surface_total,
        validated_at=imp.validated_at.isoformat(),
        published_event_type=publish_event.event_type,
        published_at=publish_event.occurred_at.isoformat(),
        published_by_app_user_id=publish_event.actor_user_id,
        published_by_display_name=publish_event.display_name,
        warning_count=imp.warning_count,
        source_fields=_source_fields(imp.schema_contract_version, imp.mapping_report),
    )


class TranselecImportReportResponse(BaseModel):
    import_id: int
    schema_contract_version: str
    parser_version: str
    validated_at: str
    warning_count: int
    source_fields: list[str]
    mapping_report: dict[str, Any] | None


@router.get(
    "/imports/{import_id}/report",
    response_model=TranselecImportReportResponse,
    dependencies=[Depends(require_transelec_grant(Action.PROCESS))],
)
def get_import_report(
    import_id: int,
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> TranselecImportReportResponse:
    """The persisted layout report of one import, for review before (or
    after) publishing. Operator-only, like the import flow that produced it.
    """

    imp = connection.execute(
        text(
            """
            SELECT id, schema_contract_version, parser_version, validated_at,
                   warning_count, mapping_report
            FROM platform.transelec_import
            WHERE id = :import_id
            """
        ),
        {"import_id": import_id},
    ).one_or_none()

    if imp is None:
        raise HTTPException(status_code=404, detail=_IMPORT_NOT_FOUND)

    return TranselecImportReportResponse(
        import_id=imp.id,
        schema_contract_version=imp.schema_contract_version,
        parser_version=imp.parser_version,
        validated_at=imp.validated_at.isoformat(),
        warning_count=imp.warning_count,
        source_fields=_source_fields(imp.schema_contract_version, imp.mapping_report),
        mapping_report=imp.mapping_report,
    )


# ---------------------------------------------------------------------------
# GET /uploads/recent — resolves ingestion_run_id for the importar UI flow
#
# Task 3 flagged that POST /transelec/uploads deliberately returns the
# shared, unmodified UploadResponse, which does not carry ingestion_run_id —
# needed to call POST /transelec/imports/{ingestion_run_id}/validate-and-project.
# This route lets the frontend resolve it (matching the returned
# source_snapshot_id) without running SQL, folded into a "recent
# uploads/runs" list per Task 3's own suggested shape.
# ---------------------------------------------------------------------------


class TranselecRecentRunView(BaseModel):
    ingestion_run_id: int
    source_snapshot_id: int
    filename: str | None
    sha256: str
    requested_by_app_user_id: int | None
    created_at: str
    import_id: int | None
    is_active: bool


@router.get(
    "/uploads/recent",
    response_model=list[TranselecRecentRunView],
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def list_recent_uploads(
    connection: Annotated[Connection, Depends(get_db_connection)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[TranselecRecentRunView]:
    active_import_id = read_active_import_id(connection)

    rows = connection.execute(
        text(
            """
            SELECT
                r.id AS ingestion_run_id,
                r.source_snapshot_id,
                r.requested_by_app_user_id,
                r.created_at,
                s.content_sha256,
                (
                    SELECT o.filename FROM platform.source_observation AS o
                    WHERE o.source_snapshot_id = s.id
                    ORDER BY o.observed_at DESC LIMIT 1
                ) AS filename,
                i.id AS import_id
            FROM platform.ingestion_run AS r
            JOIN platform.source_snapshot AS s ON s.id = r.source_snapshot_id
            LEFT JOIN platform.transelec_import AS i ON i.source_snapshot_id = s.id
            WHERE r.product_key = :product_key
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT :limit
            """
        ),
        {"product_key": TRANSELEC_PRODUCT_KEY, "limit": limit},
    ).all()

    return [
        TranselecRecentRunView(
            ingestion_run_id=row.ingestion_run_id,
            source_snapshot_id=row.source_snapshot_id,
            filename=row.filename,
            sha256=row.content_sha256,
            requested_by_app_user_id=row.requested_by_app_user_id,
            created_at=row.created_at.isoformat(),
            import_id=row.import_id,
            is_active=row.import_id is not None and row.import_id == active_import_id,
        )
        for row in rows
    ]
