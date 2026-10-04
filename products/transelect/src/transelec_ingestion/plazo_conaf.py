"""``plazo_conaf_90_habiles_v1`` — CONAF's 90-business-day term, per PMF.

Design: docs/superpowers/specs/2026-10-04-transelec-plazo-90-habiles-design.md.

CONAF has 90 business days to resolve a plan (meeting of 2026-10-02). For
each PMF in scope this module finds the date the clock started from — the
most recent ingreso: ``Fecha de ingreso2`` when the PMF has one, otherwise
``Fecha de ingreso1`` — and counts 90 business days from it. Day 1 is the
first business day after that date (INFERENCE from Ley 19.880 art. 25, not
confirmed for CONAF's procedure). A business day is Monday to Friday and not
a holiday; which days are holidays is the caller's ``is_holiday`` (the
router passes Chile's national calendar from the ``holidays`` package), so
this module never reads a clock, a calendar or the network.

Dates are PMF facts, resolved over the PMF's rows with
``resumen_layout.resolve_pmf_field``: rows that disagree are a conflict and
nothing is chosen; a cell that held text the importer could not read as one
date (``source_text_dates``) is that text, never a date. When the most
recent ingreso exists but cannot be read, the older one is NOT used instead:
counting from it would show a deadline that is not CONAF's.

The planilla's own «90 dias» column is compared with the computed deadline
and never overwritten. The rule the dashboard used before this basis —
«90 dias» before today and «Estado resumido» not «Aprobado», row by row —
is kept beside it as ``vencimiento_columna_90_dias_legacy``.

Plans whose ``lifecycle_pmf_v1`` group is closed (approved, descartado,
desistido) get «no aplica». That set is passed in (``closed_pmfs``) by the
router, so this module does not import the lifecycle basis.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from transelec_ingestion.resumen_layout import (
    PmfFieldValue,
    resolve_pmf_field,
    value_or_unread_text,
)

PLAZO_BASIS: Final = "plazo_conaf_90_habiles_v1"
LEGACY_BASIS: Final = "vencimiento_columna_90_dias_legacy"
PLAZO_HABILES: Final = 90
POR_VENCER_UMBRAL: Final = 10

PlazoEstado = Literal[
    "vencido",
    "por_vencer",
    "en_plazo",
    "sin_fecha",
    "sin_fecha_texto",
    "conflicto",
    "no_aplica",
]
PLAZO_ESTADO_ORDER: tuple[PlazoEstado, ...] = (
    "vencido",
    "por_vencer",
    "en_plazo",
    "sin_fecha",
    "sin_fecha_texto",
    "conflicto",
    "no_aplica",
)
BaseField = Literal["fecha_ingreso_2", "fecha_ingreso"]
Cruce = Literal["coincide", "difiere", "sin_dato", "sin_calculo"]
IsHoliday = Callable[[dt.date], bool]

# Most recent ingreso first: the clock restarts at the reingreso.
_BASE_FIELDS: tuple[BaseField, ...] = ("fecha_ingreso_2", "fecha_ingreso")


@dataclass(frozen=True, slots=True)
class PlazoInputRow:
    source_row_number: int
    pmf: str
    estado_resumido: str | None
    fecha_ingreso: dt.date | None
    fecha_ingreso_2: dt.date | None
    fecha_90_dias: dt.date | None
    # Persisted ``source_text_dates``: field -> {"raw", "resolution", "parsed"}.
    text_dates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PmfPlazo:
    pmf: str
    # The PMF's first row in the filtered scope (the row the Estado table shows).
    source_row_number: int
    estado: PlazoEstado
    base_field: BaseField | None
    base_date: dt.date | None
    # Rows that supplied the base date, or that disagree / hold text.
    base_source_rows: tuple[int, ...]
    deadline: dt.date | None
    elapsed_business_days: int | None
    remaining_business_days: int | None
    planilla_90_dias: dt.date | None
    cruce: Cruce
    diferencia_dias: int | None
    legacy_vencido: bool


@dataclass(frozen=True, slots=True)
class PlazoSummary:
    basis: str
    legacy_basis: str
    observed_on: dt.date
    total_pmf_count: int
    estados: dict[PlazoEstado, int]
    cruce_difiere_count: int
    legacy_vencido_row_count: int
    pmfs: tuple[PmfPlazo, ...]


def is_business_day(day: dt.date, is_holiday: IsHoliday) -> bool:
    return day.weekday() < 5 and not is_holiday(day)


def add_business_days(start: dt.date, count: int, is_holiday: IsHoliday) -> dt.date:
    """The ``count``-th business day after ``start`` (``start`` itself never counts)."""

    if count < 1:
        raise ValueError("count must be at least 1")
    day = start
    found = 0
    while found < count:
        day += dt.timedelta(days=1)
        if is_business_day(day, is_holiday):
            found += 1
    return day


def business_days_between(start: dt.date, end: dt.date, is_holiday: IsHoliday) -> int:
    """Business days ``d`` with ``start < d <= end``; 0 when ``end <= start``."""

    count = 0
    day = start
    while day < end:
        day += dt.timedelta(days=1)
        if is_business_day(day, is_holiday):
            count += 1
    return count


def date_value(row: PlazoInputRow, name: str) -> dt.date | str | None:
    """A date field as the source has it: the date, else the raw text the
    importer could not read as one date, else None (blank)."""

    return value_or_unread_text(getattr(row, name), row.text_dates, name)


def _resolve(rows: Sequence[PlazoInputRow], name: str) -> PmfFieldValue:
    return resolve_pmf_field((row.source_row_number, date_value(row, name)) for row in rows)


def _base(
    rows: Sequence[PlazoInputRow],
) -> tuple[PlazoEstado | None, BaseField | None, dt.date | None, tuple[int, ...]]:
    """(blocking status, field used, base date, rows) for one PMF."""

    for name in _BASE_FIELDS:
        resolved = _resolve(rows, name)
        if resolved.status == "blank":
            continue
        if resolved.status == "conflict":
            return "conflicto", name, None, resolved.source_rows
        if isinstance(resolved.value, dt.date):
            return None, name, resolved.value, resolved.source_rows
        return "sin_fecha_texto", name, None, resolved.source_rows
    return "sin_fecha", None, None, ()


def _cruce(
    rows: Sequence[PlazoInputRow], deadline: dt.date | None
) -> tuple[Cruce, dt.date | None, int | None]:
    resolved = _resolve(rows, "fecha_90_dias")
    planilla = (
        resolved.value
        if resolved.status == "value" and isinstance(resolved.value, dt.date)
        else None
    )
    if deadline is None:
        return "sin_calculo", planilla, None
    if planilla is None:
        return "sin_dato", None, None
    difference = (planilla - deadline).days
    return ("coincide" if difference == 0 else "difiere"), planilla, difference


def is_legacy_vencido(row: PlazoInputRow, today: dt.date) -> bool:
    """``vencimiento_columna_90_dias_legacy``, as the dashboard applied it
    row by row before this basis: «Estado resumido» not «Aprobado» and the
    planilla's «90 dias» before today. Dates compare as calendar dates in
    Chile (the browser compared UTC midnight with an instant)."""

    if (row.estado_resumido or "").strip() == "Aprobado":
        return False
    return row.fecha_90_dias is not None and row.fecha_90_dias < today


def build_plazos(
    rows: Sequence[PlazoInputRow],
    *,
    pmf_rows: Sequence[PlazoInputRow] | None = None,
    today: dt.date,
    is_holiday: IsHoliday,
    closed_pmfs: frozenset[str],
) -> PlazoSummary:
    """One ``PmfPlazo`` per PMF in ``rows`` (the filtered scope).

    Dates are resolved over ``pmf_rows`` — every row of each PMF, not only
    the rows a filter kept — so a PMF's deadline never changes with an
    unrelated filter (the rule ``/aef`` already follows). The legacy flag
    stays row-level over ``rows``, as the dashboard applied it.
    """

    scope: dict[str, list[PlazoInputRow]] = {}
    for row in sorted(rows, key=lambda row: row.source_row_number):
        scope.setdefault(row.pmf, []).append(row)

    every: dict[str, list[PlazoInputRow]] = {}
    for row in pmf_rows if pmf_rows is not None else rows:
        every.setdefault(row.pmf, []).append(row)

    pmfs: list[PmfPlazo] = []
    for pmf, scoped in scope.items():
        facts = every.get(pmf) or scoped
        blocked, base_field, base_date, base_rows = _base(facts)
        deadline = (
            add_business_days(base_date, PLAZO_HABILES, is_holiday)
            if base_date is not None
            else None
        )
        cruce, planilla, difference = _cruce(facts, deadline)

        elapsed: int | None = None
        remaining: int | None = None
        estado: PlazoEstado
        if pmf in closed_pmfs:
            estado = "no_aplica"
        elif blocked is not None or base_date is None or deadline is None:
            estado = blocked or "sin_fecha"
        else:
            elapsed = business_days_between(base_date, today, is_holiday)
            remaining = PLAZO_HABILES - elapsed
            if today > deadline:
                estado = "vencido"
            elif remaining <= POR_VENCER_UMBRAL:
                estado = "por_vencer"
            else:
                estado = "en_plazo"

        pmfs.append(
            PmfPlazo(
                pmf=pmf,
                source_row_number=scoped[0].source_row_number,
                estado=estado,
                base_field=base_field,
                base_date=base_date,
                base_source_rows=base_rows,
                deadline=deadline,
                elapsed_business_days=elapsed,
                remaining_business_days=remaining,
                planilla_90_dias=planilla,
                cruce=cruce,
                diferencia_dias=difference,
                legacy_vencido=any(is_legacy_vencido(row, today) for row in scoped),
            )
        )

    estados: dict[PlazoEstado, int] = {estado: 0 for estado in PLAZO_ESTADO_ORDER}
    for entry in pmfs:
        estados[entry.estado] += 1

    return PlazoSummary(
        basis=PLAZO_BASIS,
        legacy_basis=LEGACY_BASIS,
        observed_on=today,
        total_pmf_count=len(pmfs),
        estados=estados,
        cruce_difiere_count=sum(1 for entry in pmfs if entry.cruce == "difiere"),
        legacy_vencido_row_count=sum(1 for row in rows if is_legacy_vencido(row, today)),
        pmfs=tuple(pmfs),
    )
