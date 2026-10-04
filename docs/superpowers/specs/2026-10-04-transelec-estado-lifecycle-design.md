# Transelec: «Estado» tab with the plan lifecycle

Date: 2026-10-04. Status: design approved in conversation with Rafael; this
file awaits his review before a plan is written. Backlog item PR-1 of
[the post-launch backlog](../../../products/transelect/docs/design/2026-10-02-post-launch-backlog-v1.md).
Sibling specs, built in parallel:
[web edits and .xlsx download](2026-10-04-transelec-web-edits-xlsx-design.md)
and [90 días hábiles](2026-10-04-transelec-plazo-90-habiles-design.md).
Merge order: Estado → 90 días (stacked on the Estado branch) → web edits;
each rebased on `main` before merging.

## Goal

The meeting of 2026-10-02 (requests R1, R2, R3, R5) asked for three things:

- Replace the «Pendientes» tab with «Estado».
- Show each plan (PMF) where it is in CONAF's process. A rejection is a step
  towards a new document, never an end: every rejection ends as approved or
  withdrawn.
- Show the type of rejection and the reingreso, and link each plan to
  CONAF's Oficina Virtual.

## Decisions (DECISION, 2026-10-04)

- **What decides the group.** *Estado resumido* gives the main group and
  *Estado* gives the step inside «En trámite». A web edit of *Estado
  resumido* (sibling spec) therefore moves the plan between groups.
- **Rejection is never terminal.** «Rechazado» in either column is a step
  inside «En trámite».
- **Descartado and Desistido.** «Descartado», the planilla's own word, and
  «Desistido», if it ever appears, are each a closed state shown with the
  source word. They are not merged, because the source has not said whether
  they mean the same thing (OPEN QUESTION 1). Both stop the CONAF clock in
  the sibling plazo spec.
- **Contradictions are not hidden.** A plan whose *Estado* contradicts its
  *Estado resumido* is placed in «sin clasificar» and flagged in Calidad.
  Nothing is guessed.
- **Reingreso flags are shown raw.** `Reingreso_Tec`, `Reingreso_Legal` and
  `Reingreso_RecRep` appear as they come and are not interpreted
  (OPEN QUESTION 2).
- **Oficina Virtual.** A link opens the consulta page in a new tab, and a
  button copies the N.º de ingreso. There is no deep link (see evidence).
- **Legacy bases stay available.** `pending_priority_legacy` and
  `pending_stage_legacy` and `GET /pending` remain reachable and are explained
  under «Cómo se calcula», as the parity rule requires.

## Evidence

FACT, from the code (`main` at `d1e311f`):

- Status today is substring tests on `Estado`:
  - `is_pending_row` returns true when `N Ingreso` is blank or `Estado`
    contains «rechaz»;
  - `pending_stage` maps «prepar» → preparación, «recurso» with «rechaz» →
    recurso_rechazo, everything else → otros, which the dashboard labels
    «Rechazado» (`status_rollups.py`, `lib/pendingStage.ts`).
- «Desistido» and «Descartado» appear nowhere in the code.
- PMF-level values use `first_row_wins` (the row with the smallest
  `source_row_number`). Source Contract V1 §Status records that no deterministic
  PMF aggregation rule is established; this spec adds a basis and keeps the
  first-row rule.
- «Pendientes» is wired in:
  - `router.tsx` (`ROUTES.pendientes`), `AppHeader.tsx` (`NAV`), `App.tsx`;
  - `PendientesPage.tsx` and `ResumenPage.tsx` (links and `getPending`);
  - `QualityPanel.tsx`, `lib/summaryView.ts`, `lib/rules.ts`;
  - the e2e specs `dashboard`, `navigation` and `print-responsive`.
- The production CSP has `form-action 'self'`, so the dashboard cannot post
  a form to another site.

FACT, from CONAF's page `https://oficinavirtual.conaf.cl/consultas/index.php`,
fetched read-only on 2026-10-04: it is a form that POSTs a field `nsolicitud`
to `action.php`. There is no URL that opens one expediente by number.

FACT, labels observed in the 30-Sept-2026 planilla. Read locally with the
importer's loader; labels only, not business values.

- *Estado resumido*: «Aprobado», «En tramite», «Rechazado», «Descartado».
- *Estado*, case and accents folded:
  - «aprobado», «en evaluacion», «rechazado», «descartado»;
  - «recurso reposicion», «recurso reposicion aprobado»;
  - «recurso jerarquico», «recurso jerarquico aprobado»,
    «recurso jerarquico rechazado».
- *Tipo de rechazo*: blank, «Legal», «Tecnico», «Legal y tecnico»,
  «Reforestacion y Legal», «Legal y reforestacion».
- `Reingreso_*` hold 0, 1 or 2 (numeric), or are blank.
- No row says «Desistido».
- Rows whose *Estado* is «rechazado» are summarized as «En tramite». The
  source already treats a rejection as in progress.
- One PMF has rows that disagree on *Estado*. None disagree on *Estado
  resumido*.
- The combination *Estado resumido* «Aprobado» with *Estado* «recurso
  reposicion» (no outcome) occurs.

INFERENCE: «Recurso de reposición» and «recurso jerárquico» are the new
documents Rafael's notes describe after a rejection.

## Design

### Basis `lifecycle_pmf_v1`

New pure module `products/transelect/src/transelec_ingestion/lifecycle_view.py`.
It sits beside `status_rollups.py`, reuses `normalized_label` and
`first_row_wins`, and has no database access.

