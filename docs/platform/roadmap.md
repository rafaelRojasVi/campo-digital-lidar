# Campo Digital Platform Roadmap

## Status

Planning roadmap.

This document orders platform work by dependency and evidence. It is not a
calendar commitment and does not replace product-specific roadmaps.

**Priority update (2026-08-27)** — Transelec source/domain integration is being
advanced ahead of the previously listed product order because the stakeholder
identified it as the current operational priority and supplied a refined
workbook/dashboard source pair. The existing LiDAR and Forestry roadmap scopes
remain valid; this changes implementation priority, not product boundaries.

## Guiding principle

Campo Digital is one company platform with three bounded products:

1. LiDAR / Cubicación
2. Gestión Predial Forestal / QGIS
3. Transelec

The platform should provide common infrastructure, access, provenance,
operational visibility, and navigation without merging the three product
domains.


### Repository naming note

The stakeholder/project spelling used in this roadmap is **Transelec**.

The repository boundary currently remains:

`products/transelect/`

Do not rename that product path as part of this documentation/foundation work.
Naming alignment is a separate explicit decision.

## Phase 0 — Architecture evidence

**Status: completed foundation.**

Establish the durable platform contracts before introducing persistence or
production infrastructure.

Scope:

- provider research;
- source-system boundaries;
- product boundaries;
- client-data organization;
- local/production topology;
- infrastructure cost model;
- security foundation;
- documentation navigation.

Exit condition:

The repository has a coherent platform contract and clearly identifies what is
established, proposed, and still unknown.

## Phase 1 — Local platform foundation

**Current phase.**

Build the provider-neutral foundation locally.

Scope:

- PostgreSQL/PostGIS local development service;
- database configuration;
- migration framework;
- persistence infrastructure;
- source-snapshot/provenance foundation;
- artifact-storage boundary;
- job/use-case execution boundary;
- architecture checks;
- reproducible local developer workflow.

Current implementation status (2026-08-27):

- **FACT** — local PostgreSQL 17 / PostGIS 3.5 development and disposable test services are implemented;
- **FACT** — typed database configuration, SQLAlchemy infrastructure, and Alembic migrations are implemented;
- **FACT** — migration `0001` ensures PostGIS and establishes the empty `platform` schema;
- **FACT** — `/health` is dependency-free liveness and `/ready` checks PostgreSQL readiness;
- **FACT** — destructive migration validation is restricted to a dedicated `_test` database;
- **FACT** — real PostGIS integration tests and dedicated persistence CI are implemented;
- **FACT** — provider-neutral source provenance now distinguishes source systems, assets, immutable SHA-256 snapshots, and observations;
- **FACT** — migration `0002` persists that provenance model with database-level identity, integrity, and deletion-safety constraints;
- **FACT** — V1 read-only filesystem discovery and SHA-256 fingerprinting are implemented using normalized root-relative source paths with path-escape and symbolic-link rejection;
- **FACT** — discovered filesystem provenance can be persisted transactionally while reusing source-system, source-asset, and content-snapshot identities and appending observation history;
- **FACT** (2026-09-01) — migrations `0003`–`0006` are implemented: Forestry's immutable shapefile substrate, Transelec's hosted workbook snapshots, a platform access foundation (`app_user`, `product_grant`, `audit_event`), and a platform ingestion foundation (`upload_session`, `ingestion_run`, `processing_job`, `processing_attempt`, `generated_artifact`, plus an `object_storage_key` column on `source_snapshot`) — all as a single linear chain; see `docs/adr/ADR-003-migration-revision-allocation-convention.md`;
- **FACT** (2026-09-01) — a provider-neutral `ObjectStore` interface is implemented, with a filesystem-backed `LocalObjectStore` (content-addressed by SHA-256, atomic writes, path-traversal/symlink-safe) as the local V1 implementation;
- **FACT** (2026-09-01) — a dev-only authentication adapter and product-scoped RBAC (`ADMIN`/`OPERATOR`/`VIEWER` per product grant) are implemented, hard-gated against `APP_ENV=production`, with authentication and authorization kept strictly separate;
- **FACT** (2026-09-01) — a controlled multi-product upload/intake boundary is implemented (`POST /ingesta/upload`), with lightweight per-product inspection adapters (LiDAR header/bounds via the existing `lidar_io.inspect`, Transelec workbook via the existing `transelec_ingestion.xlsx_contract`, and a new zip-slip/zip-bomb-hardened Forestry ZIP inspector) and an append-only audit event ledger;
- **FACT** (2026-09-01) — a durable PostgreSQL-backed job queue is implemented using `SELECT ... FOR UPDATE SKIP LOCKED` (no message broker), with bounded automatic retries, stale-lease reclamation, and a local worker (`make platform-worker`, `make platform-worker-concurrency`); two-worker claim exclusivity is covered by a dedicated integration test;
- **FACT** (2026-09-01) — the full flow (dev login → role-gated upload → async processing → generated artifact → audit trail) is demonstrated end-to-end through a page in the existing portal (renamed `/archivos`, "Archivos", as of the hosted-composition slice below), manually verified in a real browser for ADMIN, OPERATOR, and VIEWER identities, including product isolation;
- **LIMITATION** — the three per-product inspectors are intentionally lightweight evidence checks, not the real LiDAR/Forestry/Transelec processing pipelines; connecting those remains future work. Cloud object storage, a production identity provider, and the upload transport for very large files (direct-to-storage signed/resumable upload) remain unimplemented — see `docs/research/2026-09-01-platform-runtime-infrastructure-study.md`.
- **RESULT** (2026-09-01) — the portal is explicitly LOCAL/STAGING-aware and LiDAR is hosted at $0 on Render as a static site reusing the already-deployed platform API's DB-independent `/runs` endpoint, verified to return a genuinely empty result set under the same configuration Render's fresh checkout will run; Forestry and Transelec show an honest not-yet-hosted state instead of a fake green status. See `docs/adr/ADR-007-hosted-product-composition-v1.md`.
- **RESULT** (2026-09-01) — hosted staging QA against the live Render deployment confirms the above: `GET /health` -> 200 `{"status":"ok"}`, `GET /ready` -> 200 `{"status":"ready"}`, `GET /runs` -> 200 `[]`, `POST /auth/dev-login` -> 404 (per `ADR-006-restrict-dev-auth-to-development.md`); `/archivos` shows the platform-sign-in-unavailable message pending Entra ID; `/estado` correctly identifies itself as public staging with no real client data; the hosted LiDAR module loads with 0 measurements; Forestry and Transelec show the honest not-yet-available state. All four Blueprint resources (`campo-digital-portal-staging`, `campo-digital-api-staging`, `campo-digital-lidar-staging`, `campo-digital-db-staging`) are deployed. Blueprint auto-sync is currently paused (deploys are manual until re-enabled); the free Postgres instance expires 2026-10-01 per ADR-005's 30-day free-tier limit.

