# Transelec: CONAF's 90-business-day deadline

Date: 2026-10-04. Status: design approved in conversation with Rafael; this
file awaits his review before a plan is written. Backlog item PR-2 of
[the post-launch backlog](../../../products/transelect/docs/design/2026-10-02-post-launch-backlog-v1.md).
Sibling specs, built in parallel:
[Estado](2026-10-04-transelec-estado-lifecycle-design.md) and
[web edits and .xlsx download](2026-10-04-transelec-web-edits-xlsx-design.md).
Merge order: Estado → 90 días (stacked on the Estado branch) → web edits;
each rebased on `main` before merging.

## Goal

CONAF has 90 business days to resolve a plan (meeting of 2026-10-02, request
R6). The platform computes that deadline for each PMF and shows how many
business days remain. It compares the result with the planilla's own
«90 dias» column instead of only trusting it.

## Decisions (DECISION, 2026-10-04)

- **Business days** are Monday to Friday, excluding Chilean national holidays.
  The calendar is the Python `holidays` package, country `CL` (Rafael's
  choice).
- **The clock starts at the most recent ingreso:** *Fecha de ingreso2* when
  present, otherwise *Fecha de ingreso1*. Rafael's notes say the ingreso
  changes after a rejection and the days start running again from there.
- **Day 1** is the first business day after the ingreso date. The deadline is
  the 90th business day. INFERENCE: this follows Ley 19.880 art. 25 (time
  limits in days are business days and run from the day after). It is not
  confirmed for CONAF's procedure (OPEN QUESTION 1).
- **"Today"** is the server's date in `America/Santiago`, never the browser's
  date or the planilla's «Hoy».
- **Closed plans are exempt.** Plans whose Estado group is `aprobado`,
  `descartado` or `desistido` show «no aplica».
- **The planilla's «90 dias» is compared, never overwritten.**
- **The old rule stays as a legacy basis.** "the «90 dias» column is before
  today and the plan is not Aprobado" is kept as
  `vencimiento_columna_90_dias_legacy` and explained under «Cómo se calcula».

## Evidence (FACT, 2026-10-04)

- **No business-day logic exists today.** The overdue check is client-only:
  `dashboard/src/lib/overdue.ts` `isOverdueRow` compares `fecha_90_dias`
  with the API's `Date` header (`observedServerNow`) and skips «Aprobado».
  There is no holiday calendar in Python or TypeScript.
- **How dates arrive per row:**
  - `fecha_ingreso`, `fecha_ingreso_2` and `fecha_90_dias` are `date`
    columns;
  - text that is not one written-out Spanish date stays raw in
    `source_text_dates` with a null date (Source Contract V2, *Rows and
    cells*);
  - `resolve_pmf_field` (`resumen_layout.py`) resolves a field per PMF to
    `value`, `blank` or `conflict`, and treats raw text as different from
    any date.
- **The 30-Sept planilla:**
  - 58 cells in *Fecha de ingreso1* and «90 dias» hold two dates, so they
    have no date;
  - *Fecha de ingreso2* is blank on every row;
  - see the
    [2026-10-02 note](../../../products/transelect/docs/es/2026-10-02-planilla-30sep-segundo-ingreso.md).
- **The calendar package:** `holidays` is at version 0.105 on PyPI
  (2026-10-04), MIT licence, Python ≥ 3.10, no network access at runtime.
  It is not a dependency yet.
- **Runtime image:** it is `python:3.12-slim`. Whether `zoneinfo` resolves
  `America/Santiago` there is unverified (see Plan checks).

## Design

### Module `plazo_conaf.py`

New pure module `products/transelect/src/transelec_ingestion/plazo_conaf.py`:

- **Holiday check is injected:** callers pass an `is_holiday(date) -> bool`.
  Tests use a fixed set; the router passes
  `holidays.country_holidays("CL")`.
- **Day helpers:**
  - `business_day(d)` is `d.weekday() < 5 and not is_holiday(d)`;
  - `add_business_days(start, n)` returns the n-th business day after
    `start`;
  - `business_days_between(start, end)` counts business days `d` with
    `start < d <= end`.
- **Per PMF:**
  1. **Base date.** Resolve `fecha_ingreso_2` over the PMF's rows with
     `resolve_pmf_field`, using a row's raw text where its date is null.
     - A date → base date, `base_field = fecha_ingreso_2`.
     - Raw text → status `sin_fecha_texto`.
     - Rows disagree → `conflicto`.
     - Blank → repeat the same steps with `fecha_ingreso`.
     - Both blank → `sin_fecha`.
  2. **Deadline** = `add_business_days(base, 90)`. Elapsed =
     `business_days_between(base, today)`; remaining = 90 − elapsed.
  3. **Status**, first match wins:
     - `no_aplica` when the plan is closed (see Inputs below), even if it has
       no usable date;
     - then the base-date statuses from step 1 (`sin_fecha`,
       `sin_fecha_texto`, `conflicto`);
     - then `vencido` when today is after the deadline;
     - then `por_vencer` when remaining ≤ 10;
     - otherwise `en_plazo`.
  4. **Cross-check against «90 dias»,** resolved per PMF the same way:
     - `coincide` when it equals the deadline;
     - `difiere` with `diferencia_dias` (planilla minus computed, calendar
       days);
     - `sin_dato` when blank, text or in conflict.
  5. **Legacy basis** `vencimiento_columna_90_dias_legacy`, computed beside
     it: «90 dias» before today and *Estado resumido* not «Aprobado».
- **Inputs from the Estado spec.** "Closed" is the `lifecycle_pmf_v1` group
  from `lifecycle_view.py`. This PR therefore branches from the Estado
  branch (stacked) and merges after it.
