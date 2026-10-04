# Transelec: edit values in the dashboard and download the planilla marked «web»

Date: 2026-10-04. Status: design approved in conversation with Rafael,
section by section; this file awaits his review before a plan is written.
Backlog item PR-3 of
[the post-launch backlog](../../../products/transelect/docs/design/2026-10-02-post-launch-backlog-v1.md).
Sibling specs, built in parallel:
[Estado](2026-10-04-transelec-estado-lifecycle-design.md) and
[90 días hábiles](2026-10-04-transelec-plazo-90-habiles-design.md).
Merge order: Estado → 90 días (stacked on the Estado branch) → web edits;
each rebased on `main` before merging.

## Goal

Campo Digital's client wants to correct values such as *Estado resumido*
in the dashboard, then download the planilla with the same structure, the
edited cells marked «web» and everything else unchanged (meeting of
2026-10-02, request R4). Every dashboard view must show the edited value. A
later upload must never silently overwrite or lose an edit.

## Decisions taken with Rafael (DECISION, 2026-10-04)

| Topic | Decision |
|---|---|
| Editable fields | The 11 status and ingreso fields listed below. Identity fields and formula columns are never editable. |
| Who edits | Operator and admin on `transelect`. Viewers read edits but cannot make them. |
| Mark in the download | Light fill on the cell plus an Excel note «web · <quién> · <fecha> · antes: <valor>». No new columns. |
| How edits reach the views | One PostgreSQL relation, "rows with edits applied", that every read goes through. |
| How the download is made | Patch the uploaded file: copy every part, rewrite only the edited cells and what they need. |
| Planilla changes an edited cell | The planilla wins; the edit is paused and flagged until someone keeps or discards it. |
| On open in Excel | Recalculate formulas and refresh pivot caches on open. |
| Granularity | One edit is one cell of one source row. No PMF-wide edit in this version. |
| Who downloads the .xlsx | Operator and admin. Viewers keep the CSV, which now carries edited values. |

## Evidence (FACT, 2026-10-04)

From the code (`main` at `d1e311f`):

- Imports and their rows are immutable. Publishing moves the singleton
  pointer `platform.transelec_dashboard_state.active_import_id`
  (`apps/api/app/transelec_publication.py:61-123`). Every read filters
  `WHERE import_id = <active>`.
- The API has no PUT, PATCH or DELETE route for Transelec data.
- `_fetch_filtered_rows` (`apps/api/app/routers/transelec.py:759-783`) feeds
  `/summary`, `/aef`, `/pending`, `/owner-status`, `/report` and
  `/export.csv`. `/pmfs` (1135-1193) and `/pmfs/{pmf}` (1204-1239) issue
  their own SQL. Filters and `q` are SQL `WHERE` clauses on the row columns
  (`_build_filter_where`, 694-721).
- The uploaded workbook is kept: `transelec_import.source_snapshot_id` →
  `source_snapshot.object_storage_key` → `ObjectStore.open()`
  (`apps/api/app/object_store.py`).
- `transelec_import.mapping_report` stores, per field, the worksheet name,
  the header row and the column letter (`resumen_layout.LayoutReport.to_dict`).
  `source_row_number` is the Excel row number.
- Roles: `access.Role` ADMIN/OPERATOR/VIEWER. `access.Action` has no edit
  action. Mutations use `Depends(require_csrf)` plus
  `require_transelec_grant(action)`.
- `record_audit_event` must not carry raw source content in `metadata`
  (`apps/api/app/audit.py`).
- Runtime dependencies: `python-calamine` (read-only) under the `transelec`
  extra. `xlsxwriter` is a dev-only dependency and is not in the production
  image. `openpyxl` is absent.

From the three planillas received (14-Ago, 09-Sept, 30-Sept-2026), read
locally with the importer's own loader; counts only:

- 729 business rows each. The key PMF + Rol + N Predio + N Area de Corta has
  726 distinct values; 5 rows share a key, in 2 groups.
