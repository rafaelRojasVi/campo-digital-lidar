# Transelec — Javier source forensic audit (v0, Actualizable, workbook)

## Status

Evidence record. Discovery/specification session, no implementation.

## Scope and method

Forensic, read-only audit of the four external source artifacts under
`03_Proyecto_Transelec/02_Datos_Entrada/` (external OneDrive source root,
files never copied into Git). Each HTML was statically analyzed (full-file
read, embedded-script parsing) and dynamically verified in a real headless
browser (Playwright/Chromium) served from a throwaway `127.0.0.1` static
server, never published externally; every interaction claimed "worked" below
was actually clicked/typed, not inferred from code reading alone, unless
explicitly marked otherwise. The workbook was profiled read-only with
Python/openpyxl. No client row-level data (names, RUTs, addresses, folios,
coordinates) appears anywhere in this document — only structural facts,
aggregate counts, and closed-vocabulary business categories (e.g. the 4
values of `Estado resumido`), which are business taxonomy, not personal data.

## 1. File identity (independently reconfirmed)

| File | SHA-256 | Size | Notes |
|---|---|---|---|
| `Dashboard_Transelec_14Ago2026_v0.html` | `b3742ac4e2d64adca94627a9a32453e2a685164319c16e8a15152e23fa1017fe` | 633,710 B | Title "Seguimiento CONAF · Campo Digital"; frozen 14-Aug-2026 snapshot; **no** Excel-refresh capability |
| `Dashboard_Transelec_14Ago2026_Actualizable.html` | `c60961c72a4b3e3b21e66a3cf8ad6fc6e8f73cd17612cf7018e69cc4b2d2680e` | 644,327 B | Same title/branding; **adds** a fully client-side XLSX refresh path |
| `Idea_Transelec.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0 B | **FACT — empty.** No requirement content exists in this file; nothing was inferred from it. |
| `PlanillaMaestra-CD_14Ago2026.xlsx` | `42d4afae62c2225634bf77c46efa54f6be4e6127dabab5f868e90736c7c8ff43` | 15,716,792 B (~15.0 MiB) | Filesystem mtime 2026-09-02 10:14 — modified the same morning as this audit. Headline aggregates (729/159/272) are unchanged from the 2026-08-27 evidence in `source-contract-v1.md`, but the file is not byte-identical to whatever produced that document — do not assume future re-fingerprints will show the same content. |

Both HTML files are fully self-contained (zero external `<script src>`/`<link href>`, logos inline as base64) — they work from a bare `file://` URL. Neither produced a real application-level console or network error across a full interaction pass; the only log entries were the test harness's own harmless `favicon.ico` 404s.

## 2. Workbook structure (`PlanillaMaestra-CD_14Ago2026.xlsx`)

7 worksheets, all `visible`: `Resumen`, `Reingresos`, `Resumen 16Feb26`, `Resumen 28Ene26`, `Resumen 05Nov25`, `Pendientes`, `Urgentes 07May`. No hidden rows/columns, no data validations, no conditional formatting, no named ranges, no Excel Tables anywhere in the workbook.

### `Resumen` — re-verifies `source-contract-v1.md` exactly

