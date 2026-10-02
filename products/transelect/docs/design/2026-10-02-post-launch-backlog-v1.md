# Transelec post-launch backlog V1 — 2026-10-02

## Status

Planning record. PR-0 below is implemented on `feat/transelec-ingreso-2-columns`
(migration `0011`, parser `@3`; see the contract amendment of 2026-10-02).
PR-1 to PR-3 are not started. The document orders the
changes requested by Campo Digital after the pilot went live
(see [Panel Transelec: el piloto está en uso](../es/2026-09-28-piloto-en-uso.md))
and records what was verified against the code and against the planilla
received on 2026-10-02 (`PlanillaMaestra-CD_30sep2026.xlsx`, kept outside the
repository). The Spanish counterpart for Campo Digital is
[Reunión del 02-10-2026: cambios pedidos y preguntas](../es/2026-10-02-reunion-cambios-y-preguntas.md).

Evidence labels follow [the documentation policy](../../../../docs/DOCUMENTATION_POLICY.md).

## 1. Evidence from the 30-Sept-2026 workbook

Inspected read-only with the importer's own recognizer
(`.claude/skills/transelec-workbook/inspect_workbook.py`, report written to a
scratchpad outside the repository). Counts and column letters only.

FACT:

- 7 worksheets: `Resumen`, `Reingresos`, three historical `Resumen …` snapshots,
  `Pendientes`, `Urgentes 07May`. Header row 2 of `Resumen`; 728 data rows.
- Column Y is headed `Fecha de ingreso1` and column Z `N Ingreso1`. Columns AC
  and AD are headed `Fecha de ingreso2` and `N Ingreso2` and are blank on every
  data row. Columns AA (`90 dias`), AB (`Hoy`) and AE (`Empresa`) are where
  the recognizer binds them.
- The recognizer does not know the `…1` spellings. It reports
  `columna_no_reconocida` for Y, Z, AC, AD, `columna_esperada_ausente` for
  `fecha_ingreso` and `columna_esencial_ausente` for `numero_ingreso`.
  **The workbook cannot be imported today.**
- `Fecha de ingreso1`: 602 real dates, 64 Spanish long-form text dates (the
  contract parses these), 58 cells with two dates, 2 cells with `-`.
- `90 dias`: 663 real dates, 3 Spanish text dates, 58 cells with two dates,
  2 with `-`.
- `N Ingreso1`: 562 cells shaped `n/n-n/n`, 101 plain numbers, about 58 cells
  with two such numbers (space or line break between them), 2 `-`, and a
  handful of other shapes.
- `Reingresos` sheet: header on row 3 (`Carpeta`, `Estado`, `Estado resumido`,
  `Tipo de rechazo`, `re ingreso`), 36 data rows. Still outside the contract
  (Source Contract V1, "Auxiliary worksheets").
- No cell in any sheet contains the word `web`.

INFERENCE: the 58 two-value cells line up across `Fecha de ingreso1`,
`N Ingreso1` and `90 dias`. They are most plausibly the first ingreso and the
reingreso written into one cell; the new `…2` columns are the source's way of
separating them, not yet filled.

## 2. Requested changes, decoded and audited

| # | Request (meeting of 2026-10-02) | Reading | What the code does today |
|---|---|---|---|
| R1 | A `Rechazado` means CONAF asked for a new document; every rejection ends as `Aprobado` or `Desistido`. | Rejection is a non-terminal lifecycle state. | FACT: no lifecycle. `Rechazado` is a substring test on `Estado` (`transelec_ingestion/status_rollups.py`, `is_pending_row`, `owner_stage_from_row`, `pending_stage`). `Desistido` appears nowhere in code. `Tipo de rechazo` and `Reingreso_Tec/Legal/RecRep` are projected as text and never interpreted. Contract V1 lists "approval/rejection transition rules" and "relationship of reingresos to current rows" as not established. |
| R2 | A reingreso carries a new fecha and número de ingreso; the rejection type says which document is owed. | Two ingresos per PMF; `Tipo de rechazo` classifies the reingreso. | FACT: one `fecha_ingreso` / `numero_ingreso` per row. The 30-Sept workbook adds the second pair (§1). HYPOTHESIS: `Tipo de rechazo` values correspond to the three `Reingreso_*` flags. |
| R3 | Connect to CONAF's Oficina Virtual. | An outbound link per PMF or ingreso. | FACT: the dashboard has no external links. The portal host and whether an expediente can be opened by N.º ingreso are unverified. |
| R4 | Values edited in the dashboard, downloaded back as a planilla with the edited cells marked `web`, everything else unchanged. | Field-level overrides with provenance, plus an xlsx export in the source layout. | FACT: the API has no PUT/PATCH/DELETE routes; the UI is read-only by design. Provenance is per import and per source row, not per field. The export is an 18-column CSV (TR-FUNC-037). `xlsxwriter` is already a dependency. |
| R5 | The "Pendientes" tab should be "Estado". | Rename and reframe the page as a per-PMF state view. | FACT: tab `AppHeader.tsx`, route `router.tsx`, `PendientesPage.tsx`, links from `ResumenPage.tsx` and `QualityPanel.tsx`, stage labels `lib/pendingStage.ts`, rule copy `lib/rules.ts`. The 2026-09-26 usability note already asked whether "Rechazado" names the catch-all stage well; R1 says it does not. |
| R6 | CONAF has 90 **business** days to resolve. | Deadline = ingreso date + 90 Chilean business days, computed by the platform. | FACT: no business-day arithmetic or holiday calendar exists in Python or TypeScript. The overdue view (`dashboard/src/lib/overdue.ts`, TR-FUNC-031) compares the workbook's `90 dias` date with the server clock; what `90 dias` holds is TR-OPEN-03. |
| R7 | Ingreso dates and office numbers have no fixed format. | Mixed shapes in the source. | FACT: §1 counts. Contract V2 keeps raw text in `source_text_dates` and never splits a two-value cell. |
| R8 | When there are two resolutions, which one applies? | Two ingresos may produce two resolutions. | FACT: no resolution field exists; `summary_view.py` reports resolutions as "No disponible" (TR-FUNC-016). |

