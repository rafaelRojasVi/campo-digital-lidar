# Transelec: show which values were edited on the web, and their history

Date: 2026-10-05. Status: design approved by Rafael in chat; this written
spec awaits his review before the implementation plan.
Follows [web edits and the «web» download](2026-10-04-transelec-web-edits-xlsx-design.md)
(PR #83). This is Spec 1 of two; Spec 2 (editing a whole PMF, editing in
the table) is outlined under "Out of scope".

## Goal

Web edits change what the dashboard shows and counts, but today nothing
outside Datos → «Ediciones web» and the Explorador says so. After this
change, anyone signed in can see at a glance that the active version has
web edits, open a short log of who changed what and when (including edits
that were later replaced or reverted), and tell which values and totals
come from edits. The edit flow itself gets three small fixes.

## Decisions taken with Rafael (DECISION, 2026-10-05)

| Topic | Decision |
|---|---|
| Scope | Two specs. This one: indicator, log with history, «web» marks in Estado, a Resumen note, drawer and suggestion fixes. Spec 2: PMF-wide edits and inline editing. |
| Indicator | A pill beside «Versión activa» in the header, opening a popover log. Not a banner, not a plain link. |
| Log contents | Full history: edits in force, plus replaced, reverted, kept and incorporated ones, shown greyed out. |
| Who sees it | Everyone signed in to Transelec. Viewers already see the «web» marks and their authors. Links to Ediciones web and the .xlsx download stay operator/admin only. |
| PMF-wide edits (for Spec 2) | An edit made at PMF level applies to every row of the PMF in one transaction; the drawer keeps per-row edits for exceptions. |

## Evidence

**RESULT (2026-10-05, UX review on a local replay of production).** An agent
signed in as the Transelec admin on the production image with the
production data of 2026-10-04 and made six edits through the UI. Findings
this spec addresses:

- After edits, the Resumen headline counts moved by one PMF with no
  explanation on the page; the Estado table has no «web» marks; the header
  shows no sign of edits.
- An edit fixed by a second edit, and an edit reverted with «Volver al
  valor de la planilla», leave no trace anywhere in the UI.
- In the drawer, «Campos editables» starts about 1,100 px down at
  1440×900, below a read-only «Tramitación» block that shows the same
  values. At 1280×720 the drawer scrolls about 2,900 px.
- After saving on one row and opening another row of the same PMF with
  «Ver la fila N», the second row's section still says «Se guardó el
  cambio en …».
- The suggestion lists contain values that differ only in capitals (for
  example an «En evaluacion» and an «En Evaluacion» entry).

Findings left to Spec 2: an edit changes one source row while the user
thinks in PMFs (one edit changed 1 of a PMF's 12 rows and created a
«estados distintos entre sus filas» issue in Calidad); «Estado resumido»
and «Estado» can be edited into disagreement; count fields accept free
text; editing is not discoverable from the tables.

**FACT (code at `main` `f984e18`).**

- **History exists but is not exposed.** `platform.transelec_field_override`
  never deletes rows. An edit ends with `ended_at`, `ended_by_app_user_id`
  and `end_reason` in (`superseded`, `discarded`, `kept`, `incorporated`)
  (migration `0012`). Producers in `app/transelec_overrides.py`:
  `save_override` ends the active row as `superseded` and inserts a new
  one, or as `discarded` when the new value equals the planilla's;
  `discard_override` (DELETE) ends as `discarded`; `keep_override` ends the
  conflicted row as `kept` and inserts a new row whose author is the
  keeper; `retire_incorporated_overrides`, called from the router's
  `_activate`, ends as `incorporated` in the activation transaction.
- `transelec_override_state` covers active edits only
  (`WHERE o.ended_at IS NULL`), so `list_overrides` and
  `GET /api/transelec/overrides` return active edits only.
- **Edits are not tied to one import.** They are keyed by
  `pmf, rol, numero_predio, numero_area_corta, key_ordinal, field` and
  evaluated against every import; an edit made under an older version
  still applies to the active one while its status is `aplicada`.
- **Activation time.** Every publish or restore inserts a
  `platform.transelec_publish_event` row (`occurred_at`); the latest one
  for the active import is `TranselecActiveImport.published_at`
  (`GET /imports/active`). Edits incorporated by an activation get
  `ended_at` equal to that event's `occurred_at` (same transaction).
- **Estado already knows its web fields.** `GET /lifecycle` reads
  `transelec_effective_row`; each `LifecyclePmfRowView` extends
  `ResumenRowView` and carries the `web_fields` of the PMF's first row in
  the filtered scope, which is the row the line shows. `EstadoTable` and
  `lib/estadoColumns.tsx` do not render `WebChip`.
- **The summary counts first rows.** `build_summary` takes the effective
  rows; the PMF headline and «Estado detallado» use each PMF's first row
  (`first_row_wins`), so only edits on first rows move them.
  `TranselecSummaryResponse` has no edit fields.
