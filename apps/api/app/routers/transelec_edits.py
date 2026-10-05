"""Transelec web edits: field overrides and the planilla download marked «web».

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
§4-§5. Mounted beside ``app.routers.transelec`` with the same ``/transelec``
prefix (and its ``/api`` alias in ``app.main``). Mutations are
CSRF-protected and need ``Action.EDIT`` (OPERATOR/ADMIN). The list needs
only ``Action.VIEW``: every viewer sees the «web» chips and who made them.

Client-facing failures are Spanish and never quote a cell value; audit
metadata carries field names, ids and counts only (``app.audit``).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError
from starlette.background import BackgroundTask

from app.access import Action
from app.access_repository import AppUser
from app.audit import record_audit_event
from app.csrf import require_csrf
from app.database import get_database_engine
from app.deps import get_current_app_user, get_db_connection, get_object_store
from app.object_store import ObjectStore, ObjectStoreError
from app.routers.transelec import (
    _DOWNLOAD_CHUNK_BYTES,
    _RESUMEN_ROW_COLUMNS,
    _SOURCE_UNAVAILABLE,
    ResumenRowView,
    _require_active_import_id,
    _resumen_row_view,
    require_transelec_grant,
)
from app.transelec_overrides import (
    FieldNotInSourceError,
    HistoryRecord,
    HistoryState,
    NoActiveVersionError,
    NotInConflictError,
    OverrideNotFoundError,
    OverrideRecord,
    OverrideStatus,
    RowNotFoundError,
    ValueChangedError,
    VersionChangedError,
    discard_override,
    keep_override,
    list_override_history,
    list_overrides,
    save_override,
)
from app.transelec_publication import TRANSELEC_PRODUCT_KEY
from transelec_ingestion.field_overrides import (
    EDITABLE_BY_NAME,
    OverrideValueError,
    comparable,
    display,
    note_text,
    parse_value,
)
from transelec_ingestion.xlsx_web_patch import CellEdit, WorkbookPatchError, patch_workbook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transelec", tags=["transelec"])

_FIELD_NOT_EDITABLE = "Este campo no se puede editar en el panel."
_FIELD_NOT_IN_SOURCE = (
    "La planilla publicada no tiene una columna para este campo; no se puede editar."
)
_ROW_NOT_FOUND = "No se encontró la fila en la versión activa."
_NO_ACTIVE_IMPORT = "No hay una versión publicada de Transelec."
_VERSION_CHANGED = (
    "Se publicó otra versión de la planilla mientras editaba. Recargue la página para ver la "
    "versión activa."
)
_VALUE_CHANGED = (
    "Otra persona cambió este valor mientras lo editaba. Recargue para ver el valor actual."
)
_OVERRIDE_NOT_FOUND = "No se encontró la edición solicitada."
_ACTIVE_CELL_INDEX = "uq_transelec_field_override_active_cell"
_NOT_IN_CONFLICT = "Sólo se puede mantener una edición que está en conflicto con la planilla."


def _is_active_cell_violation(exc: IntegrityError) -> bool:
    """True only for the partial unique index on active edits (migration 0012)."""

    diagnostic = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diagnostic, "constraint_name", None) == _ACTIVE_CELL_INDEX


def _conflict(code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": detail, "code": code})


class OverrideSaveRequest(BaseModel):
    import_id: int
    source_row_number: int
    field: str
    value: str | None = Field(default=None, max_length=4000)
    expected_value: str | None = Field(default=None, max_length=4000)


class OverrideSaveResponse(BaseModel):
    override_id: int | None
    changed: bool
    row: ResumenRowView


class OverrideKeepResponse(BaseModel):
    override_id: int


class OverrideView(BaseModel):
    id: int
    field: str
    field_label: str
    status: Literal["aplicada", "incorporada", "en_conflicto", "huerfana"]
    pmf: str
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    source_row_number: int | None
    web_value: str | None
    planilla_value_at_edit: str | None
    planilla_value_now: str | None
    created_by_display_name: str
    created_at: str


def _override_view(record: OverrideRecord) -> OverrideView:
    return OverrideView(
        id=record.id,
        field=record.field,
        field_label=EDITABLE_BY_NAME[record.field].label,
        status=record.status,
        pmf=record.pmf,
        rol=record.rol,
        numero_predio=record.numero_predio,
        numero_area_corta=record.numero_area_corta,
        source_row_number=record.source_row_number,
        web_value=display(record.web),
        planilla_value_at_edit=display(record.planilla_at_edit),
        planilla_value_now=display(record.planilla_now),
        created_by_display_name=record.created_by_display_name,
        created_at=record.created_at.isoformat(),
    )


@router.put(
    "/overrides",
    response_model=OverrideSaveResponse,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.EDIT))],
)
def save_field_override(
    payload: OverrideSaveRequest,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> OverrideSaveResponse | JSONResponse:
    """Save one cell of the active version (spec §4)."""

    field = EDITABLE_BY_NAME.get(payload.field)
    if field is None:
        raise HTTPException(status_code=422, detail=_FIELD_NOT_EDITABLE)
    try:
        value = parse_value(field, payload.value)
        expected = comparable(field, payload.expected_value)
    except OverrideValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        with engine.begin() as tx:
            outcome = save_override(
                tx,
                import_id=payload.import_id,
                source_row_number=payload.source_row_number,
                field=field,
                value=value,
                expected=expected,
                actor_app_user_id=user.id,
            )
            audited_id = outcome.override_id or outcome.ended_override_id
            if outcome.changed and audited_id is not None:
                record_audit_event(
                    tx,
                    actor_app_user_id=user.id,
                    event_type="transelec.override.saved",
                    product_key=TRANSELEC_PRODUCT_KEY,
                    subject_kind="transelec_override",
                    subject_id=str(audited_id),
                    metadata={
                        "field": field.name,
                        "import_id": payload.import_id,
                        "source_row_number": payload.source_row_number,
                        "ended_override_id": outcome.ended_override_id,
                        "returned_to_planilla": outcome.override_id is None,
                    },
                )
            row = tx.execute(
                text(
                    f"SELECT {', '.join(_RESUMEN_ROW_COLUMNS)} "
                    "FROM platform.transelec_effective_row "
                    "WHERE import_id = :import_id AND source_row_number = :row"
                ),
                {"import_id": payload.import_id, "row": payload.source_row_number},
            ).one()
    except VersionChangedError:
        return _conflict("version_changed", _VERSION_CHANGED)
    except ValueChangedError:
        return _conflict("value_changed", _VALUE_CHANGED)
    except IntegrityError as exc:
        # Only a concurrent save losing the partial unique index is "value
        # changed"; any other integrity failure is a server error.
        if not _is_active_cell_violation(exc):
            raise
        return _conflict("value_changed", _VALUE_CHANGED)
    except NoActiveVersionError as exc:
        raise HTTPException(status_code=404, detail=_NO_ACTIVE_IMPORT) from exc
    except RowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_ROW_NOT_FOUND) from exc
    except FieldNotInSourceError as exc:
        raise HTTPException(status_code=422, detail=_FIELD_NOT_IN_SOURCE) from exc

    return OverrideSaveResponse(
        override_id=outcome.override_id,
        changed=outcome.changed and audited_id is not None,
        row=_resumen_row_view(row),
    )


@router.delete(
    "/overrides/{override_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.EDIT))],
)
def discard_field_override(
    override_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> Response:
    """Return the cell to the planilla value."""

    try:
        with engine.begin() as tx:
            discard_override(tx, override_id=override_id, actor_app_user_id=user.id)
            record_audit_event(
                tx,
                actor_app_user_id=user.id,
                event_type="transelec.override.discarded",
                product_key=TRANSELEC_PRODUCT_KEY,
                subject_kind="transelec_override",
                subject_id=str(override_id),
            )
    except OverrideNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_OVERRIDE_NOT_FOUND) from exc
    return Response(status_code=204)


@router.post(
    "/overrides/{override_id}/keep",
    response_model=OverrideKeepResponse,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.EDIT))],
)
def keep_field_override(
    override_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> OverrideKeepResponse | JSONResponse:
    """Keep a web value the newer planilla contradicts (spec §4)."""

    try:
        with engine.begin() as tx:
            new_id = keep_override(tx, override_id=override_id, actor_app_user_id=user.id)
            record_audit_event(
                tx,
                actor_app_user_id=user.id,
                event_type="transelec.override.kept",
                product_key=TRANSELEC_PRODUCT_KEY,
                subject_kind="transelec_override",
                subject_id=str(new_id),
                metadata={"kept_override_id": override_id},
            )
    except NotInConflictError:
        return _conflict("not_in_conflict", _NOT_IN_CONFLICT)
    except OverrideNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_OVERRIDE_NOT_FOUND) from exc
    except NoActiveVersionError as exc:
        raise HTTPException(status_code=404, detail=_NO_ACTIVE_IMPORT) from exc
    return OverrideKeepResponse(override_id=new_id)


@router.get(
    "/overrides",
    response_model=list[OverrideView],
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def list_field_overrides(
    connection: Annotated[Connection, Depends(get_db_connection)],
    status: Annotated[OverrideStatus | None, Query()] = None,
    pmf: Annotated[str | None, Query()] = None,
) -> list[OverrideView]:
    """Active edits against the published version, conflicts and orphans first."""

    import_id = _require_active_import_id(connection)
    return [
        _override_view(record)
        for record in list_overrides(connection, import_id=import_id, status=status, pmf=pmf)
    ]


class OverrideHistoryEntryView(BaseModel):
    id: int
    field: str
    field_label: str
    pmf: str
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    source_row_number: int | None
    web_value: str | None
    planilla_value_at_edit: str | None
    created_by_display_name: str
    created_at: str
    state: HistoryState
    ended_at: str | None
    ended_by_display_name: str | None


class OverrideHistoryResponse(BaseModel):
    in_force_count: int
    needs_review_count: int
    entries: list[OverrideHistoryEntryView]


def _history_entry_view(record: HistoryRecord) -> OverrideHistoryEntryView:
    return OverrideHistoryEntryView(
        id=record.id,
        field=record.field,
        field_label=EDITABLE_BY_NAME[record.field].label,
        pmf=record.pmf,
        rol=record.rol,
        numero_predio=record.numero_predio,
        numero_area_corta=record.numero_area_corta,
        source_row_number=record.source_row_number,
        web_value=display(record.web),
        planilla_value_at_edit=display(record.planilla_at_edit),
        created_by_display_name=record.created_by_display_name,
        created_at=record.created_at.isoformat(),
        state=record.state,
        ended_at=None if record.ended_at is None else record.ended_at.isoformat(),
        ended_by_display_name=record.ended_by_display_name,
    )


@router.get(
    "/overrides/history",
    response_model=OverrideHistoryResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def list_field_override_history(
    connection: Annotated[Connection, Depends(get_db_connection)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OverrideHistoryResponse:
    """The latest edits, active or ended, for the header's edits log.

    Spec: docs/superpowers/specs/2026-10-05-transelec-web-edits-indicator-design.md §1.
    A read: no audit row.
    """

    import_id = _require_active_import_id(connection)
    page = list_override_history(connection, import_id=import_id, limit=limit)
    return OverrideHistoryResponse(
        in_force_count=page.in_force_count,
        needs_review_count=page.needs_review_count,
        entries=[_history_entry_view(record) for record in page.entries],
    )


_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXPORT_NEEDS_MAPPING = (
    "Esta versión se importó sin el mapa de columnas; vuelva a importar la planilla para "
    "descargarla con ediciones."
)
_EXPORT_FAILED = (
    "No se pudo preparar la planilla con ediciones: su estructura no es la esperada. "
    "Contacte a soporte."
)


@router.get(
    "/export.xlsx",
    response_model=None,
    dependencies=[Depends(require_transelec_grant(Action.EDIT))],
)
def export_planilla_with_edits(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> FileResponse | JSONResponse:
    """The active version's uploaded planilla with its applied edits marked «web» (spec §5)."""

    import_id = _require_active_import_id(connection)
    source = connection.execute(
        text(
            """
            SELECT i.mapping_report, s.object_storage_key,
                   (SELECT o.filename FROM platform.source_observation AS o
                    WHERE o.source_snapshot_id = s.id
                    ORDER BY o.observed_at DESC LIMIT 1) AS filename,
                   (now() AT TIME ZONE 'America/Santiago')::date AS today_chile
            FROM platform.transelec_import AS i
            JOIN platform.source_snapshot AS s ON s.id = i.source_snapshot_id
            WHERE i.id = :import_id
            """
        ),
        {"import_id": import_id},
    ).one()
    if source.mapping_report is None:
        return _conflict("mapping_report_missing", _EXPORT_NEEDS_MAPPING)
    if source.object_storage_key is None:
        return _conflict("workbook_unavailable", _SOURCE_UNAVAILABLE)

    columns = {
        entry["field"]: entry["column"]
        for entry in source.mapping_report.get("fields", [])
        if entry.get("column")
    }
    edits: list[CellEdit] = []
    unmapped = 0
    for record in list_overrides(connection, import_id=import_id, status="aplicada"):
        column = columns.get(record.field)
        if column is None or record.source_row_number is None:
            unmapped += 1
            continue
        field = EDITABLE_BY_NAME[record.field]
        text_value, date_value = record.web
        edits.append(
            CellEdit(
                row=record.source_row_number,
                column=column,
                kind=field.kind,
                value=date_value if field.kind == "date" else text_value,
                note=note_text(
                    author=record.created_by_display_name,
                    edited_on=record.created_on_chile,
                    planilla=record.planilla_at_edit,
                ),
            )
        )

    workdir = Path(tempfile.mkdtemp(prefix="campo-transelec-export-"))
    source_path = workdir / "source.xlsx"
    output_path = workdir / "planilla-web.xlsx"
    try:
        with store.open(source.object_storage_key) as reader, source_path.open("wb") as sink:
            while chunk := reader.read(_DOWNLOAD_CHUNK_BYTES):
                sink.write(chunk)
        result = patch_workbook(
            source_path,
            output_path,
            sheet_name=source.mapping_report["sheet_name"],
            edits=edits,
        )
    except ObjectStoreError:
        shutil.rmtree(workdir, ignore_errors=True)
        logger.warning("Transelec export: source object unavailable for import_id=%s", import_id)
        return _conflict("workbook_unavailable", _SOURCE_UNAVAILABLE)
    except WorkbookPatchError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        logger.warning("Transelec export refused for import_id=%s: %s", import_id, exc)
        return JSONResponse(
            status_code=422, content={"detail": _EXPORT_FAILED, "code": "workbook_unpatchable"}
        )
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    try:
        record_audit_event(
            connection,
            actor_app_user_id=user.id,
            event_type="transelec.export.xlsx_downloaded",
            product_key=TRANSELEC_PRODUCT_KEY,
            subject_kind="transelec_import",
            subject_id=str(import_id),
            metadata={
                "written": len(result.written),
                "skipped_formula": len(result.skipped),
                "unmapped": unmapped,
            },
        )
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    stem = Path(source.filename or "planilla").stem
    return FileResponse(
        output_path,
        media_type=_XLSX_MIME,
        filename=f"{stem}_web_{source.today_chile.isoformat()}.xlsx",
        background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
    )