**Input per PMF.** The first row's fields: `estado`, `estado_resumido`,
`tipo_rechazo`, `reingreso_tec`, `reingreso_legal`, `reingreso_recrep`,
`numero_ingreso`, `numero_ingreso_2`, `fecha_ingreso`, `fecha_ingreso_2`,
`source_row_number`. Also whether the PMF's rows disagree on `estado` or
`estado_resumido`.

**Group**, from `normalized_label(estado_resumido)`:

| Label | Group |
|---|---|
| `aprobado` | `aprobado` |
| `en tramite`, `rechazado` | `en_tramite` |
| `descartado` | `descartado` |
| `desistido` | `desistido` |
| blank or anything else | `sin_clasificar` (reason `resumido_desconocido`) |

**Step**, only in `en_tramite`, checked in this order:

1. `N Ingreso` and `N Ingreso2` both blank → `sin_ingreso`.
2. `en evaluacion` → `en_evaluacion`.
3. `rechazado`, or a label starting `recurso` and ending `rechazado` →
   `rechazado_esperando_recurso`, carrying `tipo_rechazo`.
4. `recurso reposicion` → `en_recurso_reposicion`.
5. `recurso jerarquico` → `en_recurso_jerarquico`.
6. Anything else → the PMF moves to `sin_clasificar`, reason
   `estado_desconocido`.

**Consistency.** These cases put the PMF in `sin_clasificar` with reason
`estado_y_resumido_no_coinciden`:

- The group is `aprobado` but *Estado* contains no «aprobado».
- *Estado* contains «aprobado» but the group is not `aprobado`.
- The group is `descartado` or `desistido` and *Estado* is anything other
  than the same word.

**Flag.** Disagreeing rows keep the first-row result and add flag
`filas_no_coinciden`.

**Output.** Counts per group and per step, and per PMF: `pmf`, `group`,
`step`, `reason`, `flags`, `tipo_rechazo`, the three `Reingreso_*` raw values,
both ingreso pairs, and `source_row_number`. The basis id
`lifecycle_pmf_v1` is returned, as the existing bases are.

### API

`GET /api/transelec/estado`:

- Viewer and above; the usual filters.
- Reads rows through `_fetch_filtered_rows`. Once the web-edits spec lands,
  that is the "rows with edits applied" relation, so edits show here with no
  change to this module.
- Returns the output above.

`GET /pending` stays.

### Dashboard

- **Route and navigation:**
  - `ROUTES.estado = '/transelec/estado'` with nav label «Estado»;
  - `/transelec/pendientes` redirects to it for one release;
  - links from Resumen and Calidad are updated.
- **`EstadoPage.tsx`**, replacing `PendientesPage.tsx`:
  - a composition bar of the groups;
  - a breakdown of the steps inside «En trámite», with attention red
    reserved for `rechazado_esperando_recurso`;
  - a table: PMF, Grupo, Paso, Tipo de rechazo, N.º ingreso (1 / 2),
    Reingreso Tec / Legal / RecRep (raw), Oficina Virtual;
  - clicking a row opens the existing drawer;
  - the 90 días column is added by the sibling spec.
- **Drawer:**
  - a «Proceso CONAF» block with group, step and reason;
  - the *Abrir Oficina Virtual CONAF* link (`target="_blank"`,
    `rel="noopener noreferrer"`) and a *Copiar N.º* button next to each
    N.º de ingreso.
- **«Cómo se calcula»** (`lib/rules.ts`) explains `lifecycle_pmf_v1` and keeps
  the two legacy bases.
- **Calidad:** a block listing PMFs in `sin_clasificar` with their reason,
  and PMFs flagged `filas_no_coinciden`.
- **Copy:** all lifecycle copy is marked provisional until Campo Digital
  confirms the vocabulary.

## Testing

- **Product** (`products/transelect/tests/test_lifecycle_view.py`). Synthetic
  rows only, covering every group, every step, each inconsistency reason,
  `filas_no_coinciden`, `sin_ingreso` from a blank ingreso, and accent, case
  and whitespace variants.
- **Integration** (`apps/api/integration_tests/test_transelec_reads_router.py`):
  `/estado` with filters, with viewer access, and with no CSRF requirement
  on the read.
- **Dashboard:**
  - vitest for the page model;
  - Playwright for the nav label, the redirect from `/pendientes`, the group
    bar, the table columns, the Oficina Virtual link attributes, the copy
    button and the Calidad block;
  - the existing specs are updated for the rename.

## Open questions for Campo Digital

Added to the Spanish meeting note.

1. Are «Descartado» and «Desistido» the same state?
2. What do the values 0, 1 and 2 in `Reingreso_Tec`, `Reingreso_Legal` and
   `Reingreso_RecRep` mean?
3. Is CONAF's N.º de solicitud the planilla's `N Ingreso`?
4. *Estado resumido* «Aprobado» with *Estado* «Recurso reposición» and no
   outcome: is the recurso pending, or is *Estado* out of date?

## Plan refinements (2026-10-04)

Found while writing
[the implementation plan](../plans/2026-10-04-transelec-estado-lifecycle.md),
which records the evidence:

- **API path.** The read is `GET /transelec/lifecycle`, not `/estado`. The
  router is also mounted without the `/api` prefix, and `transelec/estado` is
  a dashboard page path, so a shared path would answer a page reload with
  JSON. A guard test pins this.
- **Page paths.** `TRANSELEC_SPA_PAGE_PATHS` lists `transelec/estado`.
- **Display fields.** Tipo de rechazo, `Reingreso_*` and both ingreso pairs
  come from the PMF's first row hydrated as `ResumenRowView`, as `/pending`
  does. The classifier's input carries only what it classifies.
- **Old pending rule.** It stays on the Estado page as a closed «Pendientes
  prioritarios (regla anterior)» block.
