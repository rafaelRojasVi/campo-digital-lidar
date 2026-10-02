# Transelec Source Contract V2 — recognized `Resumen` layout

## Status

Implemented (`transelec_ingestion.resumen_layout`, parser
`transelec_ingestion.resumen_layout@3`, schema contract `transelec-resumen-v2`).
Supersedes the positional A:AD gate of [Source Contract V1](source-contract-v1.md);
V1's observations about identity, status and auxiliary worksheets still stand.

Amended 2026-10-02 for the 30-Sept-2026 workbook (parser `@2` → `@3`): the
first ingreso pair is recognized under its renamed headers and a second
ingreso pair is read. See "Evidence from the 30-Sept-2026 workbook" and the
DECISION there. The planning record is
[Transelec post-launch backlog V1](design/2026-10-02-post-launch-backlog-v1.md).

## Why V1 had to change

The workbook `PlanillaMaestra-CD_09Sept26.xlsx` (SHA-256 `50253143defb…`,
received 2026-09-26) inserted five columns at A:E of `Resumen`:

| Column | Header            |
| ------ | ----------------- |
| A      | `AEF`             |
| B      | `Quien solicita`  |
| C      | `Fecha solicitud` |
| D      | `Fecha corta`     |
| E      | `Fecha termino`   |

The 30 V1 business fields moved from A:AD to F:AI unchanged, the blank
separator moved from AE to AJ, and worksheet-local summary/pivot tables occupy
AK onward. V1 bound fields to fixed positions and rejected any change, so it
could only reject this benign insertion.

## Evidence from the 09-Sept-2026 workbook

FACT (reproducible with the opt-in private test
`test_private_09_sept_2026_workbook`, run with
`TRANSELEC_PRIVATE_WORKBOOK_0909=<path>`):

- 729 rows with PMF, 159 distinct PMF, 272 distinct `ID_Predo_Unico`,
  164.6288 total `Superficie de corta` — the same shape V1 observed.
- `AEF`, `Fecha corta` and `Fecha termino` are filled on 23 rows;
  `Quien solicita` and `Fecha solicitud` on 19.
- The 23 AEF rows belong to 23 different PMF, and in every case the AEF row is
  the PMF's first source row (each PMF's rows are contiguous). 19 of those 23
  PMF have other rows without AEF.
- All 23 `Fecha termino` values fall on day 1 of a month.
- Row 315: `Fecha corta` precedes `Fecha solicitud`. Row 375: `Fecha termino`
  precedes `Fecha corta`.
- `Fecha de ingreso` (Y) holds 124 and `90 dias` (AA) 63 cells that are text,
  not Excel dates. Of those 187 cells: 67 are a single date written out in
  Spanish (`Fecha de ingreso` 64, `90 dias` 3), 116 hold two dates in one
  cell (58 each; `DD-MM-YYYY` followed by `DD-MM-YY` or `DD-MM-YYYY`,
  separated by a space or a line break), and 4 are `-` (2 each).
- No PMF has two different non-blank values in any of the five AEF tracking
  fields.
- `ID_Predo_Unico` (AF) is a formula on all 729 rows and `Hoy` (AB) on 115;
  every formula has a cached value.
- Regression: for every row, each of the 30 legacy fields read by V2 equals a
  V1-style positional read shifted right by five columns.

## Evidence from the 30-Sept-2026 workbook

FACT (reproducible with the opt-in private test
`test_private_30_sept_2026_workbook`, run with
`TRANSELEC_PRIVATE_WORKBOOK_30SEP=<path>`; the workbook
`PlanillaMaestra-CD_30sep2026.xlsx` was received 2026-10-02 and stays outside
the repository):

- 729 rows with PMF. Header row 2; the AEF block at A:E and `PMF` at I as in
  the 09-Sept layout.
- Column Y is headed `Fecha de ingreso1` and Z `N Ingreso1` (the 09-Sept
  headers were `Fecha de ingreso` and `N Ingreso`). `90 dias` (AA) and `Hoy`
  (AB) are unchanged.
- Two new columns follow `Hoy`: AC `Fecha de ingreso2` and AD `N Ingreso2`,
  **blank on every row**. `Empresa` therefore moves from AC to AE, `Sector`
  from AI to AK, and the auxiliary regions start at AM.
- Before this amendment the parser reported `columna_no_reconocida` for Y, Z,
  AC and AD, `columna_esperada_ausente` for `fecha_ingreso` and
  `columna_esencial_ausente` for `numero_ingreso`: the workbook could not be
  imported. That is the intended V1/V2 behaviour for a renamed essential
  column — stop and ask — and it is what this amendment resolves.
