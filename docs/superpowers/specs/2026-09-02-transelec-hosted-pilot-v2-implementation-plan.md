# Transelec Hosted Pilot V2 — implementation plan

## Status

Proposed. Checkpoint for review before implementation begins — per the task
brief, no slice below has been started. Each slice starts from `origin/main`
(current verified head `738f34ff9cd4d868b6ac96bb57afc7d20cf4d211`), not from
PR #47 or the UI-parity branch; both are prior art referenced per-slice
below, never merged or cherry-picked wholesale.

## How to read this plan

Each slice states: scope, exact files/modules touched, which
`TR-FUNC-*`/`TR-OPEN-*` IDs it resolves, the migration(s) it adds (all
continuing the linear chain from `0007`), its test list, and its rollback
point. Slices are reviewable independently; each should be its own PR.

## Slice 1 — Ratify the source-derived functional spec (no code)

**Scope**: circulate the [source forensic audit](../../../products/transelect/docs/audit/2026-09-02-source-forensic-audit-v1.md), [parity matrix](../../../products/transelect/docs/audit/2026-09-02-functional-parity-matrix-v1.md), and [gap analysis](../../../products/transelect/docs/audit/2026-09-02-implementation-gap-analysis-v1.md) to Javier for the TR-OPEN-01…06 decisions. This is the checkpoint the task brief asks this session to stop at.

**Exit condition**: TR-OPEN items are each answered, deferred with an explicit provisional default, or explicitly still blocking — recorded in the "Open decisions" section below, not silently assumed.

**Rollback point**: none — no code changes.

## Slice 2 — Migrations: add `transelec_import`, `transelec_resumen_row`, `transelec_publish_event`; expand `transelec_dashboard_state`

