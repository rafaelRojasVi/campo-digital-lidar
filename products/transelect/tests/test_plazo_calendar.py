"""Smoke test of the real calendar the 90 días hábiles basis uses.

``plazo_conaf`` never reads a calendar itself: the router passes
``holidays.country_holidays("CL")``. These checks pin the dates fixed by law
in every year and the 2026 count observed for the locked ``holidays``
version. Task 1 of the plan compared that 2026 list with a Chilean
government source before the count was written here. A calendar update that
changes it must be re-checked the same way, not just re-numbered.
"""

from __future__ import annotations

import datetime as dt

import holidays


def test_chile_2026_has_the_holidays_fixed_by_law() -> None:
    chile = holidays.country_holidays("CL", years=2026)

    for day in (
        dt.date(2026, 1, 1),
        dt.date(2026, 5, 1),
        dt.date(2026, 5, 21),
        dt.date(2026, 9, 18),
        dt.date(2026, 9, 19),
        dt.date(2026, 12, 25),
    ):
        assert day in chile, day


def test_chile_2026_has_the_number_of_holidays_checked_against_the_government_list() -> None:
    assert len(holidays.country_holidays("CL", years=2026)) == 16


def test_an_ordinary_weekday_is_not_a_holiday() -> None:
    assert dt.date(2026, 9, 2) not in holidays.country_holidays("CL", years=2026)
