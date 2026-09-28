# Transelec — current-implementation gap analysis (main, PR #47, UI-parity branch)

## Status

Evidence record from direct, read-only inspection of `origin/main`
(`738f34ff9cd4d868b6ac96bb57afc7d20cf4d211`), PR #47
(`feat/transelec-hosted-pilot-v1` @ `1c3392725b6dba036e65158a3a9c6ee8acf21b91`),
and the UI-parity branch (`feat/transelec-ui-reference-parity-v1` @
`adc61788fa9eec388de8149d60facfe4f9e7b050`). No git write operations were
performed against any worktree during this audit.

## Branch lineage

A single linear chain, not three independent efforts:

```
PR #46 (merged) — Transelec Source Contract V1
  -> feat/transelec-domain-evidence-v1 (unmerged; adds domain_evidence.py, pmf_view.py,
     a read-only Transelec router, a read-only dashboard)
       -> feat/transelec-hosted-pilot-v1 (PR #47; adds hosted persistence, Cloud Storage,
          admin-token publish/activate, IAP deployment runbook)
            -> feat/transelec-ui-reference-parity-v1 (IA redesign pass; own final commit:
               "not an old-HTML translation")
```

## Migration lineage — collision confirmed and resolved on `main`, unresolved on PR #47

`origin/main` has a single linear migration chain, base `0001`, head `0007`:

| revision | scope |
|---|---|
| 0001 | PostGIS extension, empty `platform` schema |
| 0002 | `source_system`/`source_asset`/`source_snapshot`/`source_observation` |
| 0003 | Forestry: `forestry.shapefile_snapshot`, `forestry.source_feature` |
| **0004** | **Transelec**: `platform.transelec_workbook_snapshot`, `platform.transelec_dashboard_state` |
| 0005 | `platform.app_user`, `platform.product_grant`, `platform.audit_event` |
| 0006 | `platform.upload_session`, `platform.ingestion_run`, `platform.processing_job`, `platform.processing_attempt`, `platform.generated_artifact`, `source_snapshot.object_storage_key` |
| 0007 | `platform.session` (hashed-cookie sessions), `platform.ms_graph_grant` |

ADR-003's renumbering (Forestry keeps `0003`, Transelec's colliding migration renumbered to `0004`) is **already fully applied on `main`**.

PR #47's own `migrations/versions/0003_establish_transelec_hosted_snapshots.py` (`revision="0003"`, `down_revision="0002"`) is **byte-for-byte identical in its table/column bodies** to main's `0004`. This is not a design disagreement — PR #47 simply predates the renumbering and was never rebased. **Reconciliation is mechanical: discard PR #47's migration file entirely** (its tables already exist on main via `0004`); do not renumber and reapply it, which would attempt to `CREATE TABLE` both tables a second time.

`platform.transelec_workbook_snapshot` (already on `main`, unused by any router today) stores **aggregate counts only** — `business_rows`, `distinct_pmf`, `distinct_provisional_predio_ids`, `surface_total` — keyed 1:1 to a `source_snapshot`. `platform.transelec_dashboard_state` (already on `main`, also unused) is a singleton active-pointer row (`CHECK id = 1`, nullable FK `active_source_snapshot_id`, `ondelete=RESTRICT`) — exactly the active-version-pointer shape the target design needs for atomic publish/restore. **Neither table has a per-row projection.** No `transelec_resumen_row` (or equivalent) exists anywhere in this repository, on any of the three branches. Building it is new schema work regardless of which branch's prior art is reused.

## Current Transelec surface on `main`