- **Frontend.** No shared state for edits: `EdicionesPage`,
  `WebEditConflicts` and `RowDetailDrawer` each call `listOverrides`. The
  drawer needs a full `ResumenRow`; `getPmfDetail(pmf).rows` gives a PMF's
  rows exactly. `AppHeader`'s `.shell-side` holds the `.version-chip`,
  the identity and the Proyectos link; at ≤1023 px the chip's date and the
  identity hide, at ≤767 px the bar wraps.
- `EditableFieldsSection` keeps its save message in component state and is
  not remounted when the drawer switches rows.
- Suggestions come from `loadSuggestions` → `suggestionsFrom`
  (`lib/webEdits.ts`): distinct trimmed values, so case variants survive.

## Design

### 1. API: the history list

`GET /api/transelec/overrides/history?limit=50` (`Action.VIEW`, 404 when
nothing is published, like `/overrides`). `limit` 1–200, default 50.

Response:

```json
{
  "in_force_count": 5,
  "needs_review_count": 0,
  "entries": [
    {
      "id": 41,
      "field": "estado",
      "field_label": "Estado vigente",
      "pmf": "…", "rol": "…", "numero_predio": "…", "numero_area_corta": "…",
      "source_row_number": 77,
      "web_value": "…",
      "planilla_value_at_edit": "…",
      "created_by_display_name": "…",
      "created_at": "2026-10-05T12:41:00+00:00",
      "state": "aplicada",
      "ended_at": null,
      "ended_by_display_name": null
    }
  ]
}
```

- **Which edits.** Every active edit (status against the active import,
  whatever its creation time), plus every ended edit with
  `ended_at >= published_at` of the active import's latest publish event.
  A new activation therefore starts a fresh log; older history stays in
  the database.
- **`state`.** For active edits, the `transelec_override_state` status
  (`aplicada`, `en_conflicto`, `huerfana`, `incorporada`). For ended ones,
  the `end_reason` (`superseded`, `discarded`, `kept`, `incorporated`).
- **`source_row_number`.** The active import's row for the edit's key and
  `key_ordinal` (`transelec_keyed_row`), or `null` when the row no longer
  exists.
- **Counts.** `in_force_count` = active edits with status `aplicada` (what
  the .xlsx writes). `needs_review_count` = active `en_conflicto` plus
  `huerfana`. Both count every edit, independent of `limit`.
- **Order.** `created_at` descending, then `id` descending.
- No values go into the audit trail (unchanged rule); this is a read.

### 2. API: the summary says how many PMFs show an edited state

`TranselecSummaryResponse` gains `web_edited_pmf_count`: the number of PMFs
whose first row (the one the headline counts) has `estado_resumido` or
`estado` in its `web_fields`. Computed in the summary route from the same
effective rows; no new query.

### 3. Dashboard: shared edits state

A small `WebEditsProvider` in the shell (`App.tsx`) owns one call to the
history list and exposes `{history, status, refresh, openLog}` (`openLog`
opens the header popover, for the Resumen hint). It loads after
sign-in once an active version exists and reloads when the active version
changes. Every successful save, discard or keep anywhere calls `refresh`.
The existing per-component `listOverrides` calls stay as they are; this
spec does not refactor them.

### 4. Dashboard: the header pill

- In `.shell-side`, right after the version chip: a button styled as a
  second chip in the «web» yellow, reading «✎ 5 ediciones web»
  (singular «✎ 1 edición web»). When `needs_review_count > 0` it appends
  «· 2 por revisar» in the warning style.
- Hidden while loading, on error, when nothing is published, and when
  both counts are 0. With nothing in force, the history (replaced,
  reverted, incorporated edits) stays reachable in Ediciones web.
- At ≤1023 px it shows «✎ 5» (with «· 2» when needed); its accessible name
  always carries the full text.
- `aria-haspopup="dialog"` and `aria-expanded`; the existing shell-bar
  layout tests at laptop widths and with a long name must still pass.

### 5. Dashboard: the popover log

- Anchored under the pill; closes on Esc, on a click outside and on route
  change; focus moves into it on open and back to the pill on close.
- Header: «Ediciones web · versión #3», with the in-force count.
- The latest 8 entries, newest first. Each entry:
  - «<PMF> · <campo>» on the first line;
  - «<valor en la planilla> → <valor web>» on the second (empty values as
    «(vacío)»);
  - «<autor> · <fecha relativa>» («hoy 09:41», «ayer 17:02», then
    dd-mm-aaaa), in Chile time.
  - Entries not in force are greyed and labelled: `superseded`
    «reemplazada», `discarded` «descartada por <quien>», `kept`
    «mantenida por <quien>» (the new entry carries the value),
    `incorporated` and `incorporada` «incorporada en la planilla»,
    `en_conflicto` «en conflicto», `huerfana` «sin fila en esta versión».
