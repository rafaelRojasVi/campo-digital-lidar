# Transelec dashboard — frontend UX rearchitecture V1

Status: specification, written before implementation.

Scope: the `products/transelect/dashboard` frontend only. No backend code, no API
route or response contract, no database schema or migration, no authentication or
RBAC boundary, no status calculation, no aggregation formula, no field meaning, no
workbook parsing, no publication semantics, no CSV content is changed by this work.

---

## 1. Audit of the shipped interface

Method: the running local dashboard (`make transelec-dev`) inspected in Chromium at
1440×900 and 390×844 against the live local platform API, with the published active
version loaded. Screenshots were captured outside the repository because the local
database holds real client content.

### FACT — measured

| Observation | Measurement |
|---|---|
| `/transelec` document height at 1440×900 | 4 210 px |
| `/transelec` document height at 390×844 | 7 977 px |
| Sibling sections stacked in the single `main` column | 11 plus the footer |
| Sections rendered with the identical `.panel .section` shell | 7 |
| Header height before any content, at 1440×900 | 200 px |
| Header height before any content, at 390×844 | ~290 px, 34 % of the viewport |
| Scroll distance to the main row table (`Detalle filtrado`) at 1440×900 | ~2 800 px |
| Filter rail height vs. page height at 1440×900 | ~640 px rail against a 4 210 px page |

### Findings

**A1 — Undifferentiated card mass.** Seven sections use the same white surface, the
same radius, the same shadow and the same heading size. Reforestation chips, the
owner-status table, the FAQ grid, the report, the row table and the quality panel
are visually interchangeable, so nothing signals which of them the reader should
look at. This is the strongest single cause of the "AI-generated dashboard" reading.

**A2 — Flat KPI hierarchy.** Eight KPI cards render at identical weight. `Roles`
(reference trivia) and `Pendientes prioritarios` (the number that triggers work)
are the same size, colour and prominence. Misleading prominence in both directions.

**A3 — Information duplicated in adjacent blocks.** The pending zone prints the
three stage counts as tiles and then immediately reprints the same three counts as
labelled progress bars, one directly under the other. The status hero and the two
donuts both describe `Estado resumido` composition, at predio grain, from the same
basis, in two different forms, in two separate cards.

**A4 — Donuts are the wrong form.** Two three-slice conic-gradient donuts compare
values that are close (68,75 % vs 67,92 % in the current version). Reading either
slice angle is harder than reading the number that is already printed beside it. The
dataviz reference names both the two-slice pie and "a donut for comparing close
values" as anti-patterns.

**A5 — Exploration is buried.** The row table is the operational working surface and
the API's real cursor pagination backs it, yet it is the ninth block on the page,
roughly 2 800 px down, below an executive report the reader did not ask for. The
detail table reads as an appendix to a report rather than as a tool.

**A6 — Actions detached from their object.** `Exportar CSV` and `Imprimir / PDF` sit
in the filter rail, roughly 2 500 px above the dataset they export. `Limpiar` sits in
the same rail while its duplicate entry point `Volver al total` sits inside the
pending zone.

**A7 — Dead column.** The filter rail is a fixed left column about 640 px tall
against a 4 210 px page, so about 85 % of the left column is empty grey. At the same
time the rail is always fully expanded, presenting five multiselects whether or not
the reader is filtering.

**A8 — Oversized identity.** The header spends 200 px of the first desktop screen on
a brand block, a client block, a subtitle line, a four-line stamp and a nav row. On
a phone it takes 34 % of the viewport, and the reader must pass a further ~400 px of
notice banner and fully expanded filter rail before the first number.

**A9 — Import steps are not a workflow.** The three steps render as three static
bordered boxes with no progression, no connector, no current-step affordance that
survives a glance, and a default browser file input.

**A10 — Version history is a generic table.** Ten columns, an `Acción` column whose
cell for the active row is a disabled button reading `Versión activa`, and the active
version's own summary repeated in a second card below. It reads as a report, not as
a history with a present state.

**A11 — Permanent notice.** The `Consulta documental` banner is amber, full width and
permanently above every other thing on the page, which spends the page's strongest
alert treatment on a static explanatory sentence.