- Between consecutive planillas every key was present in both, and every row
  kept its row number.

From `PlanillaMaestra-CD_30sep2026.xlsx` (ZIP structure, read-only):

- 7 worksheets. `Resumen` is `xl/worksheets/sheet1.xml` (≈ 1 MB). `Reingresos`
  is `sheet2.xml` (≈ 151 MB uncompressed). The file is 16 MB.
- 5 pivot tables live on `Resumen` itself, right of the business table. They
  share one cache whose source is `Resumen!F1:AH726`.
- Formula cells in `Resumen`: column AH (`ID_Predo_Unico`), all 729 rows;
  column AB (`Hoy`), 109 rows. None of the 11 editable columns holds a formula.
- `Resumen` has merged cells (in `ID_Predio_UnicoII`) and no notes
  (`legacyDrawing` absent). Its relationships are the 5 pivot tables and a
  printer-settings part.
- The workbook has a `calcChain.xml`.

## Editable fields

`estado`, `estado_resumido`, `tipo_rechazo`, `reingreso_tec`,
`reingreso_legal`, `reingreso_recrep` (text), `fecha_ingreso`,
`fecha_ingreso_2`, `fecha_90_dias` (date), `numero_ingreso`,
`numero_ingreso_2` (text).

Never editable: `pmf`, `rol`, `numero_predio`, `numero_area_corta`,
`id_predio_unico`, `id_predio_unico_ii`, `id_pmf`, `hoy` (formula or identity).
All other fields are outside this version.

## Design

### 1. Storage: `platform.transelec_field_override` (migration 0012)

One row per edit of one cell. Columns:

- `id` bigint identity, primary key.
- Row key: `pmf` text not null; `rol`, `numero_predio`, `numero_area_corta`
  text null; `key_ordinal` int not null. `key_ordinal` is the 1-based position of the
  row among rows of the same import sharing the four-part key, ordered by
  `source_row_number`. It is 1 for every row whose key is unique.
- `field` text not null, checked against the 11 names.
- `value_text` text null, `value_date` date null. A check enforces that a
  date field uses only `value_date` and a text field only `value_text`.
  Both null means the cell was cleared.
- `planilla_value_text` text null, `planilla_value_date` date null. These hold
  the planilla's value at edit time. For a date field whose cell held text,
  the raw text goes in `planilla_value_text`.
- `base_import_id` bigint not null, FK to `transelec_import`.
- `created_by_app_user_id` bigint not null, FK to `app_user`;
  `created_at` timestamptz not null default `now()`.
- `ended_at` timestamptz null; `ended_by_app_user_id` bigint null;
  `end_reason` text null, checked in (`superseded`, `discarded`, `kept`,
  `incorporated`).
- Partial unique index on the key, `key_ordinal` and `field`
  `WHERE ended_at IS NULL`: at most one active edit per cell.

Rows are never deleted. Editing the same cell again ends the active edit
(`superseded`) and inserts a new one, so the table is the edit history.

Revision id `0012` follows ADR-003. Only this PR adds a migration among the
three parallel PRs.

### 2. Status of an active edit against the active version

Computed on every read:

| The active version's matching cell | Status | Shown value |
|---|---|---|
| equals the planilla value seen at edit time | `aplicada` | web value |
| equals the web value | `incorporada` | planilla value (identical) |
| anything else | `en_conflicto` | planilla value |
| no row with that key and ordinal | `huerfana` | — |

Value comparison normalizes text: trim, collapse internal whitespace,
compare case-sensitively. Dates compare as dates. For a date cell held as
text, the comparison uses its raw text.

When an import is activated (publish or restore), the same transaction ends
every active edit whose status against the newly active version is
`incorporada` (`end_reason = 'incorporated'`). Without this step, a later
legitimate change in the planilla would show as a conflict.

LIMITATION: restoring an older version after an edit was incorporated does
not bring the edit back. The edit history still shows it.

### 3. One read layer: view `platform.transelec_effective_row`

Created in migration 0012. Over `transelec_resumen_row` it:

- computes `key_ordinal` with a window function partitioned by import and
  key;
- left-joins the active edits on key and ordinal;
- applies each field as `CASE WHEN <aplicada> THEN <web value> ELSE <source
  value> END`, keeping the source column names;
- adds `web_fields text[]`, the fields currently showing a web value.

`_fetch_filtered_rows`, both `/pmfs` queries and the `/pmfs` `count(*)`
select `FROM platform.transelec_effective_row` instead of
`transelec_resumen_row`. Filters, `q`, cursor paging and every product module
(`summary_view`, `aef_view`, `pending_view`, `owner_status_view`,
`csv_export`, and the new `lifecycle_view` and `plazo_conaf`) then see edited
values without change. The ingestion and projection paths keep writing to
and reading from `transelec_resumen_row`.

`ResumenRowView` gains `web_fields: list[str]`.

### 4. API

New action `Action.EDIT`, allowed for OPERATOR and ADMIN (`access._ALLOWED`).

| Route | Gate | Behaviour |
|---|---|---|
| `PUT /api/transelec/overrides` | CSRF + EDIT | Save one cell. Body: `import_id`, `source_row_number`, `field`, `value` (string, ISO date, or null), `expected_value` (the value the editor saw). |
| `DELETE /api/transelec/overrides/{id}` | CSRF + EDIT | Return to the planilla value (`discarded`). |
| `POST /api/transelec/overrides/{id}/keep` | CSRF + EDIT | Only for `en_conflicto`. Ends the edit (`kept`) and inserts a copy with the same value and the current planilla value as `planilla_value_*`, so it applies again. |
| `GET /api/transelec/overrides` | VIEW | Active edits with status, row, field, planilla value, web value, author display name and time. Optional `status` and `pmf` filters. |
| `GET /api/transelec/export.xlsx` | EDIT | Download the active version's planilla with applied edits (§5). |

Rules for `PUT`:

- **Stale version:** if `import_id` is not the active import, respond 409
  `version_changed`.
- **Validation:** an unknown row gives 404. A non-editable field, a malformed
  date or text over 500 characters gives 422.
- **Concurrent change:** if `expected_value` differs from the current
  effective value (compared as in §2), respond 409 `value_changed`. This stops two editors from
  overwriting each other.
- **Value equals the planilla:** if the new value equals the planilla's own
  cell, end any active edit (`discarded`) and insert nothing.
- Each request runs in one transaction and returns the effective row.

Audit events `transelec.override.saved`, `.discarded`, `.kept` and
`transelec.export.xlsx_downloaded` use `subject_kind = "transelec_override"`
or `"transelec_import"`. Metadata carries field names and counts, never
values.

### 5. The .xlsx download

New pure module `products/transelect/src/transelec_ingestion/xlsx_web_patch.py`.

**Input and output.** It takes the source path, the worksheet name and a list
of `CellEdit(row, column, kind, value, note)`, and writes a new file. It
uses only the standard library (`zipfile` plus text-level XML edits). It
never re-serializes a part with an XML library, because that renames
namespace prefixes that `mc:Ignorable` depends on, and Excel then reports the
file as damaged.

**The router's part:**

1. Read the active import's stored workbook from the object store into a
   temporary file. If there is no `object_storage_key`, respond 409.
2. Build the edits from the active edits with status `aplicada`:
   - row = `source_row_number`;
   - column = the field's column letter from `mapping_report`;
   - worksheet name and header row also come from `mapping_report`.
3. Stream the result as `<original stem>_web_<YYYY-MM-DD>.xlsx`, then delete
   the temporary files.

**The patcher:**

1. **Copy.** Every ZIP entry is copied in the original order, with the same
   name and compression method. Entries are streamed in chunks, so the
   151 MB `Reingresos` part is never held in memory. Only the parts listed
   below change.