- **FACT** — 729 rows have a non-blank `PMF` (col D); 159 distinct `PMF`; 272 distinct populated `ID_Predo_Unico` (col AA, 100% filled). All three match the 2026-08-27 evidence exactly, despite today's file modification.
- **FACT** — Two columns are both literally named `Carpeta`: **E** (159 distinct — 1:1 with PMF) and **AC** (32 distinct — a coarser grouping). They are genuinely different data, not duplicates of each other. Column identity must stay positional, confirming the existing contract's decision.
- **FACT** — Column **AE** (31) is confirmed blank, the documented business-table/auxiliary boundary. Columns **AF:AY** are confirmed to be the *flattened output of Excel PivotTables* (one per `Empresa` filter state), cross-tabulating `ID_Predio_UnicoII` by a 5-category label set (`Aprobado`/`En tramite`/`Pendiente`/`Tachado`/`Total general`) that exactly matches `Estado resumido`'s own 4 distinct values — strong convergent evidence that `Estado resumido` is Transelec's canonical status vocabulary and that both HTML dashboards' KPI/status charts are reproducing this same pivot.
- **NEW FACT** — Column **AB** (`Tramite`) is a real, in-boundary (A:AD) column that is 100% empty across all 729 rows — currently inert but must still be preserved in any V1 projection (the contract owns A:AD, not "A:AD minus empty columns").
- **NEW FACT — formula evidence**:
  - **AA** (`ID_Predo_Unico`) is a live formula in all 729 rows: `=PMF & "-" & Rol & "-" & N Predio`. This is the exact, precise composition of the "provisional predio identity" `source-contract-v1.md` already flags as provisional. Because `Rol` (col O, 100% filled) and `N Predio` (col P, 99.7% filled) are each independently imperfect, the composite can encode placeholder segments in edge rows.
  - **W** (`Hoy`) is a live `=NOW()` formula in 129/729 rows; the remaining ~598 rows hold a **static cached value that is itself type-inconsistent** — some are real Excel datetimes, others are literal Spanish-formatted date **text** (e.g. a sampled cell literally reads `"08 de octubre de 2024"` as a string, not a date). This sharpens the existing "`Hoy` is not ingestion time" rule into a concrete parsing hazard: `Hoy` is both semantically wrong to use as ingestion time *and* structurally non-deterministic *and* type-mixed within the same column.
  - **V** (`90 dias`) is a **static date, not a formula**, and is **not** simply `Fecha de ingreso + 90 days` (sampled gap: 133 days, not 90). **OPEN QUESTION for Javier** — what `V` actually represents cannot be determined from data alone.
- **FACT — merged cells**: 277 vertical merges, all confined to columns **Y** (`ID_Predio_UnicoII`, one value per predio-group, 37% filled/272 distinct) and **Z** (`ID_PMF`, one value per PMF-group, 22% filled/159 distinct). These are per-group annotations, not per-row values — a naive per-row read returns mostly-null for both, which is why the existing contract already treats `AA` (not `Y`/`Z`) as the authoritative predio identity. If the target design ever wants `Y`/`Z` faithfully it must either preserve the mostly-null shape as-is or explicitly forward-fill and document that as a transformation DECISION, not a source fact.
- **Full A:AD per-column profile** (fill rate, distinct count, sanitized shape) is recorded in the underlying research notes; headline: 27 of 30 fields are fully or near-fully populated, `Reingreso_Tec`/`Reingreso_Legal`/`Reingreso_RecRep` are sparse (20-23% filled) flag-like columns, `Tipo de rechazo` is populated for 25% of rows.

### Auxiliary sheets — structure only, none ingested by V1

