# Transelec 90 días hábiles (plazo CONAF) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For each PMF, compute CONAF's 90-business-day deadline from its
most recent ingreso, using Chile's national holidays and the server's date in
Chile. Show it as a «Plazo CONAF» column in Estado, a drawer block and a
Calidad cross-check against the planilla's «90 dias» column. This replaces
the browser-only overdue panel.

**Architecture:**
- **Pure module.** `transelec_ingestion/plazo_conaf.py` does all the date
  arithmetic. It takes an injected `is_holiday` and a `closed_pmfs` set, and
  never reads a clock, a calendar or the lifecycle module.
- **Router.** A new read, `GET /transelec/plazos`, supplies the rest:
  - today in `America/Santiago`, through an overridable dependency;
  - a fresh `holidays.country_holidays("CL")` per request;
  - `_closed_pmfs(rows)` from the Estado branch;
  - rows only through `_fetch_filtered_rows`.
- **Dashboard.** It joins `/plazos` to the Estado table by PMF through
  `EstadoTable`'s `extraColumns`, and deletes `OverduePanel` and
  `lib/overdue.ts`. The old rule survives server-side as
  `vencimiento_columna_90_dias_legacy`.

**Tech Stack:**
- Python 3.12, FastAPI, SQLAlchemy `text()`, Pydantic v2, pytest, `holidays`
  (PyPI, MIT, ≥ 0.105).
- React 19 + TypeScript, vitest, Playwright with stubs.

**Spec:**
`/home/rafael/dev/freelance/campo-digital/worktrees/campo-digital-transelec-specs/docs/superpowers/specs/2026-10-04-transelec-plazo-90-habiles-design.md`.

It is on branch `docs/transelec-estado-plazo-web-specs`, not on `main`, so
read it from that path. This plan is **stacked** on the Estado plan,
`docs/superpowers/plans/2026-10-04-transelec-estado-lifecycle.md` (same
directory), and uses that plan's names exactly.

## Global Constraints

**Rules from the spec:**
- **Business days.** Monday to Friday, excluding Chilean national holidays,
  taken from `holidays.country_holidays("CL")`. Regional holidays are not
  counted.
- **Clock start.** The clock starts at `fecha_ingreso_2` when the PMF has
  one, otherwise at `fecha_ingreso`. If the most recent ingreso cannot be
  read, it is **never** replaced by the older one.
- **Day 1 and the deadline.** Day 1 is the first business day after the
  ingreso date, and the deadline is the 90th business day.
- **Status, first match wins:**
  1. `no_aplica` when the plan is closed, even without a date;
  2. otherwise `sin_fecha`, `sin_fecha_texto` or `conflicto`;
  3. otherwise `vencido` when today is after the deadline;
  4. otherwise `por_vencer` when remaining ≤ 10;
  5. otherwise `en_plazo`.
- **"Today".** It is the server's date in `America/Santiago`, never the
  browser's date and never the planilla's «Hoy».
- **«90 dias».** The planilla's column is compared with the computed deadline
  (`coincide`, `difiere` with `diferencia_dias` = planilla minus computed in
  calendar days, `sin_dato`, or `sin_calculo` when nothing was computed). It
  is never overwritten.
- **Legacy rule.** `vencimiento_columna_90_dias_legacy`: *Estado resumido*
  is not «Aprobado» and «90 dias» is **before** today. It is row-level over
  the filtered rows.
- **Ids.** Basis `plazo_conaf_90_habiles_v1`. The API returns the calendar
  as `{"source": "holidays", "country": "CL", "version": <installed version>}`.
- **Dependency.** `holidays>=0.105,<1` goes in the `transelec` extra. Among
  the three parallel PRs, only this one touches `pyproject.toml` and
  `uv.lock`.

**Interfaces this plan consumes from `feat/transelec-estado`:**
- `app.routers.transelec._closed_pmfs(rows: Sequence[Row[Any]]) -> frozenset[str]`.
- `EstadoTable({ rows, selectedRow, onOpen, extraColumns? })`.
- `EstadoColumn = { key, header, render(row: LifecycleRow) }` from
  `lib/estadoColumns.tsx`.
- `EstadoPage`, `getLifecycle`, `LifecycleRow`, `TranselecLifecycle`.
- `makeLifecycle` / `makeLifecycleRow` (factories), and `lifecycleBody`
  (e2e stub).
- `RowDetailDrawer`'s `lifecycle` prop.

**Paths:**
- **No collision with a page.** The read is `GET /transelec/plazos`
  (browsers call `/api/transelec/plazos`). `transelec/plazos` must never be a
  dashboard page path. `app.main` mounts the router at both `/transelec` and
  `/api/transelec`, and `TRANSELEC_SPA_PAGE_PATHS` equals `ROUTES`. The
  Estado plan's generic guard
  (`test_no_transelec_api_path_is_also_a_dashboard_page_path`) and this
  plan's specific one (Task 3) pin it.
- **Rows.** Every Transelec read loads rows through `_fetch_filtered_rows`.
  The web-edits PR changes the relation underneath, so web edits of the
  ingreso dates reach this basis with no change here.

**Workbook and data rules:**
- Follow `.claude/skills/transelec-workbook/SKILL.md`. Use synthetic fixtures
  only. Never open, copy, import or publish a real planilla. No names,
  predios, roles or other business values in code, tests, commits or PRs.

**Style:**
- **Python:** ruff (line 100; E F I UP B SIM), `ruff format`, mypy.
- **Dashboard:** oxlint (`react/only-export-components`: keep non-component
  exports in `src/lib/`), `tsc -b`.
- **Quotes:** most dashboard files use single quotes and no semicolons;
  `src/components/RowDetailDrawer.test.tsx` uses double quotes and
  semicolons.

**Shared test resources (all three worktrees share them):**
- **Database.** The test DB is on `127.0.0.1:5433`. Never run `make
  persistence-check`, `make migration-check` or `make db-test-reset` while
  another worktree may be running integration tests. Never run integration
  tests from two worktrees at the same time.
- **Playwright.** It serves on port 5299. Never run `npm run test:e2e` from
  two worktrees at the same time.

**Commits:**
- End every commit message with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Do not push or open a PR until Rafael asks.

## Review Focus

1. **The most recent ingreso exists but cannot be read.** For example, the
   «Fecha de ingreso2» cell holds two dates. The plan must show «sin fecha
   legible» and must **not** quietly count from «Fecha de ingreso1»; that
   would show a deadline months too early.
   - Task 2: `test_an_unreadable_second_ingreso_never_falls_back_to_the_first`.
2. **The day after a Friday deadline is a Saturday.** The PMF is `vencido`
   with 0 business days remaining. The column must read «venció el …», not
   «hace 0 días hábiles». On the deadline day itself it must read «vence
   hoy», not «quedan 0».
   - Task 2: `test_the_deadline_day_itself_is_not_yet_vencido`.
   - Task 4: the `plazoText` cases in `lib/plazo.test.ts`.
3. **A filter keeps only a PMF's row that has no date.** For example, the
   Sector filter keeps the second row while the date is on the first. The
   PMF must keep its real deadline, because dates are PMF facts as in
   `/aef`, and must not show «sin fecha».
   - Task 2: `test_dates_come_from_every_row_of_the_pmf_not_only_the_filtered_ones`.
   - Task 3: `test_plazos_follows_the_filters_but_dates_stay_pmf_facts`.
4. **An approved plan with no ingreso date reads «No aplica».** It must not
   show «Sin fecha», and it must not count as a data problem.
   - Task 2: `test_a_closed_plan_without_a_date_is_still_no_aplica`.
5. **The `/plazos` read fails while `/lifecycle` succeeds.** The Estado table
   and its groups must still render, with «—» in the plazo column and one
   banner. The page must not go blank, and the «vencidos» toggle must stay
   disabled.
   - Task 6: `EstadoPage.test.tsx` `keeps the Estado table when the plazo read fails`.

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` (modify) | `holidays` in the `transelec` extra |
| `products/transelect/tests/test_plazo_calendar.py` (create) | smoke test of the real CL calendar |
| `products/transelect/src/transelec_ingestion/plazo_conaf.py` (create) | `plazo_conaf_90_habiles_v1` + legacy basis, pure |
| `products/transelect/tests/test_plazo_conaf.py` (create) | its unit tests |
| `apps/api/app/routers/transelec.py` (modify) | `chile_today`, `plazo_observed_on`, `GET /transelec/plazos` |
| `apps/api/tests/test_transelec_plazos_routes.py` (create) | Chile date + path guard (no DB) |
| `apps/api/integration_tests/test_transelec_reads_router.py` (modify) | `/plazos` in the RBAC / 404 route lists |
| `apps/api/integration_tests/test_transelec_router.py` (modify) | `/plazos` against real PostgreSQL |
| `.../src/api.ts` (modify) | `PlazoEstado`, `PlazoCruce`, `PlazoPmf`, `TranselecPlazos`, `getPlazos` |
| `.../src/lib/plazo.ts` (create) + `plazo.test.ts` | Spanish wording, `indexPlazos`, `plazoDetail` |
| `.../src/lib/rules.ts` (modify) | «Cómo se calcula» for both bases |
| `.../src/components/PlazoCell.tsx` (create) | the table cell |
| `.../src/lib/plazoColumn.tsx` (create) | the `EstadoColumn` for `extraColumns` |
| `.../src/components/PlazoDrawerSection.tsx` (create) | the drawer block |
| `.../src/components/RowDetailDrawer.tsx` (modify) + test | `plazo` prop |
| `.../src/pages/EstadoPage.tsx` (rewrite) + test | column, «vencidos» toggle, drawer wiring |
| `.../src/components/OverduePanel.tsx`, `src/lib/overdue.ts`, `src/lib/overdue.test.ts` (delete) | replaced by the server basis |
| `.../src/App.test.tsx` (modify) | mock `getPlazos` |
| `.../src/components/PlazoQualityPanel.tsx` (create) + test | Calidad block |
| `.../src/pages/CalidadPage.tsx` (modify) | loads `/plazos`, shows the block |
| `.../src/test/factories.ts` (modify) | `makePlazoPmf`, `makePlazos` |
| `.../tests/e2e/stubs.ts`, `tests/e2e/dashboard.spec.ts` (modify) | e2e |
| `products/transelect/dashboard/README.md`, `products/transelect/docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md` (modify) | docs |

`...` = `products/transelect/dashboard`.

**Names other work can rely on:**
- **Python:** `transelec_ingestion.plazo_conaf` exports:
  - constants `PLAZO_BASIS`, `LEGACY_BASIS`, `PLAZO_HABILES` (90),
    `POR_VENCER_UMBRAL` (10), `PLAZO_ESTADO_ORDER`;
  - types `PlazoEstado`, `BaseField`, `Cruce`, `IsHoliday`;
  - dataclasses `PlazoInputRow`, `PmfPlazo`, `PlazoSummary`;
  - functions `is_business_day`, `add_business_days`,
    `business_days_between`, `date_value`, `is_legacy_vencido`,
    `build_plazos`.
- **Router:** `chile_today(now=None) -> date`, `plazo_observed_on() -> date`
  (a FastAPI dependency), `_to_plazo_input_row`, `_plazo_pmf_view`,
  `TranselecPlazosResponse`.
- **Dashboard:**
  - `getPlazos`, `TranselecPlazos`, `PlazoPmf`, `PlazoEstado`, `PlazoCruce`;
  - `lib/plazo.ts`: `PLAZO_ESTADO_LABELS`, `PLAZO_ESTADO_PILL`, `plazoText`,
    `plazoBaseText`, `cruceText`, `indexPlazos`, `plazoDetail`,
    `PlazoDetail`;
  - `plazoColumn(byPmf, loading)`;
  - components `PlazoCell`, `PlazoDrawerSection`, `PlazoQualityPanel`.

---

### Task 0: Stacked worktree and baseline

**Files:** none.

- [ ] **Step 1: Check that the Estado branch is ready to stack on**

Run from `/home/rafael/dev/freelance/campo-digital`:

```bash
git -C campo-digital-platform fetch origin
git -C campo-digital-platform log --oneline -12 feat/transelec-estado
git -C campo-digital-platform show feat/transelec-estado:products/transelect/src/transelec_ingestion/lifecycle_view.py | head -5
git -C campo-digital-platform show feat/transelec-estado:products/transelect/dashboard/src/lib/estadoColumns.tsx | head -5
```

Expected: the Estado commits through its Task 7 ("Calidad lists the PMFs the
Estado rule could not place") are present, and both files print.

If the local branch does not exist but `origin/feat/transelec-estado` does,
use `origin/feat/transelec-estado` in Step 2. If neither exists, stop. This
plan cannot start before the Estado plan's Tasks 1–7 are committed.

- [ ] **Step 2: Create the stacked worktree**

```bash
git -C campo-digital-platform worktree add ../worktrees/campo-digital-transelec-plazo -b feat/transelec-plazo-90-habiles feat/transelec-estado
cd worktrees/campo-digital-transelec-plazo
```

Every later path is relative to this worktree.

- [ ] **Step 3: Install and run the baseline**

```bash
make setup
cd products/transelect/dashboard && npm ci && cd -
uv run pytest products/transelect/tests apps/api/tests -q
cd products/transelect/dashboard && npm test && npx tsc -b && npm run lint && cd -
```

Expected: everything passes. If not, stop and report; do not fix unrelated
failures.

- [ ] **Step 4: Prepare the test database (shell used for integration tests)**

```bash
make db-test-up
export APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test \
  POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api
