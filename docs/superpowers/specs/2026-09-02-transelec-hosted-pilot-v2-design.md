# Transelec Hosted Pilot V2 — target design

## Status

Proposed. Discovery/specification checkpoint — no implementation performed
under this document. Builds on `origin/main` @
`738f34ff9cd4d868b6ac96bb57afc7d20cf4d211`. Supersedes PR #47 and the
UI-parity branch as prior art only (see
[gap analysis](../../../products/transelect/docs/audit/2026-09-02-implementation-gap-analysis-v1.md)) — neither branch is merged or cherry-picked by this design.

## Purpose

Give Javier every intentional, useful function from his two HTML dashboards
(see the [functional parity matrix](../../../products/transelect/docs/audit/2026-09-02-functional-parity-matrix-v1.md), 46 TR-FUNC rows), rebuilt as a private,
authenticated, database-backed application on the platform's existing shared
provenance/ingestion/RBAC/audit/session/object-store foundation — replacing
the manual "open a static HTML file" workflow with an authorized upload that
validates, fingerprints, stores, imports, and atomically publishes a new
version, with dashboard reads served from the active database projection,
never from a re-parsed workbook.

## Non-goals (explicit)

- No Kubernetes, microservices, Redis, Kafka, or Celery.
- No second object-store abstraction, no second auth model, no separate database.
- No merge or cherry-pick of PR #47 or the UI-parity branch as units.
- No canonical PMF/predio/area-of-cut key beyond what `source-contract-v1.md` already establishes.
- No automatic merge of historical `Resumen` sheets, `Pendientes`, `Reingresos`, or `Urgentes 07May` into current state.
- No OneDrive/Graph automation — manual authenticated upload is the V1 pilot path.
- No deployment of real Transelec data to the current public Render staging environment, under any circumstance.
- No invented business formula for any TR-OPEN-* item in the parity matrix; V1 replicates Javier's current dashboard behavior (bugs included, except the one mechanical fix at TR-FUNC-031) rather than guessing a fix.

## 1. Ingestion / publication lifecycle

**Correction note**: an earlier draft of this section described row
projection, invariant verification, and activation as one combined database
transaction. That contradicted this same section's own idempotency and
restore rules (both already required activation to be a separate, explicit
action) and is corrected below into four distinct lifecycle steps, each its
own transaction boundary: **upload**, **validate/project**, **publish**,
**restore**. Validating and projecting a workbook never activates it.

### Step A — upload (existing shared intake, unchanged for Transelec)

```
authorized upload (ADMIN/OPERATOR, real session, CSRF-checked — a new,
   platform-wide CSRF mechanism; no CSRF protection exists in the codebase
   today, see §5 "CSRF and cookies")
      |
      v
bounded streaming intake (existing: 2 GiB cap, 1 MiB chunks)
      |
      v
file-type + archive safety checks (existing per-product inspection boundary)
      |
      v
SHA-256 content-addressed private object storage (existing ObjectStore.put())
      |
      v
source_snapshot / ingestion_run (existing shared provenance)
```

Step A makes no change to `transelec_dashboard_state`. It is the existing
generic multi-product pipeline, unmodified for Transelec.

### Step B — validate / project (one transaction; ends in COMMIT, not activation)

```
STRICT Transelec Source Contract V1 validation — a HARD GATE for this step
   (xlsx_contract.py, reused as-is; a violation here raises, aborts the
    transaction, no partial import, no silent projection)
      |
      v
immutable transelec_import row created (new) — records
   validated_by_app_user_id / validated_at here, NOT publish metadata
   (publish/restore actor+timestamp live on transelec_publish_event — see §2)
      |
      v
transactional row projection: all validated business rows for this upload
   -> transelec_resumen_row (new)
      |
      v
aggregate/invariant verification — purely structural and internal:
   business_rows/distinct_pmf/surface_total match the *projected rows
   themselves*, row count matches the contract's own PMF-row-selection rule,
   no orphaned FKs. This step never compares against the 729/159/272/164.63
   counts observed in the reviewed 14-Aug snapshot — those are evidence for
   one snapshot (source-contract-v1.md: "not permanent business
   invariants"), not acceptance-gate constants; a differently-sized future
   workbook that satisfies the structural contract must still pass.
      |
      v
COMMIT — no activation happens in this transaction
```

If any part of Step B fails, the entire transaction rolls back: no
`transelec_import` row exists, no `transelec_resumen_row` rows exist, and
`transelec_dashboard_state` is untouched — there is nothing yet to activate.
The only durable evidence of a failed Step B is the existing
`ingestion_run`/`processing_attempt` failure record (already existing
infrastructure).

### Step C — publish (separate, short transaction; explicit, never automatic)

