"""The plazo read without a database: Chile's date, and the path guard.

"Today" for CONAF's term is the calendar date in Chile, from the server's
clock — never the browser's, never the planilla's «Hoy». The read lives at
``/transelec/plazos`` (also mounted under ``/api``), which must never be a
dashboard page path: a page reload would otherwise answer JSON.
"""

from __future__ import annotations

import datetime as dt

from app.routers.transelec import chile_today, plazo_observed_on


def test_late_evening_in_chile_is_still_the_chilean_date() -> None:
    # 02:30 UTC on 3 Sept is 22:30 on 2 Sept in Chile (winter time, UTC-4).
    assert chile_today(dt.datetime(2026, 9, 3, 2, 30, tzinfo=dt.UTC)) == dt.date(2026, 9, 2)


def test_summer_time_is_applied() -> None:
    # 02:30 UTC on 31 Dec is 23:30 on 30 Dec in Chile (summer time, UTC-3).
    assert chile_today(dt.datetime(2026, 12, 31, 2, 30, tzinfo=dt.UTC)) == dt.date(2026, 12, 30)


def test_midday_is_the_same_date_in_both() -> None:
    assert chile_today(dt.datetime(2026, 9, 2, 15, 0, tzinfo=dt.UTC)) == dt.date(2026, 9, 2)


def test_the_dependency_answers_a_date() -> None:
    assert isinstance(plazo_observed_on(), dt.date)


def test_the_plazos_read_is_an_api_path_and_never_a_dashboard_page() -> None:
    from app.main import TRANSELEC_SPA_PAGE_PATHS, app

    # ``app.routes`` nests included routers; the OpenAPI schema lists every path.
    api_paths = set(app.openapi()["paths"])

    assert {"/transelec/plazos", "/api/transelec/plazos"} <= api_paths
    assert "transelec/plazos" not in TRANSELEC_SPA_PAGE_PATHS
