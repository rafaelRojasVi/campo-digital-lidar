# ADR-004 — Revisit production cloud provider choice

## Status

Proposed. Does not supersede ADR-001 yet; both remain open pending team
review. Neither GCP nor Azure provisioning is authorized by this ADR.

## Context

ADR-001 (2026-08-27, Proposed) leaned toward GCP Santiago
(`southamerica-west1`) based on the research snapshot in
`../research/2026-08-27-infrastructure-provider-study.md`. That snapshot did
not have, and could not have had, confirmation that Microsoft Azure's Chile
Central region (`chilecentral`) had reached general availability — this is a
new fact established in `../research/2026-09-01-platform-runtime-infrastructure-study.md`.

Since ADR-001, the platform has also gained a concrete local ingestion/
access foundation whose design already anticipates provider-neutral
`ObjectStore` and `ExecutionBackend` abstractions, and real measured local
workload evidence (one LiDAR file at 315.13 MB / 9,718,909 points, one
Forestry ZIP at 2.57 MB, one Transelec XLSX at 14.99 MB with a 150 MB
uncompressed internal sheet) that did not exist when ADR-001 was written.

The 2026-09-01 research independently re-verified current GCP, Azure, AWS,
and Supabase capabilities against official documentation and, where
possible, official pricing APIs (Azure's Retail Prices API returned real,
verifiable numbers; GCP and AWS pricing calculators did not render as
fetchable text and remain largely unverified for exact dollar figures).

Key findings from that research, in brief:

- Azure Chile Central now offers genuine regional parity with GCP Santiago
  for the services this platform needs (Postgres+PostGIS, blob/object
  storage, container-based job compute, secrets, monitoring).
- Campo Digital's actual current source-of-truth is OneDrive/Microsoft 365;
  Azure's Entra ID and Microsoft Graph integration is a structural
  home-field advantage for this specific platform, not a generic feature
  checkbox — including Entra ID's Free tier being sufficient for this
  platform's basic authenticated-sign-in-with-roles needs.
- Azure Container Apps Jobs' ephemeral-storage ceiling (8 GiB at >1 vCPU on
  the Consumption profile) is measurably tighter than GCP Cloud Run Jobs
  (32 GiB) and much tighter than AWS Fargate (up to 200 GiB, no execution
  timeout) — a real, documented weakness, not dismissed by this proposal.
- Supabase remains unsuitable as the sole platform: its research confirmed,
  with a specific number (Edge Functions' 400-second execution cap), the
  "no full compute story" rejection already recorded informally in prior
  research.

## Decision (proposed)

Propose Azure — Chile Central region, Microsoft Entra ID for identity,
Azure Database for PostgreSQL Flexible Server with PostGIS, Blob Storage,
and Container Apps Jobs for async processing, with Azure Batch as the
explicit same-cloud escalation path for any job a real benchmark shows
exceeds Container Apps Jobs' ceilings — as the leading candidate, ahead of
GCP Santiago (ADR-001's current lean).

This proposal explicitly does **not**:

- Mark ADR-001 superseded or rejected. GCP remains a fully viable, closely
  scored second choice (see the decision-criteria table in the linked
  research), and this ADR does not have team sign-off yet.
- Authorize provisioning of any Azure resources.
- Claim the LiDAR compute question is settled. No benchmark of a full
  cubicación pipeline run (wall-clock, peak RSS, peak scratch-disk usage)
  exists on any provider yet — this is the single most important open
  question this proposal inherits, and it should be run before any
  production commitment, since it could change the LiDAR-compute-specific
  part of this recommendation regardless of which cloud is otherwise chosen.

## Rationale

See the full evidence, source citations, and decision-criteria scoring in
`../research/2026-09-01-platform-runtime-infrastructure-study.md`. In
summary: with genuine regional parity established, the deciding factors
become ecosystem fit (Microsoft/OneDrive/Entra, where Campo Digital already
lives) and pricing verifiability (Azure's Retail Prices API vs. GCP/AWS's
unrendered calculators) rather than raw infrastructure capability, where all
three major clouds are workable. The one genuine technical weakness
(Container Apps Jobs' ephemeral-storage ceiling) is addressed by pairing it
with Azure Batch rather than ignored.

## Consequences

If accepted, future infrastructure work should target Azure Chile Central
first. The platform's existing `ObjectStore` and `ExecutionBackend`-shaped
abstractions (local V1: `LocalObjectStore`, `PostgresLocalWorker`) should
gain Azure-specific implementations (`AzureBlobObjectStore`, a Container
Apps Jobs / Batch dispatcher) without any change to product-domain code,
per the platform's existing local→production adapter-boundary rule.

If this ADR is not accepted, ADR-001's GCP lean stands, and this document
remains a recorded, evidence-based dissenting proposal for future
reference — it should not be silently discarded, since the underlying
Azure-regional-parity fact will remain true regardless of which way the
team ultimately decides.

This ADR does not resolve until a team member with authority over
production infrastructure choice reviews it and either accepts it
(superseding ADR-001), rejects it (ADR-001 stands, this ADR moves to
Rejected with its reasoning preserved), or requests the outstanding LiDAR
benchmark before deciding.

## Update (2026-09-03) — scoped to the Transelec private pilot only

The Slice 8 task evaluated hosting for the first real private deployment —
a Transelec-only pilot for Javier, not the full multi-product platform —
and re-checked Render's current paid tier (not previously compared here,
since ADR-005 only evaluated Render's free staging tier).

- **The one real objection to Azure in this ADR — Container Apps Jobs'
  8 GiB ephemeral-storage ceiling — does not apply to this pilot.**
  Transelec's workload (`docs/superpowers/plans/
  2026-09-01-secure-file-access-slice-design.md`, `app.execution`) is
  synchronous XLSX row processing, not LiDAR point-cloud geometry; it needs
  no async batch job compute at all, let alone one near that ceiling. This
  removes Azure's only documented technical weakness for this specific,
  narrower deployment.
- Real Chile Central pricing for a pilot this size (Postgres Burstable
  B1ms + ~32 GiB storage, low-volume Blob Storage, one small Container
  Apps replica, Key Vault, Entra ID Free): **≈$45–55/month**, verified
  against the Azure Retail Prices API (see
  `docs/research/2026-09-01-platform-runtime-infrastructure-study.md`'s
  PILOT scenario) — likely toward the low end for Transelec alone, which
  needs less storage/compute than that platform-wide estimate (which
  includes occasional LiDAR jobs).
- **Render paid tier** (checked 2026-09-03, third-party-aggregated pricing
  since Render's own pricing page did not render as fetchable text —
  Postgres Starter ≈$7/month, web service Starter ≈$7/month, persistent
  disk ≈$0.25/GB/month) is the cheapest sticker price of any option
  considered, but has two real, unresolved weaknesses for this pilot: no
  South America region (still Oregon/Ohio/Virginia/Frankfurt/Singapore —
  Virginia remains the least-bad choice, per ADR-005's reasoning), and no
  true managed object-storage product — `app.object_store.ObjectStore`
  would map to a paid Disk instead of an S3/Blob/GCS-equivalent, a real
  architectural downgrade from every other candidate here. Not recommended
  as the pilot's primary provider; the cost gap does not offset those two
  weaknesses for data this platform explicitly must keep private and
  durable.

This update does not change this ADR's Proposed status or its
platform-wide recommendation — it only makes the case for Azure stronger
for the Transelec pilot specifically, and adds Render as a considered (and
rejected) candidate for that narrower decision. Acceptance is still
Rafael's decision.
