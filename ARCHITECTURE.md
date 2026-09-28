# Campo Digital Platform Architecture

## Shape

Campo Digital is a product-first monorepo with a modular-monolith backend.

There are three bounded products:

- LiDAR / Cubicación
- Gestión Predial Forestal / QGIS
- Transelec

## Product boundary

Product-owned code, tests, documentation, configuration, and frontend code
belong under:

    products/<product>/

Bounded product contexts:

    lidar
    forestry
    transelect

Materialized product roots are created only when product-owned implementation
exists. Currently:

    products/lidar/
    products/forestry/
    products/transelect/

## Shared API

One FastAPI application acts as the HTTP composition layer:

    apps/api/

Its product adapters are isolated by bounded context.

The API may depend on product-domain code.

Product-domain code must not depend on FastAPI.

## Shared frontend packages

Cross-product frontend code may live under:

    packages/contracts/
    packages/ui/

Shared packages must not depend on product applications.

Product applications must not directly import another product application.

## External systems

External providers belong behind adapters.

OneDrive is an external source/collaboration system.

Product logic must not contain:

- Microsoft Graph authentication details
- OneDrive browser URLs
- machine-specific OneDrive paths
- provider-specific retry/status semantics

## Data

PostgreSQL/PostGIS is the target canonical structured-data store.

Large binary assets belong in object storage.

Raw private client datasets never belong in Git.

## Architecture enforcement

Architecture documentation describes the intended system.

`scripts/check_architecture_boundaries.py` enforces the current Python
dependency boundaries locally and in CI through `make architecture-check`
and the canonical `make check` gate.

For every materialized `products/<product>/src` tree, product-owned Python
code must not import FastAPI, the `app` API package, or another product's
top-level Python packages. The shared API may adapt and import product
packages.

These checks intentionally enforce established product boundaries without
inventing unsupported internal layering rules inside a product.

## Canonical details

See:

- `docs/platform/product-boundaries.md`
- `docs/platform/monorepo.md`
- `docs/source-systems/onedrive.md`
- `config/source-catalog.yaml`

## AI-assisted engineering

Repository-level AI engineering configuration belongs under:

    .claude/

Product-specific implementation knowledge may be encoded as namespaced skills
there once repeated real workflows justify them.

Skills must reinforce the repository architecture rather than bypass it.

In particular, AI tooling must respect:

- product ownership boundaries;
- external-data safety;
- canonical `make` quality gates;
- scientific evidence rules for LiDAR;
- adapter boundaries for external providers;
- generated API contracts and executable architecture checks.

Do not create generic skills merely to restate documentation. Add a skill when
it captures a recurring workflow, domain constraint, or review discipline that
materially improves engineering work.
