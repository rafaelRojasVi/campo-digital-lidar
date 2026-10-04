"""Which ``Resumen`` fields a dashboard user may edit, and the one rule for
comparing an edited value with the planilla's cell.

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
("Editable fields", §2). ``platform.transelec_norm_text`` (migration 0012)
is ``normalize_text`` in SQL; the two must stay identical, and
``apps/api/integration_tests/test_transelec_overrides.py`` checks they agree.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from transelec_ingestion.resumen_layout import FIELD_BY_NAME

EditableKind = Literal["text", "date"]

# A planilla cell as the comparison sees it: (text, date). A filled cell sets
# exactly one side; a blank cell sets neither. A date cell that held text the
# importer could not read as one date compares by that text.
Signature = tuple[str | None, dt.date | None]

MAX_TEXT_LENGTH = 500

# ASCII whitespace plus the non-breaking space (U+00A0), which planilla cells carry.
_SPACE = " \t\r\n\f\v\u00a0"
_SPACE_RUN = re.compile(r"[ \t\r\n\f\v\u00a0]+")
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Spec order of the 30-Sept-2026 layout. Identity fields (PMF, Rol, N Predio,
# ID_Predo_Unico) and the formula column "Hoy" are never editable.
_EDITABLE_NAMES: tuple[str, ...] = (
    "estado",
    "estado_resumido",
    "tipo_rechazo",
    "reingreso_tec",
    "reingreso_legal",
    "reingreso_recrep",
    "fecha_ingreso",
    "numero_ingreso",
    "fecha_90_dias",
    "fecha_ingreso_2",
    "numero_ingreso_2",
)


@dataclass(frozen=True, slots=True)
class EditableField:
    """One editable field: its contract name, its kind and its source header."""

    name: str
    kind: EditableKind
    label: str


def _editable(name: str) -> EditableField:
    spec = FIELD_BY_NAME[name]
    if spec.kind not in ("text", "date"):  # pragma: no cover - a contract change must break loudly
        raise RuntimeError(f"{name} is a {spec.kind} field; web edits support text and date only")
    return EditableField(name=name, kind=cast(EditableKind, spec.kind), label=spec.header)


EDITABLE_FIELDS: tuple[EditableField, ...] = tuple(_editable(name) for name in _EDITABLE_NAMES)
EDITABLE_BY_NAME: dict[str, EditableField] = {field.name: field for field in EDITABLE_FIELDS}


class OverrideValueError(ValueError):
    """A submitted value cannot be stored. The message is shown to the user."""


def normalize_text(value: str | None) -> str | None:
    """Trim and collapse whitespace (ASCII and NBSP); blank is None. Case is kept."""

    if value is None:
        return None
    collapsed = _SPACE_RUN.sub(" ", value.strip(_SPACE))
    return collapsed or None


def _parse_date(raw: str) -> dt.date:
    text = raw.strip(_SPACE)
    if not _ISO_DATE.match(text):
        raise OverrideValueError("La fecha debe tener el formato AAAA-MM-DD.")
    try:
        return dt.date.fromisoformat(text)
    except ValueError as exc:
        raise OverrideValueError("La fecha no existe en el calendario.") from exc


def parse_value(field: EditableField, raw: str | None) -> str | dt.date | None:
    """A submitted value as it will be stored. Blank means "clear the cell"."""

    if raw is None or not raw.strip(_SPACE):
        return None
    if field.kind == "date":
        return _parse_date(raw)
    if _CONTROL.search(raw):
        raise OverrideValueError("El texto contiene caracteres no permitidos.")
    text = normalize_text(raw)
    if text is not None and len(text) > MAX_TEXT_LENGTH:
        raise OverrideValueError(f"El texto no puede superar {MAX_TEXT_LENGTH} caracteres.")
    return text


def comparable(field: EditableField, raw: str | None) -> str | dt.date | None:
    """What an editor saw (``expected_value``), ready to compare with ``shown_value``."""

    if raw is None or not raw.strip(_SPACE):
        return None
    if field.kind == "date":
        return _parse_date(raw)
    return normalize_text(raw)


def shown_value(field: EditableField, value: Any) -> str | dt.date | None:
    """A value read from ``transelec_effective_row``, in ``comparable`` form."""

    if value is None:
        return None
    if field.kind == "date":
        return cast(dt.date, value)
    return normalize_text(str(value))


def value_signature(field: EditableField, value: str | dt.date | None) -> Signature:
    if field.kind == "date":
        return (None, cast("dt.date | None", value))
    return (normalize_text(cast("str | None", value)), None)


def cell_signature(
    field: EditableField, *, value: Any, text_dates: Mapping[str, Any] | None
) -> Signature:
    """A stored cell (value plus ``source_text_dates``) as a ``Signature``."""

    if field.kind == "date":
        if value is not None:
            return (None, cast(dt.date, value))
        evidence = (text_dates or {}).get(field.name) or {}
        return (normalize_text(evidence.get("raw")), None)
    return (normalize_text(None if value is None else str(value)), None)


def display(signature: Signature) -> str | None:
    """A signature as the API shows it: an ISO date, the text, or None."""

    text, date = signature
    return date.isoformat() if date is not None else text


def note_text(*, author: str, edited_on: dt.date, planilla: Signature) -> str:
    """The Excel note written next to an edited cell (spec §5)."""

    text, date = planilla
    before = date.strftime("%d-%m-%Y") if date is not None else (text or "(vacía)")
    return f"web · {author} · {edited_on:%d-%m-%Y} · antes: {before}"
