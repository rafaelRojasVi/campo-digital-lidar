"""Persistence for Transelec web edits (field overrides).

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
§1-§4. The table and the three views come from migration 0012. An edit's
status is computed only by ``platform.transelec_override_state``; this
module never re-derives it, so the dashboard, the download and activation
always agree on which edits apply.

Every function runs inside the caller's transaction; the caller commits.
Field names interpolated into SQL come only from ``EDITABLE_BY_NAME``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Connection, text

from transelec_ingestion.field_overrides import (
    EditableField,
    Signature,
    cell_signature,
    shown_value,
    value_signature,
)
from transelec_ingestion.xlsx_contract import RESUMEN_COLUMNS

OverrideStatus = Literal["aplicada", "incorporada", "en_conflicto", "huerfana"]


class OverrideError(RuntimeError):
    """Base error for a web-edit operation."""


class NoActiveVersionError(OverrideError):
    """Nothing is published, so there is nothing to edit."""


class VersionChangedError(OverrideError):
    """The edit was made against a version that is no longer the active one."""


class RowNotFoundError(OverrideError):
    """The source row does not exist in the active version."""


class FieldNotInSourceError(OverrideError):
    """The published planilla has no column for this field."""


class ValueChangedError(OverrideError):
    """The value changed since the editor loaded it."""


class OverrideNotFoundError(OverrideError):
    """No active edit with that id."""


class NotInConflictError(OverrideError):
    """Only an edit in conflict with the planilla can be kept."""


@dataclass(frozen=True, slots=True)
class SaveOutcome:
    """``override_id`` is None when the cell went back to the planilla value."""

    override_id: int | None
    ended_override_id: int | None
    changed: bool


@dataclass(frozen=True, slots=True)
class OverrideRecord:
    id: int
    field: str
    status: OverrideStatus
    pmf: str
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    key_ordinal: int
    source_row_number: int | None
    web: Signature
    planilla_at_edit: Signature
    planilla_now: Signature
    created_by_display_name: str
    created_at: dt.datetime
    created_on_chile: dt.date


_KEY_MATCH = """
    pmf = :pmf
    AND rol IS NOT DISTINCT FROM :rol
    AND numero_predio IS NOT DISTINCT FROM :numero_predio
    AND numero_area_corta IS NOT DISTINCT FROM :numero_area_corta
    AND key_ordinal = :key_ordinal
"""

_INSERT = """
    INSERT INTO platform.transelec_field_override (
        pmf, rol, numero_predio, numero_area_corta, key_ordinal, field,
        value_text, value_date, planilla_value_text, planilla_value_date,
        base_import_id, created_by_app_user_id
    )
    VALUES (
        :pmf, :rol, :numero_predio, :numero_area_corta, :key_ordinal, :field,
        :value_text, :value_date, :planilla_value_text, :planilla_value_date,
        :base_import_id, :actor
    )
    RETURNING id