uv run alembic upgrade head
```

Expected: the migration ends at `0011`. This plan adds no migration.

If it fails with "Can't locate revision", another worktree migrated the
shared container past `0011` (the web-edits plan adds `0012`). Run
`make db-test-reset` and then `uv run alembic upgrade head`, but only after
confirming no other worktree is running integration tests. Otherwise, wait.

---

### Task 1: `holidays` dependency, the two plan checks, calendar smoke test

**Files:**
- Modify: `pyproject.toml` (the `transelec` extra, lines 25-27)
- Modify: `uv.lock` (generated)
- Create: `products/transelect/tests/test_plazo_calendar.py`

**Interfaces:**
- Produces: `import holidays` is available wherever the `transelec` extra is
  installed: `make setup`, the Dockerfile's
  `uv sync --frozen --no-dev --extra api --extra transelec`, and
  `render.yaml`.

- [ ] **Step 1: Write the failing smoke test**

Create `products/transelect/tests/test_plazo_calendar.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest products/transelect/tests/test_plazo_calendar.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'holidays'`.

- [ ] **Step 3: Add the dependency**

In `pyproject.toml`, change the `transelec` extra to:

```toml
transelec = [
  "python-calamine>=0.8,<0.9",
  "holidays>=0.105,<1",
]
```

Then:

```bash
uv lock
git diff --stat uv.lock
git diff uv.lock | grep '^+name = ' || true
uv sync --all-extras --dev
```

Expected:
- `uv.lock` gains `holidays`, plus `python-dateutil` only if it was not
  already locked.
- No other package changes version. If `uv lock` moved other packages, run
  `git checkout uv.lock` and lock again with `uv lock --upgrade-package holidays`.

- [ ] **Step 4: Run the smoke test**

Run: `uv run pytest products/transelect/tests/test_plazo_calendar.py -v`
Expected: 3 PASS. The count 16 was observed for `holidays` 0.105 on
2026-10-04. If the locked version differs and the count changed, do not
edit the number yet; Step 5 decides it.

- [ ] **Step 5: Plan check: compare the 2026 list with a government source**

1. **Print the package's list:**

   ```bash
   uv run python -c "import holidays; [print(d, d.strftime('%a'), n) for d, n in sorted(holidays.country_holidays('CL', years=2026).items())]"
   ```

2. **Find a Chilean government page** listing the 2026 national holidays.
   Search with WebSearch `feriados legales 2026 Chile site:gob.cl`. If that
   finds nothing usable, try `site:dt.gob.cl` (Dirección del Trabajo) and
   then `site:bcn.cl` (Biblioteca del Congreso). Read the page with WebFetch.

   **Do not** use a non-government site or a list from memory. If no
   government page is reachable, stop and report.

3. **Compare date by date.** Count every date the government lists as a
   national holiday ("feriado legal"), including those that fall on a
   weekend. Record two things for the PR body (Task 8): the URL, and either
   "identical" or the exact differences.

4. **If they differ:**
   - **The package is missing a national holiday:** stop and report. Do not
     patch the calendar in code.
   - **They agree but the count is not 16:** set the count in
     `test_chile_2026_has_the_number_of_holidays_checked_against_the_government_list`
     to the government's count, and say so in the PR.

- [ ] **Step 6: Plan check: `America/Santiago` inside the runtime image**

Make sure Docker is running, then from the worktree root:

```bash
docker build -t campo-digital-transelec:plazo-check .
docker run --rm --entrypoint /app/.venv/bin/python campo-digital-transelec:plazo-check -c \
  "import datetime as dt; from zoneinfo import ZoneInfo; import holidays; print(dt.datetime.now(ZoneInfo('America/Santiago')).isoformat(), holidays.__version__)"
```

Expected: it prints a Chilean timestamp (offset `-03:00` or `-04:00`) and the
locked `holidays` version.

If it fails with `ZoneInfoNotFoundError`:
1. Add `"tzdata>=2024.1",` to the `transelec` extra.
2. Run `uv lock` and `uv sync --all-extras --dev`.
3. Rebuild and re-run this step.

Record which case happened for the PR body. Remove the image afterwards:
`docker rmi campo-digital-transelec:plazo-check`.

- [ ] **Step 7: Dependency audit**

Run: `make dependency-audit`
Expected: exits 0. If it flags the new package, stop and report.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock products/transelect/tests/test_plazo_calendar.py
git commit -m "build(transelec): add the holidays calendar to the transelec extra" -m "Chile's national holidays for the 90 días hábiles basis; no network at runtime." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `plazo_conaf_90_habiles_v1` pure module

**Files:**
- Create: `products/transelect/src/transelec_ingestion/plazo_conaf.py`
- Test: `products/transelect/tests/test_plazo_conaf.py`

**Interfaces:**
- Consumes: `transelec_ingestion.resumen_layout.resolve_pmf_field(entries: Iterable[tuple[int, Any]]) -> PmfFieldValue` and `PmfFieldValue` (`status` in `"value" | "blank" | "conflict"`, `value`, `source_rows`, `variants`). It treats raw text as different from any date.
- Produces: every Python name listed under "Names other work can rely on".

- [ ] **Step 1: Write the failing tests**

Create `products/transelect/tests/test_plazo_conaf.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest products/transelect/tests/test_plazo_conaf.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'transelec_ingestion.plazo_conaf'`.

- [ ] **Step 3: Write the module**

Create `products/transelect/src/transelec_ingestion/plazo_conaf.py`:

```python
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

from transelec_ingestion.resumen_layout import PmfFieldValue, resolve_pmf_field

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

    value: dt.date | None = getattr(row, name)
    if value is None and name in row.text_dates:
        evidence = row.text_dates[name]
        if evidence.get("parsed") is None:
            raw = evidence.get("raw")
            return raw if isinstance(raw, str) else None
    return value


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest products/transelect/tests/test_plazo_conaf.py -v`
Expected: 44 PASS.

The test expectations are hand-checkable with `no_holidays`: 90 business
days from a weekday is exactly 18 weeks later. For example, Mon 2026-03-02
gives Mon 2026-07-06, and Wed 2026-05-06 gives Wed 2026-09-09.

- [ ] **Step 5: Lint, format, type-check**

Run: `uv run ruff format products/transelect/src/transelec_ingestion/plazo_conaf.py products/transelect/tests/test_plazo_conaf.py && uv run ruff check products/transelect && uv run mypy products/transelect/src/transelec_ingestion/plazo_conaf.py && uv run pytest products/transelect/tests/test_plazo_conaf.py -q`
Expected: no findings; 44 PASS.

- [ ] **Step 6: Commit**

```bash
git add products/transelect/src/transelec_ingestion/plazo_conaf.py products/transelect/tests/test_plazo_conaf.py
git commit -m "feat(transelec): plazo_conaf_90_habiles_v1, CONAF's 90 business days per PMF" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `GET /transelec/plazos`

**Files:**
- Modify: `apps/api/app/routers/transelec.py`. The imports are at lines 25-81. The new section goes directly **above** the `# GET /owner-status — TR-FUNC-013` banner, i.e. right after the Estado plan's `get_lifecycle`.
- Create: `apps/api/tests/test_transelec_plazos_routes.py`
- Modify: `apps/api/integration_tests/test_transelec_reads_router.py` (`READ_ROUTES` and the 404 list)
- Modify: `apps/api/integration_tests/test_transelec_router.py` (append at the end)

**Interfaces:**
- Consumes: from Task 2, every `plazo_conaf` name. From the Estado branch, `_closed_pmfs`. From the router, `_fetch_filtered_rows`, `_require_active_import_id`, `TranselecFilters`, `_transelec_filters`, `require_transelec_grant`, `_iso` and `Action`.
- Produces: `chile_today(now: dt.datetime | None = None) -> dt.date` and `plazo_observed_on() -> dt.date`. Integration tests override the latter with `app.dependency_overrides`. Also `TranselecPlazosResponse`, with this JSON:

```json
{
  "basis": "plazo_conaf_90_habiles_v1",
  "legacy_basis": "vencimiento_columna_90_dias_legacy",
  "observed_on": "2026-09-02",
  "calendar": {"source": "holidays", "country": "CL", "version": "0.105"},
  "plazo_habiles": 90,
  "por_vencer_umbral": 10,
  "total_pmf_count": 0,
  "estados": {"vencido": 0, "por_vencer": 0, "en_plazo": 0, "sin_fecha": 0,
              "sin_fecha_texto": 0, "conflicto": 0, "no_aplica": 0},
  "cruce_difiere_count": 0,
  "legacy_vencido_row_count": 0,
  "pmfs": [{"pmf": "…", "source_row_number": 2, "estado": "en_plazo",
            "base_field": "fecha_ingreso", "base_date": "2026-08-03", "base_source_rows": [2],
            "deadline": "2026-12-10", "elapsed_business_days": 22, "remaining_business_days": 68,
            "planilla_90_dias": "2026-12-10", "cruce": "coincide", "diferencia_dias": 0,
            "legacy_vencido": false}]
}
```

- [ ] **Step 1: Write the failing unit tests (no database)**

Create `apps/api/tests/test_transelec_plazos_routes.py`:

```python
"""The plazo read without a database: Chile's date, and the path guard.

"Today" for CONAF's term is the calendar date in Chile, from the server's
clock — never the browser's, never the planilla's «Hoy». The read lives at
``/transelec/plazos`` (also mounted under ``/api``), which must never be a
dashboard page path: a page reload would otherwise answer JSON.
"""

from __future__ import annotations

import datetime as dt

from app.routers.transelec import chile_today, plazo_observed_on
from fastapi.routing import APIRoute


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

    api_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert {"/transelec/plazos", "/api/transelec/plazos"} <= api_paths
    assert "transelec/plazos" not in TRANSELEC_SPA_PAGE_PATHS
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest apps/api/tests/test_transelec_plazos_routes.py -v`
Expected: collection error `ImportError: cannot import name 'chile_today'`.

- [ ] **Step 3: Add the imports to the router**

In `apps/api/app/routers/transelec.py`:

(a) In the standard-library block, after `from typing import Annotated, Any, Literal`, add:

```python
from zoneinfo import ZoneInfo
```

(b) Make `import holidays` the first line of the third-party block, directly
above `from fastapi import APIRouter, …`.

(c) After the `from transelec_ingestion.pending_view import …` line, add:

```python
from transelec_ingestion.plazo_conaf import (
    LEGACY_BASIS,
    PLAZO_BASIS,
    PLAZO_HABILES,
    POR_VENCER_UMBRAL,
    BaseField,
    Cruce,
    PlazoEstado,
    PlazoInputRow,
    PmfPlazo,
    build_plazos,
)
```

Run `uv run ruff check --fix apps/api/app/routers/transelec.py` afterwards
so the import order matches the project's isort settings.

- [ ] **Step 4: Add the route section**

