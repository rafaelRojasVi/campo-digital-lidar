# Transelec dashboard usability pass — 2026-09-26

## Status

Implemented on PR #59 (`feat/transelec-dashboard-ux-pass`), targeting the Railway deploy branch `feat/transelec-ux-rearchitecture-v1`. At the time of this note the PR is open. No production deployment or workbook publication is part of this change.

## Observations

- In the local 09-Sept workbook preview, PMF entries in Pendientes looked actionable but the table rendered plain cells with no action. Two adjacent reset buttons did the same thing and had no effect without filters.
- The Explorador drawer opened on one source row and showed its row-level AEF fields as blank even when a sibling row carried AEF for the PMF. For example, BN001's selected source row 5 is blank while source row 4 carries the PMF's tracking record. The row must remain blank in the projection.
- Calidad exposed internal rule IDs such as `estado_resumido_first_row` and `owner_stage_legacy` in its reading text. The status-by-owner table and the main summary also use different grains/rules, so a bare difference in numbers was hard to explain.
- The top bar used a generic glyph. Campo Digital publishes a white logo at `https://www.campodigital.cl/wp-content/uploads/2019/11/logo-campo-blanco-home-1-02.png`.

## Decisions and implementation

- Pendientes and the Resumen work queue open the existing PMF detail drawer. An unfiltered Pendientes page has no redundant reset action. Keyboard activation, Escape, focus return and mobile presentation are covered by the dashboard interaction checks.
- The drawer presents tramitación and AEF near the top. It requests the existing `GET /transelec/aef` projection for the exact PMF to show resolved values, source rows and conflicts, then labels the selected source row's own cells separately. It permits switching among the PMF's rows. Blank source cells remain blank; no client-side field resolution is invented. The source row number stays visible.
- Calidad leads with what was found, its affected unit (PMF, predio or source row), and what to review. A closed **Cómo se calcula** disclosure retains exact source fields and internal rule IDs for audit. The owner-status comparison displays the two existing API result sets under the same filters; it does not derive a new official status.
- The dashboard bundles a resized copy of the official Campo Digital logo instead of fetching it from the public website at runtime. The Transelec name remains text and the brand link has an accessible name.
- `.claude/skills/transelec-workbook/SKILL.md` provides an intake procedure and `CLAUDE.md` routes planilla tasks to it. The canonical parsing rules remain in [Source Contract V2](../source-contract-v2.md). The private structural inspector uses the importer's recognizer and writes its report outside the repository.

## Follow-up audit on the final head

A second review of the final head used the `web-design-guidelines`, `design:accessibility-review`, `design:ux-copy` and `playwright-cli` skills at 1440×900 and 390×844 with synthetic stub data. It found and fixed:

- White count labels on the amber (2.75:1) and grey (3.6:1) composition segments, and amber `td.warn` text (2.6:1), failed WCAG 1.4.3. They now use dark ink or a new `--st-progress-ink` token (5.8:1 or more on every ground).
- The drawer repeated «fila N» under every PMF AEF value. When all values come from the same rows, it now says so once; per-value rows are shown only when they differ. Conflicts still list each variant with its rows.
- A Calidad card's number and title split onto separate lines when the title wrapped.

No calculation, API call or permission changed.

## Verification and limits

The author reported 228 Vitest tests, 107 Playwright tests, typecheck and build passing locally on the PR head. Two early browser runs each had one timeout; the cause was not established. GitHub CI is the merge gate. PR #59 adds a Transelec dashboard job for lint, unit tests, typecheck/build and browser tests; its outcome must be checked on the final head. Screenshots were made with synthetic data in a local scratchpad and are not committed to the PR.

The UI does not decide which owner-status rule is official, what AEF means, whether AEF is per PMF or area of cutting, which status to choose when a PMF's rows disagree, or whether the pending-stage label **Rechazado** is correct for every case in that bucket. These are [questions for Campo Digital](../es/2026-09-26-panel-usabilidad.md).
