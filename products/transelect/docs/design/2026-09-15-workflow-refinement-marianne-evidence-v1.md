# Transelec dashboard — workflow refinement from Marianne's evidence V1

Status: implemented.

Scope: the Resumen/Calidad presentation in `products/transelect/dashboard`, the
pure aggregation in `products/transelect/src/transelec_ingestion`, and the
`GET /transelec/summary` response shape. No database schema, no migration, no
authentication or RBAC boundary, no import/publication semantics, no CSV field
set, and no existing status-rollup basis is changed by this work.

This refines [the UX rearchitecture](2026-09-13-frontend-ux-rearchitecture-v1.md)
rather than replacing it.

---

## 1. New evidence

First-hand, from Marianne — the person who currently produces Javier's Power BI
summary from the master workbook.

### FACT — stated by Marianne

- The spreadsheet is the template she uses to generate the Power BI summary.
- Javier's recurring question is **"¿Cuál es el estado de los planes de manejo?"**
- She answers it from the `Estado resumido` column.
- She additionally asked for "¿cuántos predios de reforestación son?" and
  "¿cuántos propietarios de reforestación son?"

### FACT — measured this session

Direct read of `PlanillaMaestra-CD_14Ago2026.xlsx` through the repository's own
`load_transelec_workbook`, from the read-only external source root. No file was
written, moved or renamed there.

| Observation | Value |
|---|---|
| Business rows in `Resumen` | 729 |
| Distinct `PMF` | 159 |
| Distinct `ID_Predo_Unico` | 272 |
| Distinct `Rol` | 221 |
| `Estado resumido` values | `Aprobado` 476, `En tramite` 248, `Tachado` 3, `Pendiente` 2 |
| `Estado` raw spellings | 13 |
| `Estado` spellings after case/accent folding | 11 |
| `Empresa` | `Campo digital` 652, `Ecores` 77 |
| Distinct non-blank `Predio Ref` | 33 (32 excluding `Sin reforestacion`) |
| Distinct non-blank `Rol Ref` | 35 |
| Non-blank `ID_PMF` rows | 159 of 729 |
| Blank `ID_Predo_Unico` rows | 0 |

PMF-grain, under the repository's existing `estado_resumido_first_row` basis:

| Bucket | PMF |
|---|---|
| Aprobado | 108 |
| En tramite | 48 |
| Tachado | 2 |
| Pendiente | 1 |
| **Total** | **159** |

By company, same grain: `Campo digital` 135 (86/46/2/1), `Ecores` 24 (22/2/0/0).
Both reconcile to the overall figures exactly.

### FACT — the source inconsistency, located

The 29 July Power BI summary reports 101 approved + 56 in process + 3 struck out
against a stated total of 159. Those buckets sum to **160**. The briefing
attributes this to `MP015` appearing under two `Estado resumido` values.

In the 14 August workbook, `MP015` carries a single `Estado resumido`
(`En tramite`, detailed `Estado` `Rechazado`, rows 259-261). The PMF that
carries two in this snapshot is **`MP022`**: `En tramite` on rows 293-306 and
308-314, `Tachado` on row 307, detailed `Estado` `Rechazado` throughout.

**INFERENCE.** The two snapshots differ; the mechanism is identical. The
implementation therefore detects the conflict generically and names whichever
PMF the published version actually contains. Nothing anywhere hard-codes
`MP015` or `MP022`.

### LIMITATION — the WhatsApp five-category screenshot

A separate screenshot reports Pendientes 27, No ingreso 3, Desistida 1,
Recurso 16, Rechazos 18, total 65. Those categories and that total **cannot be
reproduced** from `Estado resumido`, from `Estado`, or from any combination of
the supplied workbook's columns without an additional mapping, filter or a
different snapshot. No rule was invented to make the dashboard match 65. See
§6.

---

## 2. DECISION — PMF grain is the headline's unit

**Context.** The shipped Resumen led with an approval *percentage* at two
grains, with the plan counts demoted to a quiet reference strip. Javier's
question is about plans, and its answer is a count.

**Decision.** The Resumen's first analytical section is
`Estado de los planes de manejo`: the PMF total, then the `Estado resumido`
buckets at PMF grain, each clickable.

**Rationale.** The question is asked in plans; answering it in percentages of
two different denominators makes the reader do arithmetic the page should have
done. 729 rows describe 159 plans, so row-grain counting overstates the
programme by roughly 4.6×.