**A12 — Motion absent.** No entrance, no drawer, no transition. State changes are
instantaneous swaps, so a filter change gives no sense of what moved.

**A13 — Typography is undifferentiated.** One family at four sizes, no numeric
tabular alignment in numeric table columns, no measure constraint on long
explanatory paragraphs (some exceed 140 characters per line at 1440 px).

### LIMITATION

The audit covers the shipped interface only. It makes no judgement about the
underlying status rules, which are the API's and are deliberately preserved,
divergences included.

---

## 2. Users, roles and jobs

| Role | Grant | Jobs |
|---|---|---|
| Viewer | `viewer` on `transelect` | Understand current state; find one PMF, predio, rol or ingreso; see what is pending; export or print evidence. |
| Operator | `operator` | All of the above, plus replace the published version. |
| Administrator | `admin` | Same surface as operator in this product. |

Primary jobs, ordered by frequency:

1. *Where does the programme stand right now, and how fresh is that answer?*
2. *What needs attention, and which case is next?*
3. *Find this specific PMF / rol / N.º de ingreso and read its detail.*
4. *Produce evidence: an export, a printout, the executive text.*
5. *Publish a corrected planilla, and be able to roll it back.* (operator/admin)

Job 3 has no dedicated surface today. Job 5 has two thin surfaces. Job 1 is spread
across four visually equal blocks.

---

## 3. Information architecture

Five sections replace the current three routes.

| Route | Section | Access | Job |
|---|---|---|---|
| `/transelec` | Resumen operativo | all | 1 |
| `/transelec/explorador` | Explorador | all | 3, 4 |
| `/transelec/pendientes` | Pendientes | all | 2 |
| `/transelec/calidad` | Calidad y reportes | all | 4 |
| `/transelec/datos` | Administración de datos | operator, admin | 5 |

`/transelec/importar` and `/transelec/versiones` remain live routes and resolve into
the `datos` section, so existing links and the e2e suite's navigations keep working.

### DECISION — filter state lives in the URL

The shared filter contract moves into the query string and is read back on load, so
a filtered view is linkable, survives reload, and is shared across the four
data-reading sections from one source of truth. The serialization is `api.ts`'s
existing `filterParams`, unchanged, so the URL and the API request carry identical
parameters. This makes TR-FUNC-017's cross-section consistency observable rather
than merely implemented.

### Persistent shell

A single 56 px bar: wordmark, section nav, then a right cluster carrying the active
version stamp, the identity and role, and the session control. The client name moves
into a one-line context strip under the bar on the Resumen only. Below 900 px the
nav collapses to a disclosure button; the version stamp collapses to its number.

A skip link precedes the bar.

---

## 4. Page hierarchy

### 4.1 Resumen operativo (`/transelec`)

1. Context strip: client, active version number, publish timestamp, actor. One line.
2. **Lead figure** — approval at PMF grain: the percentage as a hero figure with the
   count beneath it, and the basis identifier beside it.
3. **Composition** — one horizontal stacked bar per grain (predio, PMF), replacing
   both donuts and the status hero. Segments carry a 2 px surface gap, 4 px rounded
   data-end, direct labels on segments wide enough to hold one, and a shared legend.
4. **Attention row** — three figures that mean work: pendientes prioritarios,
   PMF sin N.º de ingreso, predios sin ID predial único. Each links to the view that
   resolves it.
5. **Scale row** — the reference counts (PMF, predios, roles, superficie, con
   servidumbre) at reduced weight, as a rule-separated strip rather than cards.
6. **Cola de trabajo** — the first pending cases, each as a row with its stage, its
   reason and its PMF, and a link into Pendientes.
7. Path into the Explorador.

All eight existing KPI values survive; four move to the attention row, five to the
scale strip, and the approval pair is absorbed into the lead figure and composition.

### 4.2 Explorador (`/transelec/explorador`)

Search first and full width. Filters behind a disclosure that opens into a panel;
active filters always visible as removable chips regardless of whether the panel is
open. Result count, then the dense table with a sticky header. Export and print sit
in the table's own toolbar. A row opens a detail drawer carrying that row's PMF, its
predio, its rol, its source row and the other rows of the same PMF, fetched from
`GET /transelec/pmfs/{pmf}`.