2. **Cells.** The patcher rewrites only the target `<c>` elements in the
   worksheet XML.
   - **Text:** an inline string (`t="inlineStr"`). It becomes a number when
     the original cell was numeric and the new value parses as a number;
     this keeps `Reingreso_*` and plain `N Ingreso` cells numeric for pivots.
   - **Date:** an Excel serial number.
   - **Cleared:** an empty cell that keeps its style.
   - **Missing cell:** inserted at its column position in the row.
   - **Formula cell:** never written. It is reported back, and the pane
     lists it.
3. **Styles** (`xl/styles.xml`): append one `<fill>`, solid light yellow
   `FFFFF2CC`. For each distinct original style index among edited cells,
   append a clone of its `<xf>` with that fill. A date written into a cell
   whose style has no date format also gets `numFmtId="14"`. The `count`
   attributes are updated. Existing entries are untouched.
4. **Notes.** One note per edited cell, author `web`, text
   `web · <display name> · <dd-mm-aaaa> · antes: <planilla value or (vacía)>`.
   - If the sheet has no notes, the patcher adds a comments part, a VML
     drawing part, two relationships, a `<legacyDrawing>` element at its
     schema position, and the content-type entries.
   - If notes exist, it appends to the existing parts.
5. **On open:**
   - `xl/workbook.xml`: `<calcPr fullCalcOnLoad="1">`, adding `calcPr` if
     absent.
   - Each `pivotCacheDefinition`: `refreshOnLoad="1"`.
   - `calcChain.xml` is left as is, since no formula is added or removed.

Uploading the downloaded file as a new version works like any other upload.
Fills and notes are ignored by the importer. Every edit then becomes
`incorporada` and retires on activation.

### 6. Dashboard

- **Row drawer** (`RowDetailDrawer.tsx`):
  - for operator/admin, an *Editar* control beside each editable field;
  - a date input for dates;
  - for `estado`, `estado_resumido` and `tipo_rechazo`, a text input with a
    `datalist` of the values present in the active version;
  - Guardar and Cancelar;
  - errors from 409 and 422 shown in place, with a *Recargar* action.
- **«web» chip** next to a value whose field is in `web_fields`. The tooltip
  reads "Editado en la web por <nombre> · <fecha> · en la planilla: <valor>",
  taken from `GET /overrides?pmf=`. *Volver al valor de la planilla* calls
  `DELETE`. Viewers see the chip and tooltip only.
- **Explorador:** edited cells carry the chip.
- **Datos → «Ediciones web»** (operator/admin, beside Importar and Versiones):
  - a table of active edits, `en_conflicto` and `huerfana` first;
  - row, field, planilla → web, author and date, status;
  - actions *Mantener valor web* (conflicts), *Descartar* and *Ver fila*;
  - the button *Descargar planilla con ediciones (.xlsx)*, with a note on how
    many edits it writes and which it skips and why.
- **Calidad:** a block "Ediciones web en conflicto" with the count and a link
  to the pane. It is hidden when there are none.
- **API client:** `api.ts` gains `saveOverride`, `discardOverride`,
  `keepOverride`, `listOverrides` and `exportXlsxUrl`, using `request()` (CSRF
  handled). `canEdit` mirrors `canPublish`.

## Testing

- **Product unit tests** (`products/transelect/tests/test_xlsx_web_patch.py`).
  Workbooks are built with `xlsxwriter` in the test. They cover text, number,
  date and missing cells; a formula cell refused; a sheet with and without
  notes; and a pivot-cache flag.
  - Every ZIP part except the touched ones is byte-identical after
    decompression.
  - `load_transelec_workbook` on the output reads the web values.
  - The note text and the new `<xf>` are present.
- **Integration tests** (`apps/api/integration_tests/test_transelec_overrides.py`):
  - **Gating:** CSRF required; viewer 403; operator and admin allowed.
  - **PUT outcomes:** 409 `version_changed`, 409 `value_changed`, 422 for a
    non-editable field, no-op when the value equals the planilla.
  - **History:** supersede keeps history.
  - **Every read sees the edit:** `/summary`, `/pmfs`, `/pmfs/{pmf}`, filters,
    `q` and `/export.csv`.
  - **Statuses on activation:** `incorporada` retires;
    `en_conflicto` shows the planilla value; `keep` re-applies; `huerfana`
    is listed.
  - `/export.xlsx` returns a workbook whose target cell holds the web value.
  - Audit rows carry no values.
