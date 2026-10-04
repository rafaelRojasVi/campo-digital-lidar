# Transelec

Transelec is a Campo Digital bounded product context.

The repository path retains the historical technical spelling
`products/transelect/`. The stakeholder/project name is **Transelec**.

## Current status

Source Contract V2 is implemented: the `Resumen` worksheet's columns are
recognized by header, the review report is persisted with each import, and
the AEF tracking block added in the 09-Sept-2026 workbook is projected and
shown in the dashboard. See [Source Contract V2](docs/source-contract-v2.md)
and, for the original observations, [Source Contract V1](docs/source-contract-v1.md).

## Source boundary

Expected external source location:

`03_Proyecto_Transelec/02_Datos_Entrada/`

Source files remain outside Git.

## Current implementation

`transelec_ingestion.resumen_layout` (used through
`transelec_ingestion.xlsx_contract.load_transelec_workbook`):

- finds the `Resumen` worksheet and detects its header row;
- maps columns by normalized header and documented aliases, tolerating
  inserted, reordered and extra columns and a moved separator;
- binds the two source columns both named `Carpeta` explicitly, from their
  neighbours, and refuses when that is ambiguous;
- ignores worksheet-local summary/pivot regions beyond a blank separator;
- preserves source row numbers and records every mapping decision, ignored
  column and issue (with row/column references) in a report;
- blocks on missing identity/required columns, ambiguous mappings and
  conflicting duplicate columns; warns on data it cannot read as typed, on
  AEF date-order inconsistencies, on PMF whose rows carry different AEF
  tracking values and on rows without PMF;
- reads a text date only when it is one written-out Spanish date, and keeps
  the raw text of every text cell in a date column;
- treats `ID_Predo_Unico` only as a provisional source-derived predio identity.

AEF tracking values are presented per PMF with the source rows that supplied
them; rows are never rewritten, and a PMF whose rows disagree is flagged, not
resolved. No PMF-level status rule has been inferred.

## Dashboard

The operator-facing dashboard lives in `dashboard/` (React 19, no UI
framework, no routing library). Its information architecture, design tokens
and the audit that produced them are recorded in:

- [Frontend UX rearchitecture V1](docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md)
- [Rediseño de la interfaz (español)](docs/es/2026-09-13-rediseno-interfaz-transelec.md)
- [Workflow refinement from Marianne's evidence V1](docs/design/2026-09-15-workflow-refinement-marianne-evidence-v1.md)
- [Estado de los planes de manejo (español)](docs/es/2026-09-15-estado-planes-de-manejo.md)
- [Planilla del 09-sept: seguimiento AEF y revisión de columnas (español)](docs/es/2026-09-26-planilla-09sept-seguimiento-aef.md)
- [Dashboard usability pass — 2026-09-26](docs/design/2026-09-26-dashboard-usability-pass.md)
- [Panel Transelec: mejoras de uso y preguntas (español)](docs/es/2026-09-26-panel-usabilidad.md)
- [Post-launch backlog V1 — 2026-10-02](docs/design/2026-10-02-post-launch-backlog-v1.md)
- [Reunión del 02-10-2026: cambios pedidos y preguntas (español)](docs/es/2026-10-02-reunion-cambios-y-preguntas.md)
- [Planilla del 30-sept: segundo ingreso y columnas renombradas (español)](docs/es/2026-10-02-planilla-30sep-segundo-ingreso.md)

### Web edits

Operators and administrators can correct eleven status and ingreso fields
from the row drawer; viewers see the edited values and who made them. The
design is `docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md`
(on the specs branch, not linked here).

- FACT: The editable fields, with their drawer labels, are «Estado resumido»,
  «Estado vigente», «Motivo», «Reingreso técnico», «Reingreso legal»,
  «Reingreso rec. reposición», «N.º ingreso», «Fecha ingreso», «N.º ingreso 2»,
  «Fecha ingreso 2» and «90 días». Identity fields (PMF, Rol, N Predio,
  ID_Predo_Unico) and the formula column «Hoy» are never editable.
- FACT: An edited value is shown everywhere with a «web» chip and its
  provenance (who and when). «Volver al valor de la planilla» ends the edit.
  Web edits never modify the published version or the stored planilla.
- FACT: Conflicts. When a later published version changes the same cell, the
  planilla wins and the edit is flagged «En conflicto con la planilla».
  «Mantener valor web» re-applies the web value over the new planilla value;
  «Descartar» deletes the edit. An edit whose row no longer exists is shown
  as «Sin fila en la versión publicada» and is neither displayed nor written.
  An edit whose value the planilla already holds is «Ya está en la planilla».
- FACT: Datos → Ediciones web (`/transelec/ediciones`) lists the edits and
  downloads the uploaded planilla with only the applied edits written. Each
  written cell gets a fill colour and an Excel note; the workbook and its
  pivot are set to recalculate and refresh when opened. All other parts of
  the package are copied unchanged.
- FACT: A cell holding a formula is skipped by the download (audit only: the
  edit stays recorded but is not written).
- DECISION: The planilla wins on conflict, so a stale web value can never
  silently override newer source data.
- LIMITATION: Planillas in the V1 layout have no second-ingreso columns, so
  «N.º ingreso 2» and «Fecha ingreso 2» cannot be edited on a V1 version.
- LIMITATION: Restoring an older version does not resurrect an edit that was
  already incorporated into a newer planilla.
- RESULT: A read-only check of a real planilla (counts only, no business
  values recorded) wrote 3 edits in 2.0 s with 0 skipped,
  left every untouched package part byte-identical, preserved entry order and
  re-imported with 729 rows and 0 errors. OPEN QUESTION: the check in Excel
  itself is pending.

Run it locally with `make transelec-dev` from the repository root.