```
authorization (PUBLISH action, OPERATOR/ADMIN)
      |
      v
lock dashboard state (transelec_dashboard_state singleton row)
      |
      v
confirm target transelec_import is a valid, already-committed Step B result
      |
      v
atomically flip transelec_dashboard_state.active_import_id
      |
      v
insert transelec_publish_event (event_type='publish', actor_user_id,
   occurred_at)
      |
      v
insert a corresponding platform audit_event (belt and braces — §2)
      |
      v
COMMIT
```

Publication is never a side effect of validation succeeding — Step B
committing a valid import does not, by itself, change what the dashboard
serves. Dashboard reads query `transelec_resumen_row` (or a materialized
read view) for the *active* import only — never the workbook bytes.

### Step D — restore (same activation primitive as Step C, different target and event type)

Restore is not a new import: it is the same publish/activate mutation as
Step C (`POST /api/transelec/imports/{id}/restore`, see §3), targeting an
*already validated, already immutable* prior `transelec_import`, gated by
the same `PUBLISH` action, recording `event_type='restore'` on
`transelec_publish_event` so the audit trail distinguishes "published a new
version" from "reverted to an old one." No re-validation happens on restore
— it cannot, because an invalid import is never committed by Step B in the
first place, so there is never a bad version for restore to skip validating.

**Idempotency**: the existing `source_snapshot` layer is already
content-addressed by SHA-256 — re-uploading byte-identical content resolves
to the same snapshot. Step B must check whether a `transelec_import` already
exists for that `source_snapshot_id` before projecting again; if one exists
and is already active, the upload is a no-op (reported to the user as
"already current," not silently re-imported or re-activated); if one exists
but is not active, uploading does not auto-activate it — activation (Step C)
stays an explicit, separate, audited action, invoked deliberately by an
operator, never triggered automatically by Step B succeeding.

## 2. Data model

Builds on and evolves — does not duplicate — the existing `platform.transelec_workbook_snapshot` / `platform.transelec_dashboard_state` pair from migration `0004`.