- **Migration:** `test_migration_graph.py` passes, plus upgrade/downgrade on
  the disposable test database.
- **Dashboard:**
  - vitest for the field editor and chip;
  - Playwright with `stubPlatform` extras: edit and save, 409 path, viewer
    without controls, the Ediciones web pane, Calidad block, download link.
- **Manual, before the first release, not in CI** (the file stays outside
  Git): patch three cells of the real 30-Sept planilla locally and check
  that every other part is identical, then Rafael opens it in Excel and
  confirms the fills, the notes, the refreshed pivots and that no repair
  prompt appears.

## Risks and limitations

- **Download time.** Recompressing the 151 MB part takes seconds per
  download. If measurement shows it is too slow, copy that entry's
  compressed bytes without recompressing (a low-level ZIP copy). This would
  not change the design.
- **Restore.** See §2: restoring an older version does not resurrect an
  incorporated edit.
- **Not a full XML parser.** The text-level XML edits rely on the SpreadsheetML
  shapes Excel writes. The tests pin those shapes. An unexpected shape makes
  the patcher refuse with a clear error rather than write a damaged file.
- **Edits are per row.** Editing *Estado resumido* on a PMF's second row
  does not change PMF-level counts, which read the first row (existing
  `first_row_wins` rule). The drawer already says which row counts.

## Out of scope

- Editing fields beyond the 11.
- PMF-wide edits.
- Bulk edit.
- Writing edits into the other worksheets.
- Viewer downloads of the .xlsx.

## Plan refinements (2026-10-04)

Found while writing
[the implementation plan](../plans/2026-10-04-transelec-web-edits-xlsx.md),
which records the evidence (the migration SQL and the patcher were exercised
locally; the patcher handled the real 30-Sept planilla in 1.9 s with every
untouched part byte-identical):

- **Blank cells.** A cell absent from the sheet XML also accepts a number. The
  real planilla omits blank cells.
- **Fields without a column.** Editing a field the active version has no
  column for answers 422, since such an edit could never be downloaded.
- **Retiring incorporated edits.** This happens in the router's `_activate`,
  inside the activation transaction.
- **Note dates.** The date in each note comes from PostgreSQL in
  `America/Santiago`; no `tzdata` dependency is needed for this feature.
- **Page paths.** The «Ediciones web» pane adds `transelec/ediciones` to
  `TRANSELEC_SPA_PAGE_PATHS`.
- **View columns.** The view's column list is fixed in migration 0012. A test
  fails if a future contract column is missing from it.

### Execution refinements (2026-10-04, decided while building)

- **Text comparison.** It treats U+00A0 (NBSP) as whitespace in both Python and
  SQL, so a value padded with NBSP equals the plain one.
- **Concurrent edits.**
  - Save, discard and keep take a per-cell advisory lock before checking the
    value the editor saw, so two concurrent edits cannot overwrite each other.
  - Only a violation of the active-cell unique index maps to 409
    `value_changed`.
- **Database checks.** An ended edit must carry `end_reason`, and a stored
  planilla value sets at most one side (text or date).
- **Incorporated edits.** Retirement on activation considers only fields the
  newly active version has a column for. LIMITATION: while an older layout is
  active, an edit to a «…2» field shows as incorporated or applied until the
  newer layout returns.
- **Formula cells.** Skips are recorded in the export's audit row only.
- **Download.**
  - The download fetches the file and shows the server's Spanish error, or
    Spanish copy for 403/5xx.
  - The patcher places the note anchor among the sheet's top-level elements
    only, so an Excel 2010 data bar's nested `<extLst>` cannot capture it.
  - A blank cell starts from the row or column style Excel shows for it.
