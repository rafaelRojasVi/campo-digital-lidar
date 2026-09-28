# Campo Digital Platform — Monorepo Architecture

## Architectural shape

Campo Digital is a product-first monorepo with three bounded product contexts:

1. LiDAR / Cubicación
2. Gestión Predial Forestal / QGIS
3. Transelec

The repository uses a modular-monolith backend and separate product-owned
frontends.

## Target structure

    products/
      lidar/
        src/
        tests/
        dashboard/
        docs/
        configs/
        data/
        pipelines/
        notebooks/
        reports/

      forestry/
        src/
        tests/
        dashboard/
        docs/

      transelect/
        src/
        tests/
        dashboard/
        docs/

    apps/
      api/
        app/
          routers/
          inspection/

    packages/
      contracts/
      ui/

    config/
      source-catalog.yaml

    scripts/
      tests/

    docs/
      platform/
      adr/
      source-systems/

## Product ownership

Anything specific to one product belongs under that product root.

Examples:

- LiDAR geometry belongs under `products/lidar/`.
- Forestry rodal logic belongs under `products/forestry/`.
- Transelec business logic belongs under `products/transelect/`.

Platform-level directories contain only genuinely cross-product concerns.

## LiDAR migration

**Status: complete.** The LiDAR project lives under `products/lidar/`,
including its Python source, tests, dashboard, research documentation,
sensor/measurement configuration, notebooks, PDAL pipelines, data layout,
and generated-report layout. The migration preserved the established
scientific behavior and test baseline.

## Backend

`apps/api` is the shared HTTP composition layer. Its Python package is
`apps/api/app/` — a flat package, not nested under `src/`.

Established convention: code is grouped by technical role, not by product
namespace, because most of what lives here today is genuinely
cross-product platform infrastructure (access control, authentication,
audit, the job queue, object storage, source provenance) with only a thin
layer of product-specific adapters on top:

- `apps/api/app/routers/` — HTTP route modules. Product-specific routers
  are named per product (e.g. `routers/lidar.py`); platform-wide routers
  (e.g. `routers/ingestion.py`, `routers/dev_auth.py`) are not.
- `apps/api/app/inspection/` — lightweight per-product intake inspection
  adapters (`lidar_inspector.py`, `forestry_inspector.py`,
  `transelec_inspector.py`), one file per product.

Per-product subpackages (`app/lidar/`, `app/forestry/`, `app/transelect/`)
remain a reasonable future step if a product's router/adapter surface
grows enough to justify the extra nesting — introduce that split only when
it has real files to hold, not ahead of demonstrated need.

Core product logic must not depend on FastAPI.

## Shared packages

Shared packages are created only when multiple real consumers require them.

Initial shared packages:

- `packages/contracts`
- `packages/ui`

Avoid generic `common`, `helpers`, `shared-domain`, or `services` dumping
grounds.

## External integrations

External systems are accessed through platform adapters.

Examples:

- OneDrive / Microsoft Graph
- object storage

Product domains must not depend directly on vendor URLs, OAuth details,
filesystem-specific paths, or SDK-specific payloads.

## Dependency direction

Allowed:

    dashboard
       ↓
    contracts
       ↓
    API adapter
       ↓
    product domain

Forbidden:

    product A → product B frontend
    packages → apps
    pure product domain → FastAPI
    pure product domain → OneDrive SDK
    pure product domain → HTTP router

## Persistence

Canonical structured/geospatial data:

- PostgreSQL
- PostGIS

Large private/source assets:

- object storage

OneDrive remains a collaboration/source system, not the production database.

## Migration discipline

1. Define architecture and safety rules.
2. Move LiDAR as one bounded product.
3. Re-establish the full LiDAR quality baseline.
4. Introduce workspace tooling and executable architecture checks.
5. Add Forestry foundations.
6. Add Transelec after its real workflow is understood.
7. Add production persistence and ingestion infrastructure.