Exit condition:

A clean checkout can start the local platform and apply the database schema
reproducibly without requiring paid cloud services.

## Phase 2 — LiDAR platform integration

Do **not** rebuild the LiDAR scientific engine.

LiDAR is the first mature product used to prove the shared platform
foundation.

Scope:

- preserve existing scientific behavior and evidence;
- preserve existing API behavior unless an explicit change is approved;
- connect measurement/run metadata to platform persistence where justified;
- route large/private artifacts through the storage boundary;
- separate long-running processing from normal HTTP request handling;
- keep LAS/LAZ and other private client data outside Git;
- preserve readiness and scientific-evidence rules;
- run the full existing LiDAR regression suite.

Exit condition:

A real mature product uses the platform foundation without contaminating its
scientific/domain boundary.

## Phase 3 — Forestry source/domain contract

Derive the Forestry model from real source evidence and stakeholder
confirmation.

Scope:

- Shapefile/source ingestion;
- immutable source snapshots;
- schema validation;
- canonical polygon state;
- PostGIS persistence;
- geometry/history semantics;
- API projection;
- product tests;
- initial Forestry dashboard contract.

Do not invent workflow states, approval semantics, or business entities that
have not been established.

Current implementation status (2026-08-29):

- **FACT** — the first real Forestry source snapshot (Degenfeld estate
  shapefile family) has a forensic evidence record in
  `products/forestry/docs/source-evidence-v1.md`;
- **FACT** — a structural Source Contract V1 (family completeness, declared
  CRS/encoding, DBF schema, record-count integrity, fingerprinting) is
  implemented in `forestry_ingestion.shapefile_contract` with synthetic-fixture
  tests;
- **FACT** — Ingestion Substrate V1 is implemented
  (`products/forestry/docs/ingestion-substrate-v1.md`): immutable,
  idempotent PostGIS persistence of contract-valid snapshots (migration
  `0003`, schema `forestry`) with snapshot-local feature identity,
  faithful geometry storage under EPSG:32718, quality-flag evidence, and
  service-level read projections — verified read-only against the real
  Degenfeld snapshot;
- **FACT** — Read API V1 is implemented
  (`products/forestry/docs/read-api-v1.md`): a read-only factual HTTP
  projection under `/api/forestry` (snapshot list/summary, source predio
  and use distributions, literal source-field comparison, paginated and
  filterable feature listing, feature detail, GeoJSON-encoded geometry in
  the source CRS) — verified read-only against the real Degenfeld snapshot;
  it establishes no canonical identity, workflow, or current-state
  semantics;
- **OPEN QUESTION (integration)** — Alembic revision `0003` also exists on
  the unmerged Transelec hosted-pilot branch; whichever product branch is
  integrated second must be re-revisioned so `main` keeps a single Alembic
  head (see `products/forestry/docs/read-api-v1.md`, Integration concerns);
