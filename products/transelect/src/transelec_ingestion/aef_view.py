"""The AEF tracking view over one filtered row set.

The 09-Sept-2026 workbook records five AEF tracking fields (``AEF``,
``Quien solicita``, ``Fecha solicitud``, ``Fecha corta``, ``Fecha termino``)
in ``Resumen``. In that workbook all 23 AEF values sit on the first source
row of 23 different PMF, and 19 of those PMF have further rows left blank:
the fields read as describing the PMF, written once on its first row.

So this view resolves each field per PMF (``resumen_layout.resolve_pmf_field``)
without rewriting any row:

- a PMF-level value is shown with the source row(s) that supplied it;
- a blank row is never given the value — row-level values stay exactly as
  the workbook has them, and row-level counts are still reported;
- two different non-blank values within one PMF are a *conflict*: no value
  is chosen, and every variant is listed with its rows for review.

Nothing here interprets what an AEF value means beyond its text: values are
grouped by their literal spelling only. A date column whose cell held text
that was not resolved to a date contributes that raw text, so it can only
agree with the same text, never with a date.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from transelec_ingestion.resumen_layout import (
    AEF_TRACKING_FIELDS,
    PmfFieldValue,
    chronology_flags,
    resolve_pmf_field,
)


@dataclass(frozen=True, slots=True)
class AefInputRow:
    source_row_number: int
    pmf: str
    aef: str | None
    quien_solicita: str | None
    fecha_solicitud: dt.date | None
    fecha_corta: dt.date | None
    fecha_termino: dt.date | None
    # Persisted ``source_text_dates``: field -> {"raw", "resolution", "parsed"}.
    text_dates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LabelCount:
    """A count under one literal value; ``label`` None means blank."""

    label: str | None
    count: int


@dataclass(frozen=True, slots=True)
class PmfAefRecord:
    """One PMF's tracking fields, resolved from all of its rows."""

    pmf: str
    total_rows: int
    rows_with_any_tracking: int
    rows_with_aef: int
    source_row_numbers: tuple[int, ...]
    fields: dict[str, PmfFieldValue]
    chronology_flags: tuple[str, ...]

    @property
    def has_conflict(self) -> bool:
        return any(value.status == "conflict" for value in self.fields.values())

    @property
    def has_tracking(self) -> bool:
        return self.rows_with_any_tracking > 0


@dataclass(frozen=True, slots=True)
class AefSummary:
    row_count: int
    pmf_count: int
    rows_with_any_tracking: int
    rows_with_aef: int
    rows_with_quien_solicita: int
    rows_with_fecha_solicitud: int
    rows_with_fecha_corta: int
    rows_with_fecha_termino: int
    pmf_with_tracking: int
    pmf_with_aef: int
    pmf_with_conflict: int
    pmf_conflicts_by_field: dict[str, int]
    rows_with_chronology_warning: int
    pmf_with_chronology_warning: int
    por_aef: tuple[LabelCount, ...]
    por_solicitante: tuple[LabelCount, ...]
    pmf_por_aef: tuple[LabelCount, ...]
    pmf_por_solicitante: tuple[LabelCount, ...]
    pmfs: tuple[PmfAefRecord, ...]
    tracked_row_numbers: tuple[int, ...]


def _present(value: object) -> bool:
    if value is None:
        return False
    return not (isinstance(value, str) and not value.strip())


def tracking_value(row: AefInputRow, name: str) -> Any:
    """The row's value for one tracking field, for display and comparison.

    A date column that is NULL because its cell held unresolved text yields
    that raw text, so the cell is neither lost nor mistaken for a blank.
    """

    value = getattr(row, name)
    if value is None and name in row.text_dates:
        evidence = row.text_dates[name]
        if evidence.get("parsed") is None:
            return evidence.get("raw")
    return value


def has_tracking(row: AefInputRow) -> bool:
    return any(_present(tracking_value(row, name)) for name in AEF_TRACKING_FIELDS)


def row_chronology_flags(row: AefInputRow) -> tuple[str, ...]:
    return chronology_flags(
        {
            "fecha_solicitud": row.fecha_solicitud,
            "fecha_corta": row.fecha_corta,
            "fecha_termino": row.fecha_termino,
        }
    )