```sql
-- Evolves 0004's transelec_workbook_snapshot: rename intent preserved via a
-- new migration that ADDS a transelec_import table keyed to the existing
-- snapshot table, rather than dropping/renaming it. transelec_dashboard_state
-- gets a new, additional active_import_id column in this same migration
-- (expand/migrate/contract — see the ALTER TABLE below); its existing
-- active_source_snapshot_id column and FK are NOT dropped or repointed here.

CREATE TABLE platform.transelec_import (
    id                          BIGSERIAL PRIMARY KEY,
    source_snapshot_id          BIGINT NOT NULL REFERENCES platform.source_snapshot(id) ON DELETE RESTRICT,
    ingestion_run_id            BIGINT NOT NULL REFERENCES platform.ingestion_run(id) ON DELETE RESTRICT,
    schema_contract_version     TEXT NOT NULL,      -- e.g. "transelec-resumen-v1"
    parser_version              TEXT NOT NULL,      -- xlsx_contract.py's own version tag
    business_rows                INTEGER NOT NULL CHECK (business_rows > 0),
    distinct_pmf                 INTEGER NOT NULL CHECK (distinct_pmf > 0),
    distinct_provisional_predio_ids INTEGER NOT NULL CHECK (distinct_provisional_predio_ids >= 0),
    surface_total                DOUBLE PRECISION NOT NULL,
    validated_by_app_user_id     BIGINT NOT NULL REFERENCES platform.app_user(id) ON DELETE RESTRICT,
    validated_at                 TIMESTAMPTZ NOT NULL,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_snapshot_id)  -- one import per immutable content snapshot: idempotency at the DB layer
    -- NOTE: no published_by_user_id/published_at column here. An import can
    -- exist (Step B, validated) before it is ever published (Step C), and a
    -- historical import may later be activated again by a restore (Step D)
    -- -- i.e. it may accumulate more than one activation event over its
    -- lifetime. Publish/restore actor + timestamp therefore live on
    -- transelec_publish_event (below), one row per activation event, not on
    -- this immutable import row, which would otherwise wrongly imply exactly
    -- one publication ever happens per import.
);

CREATE TABLE platform.transelec_resumen_row (
    id                    BIGSERIAL PRIMARY KEY,
    import_id             BIGINT NOT NULL REFERENCES platform.transelec_import(id) ON DELETE CASCADE,
    source_row_number     INTEGER NOT NULL,          -- 1-indexed, equals the real Excel row (xlsx_contract.py already produces this)
    predio_ref            TEXT, rol_ref TEXT, area_ref TEXT,
    pmf                   TEXT NOT NULL,
    carpeta_source         TEXT,                      -- column E (positional)
    carpeta_normalizada     TEXT,                      -- column AC (positional) — BOTH preserved, resolving TR-OPEN-02 by not choosing
    pas TEXT, estado TEXT, estado_resumido TEXT, tipo_rechazo TEXT,
    reingreso_tec TEXT, reingreso_legal TEXT, reingreso_recrep TEXT,
    tipo_propietario TEXT, id_transelec TEXT,
    rol TEXT, numero_predio TEXT, numero_area_corta TEXT,
    superficie_corta DOUBLE PRECISION, superficie_total_corta DOUBLE PRECISION,
    fecha_ingreso DATE, numero_ingreso TEXT,
    fecha_90_dias DATE,       -- stored verbatim as a date; meaning stays TR-OPEN-03, not interpreted
    hoy_raw TEXT,             -- stored as the raw source representation (date OR free text) per the workbook audit's type-inconsistency finding; NEVER used as ingestion time
    empresa TEXT,
    id_predio_unico_ii TEXT, id_pmf TEXT,   -- columns Y, Z (positional) — see rationale below: imported as-is, mostly null by source design
    id_predio_unico TEXT,   -- NULLABLE: the raw provisional predio identity (AA's formula value), stored as-is (not recomputed — see rationale below). Nullable because TR-FUNC-002/014 both evidence that a blank ID_Predo_Unico is a real, expected case the app must handle (0/729 in the reviewed snapshot, but the quality-indicator row TR-FUNC-014 exists precisely to count this for a future workbook where it isn't 0) — a NOT NULL constraint here would contradict that fallback behavior.
    predio_group_key TEXT NOT NULL,   -- DERIVED, provisional display/grouping key: id_predio_unico when non-blank, else the composite `PMF || '-' || rol || '-' || numero_predio` (TR-FUNC-002's evidenced fallback). Computed at projection time in application code, never overwrites the raw id_predio_unico column above.
    tramite TEXT, sector TEXT,
    UNIQUE (import_id, source_row_number)   -- one row per import per original source row, exactly per the brief's requirement
);
CREATE INDEX ix_transelec_resumen_row_import_pmf ON platform.transelec_resumen_row (import_id, pmf);
CREATE INDEX ix_transelec_resumen_row_import_predio ON platform.transelec_resumen_row (import_id, predio_group_key);
CREATE INDEX ix_transelec_resumen_row_import_estado_resumido ON platform.transelec_resumen_row (import_id, estado_resumido);
CREATE INDEX ix_transelec_resumen_row_import_sector ON platform.transelec_resumen_row (import_id, sector);
CREATE INDEX ix_transelec_resumen_row_import_empresa ON platform.transelec_resumen_row (import_id, empresa);
CREATE INDEX ix_transelec_resumen_row_import_pas ON platform.transelec_resumen_row (import_id, pas);
CREATE INDEX ix_transelec_resumen_row_import_tipo_propietario ON platform.transelec_resumen_row (import_id, tipo_propietario);

-- transelec_dashboard_state (existing, from 0004) is REUSED, EXPANDED only
-- in this migration (0008) — expand/migrate/contract, not a destructive
-- rename. active_source_snapshot_id is confirmed unused by any router today
-- (grep of apps/api finds no reference outside migration 0004 itself), but
-- "unused in this checked-out worktree" is not proof no already-deployed
-- environment depends on the column, so this migration only ADDS the new
-- pointer column; it does not drop the old one or its FK constraint.
ALTER TABLE platform.transelec_dashboard_state
    ADD COLUMN active_import_id BIGINT REFERENCES platform.transelec_import(id) ON DELETE RESTRICT;
-- active_source_snapshot_id (and its FK to transelec_workbook_snapshot) is
-- left in place, deprecated, for this migration. Application code (Slice 3
-- onward) reads/writes only active_import_id from day one. A future
-- CONTRACT migration drops active_source_snapshot_id (and
-- transelec_workbook_snapshot, which nothing ever projects into either) —
-- only after confirming, in every environment 0004 has actually run, that
-- the column is genuinely unused there too, not merely in this worktree.

CREATE TABLE platform.transelec_publish_event (
    id            BIGSERIAL PRIMARY KEY,
    import_id     BIGINT NOT NULL REFERENCES platform.transelec_import(id) ON DELETE RESTRICT,
    event_type    TEXT NOT NULL CHECK (event_type IN ('publish', 'restore')),
    actor_user_id BIGINT NOT NULL REFERENCES platform.app_user(id) ON DELETE RESTRICT,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    -- this table gives Transelec a queryable "version history" view for the
    -- UI's restore screen without re-deriving it from the generic audit_event
    -- table's freeform payload; app.audit also gets a corresponding
    -- audit_event row per the platform-wide audit contract (belt and braces:
    -- one product-queryable table, one platform-wide audit trail).
);
```