The 13-column set, the column labels, the cursor pagination, the page-size control
and the range readout are preserved exactly.

### 4.3 Pendientes (`/transelec/pendientes`)

The pending-priority surface. The stage counts appear once, as a stacked composition
bar with direct labels, not twice. Below it the pending rows as a work queue. The
90-day consultation becomes a toggle on this page rather than a card on the Resumen,
with its scope and its server-clock reference stated as they are today.

### 4.4 Calidad y reportes (`/transelec/calidad`)

Three quality indicators, the reforestation predios, the owner-status table and the
executive report. Quality indicators render calm when the counts are zero and
escalate to a warning treatment only when they are not, so a healthy source does not
compete with daily work.

### 4.5 Administración de datos (`/transelec/datos`)

Two panes: `Importar` and `Versiones`. Import becomes a real stepper — a numbered
rail whose current step is unambiguous, a proper drop zone, and per-step evidence
revealed in place. Versions become a timeline: the active entry anchored at the top
with its full provenance inline, prior activations below as timeline entries with
their actor, event type and restore action.

Viewers never see this nav item, and the route keeps its server-enforced 403.

---

## 5. Component system

Primitives, each one file under `src/ui/`:

`Surface`, `SectionHeader`, `Figure`, `StatStrip`, `CompositionBar`, `Chip`,
`Toolbar`, `DataTable`, `Drawer`, `Stepper`, `Timeline`, `Disclosure`, `Skeleton`,
`StateBlock`, `AlertBanner`, `StatusPill`, `BasisTag`, `Button`.

Surfaces come in three levels only — `page`, `raised`, `sunken` — so a section can
be grouped without every block becoming a card. Grouping by rule and by space is
preferred to grouping by card.

---

## 6. Visual language

### Palette

Deep forest and graphite on a warm neutral ground, with a single operational accent.

| Token | Value | Job |
|---|---|---|
| `--ink` | `#16211d` | Primary text |
| `--ink-2` | `#42524c` | Secondary text |
| `--ink-3` | `#6b7a74` | Muted text |
| `--ground` | `#f4f5f2` | Page |
| `--surface` | `#fbfbfa` | Raised surface, chart surface |
| `--sunken` | `#eef0ec` | Sunken surface |
| `--line` | `#dde1db` | Hairline |
| `--line-strong` | `#c3cabf` | Emphasised rule |
| `--forest` | `#1e8055` | Accent, primary action, `Aprobado` |
| `--forest-deep` | `#15503a` | Shell, headings on dark |
| `--amber` | `#cf9000` | `En trámite` |
| `--clay` | `#b8492a` | `Pendiente`, overdue |
| `--brick` | `#96272b` | `Rechazado` (table text accent only) |
| `--graphite` | `#7d8a84` | `Tachado`, de-emphasis |
| `--graphite-soft` | `#b9c1bb` | `Sin estado`, chart rest |
| `--focus` | `#0b6ea8` | Focus ring |

### RESULT — palette validation

The three colours that appear as adjacent marks in one chart were validated with the
dataviz skill's own validator rather than judged by eye:

```
node scripts/validate_palette.js "#1e8055,#cf9000,#b8492a" \
  --mode light --surface "#fbfbfa" --pairs all

[PASS] Lightness band       all 3 inside L 0.43–0.77
[PASS] Chroma floor         all 3 >= 0.1
[WARN] CVD separation       worst #b8492a↔#1e8055 ΔE 7.3 (deutan) · tritan 16.3
[PASS] Normal-vision floor  worst #b8492a↔#cf9000 ΔE 18.2 (normal)
[WARN] Contrast vs surface  below 3:1: [["#cf9000",2.65]]
→ ALL CHECKS PASS
```

Both warnings are discharged by mandatory secondary encoding, which the composition
bar ships: a 2 px surface gap between segments, direct labels on segments, a legend
present for every multi-segment bar, and the same values available as text in the
tables. Colour is never the only channel carrying a status.