- **Historical `Resumen <date>` sheets (3)** — **correction to an assumption implicit in prior docs' phrasing**: these are **not row-level historical snapshots**. Each is a tiny 12-14-row pivot-style status-count table (rows = a *different*, more granular 5/6-category vocabulary — `Pendientes`/`No ingreso`/`Desistida`/`Recurso`/`Rechazos`/`Total` — columns = `Tipo de propietario` categories). This vocabulary is not obviously reconcilable with `Estado resumido`'s 4 categories and should not be assumed equivalent without stakeholder confirmation.
- **`Pendientes`** (30 rows) and **`Urgentes 07May`** (~36 rows) are both unstructured 2-column free-text lists with no `PMF`/`ID_Predo_Unico` column — no clean join key back to `Resumen` exists without text parsing. Confirms `source-contract-v1.md`'s caution that both "require separate schema and semantics review."
- **`Reingresos`** — header starts at C3, 15 columns; this pass could not confirm the true last data row (openpyxl's naive `max_row` of >1,000,000 is a used-range artifact, not real data) — flagged as a LIMITATION for any future ingestion-scoping pass, not resolved here.

## 3. HTML v0 — full inventory

633,710 bytes, 11 sections, 8 KPI cards, 2 CSS-only donut charts, 2 tables, 21 live-tested controls (6 filter inputs, 3 top-level buttons, 8 dual-purpose FAQ/quick-action cards, 2 pendingzone buttons, 2 report buttons), 1 verified CSV export + 1 inferred TXT export + verified print/PDF. 729 embedded rows / 30 fields; live-verified KPI/report totals (159 PMF, 272 predios, 221 roles, 164.63 ha, 108 Aprobados, 48 En trámite, 9 Pendientes prioritarios, 148 con servidumbre) cross-check exactly against `source-contract-v1.md` and the portal's "164,63 ha" marketing fact.

Real, evidenced findings (none are hard breakage — every control does *something* when clicked):

- **Divergent status rules, live-proven**: filtering to the substring `"rechaz"` returns 8 PMF whose recomputed KPIs show `Aprobados=0, En trámite=8` — i.e. the detailed-`Estado`-based "pending priority" rule and the `Estado resumido`-based approval-rate rule can disagree about the same rows. This is the same ambiguity `source-contract-v1.md` already flags as unresolved, now precisely characterized and reproduced live.
- **Hardcoded "today"**: the "¿Qué ingresos superaron 90 días?" filter uses a literal `new Date('2026-08-26')`, not `new Date()`. It can never advance.
- **3 label/behavior-mismatch controls**: `quick('surface')`, `quick('company')`, `quick('lookup')` each promise more (a comparison view, a lookup, a surface breakdown) than they deliver (a scroll, a dropdown focus, a search-box focus).
- **8 of 30 schema fields wired into the embedded data but read by zero JS functions**: `Tramite`, `N° Area de Ref`, `Rol Ref`, `Predio Ref`, `Superficie de total de corta`, `ID TRANSELEC`, `ID_Predio_UnicoII`, `ID_PMF`.
- **Upstream data-quality defect, not an HTML bug**: `Estado`'s 13 distinct values include case-duplicate pairs ("En Evaluacion" vs "En evaluacion") from inconsistent source data entry.
- **Only one `Carpeta` key survives in the embedded JSON** — JSON object literals can only hold one value per key, so if the source truly has two `Carpeta` columns (confirmed above), v0's export step already silently discarded one of them before embedding.
- CSV export is a hardcoded 17-of-30-field subset, including raw `Estado` but not `Predio Ref`. **Exact field list, confirmed by direct read of `exportCSV()` this session**: `PMF, Carpeta, PAS, Estado, Estado resumido, Tipo de rechazo, Tipo de propietario, Rol, N Predio, N Area de Corta, Superficie de corta, Fecha de ingreso, N Ingreso, Empresa, ID_Predo_Unico, Sector, Observación auxiliar` (in this order; `;`-delimited, UTF-8 BOM). `Carpeta` here is header-text-keyed, so it silently resolves to whichever of the two source `Carpeta` columns JS object-literal key collision leaves standing (see the "only one `Carpeta` key survives" finding above) — not independently confirmed which one wins without tracing the exact row-construction order, so treat this export's single `Carpeta` value as ambiguous provenance, not a confirmed choice between E and AC.

## 4. HTML Actualizable — full inventory

644,327 bytes, 13 sections, the same 8 KPI cards, 2 donut charts, 3 tables (adds an owner-status breakdown table), 22 live-tested controls (adds "Actualizar base Excel"), 3 export mechanisms + clipboard copy. Same embedded 729×30 dataset; a `BASE` constant additionally records `roles: 221, surface: 164.6288` (not previously written down in `source-contract-v1.md`, now confirmed as evidence).

Real, evidenced findings beyond what v0 already had:

- **Same hardcoded-`2026-08-26`-today bug**, independently confirmed present in Actualizable's own overdue quick filter — this is not a v0-only defect, it is baked into both files identically. **Any target design that reuses "static file with baked-in today" reproduces this defect structurally** — the fix is computing "today" server-side at read time, not a one-line patch to either file.
- **A new, second status-derivation rule** (`ownerStage()`, used only by the new owner-status table) overrides `Estado resumido` in exactly one case: any row whose raw `Estado` contains "rechaz" is shown as "Rechazado" in that one table, regardless of what `Estado resumido` says. Since most `Estado`="Rechazado" rows actually carry `Estado resumido` ∈ {Aprobado, En tramite} (a rejection later superseded by an approved recurso, most plausibly), **the same row is classified differently in two different sections of the same file** depending on which section's author trusted which field. This is a genuine, evidenced internal inconsistency in Javier's own current dashboard, not a hypothetical one.
- **Confirmed duplicate-`Carpeta`-column collapse in two places, not one**: both the static embed (same defect as v0) *and* the live client-side Excel-refresh path (`updateFromExcel`, header-text-keyed row objects) collapse the two source `Carpeta` columns to one value on every refresh — this directly contradicts the backend Source Contract V1's positional-column decision and would keep happening every time Javier refreshes the file.
- **Zero schema validation on refresh**: the hand-rolled client-side XLSX parser (~110 lines implementing its own ZIP/DEFLATE/sharedStrings reader with no library) has no column-position or column-count check equivalent to the backend's A:AD/blank-AE-separator contract. A renamed, reordered, or extra column would silently produce a `DATA` array with wrong/missing keys, most likely surfacing as blank/`NaN` KPI cards rather than a clear error — it fails open, not closed.
- **CSV export field set changed**: Actualizable's 17-of-30 export includes `Predio Ref` (new) but drops raw `Estado` (present in v0's export) — a genuine, unexplained difference in "what's useful to export," not an improvement or regression on its face; needs a canonical answer. **Exact field list, confirmed by direct read of `exportCSV()` this session**: `PMF, Predio Ref, Carpeta, PAS, Estado resumido, Tipo de rechazo, Tipo de propietario, Rol, N Predio, N Area de Corta, Superficie de corta, Fecha de ingreso, N Ingreso, Empresa, ID_Predo_Unico, Sector, Observación auxiliar` (same order/format as v0's, `Predio Ref` swapped in for raw `Estado` at position 2). `Observación auxiliar` renders empty for every row in the reviewed snapshot's embedded data — consistent with the footer's own claim that "la hoja 'Pendientes' se usa sólo como observación auxiliar" (line 54's `.foot` text), i.e. this column is meant to hold a manually-cross-referenced note from the `Pendientes` sheet, not a `Resumen` A:AD field. Populating it in V1 would require exactly the auxiliary-sheet merge this design's non-goals already rule out — ship the column (for structural familiarity) but leave it empty, not wired to any merge, until Javier asks for it.
- **Report template — CORRECTION, this was previously miscited as already captured**: the functional parity matrix's TR-FUNC-034 row claimed this template was "verbatim ... captured in the source audit," but no prior version of this document actually contained the text. Confirmed by direct read of `renderReport()` this session, both files (near-identical, v0's second paragraph differs slightly in wording): `` `REPORTE EJECUTIVO · SEGUIMIENTO CONAF\nCorte de información: 14-08-2026\n\nEl alcance seleccionado comprende ${p.length} PMF, ${props} predios identificados y ${roles} roles, con ${fmt(sup)} ha de superficie de corta.\n\nEstado resumido: ${approved} PMF aprobados (${fmt(rate)}%), ${progress} en trámite y ${pending} PMF con registros Pendiente o Tachado. Se identifican ${ease} predios con servidumbre firmada.\n\nCriterio: los PMF y predios se cuentan sin duplicados; la superficie corresponde a la suma de las áreas de corta filtradas. El N.º de ingreso se vincula al PMF correspondiente. Las resoluciones no pueden verificarse porque la fuente no incluye un campo específico para ellas.` `` (Actualizable's wording; v0's second paragraph reads "... progress} en trámite y ${pending} PMF prioritarios por no haber sido presentados o por registrar rechazo vigente." instead). The literal `Corte de información: 14-08-2026` is a hardcoded snapshot date in both files — the target design must not reproduce this as a frozen literal (same defect class as the hardcoded "today" bug); substitute the active import's own publish/snapshot date instead, per this document's already-established rule that "today"/freshness must be computed from real provenance, never a baked-in string.
- **Refresh has zero persistence**: purely in-tab memory; reload or reopen reverts to the embedded 14-Aug snapshot; no write-back to the source workbook (footer's claim "no modifica la planilla de origen" is accurate); no way to share an updated view except re-sending the whole HTML file by hand. **This exact gap is what the target upload → validate → import → publish pipeline exists to close.**
- **"¿Cómo avanza cada empresa?"** quick action only focuses the Empresa dropdown — the question's own wording ("cada empresa", i.e. a per-company comparison) is not actually answered by any rendered view; only `Tipo de propietario` gets a comparison table. Flagged as an OPEN QUESTION for the parity matrix: genuinely missing function, or is filter-then-read-KPIs sufficient?
- New "Predios de reforestación" chip section reads `Predio Ref` — a field v0 left completely unused — meaning at least one of v0's 8 "dead" fields was revived in Actualizable. Whether the other 7 remain dead in Actualizable was not independently re-confirmed field-by-field in this pass (the Actualizable audit fork did not reproduce a full dead-field list); flagged as a LIMITATION — a direct grep diff of the two files' JS is a cheap follow-up before implementation if exact parity on this point matters.

## 5. Semantic version diff — v0 vs Actualizable

**Directionality**: Actualizable is a superset-plus-enhancement of v0. No section, KPI, chart, control, or export present in v0 was found to be dropped in Actualizable.

### Present only in Actualizable (new since v0)

| Function | Evidence |
|---|---|
| Client-side Excel-refresh (`Actualizar base Excel` → `updateFromExcel`) | ACT-CTRL-007; absent in v0 (confirmed no `<input type="file">`, no XLSX-reading code anywhere in v0) |
| "Estado resumido" status-hero block (predio-grain 4-state counts) | ACT-SEC-004; no v0 equivalent section |
| "Predios de reforestación" chip list | ACT-SEC-005; reads `Predio Ref`, dead in v0 |
| "Estado por tipo de propietario" owner-status table + `ownerStage()` derived-status rule | ACT-SEC-008; no v0 equivalent table or rule |
| Detail table 12th column ("Predio de reforestación") | ACT-SEC-011 vs v0's 11-column V0-TBL-002 |

### Same intention, wording/implementation changed

| Function | v0 | Actualizable |
|---|---|---|
| "Pending" FAQ label | "¿Qué falta presentar a CONAF?" | "¿Qué figura pendiente?" (same `type='pending'`/`showPending()` behavior; only the question text changed) |
| CSV export field set (17 of 30 fields, same count) | includes raw `Estado`, excludes `Predio Ref` | includes `Predio Ref`, excludes raw `Estado` |
| Pending-zone detail table | 7 columns | 9 columns (enhanced, same purpose) |

All other 7 FAQ/quick-action labels (`lookup`, `easement`, `surface`, `rejected`, `legal`, `company`, `overdue`) are byte-identical in both files, same `type` key, same behavior.

### Broken or fragile in both versions identically (not introduced by Actualizable, not fixed by it either)

- Hardcoded `2026-08-26` "today" in the 90-day overdue filter.
- `quick('rejected')`/`quick('legal')` as blunt whole-row substring searches rather than field-scoped predicates.
- Divergence between the detailed-`Estado`-based "pending" rule and the `Estado resumido`-based approval rate for the same underlying rows.
- Duplicate `Carpeta` column silently collapsed to one value.
- Three FAQ cards (`surface`, `company`, `lookup`) under-deliver on their own promised behavior.

### Ambiguous conflicts requiring a named decision (Javier)

1. Which `Carpeta` column (E, AC, or both, and how labeled) should the target UI show, given the backend already preserves both positionally?
2. What is the canonical PMF-level / predio-level status rollup rule when a PMF/predio's rows disagree? (Neither file has one true rule — v0/Actualizable's shared "first source row wins" is a `Map`-insertion-order artifact, not a stated business rule, and Actualizable's `ownerStage()` is a second, disagreeing ad-hoc rule.)
3. What does the `90 dias` column actually represent, given it is not `Fecha de ingreso + 90`?
4. Should the CSV export include raw `Estado`, `Predio Ref`, both, or a field set Javier defines explicitly?
5. Is a per-empresa comparison view (implied by "¿Cómo avanza cada empresa?") a real missing function, or is filter+KPI sufficient?
6. Should merged-cell columns `Y`/`Z` be preserved mostly-null (source-faithful) or forward-filled (a stated transformation) if ever surfaced?

None of the above conflicts is resolved by this document — each becomes a named open-decision row in the implementation plan, owned by Javier where business meaning is involved.

## Related documentation

- [Transelec Source Contract V1](../source-contract-v1.md)
- [Functional parity matrix](2026-09-02-functional-parity-matrix-v1.md)
- [Implementation gap analysis](2026-09-02-implementation-gap-analysis-v1.md)
- [Target architecture spec](../../../../docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-design.md)