Insert directly above the banner block that reads
`# GET /owner-status — TR-FUNC-013` (after the Estado plan's `get_lifecycle`):

```python
# ---------------------------------------------------------------------------
# GET /plazos — plazo_conaf_90_habiles_v1, CONAF's 90 business days
#
# Not a dashboard page path (see the /lifecycle note above): the «Plazo
# CONAF» column lives on the /transelec/estado page.
# ---------------------------------------------------------------------------

# CONAF's calendar: business days and "today" are Chilean.
_CONAF_TIMEZONE = "America/Santiago"


def chile_today(now: dt.datetime | None = None) -> dt.date:
    """The calendar date in Chile at ``now`` (default: the server's clock)."""

    instant = now if now is not None else dt.datetime.now(dt.UTC)
    return instant.astimezone(ZoneInfo(_CONAF_TIMEZONE)).date()


def plazo_observed_on() -> dt.date:
    """Dependency: today in Chile. Integration tests override it to fix the date."""

    return chile_today()


class PlazoEstadoCountsView(BaseModel):
    vencido: int
    por_vencer: int
    en_plazo: int
    sin_fecha: int
    sin_fecha_texto: int
    conflicto: int
    no_aplica: int


class PlazoCalendarView(BaseModel):
    source: Literal["holidays"]
    country: Literal["CL"]
    version: str


class PlazoPmfView(BaseModel):
    pmf: str
    source_row_number: int
    estado: PlazoEstado
    base_field: BaseField | None
    base_date: str | None
    base_source_rows: list[int]
    deadline: str | None
    elapsed_business_days: int | None
    remaining_business_days: int | None
    planilla_90_dias: str | None
    cruce: Cruce
    diferencia_dias: int | None
    legacy_vencido: bool


class TranselecPlazosResponse(BaseModel):
    basis: Literal["plazo_conaf_90_habiles_v1"]
    legacy_basis: Literal["vencimiento_columna_90_dias_legacy"]
    observed_on: str
    calendar: PlazoCalendarView
    plazo_habiles: int
    por_vencer_umbral: int
    total_pmf_count: int
    estados: PlazoEstadoCountsView
    cruce_difiere_count: int
    legacy_vencido_row_count: int
    pmfs: list[PlazoPmfView]


def _to_plazo_input_row(row: Row[Any]) -> PlazoInputRow:
    return PlazoInputRow(
        source_row_number=row.source_row_number,
        pmf=row.pmf,
        estado_resumido=row.estado_resumido,
        fecha_ingreso=row.fecha_ingreso,
        fecha_ingreso_2=row.fecha_ingreso_2,
        fecha_90_dias=row.fecha_90_dias,
        text_dates=row.source_text_dates or {},
    )


def _plazo_pmf_view(entry: PmfPlazo) -> PlazoPmfView:
    return PlazoPmfView(
        pmf=entry.pmf,
        source_row_number=entry.source_row_number,
        estado=entry.estado,
        base_field=entry.base_field,
        base_date=_iso(entry.base_date),
        base_source_rows=list(entry.base_source_rows),
        deadline=_iso(entry.deadline),
        elapsed_business_days=entry.elapsed_business_days,
        remaining_business_days=entry.remaining_business_days,
        planilla_90_dias=_iso(entry.planilla_90_dias),
        cruce=entry.cruce,
        diferencia_dias=entry.diferencia_dias,
        legacy_vencido=entry.legacy_vencido,
    )


@router.get(
    "/plazos",
    response_model=TranselecPlazosResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_plazos(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
    observed_on: Annotated[dt.date, Depends(plazo_observed_on)],
) -> TranselecPlazosResponse:
    """Each PMF of the filtered scope, once, with CONAF's 90-business-day term.

    Rows come only from ``_fetch_filtered_rows``. Dates are PMF facts read
    from every row of each PMF, as ``/aef`` does, so a deadline never moves
    with an unrelated filter. «No aplica» uses the same filtered rows as the
    Estado table beside it (``_closed_pmfs``).
    """

    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)
    pmf_rows = (
        _fetch_filtered_rows(connection, import_id=import_id, filters=TranselecFilters())
        if filters != TranselecFilters()
        else rows
    )
    # One calendar per request: ``holidays`` fills years in lazily, and a
    # shared instance would be mutated from several worker threads at once.
    calendar = holidays.country_holidays("CL")
    summary = build_plazos(
        [_to_plazo_input_row(row) for row in rows],
        pmf_rows=[_to_plazo_input_row(row) for row in pmf_rows],
        today=observed_on,
        is_holiday=lambda day: day in calendar,
        closed_pmfs=_closed_pmfs(rows),
    )

    return TranselecPlazosResponse(
        basis=PLAZO_BASIS,
        legacy_basis=LEGACY_BASIS,
        observed_on=summary.observed_on.isoformat(),
        calendar=PlazoCalendarView(source="holidays", country="CL", version=holidays.__version__),
        plazo_habiles=PLAZO_HABILES,
        por_vencer_umbral=POR_VENCER_UMBRAL,
        total_pmf_count=summary.total_pmf_count,
        estados=PlazoEstadoCountsView(**summary.estados),
        cruce_difiere_count=summary.cruce_difiere_count,
        legacy_vencido_row_count=summary.legacy_vencido_row_count,
        pmfs=[_plazo_pmf_view(entry) for entry in summary.pmfs],
    )
```

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_transelec_plazos_routes.py apps/api/tests/test_transelec_lifecycle_routes.py apps/api/tests/test_dashboard_static.py -v`
Expected: all PASS. The Estado plan's generic path guard still finds no
overlap.

- [ ] **Step 6: Add `/plazos` to the shared read-route lists**

In `apps/api/integration_tests/test_transelec_reads_router.py`:

(a) In `READ_ROUTES`, add `"/transelec/plazos",` after `"/transelec/lifecycle",`.

(b) In `test_data_dependent_routes_404_with_a_clear_message_when_nothing_is_published`,
add `"/transelec/plazos",` after `"/transelec/lifecycle",`.

These lists already run the RBAC, viewer, forestry-only-forbidden, no-CSRF
and nothing-published tests for every route in them.

- [ ] **Step 7: Write the failing data tests**

Append to `apps/api/integration_tests/test_transelec_router.py`. That file
already has `_current_row`, `_CURRENT_HEADERS`, `_workbook_bytes` (which
writes `dt.date` cells as real Excel dates), `_upload_and_validate`, `_login`
and `_SAME_ORIGIN`.

```python
# ---------------------------------------------------------------------------
# GET /plazos — plazo_conaf_90_habiles_v1 against real PostgreSQL
# ---------------------------------------------------------------------------

# Synthetic: one PMF per plazo status, read on Wed 2026-09-02 with Chile's
# real calendar (holidays inside the windows: 18 Sep, 12 Oct, 8 Dec 2026).
#
#  row  PMF    dates                                   → expected
#   2   PL001  ingreso 2026-08-03, 90 dias 2026-12-10  → en_plazo, coincide
#   3   PL002  ingreso1 2026-01-05, ingreso2 2026-07-01 → base ingreso2
#   4   PL003  ingreso 2026-03-02, 90 dias 2026-07-01  → vencido, difiere -9
#   5   PL004  Aprobado / Aprobado, ingreso 2026-03-02 → no_aplica
#   6   PL005  ingreso "20-12-2024 09-06-26" (two dates) → sin_fecha_texto
#   7-8 PL006  ingreso 2026-05-04 / 2026-05-11          → conflicto
#   9   PL007  no dates                                → sin_fecha
#  10   PL008  ingreso 2026-04-30                      → por_vencer, 5 left
#  11   PL009  ingreso 2026-08-03, Sector Sur
#  12   PL009  no date, Sector Norte                   → the PMF keeps row 11's date
_PLAZO_TODAY = dt.date(2026, 9, 2)


def _plazo_row(pmf: str, number: int, **overrides: Any) -> list[Any]:
    values: dict[str, Any] = {
        "pmf": pmf,
        "numero_predio": str(number),
        "id_predio_unico": f"{pmf}-{number}",
        "estado": "En evaluacion",
        "estado_resumido": "En tramite",
        "numero_ingreso": f"ING-{pmf}",
    }
    values.update(overrides)
    return _current_row(**values)


def _plazo_workbook(tmp_path: Path) -> bytes:
    return _workbook_bytes(
        tmp_path,
        "plazos.xlsx",
        [
            _plazo_row(
                "PL001", 1, fecha_ingreso=dt.date(2026, 8, 3), fecha_90_dias=dt.date(2026, 12, 10)
            ),
            _plazo_row(
                "PL002", 2, fecha_ingreso=dt.date(2026, 1, 5), fecha_ingreso_2=dt.date(2026, 7, 1)
            ),
            _plazo_row(
                "PL003",
                3,
                estado="Rechazado",
                fecha_ingreso=dt.date(2026, 3, 2),
                fecha_90_dias=dt.date(2026, 7, 1),
            ),
            _plazo_row(
                "PL004",
                4,
                estado="Aprobado",
                estado_resumido="Aprobado",
                fecha_ingreso=dt.date(2026, 3, 2),
            ),
            _plazo_row("PL005", 5, fecha_ingreso="20-12-2024 09-06-26"),
            _plazo_row("PL006", 6, fecha_ingreso=dt.date(2026, 5, 4)),
            _plazo_row("PL006", 7, fecha_ingreso=dt.date(2026, 5, 11)),
            _plazo_row("PL007", 8),
            _plazo_row("PL008", 9, fecha_ingreso=dt.date(2026, 4, 30)),
            _plazo_row("PL009", 10, sector="Sector Sur", fecha_ingreso=dt.date(2026, 8, 3)),
            _plazo_row("PL009", 11, sector="Sector Norte"),
        ],
        headers=_CURRENT_HEADERS,
    )


def _publish_plazo_fixture(client: TestClient, engine: Engine, tmp_path: Path) -> None:
    _login(client, "dev-admin")
    _, validated = _upload_and_validate(client, engine, _plazo_workbook(tmp_path))
    assert validated.status_code == 200, validated.text
    # PL005's two-date cell is a warning the operator acknowledges.
    published = client.post(
        f"/transelec/imports/{validated.json()['import_id']}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )
    assert published.status_code == 200, published.text
    app.dependency_overrides[plazo_observed_on] = lambda: _PLAZO_TODAY


def test_plazos_counts_ninety_chilean_business_days_from_the_latest_ingreso(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _publish_plazo_fixture(client, integration_engine, tmp_path)

    body = client.get("/transelec/plazos").json()

    assert (body["basis"], body["legacy_basis"]) == (
        "plazo_conaf_90_habiles_v1",
        "vencimiento_columna_90_dias_legacy",
    )
    assert body["observed_on"] == "2026-09-02"
    assert (body["calendar"]["source"], body["calendar"]["country"]) == ("holidays", "CL")
    assert body["calendar"]["version"]
    assert (body["plazo_habiles"], body["por_vencer_umbral"]) == (90, 10)
    assert body["total_pmf_count"] == 9
    assert body["estados"] == {
        "vencido": 1,
        "por_vencer": 1,
        "en_plazo": 3,
        "sin_fecha": 1,
        "sin_fecha_texto": 1,
        "conflicto": 1,
        "no_aplica": 1,
    }
    assert [entry["pmf"] for entry in body["pmfs"]] == [f"PL00{n}" for n in range(1, 10)]

    by_pmf = {entry["pmf"]: entry for entry in body["pmfs"]}
    pl001 = by_pmf["PL001"]
    assert (pl001["estado"], pl001["base_field"], pl001["deadline"]) == (
        "en_plazo",
        "fecha_ingreso",
        "2026-12-10",
    )
    assert (pl001["elapsed_business_days"], pl001["remaining_business_days"]) == (22, 68)
    assert (pl001["cruce"], pl001["diferencia_dias"]) == ("coincide", 0)

    assert (by_pmf["PL002"]["base_field"], by_pmf["PL002"]["base_date"]) == (
        "fecha_ingreso_2",
        "2026-07-01",
    )
    assert by_pmf["PL002"]["deadline"] == "2026-11-09"

    pl003 = by_pmf["PL003"]
    assert (pl003["estado"], pl003["deadline"], pl003["remaining_business_days"]) == (
        "vencido",
        "2026-07-10",
        -37,
    )
    assert (pl003["cruce"], pl003["planilla_90_dias"], pl003["diferencia_dias"]) == (
        "difiere",
        "2026-07-01",
        -9,
    )
    assert pl003["legacy_vencido"] is True

    assert by_pmf["PL004"]["estado"] == "no_aplica"
    assert by_pmf["PL004"]["remaining_business_days"] is None
    assert by_pmf["PL005"]["estado"] == "sin_fecha_texto"
    assert (by_pmf["PL006"]["estado"], by_pmf["PL006"]["base_source_rows"]) == (
        "conflicto",
        [7, 8],
    )
    assert by_pmf["PL007"]["estado"] == "sin_fecha"
    assert (by_pmf["PL008"]["estado"], by_pmf["PL008"]["remaining_business_days"]) == (
        "por_vencer",
        5,
    )
    assert by_pmf["PL008"]["deadline"] == "2026-09-09"

    assert body["cruce_difiere_count"] == 1
    assert body["legacy_vencido_row_count"] == 1


def test_plazos_follows_the_filters_but_dates_stay_pmf_facts(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _publish_plazo_fixture(client, integration_engine, tmp_path)

    narrowed = client.get("/transelec/plazos", params={"sector": "Sector Norte"}).json()
    assert [entry["pmf"] for entry in narrowed["pmfs"]] == ["PL009"]
    (entry,) = narrowed["pmfs"]
    # The filter kept row 12, which has no date; the PMF's date is on row 11.
    assert (entry["estado"], entry["base_date"], entry["base_source_rows"]) == (
        "en_plazo",
        "2026-08-03",
        [11],
    )
    assert entry["source_row_number"] == 12

    closed = client.get("/transelec/plazos", params={"estado_resumido": "Aprobado"}).json()
    assert [entry["pmf"] for entry in closed["pmfs"]] == ["PL004"]
    assert closed["estados"]["no_aplica"] == 1
```

Add `from app.routers.transelec import plazo_observed_on` to the
`app.*` imports of that file, after `from app.object_store import LocalObjectStore`.

`client` already calls `app.dependency_overrides.clear()` on teardown, so
the date override never leaks into another test.

- [ ] **Step 8: Run the integration tests**

In the shell with the Task 0 Step 4 exports, and with no other worktree
running integration tests:

Run: `uv run pytest -q apps/api/integration_tests/test_transelec_router.py apps/api/integration_tests/test_transelec_reads_router.py`
Expected: all PASS, including the parametrized RBAC, viewer, no-CSRF and
404 cases for `/transelec/plazos`.

If a deadline assertion is off by one or more business days, print
`holidays.country_holidays("CL", years=2026)` for the locked version and
compare it with the list from Task 1 Step 5. The expected dates were computed
with `holidays` 0.105 (holidays inside the windows: 18 Sep, 12 Oct, 8 Dec
2026; 29 Jun and 16 Jul for PL003 and PL008). Do not change an expectation
without that comparison.

- [ ] **Step 9: Lint and type-check**

Run: `uv run ruff format apps/api/app/routers/transelec.py apps/api/tests/test_transelec_plazos_routes.py apps/api/integration_tests/test_transelec_router.py apps/api/integration_tests/test_transelec_reads_router.py && uv run ruff check apps/api && uv run mypy apps/api/app/routers/transelec.py apps/api/tests/test_transelec_plazos_routes.py`
Expected: no findings.

- [ ] **Step 10: Commit**

```bash
git add apps/api/app/routers/transelec.py apps/api/tests/test_transelec_plazos_routes.py apps/api/integration_tests/test_transelec_router.py apps/api/integration_tests/test_transelec_reads_router.py
git commit -m "feat(transelec): GET /transelec/plazos counts CONAF's 90 business days in Chile's calendar" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Dashboard data layer (types, wording, rules, factories, e2e stub)

**Files:**
- Modify: `products/transelect/dashboard/src/api.ts`. Types go after the Estado plan's `TranselecLifecycle` interface; the function goes after `getLifecycle`.
- Create: `products/transelect/dashboard/src/lib/plazo.ts`, `src/lib/plazo.test.ts`
- Modify: `products/transelect/dashboard/src/lib/rules.ts` (two `RULES` entries)
- Modify: `products/transelect/dashboard/src/test/factories.ts`
- Modify: `products/transelect/dashboard/tests/e2e/stubs.ts`

**Interfaces:**
- Consumes: the JSON shape from Task 3.
- Produces:
  - `PlazoEstado`, `PlazoCruce`, `PlazoPmf`, `TranselecPlazos` and `getPlazos(filters)` (api.ts);
  - `PLAZO_ESTADO_LABELS`, `PLAZO_ESTADO_PILL`, `plazoText`, `plazoBaseText`, `cruceText`, `indexPlazos`, `plazoDetail` and `PlazoDetail` (lib/plazo.ts);
  - `makePlazoPmf` and `makePlazos` (factories), and `plazosBody` (stubs).

Commands run from `products/transelect/dashboard`.

- [ ] **Step 1: Add the API types and read**

In `src/api.ts`, after the `TranselecLifecycle` interface, add:

```ts
/** `plazo_conaf_90_habiles_v1` — see transelec_ingestion/plazo_conaf.py. */
export type PlazoEstado =
  | 'vencido'
  | 'por_vencer'
  | 'en_plazo'
  | 'sin_fecha'
  | 'sin_fecha_texto'
  | 'conflicto'
  | 'no_aplica'

export type PlazoCruce = 'coincide' | 'difiere' | 'sin_dato' | 'sin_calculo'

/** One PMF's CONAF term. Dates are ISO `YYYY-MM-DD`; days are business days. */
export interface PlazoPmf {
  pmf: string
  /** The PMF's first row in the filtered scope (the Estado table's row). */
  source_row_number: number
  estado: PlazoEstado
  base_field: 'fecha_ingreso_2' | 'fecha_ingreso' | null
  base_date: string | null
  base_source_rows: number[]
  deadline: string | null
  elapsed_business_days: number | null
  remaining_business_days: number | null
  planilla_90_dias: string | null
  cruce: PlazoCruce
  diferencia_dias: number | null
  legacy_vencido: boolean
}

export interface TranselecPlazos {
  basis: string
  legacy_basis: string
  /** The server's date in Chile (`America/Santiago`). */
  observed_on: string
  calendar: { source: string; country: string; version: string }
  plazo_habiles: number
  por_vencer_umbral: number
  total_pmf_count: number
  estados: Record<PlazoEstado, number>
  cruce_difiere_count: number
  legacy_vencido_row_count: number
  pmfs: PlazoPmf[]
}
```

After `getLifecycle`, add:

```ts
/** `GET /transelec/plazos` — CONAF's 90 business days per PMF. */
export function getPlazos(filters: TranselecFilterState): Promise<ApiResult<TranselecPlazos>> {
  return request<TranselecPlazos>(withParams('/api/transelec/plazos', filterParams(filters)))
}
```

- [ ] **Step 2: Add the factories**

In `src/test/factories.ts`, extend the type import with `PlazoPmf` and
`TranselecPlazos`. Then add after `makeLifecycle`:

```ts
export function makePlazoPmf(overrides: Partial<PlazoPmf> = {}): PlazoPmf {
  return {
    pmf: 'MP001',
    source_row_number: 2,
    estado: 'en_plazo',
    base_field: 'fecha_ingreso',
    base_date: '2026-08-03',
    base_source_rows: [2],
    deadline: '2026-12-10',
    elapsed_business_days: 22,
    remaining_business_days: 68,
    planilla_90_dias: '2026-12-10',
    cruce: 'coincide',
    diferencia_dias: 0,
    legacy_vencido: false,
    ...overrides,
  }
}

/** One entry per `makeLifecycle()` row (MP001 row 2 … MP004 row 7). */
export function makePlazos(overrides: Partial<TranselecPlazos> = {}): TranselecPlazos {
  return {
    basis: 'plazo_conaf_90_habiles_v1',
    legacy_basis: 'vencimiento_columna_90_dias_legacy',
    observed_on: '2026-09-02',
    calendar: { source: 'holidays', country: 'CL', version: '0.105' },
    plazo_habiles: 90,
    por_vencer_umbral: 10,
    total_pmf_count: 4,
    estados: {
      vencido: 1,
      por_vencer: 0,
      en_plazo: 1,
      sin_fecha: 0,
      sin_fecha_texto: 0,
      conflicto: 1,
      no_aplica: 1,
    },
    cruce_difiere_count: 1,
    legacy_vencido_row_count: 3,
    pmfs: [
      makePlazoPmf({
        pmf: 'MP001',
        source_row_number: 2,
        estado: 'no_aplica',
        base_date: '2026-03-04',
        deadline: '2026-07-14',
        elapsed_business_days: null,
        remaining_business_days: null,
        planilla_90_dias: '2026-07-14',
      }),
      makePlazoPmf({
        pmf: 'MP002',
        source_row_number: 3,
        estado: 'vencido',
        base_date: '2026-03-04',
        base_source_rows: [3],
        deadline: '2026-07-14',
        elapsed_business_days: 125,
        remaining_business_days: -35,
        planilla_90_dias: '2026-06-02',
        cruce: 'difiere',
        diferencia_dias: -42,
        legacy_vencido: true,
      }),
      makePlazoPmf({
        pmf: 'MP003',
        source_row_number: 5,
        base_field: 'fecha_ingreso_2',
        base_source_rows: [5],
      }),
      makePlazoPmf({
        pmf: 'MP004',
        source_row_number: 7,
        estado: 'conflicto',
        base_date: null,
        base_source_rows: [7, 8],
        deadline: null,
        elapsed_business_days: null,
        remaining_business_days: null,
        planilla_90_dias: '2026-06-02',
        cruce: 'sin_calculo',
        diferencia_dias: null,
        legacy_vencido: true,
      }),
    ],
    ...overrides,
  }
}
```

- [ ] **Step 3: Write the failing wording tests**

Create `src/lib/plazo.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { cruceText, indexPlazos, plazoBaseText, plazoDetail, plazoText } from './plazo'
import { ruleFor } from './rules'
import { makePlazoPmf, makePlazos } from '../test/factories'

describe('plazo_conaf_90_habiles_v1 wording', () => {
  it('says when the term ends and how many business days are left', () => {
    expect(plazoText(makePlazoPmf())).toBe('vence el 10-12-2026 · quedan 68 días hábiles')
    expect(plazoText(makePlazoPmf({ estado: 'por_vencer', remaining_business_days: 1 }))).toBe(
      'vence el 10-12-2026 · queda 1 día hábil',
    )
  })

  it('says «vence hoy» on the deadline day, never «quedan 0»', () => {
    expect(plazoText(makePlazoPmf({ estado: 'por_vencer', remaining_business_days: 0 }))).toBe(
      'vence hoy (10-12-2026)',
    )
  })

  it('counts business days since a passed deadline, and only when there are some', () => {
    const vencido = makePlazoPmf({ estado: 'vencido', deadline: '2026-07-10' })
    expect(plazoText({ ...vencido, remaining_business_days: -37 })).toBe(
      'venció el 10-07-2026 · hace 37 días hábiles',
    )
    // A Friday deadline seen on Saturday: past, with no business day elapsed since.
    expect(plazoText({ ...vencido, remaining_business_days: 0 })).toBe('venció el 10-07-2026')
  })

  it('names why there is no count', () => {
    expect(plazoText(makePlazoPmf({ estado: 'no_aplica' }))).toBe('Proceso cerrado')
    expect(plazoText(makePlazoPmf({ estado: 'sin_fecha', base_field: null }))).toBe(
      'Sin fecha de ingreso',
    )
    expect(
      plazoText(makePlazoPmf({ estado: 'sin_fecha_texto', base_field: 'fecha_ingreso_2' })),
    ).toBe('«Fecha de ingreso2» no se pudo leer como una fecha')
    expect(plazoText(makePlazoPmf({ estado: 'conflicto' }))).toBe(
      'Las filas del PMF tienen fechas de ingreso distintas',
    )
  })

  it('names the ingreso the clock started from', () => {
    expect(plazoBaseText(makePlazoPmf({ base_field: 'fecha_ingreso_2' }))).toBe(
      'Fecha de ingreso2 · 03-08-2026',
    )
    expect(plazoBaseText(makePlazoPmf({ base_field: null, base_date: null }))).toBe('—')
  })

  it('compares the planilla «90 dias» with the computed deadline', () => {
    expect(cruceText(makePlazoPmf())).toBe('Coincide con el cálculo')
    expect(
      cruceText(
        makePlazoPmf({ cruce: 'difiere', planilla_90_dias: '2026-07-01', diferencia_dias: -9 }),
      ),
    ).toBe('Difiere: la planilla dice 01-07-2026, 9 días antes del cálculo')
    expect(
      cruceText(
        makePlazoPmf({ cruce: 'difiere', planilla_90_dias: '2026-12-11', diferencia_dias: 1 }),
      ),
    ).toBe('Difiere: la planilla dice 11-12-2026, 1 día después del cálculo')
    expect(cruceText(makePlazoPmf({ cruce: 'sin_dato', planilla_90_dias: null }))).toBe(
      'La planilla no trae una fecha «90 dias» legible',
    )
    expect(cruceText(makePlazoPmf({ cruce: 'sin_calculo' }))).toBe('Sin cálculo con qué comparar')
  })

  it('indexes the plazos by PMF and builds the drawer detail', () => {
    const data = makePlazos()
    expect(indexPlazos(data).get('MP002')?.estado).toBe('vencido')
    expect(indexPlazos(null).size).toBe(0)
    expect(plazoDetail(data, 'MP002')).toEqual({
      entry: data.pmfs[1],
      observedOn: '2026-09-02',
      calendarVersion: '0.105',
    })
    expect(plazoDetail(data, 'NOPE')).toBeNull()
    expect(plazoDetail(null, 'MP002')).toBeNull()
  })

  it('explains both rules in «Cómo se calcula», provisional', () => {
    const rule = ruleFor('plazo_conaf_90_habiles_v1')
    expect(rule?.sourceColumns).toEqual([
      'PMF',
      'Fecha de ingreso2',
      'Fecha de ingreso1',
      '90 dias',
      'Estado resumido',
    ])
    expect(rule?.steps.join(' ')).toContain('provisional')
    expect(ruleFor('vencimiento_columna_90_dias_legacy')?.sourceColumns).toEqual([
      'Estado resumido',
      '90 dias',
    ])
  })
})
```

- [ ] **Step 4: Run it to verify it fails**

Run: `npm test -- src/lib/plazo.test.ts`
Expected: FAIL. `Failed to resolve import "./plazo"`.

- [ ] **Step 5: Write `src/lib/plazo.ts`**

```ts
/**
 * `plazo_conaf_90_habiles_v1` in Spanish, for the «Estado» table, the drawer
 * and Calidad.
 *
 * The count is the server's (`transelec_ingestion/plazo_conaf.py`): 90
 * business days — Monday to Friday without Chile's national holidays — from
 * the most recent ingreso, with «today» the server's date in Chile. This
 * module only words it. Provisional until Campo Digital answers when CONAF's
 * term starts and whether it pauses (spec 2026-10-04, open questions).
 */
import type { PlazoEstado, PlazoPmf, TranselecPlazos } from '../api'
import { formatDate, formatInteger } from '../format'

export const PLAZO_ESTADO_LABELS: Record<PlazoEstado, string> = {
  vencido: 'Vencido',
  por_vencer: 'Por vencer',
  en_plazo: 'En plazo',
  sin_fecha: 'Sin fecha',
  sin_fecha_texto: 'Sin fecha legible',
  conflicto: 'Fechas distintas',
  no_aplica: 'No aplica',
}

/** The existing `.pill-*` tones. */
export const PLAZO_ESTADO_PILL: Record<PlazoEstado, string> = {
  vencido: 'pill-pendiente',
  por_vencer: 'pill-en-tramite',
  en_plazo: 'pill-aprobado',
  sin_fecha: 'pill-otro',
  sin_fecha_texto: 'pill-otro',
  conflicto: 'pill-otro',
  no_aplica: 'pill-tachado',
}

const BASE_FIELD_LABELS: Record<NonNullable<PlazoPmf['base_field']>, string> = {
  fecha_ingreso_2: 'Fecha de ingreso2',
  fecha_ingreso: 'Fecha de ingreso1',
}

function habiles(count: number): string {
  return `${formatInteger(count)} ${count === 1 ? 'día hábil' : 'días hábiles'}`
}

function calendarDays(count: number): string {
  return `${formatInteger(count)} ${count === 1 ? 'día' : 'días'}`
}

/** «vence el …», «vence hoy», «venció el …», or why there is no count. */
export function plazoText(plazo: PlazoPmf): string {
  switch (plazo.estado) {
    case 'no_aplica':
      return 'Proceso cerrado'
    case 'sin_fecha':
      return 'Sin fecha de ingreso'
    case 'sin_fecha_texto':
      return `«${BASE_FIELD_LABELS[plazo.base_field ?? 'fecha_ingreso']}» no se pudo leer como una fecha`
    case 'conflicto':
      return 'Las filas del PMF tienen fechas de ingreso distintas'
    case 'vencido': {
      const since = -(plazo.remaining_business_days ?? 0)
      const ended = `venció el ${formatDate(plazo.deadline)}`
      return since > 0 ? `${ended} · hace ${habiles(since)}` : ended
    }
    default: {
      const left = plazo.remaining_business_days ?? 0
      if (left === 0) return `vence hoy (${formatDate(plazo.deadline)})`
      return `vence el ${formatDate(plazo.deadline)} · ${left === 1 ? 'queda' : 'quedan'} ${habiles(left)}`
    }
  }
}

/** Which ingreso the clock started from, and its date. */
export function plazoBaseText(plazo: PlazoPmf): string {
  if (!plazo.base_field || !plazo.base_date) return '—'
  return `${BASE_FIELD_LABELS[plazo.base_field]} · ${formatDate(plazo.base_date)}`
}

/** The planilla's «90 dias» against the computed deadline. */
export function cruceText(plazo: PlazoPmf): string {
  switch (plazo.cruce) {
    case 'coincide':
      return 'Coincide con el cálculo'
    case 'difiere': {
      const difference = plazo.diferencia_dias ?? 0
      const side = difference < 0 ? 'antes' : 'después'
      return `Difiere: la planilla dice ${formatDate(plazo.planilla_90_dias)}, ${calendarDays(Math.abs(difference))} ${side} del cálculo`
    }
    case 'sin_dato':
      return 'La planilla no trae una fecha «90 dias» legible'
    default:
      return 'Sin cálculo con qué comparar'
  }
}

export function indexPlazos(data: TranselecPlazos | null): Map<string, PlazoPmf> {
  return new Map((data?.pmfs ?? []).map((entry) => [entry.pmf, entry]))
}

/** What the drawer needs about one PMF's term. */
export interface PlazoDetail {
  entry: PlazoPmf
  /** ISO date: the server's «today» in Chile. */
  observedOn: string
  calendarVersion: string
}

export function plazoDetail(data: TranselecPlazos | null, pmf: string): PlazoDetail | null {
  const entry = data?.pmfs.find((candidate) => candidate.pmf === pmf)
  if (!data || !entry) return null
  return { entry, observedOn: data.observed_on, calendarVersion: data.calendar.version }
}
```

- [ ] **Step 6: Add the two rule explanations**

In `src/lib/rules.ts`, add these entries to `RULES` after the Estado plan's
`lifecycle_pmf_v1`:

```ts
  plazo_conaf_90_habiles_v1: {
    name: 'Plazo CONAF de 90 días hábiles',
    steps: [
      'Para cada PMF, la fecha de inicio es «Fecha de ingreso2» si la tiene; si no, «Fecha de ingreso1». Un reingreso vuelve a contar el plazo.',
      'Si la fecha más reciente no se puede leer, no se usa la anterior: el PMF queda «Sin fecha legible».',
      'Las fechas se leen en todas las filas del PMF; si las filas traen fechas distintas, no se elige ninguna («Fechas distintas»).',
      'El día 1 es el primer día hábil después del ingreso; el plazo vence el día hábil 90. Son hábiles los días de lunes a viernes que no son feriados nacionales de Chile.',
      '«Hoy» es la fecha del servidor en Chile, no la del navegador ni la columna «Hoy» de la planilla.',
      'Vencido si hoy es posterior al vencimiento; por vencer si quedan 10 días hábiles o menos; los PMF Aprobados, Descartados o Desistidos no aplican.',
      'La columna «90 dias» de la planilla se compara con este cálculo; nunca se reemplaza.',
      'Regla provisional hasta que Campo Digital confirme cuándo empieza el plazo y si se suspende.',
    ],
    sourceColumns: ['PMF', 'Fecha de ingreso2', 'Fecha de ingreso1', '90 dias', 'Estado resumido'],
  },
  vencimiento_columna_90_dias_legacy: {
    name: 'Ingresos sobre 90 días, regla anterior',
    steps: [
      'Fila por fila: «Estado resumido» distinto de «Aprobado» y fecha «90 dias» de la planilla anterior a hoy.',
      'Usa la fecha que trae la planilla, sin contar días hábiles. Se muestra solo para comparar con el plazo calculado.',
    ],
    sourceColumns: ['Estado resumido', '90 dias'],
  },
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `npm test -- src/lib/plazo.test.ts`
Expected: PASS.

- [ ] **Step 8: Add the e2e stub**

In `tests/e2e/stubs.ts`, add after the Estado plan's `lifecycleBody`:

```ts
/**
 * `GET /transelec/plazos`: one entry per `lifecycleBody()` PMF (PMF-001 …
 * PMF-006), read on 2026-09-02 like every stubbed `Date` header. A filtered
 * request keeps only PMF-001, so a filter change visibly moves the counts.
 */
export function plazosBody(filtered: boolean) {
  const entry = (index: number, plazo: Record<string, unknown>) => ({
    pmf: `PMF-${String(index).padStart(3, '0')}`,
    source_row_number: index,
    base_field: 'fecha_ingreso',
    base_date: '2026-02-10',
    base_source_rows: [index],
    deadline: '2026-06-19',
    elapsed_business_days: 141,
    remaining_business_days: -51,
    planilla_90_dias: '2026-05-10',
    cruce: 'difiere',
    diferencia_dias: -40,
    legacy_vencido: true,
    ...plazo,
  })
  const all = [
    entry(1, { estado: 'vencido' }),
    entry(2, {
      estado: 'por_vencer',
      base_date: '2026-04-30',
      deadline: '2026-09-09',
      elapsed_business_days: 85,
      remaining_business_days: 5,
      diferencia_dias: -122,
    }),
    entry(3, {
      estado: 'en_plazo',
      base_field: 'fecha_ingreso_2',
      base_date: '2026-08-03',
      deadline: '2026-12-10',
      elapsed_business_days: 22,
      remaining_business_days: 68,
      diferencia_dias: -214,
    }),
    entry(4, { estado: 'vencido' }),
    entry(5, {
      estado: 'no_aplica',
      elapsed_business_days: null,
      remaining_business_days: null,
      legacy_vencido: false,
    }),
    entry(6, {
      estado: 'conflicto',
      base_date: null,
      base_source_rows: [6, 7],
      deadline: null,
      elapsed_business_days: null,
      remaining_business_days: null,
      cruce: 'sin_calculo',
      diferencia_dias: null,
    }),
  ]
  const pmfs = filtered ? all.slice(0, 1) : all
  const count = (estado: string) => pmfs.filter((item) => item.estado === estado).length
  return {
    basis: 'plazo_conaf_90_habiles_v1',
    legacy_basis: 'vencimiento_columna_90_dias_legacy',
    observed_on: '2026-09-02',
    calendar: { source: 'holidays', country: 'CL', version: '0.105' },
    plazo_habiles: 90,
    por_vencer_umbral: 10,
    total_pmf_count: pmfs.length,
    estados: {
      vencido: count('vencido'),
      por_vencer: count('por_vencer'),
      en_plazo: count('en_plazo'),
      sin_fecha: 0,
      sin_fecha_texto: 0,
      conflicto: count('conflicto'),
      no_aplica: count('no_aplica'),
    },
    cruce_difiere_count: pmfs.filter((item) => item.cruce === 'difiere').length,
    // The former row-level rule over the stubbed rows (60 unfiltered, 8 filtered).
    legacy_vencido_row_count: filtered ? 8 : 60,
    pmfs,
  }
}
```

In `stubPlatform`, after the Estado plan's `**/api/transelec/lifecycle*` route, add:

```ts
  await page.route('**/api/transelec/plazos*', (route) => {
    if (fail) return json(route, failBody, fail)
    const url = new URL(route.request().url())
    return json(route, plazosBody(isFiltered(url)))
  })
```

- [ ] **Step 9: Type-check, lint, unit suite**

Run: `npx tsc -b && npm run lint && npm test`
Expected: clean; all PASS.

- [ ] **Step 10: Commit**

```bash
git add src/api.ts src/lib/plazo.ts src/lib/plazo.test.ts src/lib/rules.ts src/test/factories.ts tests/e2e/stubs.ts
git commit -m "feat(transelec-dashboard): plazo types, wording and read for the 90 días hábiles basis" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Plazo cell, «Plazo CONAF» column and the drawer block

**Files:**
- Create: `products/transelect/dashboard/src/components/PlazoCell.tsx`
- Create: `products/transelect/dashboard/src/lib/plazoColumn.tsx`
- Create: `products/transelect/dashboard/src/components/PlazoDrawerSection.tsx`
- Modify: `products/transelect/dashboard/src/components/RowDetailDrawer.tsx` (props; one insertion above the Tramitación section)
- Modify: `products/transelect/dashboard/src/components/RowDetailDrawer.test.tsx` (double quotes, semicolons)
- Modify: `products/transelect/dashboard/src/components/EstadoTable.test.tsx` (one test)
- Modify: `products/transelect/dashboard/src/styles/components.css` (append)

**Interfaces:**
- Consumes: Task 4's names, plus `EstadoColumn` (Estado plan).
- Produces:
  - `PlazoCell({ plazo, loading? })`, with test id `plazo-<source_row_number>`;
  - `plazoColumn(byPmf: ReadonlyMap<string, PlazoPmf>, loading: boolean): EstadoColumn`;
  - `PlazoDrawerSection({ detail })`, with test id `drawer-plazo`;
  - `RowDetailDrawer` gains the optional prop `plazo?: PlazoDetail | null`.

Commands run from `products/transelect/dashboard`.

- [ ] **Step 1: Write the failing tests**

(a) Append to `src/components/EstadoTable.test.tsx`, inside `describe('EstadoTable', …)`.
Add `import { plazoColumn } from '../lib/plazoColumn'` and change the factories
import to `import { makeLifecycle, makePlazos } from '../test/factories'`, plus
`import { indexPlazos } from '../lib/plazo'`.

```tsx
  it('shows the «Plazo CONAF» column joined by PMF, and a dash where there is none', () => {
    const byPmf = indexPlazos(makePlazos())
    byPmf.delete('MP003')
    render(
      <EstadoTable
        rows={rows}
        selectedRow={null}
        onOpen={() => {}}
        extraColumns={[plazoColumn(byPmf, false)]}
      />,
    )
    expect(screen.getByTestId('plazo-3')).toHaveTextContent('Vencido')
    expect(screen.getByTestId('plazo-3')).toHaveTextContent('venció el 14-07-2026 · hace 35 días hábiles')
    expect(screen.getByTestId('estado-row-5')).toHaveTextContent('—')
  })

  it('says it is still calculating while the plazo read is on its way', () => {
    render(
      <EstadoTable
        rows={rows}
        selectedRow={null}
        onOpen={() => {}}
        extraColumns={[plazoColumn(new Map(), true)]}
      />,
    )
    expect(screen.getByTestId('estado-row-2')).toHaveTextContent('Calculando…')
  })
```

(b) In `src/components/RowDetailDrawer.test.tsx`, change the factories import
to `import { makeLifecycleRow, makePlazos, makeRow } from "../test/factories";`,
add `import { plazoDetail } from "../lib/plazo";`, and append:

```tsx
describe("RowDetailDrawer — Plazo CONAF (plazo_conaf_90_habiles_v1)", () => {
  beforeEach(() => {
    vi.mocked(getPmfDetail).mockReset();
    vi.mocked(getAef).mockReset();
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: { pmfs: [] } as unknown as TranselecAef,
    });
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: "MP002",
        row_count: 1,
        basis_estado_resumido: "estado_resumido_first_row",
        estado_resumido: "En tramite",
        rows: [makeRow({ source_row_number: 3, pmf: "MP002" })],
      },
    });
  });

  it("explains the term: where it counts from, when it ends and the planilla's «90 dias»", () => {
    const row = makeLifecycleRow({ source_row_number: 3, pmf: "MP002" });
    render(
      <RowDetailDrawer row={row} plazo={plazoDetail(makePlazos(), "MP002")} onClose={() => {}} />,
    );

    const block = screen.getByTestId("drawer-plazo");
    expect(block).toHaveTextContent("Plazo CONAF (90 días hábiles)");
    expect(block).toHaveTextContent("Vencido");
    expect(block).toHaveTextContent("Fecha de ingreso1 · 04-03-2026");
    expect(block).toHaveTextContent("14-07-2026");
    expect(block).toHaveTextContent("125 transcurridos");
    expect(block).toHaveTextContent("Difiere: la planilla dice 02-06-2026, 42 días antes del cálculo");
    expect(block).toHaveTextContent("02-09-2026");
    expect(block).toHaveTextContent("holidays 0.105");
  });

  it("has no Plazo CONAF block when opened without one", () => {
    render(<RowDetailDrawer row={makeRow({ source_row_number: 3, pmf: "MP002" })} onClose={() => {}} />);
    expect(screen.queryByTestId("drawer-plazo")).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm test -- src/components/EstadoTable.test.tsx src/components/RowDetailDrawer.test.tsx`
Expected: FAIL. `Failed to resolve import "../lib/plazoColumn"` / `drawer-plazo` not found.

- [ ] **Step 3: Create `src/components/PlazoCell.tsx`**

```tsx
/**
 * One PMF's CONAF term in the «Estado» table: a status pill and the date
 * line. A dash when the read has no entry for the PMF; «Calculando…» while
 * the read is on its way.
 */
import type { PlazoPmf } from '../api'
import { PLAZO_ESTADO_LABELS, PLAZO_ESTADO_PILL, plazoText } from '../lib/plazo'

export function PlazoCell({ plazo, loading = false }: { plazo: PlazoPmf | undefined; loading?: boolean }) {
  if (!plazo) return <span className="hint">{loading ? 'Calculando…' : '—'}</span>
  return (
    <span className="plazo-cell" data-testid={`plazo-${plazo.source_row_number}`}>
      <span className={`pill ${PLAZO_ESTADO_PILL[plazo.estado]}`}>
        {PLAZO_ESTADO_LABELS[plazo.estado]}
      </span>
      <span className="hint">{plazoText(plazo)}</span>
    </span>
  )
}
```

- [ ] **Step 4: Create `src/lib/plazoColumn.tsx`**

```tsx
/**
 * The «Plazo CONAF» column, added to the «Estado» table through
 * `EstadoTable`'s `extraColumns` and joined to each lifecycle row by PMF.
 * Kept in `lib/` so component modules export only components.
 */
import type { PlazoPmf } from '../api'
import { PlazoCell } from '../components/PlazoCell'
import type { EstadoColumn } from './estadoColumns'

export function plazoColumn(byPmf: ReadonlyMap<string, PlazoPmf>, loading: boolean): EstadoColumn {
  return {
    key: 'plazo',
    header: 'Plazo CONAF',
    render: (row) => <PlazoCell plazo={byPmf.get(row.pmf)} loading={loading} />,
  }
}
```

- [ ] **Step 5: Create `src/components/PlazoDrawerSection.tsx`**

```tsx
/**
 * «Plazo CONAF (90 días hábiles)» in the PMF drawer: where the clock started,
 * when it ends, the business days counted, and the planilla's own «90 dias»
 * beside the calculation. Everything is the server's
 * (`plazo_conaf_90_habiles_v1`); provisional wording.
 */
import { formatDate, formatInteger } from '../format'
import {
  PLAZO_ESTADO_LABELS,
  PLAZO_ESTADO_PILL,
  type PlazoDetail,
  cruceText,
  plazoBaseText,
} from '../lib/plazo'

function daysText(detail: PlazoDetail): string {
  const { elapsed_business_days: elapsed, remaining_business_days: remaining } = detail.entry
  if (elapsed === null || remaining === null) return '—'
  if (remaining < 0) {
    return `${formatInteger(elapsed)} transcurridos · ${formatInteger(-remaining)} desde el vencimiento`
  }
  return `${formatInteger(elapsed)} transcurridos · ${formatInteger(remaining)} por transcurrir`
}

export function PlazoDrawerSection({ detail }: { detail: PlazoDetail }) {
  const { entry } = detail
  return (
    <section className="drawer-section" aria-labelledby="drawer-plazo-title" data-testid="drawer-plazo">
      <h3 id="drawer-plazo-title">Plazo CONAF (90 días hábiles)</h3>
      <dl className="facts">
        <div className="fact">
          <dt>Estado del plazo</dt>
          <dd>
            <span className={`pill ${PLAZO_ESTADO_PILL[entry.estado]}`}>
              {PLAZO_ESTADO_LABELS[entry.estado]}
            </span>
          </dd>
        </div>
        <div className="fact">
          <dt>Cuenta desde</dt>
          <dd>{plazoBaseText(entry)}</dd>
        </div>
        <div className="fact">
          <dt>Vence</dt>
          <dd>{entry.deadline ? formatDate(entry.deadline) : '—'}</dd>
        </div>
        <div className="fact">
          <dt>Días hábiles</dt>
          <dd>{daysText(detail)}</dd>
        </div>
        <div className="fact wide">
          <dt>«90 dias» de la planilla</dt>
          <dd>
            {entry.planilla_90_dias ? formatDate(entry.planilla_90_dias) : 'Sin fecha'} ·{' '}
            {cruceText(entry)}
          </dd>
        </div>
      </dl>
      <p className="hint">
        Días hábiles: lunes a viernes sin feriados nacionales de Chile (calendario holidays{' '}
        {detail.calendarVersion}). Hoy es {formatDate(detail.observedOn)}, la fecha del servidor en
        Chile. Regla provisional hasta que Campo Digital confirme cuándo empieza el plazo.
      </p>
    </section>
  )
}
```

- [ ] **Step 6: Wire the drawer**

In `src/components/RowDetailDrawer.tsx`:

(a) Add the imports:

```tsx
import type { PlazoDetail } from '../lib/plazo'
import { PlazoDrawerSection } from './PlazoDrawerSection'
```

(b) Add the prop to the signature's destructuring and its type, after the
Estado plan's `lifecycle = null,` / `lifecycle?: LifecycleRow | null`:

```tsx
  plazo = null,
```

```tsx
  /** CONAF's 90-business-day term for this PMF, when the Estado section opens it. */
  plazo?: PlazoDetail | null
```

(c) Directly above `<section className="drawer-section" aria-labelledby="drawer-tramitacion">`
(that is, after the Estado plan's `{lifecycle && (…)}` block), insert:

```tsx
        {plazo && <PlazoDrawerSection detail={plazo} />}
```

- [ ] **Step 7: Add the style**

Append to `src/styles/components.css`:

```css
/* «Plazo CONAF» cell: the status pill, then its date line. */
.plazo-cell {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-3);
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `npm test -- src/components/EstadoTable.test.tsx src/components/RowDetailDrawer.test.tsx`
Expected: PASS, including every earlier drawer and table test.

- [ ] **Step 9: Type-check and lint**

Run: `npx tsc -b && npm run lint`
Expected: clean.

- [ ] **Step 10: Commit**

```bash
git add src/components/PlazoCell.tsx src/lib/plazoColumn.tsx src/components/PlazoDrawerSection.tsx src/components/RowDetailDrawer.tsx src/components/RowDetailDrawer.test.tsx src/components/EstadoTable.test.tsx src/styles/components.css
git commit -m "feat(transelec-dashboard): «Plazo CONAF» cell, column and drawer block" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: EstadoPage reads `/plazos`; the browser-only overdue panel goes

**Files:**
- Rewrite: `products/transelect/dashboard/src/pages/EstadoPage.tsx`
- Modify: `products/transelect/dashboard/src/pages/EstadoPage.test.tsx`
- Delete: `src/components/OverduePanel.tsx`, `src/lib/overdue.ts`, `src/lib/overdue.test.ts`
- Modify: `products/transelect/dashboard/src/App.test.tsx`
- Modify: `products/transelect/dashboard/tests/e2e/dashboard.spec.ts`

**Interfaces:**
- Consumes: Task 4's `getPlazos`, `TranselecPlazos`, `indexPlazos` and `plazoDetail`; Task 5's `plazoColumn` and the `plazo` drawer prop; the Estado plan's `EstadoTable`, `LegacyPendingSection` and `getLifecycle`.
- Produces: test ids `plazo-vencidos-note`, `plazo-vencidos-count`, `plazo-legacy-count`. The button with `data-quick="overdue"` reads «¿Qué PMF superaron los 90 días hábiles?»; pressed, it reads «Ver todos los PMF».

Commands run from `products/transelect/dashboard`.

- [ ] **Step 1: Confirm the overdue code has no other user**

Run: `grep -rn "OverduePanel\|lib/overdue\|selectOverdueRows\|isOverdueRow" src tests`
Expected: hits only in `src/pages/EstadoPage.tsx`,
`src/components/OverduePanel.tsx`, `src/lib/overdue.ts` and
`src/lib/overdue.test.ts`. If anything else uses them, stop and report.

- [ ] **Step 2: Write the failing page tests**

In `src/pages/EstadoPage.test.tsx`:

(a) In the `vi.mock('../api', …)` factory, add `getPlazos: vi.fn(),`.

(b) Change `const { getLifecycle, getPending, getPmfDetail, getAef } = await import('../api')`
to `const { getLifecycle, getPending, getPlazos, getPmfDetail, getAef } = await import('../api')`.

(c) Change the factories import to
`import { makeLifecycle, makePending, makePlazos } from '../test/factories'`.

(d) In `beforeEach`, add:

```tsx
    vi.mocked(getPlazos).mockReset()
    vi.mocked(getPlazos).mockResolvedValue({ ok: true, data: makePlazos() })
```

(e) Append inside `describe('EstadoPage', …)`:

```tsx
  it('adds the «Plazo CONAF» column, joined by PMF', async () => {
    renderPage()
    const row = await screen.findByTestId('estado-row-3')
    await waitFor(() => expect(row).toHaveTextContent('Vencido'))
    expect(row).toHaveTextContent('venció el 14-07-2026')
    expect(screen.getByTestId('estado-row-5')).toHaveTextContent('En plazo')
  })

  it('shows only the vencidos when asked, with the server date and the former rule beside it', async () => {
    renderPage()
    const toggle = await screen.findByRole('button', {
      name: '¿Qué PMF superaron los 90 días hábiles?',
    })
    await waitFor(() => expect(toggle).toBeEnabled())
    await userEvent.click(toggle)

    expect(screen.getByTestId('plazo-vencidos-count')).toHaveTextContent('1')
    expect(screen.getByTestId('plazo-vencidos-note')).toHaveTextContent('02-09-2026')
    expect(screen.getByTestId('plazo-legacy-count')).toHaveTextContent('3')
    expect(screen.getByTestId('estado-row-3')).toBeInTheDocument()
    expect(screen.queryByTestId('estado-row-5')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Ver todos los PMF' }))
    expect(screen.getByTestId('estado-row-5')).toBeInTheDocument()
    expect(screen.queryByTestId('plazo-vencidos-note')).toBeNull()
  })

  it('opens the drawer with the PMF plazo block', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('estado-row-3')).toHaveTextContent('Vencido'))
    await userEvent.click(screen.getByTestId('estado-row-3'))
    expect(await screen.findByTestId('drawer-plazo')).toHaveTextContent('Vencido')
  })

  it('keeps the Estado table when the plazo read fails', async () => {
    vi.mocked(getPlazos).mockResolvedValue({ ok: false, status: 500, error: 'boom' })
    renderPage()
    await screen.findByTestId('estado-zone')
    await waitFor(() =>
      expect(screen.getByText('No se pudo calcular el plazo CONAF')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('estado-row-3')).toHaveTextContent('—')
    expect(
      screen.getByRole('button', { name: '¿Qué PMF superaron los 90 días hábiles?' }),
    ).toBeDisabled()
  })
```

- [ ] **Step 3: Run them to verify they fail**

Run: `npm test -- src/pages/EstadoPage.test.tsx`
Expected: the four new tests FAIL. There is no plazo column, and the button
still carries the old label.

- [ ] **Step 4: Rewrite `src/pages/EstadoPage.tsx`**

Replace the whole file with:

```tsx
/**
 * `/transelec/estado` — where each plan (PMF) stands in CONAF's process, and
 * how much of CONAF's 90-business-day term is left.
 *
 * Replaces «Pendientes» (meeting of 2026-10-02; specs
 * docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md and
 * docs/superpowers/specs/2026-10-04-transelec-plazo-90-habiles-design.md).
 * `GET /transelec/lifecycle` gives each PMF's group and step
 * (`lifecycle_pmf_v1`); `GET /transelec/plazos` gives its term
 * (`plazo_conaf_90_habiles_v1`), joined to the table by PMF through
 * `EstadoTable`'s `extraColumns`. Both follow the current filter state.
 *
 * TR-FUNC-031 («¿Qué ingresos superaron 90 días?») is answered by the server
 * now: business days in Chile's calendar from the most recent ingreso, with
 * «today» the server's date in Chile. The browser-only panel that compared
 * the planilla's «90 dias» with the response's `Date` header is gone; its
 * rule is kept by the API as `vencimiento_columna_90_dias_legacy` and its
 * count is shown beside the new one. The old «Pendientes prioritarios» rule
 * stays, closed, in `LegacyPendingSection`.
 */
import { useCallback, useMemo, useState } from 'react'
import {
  type LifecycleRow,
  type ResumenRow,
  type TranselecLifecycle,
  type TranselecPlazos,
  getLifecycle,
  getPlazos,
} from '../api'
import { EstadoTable } from '../components/EstadoTable'
import { LegacyPendingSection } from '../components/LegacyPendingSection'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { formatDate, formatInteger } from '../format'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { lifecycleGroupSegments, lifecycleStepSegments } from '../lib/lifecycle'
import { indexPlazos, plazoDetail } from '../lib/plazo'
import { plazoColumn } from '../lib/plazoColumn'
import { useReads, type FilterController } from '../lib/useFilters'
import { CompositionBar } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Chip, SectionHeader } from '../ui/Primitives'

export function EstadoPage({
  filterController,
  sourceFields = null,
}: {
  filterController: FilterController
  /** Contract fields the published workbook had, for the detail drawer. */
  sourceFields?: readonly string[] | null
}) {
  const { filters, replaceFilters, reset } = filterController
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<TranselecLifecycle>(
    useCallback(
      () => getLifecycle(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )

  // A separate read: the lifecycle table stands on its own if the plazo
  // calculation fails, with a dash in its column and one banner.
  const plazos = useReads<TranselecPlazos>(
    useCallback(
      () => getPlazos(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )
  const plazoIndex = useMemo(() => indexPlazos(plazos.data), [plazos.data])

  const [openRow, setOpenRow] = useState<ResumenRow | null>(null)
  const [soloVencidos, setSoloVencidos] = useState(false)

  const chips = activeFilterChips(filters)
  const openLifecycle: LifecycleRow | null =
    openRow && data ? (data.rows.find((entry) => entry.pmf === openRow.pmf) ?? null) : null
  const rows =
    data && soloVencidos && plazos.data
      ? data.rows.filter((row) => plazoIndex.get(row.pmf)?.estado === 'vencido')
      : (data?.rows ?? [])

  if (failure && !data) {
    return (
      <div className="page">
        <StateBlock view={failure} />
      </div>
    )
  }

  return (
    <div className="page enter">
      <SectionHeader
        title="Estado"
        meta="Dónde está cada PMF en la tramitación CONAF y cuánto le queda del plazo de 90 días hábiles. Un rechazo es un paso, no un final."
      />

      {chips.length > 0 && (
        <div className="active-filters no-print" style={{ paddingBottom: 'var(--s-5)' }}>
          <span className="eyebrow">Alcance filtrado</span>
          {chips.map((chip) => (
            <Chip
              key={chip.key}
              onRemove={() => replaceFilters(withoutChip(filters, chip))}
              removeLabel={`Quitar el filtro ${chip.label}: ${chip.value}`}
            >
              {chip.label}: {chip.value}
            </Chip>
          ))}
        </div>
      )}

      {failure && data && <AlertBanner title={failure.title}>{failure.message}</AlertBanner>}
      {plazos.failure && (
        <AlertBanner title="No se pudo calcular el plazo CONAF">{plazos.failure.message}</AlertBanner>
      )}

      {!data && loading && <LoadingBlock label="Cargando el estado de los PMF…" shape="bar" />}

      {data && (
        <section id="estadozone" data-testid="estado-zone">
          <div className="pending-lead">
            <CompositionBar
              title="PMF por grupo"
              noun="PMF"
              testId="estado-group"
              segments={lifecycleGroupSegments(data)}
            />
            <CompositionBar
              title="En trámite, por paso"
              noun="PMF en trámite"
              testId="estado-step"
              lead={false}
              segments={lifecycleStepSegments(data)}
            />
          </div>

          <p className="hint">
            El grupo sale del «Estado resumido» de la primera fila de cada PMF; el paso, de su
            «Estado». «Rechazado» es un paso dentro de «En trámite»: todo rechazo termina en
            «Aprobado», «Descartado» o «Desistido». Lo que esta regla no reconoce queda «Sin
            clasificar» y se lista en Calidad. El plazo CONAF cuenta 90 días hábiles desde el ingreso
            más reciente. Categorías y plazo provisionales hasta que Campo Digital los confirme.
          </p>
          <HowCalculated
            bases={[
              data.basis,
              ...(plazos.data ? [plazos.data.basis, plazos.data.legacy_basis] : []),
            ]}
            testId="estado-how"
          />

          <div className="btns no-print" style={{ margin: 'var(--s-5) 0' }}>
            {chips.length > 0 && (
              <button
                type="button"
                className="btn alt"
                onClick={reset}
                data-testid="clear-estado-filters"
              >
                Quitar filtros y ver todos los PMF
              </button>
            )}
            <button
              type="button"
              className={soloVencidos ? 'btn' : 'btn alt'}
              aria-pressed={soloVencidos}
              disabled={!plazos.data}
              onClick={() => setSoloVencidos((value) => !value)}
              data-quick="overdue"
            >
              {soloVencidos ? 'Ver todos los PMF' : '¿Qué PMF superaron los 90 días hábiles?'}
            </button>
          </div>

          {soloVencidos && plazos.data && (
            <p className="section-note" data-testid="plazo-vencidos-note">
              <b data-testid="plazo-vencidos-count">{formatInteger(plazos.data.estados.vencido)}</b>{' '}
              PMF con el plazo CONAF vencido al <b>{formatDate(plazos.data.observed_on)}</b>, la fecha
              del servidor en Chile, no una fecha fija. Con la regla anterior (fecha «90 dias» de la
              planilla anterior a hoy, sin «Aprobado») serían{' '}
              <b data-testid="plazo-legacy-count">
                {formatInteger(plazos.data.legacy_vencido_row_count)}
              </b>{' '}
              áreas de corta.
            </p>
          )}

          <section className="ruled" aria-labelledby="estado-rows-title">
            <SectionHeader
              id="estado-rows-title"
              title="PMF del alcance"
              meta={`${formatInteger(rows.length)} PMF · seleccione uno para ver su detalle`}
            />
            <EstadoTable
              rows={rows}
              selectedRow={openRow?.source_row_number ?? null}
              onOpen={setOpenRow}
              extraColumns={[plazoColumn(plazoIndex, plazos.loading)]}
            />
          </section>

          <section className="ruled">
            <LegacyPendingSection
              filters={filters}
              selectedRow={openRow?.source_row_number ?? null}
              onOpenRow={setOpenRow}
            />
          </section>
        </section>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          lifecycle={openLifecycle}
          plazo={plazoDetail(plazos.data, openRow.pmf)}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 5: Delete the browser-only overdue code**

```bash
git rm src/components/OverduePanel.tsx src/lib/overdue.ts src/lib/overdue.test.ts
```

Its predicate's cases now live in Python as
`test_the_legacy_rule_matches_the_dashboards_former_predicate` (Task 2).

- [ ] **Step 6: Mock `getPlazos` in `src/App.test.tsx`**

- In the `vi.mock('./api', …)` factory, add `getPlazos: vi.fn(),` after the Estado plan's `getLifecycle: vi.fn(),`.
- In `stubDashboardReads`, add `api.getPlazos` to the array.
- In the `beforeEach` reset list, add `api.getPlazos,` after `api.getLifecycle,`.

- [ ] **Step 7: Run the unit suite**

Run: `npx tsc -b && npm run lint && npm test`
Expected: clean; all PASS.

- [ ] **Step 8: Update the e2e specs**

In `tests/e2e/dashboard.spec.ts`:

(a) Replace the Estado plan's versions of "TR-FUNC-031: the overdue consultation…" and
"TR-FUNC-017/031: the overdue panel follows a filter change…" with:

```ts
test('TR-FUNC-031: the overdue question is answered with the server date in Chile, never a frozen literal', async ({
  page,
}) => {
  await openEstado(page)
  await page.getByRole('button', { name: '¿Qué PMF superaron los 90 días hábiles?' }).click()

  const note = page.getByTestId('plazo-vencidos-note')
  await expect(note).toBeVisible()
  await expect(page.getByTestId('plazo-vencidos-count')).toHaveText('2')
  // The source dashboards froze this comparison at 2026-08-26.
  await expect(note).not.toContainText('26-08-2026')
  await expect(note).toContainText('02-09-2026')
  await expect(note).toContainText('la fecha del servidor en Chile')
  await expect(page.getByTestId('plazo-legacy-count')).toHaveText('60')
  await expect(page.getByTestId('estado-table').locator('tbody tr')).toHaveCount(2)

  await page.getByRole('button', { name: 'Ver todos los PMF' }).click()
  await expect(note).toBeHidden()
  await expect(page.getByTestId('estado-table').locator('tbody tr')).toHaveCount(6)
})

test('TR-FUNC-017/031: the vencidos view follows a filter change instead of going stale', async ({
  page,
}) => {
  await openEstado(page)
  await page.getByRole('button', { name: '¿Qué PMF superaron los 90 días hábiles?' }).click()
  await expect(page.getByTestId('plazo-vencidos-count')).toHaveText('2')

  await page.goto('/transelec/estado?q=rechaz')
  await expect(page.getByTestId('estado-zone')).toBeVisible()
  await page.getByRole('button', { name: '¿Qué PMF superaron los 90 días hábiles?' }).click()
  await expect(page.getByTestId('plazo-vencidos-count')).toHaveText('1')
  await expect(page.getByTestId('plazo-legacy-count')).toHaveText('8')
})

test('Estado: the «Plazo CONAF» column and the drawer explain each term', async ({ page }) => {
  await openEstado(page)
  const headers = page.getByTestId('estado-table').locator('thead th')
  await expect(headers.last()).toHaveText('Plazo CONAF')
  await expect(page.getByTestId('plazo-1')).toContainText('Vencido')
  await expect(page.getByTestId('plazo-1')).toContainText('venció el 19-06-2026 · hace 51 días hábiles')
  await expect(page.getByTestId('plazo-2')).toContainText('Por vencer')
  await expect(page.getByTestId('plazo-3')).toContainText('quedan 68 días hábiles')
  await expect(page.getByTestId('plazo-5')).toContainText('No aplica')

  await page.getByTestId('estado-row-1').locator('td').first().click()
  const block = page.getByTestId('drawer-plazo')
  await expect(block).toContainText('Fecha de ingreso1 · 10-02-2026')
  await expect(block).toContainText('Difiere: la planilla dice 10-05-2026, 40 días antes del cálculo')
  await expect(block).toContainText('holidays 0.105')
})
```

(b) In "no section shows a raw rule identifier in its reading text", change
the regex to
`/_legacy|_first_row|pmf_from_source_rows|lifecycle_pmf|plazo_conaf|canónic|deduplica/`.

- [ ] **Step 9: Run the e2e suite**

Make sure no other worktree is using port 5299. Then:

Run: `npm run test:e2e`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add -A src tests
git commit -m "feat(transelec-dashboard): Estado shows the CONAF term; the browser-only overdue panel is retired" -m "TR-FUNC-031 is answered by the server's 90 días hábiles basis; the former rule is kept as vencimiento_columna_90_dias_legacy." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(The `git add` runs from `products/transelect/dashboard`. Check
`git status`: the three deletions must be staged.)

---

### Task 7: Calidad lists the PMFs whose «90 dias» differs from the calculation

**Files:**
- Create: `products/transelect/dashboard/src/components/PlazoQualityPanel.tsx` + `PlazoQualityPanel.test.tsx`
- Modify: `products/transelect/dashboard/src/pages/CalidadPage.tsx` (the Estado plan's version)
- Modify: `products/transelect/dashboard/tests/e2e/dashboard.spec.ts` (append one test)

**Interfaces:**
- Consumes: `getPlazos`, `TranselecPlazos`, `cruceText`, `makePlazos` (Task 4); `ROUTES.estado` (Estado plan).
- Produces: `PlazoQualityPanel({ plazos, filters? })`, with test ids `plazo-quality`, `plazo-difiere-count`, `plazo-difiere-list`, `plazo-difiere-<source_row_number>` and `how-plazo-difiere`.

- [ ] **Step 1: Write the failing test**

Create `src/components/PlazoQualityPanel.test.tsx`:

```tsx
import { render as renderInDom, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { PlazoQualityPanel } from './PlazoQualityPanel'
import { ROUTES, RouterProvider } from '../router'
import { makePlazos } from '../test/factories'

function render(node: ReactNode) {
  return renderInDom(<RouterProvider initialPath={ROUTES.calidad}>{node}</RouterProvider>)
}

describe('PlazoQualityPanel', () => {
  it('lists each PMF whose «90 dias» differs from the calculation, with its row', () => {
    render(<PlazoQualityPanel plazos={makePlazos()} />)

    expect(screen.getByTestId('plazo-difiere-count')).toHaveTextContent('1')
    const item = screen.getByTestId('plazo-difiere-3')
    expect(item).toHaveTextContent('MP002')
    expect(item).toHaveTextContent('fila 3')
    expect(item).toHaveTextContent('Difiere: la planilla dice 02-06-2026, 42 días antes del cálculo')
    expect(screen.getByRole('link', { name: 'Ver en Estado →' })).toHaveAttribute(
      'href',
      '/transelec/estado',
    )
  })

  it('reads calm when every «90 dias» matches', () => {
    const plazos = makePlazos()
    render(
      <PlazoQualityPanel
        plazos={{ ...plazos, pmfs: plazos.pmfs.filter((entry) => entry.cruce !== 'difiere') }}
      />,
    )

    expect(screen.getByTestId('plazo-difiere-count')).toHaveTextContent('0')
    expect(screen.queryByTestId('plazo-difiere-list')).toBeNull()
  })

  it('keeps the rule one «Cómo se calcula» away', () => {
    render(<PlazoQualityPanel plazos={makePlazos()} />)

    const how = screen.getByTestId('how-plazo-difiere')
    expect(how.tagName).toBe('DETAILS')
    expect(how).toHaveTextContent('plazo_conaf_90_habiles_v1')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test -- src/components/PlazoQualityPanel.test.tsx`
Expected: FAIL. `Failed to resolve import "./PlazoQualityPanel"`.

- [ ] **Step 3: Create `src/components/PlazoQualityPanel.tsx`**

```tsx
/**
 * Calidad: PMFs whose planilla «90 dias» is not the date 90 business days
 * from their most recent ingreso (`plazo_conaf_90_habiles_v1`). Listed with
 * their row so a person reads the planilla; the planilla is never corrected.
 */
import type { TranselecFilterState, TranselecPlazos } from '../api'
import { formatInteger } from '../format'
import { searchFromFilters } from '../lib/filterUrl'
import { cruceText } from '../lib/plazo'
import { Link, ROUTES } from '../router'
import { HowCalculated } from '../ui/HowCalculated'

export function PlazoQualityPanel({
  plazos,
  filters,
}: {
  plazos: TranselecPlazos
  /** Carried into the link, so the finding opens under the same scope. */
  filters?: TranselecFilterState
}) {
  const differ = plazos.pmfs.filter((entry) => entry.cruce === 'difiere')
  const search = filters ? searchFromFilters(filters) : ''

  return (
    <div data-testid="plazo-quality">
      <ul className="quality" aria-label="PMF cuya fecha «90 dias» no coincide con el cálculo">
        <li className="quality-item" data-tone={differ.length > 0 ? 'warn' : 'calm'}>
          <p className="quality-headline">
            <b data-testid="plazo-difiere-count">{formatInteger(differ.length)}</b>
            <span>PMF cuya fecha «90 dias» no coincide con 90 días hábiles desde el ingreso</span>
          </p>
          {differ.length === 0 ? (
            <p className="quality-what">
              En los PMF del alcance con fecha «90 dias» legible, la planilla coincide con el
              cálculo.
            </p>
          ) : (
            <>
              <ul className="variant-list" data-testid="plazo-difiere-list">
                {differ.map((entry) => (
                  <li
                    key={entry.source_row_number}
                    data-testid={`plazo-difiere-${entry.source_row_number}`}
                  >
                    <b>{entry.pmf}</b> · fila {formatInteger(entry.source_row_number)} ·{' '}
                    {cruceText(entry)}
                  </li>
                ))}
              </ul>
              <p className="quality-todo">
                <b>Qué revisar:</b> la columna «90 dias» y la fecha de ingreso de esas filas en la
                planilla. La diferencia puede venir de feriados, de un reingreso o de cómo se cuenta
                el día 1.
              </p>
              <Link to={`${ROUTES.estado}${search}`} className="quality-go">
                Ver en Estado →
              </Link>
            </>
          )}
          <HowCalculated bases={[plazos.basis]} testId="how-plazo-difiere" />
        </li>
      </ul>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- src/components/PlazoQualityPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Add the block to `CalidadPage`**

In `src/pages/CalidadPage.tsx`, working on the Estado plan's version:

(a) Add `type TranselecPlazos,` and `getPlazos,` to the `from '../api'` import.
Add `import { PlazoQualityPanel } from '../components/PlazoQualityPanel'`
after the `LifecycleQualityPanel` import.

(b) Add `plazos: TranselecPlazos` to `interface CalidadData`.

(c) In the `useReads` body:
- add `getPlazos(filters),` as the fifth `Promise.all` entry and `plazos` to
  the destructured names;
- add `if (!plazos.ok) return plazos` after the lifecycle check;
- add `plazos: plazos.data,` to the returned `data`.

(d) Directly after the Estado plan's `lifecycle-review-title` section, add:

```tsx
          <section className="ruled" aria-labelledby="plazo-difiere-title">
            <SectionHeader
              id="plazo-difiere-title"
              title="PMF cuya fecha «90 dias» no coincide con el plazo calculado"
              meta="La planilla se compara con 90 días hábiles desde el ingreso más reciente; no se corrige."
            />
            <PlazoQualityPanel plazos={data.plazos} filters={filters} />
          </section>
```

- [ ] **Step 6: Add the e2e test**

Append to `tests/e2e/dashboard.spec.ts`:

```ts
test('Calidad: the PMFs whose «90 dias» differs from the calculation are listed', async ({
  page,
}) => {
  await openCalidad(page)
  await expect(page.getByTestId('plazo-difiere-count')).toHaveText('5')
  await expect(page.getByTestId('plazo-difiere-1')).toContainText(
    'Difiere: la planilla dice 10-05-2026, 40 días antes del cálculo',
  )
})
```

- [ ] **Step 7: Run everything for the dashboard**

Run: `npx tsc -b && npm run lint && npm test && npm run test:e2e`
Expected: all PASS. Run e2e only when no other worktree is using port 5299.

- [ ] **Step 8: Commit**

```bash
git add src/components/PlazoQualityPanel.tsx src/components/PlazoQualityPanel.test.tsx src/pages/CalidadPage.tsx tests/e2e/dashboard.spec.ts
git commit -m "feat(transelec-dashboard): Calidad lists the PMFs whose «90 dias» differs from the calculated term" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation, full verification, hand-off

**Files:**
- Modify: `products/transelect/dashboard/README.md`. This is the routes-table row the Estado plan wrote for `/transelec/estado`.
- Modify: `products/transelect/docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md`. This is the Estado plan's «Superseded 2026-10-04» paragraph at the end of §4.3.

- [ ] **Step 1: Dashboard README route**

Replace the Estado plan's `/transelec/estado` row with:

```markdown
| `/transelec/estado` | viewer+ | Where each PMF stands (`lifecycle_pmf_v1`), its CONAF 90-business-day term (`plazo_conaf_90_habiles_v1`, column «Plazo CONAF»), and the former pending rule (closed) |
```

- [ ] **Step 2: UX document note**

In that paragraph, replace the sentence `The 90-day toggle stays on the page.` with:

```markdown
The 90-day question («¿Qué PMF superaron los 90 días hábiles?») is answered
by the server's `plazo_conaf_90_habiles_v1` (90 business days in Chile's
calendar from the most recent ingreso; «today» is the server's date in
Chile), shown as the «Plazo CONAF» column. The browser-only panel that
compared the planilla's «90 dias» with the response's `Date` header was
removed on 2026-10-04; its rule is kept by the API as
`vencimiento_columna_90_dias_legacy` and its count is shown beside the new
one.
```

- [ ] **Step 3: Full verification (repo root)**

```bash
make format-check lint typecheck architecture-check docs-check
uv run pytest products/transelect/tests apps/api/tests -q
uv run pytest -q apps/api/integration_tests/test_transelec_reads_router.py apps/api/integration_tests/test_transelec_router.py
cd products/transelect/dashboard && npx tsc -b && npm run lint && npm test && npm run build && npm run test:e2e && cd -
```

Run the integration line in the shell with the Task 0 Step 4 exports, only
when no other worktree is using the test database. Run e2e only when no other
worktree is using port 5299.

Expected: every command exits 0. Record the pass counts.

- [ ] **Step 4: Manual check in the browser (local only)**

Run `make transelec-dev`, open `http://127.0.0.1:5200/transelec/estado` and
sign in with the demo admin identity. Check:
- the «Plazo CONAF» column;
- «¿Qué PMF superaron los 90 días hábiles?» and back;
- a row's drawer «Plazo CONAF» block;
- Calidad's «90 dias» block.

Use only the already-published local version. Do not upload, import or
publish any workbook.

- [ ] **Step 5: Commit the docs**

```bash
git add products/transelect/dashboard/README.md products/transelect/docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md
git commit -m "docs(transelec): the Estado page shows CONAF's 90 business days" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Hand-off (push and PR only when Rafael asks)**

Report:
- the branch `feat/transelec-plazo-90-habiles`, stacked on `feat/transelec-estado`;
- the commit list and the verification counts;
- the two plan checks (Task 1 Steps 5 and 6).

When Rafael says to publish it and the Estado PR is already merged, do
Task 9 first. If Estado is not merged yet, open the PR against
`feat/transelec-estado`:

```bash
git push -u origin feat/transelec-plazo-90-habiles
gh pr create --base feat/transelec-estado --head feat/transelec-plazo-90-habiles \
  --title "feat(transelec): CONAF's 90 business days per PMF (plazo_conaf_90_habiles_v1)" \
  --body "$(cat <<'EOF'
Implements docs/superpowers/specs/2026-10-04-transelec-plazo-90-habiles-design.md. Stacked on the Estado PR.

- plazo_conaf_90_habiles_v1 (transelec_ingestion/plazo_conaf.py): 90 business days (Mon–Fri minus Chile's national holidays) from the most recent ingreso; day 1 is the first business day after it; vencido / por vencer (≤10) / en plazo / sin fecha / sin fecha legible / fechas distintas / no aplica (closed lifecycle groups). An unreadable most-recent ingreso never falls back to the older one. The planilla's «90 dias» is compared, never overwritten.
- GET /api/transelec/plazos: today is the server's date in America/Santiago; one holidays calendar per request; rows only through _fetch_filtered_rows; returns the calendar version.
- Dashboard: «Plazo CONAF» column in Estado (extraColumns), drawer block, Calidad block. The browser-only overdue panel is removed; its rule is kept server-side as vencimiento_columna_90_dias_legacy and its count shown beside the new one.
- Dependency: holidays>=0.105,<1 in the transelec extra.

Plan checks:
- 2026 holidays vs <government source URL>: <identical | differences>.
- zoneinfo America/Santiago in the runtime image: <works as is | tzdata added>.

Verification: <paste the pass counts from Task 8 Step 3>.

Synthetic fixtures only; no workbook was opened, imported or published.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Fill in the three angle-bracket lines with the real results before running
`gh pr create`.

---

### Task 9: Rebase onto `main` after the Estado PR merges

**Files:** none (history only).

- [ ] **Step 1: Confirm Estado is on `main`**

```bash
git fetch origin
git log --oneline origin/main | grep -m1 "Estado\|lifecycle" || echo "Estado not merged yet: stop"
```

- [ ] **Step 2: Rebase**

If the Estado PR was merged with a merge commit (this repository's practice):

```bash
git rebase origin/main
```

If it was squash-merged, replay only this branch's commits:

```bash
git rebase --onto origin/main feat/transelec-estado feat/transelec-plazo-90-habiles
```

Resolve conflicts by keeping both sides' intent. The likely spots are:
- `apps/api/app/routers/transelec.py`, around the `/lifecycle` and
  `/owner-status` sections;
- `src/pages/EstadoPage.tsx`, `src/pages/CalidadPage.tsx`,
  `tests/e2e/stubs.ts` and `tests/e2e/dashboard.spec.ts`.

- [ ] **Step 3: Re-run Task 8 Step 3 in full**

Expected: every command exits 0. If the web-edits PR (`0012`) landed on
`main` first, run `uv run alembic upgrade head` on the test database before
the integration tests. `/plazos` reads through `_fetch_filtered_rows`, so it
needs no change for web edits.

- [ ] **Step 4: Retarget the PR (when Rafael asks)**

```bash
git push --force-with-lease origin feat/transelec-plazo-90-habiles
gh pr edit --base main
```

---

## Self-review notes (resolved inline)

**Spec coverage:**

| Spec item | Task |
|---|---|
| Business days Mon–Fri minus CL national holidays via `holidays` | Tasks 1 and 3 |
| Clock from ingreso 2 else ingreso 1, no fallback when unreadable | Task 2 |
| Day 1 = next business day; deadline = 90th | Task 2 |
| Today in `America/Santiago` | Task 3 (`chile_today`, dependency override) |
| Closed groups «no aplica» | Task 2; Task 3 passes `_closed_pmfs` |
| «90 dias» cross-check `coincide` / `difiere` / `sin_dato` | Task 2; Task 4 wording |
| Legacy basis kept and described | Tasks 2 and 3; Task 4 `rules.ts`; Task 6 count beside the new one |
| Basis id; calendar version in the API | Task 3 |
| Estado column with chip and date line; «Vencidos» filter on the server status | Tasks 5 and 6 |
| Drawer block | Task 5 |
| Overdue panel removed | Task 6 |
| Calidad block linking to Estado | Task 7 |
| Dependency `holidays>=0.105,<1` and lock | Task 1 |
| Plan checks (zoneinfo in the image, government list) | Task 1 Steps 5–6 |
| Testing list (calendar edge cases, smoke test, integration, vitest, Playwright) | Tasks 1–7 |

**Deviations, recorded:**
- **API path.** The read is `/transelec/plazos`, not `/api/transelec/plazos`
  as a router path; browsers call `/api/transelec/plazos`. This is the same
  mounting rule as the Estado plan's `/lifecycle`. It never collides with a
  page path, and a specific guard is added.
- **`sin_calculo`.** The spec lists `coincide`, `difiere` and `sin_dato`. The
  plan adds `sin_calculo` for PMFs with no computed deadline (no usable base
  date), so «there is no planilla date» is not conflated with «there is
  nothing to compare it with».
- **Closed plans still get a deadline.** They keep a computed deadline and
  cross-check (shown, not counted), with `elapsed` and `remaining` null. The
  spec only fixes their status, «no aplica».
- **Legacy rule compares in Chile.** It compares calendar dates in Chile,
  «90 dias» strictly **before** today, as the spec words it. The removed
  browser code compared UTC midnight with the current instant, which in
  Chile flipped up to a day early. The shared cases from `overdue.test.ts`
  keep their results.
- **Spec "Inputs below".** "Closed" comes from `_closed_pmfs(rows)` over the
  same filtered rows the Estado table classifies. Dates are resolved over all
  of each PMF's rows, following the `/aef` precedent.

**Type consistency:** the same field names run end to end.
- **Python:** `PmfPlazo` fields map 1:1 to `PlazoPmfView`, to JSON and to
  TS `PlazoPmf`: `elapsed_business_days`, `remaining_business_days`,
  `planilla_90_dias`, `diferencia_dias`, `legacy_vencido`.
- **Counts:** `PlazoSummary.estados` (`PLAZO_ESTADO_ORDER`) →
  `PlazoEstadoCountsView` → TS `Record<PlazoEstado, number>`.
- **Dashboard:**
  - `plazoColumn(byPmf, loading)` returns `EstadoColumn`, whose `render`
    takes a `LifecycleRow`, as in the Estado plan;
  - `PlazoDetail` is used by `plazoDetail`, `RowDetailDrawer` and
    `PlazoDrawerSection`.

**Verification of the code in this plan:** the module and unit tests of
Task 2 were run before writing this plan, on 2026-10-04, against the
repository's `resumen_layout`. The result was 44 passed, with ruff and mypy
clean. The real-calendar deadlines in Task 3 were computed with `holidays`
0.105 by the same module.
