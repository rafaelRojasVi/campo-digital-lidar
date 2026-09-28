# Transelec Source Contract V1

## Status

Superseded for layout handling by [Source Contract V2](source-contract-v2.md)
(2026-09-26): columns are now recognized by header rather than bound to
A:AD, because the 09-Sept-2026 workbook inserted five columns at A:E. The
identity, status and auxiliary-worksheet observations below still apply.

## Authoritative current source

The current operational workbook is read from the Campo Digital OneDrive source
boundary. Private source files are not committed to Git.

The current source workbook contains these worksheets:

- `Resumen`
- `Reingresos`
- historical `Resumen` snapshots
- `Pendientes`
- `Urgentes 07May`

V1 ingestion reads only `Resumen`.

## Established observations

For the workbook reviewed on 2026-08-27:

- 729 rows in `Resumen` contain a PMF and are treated as current business rows;
- 159 distinct PMF values are present;
- 272 distinct populated `ID_Predo_Unico` values are present;
- `Resumen` contains two different columns both named `Carpeta`;
- column identity must therefore be positional rather than dictionary-by-header;
- rows without PMF are outside the V1 current-business-row projection.

These counts are evidence for the reviewed source snapshot, not permanent
business invariants.

## Identity

`PMF` is a source identifier.

`ID_Predo_Unico` appears useful as a predio-level source identifier, but its
long-term stability and business semantics have not yet been confirmed.
Accordingly the code calls it a provisional predio identity.

`N Area de Corta` is preserved as source data and is not assumed to be globally
unique.

No canonical area-of-cut primary key is defined by this contract.

## Status

Both detailed `Estado` and summarized `Estado resumido` are preserved as source
fields.

The source evidence does not yet establish a deterministic rule for collapsing
multiple row states into one PMF-level state. No such aggregation rule is
implemented in V1.

## Dates

Workbook date fields are source data.

The workbook field `Hoy` must not be treated as platform ingestion time.
Observation time belongs to the shared source-provenance infrastructure.

## Auxiliary worksheets

`Pendientes` and `Reingresos` contain potentially relevant operational evidence,
but they are deliberately outside the first parser contract.

They require separate schema and semantics review before ingestion.

Historical `Resumen` worksheets must not be merged automatically into current
state. Platform snapshot/history semantics own source history.

## Schema-change policy

A changed value under the established columns is a normal data change.

The V1 business-table contract owns columns A through AD of `Resumen`.

A renamed, removed, or reordered column inside A:AD is a schema change and must
fail validation for review rather than silently changing the projection.

Column AE is currently a blank separator and is validated as such. Content from
AF onward is worksheet-local auxiliary/presentation material and is deliberately
outside the V1 business-table projection.

## Not yet established

The following require stakeholder or stronger source evidence:

- canonical PMF identity semantics;
- canonical predio identity semantics;
- canonical area-of-cut identity;
- PMF-level status aggregation;
- relationship of reingresos to current rows;
- operational meaning of `Pendientes`;
- approval/rejection transition rules;
- whether source rows may legitimately disappear;
- correction versus supersession semantics.