**Typed columns, not JSONB — rationale.** The Resumen contract is a strict,
versioned 30-field V1 shape and every field is independently filterable
(TR-FUNC-017–022) or exported (TR-FUNC-037); a JSONB blob would need
expression indexes on ~9 fields to match the typed-column index list above,
loses `NOT NULL`/type constraints at the database layer, and makes the
positional-`Carpeta`-disambiguation fact (the single most important schema
lesson from the workbook audit) invisible to anyone reading the schema.
JSONB would only pay off if the schema were expected to change per-import
without a new contract version — it explicitly is not (`source-contract-v1.md`:
"a renamed, removed, or reordered column inside A:AD is a schema change and
must fail validation"). `schema_contract_version`/`parser_version` on
`transelec_import` is the correct place to encode *that* kind of change —
a new contract version gets a new parser and, if the shape truly changes, a
new/altered `transelec_resumen_row`-equivalent table in a future migration,
not a schema-less blob absorbing drift silently.

**`id_predio_unico` stored as-is, not recomputed, and stays nullable.** The
workbook audit found `AA` is a live formula (`PMF & "-" & Rol & "-" & N
Predio`). The platform stores the workbook's own computed string rather than
recomputing it, because recomputing would silently diverge from the
workbook the moment Javier's formula changes (e.g. if he ever adds a
disambiguating suffix) — the platform's job is to preserve what the source
asserts, not to reimplement Javier's spreadsheet logic as platform business
logic. This matches the existing "no canonical predio identity beyond
current evidence" rule. The column is **nullable**, not `NOT NULL`: the
reviewed 14-Aug snapshot happens to have zero blanks (272/272 populated),
but TR-FUNC-002's evidenced fallback (`[PMF, Rol, N Predio]` when blank) and
TR-FUNC-014's quality indicator (a count of blank `ID_Predo_Unico` rows)
both only make sense if the schema can actually represent a blank value for
a future workbook. `predio_group_key` (above) is the separate, explicit
derived column that implements the fallback for display/grouping purposes
— it is never written back into `id_predio_unico` itself.

**`Y`/`Z` (merged-cell per-group annotations) ARE imported, positionally,
mostly-null.** Correcting an earlier draft of this document, which said `Y`
(`ID_Predio_UnicoII`) and `Z` (`ID_PMF`) were "intentionally not imported" —
that contradicted this same schema's own `id_predio_unico_ii`/`id_pmf`
columns above, and the "preserve all 30 A:AD fields positionally" rule
`xlsx_contract.py`'s `RESUMEN_COLUMNS` already establishes (`Tramite`, 100%
empty, is preserved for the identical reason). `Y`/`Z` are stored exactly as
a positional per-row read returns them: populated only on the first row of
each vertical merge group, `NULL`/blank on every other row in that group —
the source-faithful shape, not forward-filled. Forward-filling would be an
invented transformation DECISION the brief prohibits; the workbook audit
already flagged this exact choice as open ("preserve the mostly-null shape
as-is or explicitly forward-fill and document that as a transformation
DECISION, not a source fact") — V1 takes the preserve-as-is branch. `AA`
(`id_predio_unico`) remains the authoritative predio identity for all
KPI/filter/dedup logic; `Y`/`Z` are stored for completeness and any future
Javier-confirmed use, not read by any TR-FUNC-* logic in V1.

## 3. API design

All Transelec routes live under `apps/api/app/routers/transelec.py` (new,
replacing nothing — PR #47's identically-named router is prior art only,
not present on `main`), composed the same way every other product router is:
mounted in `app.main`, depending only on `app.deps.get_current_app_user` and
a new `require_transelec_grant(action)` dependency mirroring the existing
per-product RBAC pattern.

### Reads (VIEWER and above)

- `GET /api/transelec/summary?…filters` — TR-FUNC-001–011 (KPIs, charts, status hero), computed from `transelec_resumen_row` for the active import, filter params matching TR-FUNC-017–022's semantics exactly (AND across params, OR within a repeated param).
- `GET /api/transelec/pmfs?…filters&cursor=` — TR-FUNC-039 (paginated row/PMF explorer), same filter params, real cursor pagination (no hidden 1000-row cliff).
- `GET /api/transelec/pmfs/{pmf}` — TR-FUNC-039 detail drawer.
- `GET /api/transelec/pending?…filters` — TR-FUNC-007, 032, 033 (pending-priority section), same filter contract.
- `GET /api/transelec/owner-status` — TR-FUNC-013, predio-grain, ships Javier's existing `ownerStage()` legacy rule (basis identifier `owner_stage_legacy`), named explicitly in the response so the ambiguity is visible rather than hidden. This does **not** resolve TR-OPEN-01 — see the new "Status-rollup basis" note at the end of this section — it only avoids silently disagreeing without saying so.
- `GET /api/transelec/report` — TR-FUNC-034 (executive report text), same template, computed server-side so "today" in any report text is never frozen (fixes the same class of bug as TR-FUNC-031, applied consistently).
- `GET /api/transelec/export.csv?…filters` — TR-FUNC-037, field set per TR-OPEN-04's resolution (defaults to Actualizable's 17-field set pending Javier's confirmation).
- `GET /api/transelec/imports` — version history list (publish/restore audit trail) for the restore UI.
- `GET /api/transelec/imports/active` — current active version's provenance (snapshot hash, filename, and the *publish* timestamp/actor — read from the most recent `transelec_publish_event` row for the active import, not from `transelec_import` itself, since the import row only records who/when it was *validated*, per §2's corrected schema) — replaces TR-FUNC-043's static footer text with real data.