"""


def _locked_active_import(connection: Connection) -> int:
    """The active import, share-locked so no activation interleaves with an edit.

    ``activate_import`` takes ``FOR UPDATE`` on the same singleton row, so an
    edit and a publish/restore serialize instead of racing.
    """

    active = connection.execute(
        text(
            "SELECT active_import_id FROM platform.transelec_dashboard_state WHERE id = 1 FOR SHARE"
        )
    ).scalar_one()
    if active is None:
        raise NoActiveVersionError()
    return int(active)


def source_fields(schema_contract_version: str, mapping_report: dict[str, Any] | None) -> list[str]:
    """Fields the source layout carried for one import.

    Contract V1 imports kept no report, but V1 accepted a workbook only if it
    had exactly the 30 legacy columns, so those, and only those, were present.
    A V2 import states its mapped fields in its report. The router's read
    models and the edit check share this one rule.
    """

    if mapping_report is None:
        if schema_contract_version == "transelec-resumen-v1":
            return [name for _, name in RESUMEN_COLUMNS]
        return []
    return [entry["field"] for entry in mapping_report.get("fields", []) if entry.get("column")]


def _import_source_fields(connection: Connection, *, import_id: int) -> set[str]:
    row = connection.execute(
        text(
            "SELECT schema_contract_version, mapping_report "
            "FROM platform.transelec_import WHERE id = :id"
        ),
        {"id": import_id},
    ).one()
    return set(source_fields(row.schema_contract_version, row.mapping_report))


def _lock_cell(
    connection: Connection,
    *,
    pmf: str,
    rol: str | None,
    numero_predio: str | None,
    numero_area_corta: str | None,
    key_ordinal: int,
    field: str,
) -> None:
    """Serialize every edit of one cell for the rest of the transaction.

    Lock order in every edit path: the dashboard-state singleton (FOR SHARE),
    then this advisory lock, then rows. Activation takes the singleton FOR
    UPDATE and never an advisory lock, so no cycle can form. The effective
    value must be read only after this lock, or ``expected`` is checked
    against a value another transaction is about to end.
    """

    identity = "|".join(
        [
            pmf,
            "" if rol is None else "v" + rol,
            "" if numero_predio is None else "v" + numero_predio,
            "" if numero_area_corta is None else "v" + numero_area_corta,
            str(key_ordinal),
            field,
        ]
    )
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": identity},
    )


def _end(connection: Connection, *, override_id: int, reason: str, actor: int) -> None:
    connection.execute(
        text(
            """
            UPDATE platform.transelec_field_override
            SET ended_at = now(), ended_by_app_user_id = :actor, end_reason = :reason
            WHERE id = :id AND ended_at IS NULL
            """
        ),
        {"id": override_id, "reason": reason, "actor": actor},
    )


def save_override(
    connection: Connection,
    *,
    import_id: int,
    source_row_number: int,
    field: EditableField,
    value: str | dt.date | None,
    expected: str | dt.date | None,
    actor_app_user_id: int,
) -> SaveOutcome:
    """Save one cell. ``expected`` is what the editor saw (``comparable`` form)."""

    if import_id != _locked_active_import(connection):
        raise VersionChangedError()

    if field.name not in _import_source_fields(connection, import_id=import_id):
        raise FieldNotInSourceError()

    source = connection.execute(
        text(
            "SELECT * FROM platform.transelec_keyed_row "
            "WHERE import_id = :import_id AND source_row_number = :row"
        ),
        {"import_id": import_id, "row": source_row_number},
    ).one_or_none()
    if source is None:
        raise RowNotFoundError()

    _lock_cell(
        connection,
        pmf=source.pmf,
        rol=source.rol,
        numero_predio=source.numero_predio,
        numero_area_corta=source.numero_area_corta,
        key_ordinal=source.key_ordinal,
        field=field.name,
    )
    effective = connection.execute(
        text(
            f"SELECT {field.name} AS value, source_text_dates "
            "FROM platform.transelec_effective_row "
            "WHERE import_id = :import_id AND source_row_number = :row"
        ),
        {"import_id": import_id, "row": source_row_number},
    ).one()
    if shown_value(field, effective.value) != expected:
        raise ValueChangedError()

    key = {
        "pmf": source.pmf,
        "rol": source.rol,
        "numero_predio": source.numero_predio,
        "numero_area_corta": source.numero_area_corta,
        "key_ordinal": source.key_ordinal,
        "field": field.name,
    }
    active_id = connection.execute(
        text(
            "SELECT id FROM platform.transelec_field_override "
            f"WHERE ended_at IS NULL AND field = :field AND {_KEY_MATCH} FOR UPDATE"
        ),
        key,
    ).scalar_one_or_none()

    web = value_signature(field, value)
    if web == cell_signature(field, value=effective.value, text_dates=effective.source_text_dates):
        return SaveOutcome(override_id=active_id, ended_override_id=None, changed=False)

    # Exactly one side is set: a date cell that held raw text records that
    # text only; a real date records the date only (see ``cell_signature``).
    planilla = cell_signature(
        field, value=getattr(source, field.name), text_dates=source.source_text_dates
    )
    if web == planilla:
        if active_id is not None:
            _end(connection, override_id=active_id, reason="discarded", actor=actor_app_user_id)
        return SaveOutcome(override_id=None, ended_override_id=active_id, changed=True)

    if active_id is not None:
        _end(connection, override_id=active_id, reason="superseded", actor=actor_app_user_id)
    new_id = connection.execute(
        text(_INSERT),
        {
            **key,
            "value_text": web[0],
            "value_date": web[1],
            "planilla_value_text": planilla[0],
            "planilla_value_date": planilla[1],
            "base_import_id": import_id,
            "actor": actor_app_user_id,
        },
    ).scalar_one()
    return SaveOutcome(override_id=int(new_id), ended_override_id=active_id, changed=True)


def _lock_cell_of_override(connection: Connection, *, override_id: int) -> None:
    """Take the cell lock for an edit found by id (no row lock yet)."""

    key = connection.execute(
        text(
            "SELECT pmf, rol, numero_predio, numero_area_corta, key_ordinal, field "
            "FROM platform.transelec_field_override WHERE id = :id"
        ),
        {"id": override_id},
    ).one_or_none()
    if key is None:
        raise OverrideNotFoundError()
    _lock_cell(
        connection,
        pmf=key.pmf,
        rol=key.rol,
        numero_predio=key.numero_predio,
        numero_area_corta=key.numero_area_corta,
        key_ordinal=key.key_ordinal,
        field=key.field,
    )


def discard_override(connection: Connection, *, override_id: int, actor_app_user_id: int) -> None:
    """Return the cell to the planilla value."""

    connection.execute(
        text("SELECT 1 FROM platform.transelec_dashboard_state WHERE id = 1 FOR SHARE")
    )
    _lock_cell_of_override(connection, override_id=override_id)
    ended = connection.execute(
        text(
            """
            UPDATE platform.transelec_field_override
            SET ended_at = now(), ended_by_app_user_id = :actor, end_reason = 'discarded'
            WHERE id = :id AND ended_at IS NULL
            RETURNING id
            """
        ),
        {"id": override_id, "actor": actor_app_user_id},
    ).scalar_one_or_none()
    if ended is None:
        raise OverrideNotFoundError()


def keep_override(connection: Connection, *, override_id: int, actor_app_user_id: int) -> int:
    """Keep a conflicting web value: re-anchor it to the current planilla value."""

    import_id = _locked_active_import(connection)
    _lock_cell_of_override(connection, override_id=override_id)
    current = connection.execute(
        text(
            "SELECT * FROM platform.transelec_field_override "
            "WHERE id = :id AND ended_at IS NULL FOR UPDATE"
        ),
        {"id": override_id},
    ).one_or_none()
    if current is None:
        raise OverrideNotFoundError()
    state = connection.execute(
        text(
            "SELECT status, source_text, source_date FROM platform.transelec_override_state "
            "WHERE override_id = :id AND import_id = :import_id"
        ),
        {"id": override_id, "import_id": import_id},
    ).one()
    if state.status != "en_conflicto":
        raise NotInConflictError()

    _end(connection, override_id=override_id, reason="kept", actor=actor_app_user_id)
    new_id = connection.execute(
        text(_INSERT),
        {
            "pmf": current.pmf,
            "rol": current.rol,
            "numero_predio": current.numero_predio,
            "numero_area_corta": current.numero_area_corta,
            "key_ordinal": current.key_ordinal,
            "field": current.field,
            "value_text": current.value_text,
            "value_date": current.value_date,
            "planilla_value_text": state.source_text,
            "planilla_value_date": state.source_date,
            "base_import_id": import_id,
            "actor": actor_app_user_id,
        },
    ).scalar_one()
    return int(new_id)


def list_overrides(
    connection: Connection,
    *,
    import_id: int,
    status: OverrideStatus | None = None,
    pmf: str | None = None,
) -> list[OverrideRecord]:
    """Active edits against ``import_id``: conflicts first, then orphans, then the rest."""

    clauses = ""
    params: dict[str, Any] = {"import_id": import_id}
    if status is not None:
        clauses += " AND s.status = :status"
        params["status"] = status
    if pmf is not None:
        clauses += " AND o.pmf = :pmf"
        params["pmf"] = pmf

    rows = connection.execute(
        text(
            f"""
            SELECT o.id, o.field, s.status, o.pmf, o.rol, o.numero_predio,
                   o.numero_area_corta, o.key_ordinal, s.source_row_number,
                   o.value_text, o.value_date, o.planilla_value_text, o.planilla_value_date,
                   s.source_text, s.source_date, u.display_name, o.created_at,
                   (o.created_at AT TIME ZONE 'America/Santiago')::date AS created_on_chile
            FROM platform.transelec_override_state AS s
            JOIN platform.transelec_field_override AS o ON o.id = s.override_id
            JOIN platform.app_user AS u ON u.id = o.created_by_app_user_id
            WHERE s.import_id = :import_id{clauses}
            ORDER BY
                CASE s.status
                    WHEN 'en_conflicto' THEN 0
                    WHEN 'huerfana' THEN 1
                    WHEN 'aplicada' THEN 2
                    ELSE 3
                END,
                o.pmf, s.source_row_number NULLS LAST, o.field, o.id
            """
        ),
        params,
    ).all()
    return [
        OverrideRecord(
            id=row.id,
            field=row.field,
            status=row.status,
            pmf=row.pmf,
            rol=row.rol,
            numero_predio=row.numero_predio,
            numero_area_corta=row.numero_area_corta,
            key_ordinal=row.key_ordinal,
            source_row_number=row.source_row_number,
            web=(row.value_text, row.value_date),
            planilla_at_edit=(row.planilla_value_text, row.planilla_value_date),
            planilla_now=(row.source_text, row.source_date),
            created_by_display_name=row.display_name,
            created_at=row.created_at,
            created_on_chile=row.created_on_chile,
        )
        for row in rows
    ]


def retire_incorporated_overrides(
    connection: Connection, *, import_id: int, actor_app_user_id: int
) -> int:
    """End every edit the newly active planilla already carries; return how many."""

    fields = sorted(_import_source_fields(connection, import_id=import_id))
    retired = connection.execute(
        text(
            """
            UPDATE platform.transelec_field_override AS o
            SET ended_at = now(), ended_by_app_user_id = :actor, end_reason = 'incorporated'
            FROM platform.transelec_override_state AS s
            WHERE s.override_id = o.id
              AND s.import_id = :import_id
              AND s.status = 'incorporada'
              AND o.ended_at IS NULL
              AND o.field = ANY(:fields)
            RETURNING o.id
            """
        ),
        {"import_id": import_id, "actor": actor_app_user_id, "fields": fields},
    ).all()
    return len(retired)