def _label_counts(values: Sequence[str | None]) -> tuple[LabelCount, ...]:
    counts = Counter(value.strip() if _present(value) else None for value in values)  # type: ignore[union-attr]
    # Most frequent first; blank last; ties by Spanish-insensitive label.
    return tuple(
        LabelCount(label=label, count=count)
        for label, count in sorted(
            counts.items(),
            key=lambda item: (item[0] is None, -item[1], (item[0] or "").casefold()),
        )
    )


def build_pmf_record(pmf: str, pmf_rows: Sequence[AefInputRow]) -> PmfAefRecord:
    """Resolve one PMF's tracking fields from all of its rows."""

    fields = {
        name: resolve_pmf_field(
            (row.source_row_number, tracking_value(row, name)) for row in pmf_rows
        )
        for name in AEF_TRACKING_FIELDS
    }
    # Chronology over PMF-level dates: only resolved, agreed values count; a
    # conflicting or blank date is not an ordering error.
    return PmfAefRecord(
        pmf=pmf,
        total_rows=len(pmf_rows),
        rows_with_any_tracking=sum(1 for row in pmf_rows if has_tracking(row)),
        rows_with_aef=sum(1 for row in pmf_rows if _present(row.aef)),
        source_row_numbers=tuple(row.source_row_number for row in pmf_rows),
        fields=fields,
        chronology_flags=chronology_flags(
            {
                name: fields[name].value
                for name in ("fecha_solicitud", "fecha_corta", "fecha_termino")
                if fields[name].status == "value"
            }
        ),
    )


def _pmf_label_counts(records: Sequence[PmfAefRecord], name: str) -> tuple[LabelCount, ...]:
    # A conflicting PMF has no single label; it is counted in
    # pmf_conflicts_by_field instead of under any value.
    return _label_counts(
        [
            record.fields[name].value
            for record in records
            if record.fields[name].status != "conflict"
        ]
    )


def build_aef_summary(
    rows: Sequence[AefInputRow],
    *,
    pmf_rows: Sequence[AefInputRow] | None = None,
) -> AefSummary:
    """Summarize AEF tracking.

    ``rows`` is the filtered scope, in source order: row-level counts and the
    set of PMF shown come from it. ``pmf_rows`` holds every row of those PMF
    in the version (default: ``rows``), so a PMF-level value does not depend
    on which of the PMF's rows a filter happened to keep.
    """

    tracked = [row for row in rows if has_tracking(row)]

    in_scope = list(dict.fromkeys(row.pmf for row in rows))
    by_pmf: dict[str, list[AefInputRow]] = {pmf: [] for pmf in in_scope}
    for row in pmf_rows if pmf_rows is not None else rows:
        if row.pmf in by_pmf:
            by_pmf[row.pmf].append(row)

    records = [build_pmf_record(pmf, by_pmf[pmf]) for pmf in in_scope]
    tracked_records = [record for record in records if record.has_tracking]

    return AefSummary(
        row_count=len(rows),
        pmf_count=len(in_scope),
        rows_with_any_tracking=len(tracked),
        rows_with_aef=sum(1 for row in rows if _present(row.aef)),
        rows_with_quien_solicita=sum(1 for row in rows if _present(row.quien_solicita)),
        rows_with_fecha_solicitud=sum(
            1 for row in rows if _present(tracking_value(row, "fecha_solicitud"))
        ),
        rows_with_fecha_corta=sum(
            1 for row in rows if _present(tracking_value(row, "fecha_corta"))
        ),
        rows_with_fecha_termino=sum(
            1 for row in rows if _present(tracking_value(row, "fecha_termino"))
        ),
        pmf_with_tracking=len(tracked_records),
        pmf_with_aef=sum(1 for record in records if record.fields["aef"].status != "blank"),
        pmf_with_conflict=sum(1 for record in records if record.has_conflict),
        pmf_conflicts_by_field={
            name: sum(1 for record in records if record.fields[name].status == "conflict")
            for name in AEF_TRACKING_FIELDS
        },
        rows_with_chronology_warning=sum(1 for row in tracked if row_chronology_flags(row)),
        pmf_with_chronology_warning=sum(1 for record in records if record.chronology_flags),
        por_aef=_label_counts([row.aef for row in tracked]),
        por_solicitante=_label_counts([row.quien_solicita for row in tracked]),
        pmf_por_aef=_pmf_label_counts(tracked_records, "aef"),
        pmf_por_solicitante=_pmf_label_counts(tracked_records, "quien_solicita"),
        pmfs=tuple(tracked_records),
        tracked_row_numbers=tuple(row.source_row_number for row in tracked),
    )
