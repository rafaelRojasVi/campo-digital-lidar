# Campo Digital Platform

Multi-product geospatial and forestry software platform for Campo Digital.

## Company portal (local demo)

A local company-branded portal at `apps/portal/` gives one URL that
navigates into all three products. It is a local demo composition, not a
production routing architecture — see
[Company portal V1](docs/platform/company-portal-v1.md).

    make campo-demo      # start (or adopt) all products + the portal
    make campo-status
    make campo-stop

## Products

### LiDAR / Cubicación

Point-cloud processing and measurement R&D for timber stacks.

Existing capabilities include:

- LAS/LAZ forensic inspection
- pile localization
- local face geometry
- projected-face measurement
- estimator benchmarking
- reference validation
- geometric volume analysis

The existing LiDAR scientific documentation remains authoritative for this
product.

See:

- `products/lidar/`
- `products/lidar/docs/roadmap.md`
- `products/lidar/docs/experiments/`
- `products/lidar/docs/decisions/`

### Gestión Predial Forestal / QGIS

Forestry GIS product for:

- predios and properties
- rodales
- polygon management
- partial harvest operations
- area calculations
- cartographic visualization
- GIS and Excel export
- client reporting

Status: Source Evidence V1 and Source Contract V1 established from the first
real estate snapshot. See `products/forestry/README.md`.

### Transelec

Independent application domain for the Campo Digital Transelec project.

Status: requirements discovery from source material.

## Architecture

The repository is transitioning to a monorepo with explicit bounded contexts.

See:

- `docs/platform/product-boundaries.md`
- `docs/platform/monorepo.md`
- `docs/source-systems/onedrive.md`
- `config/source-catalog.yaml`

## External source data

Campo Digital source material is maintained outside Git, primarily through the
shared OneDrive hub.

Local development may expose a synchronized read-only source tree through:

`CAMPO_DIGITAL_SOURCE_ROOT`

Source data must never be committed to this repository.

## Current implementation

The validated LiDAR implementation remains temporarily in its historical
layout:

    apps/api
    products/lidar/dashboard

    products/lidar/src/lidar_core
    products/lidar/src/lidar_io
    products/lidar/src/lidar_volume
    products/lidar/src/lidar_cli

These paths will be migrated incrementally rather than through one high-risk
rewrite.

## Target platform

The repository is evolving toward a product-first monorepo:

    products/
      lidar/
        src/
        tests/
        dashboard/
        docs/

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

    packages/
      contracts/
      ui/

Anything specific to one product belongs inside that product boundary.

The shared API, integration adapters, generated contracts, reusable UI
components, repository tooling, and platform documentation remain outside the
individual product roots.

See `ARCHITECTURE.md` for the canonical dependency rules.

## Data safety

Never commit:

- private LAS/LAZ files
- client GIS source files
- QGIS project data
- client spreadsheets
- client photographs
- generated private reports
- credentials
- machine-specific OneDrive paths

## LiDAR product documentation

The LiDAR bounded-context entry point is:

`products/lidar/README.md`

The original pre-monorepo repository state remains preserved in Git history at commit `423932c862c1a46bcc7b197c7529fe3b8635ad95`.