## 3. Ordered backlog

Order is by dependency first, then by value against risk. Each item is a
separate pull request from `main`. No item deploys or publishes a workbook
without an explicit instruction.

### PR-0 — Recognize `Fecha de ingreso1/2` and `N Ingreso1/2` (blocking)

The client's current planilla cannot be published until this lands, and
every later item reads the second ingreso.

DECISIONS taken in planning:

- `Fecha de ingreso1` and `N Ingreso1` become documented aliases of
  `fecha_ingreso` and `numero_ingreso`. `Fecha de ingreso2` and `N Ingreso2`
  become new fields `fecha_ingreso_2` (date) and `numero_ingreso_2` (text).
- Tier **optional** (info `columna_opcional_ausente`), the same precedent as
  the AEF block: older workbooks keep importing without new warnings, the
  live 09-Sept import is not forced through re-acknowledgement, and the
  tests that pin warning counts stay valid.
- Parser version becomes `transelec_ingestion.resumen_layout@3`; the schema
  contract string stays `transelec-resumen-v2` and the document is amended.
- The CSV export gains the two columns after `N Ingreso` (18 to 20 fields).
- Migration id `0011`, extending `0010` (the forestry publication migration
  that PR #69 merged on 2026-10-02). `apps/api/tests/test_migration_graph.py`
  moves its head pin accordingly.

Steps and verified constraints:

1. Amend `source-contract-v2.md` first (evidence block from §1, DECISION,
   alias table, persistence, limitations, open questions).
2. `resumen_layout.py`: aliases on the two existing `FieldSpec`s; two new
   `FieldSpec`s inserted after `hoy` so they land at AC/AD and `Empresa` at
   AE. `normalize_header` keeps digits, so the aliases are required and
   cannot collide; `_build_alias_index` raises on a duplicate key. Add an
   `INGRESO_2_FIELDS` tuple and exclude it from `RESUMEN_COLUMNS` in
   `xlsx_contract.py`, otherwise the legacy 30-column fixtures become 32
   columns and the V1 `_source_fields` fallback misreports.
3. `import_projection.py`: two `ColumnProjection`s at the same index as the
   specs (order is checked at import time); the `len == 35` assertion in
   `tests/test_import_projection.py` becomes 37. Text dates in
   `Fecha de ingreso2` already flow through `classify_text_date` and
   `source_text_dates`.
4. Migration `0011`: two nullable columns on `transelec_resumen_row`, no
   index. Update `EXPECTED_TRANSELEC_RESUMEN_ROW_COLUMNS` in
   `apps/api/integration_tests/test_transelec_import_schema.py`.
5. Router: `ResumenRowView` and `_resumen_row_view` gain the fields; the
   column lists and the `q` search are derived.
6. Dashboard: `ResumenRow` type (required fields, so factories, e2e stubs and
   `rowCollection.test.ts` update), `SourceDate` field union, the drawer's
   tramitación block shows ingreso 1 and 2 side by side and one notice when
   the published version has no such columns (same pattern as `aefInSource`).
7. Tests: synthetic 30-Sept layout, text date in `fecha_ingreso_2`, the
   09-Sept layout still importing with info only, the position-dependent
   duplicate-header test, and a private test gated by
   `TRANSELEC_PRIVATE_WORKBOOK_30SEP` asserting 728 rows, no errors, letters
   Y/Z/AC/AD, zero filled rows in both new fields and 58 `multiple_dates` in
   `fecha_ingreso`. Nothing asserts a business value.
8. Spanish note on the 30-Sept planilla, linked from the product README.

### PR-1 — "Estado" page: rejection as in progress, reingreso visible

1. Rename the tab, route and page from Pendientes to Estado, keep the old
   route as a redirect for one release, update the UX document §4.3 and the
   e2e specs.
2. New server-side basis `lifecycle_pmf_v1` beside `status_rollups.py`,
   reading the first row's `Estado`, `Estado resumido`, `Tipo de rechazo`,
   the three `Reingreso_*` flags, `numero_ingreso` and `numero_ingreso_2`:
   `sin_ingreso`, `ingresado`, `rechazado_pendiente_reingreso` (with its
   `tipo_rechazo`), `reingresado`, `aprobado`, `desistido`, and
   `sin_clasificar` for every combination not covered. Nothing is guessed.
   The legacy bases `pending_priority_legacy` and `pending_stage_legacy`
   stay reachable, as the parity rule requires.
3. The page leads with the lifecycle buckets; the queue gains `Tipo de
   rechazo`, `Reingreso` and `Ingreso 2`; attention red is reserved for
   `rechazado_pendiente_reingreso`; `rules.ts` explains the basis.
4. Optional here: an "Abrir Oficina Virtual CONAF" link next to the N.º
   ingreso in the drawer, base URL in configuration, no deep link until the
   portal's scheme is confirmed.
5. All copy marked provisional until Campo Digital confirms the vocabulary.

### PR-2 — 90 business days (after PR-0)

1. Dependency: a Chilean national holiday calendar (candidate: the Python
   `holidays` package, country `CL`; verify version, licence and the
   `country_holidays` API before adding under the `transelec` extra). No
   network at runtime. The calendar version is returned by the API so a
   calendar change is auditable.
2. Pure module `transelec_ingestion/plazo_conaf.py` with an injected
   `is_holiday` callable. Per PMF: base date is `fecha_ingreso_2` when present
   else `fecha_ingreso`, resolved with `resolve_pmf_field` so raw text yields
   `texto_sin_fecha` and disagreeing rows yield `conflicto`; deadline is +90
   business days; business days elapsed and remaining; `vencido` when the
   deadline is before the server's observation date and the PMF is not
   `Aprobado` (mirrors the legacy predicate). A cross-check compares the
   computed deadline with the workbook's `90 dias`.
3. Endpoint `GET /transelec/plazos` with the usual filters; observation time
   is the server's, in `America/Santiago`. Bases `plazo_conaf_90_habiles_v1`
   and `vencimiento_columna_90_dias_legacy`.
4. The overdue panel gets a basis toggle and the new columns; counts of rows
   that could not be computed are shown in the lead; the e2e stubs gain the
   route.
5. INFERENCE to confirm: Monday to Friday excluding national holidays, day 1
   being the first business day after the ingreso (Ley 19.880 art. 25).
   Inclusive/exclusive counting and whether the clock stops during
   observaciones are open questions.

### PR-3 — Dashboard edits exported back to the planilla marked `web`

Architectural: it changes the product's read-only invariant and needs its
own design document before any plan. Scope sketch for that design:

- An override store keyed by row identity and field, with value, author,
  timestamp and the source value seen at edit time; role gated; audited.
- API rows carry their overrides with `source: "web"`; the UI shows a `web`
  chip and keeps the raw source visible.
- On publishing a new version, an override whose source cell now equals it
  retires; one whose source cell changed elsewhere is flagged in Calidad,
  never applied silently.
- `GET /export.xlsx` built with `xlsxwriter` reproducing the published
  version's header row and column order, writing override values and marking
  them (an `Origen` column per row and a cell comment or fill); the CSV
  export stays.
- Identity fields (`PMF`, `Rol`, `N Predio`, `ID_Predo_Unico`) are not
  editable.

## 4. Open questions for Campo Digital

Listed in Spanish, for Javier, in
[the meeting note](../es/2026-10-02-reunion-cambios-y-preguntas.md). In
short: the lifecycle vocabulary (`Desistido`), the meaning of `Tipo de
rechazo` against the `Reingreso_*` flags, whether the `…2` columns always hold
the reingreso and whether the 58 two-value cells will be split at source,
whether more than two ingresos can occur, which ingreso starts the 90-day
clock and whether it restarts, what `90 dias` holds today, how two
resolutions are handled, the Oficina Virtual URL, the editing rules for PR-3,
and the official `N Ingreso` format.

## 5. Verification per PR

- Backend: `uv run pytest products/transelect/tests apps/api/tests`, then
  the integration subset on the disposable test database
  (`apps/api/integration_tests/test_transelec_*`) and
  `scripts/migration_check.py`. Never `make persistence-check` from a
  workbook session.
- Dashboard: `npm test`, `npm run lint`, `npm run build`, `npm run test:e2e`
  in `products/transelect/dashboard`.
- PR-0 end to end: upload, validate-and-project, review the layout report in
  Datos → Importar; Y/Z must bind to ingreso 1 and AC/AD to ingreso 2 with no
  error. Publishing is a separate, explicit instruction.
- Documentation: `python scripts/check_doc_links.py` after adding files.

## Related documentation

[Transelec product](../../README.md) ·
[Source Contract V2](../source-contract-v2.md) ·
[Functional parity matrix V1](../audit/2026-09-02-functional-parity-matrix-v1.md) ·
[Reunión del 02-10-2026 (español)](../es/2026-10-02-reunion-cambios-y-preguntas.md)