- Clicking an entry with a `source_row_number` opens that row's drawer:
  the shell fetches `getPmfDetail(pmf)`, picks the row, and renders
  `RowDetailDrawer` with the same edit rights as Estado. After an edit made
  there, the edits state refreshes and the current page reloads its data.
  Entries without a row are not clickable.
- More than 8: «y N más» above the footer.
- Footer, operator/admin only: «Ver todas en Ediciones web →» and
  «⬇ Descargar planilla con ediciones (.xlsx)» (the existing download
  action, with its error handling).
- A failed history load shows nothing in the header (the pill hides); the
  Ediciones web page shows the error as it does today.

### 6. Dashboard: «Ediciones web» shows the history

Below the existing table of active edits, a «Historial» section lists every
history entry in the popover's format, with the same labels. It reuses the
shared state.

### 7. Dashboard: «web» marks in Estado

`EstadoTable` renders `WebChip` in a cell when any field it shows is in the
line's `web_fields`: «Grupo» and «Paso» (`estado_resumido`, `estado`),
«Tipo de rechazo», «N.º ingreso (1 / 2)», «Reingreso tec / legal / recrep»,
and the plazo cell (`fecha_ingreso`, `fecha_ingreso_2`, `fecha_90_dias`). The chip's
`description` names the field for screen readers, as in the Explorador.

### 8. Dashboard: the Resumen explains edited totals

When `web_edited_pmf_count > 0`, `StatusHeadline` shows a hint line next to
its existing notes: «Incluye 1 PMF con estado editado en la web.» (plural
«N PMF»), with a «Ver ediciones» button that opens the header popover.

### 9. Dashboard: drawer fixes

- For operator/admin, «Campos editables» moves to the top of the drawer,
  right under the header chips.
- For operator/admin, «Tramitación» stops repeating the values shown in
  «Campos editables». Its actions and notices stay: «Abrir Oficina Virtual
  CONAF», «Copiar N.º» and «Varias fechas en la celda». Viewers see no
  change.
- `EditableFieldsSection` is keyed by `source_row_number`, so switching rows
  starts it fresh (no stale «Se guardó el cambio»).

### 10. Dashboard: suggestions without case variants

`suggestionsFrom` groups values by a key that ignores case, accents and
repeated spaces, and keeps the spelling that occurs most often in the
active version (ties: first in `es` order). Typing any value is still
allowed; the server's rules are unchanged.

## Testing

- **API integration** (`apps/api/integration_tests/test_transelec_overrides.py`):
  history after save, supersede, discard (both producers), keep and
  incorporation, with the right `state`, `ended_by_display_name` and
  order; the activation cutoff (an edit ended before the latest activation
  is absent; an older edit still in force is present; incorporated edits of
  this activation are present); counts independent of `limit`; viewer 200;
  404 with nothing published.
- **API reads** (`test_transelec_reads_router.py`): `web_edited_pmf_count`
  counts first-row edits to `estado_resumido`/`estado` and ignores edits on
  other rows and other fields.
- **Vitest:** pill text, singular and plural, «por revisar», hidden states,
  narrow form (`Chrome.test.tsx`); popover entries, labels per state,
  footer by role, click opens the drawer; Estado chips
  (`EstadoTable.test.tsx`); Resumen hint (`StatusHeadline.test.tsx`);
  drawer order and the remount (`RowDetailDrawer.test.tsx`,
  `EditableFieldsSection.test.tsx`); grouped suggestions
  (`lib/webEdits.test.ts`); Ediciones «Historial».
- **Playwright** (`tests/e2e/web-edits.spec.ts`, `stubPlatform` extras):
  pill and popover; edit from the popover's drawer refreshes the pill;
  viewer sees the pill without the footer links; shell bar at 1280 and
  1024 px still fits (`navigation.spec.ts`).
- **Manual:** the local replay of production, signed in as the Transelec
  admin, which already holds the UX review's edits (in force, replaced and
  reverted).

## Risks and limitations

- **LIMITATION:** edits made before the latest activation that ended
  before it are not in the log; they remain in the database only.
- **LIMITATION:** `kept` and `superseded` rows have no link to the row that
  replaced them; the log shows both entries side by side, matched only by
  field and time.
- **LIMITATION:** «web» marks in Estado reflect the PMF's first row only,
  like every Estado value. Edits on other rows show in the Explorador and
  the log.
- The history query joins `transelec_keyed_row` for the active import;
  with a few hundred edits at most this is cheap, and `limit` caps the
  payload.

## Out of scope (Spec 2, to be designed next)

- Editing a whole PMF: one save applies to every row of the PMF in one
  transaction, with «se aplicará a las N filas de …»; per-row edits stay in
  the drawer for exceptions (DECISION above). Needs a new API.
- «Estado resumido» and «Estado» edited together as one control.
- Editing in the Estado table (PMF level) and the Explorador (row level)
  with editors anchored to the cell; the drawer stays the mobile path.
- Validating count fields («Reingreso …») as non-negative whole numbers.
- Linking Calidad findings to the editor.