**Consequences.** `avance_por_pmf` (the three-way `aprobado` /
`en_tramite` / `pendiente_o_tachado` bar, TR-FUNC-010) is superseded at that
grain: the headline reads the same basis at the same grain, one bucket finer,
so `Tachado` is no longer merged into a catch-all. Its API field is unchanged
and still returned. The predio-grain figures (TR-FUNC-009 and TR-FUNC-011) are
**kept**, demoted to a section below the fold — a plan covers several cutting
properties, so 159 and 272 are two genuine denominators, and dropping one would
be a parity regression this work is not entitled to make.

---

## 3. DECISION — one PMF, one headline bucket

**Context.** A PMF whose rows disagree about `Estado resumido` can be counted
twice if the buckets are built row by row. That is precisely what produces
160 ≠ 159 in the Power BI summary.

**Decision.** Every headline figure is computed from one shared
`first_row_wins` representative per PMF — the row with the smallest
`source_row_number`, which is the contract `status_rollups` has always used.
The representative is computed **once** in `build_summary` and reused by the
status buckets, the detailed breakdown, the company matrix and the quality
indicators.

**Rationale.** Making the dedup structural rather than repeated at four call
sites is what makes "buckets sum to the total" a property of the code instead
of a property four separate places must each remember to preserve.

**Consequences.**

- Headline buckets sum exactly to the filtered PMF total, asserted in unit
  tests, in an API integration test, and **on screen**: if a future import ever
  breaks it, the reader is told the total is unreliable rather than shown
  buckets that quietly do not add up.
- The discarded evidence is not hidden. `estado_resumido_conflicts` reports
  every PMF carrying more than one summarized value, with all raw values, the
  canonical one, the detailed `Estado`, and the source row it came from. It
  surfaces in `Calidad` as its own section and as a note beside the headline.
- No new rollup basis was invented. TR-OPEN-01 stays open.

---

## 4. DECISION — normalisation reconciles spelling, never the source value

`normalized_label` folds case, combining accents and whitespace runs. It
collapses the workbook's 13 raw `Estado` spellings to 11 states — `En Evaluacion`
(129 rows) merges with `En evaluacion` (2), `Recurso reposicion` (9) with
`Recurso Reposicion` (1).

It is a **comparison key only**. Every breakdown displays the first raw spelling
the source used, never a rewrite, and the normalized key travels beside the
label in the API so a caller can reconcile two spellings that merged.

`ID_PMF` is populated on 159 of 729 rows. It is a per-PMF marker, not a row
identity, and it is deliberately not part of `SummaryInputRow` at all — a unit
test asserts its absence, so grouping on it cannot be reintroduced by accident.

---

## 5. DECISION — reforestation reports labels, and no owner count

**Inspection of the existing metric.** `predios_reforestacion` was
`sorted({predio_ref for rows if non-blank})` — distinct non-blank `Predio Ref`,
with no sentinel handling. In the 14 August workbook that returns 33, one of
which is the literal `Sin reforestacion`.

**Decision.**

- The metric counts **distinct non-blank `Predio Ref` values, excluding the
  literal `Sin reforestacion`** — 32 in the reviewed snapshot. Matching is on
  the normalized label, so an accented or recased spelling of the sentinel is
  still excluded.
- It is labelled `Etiquetas de «Predio Ref»`, not "predios", and the full
  definition is printed beside the number.
- Six values visibly name more than one property
  (`Helga + Niklitschek + Alcaino + Marin`, `Ref. 2_Toro + Ref. 35 Barria`,
  `Ref036_ Reyes y Ref037_ Reyes`, `Rubi + Marin`, `Rubi + Narwrath`,
  `Werner + Mavelasqquez`). These are listed, and the disclosure states the
  detection is a lower bound — `Ref003 Ref004_ Nawrath` names two properties
  with no separator at all and is not caught.
- **No owner count is produced anywhere.** `Tipo de propietario` is a tenure
  category (`Servidumbre firmada` 382 rows, `Poseedor` 126, `BNUP` 87,
  concession variants 129, `-` 5) shared by hundreds of rows, and the surnames
  inside `Predio Ref` are free text within a label that sometimes names several
  properties. The owner slot carries the literal
  `No disponible en el origen` — deliberately not a zero, which would read as
  "there are no owners" rather than "this cannot be known".
