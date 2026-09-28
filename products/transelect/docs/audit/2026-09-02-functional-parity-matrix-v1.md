# Transelec — Javier functional parity matrix (TR-FUNC-*)

## Status

Controlling artifact for the target Transelec slice. Every visible functional
section and every interactive handler identified in
[the source forensic audit](2026-09-02-source-forensic-audit-v1.md) has
exactly one row below and exactly one disposition. Nothing from either HTML
disappears silently. Business rules that are provisional in the source
(status rollup, `90 dias` meaning, duplicate `Carpeta` handling) are marked
**PROVISIONAL** in the Acceptance test column: V1 replicates Javier's
existing, current dashboard behavior faithfully (bugs included, unless the
bug is unambiguous and mechanically fixable — see TR-FUNC-031) rather than
inventing a "better" rule, so Javier is never asked to accept an
unrequested behavior change silently.

Legend — **Disposition**: `implement` (build it) · `merge` (same underlying
function/code path as another row, one or more UI entry points) · `blocked`
(cannot be meaningfully implemented before a named stakeholder decision).
No row is marked `superseded` in this matrix: no evidence surfaced in this
audit justifies dropping any function Javier's dashboards actually perform.
**Confidence**: FACT (directly observed in code/live test) ·
INFERENCE (strongly supported, not directly proven) · OPEN (undetermined
from evidence).
**Main/PR47/UI branch** columns report only what the branch-archaeology
fork directly confirmed present; "not found" means absent from the audited
evidence, not proven absent from the branch in every possible location.

Row count: **46**. Category counts: KPIs 8, charts 2, status/quality
indicators 6, filters 7, quick-actions 8, pendingzone 2, report/export 6,
main table 1, upload/refresh 1, structural/chrome 6 — summing to every
section (11 in v0 / 13 in Actualizable), every KPI/chart/table, and every
one of the 21 (v0) / 22 (Actualizable) live-tested controls, with the two
literal code-level duplicate pairs (`Limpiar`≡`Volver al total`,
`quick('pending')`≡`Ver sólo PMF pendientes`) merged into single rows.

---

## A. KPI cards (TR-FUNC-001 – 008)

Present identically in v0 and Actualizable **except TR-FUNC-007** (see its row — correction below). Grain: PMF-dedup unless noted. Dedup tie-break for a PMF/predio with disagreeing rows is **first source row encountered** — a `Map`-insertion-order artifact of the current HTML, not a stated business rule (PROVISIONAL, see TR-FUNC open decision list).