- `products/transelect/src/transelec_ingestion/xlsx_contract.py` — the schema-contract parser only. Positional (not header-keyed) column mapping for all 30 A:AD fields, explicitly distinguishing the two `Carpeta` columns as `carpeta_source` (col 5) and `carpeta_normalizada` (col 29); blank-separator check at column 31; rows without `pmf` are silently skipped (`continue`, no per-row warning recorded); source row number is 1-indexed from the header, equal to the real Excel row number.
- `apps/api/app/inspection/transelec_inspector.py` — wraps the contract parser for the generic upload pipeline. Confirmed: `dispatch_inspection("transelect", path)` never raises on a contract violation; it records `contract_error` as evidence on the inspection result. "Intake inspection reports evidence; it does not gate upload" — by design, for now.
- **No `products/transelect/dashboard/` exists on `main`.** The demo dashboard visible in the current working branch (`feat/hosted-demo-data-v1`, this task's starting point) is unmerged ADR-008 work, not yet on `main`.
- **Confirmed end-to-end today**: a Transelec upload goes through the shared pipeline — bounded streaming intake (2 GiB cap) → `ObjectStore.put()` (SHA-256 content-addressed) → `source_snapshot` provenance row → `ingestion_run` row → `processing_job` enqueued (Postgres `SELECT ... FOR UPDATE SKIP LOCKED`) → worker claims the job, re-runs the inspector, writes a `generated_artifact` (JSON). **No code path anywhere on `main` writes Resumen rows into any table, and no code path reads `transelec_workbook_snapshot`/`transelec_dashboard_state`.** Main can validate/inspect a Transelec upload; it cannot import or publish one. This fully confirms the task brief's stated understanding of `main`'s current state.
- **RBAC** (`app.access`): `Role` = `admin`/`operator`/`viewer`; `Action` = `VIEW`, `UPLOAD`, `PROCESS`, `RETRY`, `MANAGE_ACCESS`. **No `PUBLISH` or `RESTORE` action exists yet.** Adding Transelec's publish/restore lifecycle needs either a documented reuse of `PROCESS`/`MANAGE_ACCESS`, or two narrow new `Action` members — a small, additive change to one `frozenset` literal.
- Session auth (`platform.session`, hashed-cookie, migration `0007`) exists and is reusable as-is; nothing Transelec-specific consumes it yet.

## PR #47 (`feat/transelec-hosted-pilot-v1`) — prior art, not a mergeable unit

Its architecture predates migrations `0005`–`0007` entirely and is a **parallel universe**, not an extension of `main`'s current foundation: no `app_user`/`product_grant`/`audit_event`, no job queue, no `platform.session`. Instead:

- **Separate, incompatible object-store module** (`apps/api/app/object_storage.py`, 148 lines; `local`/`gcs` backends). Conceptually the same idea as `main`'s `ObjectStore` protocol, but a second implementation — adopting it as-is means two object-store abstractions in one app. Its GCS-backend logic has no equivalent on `main` and may be worth extracting later on its own merits, not as this module.
- **Reparses the workbook on every dashboard read, confirmed by direct code read**: `_load_hosted_rows()` in `routers/transelec.py` calls `load_workbook_from_bytes()` inside every single `/summary`, `/filters`, `/pmfs`, `/pmfs/{pmf}` handler. This is the one pattern that must not be reused under any circumstance — it is exactly the architecture the task brief instructs against.
- **Admin-token boundary, exact mechanism confirmed**: `require_admin_token()` compares an `X-Transelec-Admin-Token` header via `secrets.compare_digest` against a single shared `CAMPO_TRANSELEC_ADMIN_TOKEN` environment secret. Gates only `POST /snapshots` (publish) and `POST /snapshots/{id}/activate` (restore). No per-user identity, no session, no CSRF token, no audit-event write anywhere in `transelec_snapshots.py` on publish or activate. One secret authorizes every operator with no attribution of which human acted.
- **`pmf_view.py` (383 lines) is the one genuinely valuable, reusable asset**: `filter_resumen_rows()` (AND across dimensions, OR within a multi-select — confirmed from the router's own docstring and query-param plumbing), `build_summary()` (KPIs computed from the *same* filtered set the row list uses, so KPIs and table never disagree under a filter), `list_pmfs()`/`get_pmf_detail()` (PMF → predio-group → row hierarchy). **This is exactly the PMF-level status aggregation `source-contract-v1.md` calls "not yet established from stakeholder evidence"** — PR #47 built and shipped one anyway, without documented sign-off. Its *shape* (filter semantics, response types, the "KPIs and table share one filter set" discipline) is worth reusing; its *business rules* need verification against TR-OPEN-01 before being treated as canonical, not assumed correct because code exists.
- **`products/transelect/docs/deployment.md`** proposes Cloud Run + Cloud SQL (shared `platform` schema, explicitly "interim pilot placement") + a private Cloud Storage bucket + **Cloud Run IAP restricted to a named Google Group as the sole access gate** (the admin token protects mutations *underneath* IAP, explicitly documented as "not a substitute for IAP"). This conflicts with a platform fact confirmed independently in this same audit session: **no Campo Digital Entra tenant exists, and the real OneDrive source is a personal Microsoft account, not a Google Workspace** — every Transelec viewer would need a Google identity the rest of the platform doesn't use anywhere else. This is a genuine hosting-gate mismatch with current platform reality, not merely a stale draft.
- **Tests**: `test_xlsx_contract.py`, `test_domain_evidence.py`, `test_pmf_view.py` — pure-logic tests exist; no API/DB integration test coverage was confirmed for `transelec_snapshots.py` or `routers/transelec.py` in this pass (not exhaustively enumerated — spot-check before relying on this claim for planning purposes).

**Verdict**: treat the whole branch as prior art. Migration: discard. Object storage and admin-token auth: discard, superseded by `main`'s foundation. `pmf_view.py` shape: port after validating business rules. Reparse-on-read: must not be repeated.

## UI-parity branch (`feat/transelec-ui-reference-parity-v1`)

Component tree (`products/transelect/dashboard/src/`): `App.tsx`, `MultiSelectField.tsx`, `api.ts` (same TypeScript interfaces as PR #47's backend, still assumes the admin-token API), plus `AppHeader.tsx`, `ExecutiveKpis.tsx`, `FilterPanel.tsx`, `Pagination.tsx`, `PmfDetailDrawer.tsx`, `PmfExplorer.tsx`, `SourceManager.tsx`, `SourceStatusCard.tsx`, `StatusDistribution.tsx`, `StatusPills.tsx`.

**Its own final commit message is direct, self-documented evidence of the exact problem this task exists to correct.** Quoted verbatim: *"Re-evaluated the dashboard from data shape and real workflows rather than continuing to track Javier's HTML layout... QuickActions removed entirely — audited all 6 actions and every one duplicated a better-placed control elsewhere... ViewSummaryPanel ('Vista actual') restated 5 of its 6 facts verbatim from the KPI cards... removed as duplication."* This is a unilateral IA/feature decision based on the branch author's own judgment of "duplication," made without verified evidence that the removed functions were actually redundant to Javier. The parity matrix in this discovery treats every function named or implied by that commit message as a **candidate row requiring independent re-verification against the HTML audits**, not as settled non-functionality — see TR-FUNC-024 through 031 and TR-FUNC-034, which is exactly where a "QuickActions"/"ViewSummaryPanel"-shaped set of removed functions would have mapped had this discovery not independently re-derived the full set directly from the HTML files.

**Diff against the ADR-008 demo port already present in this session's starting branch** (`feat/hosted-demo-data-v1`, not on `main`):

- **Removed** in the ADR-008 port (correctly, per that ADR's own scope — real-data/upload safety for a public demo, not a parity judgment): `SourceManager.tsx`, `SourceStatusCard.tsx` (upload/admin/source-history UI), `AppHeader.tsx` (replaced by a generic `DemoHeader.tsx`).
- **Kept as pure presentation, filenames unchanged**: `ExecutiveKpis.tsx`, `FilterPanel.tsx`, `Pagination.tsx`, `PmfDetailDrawer.tsx`, `PmfExplorer.tsx`, `StatusDistribution.tsx`, `StatusPills.tsx`, `MultiSelectField.tsx`, `format.ts`, `icons.tsx` (not diffed line-by-line against the UI-parity branch's originals in this pass — recommend a direct `diff -rq` before relying on exact line-level reuse).
- **New in the ADR-008 port**: `demoData.ts` (synthetic fixture), `demoPmfView.ts` (`pmf_view.py`'s logic reimplemented in TypeScript against fixture data) — confirming those business rules were considered stable enough to port to a second language, which is more reason to validate them against TR-OPEN-01 before treating them as canonical, not less.
- `api.ts` in the current working branch has zero `fetch()` calls — fully static, as ADR-008 documents.

## Architectural conflicts a target design must resolve, not inherit

1. **Two object-store abstractions** (main's `ObjectStore` protocol vs. PR #47's `object_storage.py`) — resolve by extending main's protocol only.
2. **Two auth models** (main's session/RBAC vs. PR #47's shared admin token) — resolve by extending main's `Action` enum, discard the token model.
3. **Generic ingestion vs. Transelec publication** — main's pipeline stops at "inspected"; Transelec needs a strict-validation-as-hard-gate step, a transactional row projection, an invariant check, and an explicit atomic publish step layered on top, not a fork of the generic pipeline.
4. **Reparse-on-read vs. DB-backed reads** — no branch has a working example of the latter for Transelec; it is new work everywhere, and the one existing example (PR #47) is the anti-pattern to avoid.
5. **IAP/Google identity vs. the platform's actual identity surface** — PR #47's deployment runbook assumes an identity system Campo Digital does not otherwise use; see the target architecture's hosting-decision-gate section.

## Capability × branch reuse summary

| Capability | `main` | PR #47 | UI-parity branch | Reuse verdict |
|---|---|---|---|---|
| 30-field Resumen schema contract, positional parsing | Yes (`xlsx_contract.py`) | Yes (identical) | N/A | Reuse as-is — canonical, tested |
| Upload → object storage → provenance → job queue → audit | Yes, generic multi-product | No (own store, no queue) | N/A | Reuse main's pipeline, add a Transelec post-inspection step |
| RBAC (role × action) | Yes, no `PUBLISH`/`RESTORE` | No (shared static token) | N/A | Extend main's `Action` enum |
| Session auth | Yes (`platform.session`) | No | N/A | Reuse as-is |
| Real production identity provider | No (no Entra tenant; personal-account OneDrive) | Assumes Google IAP | N/A | Neither ready — genuine open blocker |
| Immutable per-import Resumen row table | **No, anywhere** | **No** (aggregate counts only) | N/A | New work, all three branches |
| Active-version pointer table | Yes, unused | Yes, its own copy of the same shape | N/A | Reuse main's `transelec_dashboard_state` |
| Dashboard reads from a DB projection | N/A (no reads exist) | **No — reparses XLSX every request** | N/A (calls the same pattern) | Do not reuse this pattern |
| PMF-level status aggregation / filter semantics | No | Yes, unverified against stakeholder evidence | Ported to TS, same caveat | Reuse the shape, re-verify the rules |
| Presentation components (KPIs, filters, pagination, PMF drawer, status donut) | No | Baseline | Refined, with acknowledged unilateral removals | Reuse as a starting point; restore anything the parity matrix shows was dropped without evidence |
| Object storage abstraction | Yes (`ObjectStore` protocol) | Separate, incompatible | N/A | Reuse main's; consider porting GCS-backend logic later |
| CSRF / cookie security for mutations | **Correction**: does not exist anywhere on `main`, for any product, not just "not yet wired to Transelec" — confirmed by grep this session: zero `csrf` hits (case-insensitive) in any `.py`/`.ts`/`.tsx` file in the repository. `main`'s mutation routes (e.g. `/ingesta/upload`) authenticate via the `campo_session` cookie plus RBAC only | None (bearer-style token) | N/A | New, platform-wide work — session infra is reused, but the CSRF mechanism itself must be built once for every product, not assumed present |

## Related documentation

- [Source forensic audit](2026-09-02-source-forensic-audit-v1.md)
- [Functional parity matrix](2026-09-02-functional-parity-matrix-v1.md)
- [Target architecture spec](../../../../docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-design.md)
- [ADR-003 — Migration revision allocation convention](../../../../docs/adr/ADR-003-migration-revision-allocation-convention.md)