- **No migration was added.** The repository has no approved extension
  mechanism for speculative source fields, so the proposed contract below is
  documentation, not schema.

**Smallest future source contract** that would make both of Marianne's questions
answerable:

| Field | Meaning |
|---|---|
| `id_predio_reforestacion` | Stable identifier for one reforestation property |
| `id_propietario_reforestacion` | Stable identifier for one owner |
| `nombre_propietario_reforestacion` | Display name for that owner |
| association table | Allows more than one owner per property |

---

## 6. OPEN QUESTIONS for Campo Digital / Javier

1. What columns and rules produce `Pendientes`, `No ingreso`, `Desistida`,
   `Recurso` and `Rechazos` in the WhatsApp summary?
2. Is the total 65 all companies, only Campo Digital, only non-approved plans,
   or another filter?
3. What uniquely identifies a reforestation property: `Predio Ref`, `Rol Ref`,
   their combination, or an identifier the workbook does not yet carry?
4. Can a reforestation property have more than one owner?
5. What source field identifies an owner?
6. Which summarized status should the conflicting PMF have — `MP015` in the
   29 July snapshot, `MP022` in the 14 August one? The dashboard currently
   keeps the value on the plan's first source row.

Until 1 and 2 are answered, the five-category classification is **not
implemented**. Reproducing a total of 65 would require inventing a rule.

---

## 7. RESULT — what changed

### Backend (pure aggregation)

| Addition | Grain | Invariant |
|---|---|---|
| `estado_resumido_pmf` | PMF | Five buckets sum to `pmf_count` |
| `estado_detalle_pmf` | PMF | Counts sum to `pmf_count`; blank keeps its own bucket |
| `estado_resumido_valores` | row | Raw spellings per bucket, for exact click-through |
| `por_empresa` | PMF | Company subtotals reconcile to the overall total |
| `reforestacion` | row | Definition attached; owner slot is a literal |
| `calidad_pmf_estado_resumido_conflictivo` | PMF | Conflicting evidence, not hidden |
| `normalized_label`, `distinct_estado_resumido`, `estado_resumido_conflicts` | — | Spelling fold and conflict detection |

`predios_reforestacion` keeps its field name and now excludes the sentinel.
Nothing else in the response changed.

### Frontend

- New first section on `Resumen`: `Estado de los planes de manejo` — PMF total,
  one composition bar, and aligned clickable status cards. No doughnut.
- Detailed `Estado` breakdown as a table drill-down beneath it.
- Company comparison as one compact matrix with a reconciling TOTAL row,
  replacing the Power BI summary's two repeated per-company blocks.
- A distinct `Reforestación` section on `Resumen`, and the full evidence in
  `Calidad`.
- A conflicting-status section in `Calidad`.
- Semantic colour used consistently: approved green, in process amber,
  attention red only on detailed states containing "rechaz", struck-out neutral
  grey. Colour is never the only signal — every card and row prints its count,
  its label and its share.
- **Fix:** `Link` silently dropped `data-*` attributes. TypeScript accepts a
  hyphenated attribute on a component and React then discards it, so
  `<Link data-tone="late">` compiled, rendered, and styled nothing — every
  `.attention-card[data-tone=…]` rule in the stylesheet had no element to
  match. The attention row has therefore been uncoloured since the
  rearchitecture shipped. `Link` now forwards them.

### Navigation, RBAC and protections

Unchanged. Five sections, same routes, same admin gating, same login, import,
validation, publication, history and CSV export, same production-bundle
exclusions.

---

## 8. Verification

| Check | Result |
|---|---|
| `pytest` (full backend) | 648 passed, 7 skipped |
| `pytest apps/api/integration_tests` (real PostgreSQL) | 280 passed |
| `mypy .` | no issues, 216 source files |
| `ruff check` / `ruff format --check` | clean |
| `npm run lint` | no errors |
| `npm run build` | succeeds |
| `npx vitest run` | 197 passed |
| `npx playwright test` | 98 passed |

## Related documentation

[UX rearchitecture V1](2026-09-13-frontend-ux-rearchitecture-v1.md) ·
[Source contract V1](../source-contract-v1.md) ·
[Functional parity matrix](../audit/2026-09-02-functional-parity-matrix-v1.md) ·
[Nota en español](../es/2026-09-15-estado-planes-de-manejo.md)
