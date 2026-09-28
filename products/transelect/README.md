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

Run it locally with `make transelec-dev` from the repository root.