- **Basis id:** `plazo_conaf_90_habiles_v1`.

### API

`GET /api/transelec/plazos`:

- Viewer and above; the usual filters; reads through `_fetch_filtered_rows`,
  so web edits of the ingreso dates apply once the web-edits spec lands.
- Returns:
  - `basis`;
  - `observed_on`, the server date in Chile;
  - `calendar`: `{"source": "holidays", "country": "CL", "version": "<installed holidays version>"}`, so a
    change of calendar is auditable;
  - counts per status;
  - per PMF: `base_field`, base date, deadline, elapsed, remaining, status,
    the planilla's «90 dias», cross-check and legacy flag.

### Dashboard

- **Estado table:** a «Plazo CONAF» column.
  - A status chip: vencido, por vencer, en plazo, sin fecha, no aplica.
  - Then «vence dd-mm-aaaa · quedan N días hábiles» or «venció hace N días
    hábiles».
  - A «Vencidos» filter chip uses the server status.
  - The page joins `/plazos` to `/estado` by PMF.
- **Drawer:** a «Plazo CONAF (90 días hábiles)» block with:
  - the date the clock started from, and which ingreso it is;
  - the deadline, and business days elapsed and remaining;
  - the planilla's «90 dias» with «coincide» or «difiere N días»;
  - the calendar version.
- **Overdue panel:** the client-only panel built on `lib/overdue.ts` is
  removed from the page. Its rule survives as the legacy basis returned by
  the API and is described in «Cómo se calcula».
- **Calidad:** a count of PMFs whose «90 dias» differs from the computed
  deadline, linking to the filtered Estado table.

### Dependency

Add `holidays>=0.105,<1` to the `transelec` extra. `uv.lock` pins the exact
version and Dependabot proposes calendar updates. Only this PR among the
three touches `pyproject.toml` and `uv.lock`.

## Plan checks

- Run `python -c "from zoneinfo import ZoneInfo; ZoneInfo('America/Santiago')"`
  inside the built runtime image. If it fails, add the `tzdata` package to
  the `transelec` extra.
- Confirm `holidays.country_holidays("CL", years=2026)` lists every 2026
  national holiday published by the Chilean government, and record the
  comparison in the PR.

## Testing

- **Product** (`products/transelect/tests/test_plazo_conaf.py`), fixed
  calendar:
  - an ingreso on Friday, on the eve of a holiday and on a holiday;
  - a deadline crossing a long weekend and crossing the new year;
  - ingreso 2 taking over from ingreso 1;
  - raw text giving `sin_fecha_texto`; disagreeing rows giving `conflicto`;
  - closed plans giving `no_aplica`;
  - `por_vencer` at exactly 10 days remaining;
  - the cross-check `coincide`, `difiere` and `sin_dato` cases;
  - the legacy basis matching `isOverdueRow` on shared fixtures.
- **Calendar smoke test** with the real `holidays` package: 18 September
  2026 is a holiday, and the 2026 list has the expected count.
- **Integration:** `/plazos` with filters, viewer access, and `observed_on`
  in Chilean time.
- **Dashboard:**
  - vitest for the plazo cell formatting;
  - Playwright for the column, the drawer block and the «Vencidos» filter;
  - the stubs fix `observed_on`.

## Limitations

- Regional holidays are not counted; only national holidays are.
- A holiday declared after the installed `holidays` version is released is
  missing until the package is updated. The calendar version in the API
  makes this visible.
- Until the 58 two-date cells are split into the `…2` columns at source, or
  corrected through a web edit (sibling spec), those plans show «sin fecha».

## Open questions for Campo Digital

Added to the Spanish meeting note.

1. Does CONAF's 90-day term start the business day after the ingreso, and
   does it pause while the applicant answers observations?
2. Does a recurso de reposición or jerárquico restart the 90 days, or only a
   new ingreso (*Fecha de ingreso2*)?
3. Should regional holidays count?

## Plan refinements (2026-10-04)

Found while writing
[the implementation plan](../plans/2026-10-04-transelec-plazo-90-habiles.md):

- **Cross-check.** It gains `sin_calculo` for PMFs without a computed
  deadline.
- **Legacy basis.** It uses «90 dias» strictly before the server's date in
  Chile, as specified. The browser check it replaces could flip up to a day
  early.
- **Test location.** Integration tests with dated cells go in
  `test_transelec_router.py`; the reads-router fixtures cannot write dates.
- **Holiday list.** The government page with the official 2026 list is
  located at execution time; `gob.cl/feriados` answered 404 on 2026-10-04.

### Execution refinements (2026-10-04, decided while building)

- **Column position.** «Plazo CONAF» sits right after «PMF» (`EstadoColumn.after`)
  so it stays visible at 390 px and at 1280 px.
- **Vencidos filter.** It is a toggle button, «¿Qué PMF superaron los 90 días
  hábiles?» / «Ver todos los PMF», rather than a chip. A printed vencidos view
  states its scope and the server date.
- **Calidad block.** It lists the PMFs whose «90 dias» differs, up to 10, each
  with «Buscar <PMF> en Estado», and links to Estado with the current filters.
- **Failures and dates.**
  - A `/plazos` failure shows Spanish text with «Reintentar».
  - A base date whose deadline would overflow the calendar reads
    `sin_fecha_texto` for that PMF instead of failing the request.
- **OPEN QUESTION.** A «-» in *Fecha de ingreso2* gives `sin_fecha_texto` with
  no fallback to ingreso 1. Source Contract V2 treats «-» as empty.
- **OPEN QUESTION.** The Calidad «difiere» list includes closed PMFs.