Every read endpoint accepts the same filter query-param contract so KPIs,
charts, and tables can never disagree under a given filter state — this is
the server-side equivalent of both HTML files' single shared `view` variable,
and is itself a parity requirement (TR-FUNC-017's acceptance test).

**Status-rollup basis (TR-OPEN-01) — not blocked, not unified.** Until
Javier picks one canonical PMF/predio status-rollup rule, V1 does not
invent one, and TR-OPEN-01 does not gate the schema, the ingestion/
publication pipeline, RBAC, CSRF, or any non-status-dependent read (filters,
table browsing, export, pagination). Instead, every place a PMF/predio-grain
status appears keeps its own evidenced *legacy* rule, each under an explicit
basis identifier so the disagreement is visible rather than hidden:
`estado_resumido_first_row` (TR-FUNC-005/006/011's `Map`-insertion-order
"first row wins" dedup, matching the HTML's `pmfRows()`/`propertyRows()`),
`pending_priority_legacy` (TR-FUNC-007/032's `isPendingPMF` rule), and
`owner_stage_legacy` (TR-FUNC-013's `ownerStage()` rule). Each is
implemented as its own small, named function/module behind a common
interface (e.g. one lookup keyed by basis identifier), so that when Javier
picks a canonical rule it replaces the relevant basis centrally in one place
— not scattered across every call site — without that decision blocking any
other slice of this plan today.

### Mutations (OPERATOR/ADMIN, session-authenticated, CSRF-protected once the new platform CSRF mechanism in §5 exists)

- `POST /api/transelec/uploads` — reuses the existing generic `/ingesta/upload` boundary unchanged; Transelec-specific behavior begins after inspection.
- `POST /api/transelec/imports/{ingestion_run_id}/validate-and-project` — the new hard-gate step (contract validation → row projection → invariant check), OPERATOR-gated, idempotent per `source_snapshot_id`.
- `POST /api/transelec/imports/{id}/publish` — atomic activation, new `PUBLISH` action.
- `POST /api/transelec/imports/{id}/restore` — same `PUBLISH` action, `event_type='restore'`.

### RBAC

Add two narrow `Action` enum members — `PUBLISH`, and reuse existing `RETRY`
for re-running a failed validate-and-project step rather than adding a third.
`PUBLISH` is granted to `OPERATOR` and `ADMIN`; plain `VIEW` covers every read
route above. This is additive to the existing `_ALLOWED` matrix, not a
redesign — matches the gap analysis's finding that this is a small change.

## 4. UI direction

Rebuilds `products/transelect/dashboard/` on `main` (the ADR-008 demo port's
presentation components — `ExecutiveKpis.tsx`, `FilterPanel.tsx`,
`Pagination.tsx`, `PmfDetailDrawer.tsx`, `PmfExplorer.tsx`,
`StatusDistribution.tsx`, `StatusPills.tsx`, `MultiSelectField.tsx` — are a
starting point for adaptation, not a foundation to build on unmodified,
since they were built against a fixture shaped by `pmf_view.py`'s
*unverified* rollup rules and are missing several TR-FUNC rows entirely —
see the matrix's Main/PR47/UI-branch columns). `api.ts` is rewritten to call
the real endpoints above instead of a fixture module.

Page/section structure, each item traceable to its TR-FUNC row(s):

- **`/transelec`** — main dashboard: header (041) → notice banner (042) → filter panel (017–023) → KPI row (001–008) → status hero (011) → donut charts (009–010) → reforestación chips (012) → owner-status table (013, with its status-rule choice made explicit) → quick-actions (024–030) → pendingzone (007, 032, 033) → report panel (034–036) → main table with real pagination (039) → data-quality panel (014–016) → footer with real provenance (043).
- **`/transelec/importar`** — OPERATOR/ADMIN only: upload, validation result, publish confirmation, replacing TR-FUNC-040's client-side refresh entirely.
- **`/transelec/versiones`** — version history + restore, reading `transelec_publish_event`/`transelec_import`.

Required UI states beyond the happy path: empty (no import ever published),
loading, unauthorized (401/403 per route), invalid-upload (contract
violation, generic message to the viewer, technical detail in audit log
only), unavailable-source, import-failed (validation or invariant check
failed — active version unchanged, shown clearly), duplicate-upload (content
already imported), restore-confirmation (explicit "you are about to make
import #N active again" dialog before the mutation fires).

Filter-consistency test (TR-FUNC-017's acceptance criterion): a single
Playwright test drives one filter change and asserts the KPI row, both
donuts, the status hero, and the main table's row count all update
consistently in one render pass — this is the automated equivalent of the
manual cross-check the forensic audit had to do by hand across two separate
HTML files.

Desktop/mobile: reproduce the two confirmed breakpoints (1000px, 600px) as a
starting point, refined for actual component density once built — TR-FUNC-044.
Print: TR-FUNC-038/045's acceptance test (Playwright print-emulation,
pixel-equivalent chrome-hiding) is mandatory, not optional, since it is a
real function Javier uses today.

Logos: TR-FUNC-041/TR-OPEN-06 — do not extract the base64 payloads from
either HTML without Javier/Campo Digital's explicit authorization to reuse
those specific image assets; ask before the UI slice starts, not after.

## 5. Security design

### Authentication and authorization

Every Transelec route (read and mutation) requires
`app.deps.get_current_app_user` (existing hashed-cookie `platform.session`
mechanism) — no route is ever reachable unauthenticated. `VIEW` covers all
read routes; `UPLOAD`/`PROCESS`/`RETRY` cover the existing generic ingestion
steps; the new `PUBLISH` action gates validate-and-project, publish, and
restore. This is server-side, product-scoped authorization via real
`app_user`/`product_grant` rows — not a shared static token.

### CSRF and cookies

**Correction — FACT, confirmed by direct code inspection this session**: no
CSRF protection exists anywhere in this codebase today. `apps/api/app/deps.py`'s
`get_current_app_user` authenticates every state-changing route — including
the existing generic upload boundary (`POST /ingesta/upload` in
`apps/api/app/routers/ingestion.py`) — via the `campo_session` cookie plus
RBAC (`app.access.can`) alone; there is no CSRF token, header, cookie, or
middleware anywhere in `apps/api` or any frontend (`grep -ri csrf` across
every `.py`/`.ts`/`.tsx` file in the repository returns zero hits). An
earlier draft of this document claimed CSRF protection was "the platform's
existing" mechanism — that was incorrect and is corrected here.

**DECISION**: before any product's cookie-authenticated mutation routes ship
(Transelec's included), the platform needs one reusable, cross-product CSRF
defense — new work, not Transelec-specific — with these properties:

- a cryptographically unpredictable token, minted server-side per
  session/request (`secrets.token_urlsafe`, matching the pattern
  `PlatformSessionStore` already uses for session tokens);
- explicit verification on every state-changing, cookie-authenticated
  request (double-submit-cookie or synchronizer-token pattern — the exact
  mechanism is an implementation choice for whichever slice builds it, not
  decided by this document);
- **fail-closed**: a missing or mismatched token is a `403`, never a silent
  pass-through;
- same-origin (`Origin`/`Referer`) validation as an independent second
  layer — defense in depth, not a substitute for the token check;
- no CSRF secret ever embedded in the compiled frontend bundle — the token
  is issued per session/request via a normal response, not baked into build
  output;
- implemented **once**, as a shared FastAPI dependency/middleware covering
  at minimum the generic upload route and Transelec's validate-and-project,
  publish, restore, and retry mutations — every product's mutation routes
  consume the same mechanism, none gets its own.

This is new platform-level work with no code today (see the corrected
capability table in the
[gap analysis](../../../products/transelect/docs/audit/2026-09-02-implementation-gap-analysis-v1.md))
— a prerequisite for shipping any of Transelec's mutation routes for real
users, not something already wired up that this design can assume. Session
cookies stay `HttpOnly`, `Secure`, `SameSite=Lax` (matching the existing
session store's documented posture in `docs/platform/security-model.md`) —
`SameSite=Lax` reduces but does not eliminate CSRF risk for state-changing
`POST` routes, which is exactly why the explicit token check above is still
required, not optional belt-and-braces. No secret (admin token or
otherwise) is ever placed in the frontend bundle.

### Upload safety

Reuses the existing bounded-streaming/2 GiB/1 MiB-chunk intake and per-product
inspection boundary unmodified. Transelec-specific hardening layered on top:
the contract-validation step becomes a **hard gate** for the
validate-and-project mutation specifically (inspection at upload time stays
evidence-only, matching the existing multi-product design — gating happens
at the Transelec-specific step, not by changing the shared upload boundary's
behavior for every product).

**Correction — FACT**: `xlsx_contract.py` on current `main` imports
`python_calamine.CalamineWorkbook`, **not** `openpyxl` — an earlier draft of
this document said `openpyxl` `data_only=True` mode; that was incorrect.
Calamine parses the XLSX XML directly and does not implement a formula
engine, so it does not evaluate formulas the way a non-data-only `openpyxl`
read would. **OPEN QUESTION**, not yet independently verified against the
real workbook in this pass: exactly what `python_calamine` returns for a
cell holding a live formula — the workbook audit found formulas in columns
`AA` (`=PMF & "-" & Rol & "-" & N Predio`, all 729 rows) and `W`
(`=NOW()`, 129/729 rows) — whether that is the last cached computed value
stored in the workbook XML, `None`/blank, or the literal formula string, is
not established by this document and must be confirmed by a dedicated test
(e.g. asserting the parsed value for a known-formula cell in a small fixture
workbook) before this design is implemented, not assumed either way. No
macro execution and no formula evaluation by the platform in any case; no
external-link fetching; safe temp files with guaranteed cleanup (reuse the
existing pattern); a ZIP-bomb/archive-safety check equivalent to the one
already built for the Forestry ZIP inspector.

V1 supports `.xlsx` only. No evidence in this discovery session supports
adding `.xlsm` (macro-enabled workbook) support — PR #47's draft reportedly
proposed it, but an unmerged draft PR is not, on its own, evidence of a real
Javier workflow requirement, and macro-enabled workbooks raise exactly the
macro-execution risk this section is designed to exclude.

### Error handling

Client-facing errors for contract violations, duplicate uploads, and
failed publishes are generic and stakeholder-safe ("La planilla no cumple el
contrato de origen esperado. Contacte a soporte." style copy) — never a raw
Python traceback, file path, or row content. Full technical detail
(exception, offending column, row count) goes to the existing audit-event/log
infrastructure only.

### Object and database security

No change to the existing posture: private object storage, no permanent
public URLs, least-privilege DB identity, no anonymous DB access, migrations
run separately from the application runtime identity (existing pattern).
Transelec introduces no new object-storage or DB-connectivity code — it is a
consumer of the existing boundaries.

### Headers, CORS, rate limits

No new CORS surface — Transelec's frontend is served same-origin through the
same `/api/*` rewrite pattern the portal, LiDAR, and (per ADR-007/ADR-008)
every hosted module already uses; no wildcard CORS is introduced. Existing
CSP/security-header posture applies unchanged. Upload and export routes
should carry the same abuse/rate-limit posture as the existing generic
upload route — no Transelec-specific exemption.

### Threat model (delta from the platform's existing model)

| Threat | Mitigation |
|---|---|
| Unauthorized viewing of real client operational data | Session auth + `VIEW` grant on every read route; never deployed to public Render staging |
| Privilege escalation to publish/restore | New narrow `PUBLISH` action, not reuse of a broad existing one; audited |
| Malicious workbook upload (macro, zip bomb, formula injection) | Reuses existing streaming/inspection hardening; `python_calamine`'s cell-value behavior for formula-bearing cells confirmed by a dedicated test (see "Upload safety" above — OPEN QUESTION until then); no macro execution in any case; archive-safety check |
| Data exfiltration via export | Export routes still require `VIEW` + session auth; no unauthenticated export path |
| Broken restore (activating a bad version) | Restore only targets an already-validated immutable `transelec_import`; no re-validation skip possible since invalid imports never reach a state restore can target |
| Object/DB inconsistency (row projection succeeds, object write fails, or vice versa) | The object write (Step A) already happened, and was already committed, before Step B's validation begins (existing pipeline order); Step B (projection + invariant check) is its own transaction, entirely separate from Step C (activation) — so a Step B failure never leaves a dangling activation, since activation is never reached. It leaves an unreferenced but harmless object plus a failed `ingestion_run` |
| Partial import silently going live | Step B (validate/project) is one transaction that ends in `COMMIT` with no activation; Step C (publish) is a separate, later, explicitly-invoked transaction. A Step B failure rolls back the whole transaction, leaving no `transelec_import` row to activate at all — there is no state in which a partial import is one step away from going live |

## 6. Hosting decision gate

**Real Transelec data is never deployed to the current public Render staging
environment** — confirmed unsuitable on three independent grounds already
established in this repository's own ADRs, reconfirmed here: no real
authentication exists on Render staging (ADR-006: dev-auth is
development-only, Entra sign-in is externally blocked), object storage there
is ephemeral (ADR-005), and Transelec was explicitly scoped out of even
synthetic hosting there as "Category C, architecturally blocked" (ADR-007)
— this design does not change that classification. ADR-008's synthetic
Transelec demo (fabricated fixture data, no backend) remains the only
Transelec surface on public staging; this design's real-data pilot is a
**separate, private deployment**, not an extension of staging.

**Identity fit — the load-bearing open blocker.** No Campo Digital Entra
tenant exists yet (`docs/platform/entra-app-registration-handoff.md`,
confirmed current as of this session); the real OneDrive source is a
personal Microsoft account, not a SharePoint/M365 tenant. PR #47's
IAP/Google-Workspace-gated design does not fit this reality any better than
an ungated deployment would — it substitutes one unbuilt identity system for
another, without actually being closer to done. **Until a Campo Digital
Entra tenant exists and the app registration in
`entra-app-registration-handoff.md` is completed by a tenant admin (an
externally-gated prerequisite this task cannot perform), there is no
private-real-data-capable identity provider for Javier or any authorized
Campo Digital user.** This is the single blocking fact for private real-data
deployment — everything else in this section is buildable in parallel.

**Compute/DB/storage/secrets/migrations/backups**: no new decision is
proposed here beyond what `docs/platform/production-platform-v1.md`,
`environments-and-costs.md`, ADR-001 (GCP Santiago, Proposed), and ADR-004
(Azure Chile Central, Proposed, not yet accepted) already establish for the
platform as a whole — Transelec does not need its own infrastructure
decision. Whichever provider the team accepts for ADR-001/ADR-004, Transelec
runs as one more schema in the shared `platform` PostgreSQL/PostGIS instance
and one more prefix in the shared object store, per
`production-platform-v1.md`'s "one managed instance, logical ownership stays
explicit" rule — explicitly *not* PR #47's "interim pilot placement in a
shared schema" framing, which was a workaround for not having this decision
yet, not a deliberate design choice worth preserving.

**Chile/latency/residency**: no Transelec-specific evidence beyond what
ADR-001/ADR-004 already establish (GCP `southamerica-west1` vs. Azure
`chilecentral`, both regionally comparable per ADR-004's research). No new
claim is made here.

**Cost drivers**: Transelec adds no new infrastructure category to
`environments-and-costs.md`'s existing lean-production envelope
($57–125/month) — one more schema, one more object-store prefix, no new
compute service, no new database instance. The workbook audit's confirmed
15 MiB file size and 729×30 row scale are trivial against that envelope's
planning assumptions (which already account for a 315 MB LiDAR file and a
150 MB uncompressed Transelec sheet per ADR-004's research).

**Operational burden / rollback**: the atomic-publish design means rollback
is always "restore the previous import," a single audited mutation, never a
database restore-from-backup for an ordinary bad-data mistake — a real
operational advantage over both HTML files' "re-send the whole file by
hand" status quo and over PR #47's admin-token model (no attribution of who
restored what).

### Readiness classification for this design

**NOT READY for private real-data deployment.** Blocking, in priority order:

1. Campo Digital Entra tenant does not exist (externally gated — tenant admin action, not platform engineering).
2. ADR-001 vs. ADR-004 (production cloud provider) remains unresolved — Proposed/Proposed, neither accepted.
3. No managed production PostgreSQL/PostGIS or object storage has been provisioned on either candidate provider.
4. The schema, ingestion pipeline, and UI described in this document do not exist yet — this is a design, not an implementation.

**READY FOR SYNTHETIC STAGING** in the ADR-008 sense only (fabricated fixture
data, no backend) — already true today, unaffected by this design, and
insufficient for Javier's real operational use.

A locally-verified production container image or a synthetic staging
deployment must never be reported as evidence that private real-data access
is complete — per the brief's own instruction, restated here as a standing
constraint on this design's own future acceptance testing.

## Related documentation

- [Functional parity matrix](../../../products/transelect/docs/audit/2026-09-02-functional-parity-matrix-v1.md)
- [Implementation gap analysis](../../../products/transelect/docs/audit/2026-09-02-implementation-gap-analysis-v1.md)
- [Implementation plan](2026-09-02-transelec-hosted-pilot-v2-implementation-plan.md)
- [Source ingestion](../../platform/source-ingestion.md) · [Security model](../../platform/security-model.md) · [Production platform V1](../../platform/production-platform-v1.md)
- [ADR-001](../../adr/ADR-001-managed-production-platform.md) · [ADR-004](../../adr/ADR-004-revisit-production-cloud-provider-choice.md) · [ADR-006](../../adr/ADR-006-restrict-dev-auth-to-development.md) · [ADR-007](../../adr/ADR-007-hosted-product-composition-v1.md) · ADR-008 (`docs/adr/ADR-008-hosted-demo-data-v1.md` — exists on local branch `feat/hosted-demo-data-v1` only, not yet on `origin/main` as of this session; not linked here to avoid a broken reference in this worktree)