**Scope**: one new Alembic migration, `revision="0008"`, `down_revision="0007"` — confirmed fresh this session: `migrations/versions/0001`…`0007` form a single linear chain (each file's `down_revision` points to exactly the prior revision, no fork), so `0008` is the genuinely next-free id, but re-run `git log --all --oneline -- migrations/versions/` immediately before writing it, since sibling worktrees may have allocated `0008` in the meantime. Implements the schema in the [design doc, §2](2026-09-02-transelec-hosted-pilot-v2-design.md#2-data-model): the two new tables, the publish-event table, and an **expand-only** change to `transelec_dashboard_state` — `ADD COLUMN active_import_id` (nullable FK to the new `transelec_import`). This migration does **not** drop `active_source_snapshot_id` or its FK to `transelec_workbook_snapshot`; that column is confirmed unused by any router on `main` today (grepped this session), but is left in place, deprecated, per expand/migrate/contract — a later CONTRACT migration drops it only after confirming it is unused in every environment where `0004` has actually run, not just in this worktree. Also deletes PR #47's now-irrelevant migration file if that branch is ever formally closed out (not required for this slice to merge — the collision only matters if PR #47 is merged, which it will not be).

**Depends on**: nothing — pure schema.

**Tests**:
- `apps/api/tests/test_migration_graph.py` — extend/re-run to confirm the chain stays single-base/single-head through `0008`.
- Alembic upgrade/downgrade round-trip test against a disposable test database (existing pattern).
- Constraint tests: `UNIQUE(import_id, source_row_number)`, `UNIQUE(source_snapshot_id)` on `transelec_import`, all `CHECK` constraints, all `ON DELETE RESTRICT`/`CASCADE` behaviors exercised directly.

**Rollback point**: `alembic downgrade` to `0007`; no application code depends on the new tables yet, so this slice is safe to revert in isolation.

## Slice 3 — Strict import (validate/project) and separate publication/restore on shared platform boundaries

**Scope**: `products/transelect/src/transelec_ingestion/import_projection.py` (new) — the validate-and-project step (**Step B** in the [design doc §1](2026-09-02-transelec-hosted-pilot-v2-design.md#1-ingestion--publication-lifecycle)): reuses `xlsx_contract.py` unchanged as a **hard gate** (raise, don't just record `contract_error`, in this specific code path — `transelec_inspector.py`'s evidence-only behavior at upload time is untouched), projects all 30 fields per row into `transelec_resumen_row`, verifies aggregate invariants (structural only — never against the reviewed snapshot's 729/159/272/164.63 counts) against the contract's own counts, and **commits** — this transaction never activates anything. A separate publish/restore mutation (**Step C/D**) — its own short transaction, gated by the new `PUBLISH` action — does the atomic activation. Corrects an earlier draft of this plan, which described validate-and-project as also "performing the atomic activation in one transaction"; that contradicted the design doc's own separate `publish`/`restore` endpoints and is fixed here: three separate mutations (`validate-and-project`, `publish`, `restore`), two transaction shapes (Step B; Step C/D), never combined. New RBAC `Action.PUBLISH` member (`app/access.py`), granted to `OPERATOR`/`ADMIN`. New router endpoints per the [design doc §3 mutations](2026-09-02-transelec-hosted-pilot-v2-design.md#3-api-design). Audit events for `import.validated`, `import.publish.failed`, `import.published`, `import.restored`.

**New platform-level work in this slice, not reused from anywhere**: the CSRF defense described in the [design doc §5](2026-09-02-transelec-hosted-pilot-v2-design.md#5-security-design) does not exist anywhere in this codebase today (confirmed by grep: zero `csrf` hits in any `.py`/`.ts`/`.tsx` file) — it is not Transelec-specific and should land as one shared FastAPI dependency/middleware applied to the generic upload route and every Transelec mutation route alike, not reimplemented per product. If a separate, earlier slice/PR builds this platform-wide, Slice 3 depends on it instead of duplicating it; either way, no Transelec mutation route ships without it.

**Depends on**: Slice 2.

**Reused as-is**: `xlsx_contract.py`, the existing upload/inspection/object-store/job-queue pipeline through `generated_artifact`, `platform.session`/RBAC. **Not** reused, because it doesn't exist: CSRF protection (new, see above).
**Adapted from PR #47**: the *shape* of `persist_validated_workbook()`'s aggregate-count computation (not its code — main's schema already differs in having a row table) — cross-check the aggregate math, not the persistence code.
**Discarded**: PR #47's `object_storage.py`, `transelec_snapshots.py`, admin-token boundary — not touched, not imported.

**Tests**:
- Pure-logic: contract-violation cases (renamed/reordered A:AD column, non-blank AE, wrong row count vs. header) each fail closed with no partial write — synthetic fixture workbooks only, built for this test suite, never the real workbook. Include a fixture with a different row/PMF/predio count than the reviewed 14-Aug snapshot to prove the structural gate does not silently assume 729/159/272.
- Real-PostgreSQL integration: full upload → validate-and-project (commits, no activation) → publish (separate call, separate transaction) → query → duplicate-upload (idempotent, no double-import) → invalid-upload (rejected, active version unchanged) → restore.
- **Transactional-separation test**: inject an invariant-mismatch failure during validate-and-project and assert (a) the whole Step B transaction rolls back — no `transelec_import` row and no `transelec_resumen_row` rows persist — and (b) `transelec_dashboard_state.active_import_id` is byte-identical before and after the attempt, because publish (Step C) was never invoked. Separately, test that a successfully validated-and-projected import does **not** become active until publish is called explicitly.
- RBAC test: `VIEWER` gets 403 on every mutation route; `OPERATOR`/`ADMIN` succeed; cross-product isolation test (a user with only Forestry `PUBLISH`-equivalent grants cannot publish Transelec).
- CSRF test on every mutation route (generic upload, validate-and-project, publish, restore, retry) — exercising the new platform CSRF mechanism above, not an assumed pre-existing one.

**Rollback point**: this slice's router/action additions are additive; reverting the PR removes the endpoints without touching Slice 2's schema (the tables simply stay empty and unused, matching `0004`'s current state today).

## Slice 4 — Authenticated database-backed read APIs

**Scope**: the read endpoints from [design doc §3](2026-09-02-transelec-hosted-pilot-v2-design.md#3-api-design), implementing TR-FUNC-001–023, 032–034, 037, 039, 043's server-side logic against `transelec_resumen_row` for the active import. **TR-OPEN-01 does not block this slice and is not resolved by it.** Corrects an earlier draft of this plan, which said the status-rollup rule would be "implemented once ... and used consistently everywhere," closing the multi-rule inconsistency — that would mean inventing a canonical rule Javier has not picked, which the brief prohibits. Instead, each PMF/predio-grain status computation keeps its own evidenced *legacy* rule from Slice 1's ratified matrix, each under its own explicit basis identifier per the [design doc's "Status-rollup basis" note](2026-09-02-transelec-hosted-pilot-v2-design.md#3-api-design): `estado_resumido_first_row` (TR-FUNC-005/006/011), `pending_priority_legacy` (TR-FUNC-007/032), `owner_stage_legacy` (TR-FUNC-013). TR-FUNC-013 ships in this slice as a normal, unblocked row — not gated — using `owner_stage_legacy`. Each basis is implemented behind one common, named lookup so a future canonical decision replaces the relevant basis centrally, without re-touching every call site.

**Depends on**: Slice 3 (needs at least one published import to read against; tests use a synthetic one).

**Tests**:
- API contract tests: filter-consistency (one filter change, assert KPIs/charts/table all agree — the automated form of TR-FUNC-017's acceptance test), pagination correctness (no hidden row cap), export field-set matches TR-OPEN-04's resolution, version-metadata correctness on `/imports/active` (sourced from `transelec_publish_event`, not `transelec_import` — see design doc §2/§3 corrections).
- Every numeric formula in TR-FUNC-001–016 gets a direct unit test against a hand-built synthetic fixture reproducing the known edge cases from the workbook audit (blank `id_predio_unico` triggering the `predio_group_key` composite fallback, a PMF with disagreeing row statuses to exercise each named legacy rollup basis independently, a row with 100%-empty `Tramite`). Include a fixture whose row/PMF/predio counts differ from 729/159/272 to prove no code path assumes those specific numbers.

**Rollback point**: read-only additions; revertible without any data-model impact.

## Slice 5 — Rebuild UI to complete parity by requirement ID

**Scope**: `products/transelect/dashboard/` on `main` (does not yet exist there — this slice creates it, informed by, not copied from, the ADR-008 demo port's presentation components and the UI-parity branch's originals). Implements every TR-FUNC row's UI per the [design doc §4](2026-09-02-transelec-hosted-pilot-v2-design.md#4-ui-direction). `api.ts` calls the real endpoints from Slice 4 — zero fixture data, zero `demoData.ts`-style module in this product surface (that stays exclusively ADR-008's separate demo app).

**Tests**:
- React component tests for every TR-FUNC UI element.
- Playwright acceptance tests, one per TR-FUNC-* interaction ID from the parity matrix (46 tests, matching the matrix's own row count, so matrix coverage and test coverage are mechanically kept in sync) — including the print/PDF pixel-equivalence test (TR-FUNC-038/045) and the clipboard-copy test (TR-FUNC-035, re-verified live since the forensic audit could only partially confirm it under headless permissions).
- Desktop + phone-width QA at the two confirmed breakpoints, keyboard/focus pass, zero console errors.
- Empty/loading/unauthorized/invalid-upload/import-failed/duplicate-upload/restore-confirmation state tests.

**Rollback point**: new frontend app; does not touch the API or schema — revertible independently.

## Slice 6 — Integrate portal/private access and production packaging

**Scope**: wire `/transelec` into the company portal's module registry (real backend, session-authenticated — not the ADR-007/ADR-008 iframe-to-a-static-demo pattern, which stays exactly as it is for the separate synthetic demo app). Production container packaging (non-root user, health/readiness endpoints — reuses the existing platform-wide pattern, no Transelec-specific runtime).

**Depends on**: Slices 3–5.

**Tests**: production-image verification as a non-root user; health/readiness behavior under the platform's existing test pattern.

**Rollback point**: portal wiring is additive routing; revertible without touching the product code itself.

## Slice 7 — Synthetic staging verification

**Scope**: exercise the full pipeline against synthetic, clearly-fake fixture data only (same discipline as ADR-008) in a non-public or access-controlled environment — **not** the current public Render staging blueprint, which stays exactly as ADR-007/ADR-008 left it (LiDAR hosted for real, Forestry/Transelec synthetic-demo-only). This slice proves the real pipeline works end-to-end before any real-data question is even asked.

**Tests**: full `make check`, persistence/migration checks, dashboard lint/test/build, dependency audit, full-history secret scan, `git diff --check` — all against synthetic fixtures only.

**Rollback point**: environment-level; no schema/code impact beyond what Slices 1–6 already introduced.

## Slice 8 — Private identity/storage/database gate and real-data pilot deployment

**Scope**: **blocked** on the Entra tenant prerequisite (see [design doc §6](2026-09-02-transelec-hosted-pilot-v2-design.md#6-hosting-decision-gate)) and on ADR-001/ADR-004's resolution. This slice is not started by writing code first — it starts when a tenant admin completes `entra-app-registration-handoff.md` and the team accepts a production provider. Only then does real Transelec data ever get uploaded anywhere outside a developer's own machine.

**Exit condition**: private, authenticated, real-data pilot live for Javier, with the classification in the design doc's §6 upgraded from NOT READY to READY FOR PRIVATE REAL-DATA PILOT, backed by a verified Entra sign-in test and a verified private deployment (not a local image, not synthetic staging).

## Requirement-ID traceability

Every `TR-FUNC-*` row's acceptance test lives in Slice 4 (server logic) and/or Slice 5 (UI/E2E) as named above. Every `TR-OPEN-*` item is either answered by Javier in Slice 1, or shipped behind an explicit, named provisional default that a later, centralized change can replace — **none is left implicit in code, but not all are resolved by this plan**; TR-OPEN-01 in particular is deliberately deferred, not resolved, by every slice below. The [functional parity matrix](../../../products/transelect/docs/audit/2026-09-02-functional-parity-matrix-v1.md) is the source of truth for this mapping — this plan does not restate all 46 rows, it points to them.

## Open decisions

### Blocks only production (real-data) deployment — Slice 8

- Campo Digital Entra tenant creation and app registration (externally gated, tenant-admin action).
- ADR-001 vs. ADR-004 production provider acceptance.

### Can safely use an explicit provisional default (does not block any slice)

- **TR-OPEN-01 — canonical PMF/predio status-rollup rule.** Corrects an earlier draft of this plan, which listed this under "Blocks implementation now." It does not block schema design (Slice 2), uploads/snapshots/projection/immutable imports (Slice 3), publication/restore/provenance (Slice 3), RBAC/CSRF (Slice 3), non-rollup-dependent filters/table-browsing/export (Slice 4), the UI build (Slice 5), or production packaging (Slice 6) — none of those depend on Javier having picked one canonical rule. Until he does, each affected view (TR-FUNC-005/006/007/011/013/032) ships Javier's own evidenced *legacy* rule under an explicit basis identifier (`estado_resumido_first_row`, `pending_priority_legacy`, `owner_stage_legacy` — see [design doc §3](2026-09-02-transelec-hosted-pilot-v2-design.md#3-api-design)), architected so Javier's later decision replaces the rule centrally, in one place, rather than gating Slice 4/5 on a decision only he can make. TR-FUNC-013 in particular ships unblocked in Slice 4/5 using `owner_stage_legacy` — it is not held back pending TR-OPEN-01.
- TR-OPEN-02 — which `Carpeta` column(s) to surface: the schema already preserves both (`carpeta_source`, `carpeta_normalizada`), so this only affects the UI's exact labeling, not the data model; ship both as separate labeled fields pending Javier's preference.
- TR-OPEN-03 (`90 dias`/`Superficie de total de corta` meaning) — store verbatim, don't surface a derived interpretation, until Javier clarifies; TR-FUNC-031's "today" bug fix does not require knowing what `90 dias` means, only that "today" must be computed dynamically.
- TR-OPEN-04 (CSV field set) — default to Actualizable's 17-field set (most recent file), changeable in one place later.
- TR-OPEN-05 (per-empresa comparison view) — default to *not* building a new table; ship the existing focus-only behavior, revisit if Javier asks.
- TR-OPEN-06 (logo asset authorization) — use a placeholder/generic Campo Digital brand mark until authorized; do not extract the base64 payloads from either HTML as a shortcut.

## Related documentation

- [Target architecture spec](2026-09-02-transelec-hosted-pilot-v2-design.md)
- [Functional parity matrix](../../../products/transelect/docs/audit/2026-09-02-functional-parity-matrix-v1.md)
- [Implementation gap analysis](../../../products/transelect/docs/audit/2026-09-02-implementation-gap-analysis-v1.md)
- [Source forensic audit](../../../products/transelect/docs/audit/2026-09-02-source-forensic-audit-v1.md)