- The text cells of the 09-Sept workbook are still there: `Fecha de ingreso1`
  holds 64 single Spanish written-out dates, 58 cells with two dates and 2
  `-`; `90 dias` holds 58 cells with two dates. `N Ingreso1` holds 562 cells
  shaped `n/n-n/n`, 101 plain numbers and about 58 cells with two such
  numbers separated by a space or a line break.

INFERENCE: the 58 two-value cells line up across `Fecha de ingreso1`,
`N Ingreso1` and `90 dias`. They most plausibly hold the first ingreso and the
reingreso of the same plan in one cell, and the new `…2` columns are the
source's way of separating them. Campo Digital has not confirmed this.

DECISION (2026-10-02):

- `Fecha de ingreso1` and `N Ingreso1` are documented aliases of
  `fecha_ingreso` and `numero_ingreso`. Both spellings bind the same field;
  the canonical headers stay `Fecha de ingreso` / `N Ingreso` (they name the
  fields in messages, the CSV export and the dashboard's rule copy).
- `Fecha de ingreso2` (date) and `N Ingreso2` (text) are new fields
  `fecha_ingreso_2` and `numero_ingreso_2`, tier **optional**: like the AEF
  block, they are absent from the 14-Aug and 09-Sept layouts, and a warning
  would force every re-publish of the live 09-Sept import through
  acknowledgement for a column its source never had. Text in
  `Fecha de ingreso2` follows "Rows and cells" unchanged and lands in
  `source_text_dates`.
- Nothing splits a two-value cell of the `…1` columns into the `…2` fields.
  Which value is the ingreso and which the reingreso is not established, and
  the source now has columns of its own for the second value.
- The parser version becomes `@3`: identical bytes now project two more
  columns. The schema contract string stays `transelec-resumen-v2`.

## Layout recognition

1. **Worksheet.** Exactly one sheet whose name normalizes to `resumen`.
   Historical snapshots (`Resumen 16Feb26`, …) never match.
2. **Header row.** The first 15 rows are scored by how many distinct fields
   they recognize. The row must contain `PMF` and at least 5 recognized
   fields; the highest score wins; a tie is an error.
3. **Normalization.** Case, accents, `°`/`º`, dots, underscores, hyphens,
   slashes and repeated whitespace are insignificant. Any other difference is
   a different header.
4. **Blocks.** Columns are split into blocks by *fully blank* columns (blank
   header and blank below it). The block holding `PMF` is the table. Another
   block is joined to it only if it contributes fields the table lacks
   (warning `columna_vacia_intermedia`); otherwise it is an ignored auxiliary
   region (`region_auxiliar_ignorada`). This is what lets the separator move
   and keeps pivot tables — even ones whose labels repeat a business header —
   out of the projection.
5. **The two `Carpeta` columns.** A bare `Carpeta` header is never resolved
   by name. It is bound by its nearest recognized neighbours:
   - left neighbour `PMF` → `carpeta_source` (the PMF's own folder);
   - left neighbour `Tramite` or right neighbour `Sector` →
     `carpeta_normalizada` (the coarser grouping).

   Both or neither rule holding, or two columns resolving to the same field,
   is `carpeta_ambigua` (error). The explicit headers `Carpeta origen` and
   `Carpeta normalizada` bind directly and are the documented way to resolve
   the ambiguity.
6. **Duplicates.** A field recognized in several columns is accepted only if
   the columns are identical on every data row (leftmost used, warning
   `encabezado_duplicado_identico`). Any differing row is
   `encabezado_duplicado_conflictivo` (error) listing the rows.

### Field registry, tiers and documented aliases

| Tier       | Missing column means            | Fields |
| ---------- | ------------------------------- | ------ |
| identity   | error `columna_esencial_ausente` | `PMF`, `ID_Predo_Unico`, `Rol`, `N Predio` |
| required   | error `columna_esencial_ausente` | `Estado`, `Estado resumido`, `Tipo de propietario`, `Superficie de corta`, `N Ingreso`, `Empresa` |
| expected   | warning `columna_esperada_ausente` | every other V1 field |
| optional   | info `columna_opcional_ausente` | the five AEF tracking fields; `Fecha de ingreso2`, `N Ingreso2` |

DECISION: identity fields feed `predio_group_key`; required fields feed the
published status/summary computations. Losing either would make published
numbers wrong rather than merely blank, so it blocks. The AEF fields are
optional so the earlier 30-column layout still imports.

Documented aliases (besides the canonical header):

| Field                    | Aliases |
| ------------------------ | ------- |
| `aef`                    | `Estado AEF` |
| `quien_solicita`         | `Solicitante`, `Solicitado por` |
| `fecha_solicitud`        | `Fecha de solicitud` |
| `fecha_corta`            | `Fecha de corta` |
| `fecha_termino`          | `Fecha de termino` (accents are insignificant) |
| `carpeta_source`         | `Carpeta origen` |
| `carpeta_normalizada`    | `Carpeta normalizada` |
| `superficie_total_corta` | `Superficie total de corta` |
| `fecha_ingreso`          | `Fecha de ingreso1` (30-Sept-2026 header) |
| `numero_ingreso`         | `N Ingreso1` (30-Sept-2026 header) |
| `id_predio_unico`        | `ID_Predio_Unico` (the source spells `ID_Predo_Unico`) |

The aliases are platform-defined, not observed in a source; adding one is a
code change reviewed like any other.

## Rows and cells

- A row blank in every mapped column is skipped.
- A row with mapped data but no PMF is not imported (warning `fila_sin_pmf`,
  with rows). DECISION: V1 skipped such rows silently; V2 keeps the
  documented V1 behaviour but reports it.
- Date fields take Excel dates. Text in a date column is classified
  (`resumen_layout.classify_text_date`), and its raw text is always kept on
  the row (`source_text_dates`, with the classification):
  - a whole cell that is one day + Spanish month word + four-digit year
    naming a real calendar day (`13 de noviembre de 2024`; case and accents
    insignificant; `setiembre` accepted) is read as that date — info
    `fecha_texto_interpretada`;
  - two or more dates in one cell are not resolved; the date is empty —
    warning `fecha_texto_multiple`;
  - a cell of only dashes is a placeholder; the date is empty — warning
    `fecha_texto_guion`;
  - anything else, including a single numeric `DD-MM-YYYY`, is not parsed;
    the date is empty — warning `fecha_no_reconocida`.

  DECISION: only the month-word form is parsed, because the word fixes the
  day/month order. Numeric forms are not parsed even when the day exceeds 12:
  the column's convention is not confirmed, and a rule that parses some
  numeric dates but not others would be hard to review. Which date of a
  two-date cell the column means is not established, so none is chosen.
  These four issues list every affected row (no 50-row cap).
- A number or time-of-day in a date column is left empty
  (`fecha_no_reconocida`).
- Non-numeric text in a number column is left empty (`numero_no_reconocido`)
  and excluded from totals, as in V1.
- Excel error cells (`#N/A`, `#REF!`, …) are left empty
  (`error_de_formula`). calamine reads them as blank, so they are detected
  from the sheet XML.
- Formula cells use their cached value (info `columna_con_formulas`); a
  formula saved without one reads as blank and is reported
  (`formula_sin_valor`).
- Chronology: `Fecha corta < Fecha solicitud`
  (`cronologia_corta_antes_de_solicitud`), `Fecha termino < Fecha corta`
  (`cronologia_termino_antes_de_corta`) and `Fecha termino < Fecha solicitud`
  (`cronologia_termino_antes_de_solicitud`). Every violated pair is reported;
  one issue per violated pair and row. The dates are stored as the source has
  them.
- Nothing is filled down, forward or across rows.

## AEF tracking per PMF

DECISION (2026-09-26): the five AEF tracking fields are presented per PMF.
In the 09-Sept workbook every AEF value is on its PMF's first row and the
PMF's other rows are blank, which reads as one record per PMF written once.
The rows themselves are not changed.

- `resumen_layout.resolve_pmf_field` resolves one field for one PMF from
  `(source_row_number, value)` pairs. Blank rows are ignored and never
  receive the value. If all non-blank rows agree (text trimmed, a midnight
  datetime equal to its date; nothing else normalized, so case differences
  disagree), the PMF value is that value, with the rows that supplied it. If
  they disagree, the status is `conflict`: no value, and each distinct value
  is listed with its rows.
- A date column whose text was not resolved contributes its raw text, so it
  can only agree with the same text, never with a date.
- Import: each field with at least one conflicting PMF produces a warning
  `aef_conflicto_pmf` listing every row that carries a value in those PMF.
  Like any warning, publishing then requires the explicit acknowledgement.
- Read: `GET /transelec/aef` resolves each PMF with a row in the filtered
  scope from *all* of that PMF's rows, so a PMF-level value does not change
  with an unrelated filter. Row-level counts and rows are still returned for
  the filtered scope.
- PMF-level chronology uses the resolved dates (which may come from
  different rows); a conflicting or blank date is not an ordering error.

## Severity and the import lifecycle

- `error` — validate-and-project answers **422** with the full layout report
  (every issue with column letters and worksheet row numbers) and persists
  nothing; the failure is audited with issue codes and references only.
- `warning` — the import is created, not activated. The dashboard requires
  the operator to acknowledge the warnings before the explicit publish step,
  and the API enforces it: `POST /imports/{id}/publish` answers **409** for
  an import with warnings unless `acknowledge_warnings=true` is sent, and the
  acknowledgement is recorded in the `import.published` audit event.
- `info` — recorded evidence.

Messages are Spanish and structural: headers, column letters, row numbers and
counts, never a business cell value (asserted by integration tests).

## Persistence

Migration `0009` (expand-only):

- `transelec_resumen_row` gains `aef`, `quien_solicita`, `fecha_solicitud`,
  `fecha_corta`, `fecha_termino` (nullable; indexed with `import_id` for
  `aef` and `quien_solicita`).
- `transelec_resumen_row` gains `source_text_dates` (JSONB, nullable): per
  date field whose cell held text, `{raw, resolution, parsed}`.
- `transelec_import` gains `mapping_report` (JSONB, NULL for V1 imports) and
  `warning_count`.

Migration `0011` (expand-only, 2026-10-02): `transelec_resumen_row` gains
`fecha_ingreso_2` (date) and `numero_ingreso_2` (text), nullable, no index.
NULL means the source row had no value or the source layout had no such
column; rows of earlier imports stay NULL.

The original upload stays content-addressed in the object store
(`source_snapshot`), and every row keeps its `source_row_number`. Imports made
under V1 report the 30 legacy fields as their source fields.

## API additions

- `ValidateAndProjectResponse`: `warning_count`, `mapping_report`.
- `GET /transelec/imports/{id}/report` (operator/admin).
- `GET /transelec/imports/active`: `warning_count`, `source_fields`.
- `GET /transelec/aef` (viewer+), `basis: "pmf_from_source_rows"`: per-PMF
  records (`pmfs`, each field with `status`, `value`, `value_kind`,
  `source_rows`, `variants`), PMF counts including conflicts and chronology,
  per-PMF value/requester breakdowns, plus the row-level counts,
  breakdowns and tracked rows, under the shared filters.
- Shared filters gain `aef` and `quien_solicita` multi-selects. They stay
  row-level: `aef=Presentado` matches the row that holds the value.
- Every row view gains the five fields, `chronology_flags` and
  `source_text_dates`. Since 2026-10-02 it also carries `fecha_ingreso_2` and
  `numero_ingreso_2`; `source_fields` of the active import says whether the
  published version's source had those columns, and the dashboard's row
  drawer shows the second ingreso only when it did.
- CSV export: the two folder columns are headed `Carpeta PMF` and `Carpeta
  normalizada` (they were `Carpeta (col. E)` / `Carpeta (col. AC)`, letters
  that became J/AH in this layout). `Fecha de ingreso` exports the raw text
  when the cell's text was not resolved to a date, instead of a blank. Since
  2026-10-02 the export has 20 columns: `Fecha de ingreso2` and `N Ingreso2`
  follow `N Ingreso`, blank for versions whose source had no such columns.

## Interpretation

INFERENCE: the AEF row being each PMF's first row suggests AEF is entered
once per PMF rather than per área de corta. The platform presents it per PMF
(see "AEF tracking per PMF") while keeping every row as the source has it;
Campo Digital has not confirmed this.

HYPOTHESIS: `Fecha termino` may have month precision (all values on day 1).
If so, row 375 (`Fecha corta` 8 Sept, `Fecha termino` 1 Sept) may not be an
error.

## Limitations

- The meaning of AEF values (`Presentado`, `Solicitado, se puede cortar`) is
  not defined by the source; values are grouped by literal text only.
- 120 text cells in `Fecha de ingreso` / `90 dias` (116 with two dates, 4
  `-`) still have no date; their raw text is kept and shown. The 90-day
  overdue view (TR-FUNC-031, `90 dias`) does not count those rows.
- The 67 parsed text dates now have a date where V1 had none; the 3 in
  `90 dias` now take part in the 90-day overdue view.
- The PMF-level presentation rests on the observed layout and a team
  decision, not on a confirmed definition of AEF.
- The 30-Sept-2026 `…2` columns are blank, so nothing yet exercises the
  second ingreso with real data; the 58 two-value cells of the `…1` columns
  remain unresolved raw text until the source moves the second value.

## Open questions for Campo Digital

- What does AEF stand for, and what does each value mean?
- Is AEF recorded once per PMF (as presented now), or per área de corta?
- Does `Fecha termino` carry a day, or only a month?
- Are rows 315 and 375 data-entry errors?
- Should text dates in `Fecha de ingreso` / `90 dias` be converted at source?
- In a cell with two dates, what does each date mean, and which one is the
  column's value?
- Is `Fecha de ingreso2` / `N Ingreso2` always the reingreso after a
  rejection? Will the two-value cells of `Fecha de ingreso1` / `N Ingreso1`
  be split into those columns at source? Can a plan have more than two
  ingresos?