- **LIMITATION** — canonical entities (predio/rodal/polygon identity across
  snapshots), workflow semantics, and the dashboard remain open pending
  stakeholder answers
  (`products/forestry/docs/es/preguntas-campo-digital.md`).

Exit condition:

Forestry source data can be ingested reproducibly into an evidence-backed
canonical model.

## Phase 4 — Transelec source/domain contract

Derive the Transelec model from workbook, dashboard, and stakeholder evidence.

Scope:

- XLSX schema contract;
- source snapshots;
- data-change vs schema-change detection;
- current state and history;
- status/workflow semantics;
- API projection;
- dashboard projection;
- product tests.

A renamed, replaced, or deleted OneDrive workbook must not silently destroy
canonical history.

Exit condition:

Daily-changing source data can be ingested safely while preserving provenance
and history.

## Phase 5 — Company platform UI/API

Create one coherent Campo Digital user experience.

Current implementation status (2026-08-31):

- **FACT** — a local company portal V1 exists (`apps/portal/`) with a
  stakeholder-facing home screen and per-module shells for all three
  products; see [Company portal V1](company-portal-v1.md).
- **FACT** — local module navigation/composition is implemented: each
  product dashboard is embedded via iframe behind a thin Campo Digital
  header, with back navigation, a compact module switcher, and an
  "open in new tab" fallback.
- **FACT** — `make campo-demo` / `make campo-status` / `make campo-stop`
  discover sibling product worktrees by branch, start or adopt each
  product's own existing launcher, and only ever stop processes they
  themselves started.
- **FACT** — LiDAR gained a minimal local launcher (`make lidar-dev`) so it
  can run alongside Forestry and Transelec in one demo; no scientific or
  persistence behavior changed.
- **LIMITATION** — the iframe composition is explicitly a local-demo
  strategy, not a production routing decision.
- **OPEN** — authentication/session entry point, production routing,
  deployment, and multi-tenant access are all still pending (Phase 6).

Target shape:

```text
                 CAMPO DIGITAL
                       |
                    Sign in
                       |
                       v
                Company portal
                       |
          +------------+------------+
          |            |            |
          v            v            v
        LiDAR       Forestry     Transelec
      Dashboard     Dashboard     Dashboard
          |            |            |
          +------------+------------+
                       |
                       v
                  Shared FastAPI
                       |
            +----------+----------+
            |                     |
            v                     v
     PostgreSQL/PostGIS     artifact storage
```

Potential company-level responsibilities:

- authentication/session entry point;
- company branding;
- navigation;
- product/project entry points;
- platform health;
- ingestion status/review;
- artifact access;
- user/account context.

Product-specific dashboards remain product-owned.

Shared UI components move to `packages/ui/` only after real reuse exists.

Exit condition:

Users can enter one Campo Digital platform and navigate to the products they
are authorized to use.

## Phase 6 — Production deployment

Finalize the production provider using then-current evidence and pricing.

Current leading candidate (per ADR-001, Proposed, 2026-08-27):

- GCP Santiago.

**OPEN QUESTION** (2026-09-01) — `docs/adr/ADR-004-revisit-production-cloud-provider-choice.md`
(Proposed, not accepted) proposes Azure Chile Central as a competing
candidate, based on newly-confirmed regional parity and Microsoft/OneDrive
ecosystem fit; see `docs/research/2026-09-01-platform-runtime-infrastructure-study.md`.
Neither ADR-001 nor ADR-004 is finalized — this phase remains open pending
team review and a real LiDAR pipeline benchmark.

Production concerns:

- managed PostgreSQL/PostGIS;
- private object storage;
- API hosting;
- jobs/workers;
- authentication;
- secrets;
- migrations;
- backups and restore testing;
- monitoring;
- billing alerts;
- CI/CD;
- domain/TLS;
- staging decision.

The provider remains revisitable until production is actually required.

Exit condition:

The shared platform is available to authorized users without depending on a
developer laptop.

## Phase 7 — Operational maturity

Add complexity only when evidence justifies it.

Possible later capabilities:

- database high availability;
- Microsoft Graph delta ingestion;
- stronger job orchestration;
- structured audit/admin cockpit;
- disaster-recovery exercises;
- read replicas;
- dedicated high-memory/CPU processing;
- cost optimization;
- more advanced observability.

Do not introduce Kubernetes, Redis, Celery, Kafka, RabbitMQ, multiple database
servers, or other infrastructure merely for hypothetical scale.

## Related documentation

- [Platform documentation](README.md)
- [System overview](system-overview.md)
- [Production platform V1](production-platform-v1.md)
- [Source ingestion](source-ingestion.md)
- [Security model](security-model.md)
- [Environments and costs](environments-and-costs.md)