| ID | Label (es) | Job/question | Source fields | Rule | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-001 | PMF | ¿Cuántos PMF hay en el alcance actual? | `Resumen.PMF` | distinct count over filtered view | none / `pmf_view.build_summary()` (unverified rule) / `ExecutiveKpis.tsx` | implement | Unfiltered active import on synthetic fixture returns `COUNT(DISTINCT pmf)` matching fixture; value updates on every filter change | FACT |
| TR-FUNC-002 | Predios | ¿Cuántos predios identificados hay? | `ID_Predo_Unico`, fallback `[PMF,Rol,N Predio]` | dedup by `ID_Predo_Unico`, composite fallback if blank | none / `pmf_view.py` / `ExecutiveKpis.tsx` | implement | Matches `COUNT(DISTINCT id_predio_unico)`; fallback path covered by a fixture row with blank `id_predio_unico` | FACT |
| TR-FUNC-003 | Roles | ¿Cuántos roles distintos hay? | `Rol` | distinct count | none / not found / `ExecutiveKpis.tsx` | implement | Matches `COUNT(DISTINCT rol)` | FACT |
| TR-FUNC-004 | Superficie | ¿Cuál es la superficie de corta total? | `Superficie de corta` | `sum()` over filtered view | none / `pmf_view.py` / `ExecutiveKpis.tsx` | implement | Matches `SUM(superficie_corta)`; `Superficie de total de corta` stays unused in V1 pending TR-OPEN-03 | FACT |
| TR-FUNC-005 | Aprobados | ¿Cuántos PMF están aprobados? | `Estado resumido` | PMF-dedup, `Estado resumido == 'Aprobado'` | none / `pmf_view.py` (unverified rollup) / `ExecutiveKpis.tsx`/`StatusDistribution.tsx` | implement, **PROVISIONAL** | Matches current-HTML output on the synthetic fixture bit-for-bit; rollup rule change requires Javier sign-off first | FACT (value) / OPEN (rule) |
| TR-FUNC-006 | En trámite | ¿Cuántos PMF están en trámite? | `Estado resumido` | same as 005, `=='En tramite'` | same as 005 | implement, **PROVISIONAL** | same pattern as 005 | FACT / OPEN |
| TR-FUNC-007 | Pendientes prioritarios | ¿Cuántos PMF requieren atención prioritaria? | detailed `Estado`, `N Ingreso` | **CORRECTION — v0 and Actualizable implement genuinely different rules, confirmed by direct code read this session (not merely a wording change); an earlier version of this row implied one shared rule.** v0's `isPendingPMF`: `!N_Ingreso \|\| Estado.toLowerCase().includes('rechaz')`. Actualizable's `isPendingPMF`: `Estado resumido.toLowerCase() === 'pendiente' \|\| === 'tachado'` — a completely different field and predicate. The ratified rule (and the one the backend implements as `pending_priority_legacy`) is **v0's** — **independently confirmed to diverge from TR-FUNC-005/006's rule for the same rows** (live-tested both files) | none / not found (no evidenced equivalent) / not found | implement, **PROVISIONAL** | Replicate v0's `isPendingPMF` exactly as evidenced (this is what `pending_priority_legacy` implements); flag divergence from 005/006 in UI copy, don't silently reconcile; UI copy must use v0's card wording, not Actualizable's, since Actualizable's wording describes the *other* rule | FACT (value+divergence+v0-vs-Actualizable rule mismatch) / OPEN (canonical rule) |
| TR-FUNC-008 | Con servidumbre | ¿Cuántos predios tienen servidumbre firmada? | `Tipo de propietario` | distinct predio where field contains "servidumbre" (case-insensitive) | none / `pmf_view.py` / `ExecutiveKpis.tsx` | implement | Matches count on fixture | FACT |

## B. Charts (TR-FUNC-009 – 010)

| ID | Label (es) | Job/question | Source fields | Rule | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-009 | Avance de aprobación — por predios | ¿Qué proporción de predios está aprobada/en trámite/pendiente? | `Estado resumido` | 3-bucket split (Aprobado / En trámite / Pendiente-o-Tachado), predio-grain | none / `pmf_view.py` / `StatusDistribution.tsx` | implement | 3 segment values sum to `TR-FUNC-002`'s total; percentages match fixture | FACT |
| TR-FUNC-010 | Avance de aprobación — por PMF | Same, PMF-grain | `Estado resumido` | same 3-bucket split, PMF-grain | none / `pmf_view.py` / `StatusDistribution.tsx` | implement | 3 segment values sum to `TR-FUNC-001`'s total | FACT |

## C. Status / quality indicators (TR-FUNC-011 – 016)

