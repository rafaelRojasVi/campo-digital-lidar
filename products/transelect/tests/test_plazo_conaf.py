"""Unit tests for ``plazo_conaf_90_habiles_v1`` — CONAF's 90-business-day term.

Synthetic PMF codes and dates only. Every test injects its own calendar:
``no_holidays`` keeps the arithmetic readable (90 business days from a
weekday is exactly 18 weeks later), and ``TEST_HOLIDAYS`` is a small fixed set
of dates chosen to land on Fridays, Mondays and the new year. It is a test
calendar, not a claim about Chile's; the real calendar has its own smoke test.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from transelec_ingestion.plazo_conaf import (
    LEGACY_BASIS,
    PLAZO_BASIS,
    PLAZO_ESTADO_ORDER,
    PlazoInputRow,
    add_business_days,
    build_plazos,
    business_days_between,
    is_legacy_vencido,
)

TODAY = dt.date(2026, 9, 2)  # a Wednesday

TEST_HOLIDAYS = frozenset(
    {
        dt.date(2026, 6, 29),  # Monday
        dt.date(2026, 9, 18),  # Friday
        dt.date(2026, 9, 19),  # Saturday
        dt.date(2026, 12, 25),  # Friday
        dt.date(2027, 1, 1),  # Friday
    }
)


def no_holidays(day: dt.date) -> bool:
    return False


def holiday_in_test_calendar(day: dt.date) -> bool:
    return day in TEST_HOLIDAYS


def _row(
    *,
    source_row_number: int = 2,
    pmf: str = "PZ001",
    estado_resumido: str | None = "En tramite",
    fecha_ingreso: dt.date | None = None,
    fecha_ingreso_2: dt.date | None = None,
    fecha_90_dias: dt.date | None = None,
    text_dates: dict[str, dict[str, Any]] | None = None,
) -> PlazoInputRow:
    return PlazoInputRow(
        source_row_number=source_row_number,
        pmf=pmf,
        estado_resumido=estado_resumido,
        fecha_ingreso=fecha_ingreso,
        fecha_ingreso_2=fecha_ingreso_2,
        fecha_90_dias=fecha_90_dias,
        text_dates=text_dates or {},
    )


def _text(raw: str, resolution: str = "multiple_dates") -> dict[str, Any]:
    return {"raw": raw, "resolution": resolution, "parsed": None}


def _one(rows: list[PlazoInputRow], **kwargs: Any) -> Any:
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("is_holiday", no_holidays)
    kwargs.setdefault("closed_pmfs", frozenset())
    (entry,) = build_plazos(rows, **kwargs).pmfs
    return entry


# --- business-day arithmetic -------------------------------------------------


def test_day_one_is_the_first_business_day_after_the_ingreso() -> None:
    friday = dt.date(2026, 9, 4)
    assert add_business_days(friday, 1, no_holidays) == dt.date(2026, 9, 7)  # Monday


def test_an_ingreso_on_the_eve_of_a_holiday_starts_after_the_long_weekend() -> None:
    thursday = dt.date(2026, 9, 17)
    assert add_business_days(thursday, 1, holiday_in_test_calendar) == dt.date(2026, 9, 21)


def test_an_ingreso_on_a_holiday_starts_on_the_next_business_day() -> None:
    holiday = dt.date(2026, 9, 18)
    assert add_business_days(holiday, 1, holiday_in_test_calendar) == dt.date(2026, 9, 21)


def test_a_monday_holiday_is_skipped() -> None:
    friday = dt.date(2026, 6, 26)
    assert add_business_days(friday, 1, holiday_in_test_calendar) == dt.date(2026, 6, 30)  # Tuesday


def test_the_count_crosses_the_new_year_skipping_both_holidays() -> None:
    thursday = dt.date(2026, 12, 24)
    assert add_business_days(thursday, 5, holiday_in_test_calendar) == dt.date(2027, 1, 4)


def test_ninety_business_days_without_holidays_is_eighteen_weeks() -> None:
    monday = dt.date(2026, 3, 2)
    assert add_business_days(monday, 90, no_holidays) == dt.date(2026, 7, 6)


def test_holidays_push_the_deadline_by_one_business_day_each() -> None:
    monday = dt.date(2026, 6, 1)
    without = add_business_days(monday, 90, no_holidays)
    with_holidays = add_business_days(monday, 90, holiday_in_test_calendar)
    # 29 Jun and 18 Sep fall on weekdays inside the window; 19 Sep is a Saturday.
    assert business_days_between(without, with_holidays, no_holidays) == 2


def test_business_days_between_counts_the_end_not_the_start() -> None:
    friday, monday = dt.date(2026, 9, 4), dt.date(2026, 9, 7)
    assert business_days_between(friday, monday, no_holidays) == 1
    assert business_days_between(monday, monday, no_holidays) == 0
    assert business_days_between(monday, friday, no_holidays) == 0


def test_add_business_days_refuses_a_count_below_one() -> None:
    with pytest.raises(ValueError):
        add_business_days(TODAY, 0, no_holidays)


# --- status ------------------------------------------------------------------


def test_a_recent_ingreso_is_en_plazo_with_its_counts() -> None:
    entry = _one([_row(fecha_ingreso=dt.date(2026, 8, 3))])

    assert entry.estado == "en_plazo"
    assert entry.base_field == "fecha_ingreso"
    assert entry.base_date == dt.date(2026, 8, 3)
    assert entry.deadline == dt.date(2026, 12, 7)
    assert (entry.elapsed_business_days, entry.remaining_business_days) == (22, 68)


@pytest.mark.parametrize(
    ("ingreso", "estado", "remaining"),
    [
        (dt.date(2026, 5, 6), "por_vencer", 5),
        (dt.date(2026, 5, 13), "por_vencer", 10),
        (dt.date(2026, 5, 14), "en_plazo", 11),
    ],
)
def test_ten_or_fewer_business_days_left_is_por_vencer(
    ingreso: dt.date, estado: str, remaining: int
) -> None:
    entry = _one([_row(fecha_ingreso=ingreso)])

    assert (entry.estado, entry.remaining_business_days) == (estado, remaining)


def test_the_deadline_day_itself_is_not_yet_vencido() -> None:
    ingreso = dt.date(2026, 5, 6)
    deadline = dt.date(2026, 9, 9)

    on_the_day = _one([_row(fecha_ingreso=ingreso)], today=deadline)
    day_after = _one([_row(fecha_ingreso=ingreso)], today=deadline + dt.timedelta(days=1))

    assert on_the_day.deadline == deadline
    assert (on_the_day.estado, on_the_day.remaining_business_days) == ("por_vencer", 0)
    assert (day_after.estado, day_after.remaining_business_days) == ("vencido", -1)


def test_a_friday_deadline_observed_on_saturday_is_vencido_with_zero_remaining() -> None:
    ingreso = dt.date(2026, 5, 8)  # Friday: 90 business days later is a Friday
    deadline = dt.date(2026, 9, 11)
    saturday = dt.date(2026, 9, 12)

    entry = _one([_row(fecha_ingreso=ingreso)], today=saturday)

    assert entry.deadline == deadline
    assert (entry.estado, entry.remaining_business_days) == ("vencido", 0)


def test_an_old_ingreso_is_vencido_with_negative_days_left() -> None:
    entry = _one([_row(fecha_ingreso=dt.date(2026, 3, 2))])

    assert entry.estado == "vencido"
    assert entry.deadline == dt.date(2026, 7, 6)
    assert (entry.elapsed_business_days, entry.remaining_business_days) == (132, -42)


def test_an_ingreso_dated_after_today_counts_nothing_yet() -> None:
    entry = _one([_row(fecha_ingreso=dt.date(2026, 9, 10))])

    assert (entry.estado, entry.elapsed_business_days, entry.remaining_business_days) == (
        "en_plazo",
        0,
        90,
    )


def test_the_second_ingreso_restarts_the_clock() -> None:
    entry = _one([_row(fecha_ingreso=dt.date(2026, 1, 5), fecha_ingreso_2=dt.date(2026, 8, 3))])

    assert entry.base_field == "fecha_ingreso_2"
    assert entry.base_date == dt.date(2026, 8, 3)
    assert entry.estado == "en_plazo"


def test_an_unreadable_second_ingreso_never_falls_back_to_the_first() -> None:
    entry = _one(
        [
            _row(
                fecha_ingreso=dt.date(2026, 1, 5),
                text_dates={"fecha_ingreso_2": _text("20-12-2025 09-06-26")},
            )
        ]
    )

    assert (entry.estado, entry.base_field, entry.deadline) == (
        "sin_fecha_texto",
        "fecha_ingreso_2",
        None,
    )


@pytest.mark.parametrize("resolution", ["multiple_dates", "placeholder", "unrecognized"])
def test_text_in_the_ingreso_column_is_sin_fecha_texto(resolution: str) -> None:
    entry = _one([_row(text_dates={"fecha_ingreso": _text("-", resolution)})])

    assert (entry.estado, entry.base_field, entry.base_source_rows) == (
        "sin_fecha_texto",
        "fecha_ingreso",
        (2,),
    )


def test_a_parsed_text_date_is_a_date() -> None:
    entry = _one(
        [
            _row(
                fecha_ingreso=dt.date(2026, 8, 3),
                text_dates={
                    "fecha_ingreso": {
                        "raw": "3 de agosto de 2026",
                        "resolution": "parsed_spanish_long",
                        "parsed": "2026-08-03",
                    }
                },
            )
        ]
    )

    assert (entry.estado, entry.base_date) == ("en_plazo", dt.date(2026, 8, 3))


def test_rows_that_disagree_on_the_ingreso_are_a_conflict_and_nothing_is_chosen() -> None:
    entry = _one(
        [
            _row(source_row_number=2, fecha_ingreso=dt.date(2026, 5, 4)),
            _row(source_row_number=3, fecha_ingreso=dt.date(2026, 5, 11)),
            _row(source_row_number=4),
        ]
    )

    assert (entry.estado, entry.base_date, entry.base_source_rows) == ("conflicto", None, (2, 3))


def test_a_date_and_text_in_the_same_pmf_are_a_conflict() -> None:
    entry = _one(
        [
            _row(source_row_number=2, fecha_ingreso=dt.date(2026, 5, 4)),
            _row(source_row_number=3, text_dates={"fecha_ingreso": _text("-", "placeholder")}),
        ]
    )

    assert entry.estado == "conflicto"


def test_blank_rows_never_disagree_with_the_row_that_has_the_date() -> None:
    entry = _one(
        [
            _row(source_row_number=2),
            _row(source_row_number=3, fecha_ingreso=dt.date(2026, 8, 3)),
        ]
    )

    assert (entry.estado, entry.base_source_rows, entry.source_row_number) == ("en_plazo", (3,), 2)


def test_no_ingreso_date_at_all_is_sin_fecha() -> None:
    entry = _one([_row()])

    assert (entry.estado, entry.base_field, entry.deadline, entry.cruce) == (
        "sin_fecha",
        None,
        None,
        "sin_calculo",
    )


def test_a_closed_plan_is_no_aplica_but_keeps_its_deadline_for_the_cross_check() -> None:
    entry = _one(
        [_row(fecha_ingreso=dt.date(2026, 3, 2), fecha_90_dias=dt.date(2026, 7, 6))],
        closed_pmfs=frozenset({"PZ001"}),
    )

    assert entry.estado == "no_aplica"
    assert entry.deadline == dt.date(2026, 7, 6)
    assert (entry.elapsed_business_days, entry.remaining_business_days) == (None, None)
    assert entry.cruce == "coincide"


def test_a_closed_plan_without_a_date_is_still_no_aplica() -> None:
    entry = _one([_row()], closed_pmfs=frozenset({"PZ001"}))

    assert entry.estado == "no_aplica"


def test_dates_come_from_every_row_of_the_pmf_not_only_the_filtered_ones() -> None:
    scoped = _row(source_row_number=3)
    every = [_row(source_row_number=2, fecha_ingreso=dt.date(2026, 8, 3)), scoped]

    entry = _one([scoped], pmf_rows=every)

    assert (entry.estado, entry.base_date, entry.source_row_number) == (
        "en_plazo",
        dt.date(2026, 8, 3),
        3,
    )


# --- cross-check against the planilla's «90 dias» ----------------------------


def test_the_planilla_90_dias_that_matches_the_deadline_coincide() -> None:
    entry = _one([_row(fecha_ingreso=dt.date(2026, 8, 3), fecha_90_dias=dt.date(2026, 12, 7))])

    assert (entry.cruce, entry.planilla_90_dias, entry.diferencia_dias) == (
        "coincide",
        dt.date(2026, 12, 7),
        0,
    )


def test_a_different_planilla_90_dias_differs_by_calendar_days() -> None:
    entry = _one([_row(fecha_ingreso=dt.date(2026, 8, 3), fecha_90_dias=dt.date(2026, 11, 1))])

    assert (entry.cruce, entry.diferencia_dias) == ("difiere", -36)


@pytest.mark.parametrize(
    "row_kwargs",
    [
        {},
        {"text_dates": {"fecha_90_dias": _text("15-11-2026 02-12-2026")}},
    ],
)
def test_a_blank_or_unreadable_planilla_90_dias_has_no_data(row_kwargs: dict[str, Any]) -> None:
    entry = _one([_row(fecha_ingreso=dt.date(2026, 8, 3), **row_kwargs)])

    assert (entry.cruce, entry.planilla_90_dias, entry.diferencia_dias) == ("sin_dato", None, None)


# --- legacy basis: the dashboard's former row-level rule ---------------------
# Same cases as products/transelect/dashboard/src/lib/overdue.test.ts.


@pytest.mark.parametrize(
    ("estado_resumido", "noventa", "today", "expected"),
    [
        ("En tramite", dt.date(2026, 6, 1), TODAY, True),
        ("Aprobado", dt.date(2020, 1, 1), TODAY, False),
        ("Pendiente", None, TODAY, False),
        ("Pendiente", dt.date(2026, 12, 31), TODAY, False),
        ("Pendiente", dt.date(2026, 8, 27), dt.date(2026, 8, 26), False),
        ("Pendiente", dt.date(2026, 8, 27), TODAY, True),
        # «before today»: the 90 dias date itself is not yet past.
        ("Pendiente", TODAY, TODAY, False),
        ("  Aprobado ", dt.date(2020, 1, 1), TODAY, False),
    ],
)
def test_the_legacy_rule_matches_the_dashboards_former_predicate(
    estado_resumido: str, noventa: dt.date | None, today: dt.date, expected: bool
) -> None:
    row = _row(estado_resumido=estado_resumido, fecha_90_dias=noventa)

    assert is_legacy_vencido(row, today) is expected


def test_the_legacy_rule_stays_row_level_and_is_counted_in_rows() -> None:
    summary = build_plazos(
        [
            _row(source_row_number=2, fecha_90_dias=dt.date(2026, 6, 1)),
            _row(source_row_number=3, fecha_90_dias=dt.date(2026, 6, 1)),
            _row(source_row_number=4, pmf="PZ002", fecha_90_dias=dt.date(2026, 12, 1)),
        ],
        today=TODAY,
        is_holiday=no_holidays,
        closed_pmfs=frozenset(),
    )

    assert summary.legacy_vencido_row_count == 2
    assert [entry.legacy_vencido for entry in summary.pmfs] == [True, False]


# --- summary -----------------------------------------------------------------


def test_the_summary_counts_every_status_in_order_and_keeps_source_order() -> None:
    summary = build_plazos(
        [
            _row(source_row_number=9, pmf="PZ003", fecha_ingreso=dt.date(2026, 3, 2)),
            _row(source_row_number=2, pmf="PZ001", fecha_ingreso=dt.date(2026, 8, 3)),
            _row(source_row_number=5, pmf="PZ002"),
            _row(
                source_row_number=7,
                pmf="PZ004",
                fecha_ingreso=dt.date(2026, 8, 3),
                fecha_90_dias=dt.date(2026, 11, 1),
            ),
        ],
        today=TODAY,
        is_holiday=no_holidays,
        closed_pmfs=frozenset({"PZ004"}),
    )

    assert (summary.basis, summary.legacy_basis) == (PLAZO_BASIS, LEGACY_BASIS)
    assert summary.basis == "plazo_conaf_90_habiles_v1"
    assert summary.observed_on == TODAY
    assert summary.total_pmf_count == 4
    assert tuple(summary.estados) == PLAZO_ESTADO_ORDER
    assert summary.estados == {
        "vencido": 1,
        "por_vencer": 0,
        "en_plazo": 1,
        "sin_fecha": 1,
        "sin_fecha_texto": 0,
        "conflicto": 0,
        "no_aplica": 1,
    }
    assert summary.cruce_difiere_count == 1
    assert [entry.pmf for entry in summary.pmfs] == ["PZ001", "PZ002", "PZ004", "PZ003"]


def test_no_rows_is_an_empty_summary() -> None:
    summary = build_plazos([], today=TODAY, is_holiday=no_holidays, closed_pmfs=frozenset())

    assert summary.total_pmf_count == 0
    assert summary.pmfs == ()
    assert set(summary.estados.values()) == {0}


def test_holidays_inside_the_window_are_not_elapsed_business_days() -> None:
    thursday = dt.date(2026, 9, 17)
    monday = dt.date(2026, 9, 21)  # the 18th and 19th are holidays in the test calendar
    assert business_days_between(thursday, monday, holiday_in_test_calendar) == 1

    entry = _one([_row(fecha_ingreso=thursday)], today=monday, is_holiday=holiday_in_test_calendar)

    assert (entry.estado, entry.elapsed_business_days, entry.remaining_business_days) == (
        "en_plazo",
        1,
        89,
    )


def test_a_deadline_pushed_by_holidays_is_observed_with_zero_remaining() -> None:
    entry = _one(
        [_row(fecha_ingreso=dt.date(2026, 6, 1))],
        today=dt.date(2026, 10, 7),
        is_holiday=holiday_in_test_calendar,
    )

    assert entry.deadline == dt.date(2026, 10, 7)
    assert (entry.estado, entry.elapsed_business_days, entry.remaining_business_days) == (
        "por_vencer",
        90,
        0,
    )


def test_an_ingreso_too_late_for_a_deadline_is_sin_fecha_texto_not_an_error() -> None:
    entry = _one([_row(fecha_ingreso=dt.date(9999, 12, 30))])

    assert entry.estado == "sin_fecha_texto"
    assert (entry.base_date, entry.deadline) == (None, None)
    assert entry.base_field == "fecha_ingreso"
    assert (entry.elapsed_business_days, entry.remaining_business_days) == (None, None)
    assert entry.cruce == "sin_calculo"