`--brick` is not part of any chart's mark set. It appears only as a text accent in
the owner-status table's `Rechazados` column, beside that column's own header, and
is therefore checked as text contrast (7.0:1 on `--surface`) rather than as a
categorical slot. Establishing this scoping was what let the palette pass at all;
`--forest` against `--brick` is the classic green/red pair and cannot clear the CVD
target inside the lightness band.

### DECISION — one light theme

No dark theme. This is an internal operational tool with a hard print requirement
and a single controlled viewing context; a second theme would double the
verification surface for no stated need. `color-scheme: light` is declared on the
root so native controls render correctly rather than being left to guess.

### Type

System sans (`ui-sans-serif` stack) with a deliberate scale: 30/22/17/14/13/11 px.
`font-variant-numeric: tabular-nums` on every numeric table column, every figure and
every stat. Explanatory prose is capped at 78ch. Headings use `text-wrap: balance`.

### Shape and depth

One radius scale: 3 px on controls, 6 px on surfaces, 999 px on chips and pills
only. Depth comes from hairlines and a single low-tint shadow; no second shadow
level, no glass, no gradient except the shell bar.

---

## 7. Motion

| Event | Treatment | Duration |
|---|---|---|
| Section entrance | opacity + 4 px rise | 220 ms |
| Drawer open / close | transform slide + backdrop fade | 240 / 180 ms |
| Filter panel disclosure | grid-template-rows + opacity | 200 ms |
| Skeleton to content | cross-fade | 180 ms |
| Login to shell | opacity | 240 ms |
| Publish / restore success | banner rise | 240 ms |
| Composition bar segments | width transition | 300 ms |
| Hover / focus | colour and border only | 120 ms |

Rules: only `transform` and `opacity` animate, except the composition bar's width,
which is the one case where the geometry *is* the information. No `transition: all`.
No staggering. Values never animate as counters — an exact figure is never obscured.
Every rule above is disabled under `prefers-reduced-motion: reduce`.

---

## 8. Responsive

| Width | Behaviour |
|---|---|
| ≥ 1280 | Full layout. Explorador table full width. Drawer 480 px. |
| 1024–1279 | Composition bars stack. Scale strip wraps to two rows. |
| 768–1023 | Nav collapses to disclosure. Drawer becomes a bottom sheet at 90 vh. |
| < 768 | Single column. Tables keep their own horizontal scroll container; the page never scrolls horizontally. Filters open as a full-height sheet. |

---

## 9. Old capability to new location

| Capability | Was | Now |
|---|---|---|
| Demo sign-in (local only) | `/transelec` login card | Redesigned login screen, same guard |
| Entra sign-in | login card | Same screen |
| Change user / sign out | header stamp | Shell identity cluster |
| Active version + publish stamp | header stamp | Shell version chip, Resumen context strip, Datos timeline |
| `Consulta documental` notice | permanent banner | Explorador search helper, at the control it describes |
| PMF / Predios / Roles / Superficie / Con servidumbre KPIs | KPI grid | Resumen scale strip |
| Aprobados / En trámite KPIs | KPI grid | Resumen lead figure and composition bar |
| Pendientes prioritarios KPI | KPI grid | Resumen attention row, links to Pendientes |
| Status hero (predio grain) | own card | Resumen composition bar, predio grain |
| Both approval donuts | own card | Resumen composition bars, both grains |
| Reforestation chips | own card | Calidad |
| Owner-status table | own card | Calidad |
| Quick actions (8) | FAQ card grid | Resumen attention row and work queue; Explorador filter presets; Pendientes toggle for 90 días |
| Pending zone | own card, below FAQ | Pendientes |
| 90-day consultation | panel on dashboard | Pendientes toggle |
| Executive report | own card | Calidad |
| Quality indicators | own card | Calidad |
| Filters | permanent left rail | Explorador disclosure + chips; state in the URL |
| Search | rail field | Explorador primary control |
| Detail table | ninth block | Explorador primary surface |
| Pagination | under table | Explorador table footer |
| CSV export | filter rail | Explorador table toolbar |
| Print / PDF | filter rail | Explorador table toolbar, Calidad report |
| Import | `/transelec/importar` | `/transelec/datos` import pane, stepper |
| Version history | `/transelec/versiones` | `/transelec/datos` versions pane, timeline |
| Restore | history table button | Timeline entry action |
| Provenance footer | dashboard footer | Datos active-version panel and Resumen context strip |