| ID | Label (es) | Job/question | Version | Source fields | Rule | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|---|
| TR-FUNC-011 | Estado resumido (hero, predio-grain) | Vista rápida del estado predial | Actualizable only | `Estado resumido` | 4-state count, predio-grain (distinct denominator from PMF-grain KPIs — same field, different grain, easy to misread as agreeing) | none / not found / not found | implement | Counts sum to `TR-FUNC-002`'s total; UI copy makes the grain explicit (predios, not PMF) | FACT |
| TR-FUNC-012 | Predios de reforestación (chips) | ¿Qué predios de referencia existen? | Actualizable only | `Predio Ref` (dead field in v0, revived here) | distinct non-blank values, chip list + overflow | none / not found / not found | implement | Chip count matches `COUNT(DISTINCT predio_ref)` on fixture with an overflow case | FACT |
| TR-FUNC-013 | Estado por tipo de propietario (tabla) | ¿Cómo avanza cada tipo de propietario? | Actualizable only | `Tipo de propietario`, `Estado`, `Estado resumido` | predio-grain; **`ownerStage()` overrides `Estado resumido` when raw `Estado` contains "rechaz" — a second, disagreeing status rule vs. TR-FUNC-005/006/011 for the same rows, confirmed live** | none / not found / not found | implement, **PROVISIONAL** (corrected from an earlier "blocked" disposition — see TR-OPEN-01 below) | Ships Javier's existing `ownerStage()` rule as-is, under the explicit basis identifier `owner_stage_legacy`, named visibly in the API response (not silently reconciled with 005/006/011's `estado_resumido_first_row`); does not require Javier's canonical-rollup decision to ship — only the *unification* of this rule with the others is blocked, not this row's own implementation | FACT (inconsistency) / OPEN (canonical unification) |
| TR-FUNC-014 | Calidad — filas sin ID predial único | ¿Cuántas filas no tienen `ID_Predo_Unico`? | v0 + Actualizable | `ID_Predo_Unico` | count of blank (currently 0/729 — always renders 0 today) | none / not found / not found | implement | Value equals `COUNT(*) WHERE id_predio_unico IS NULL/blank` on fixture including a deliberately-blank row | FACT |
| TR-FUNC-015 | Calidad — PMF sin N° ingreso | ¿Cuántos PMF no tienen N.º de ingreso? | v0 + Actualizable | `N Ingreso` | PMF-deduped (first-row-wins again) count of blank | none / not found / not found | implement, **PROVISIONAL** (dedup rule) | Matches fixture; inherits the same TR-FUNC-001 dedup tie-break | FACT |
| TR-FUNC-016 | Calidad — N° de resolución | — | v0 + Actualizable | none (field doesn't exist in source) | permanent static literal "No disponible" | none / not found / not found | implement | Static label rendered; not a computed value — cheapest row in the matrix, included for completeness per the no-silent-disappearance rule | FACT |

## D. Filters (TR-FUNC-017 – 023)

Confirmed filter semantics (both files, identical): the 5 multi-selects are **AND'd together**; **within** one multi-select, selected options are **OR'd**; free-text search is a case-insensitive substring match **OR'd across every one of the 30 fields**, AND'd with the multi-selects. All client-side today; target design must reproduce this exact combination logic server-side (or client-side over a bounded active-version row set) so KPIs, charts, and tables never disagree under a given filter state — this consistency is itself a parity requirement, not an implementation detail.

| ID | Label (es) | Job/question | Source field | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-017 | Búsqueda general | Buscar cualquier término en cualquier campo | all 30 fields | none / `filter_resumen_rows()` (partial — not confirmed all-30-field OR) / `FilterPanel.tsx` | implement | `"rechaz"` on fixture returns the same row set live-tested in the source audit's fixture-equivalent | FACT |
| TR-FUNC-018 | Filtro Estado resumido | Filtrar por estado resumido | `Estado resumido` | none / `filter_resumen_rows()` / `FilterPanel.tsx` | implement | Multi-select OR within field verified | FACT |
| TR-FUNC-019 | Filtro Empresa | Filtrar por empresa | `Empresa` | none / `filter_resumen_rows()` / `FilterPanel.tsx` | implement | Same pattern | FACT |
| TR-FUNC-020 | Filtro PAS | Filtrar por PAS | `PAS` | none / `filter_resumen_rows()` / `FilterPanel.tsx` | implement | Same pattern | FACT |
| TR-FUNC-021 | Filtro Sector | Filtrar por sector | `Sector` | none / `filter_resumen_rows()` / `FilterPanel.tsx` | implement | Same pattern | FACT |
| TR-FUNC-022 | Filtro Tipo de propietario | Filtrar por tipo de propietario | `Tipo de propietario` | none / `filter_resumen_rows()` / `FilterPanel.tsx` | implement | Same pattern | FACT |
| TR-FUNC-023 | Limpiar / Volver al total | Restablecer todos los filtros | — | none / not found / not found | **merge** — `Limpiar` (top toolbar) and `Volver al total` (pendingzone) call the identical `resetFilters()` in both HTML files; one function, two UI entry points | Clicking either entry point from any filtered state returns to the full unfiltered row view for the active import (729 rows in the reviewed snapshot — an evidenced illustration, not a fixed count a future import must match); both entry points present in the target UI | FACT |

## E. Quick actions / FAQ cards (TR-FUNC-024 – 031)

All 8 share the `type`→`quick(type)` dispatch pattern; 7 of 8 have byte-identical Spanish labels between v0 and Actualizable (only `pending`'s label changed — both wordings preserved below).

| ID | `type` | Label(s) (es) | Behavior (FACT) | Assessment | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-024 | `pending` | v0: "¿Qué falta presentar a CONAF?" · Act: "¿Qué figura pendiente?" | Same as `showPending()`/"Ver sólo PMF pendientes" — **merge**, same code path, now 3 UI entry points (FAQ card + pendingzone button + this row's own trigger) | Correct, precise | none / not found | implement, **merge with TR-FUNC-032's button** | Filters to `isPendingPMF` subset and scrolls to pendingzone | FACT |
| TR-FUNC-025 | `lookup` | "¿A qué PMF corresponde un N.º de ingreso?" | Focuses search box, swaps placeholder — a UX hint, not a dedicated lookup | Under-delivers vs. its own question | none / not found | implement (as designed) | Focus + placeholder swap reproduced; note to Javier this is not a real lookup UI — offer building one as a follow-up, not silently upgrade it | FACT |
| TR-FUNC-026 | `easement` | "¿Cuáles tienen servidumbre?" | `selectOnly('owner','Servidumbre firmada')` + apply | Correct, precise | none / not found | implement | Selecting this quick action reproduces TR-FUNC-022 filtered to exactly that value | FACT |
| TR-FUNC-027 | `surface` | "¿Cuál es la superficie de corta?" | No-op filter re-run + scroll to KPIs | Functionally a scroll shortcut | none / not found | implement (as designed) | Scrolls to KPI row, filter state unchanged | FACT |
| TR-FUNC-028 | `rejected` | "¿Qué expedientes tienen rechazo?" | Sets search text to literal `"rechaz"` | **Blunt whole-row substring search, not a field-scoped predicate** — fragile if a free-text field ever contains that substring | none / not found | implement, **flag for hardening** | Reproduces current result on fixture; recommend (not silently substitute) a real `Estado`-scoped predicate as a documented improvement Javier can accept or decline | FACT |
| TR-FUNC-029 | `legal` | "¿Dónde está el principal cuello de botella?" | Sets search text to literal `"legal"` | Same blunt-search fragility as 028 | none / not found | implement, **flag for hardening** | Same pattern as 028 | FACT |
| TR-FUNC-030 | `company` | "¿Cómo avanza cada empresa?" | Focuses Empresa dropdown only — no per-company comparison view exists anywhere in either file | Question implies a comparison table that does not exist | none / not found | implement (as designed), **blocked** on whether a per-empresa table is a real missing function | Reproduce current focus-only behavior; **do not build a new comparison table without Javier confirming it's wanted** — building one unasked would itself violate "not a loosely inspired replacement" | FACT (gap) / OPEN (is it wanted) |
| TR-FUNC-031 | `overdue` | "¿Qué ingresos superaron 90 días?" | `Estado resumido != 'Aprobado' AND '90 dias' date < hardcoded 2026-08-26` | **Broken by design** — hardcoded literal date, confirmed present identically in both files, can never advance | none / not found | implement, **fix mechanically** | Replace the hardcoded literal with a dynamically-computed reference date (server-side "now," per source-ingestion.md's rule that observation time is platform infrastructure, not workbook data) — this is the one unambiguous, non-business-judgment bug fix in this matrix; the meaning of `90 dias` itself stays PROVISIONAL (TR-OPEN-03) | FACT (bug) / OPEN (field meaning) |

## F. Pendingzone (TR-FUNC-032 – 033)

| ID | Label (es) | Job/question | Source fields | Rule | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-032 | PMF pendientes · control prioritario (número + % + etapas + barras) | ¿Cuántos PMF prioritarios hay y en qué etapa? | detailed `Estado` | **CORRECTION — `pendingStage()` also differs between files, confirmed by direct code read this session**: v0's `isPendingPMF` (TR-FUNC-007, the ratified rule) + v0's `pendingStage()` 3-way substring heuristic (`'prepar'` / `'recurso'+'rechaz'` / else) over `Estado` — this is the rule to implement. Actualizable replaced both with a different `isPendingPMF` (`Estado resumido` ∈ {pendiente, tachado}) and a different 2-way `pendingStage()` (`Tachado`/`Pendiente` split on `Estado resumido`) — a fourth disagreeing status rule beyond the three TR-OPEN-01 already names, worth folding into that decision | none / not found (no evidenced dedicated component) / not found | implement, **PROVISIONAL** | Stage counts sum to TR-FUNC-007's total; v0's `pendingStage()` heuristic reproduced exactly, flagged to Javier as INFERENCE-quality (not a confirmed CONAF taxonomy); UI copy must use v0's wording, not Actualizable's | FACT (mechanism + v0-vs-Actualizable rule mismatch) / OPEN (taxonomy correctness) |
| TR-FUNC-033 | Tabla de pendientes (detalle) | Ver el detalle de los PMF pendientes | v0: 7 cols · Act: 9 cols (enhanced) | filtered to `isPendingPMF` subset | none / not found / not found | implement | Column set matches Actualizable's 9-column version (the superset); row set matches TR-FUNC-007 | FACT |

## G. Report / export / print (TR-FUNC-034 – 039)

| ID | Label (es) | Job/question | Mechanism | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-034 | Reporte ejecutivo breve (texto generado) | Obtener un resumen narrativo listo para compartir | Template string, values substituted from current filtered view (**correction**: an earlier version of this row claimed the verbatim template was already "captured in the source audit" — it was not; the exact template for both files is now recorded in [the source forensic audit](2026-09-02-source-forensic-audit-v1.md)'s HTML Actualizable section, confirmed by direct code read this session) | none / not found (report text specifically) / not found | implement | Generated text matches the now-recorded template with fixture values substituted, with the hardcoded `14-08-2026` date replaced by the active import's own publish/snapshot date (never a frozen literal) | FACT |
| TR-FUNC-035 | Copiar reporte | Copiar el reporte al portapapeles | `navigator.clipboard.writeText()` | none / not found / not found | implement | Clipboard write succeeds in a real browser test (headless permission model prevented full confirmation in this audit — re-verify in Phase 6 acceptance testing) | INFERENCE |
| TR-FUNC-036 | Descargar TXT | Descargar el reporte como archivo de texto | Shares the `download()` helper already proven live via CSV export | none / not found / not found | implement | Real browser download fires with the expected filename and content matching TR-FUNC-034's text | INFERENCE (shared helper, not independently re-clicked) |
| TR-FUNC-037 | Exportar CSV | Exportar la vista filtrada actual | `;`-delimited, UTF-8 BOM, 17-of-30 fields — **field set differs between v0 (includes raw `Estado`) and Actualizable (includes `Predio Ref` instead)**; exact ordered field lists for both files are now recorded in [the source forensic audit](2026-09-02-source-forensic-audit-v1.md), confirmed by direct code read this session (previously only the count and the swap fact were documented) | none / not found / not found | implement, **PROVISIONAL** on canonical field set (corrected from "blocked" — the implementation plan already resolves TR-OPEN-04 with a shippable default, so nothing here actually blocks implementation) | Reproduces Actualizable's exact 17-field list as the default (most recent, most-used file), with `Carpeta` split into the two positionally-distinct source fields (`carpeta_source`, `carpeta_normalizada`) rather than guessing which one Actualizable's header-keyed collapse silently picked, and `Observación auxiliar` shipped as an always-empty reserved column (sourced from the `Pendientes` sheet in Javier's tool, out of scope per this design's non-goals) — so V1's default export is 18 columns, not a literal 17; Javier confirms or names the final field set | FACT (both sets, now exact) / OPEN (canonical set) |
| TR-FUNC-038 | Imprimir / PDF | Imprimir o guardar como PDF | `window.print()` + dedicated `@media print` stylesheet | none / not found / not found | implement | Print view hides chrome (header/filters/FAQ/notice/buttons), un-clips the table, avoids breaking sections across pages — reproduced pixel-equivalent in a Playwright print-emulation test | FACT |
| TR-FUNC-039 | Detalle filtrado (tabla principal) | Ver/explorar cada área de corta individualmente | Row-grain, v0: 11 cols · Act: 12 cols (adds `Predio de reforestación`); **hidden `slice(0,1000)` cap, no pagination UI, currently unreachable at 729 rows** | none / `list_pmfs()`/`get_pmf_detail()` hierarchy (different shape — PMF→predio→row, not flat) / `PmfExplorer.tsx`, `Pagination.tsx` | implement | Column set matches Actualizable's 12-column version; real pagination (not a silent 1000-row cliff) built from day one since the target design must not reproduce a hidden truncation | FACT |

## H. Upload / refresh (TR-FUNC-040)

| ID | Label (es) | Job/question | Mechanism | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-040 | Actualizar base Excel | Cargar una versión más reciente de la planilla | Actualizable-only; hand-rolled client-side ZIP/DEFLATE/XLSX reader, header-text-keyed rows (**collapses the duplicate `Carpeta` columns — confirmed**), **zero schema/column validation**, in-tab-memory only, no persistence | none (generic upload+inspection pipeline exists, no Transelec publish step) / `POST /snapshots`+`/activate`, admin-token-gated, **reparses full XLSX on every dashboard read** (architecturally rejected pattern, see gap analysis) / `SourceManager.tsx`/`SourceStatusCard.tsx` (removed from the ADR-008 demo port; last known in UI-parity branch, assumes admin-token backend) | implement, **redesigned** | This is the one function that must NOT be reproduced as-is (see [target architecture](../../../../docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-design.md)) — replaced end-to-end by the authenticated upload → validate → import → publish pipeline; acceptance criteria live in that document's ingestion-lifecycle tests, not here | FACT |

## I. Structural / chrome (TR-FUNC-041 – 046)

| ID | Label (es) | Job/question | Notes | Main / PR47 / UI branch | Disposition | Acceptance test | Confidence |
|---|---|---|---|---|---|---|---|---|
| TR-FUNC-041 | Encabezado / marca | Identificar Campo Digital y Transelec/Transmisora del Pacífico | Inline base64 logos in source; target must source logos legally/safely, not by extracting the base64 payload without authorization | none / not found / `AppHeader.tsx` (UI-parity) / `DemoHeader.tsx` (ADR-008 port, generic) | implement | Both brand marks render; logo provenance confirmed with Javier/Campo Digital before reuse | FACT |
| TR-FUNC-042 | Aviso "Consulta documental" | Explicar la convención N.º de ingreso ↔ PMF y la ausencia de N.º de resolución | Static explanatory banner | none / not found / not found | implement | Banner text present, matches source wording | FACT |
| TR-FUNC-043 | Pie de página / cita de fuente | Trazabilidad de la fuente y confirmación de que el archivo no modifica la planilla | Static text citing filename, hoja, exclusión de históricos, uso auxiliar de Pendientes | none / not found / not found | implement | Replaced by real provenance: active source snapshot name/hash/publish timestamp, shown via the platform's own provenance UI, not a static string | FACT |
| TR-FUNC-044 | Diseño responsivo | Uso en escritorio, tablet y teléfono | Breakpoints at 1000px/600px, live-verified at 390×844 with no errors | none / not found / partially (component-level, not independently re-verified) | implement | Playwright viewport tests at desktop/tablet/phone widths, no console errors, no horizontal scroll | FACT |
| TR-FUNC-045 | Hoja de estilos de impresión | Imprimir una vista limpia | Dedicated `@media print` block, confirmed genuinely designed (hides chrome, unclips table) | none / not found / not found | implement | Same as TR-FUNC-038's acceptance test | FACT |
| TR-FUNC-046 | Marca de tiempo / vigencia de datos | ¿Cuán vigentes son los datos mostrados? | **v0**: "Visor generado" recomputes `new Date()` live at every page load regardless of data freshness (misleading — data is a frozen 14-Aug snapshot but the stamp always says "today"). **Actualizable**: static "Base: 14 agosto 2026" plus a live "updated" text set only after a manual Excel refresh | none / not found / not found | implement, **fixed by design** | Target shows the actual active-version publish timestamp (real provenance data, not `new Date()` and not a static string) — this single change eliminates the v0 staleness-illusion defect structurally | FACT |

---

## Open decisions surfaced by this matrix (Javier as owner unless noted)

| ID | Decision | Blocks |
|---|---|---|
| TR-OPEN-01 | Canonical PMF/predio-level status rollup rule when a PMF/predio's rows disagree (currently at least 4 different de-facto rules, not 3 — **correction, confirmed by direct code read during Task 5 of the implementation plan**: first-row-wins for KPIs, v0's `isPendingPMF`/`pendingStage()` for pending priority, `ownerStage()` for the owner table, **and Actualizable's own different `isPendingPMF`/`pendingStage()` pair**, which the app does not implement — the ratified rule for TR-FUNC-007/032 is v0's) | Blocks only the *unification* of TR-FUNC-005, 006, 007, 011, 013, 032 under one canonical rule — not shipping any of them. Each ships now with its own named legacy basis (`estado_resumido_first_row`, `pending_priority_legacy`, `owner_stage_legacy`); see the implementation plan's corrected "Open decisions" section. |
| TR-OPEN-02 | Which `Carpeta` column(s) (E, AC, or both) the UI should show, and how labeled | Data model + any UI surfacing `Carpeta` |
| TR-OPEN-03 | What `90 dias` (col V) and `Superficie de total de corta` actually represent | TR-FUNC-004, 031 |
| TR-OPEN-04 | Canonical CSV export field set | TR-FUNC-037 |
| TR-OPEN-05 | Is a per-empresa comparison view a real missing function? | TR-FUNC-030 |
| TR-OPEN-06 | Logo/brand asset sourcing authorization | TR-FUNC-041 |

None of these block starting implementation of the ingestion/publication pipeline (schema, uploads, snapshots, projection, immutable imports, publication, restore, provenance, RBAC, CSRF) or the non-status-dependent UI (filters, table browsing, export, chrome). Correction: TR-OPEN-01 in particular does not even block the six rows it names (TR-FUNC-005, 006, 007, 011, 013, 032) from being *implemented* — each ships now with its own named legacy rule; TR-OPEN-01 blocks only the future step of *unifying* those rules into one canonical rollup once Javier decides. Per the brief's "blocks implementation now / blocks only production deployment / can safely use an explicit provisional default" split, which the [implementation plan](../../../../docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-implementation-plan.md) resolves per-item, TR-OPEN-01 is in the "explicit provisional default" bucket, not "blocks implementation now."

## Related documentation

- [Source forensic audit](2026-09-02-source-forensic-audit-v1.md)
- [Implementation gap analysis](2026-09-02-implementation-gap-analysis-v1.md)
- [Target architecture spec](../../../../docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-design.md)
- [Implementation plan](../../../../docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-implementation-plan.md)
