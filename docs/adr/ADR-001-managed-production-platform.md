# ADR-001: Managed Production Platform

## Status

Proposed.

**Note (2026-09-01):** `ADR-004-revisit-production-cloud-provider-choice.md`
(also Proposed) proposes Microsoft Azure as a competing candidate to the GCP
lean below, based on newly-confirmed Azure regional parity in Santiago. This
ADR's status and decision are unchanged pending review; see ADR-004 and
`../research/2026-09-01-platform-runtime-infrastructure-study.md`.

## Context

Campo Digital needs production infrastructure for:

- a FastAPI modular monolith;
- PostgreSQL/PostGIS;
- large private/geospatial source assets;
- scheduled ingestion;
- long-running processing;
- multiple product frontends;
- monitoring, backups, and secure credentials.

The primary users are expected to operate from Chile, while some stakeholders
may access the system internationally.

The engineering team is small, so operational simplicity is a major design
constraint.

A dated provider comparison is preserved in:

`../research/2026-08-27-infrastructure-provider-study.md`

## Decision

Use managed cloud infrastructure rather than a self-managed production VPS.

The current preferred V1 candidate is Google Cloud Platform in Santiago using:

- Cloud Run;
- Cloud SQL for PostgreSQL/PostGIS;
- Cloud Storage;
- Cloud Run Jobs;
- Secret Manager;
- Cloud Monitoring/Logging;
- GitHub Actions.

Do not provision this architecture until shared production access is required.

Continue local development without paid production infrastructure while
source-ingestion and persistence contracts are established.

## Rationale

This approach provides:

- managed PostgreSQL administration;
- PostGIS support;
- geographic proximity to primary users;
- container deployment compatible with the existing application;
- object storage suitable for large GIS/LiDAR assets;
- a separate execution model for batch processing;
- mature backup, monitoring, security, and secret-management facilities;
- a path to scale without requiring Kubernetes.

## Alternatives considered

### Render

Operationally simpler and a rational prototype option.

Not currently preferred for production because the provider comparison found
no South America deployment region and Campo Digital contains interactive GIS
and potentially large geospatial workloads.

Reconsider if simplicity proves substantially more valuable than measured
regional latency or if Render introduces an appropriate region.

### Railway

Excellent developer experience and low barrier to deployment.

Not currently preferred for the same geographic concern and because Campo
Digital's long-term data/processing requirements align more directly with a
full managed cloud platform.

### Supabase-based architecture

Strong PostgreSQL/PostGIS and rapid development capabilities.

Not selected as the complete infrastructure because compute-heavy LiDAR and
general batch processing still require another execution platform, increasing
multi-vendor architecture.

It remains a valid alternative if database/auth development speed becomes the
dominant requirement.

### AWS / Azure

Technically capable alternatives.

They remain candidates if organizational requirements, pricing, customer
contracts, existing accounts, or specific service capabilities justify a
change.

### Self-managed VPS

Rejected for production V1.

It would transfer operating-system maintenance, PostgreSQL administration,
backups, security patching, monitoring, and recovery responsibility to the
small engineering team.

## Consequences

Positive:

- reduced production operations burden;
- clear separation between collaboration, object storage, and canonical data;
- strong geospatial database support;
- independent batch-processing capability.

Negative:

- more initial cloud configuration than simplified PaaS platforms;
- provider-specific operational knowledge;
- some GCP lock-in around deployment and managed services;
- managed database cost even at low usage.

## Revisit when

Re-evaluate this ADR if any of the following becomes true:

- measured Chile latency no longer justifies regional hosting;
- infrastructure cost materially exceeds the agreed operating budget;
- workload is too small to justify managed-cloud complexity;
- LiDAR jobs exceed the chosen batch execution limits;
- customer/security requirements mandate another provider;
- another provider offers materially lower operational burden with equivalent
  data-safety and regional capabilities.