Nothing is dropped.

---

## 10. States

Unauthenticated, unauthorized, no published version, loading, platform
unavailable, invalid workbook, validated, published, duplicate import, empty
filter result, restore confirmation, mobile navigation, viewer mode and
administrator mode are each designed rather than defaulted. Loading uses skeletons
shaped like the content that replaces them.

---

## 11. Out of scope

Backend, API contracts, schema, migrations, auth, RBAC, status rules, aggregation,
field meanings, parsing, publication semantics, CSV content. Real Transelec logos
are not used; identity stays typographic pending TR-OPEN-06.

---

## 12. RESULT — what was built, and what it measures

Implemented on `feat/transelec-ux-rearchitecture-v1` from
`a4aaa5b63b8fe60fce117978914ee392cc07dad7`.

### Measured outcome

Same machine, same browser, same published version, same real data.

| Measurement | Before | After |
|---|---|---|
| `/transelec` document height at 1440×900 | 4 210 px | 1 439 px |
| `/transelec` document height at 390×844 | 7 977 px | 2 828 px |
| Sibling sections on the landing route | 11 + footer | 5 |
| Blocks using the identical card shell | 7 | 0 |
| Shell height before any content (desktop) | 200 px | 56 px |
| Shell height before any content (phone) | ~290 px (34 % of viewport) | ~90 px |
| Scroll distance to the row table | ~2 800 px | 0 (own section, above the fold) |
| Horizontal page overflow at 390 px | none | none |
| Filter state survives reload / is linkable | no | yes |
| Single row's full contract fields visible | nowhere | detail drawer |

### Defects the work found and fixed

Four were found by writing the navigation tests, not by reading the code:

1. Section links dropped the filter state, silently resetting the reader's
   scope on every section change.
2. A closed filter disclosure was only zero-height: its controls stayed
   focusable, clickable and announced to assistive technology.
3. Search and select inputs replaced the focus outline with a 3 px low-contrast
   tint ring — a regression for keyboard navigation. The outline is restored
   and the ring is now additive.
4. Pagination controls forced a horizontal page scroll at 390 px.

One pre-existing broken assertion was corrected rather than carried forward:
`tests/e2e/access-states.spec.ts` expected the generic `Sesión requerida`
block on a 401, which stopped being reachable when `a4aaa5b` moved sign-in
into the dashboard itself. `src/App.test.tsx` had asserted the sign-in screen
all along; the two now agree.

### Verification

| Check | Result |
|---|---|
| `make check` | 629 passed, 7 skipped (pdal CLI absent, pre-existing), doc links OK |
| `npm run lint` | clean (warnings only, same classes as before) |
| `npm run build` | clean, 271 kB JS / 39 kB CSS |
| `npx vitest run` | 163 passed, 21 files, production-bundle guard included |
| `npm run test:e2e` | 90 passed |
| Browser QA | 1440×900, 1280×800, 768×1024, 390×844; no horizontal overflow on any section at any size; no console errors |

`make migration-check` and `make persistence-check` are BLOCKED, not run.
`compose.yaml` binds `postgres-test` to `127.0.0.1:5433:5432`, and
`heavy-ops-pilot-v1-db-test-1` (`postgis/postgis:16-3.4`) already holds
`0.0.0.0:5433` and `[::]:5433`. This repository's own
`campo-digital-postgres-test-1` is in state `Created`, never started, for that
reason. The other project's container was not touched. Neither target is part
of `make check`.

### LIMITATION

Browser QA was performed in Chromium only, which is the single project the
Playwright config defines. Nothing here was verified in Firefox or WebKit.

### OPEN QUESTION

Whether the Resumen's section order matches how Javier actually works — in
particular whether the attention row leads with what he needs first, and
whether the work queue's ordering is useful — is a question for him, not
something this rebuild can settle from the workbook.

## Related documentation

[Rediseño de la interfaz (español)](../es/2026-09-13-rediseno-interfaz-transelec.md) ·
[Hallazgos y preguntas para Javier](../es/2026-09-02-hallazgos-y-preguntas-javier.md) ·
[Transelec product README](../../README.md)
