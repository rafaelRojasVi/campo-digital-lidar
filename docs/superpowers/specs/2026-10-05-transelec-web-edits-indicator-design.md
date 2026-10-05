# Transelec: show which values were edited on the web, and their history

Date: 2026-10-05. Status: design approved by Rafael in chat, revised the
same day after three reviews (backend, frontend, UI and accessibility);
awaiting his review before the implementation plan.
Follows [web edits and the «web» download](2026-10-04-transelec-web-edits-xlsx-design.md)
(PR #83). This is Spec 1 of two; Spec 2 (editing a whole PMF, editing in
the table) is outlined under "Out of scope".

## Goal

Web edits change what the dashboard shows and counts, but today nothing
outside Datos → «Ediciones web» and the Explorador says so. After this
change, anyone signed in can see at a glance that values are edited on the
web, open a short log of who changed what and when (including edits that
were later replaced or reverted), and tell which values and totals come
from edits. The edit flow itself gets three small fixes.

## Decisions taken with Rafael (DECISION, 2026-10-05)

| Topic | Decision |
|---|---|
| Scope | Two specs. This one: indicator, log with history, «web» marks in Estado, a Resumen note, drawer and suggestion fixes. Spec 2: PMF-wide edits and inline editing. |
| Indicator | A pill beside «Versión activa» in the header, opening a popover log. Not a banner, not a plain link. |
| Log contents | Full history: edits in force, plus replaced, reverted, kept and incorporated ones, shown greyed out. |
| Log scope | The latest edits ever, newest first, with no per-version cutoff. (A per-version log was rejected: restoring a version would hide its own earlier edits.) |
| Opening an entry | Go to the Explorador filtered to the PMF, with that row's drawer open. (A drawer over the current page was rejected: every page would need a new "row edited elsewhere" refresh path.) |
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
  - `save_override` ends the active row as `superseded` and inserts a new
    one; when the new value equals the planilla's, it ends the row as
    `discarded` and inserts nothing.
  - `discard_override` (DELETE, the drawer's «Volver al valor de la
    planilla» and Ediciones web's «Descartar») ends it as `discarded`.
    Both `discarded` producers return the cell to the planilla value.
  - `keep_override` ends a conflicted row as `kept` and inserts a new row
    whose author and time are the keeper's.
  - `retire_incorporated_overrides`, called from the router's `_activate`,
    ends edits as `incorporated` in the activation transaction, with the
    activating user as `ended_by_app_user_id`.
  - Every ended row has an `ended_by_app_user_id`. No row links an ended
    edit to the one that replaced it.
- `transelec_override_state` covers active edits only
  (`WHERE o.ended_at IS NULL`) and CROSS JOINs every import, so
  `list_overrides` and `GET /api/transelec/overrides` return active edits
  only, filtered to the active import.
- **Edits are not tied to one import.** They are keyed by
  `pmf, rol, numero_predio, numero_area_corta, key_ordinal, field` and
  evaluated against every import. `key_ordinal` is a row's position among
  rows with the same key, so it can point at a different physical row in a
  version with rows added or removed.
- **The download counts differently.** `export.xlsx` writes `aplicada`
  edits but skips fields the version has no column for and formula cells;
  Ediciones web already states how many it writes and skips.
- **Estado already knows its web fields.** `GET /lifecycle` reads
  `transelec_effective_row`; each `LifecyclePmfRowView` extends
  `ResumenRowView` and carries the `web_fields` of the PMF's first row in
  the filtered scope, which is the row the line shows. `EstadoTable` and
  `lib/estadoColumns.tsx` do not render `WebChip`.
- **The summary counts first rows, within the filters.** `build_summary`
  takes the filtered effective rows; the PMF headline and «Estado
  detallado» use each PMF's first row (`first_row_wins`), so only edits on
  first rows move them. `TranselecSummaryResponse` has no edit fields.
- **Frontend.**
  - No shared state for edits: `EdicionesPage`, `WebEditConflicts` and
    `RowDetailDrawer` each call `listOverrides`.
  - The Explorador keeps its filters in the URL (`lib/filterUrl.ts`,
    `lib/useFilters.ts`), so `?q=<pmf>` already narrows it to a PMF.
  - The drawer is modal: `.drawer-backdrop` is fixed over the whole
    viewport at `z-index: 60`, above the sticky top bar (`40`), so the
    header cannot be reached while a drawer is open.
  - `AppHeader`'s `.shell-side` holds the `.version-chip`, the identity
    and the Proyectos link; at ≤1023 px the chip's date and the identity
    hide, at ≤767 px the bar wraps.
  - In the drawer, «Tramitación» renders `Fact`s for fields that are also
    in `EDITABLE_FIELDS` (`lib/webEdits.ts`); «Abrir Oficina Virtual
    CONAF», «Copiar N.º» and «Varias fechas en la celda» live inside those
    `Fact`s.
  - `EditableFieldsSection` keeps its save message and open editor in
    component state and is not remounted when the drawer switches rows.
  - Suggestions come from `loadSuggestions` → `suggestionsFrom`: distinct
    trimmed values, so case and accent variants survive.
- **FACT (platform, 2026):** the HTML `popover` attribute works in all
  major browsers since 2024
  ([MDN](https://developer.mozilla.org/docs/Web/API/Popover_API)); CSS
  anchor positioning became Baseline in January 2026 with Chrome 125,
  Safari 26 and Firefox 147
  ([web.dev](https://web.dev/blog/web-platform-01-2026)).

## Design

### 1. API: the history list

`GET /api/transelec/overrides/history?limit=50` (`Action.VIEW`; 404 when
nothing is published, like `/overrides`). `limit` 1–200, default 50.

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

- **Which edits.** The latest `limit` override rows, active or ended,
  ordered by `created_at` descending, then `id` descending. No cutoff by
  version.
- **`state`.** For active edits, their `transelec_override_state` status
  against the active import (`aplicada`, `en_conflicto`, `huerfana`,
  `incorporada`). For ended edits, their `end_reason` (`superseded`,
  `discarded`, `kept`, `incorporated`). The dashboard type is a new
  `TranselecHistoryEntry` with `state`, separate from `TranselecOverride`
  and its `status`.
- **`source_row_number`.** For active edits, the active import's row from
  `transelec_override_state` (null for `huerfana`). Always null for ended
  edits: they no longer act on any row, and a stale `key_ordinal` could
  point at the wrong one.
- **`ended_by_display_name`.** Null exactly when `ended_at` is null.
- **Counts.** Over all edits, independent of `limit`:
  - `in_force_count`: active edits with status `aplicada`, the ones the
    dashboard shows.
  - `needs_review_count`: active edits with status `en_conflicto` or
    `huerfana`.
  - **DECISION:** active `incorporada` edits (the planilla already holds the
    web value; possible while an older layout is active) are listed but
    counted in neither.
- **Query.** Read `transelec_field_override` directly for the page of
  entries, joined to `app_user` twice (author, ender), and LEFT JOIN the
  state of active edits with `transelec_override_state` filtered by
  `import_id = :active_import_id` inside the joined subquery, so the
  view's cross join over every import is not materialised. Counts come
  from the same filtered state.
- No audit row is written (it is a read), and audit rows keep carrying no
  values.

### 2. API: the summary says how many PMFs show an edited state

`TranselecSummaryResponse` gains `web_edited_pmf_count`: the number of PMFs
whose first row (the one the headline counts) has `estado_resumido` or
`estado` in its `web_fields`. It is computed from the same filtered
effective rows as every other summary number, so it follows the page's
filters like they do.

### 3. Dashboard: shared edits state

A `WebEditsProvider` in the shell (`App.tsx`) owns the history list and
exposes `{history, status, refresh, openLog}` (`openLog` opens the header
popover, for the Resumen hint).

- Loads after sign-in once an active version exists; clears on sign-out
  or a 401; reloads when the active version changes (the shell's existing
  `provenanceVersion`).
- `refresh` is called after every successful save, revert, discard or keep:
  the drawer (on every page that opens it) and Ediciones web.
- Also refreshes when the tab becomes visible again, at most once a
  minute, so another tab's or person's edits show up without a reload.
- Keeps the previous data while a refresh runs (no flicker) and ignores a
  response older than the latest request.
- The existing per-component `listOverrides` calls stay as they are.

### 4. Dashboard: the header pill

- In `.shell-side`, right after the version chip: a button styled as a
  second chip in the «web» colours (`--web-chip-*`), with a 12 px SVG
  pencil (`aria-hidden="true"`) and «5 ediciones web» (singular «1
  edición web»). No Unicode pencil: it is missing from some Windows fonts.
- When `needs_review_count > 0` it adds «· 2 por revisar» on the conflict
  tint (`--st-late-tint` / `--st-late-ink`). The words carry the meaning;
  the colour only repeats it.
- Hidden until the first load succeeds, on error, when nothing is
  published, and when both counts are 0. With nothing in force, the
  history stays reachable in Ediciones web.
- At ≤1023 px it shows the pencil and «5» (and «· 2»); its accessible
  name always carries the full text.
- `popovertarget` points at the log; `aria-haspopup="dialog"`,
  `aria-controls` and `aria-expanded` (kept in sync from the popover's
  `toggle` event). It is not a live region: counts change only after the
  user's own actions or a tab refocus.
- Hidden in print (`no-print`), like the rest of the bar.

### 5. Dashboard: the popover log

- **Element.** `<div id="edit-log" popover="auto" role="dialog"
  aria-labelledby="edit-log-heading">`. The platform provides Esc, light
  dismiss and the top layer, so no outside-click handler and no z-index.
  On open, focus moves to the heading (`tabindex="-1"`); on close, back to
  the pill.
- **Position.** Under the pill with CSS anchor positioning, aligned to its
  right edge, flipping when there is no room. Where anchor positioning is
  unsupported (`@supports not (anchor-name: --edit-log)`), fixed under the
  bar at the right gutter, which is where the pill sits anyway. At
  ≤767 px, a full-width panel under the bar, at most 70 % of the viewport
  high, scrolling inside.
- **Heading.** `<h2 id="edit-log-heading">Ediciones web</h2>`, with
  «5 en vigor» (and «2 por revisar») beside it.
- **Entries.** The latest 8, newest first:
  - first line «<PMF> · <campo>»;
  - second line «<valor en la planilla> → <valor web>», each value clamped
    to two lines with the full value available to screen readers and on
    hover; an empty value reads «(vacío)»;
  - third line «<autor> · hoy 09:41» / «ayer 17:02» / «03-10-2026», in
    `America/Santiago` with `Intl.DateTimeFormat('es-CL')`.
- **State labels.** In-force entries carry none. The others are greyed and
  labelled:
  - `en_conflicto`: «en conflicto: la planilla cambió» (not greyed: it
    needs action);
  - `huerfana`: «sin fila en la versión activa» (not greyed);
  - `incorporada`, `incorporated`: «ya está en la planilla»;
  - `superseded`: «reemplazada por una edición posterior»;
  - `discarded`: «revertida al valor de la planilla · <quien>»;
  - `kept`: «conservada al resolver un conflicto · <quien>» (the newer
    entry carries the value on).
- **Opening an entry.** Entries with a `source_row_number` (in force or in
  conflict) are links to the Explorador filtered to the PMF with the row
  open: `/transelec/explorador?q=<pmf>&fila=<n>`. Following one closes the
  popover. The Explorador opens that row's drawer once its rows load, and
  removes `fila` from the URL when the drawer closes; if the row is not
  there it shows «No se encontró esta fila en la versión activa.» Edits made
  in that drawer refresh the Explorador as they do today, and the shared
  state as in §3. Other entries are not links.
- **More.** Beyond 8 entries: «y N más».
- **Footer** (operator/admin only): «Ver todas en Ediciones web →» and
  «Descargar planilla con ediciones (.xlsx)», the existing download with
  its own written/skipped note. The footer shows no count, since the
  download may write fewer cells than are in force.
- The popover never opens empty: the pill exists only after a successful
  load, and refreshes keep the old entries until new ones arrive.

### 6. Dashboard: «Ediciones web» shows the history

Below the existing table of active edits, «Historial» lists the shared
entries in the popover's format and labels, headed «Últimas 50 ediciones».

### 7. Dashboard: «web» marks in Estado

- `EstadoTable` renders `WebChip` in a cell when any field it shows is in
  the line's `web_fields`: «Grupo» and «Paso» (`estado_resumido`,
  `estado`), «Tipo de rechazo», «N.º ingreso (1 / 2)», «Reingreso tec /
  legal / recrep», and the plazo cell (`fecha_ingreso`, `fecha_ingreso_2`,
  `fecha_90_dias`).
- The chip's screen-reader `description` names the edited fields, not the
  column: «N.º ingreso 2 editado en la web»; several are joined with «y».
- When at least one line on the page has a web field, a note above the
  table reads «Los valores marcados «web» se editaron en el panel; la
  planilla publicada no cambió.»

### 8. Dashboard: the Resumen explains edited totals

When `web_edited_pmf_count > 0`, `StatusHeadline` shows a hint line next to
its existing notes: «Incluye 1 PMF con estado editado en la web.» (plural
«N PMF»), with a «Ver ediciones» button that calls `openLog`. The top bar
is sticky, so the log opens in view, and focus moves into it.

### 9. Dashboard: drawer fixes

- For operator/admin, «Campos editables» moves to the top of the drawer,
  right under the header chips.
- For operator/admin, «Tramitación» omits the `Fact`s of fields in
  `EDITABLE_FIELDS`. «Abrir Oficina Virtual CONAF», «Copiar N.º» and
  «Varias fechas en la celda» move into the matching rows of «Campos
  editables». `Fact`s of other fields stay. Viewers see no change.
- `EditableFieldsSection` is keyed by `source_row_number`, so switching rows
  starts it fresh (no stale «Se guardó el cambio»). If an editor holds an
  unsaved change when another row is chosen, `ConfirmDialog` asks
  «¿Descartar el cambio sin guardar?» first. A save always goes to the row
  the editor was opened on.

### 10. Dashboard: suggestions without case or accent variants

`suggestionsFrom` groups values by
`key(v) = v.replace(/ /g, ' ').trim().replace(/\s+/g, ' ')
.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('es')`
(the backend also treats U+00A0 as a space). Each group shows the spelling
that occurs most often in the active version; ties go to the first in `es`
order. Picking a suggestion writes it as shown. Typing any value is still
allowed; the server's rules are unchanged.

## Testing

- **API integration** (`apps/api/integration_tests/test_transelec_overrides.py`):
  - entries after save, supersede, both `discarded` producers, keep and
    incorporation, with the right `state`, `ended_by_display_name` and
    order;
  - after a restore of an older version, earlier entries are still listed;
  - `source_row_number` set for `aplicada` and `en_conflicto`, null for
    `huerfana` and every ended entry;
  - counts independent of `limit`; an active `incorporada` edit is listed
    and counted in neither; viewer 200; 404 with nothing published.
- **API reads** (`test_transelec_reads_router.py`): `web_edited_pmf_count`
  counts first-row edits to `estado_resumido`/`estado`, ignores edits on
  other rows and other fields, and follows filters.
- **Vitest.**
  - Pill: text, singular and plural, «por revisar», hidden states, narrow
    form, accessible name (`Chrome.test.tsx`).
  - Popover content: entries, the label for every state, value clamping,
    «(vacío)», dates in Chile time, footer by role, entry links.
  - Estado chips and their descriptions for combined cells, and the note
    (`EstadoTable.test.tsx`); the Resumen hint (`StatusHeadline.test.tsx`).
  - Drawer: order, Tramitación by role, the remount and the unsaved-change
    confirmation (`RowDetailDrawer.test.tsx`, `EditableFieldsSection.test.tsx`).
  - Grouped suggestions, including NBSP, accents and ties
    (`lib/webEdits.test.ts`); Ediciones «Historial»; the provider's
    refresh triggers and stale-response guard.
  - jsdom may not implement the Popover API; there, unit tests cover
    content and attributes, and Playwright covers opening and closing.
- **Playwright** (`tests/e2e/web-edits.spec.ts`, `stubPlatform` extras):
  open with the pill, Esc and outside click close it and focus returns;
  an entry opens the Explorador drawer on the right row, and an edit there
  updates the pill; an entry whose row is gone shows the notice; viewer
  sees the pill without the footer; the shell bar still fits at 1280 and
  1024 px and the panel at 390 px (`navigation.spec.ts`).
- **Manual:** the local replay of production, signed in as the Transelec
  admin, which already holds the UX review's edits (in force, replaced and
  reverted).

## Risks and limitations

- **LIMITATION:** the log shows the latest 50 edits (the popover the
  latest 8). Older ones remain in the database only.
- **LIMITATION:** `kept` and `superseded` entries have no link to the entry
  that replaced them; the labels say what happened, and the newer entry
  sits above.
- **LIMITATION:** «web» marks in Estado reflect the PMF's first row only,
  like every Estado value. Edits on other rows show in the Explorador and
  the log.
- **LIMITATION:** the pill is not live. It updates after the user's own
  edits and when the tab regains focus.
- Browsers older than January 2026 lack anchor positioning; the popover
  then sits fixed at the bar's right edge, under the pill's usual place.

## Out of scope (Spec 2, to be designed next)

- Editing a whole PMF: one save applies to every row of the PMF in one
  transaction, with «se aplicará a las N filas de …»; per-row edits stay in
  the drawer for exceptions (DECISION above). Needs a new API.
- «Estado resumido» and «Estado» edited together as one control.
- Editing in the Estado table (PMF level) and the Explorador (row level)
  with editors anchored to the cell; the drawer stays the mobile path.
- Validating count fields («Reingreso …») as non-negative whole numbers.
- Linking Calidad findings to the editor.
