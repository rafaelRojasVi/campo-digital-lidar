# Campo Digital Production Platform V1

## Status

Production target: **Proposed**.

Local persistence foundation: **Implemented (2026-08-27)**.

This document defines the current target production architecture for Campo
Digital. Managed production infrastructure has not yet been provisioned.

Provider pricing and comparative research are non-canonical and live under
`docs/research/`.

## Objective

Campo Digital needs a maintainable production platform for three separate
bounded product contexts:

1. LiDAR / Cubicación
2. Gestión Predial Forestal / QGIS
3. Transelec

The platform must centralize application state without turning individual
computers, OneDrive, generated HTML files, or spreadsheets into the production
database.

## Core principles

- OneDrive remains a collaboration and external source system.
- PostgreSQL/PostGIS becomes the canonical structured/geospatial store.
- Large and original binary source assets belong in object storage.
- Imported source versions remain auditable.
- Product business logic remains isolated by bounded context.
- The backend remains a modular monolith until concrete requirements justify
  further service separation.
- Long-running processing is separated from normal HTTP request handling.
- Managed infrastructure is preferred over self-managed servers when it
  materially reduces operational burden.
- A stakeholder or developer laptop is never the production source of truth.

## Proposed production topology

```text
Users
  |
  v
Product web applications
  |
  v
FastAPI modular monolith
  |
  +---- PostgreSQL/PostGIS
  |
  +---- Object storage
  |
  +---- asynchronous/batch jobs

External source systems
  |
  v
Source discovery and ingestion
  |
  +---- immutable source snapshot
  |
  +---- validation
  |
  +---- product-specific adapter
  |
  v
Canonical application state
```

## Current preferred production provider

The current preferred V1 candidate is Google Cloud Platform in the Santiago
region.

Proposed managed components:

- Cloud Run for the FastAPI application;
- Cloud SQL for PostgreSQL with PostGIS;
- Cloud Storage for private source assets and generated artifacts;
- Cloud Run Jobs for ingestion and long-running processing;
- Cloud Scheduler when scheduled execution becomes necessary;
- Secret Manager for production credentials;
- Cloud Monitoring / Logging for operational visibility;
- GitHub Actions for CI/CD.

This provider decision remains **Proposed** until the infrastructure ADR is
accepted and the cost/operational assumptions are reviewed.

**OPEN QUESTION** (2026-09-01) — `docs/adr/ADR-004-revisit-production-cloud-provider-choice.md`
(also Proposed) now proposes Microsoft Azure (Chile Central region, Entra ID
identity, Container Apps Jobs with Azure Batch escalation) as a competing
candidate, based on newly-confirmed Azure regional parity with GCP in
Santiago and Campo Digital's existing Microsoft/OneDrive ecosystem. See
`docs/research/2026-09-01-platform-runtime-infrastructure-study.md` for the
full comparison. Neither candidate is accepted; do not provision either.

## Database strategy

Start with one managed PostgreSQL/PostGIS instance.

Do not create independent database servers for LiDAR, Forestry, and Transelec
without an operational reason.

Logical ownership must nevertheless remain explicit:

```text
platform
forestry
transelec
lidar
```

The first Git-tracked migration now ensures PostGIS and establishes an empty
`platform` schema. Product schemas and business tables remain unimplemented
until their domain requirements are established.

## Object-storage strategy

PostgreSQL must not contain large LAS/LAZ files, source ZIP archives, workbook
binaries, imagery, or generated export packages.

Object storage will hold:

- immutable source snapshots;
- LAS/LAZ;
- Shapefile/GeoPackage packages;
- Excel workbooks;
- images;
- PDFs;
- generated HTML;
- reports;
- generated GIS exports.

The database stores metadata, provenance, current state, processing state, and
references to these objects.

## Application execution

Normal HTTP operations remain in FastAPI.

Long-running or resource-intensive work must execute outside the request
lifecycle.

Examples include:

- LiDAR processing;
- large GIS conversion;
- ingestion;
- report generation;
- artifact generation.

A persistent queue, Redis, Celery, or message broker must not be introduced
until actual workload/concurrency requirements justify one.

## Environments

### Local

- source access through the read-only synchronized OneDrive mirror;
- application services locally;
- local PostgreSQL/PostGIS through the pinned Docker Compose service;
- a separate disposable PostgreSQL/PostGIS service for destructive tests;
- no dependency on production infrastructure for normal development.

### Staging

Introduce only when integration/deployment testing requires a shared
environment.

Do not copy unrestricted private production data into staging.

### Production

Managed cloud services, isolated credentials, explicit database migrations,
backups, monitoring, and access controls.

## Non-goals for V1

Do not introduce by default:

- Kubernetes;
- microservices;
- Redis;
- Celery;
- Kafka/RabbitMQ;
- multiple production PostgreSQL servers;
- self-managed PostgreSQL on a VPS;
- automatic destructive source synchronization;
- infrastructure complexity solely for hypothetical future scale.

## Related documents

- [Source ingestion](source-ingestion.md)
- [Client data organization](client-data-organization.md)
- [Managed production platform ADR](../adr/ADR-001-managed-production-platform.md)
- [Infrastructure provider research](../research/2026-08-27-infrastructure-provider-study.md)
