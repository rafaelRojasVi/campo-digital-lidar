# Platform Runtime Infrastructure Study — 2026-09-01

**Status:** Research — non-canonical. This document is evidence gathered to
inform a production architecture decision; it is not itself an accepted
decision. See `../adr/ADR-001-managed-production-platform.md` (Proposed,
2026-08-27, GCP-leaning) and the new `../adr/ADR-004-revisit-production-cloud-provider-choice.md`
(Proposed, this study) for the decision record. Canonical architecture intent
remains `../platform/production-platform-v1.md`.

This study independently re-verifies current provider capabilities rather
than assuming the 2026-08-27 snapshot (`2026-08-27-infrastructure-provider-study.md`)
is still correct. It also incorporates real measured local workload evidence
gathered in this same work session (see "Measured local workload" below),
which the 2026-08-27 snapshot did not have.

All claims below are labeled:

- **FACT** — verified against current official provider documentation or an
  official pricing API, with a source URL and access date.
- **STRONG INFERENCE** — a conclusion that follows directly from FACTs above
  it, but is not itself independently sourced.
- **HYPOTHESIS** — a plausible claim not yet verified; treat as unconfirmed.
- **OPEN QUESTION** — genuinely unresolved; do not act on it without further
  verification.

Research was performed by three independent research passes (GCP; Azure;
AWS+Supabase), each using live web search and official documentation fetches
on 2026-09-01. Where a pricing calculator page rendered only client-side
JavaScript and could not be read as text, this is stated explicitly rather
than substituting a remembered or estimated figure.

---

## Measured local workload (ground truth for this study)

Gathered earlier in this same session from the real local `CAMPO_DIGITAL_SOURCE_ROOT`
corpus (read-only; see the session's ground-truth investigation). Restated
here because it is the basis for every "does this fit?" judgment below.

| Product | Format | Measured size | Notes |
|---|---|---|---|
| LiDAR | `.las` | 315.13 MB, 9,718,909 points, LAS 1.2, point format 3 | Only one LAS file exists in the entire corpus today (n=1). No CRS encoded. No wall-clock/peak-RSS benchmark of a full cubicación pipeline run exists yet — only header/bounds inspection and a prior full `pdal info --stats` pass have been run. |
| Forestry | `.zip` (shapefile family) | 2.57 MB compressed, ~5.9 MB uncompressed, 8 members | Only one client folder populated (n=1). |
| Transelec | `.xlsx` | 14.99 MB | One internal worksheet expands to ~150 MB of uncompressed XML — parsing cost is dominated by that one sheet, not the compressed file size. |

**LIMITATION** — this is a very small, early corpus (n=1 per product).
"Largest observed" is a lower bound on future file sizes, not a confirmed
maximum. Every compute-fit judgment below is qualified against a stated
"low single-digit GB" plausible future LiDAR file size, which is itself a
HYPOTHESIS, not a measured fact.

**FACT** (this session, same corpus) — a 16 KB read of the LiDAR file over
the OneDrive-mirror mount (`/mnt/c/...` from WSL2) took ~99 seconds of
wall-clock latency on first touch, dominated by OneDrive on-demand fetch
behavior, not CPU/memory. This reinforces the existing platform decision
that OneDrive must not be read repeatedly during processing — content must
be snapshotted into object storage once, then processed from there.

---

## Provider findings

### GCP (`southamerica-west1`, Santiago)

- **FACT** — Santiago is a real GCP region, `southamerica-west1`, 3 zones,
  launched 2021. Source: https://cloud.google.com/about/locations (accessed 2026-09-01).
- **FACT** — Cloud Run and Cloud Run Jobs are available in `southamerica-west1`.
  Source: https://docs.cloud.google.com/run/docs/locations.
- **FACT** — Cloud Tasks is **not** available in `southamerica-west1` — only
  `southamerica-east1` (São Paulo) among South American regions. Source:
  https://docs.cloud.google.com/tasks/docs/locations. This independently
  reinforces (beyond stylistic preference) the platform's existing decision
  to use a PostgreSQL-native job queue rather than Cloud Tasks: using Cloud
  Tasks from a Santiago-hosted app would mean a cross-region dependency.
- **FACT** — Cloud Run Jobs: max task timeout 168 hours (7 days, default 10
  minutes; GPU tasks capped at 1 hour); max 8 vCPU / 32 GiB memory per task;
  writable filesystem is in-memory, bounded by the configured memory (up to
  32 GiB) — there is no separate persistent-disk quota. Source:
  https://docs.cloud.google.com/run/quotas, https://docs.cloud.google.com/run/docs/configuring/task-timeout.
- **STRONG INFERENCE** — against the measured LiDAR file (315.13 MB), Cloud
  Run Jobs' 32 GiB ceiling gives roughly 100x headroom today. For a
  hypothetical future "low single-digit GB" file, the ceiling still
  comfortably fits unless a full-pipeline run turns out to need a >10-15x
  memory multiplier over raw file size — that multiplier is unmeasured
  (OPEN QUESTION), so this should be benchmarked before relying on it for
  the largest anticipated files, but the ceiling itself is generous.
- **FACT** — Cloud SQL for PostgreSQL supports versions 9.6–18 (18 default);
  PostGIS is bundled per major version (3.5.2 for PG13–17). Source:
  https://docs.cloud.google.com/sql/docs/postgres/db-versions,
  https://docs.cloud.google.com/sql/docs/postgres/extensions.
- **FACT** — Cloud SQL HA (regional) bills double the compute+storage of a
  standalone (zonal) instance. Source: Cloud SQL HA documentation.
- **FACT** — Cloud Storage: max object size 5 TiB; resumable upload API is
  standard; signed URLs valid up to 7 days (service-account-signed). Source:
  https://docs.cloud.google.com/storage/docs/uploads,
  https://docs.cloud.google.com/storage/docs/access-control/signed-urls.
- **FACT** — Identity Platform supports federating with any OIDC-discovery-
  compliant provider, which includes Microsoft Entra ID. This is a distinct
  mechanism from GCP's "Workforce Identity Federation" (which federates
  *employees* into GCP console/IAM access, not application end users) — a
  real point of potential confusion worth flagging explicitly. Source:
  https://docs.cloud.google.com/identity-platform/docs/web/oidc.
- **FACT** — Google's own guidance recommends Workload Identity Federation
  (short-lived OIDC-derived credentials) over long-lived service-account
  JSON keys for GitHub Actions → GCP deployment; the `google-github-actions/auth`
  action is the mature, actively maintained mechanism. Source:
  https://cloud.google.com/blog/products/identity-security/enabling-keyless-authentication-from-github-actions.
- **OPEN QUESTION** — exact Santiago-region Cloud SQL and Cloud Storage unit
  prices. The official pricing calculator pages render via client-side
  JavaScript and did not yield extractable numbers in this session; only US
  region examples and Cloud Tasks/Secret Manager (which have static pricing
  pages) were directly verified. Third-party trackers suggest a 20–40%
  South-America regional premium over `us-central1`, but this is not
  first-party sourced and must not be treated as fact.

### Azure (`chilecentral`, Santiago)

- **FACT** — Chile Central is a live, generally-available Azure region with
  3 availability zones (secondary-sourced GA date ~June 2025 — treat the
  exact date as INFERENCE, not primary-source FACT). Confirmed via the
  official **Azure Retail Prices API** (`prices.azure.com`) returning real,
  non-placeholder pricing for `armRegionName=chilecentral` across Azure
  Database for PostgreSQL Flexible Server (132 SKUs), Blob Storage (743
  SKUs), Container Apps (16 meters), Key Vault, and Azure Monitor. This is
  the single most consequential new fact in this study relative to the
  2026-08-27 snapshot: **Azure now has genuine regional parity with GCP in
  Santiago**, which was not established previously.
- **FACT** — Azure Database for PostgreSQL Flexible Server supports versions
  11–18 (18 current); PostGIS 3.6.1 is available for PG16 (plus companion
  extensions). Source: https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-supported-versions,
  https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-by-engine.
- **FACT** — Real Chile Central pay-as-you-go prices (Azure Retail Prices
  API, accessed 2026-09-01, USD): Burstable B1ms $0.0238/hr; General
  Purpose Ddsv5 2 vCore $0.2492/hr, 4 vCore $0.4984/hr; Premium SSD storage
  $0.161/GiB-month; backup storage (beyond included allowance) $0.133/GB-month.
- **FACT** — Zone-redundant HA bills full compute+storage for both primary
  and standby (roughly doubles cost), consistent with GCP's equivalent
  mechanism.
- **FACT** — Blob Storage, Chile Central, Hot LRS: $0.02576/GB-month
  (tiered down to $0.023699 at volume); Block Blob max size ~190.7 TiB (via
  4,000 MiB × 50,000 blocks). SAS tokens support direct browser-to-storage
  upload; Microsoft's current guidance recommends **user delegation SAS**
  (Entra-ID-secured) over account-key SAS for exactly this pattern. Source:
  Azure Retail Prices API; https://learn.microsoft.com/en-us/azure/storage/blobs/scalability-targets;
  https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview.
- **FACT** — Container Apps Jobs (Consumption): 0.25–4 vCPU / 0.5–8 GiB per
  replica; ephemeral storage scales with vCPU and caps at **8 GiB at >1
  vCPU** — this is a hard ceiling with no larger Consumption tier; job
  timeout defaults to 30 minutes, configurable up to 24 hours. GPU Dedicated
  profiles exist only in West US 3 and North Europe (not Chile Central).
  Source: https://learn.microsoft.com/en-us/azure/container-apps/containers,
  https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts.
- **STRONG INFERENCE** — against the measured LiDAR file (315 MB), Container
  Apps Jobs comfortably fits today. For a hypothetical future "low
  single-digit GB" file, the **8 GiB ephemeral-storage ceiling is the
  tightest constraint of any provider evaluated in this study** — it is a
  genuine, documented limitation, not a guess. Azure Batch (VM-level,
  same-cloud) is the documented escalation path when a job's scratch-disk
  or runtime needs exceed Container Apps Jobs' ceiling.
- **OPEN QUESTION** — Azure Batch's availability specifically in Chile
  Central returned zero pricing rows in the Retail Prices API query (Batch
  has no separate service fee and rides on VM pricing, which does not
  conclusively prove unavailability, but was not positively confirmed
  either).
- **FACT** — Microsoft Entra ID app-registration OIDC/OAuth2 sign-in with
  app-role claims works on the **Free tier** — P1 ($7/user/month) and P2
  ($10/user/month) are only required for Conditional Access, Identity
  Protection, and PIM, not for basic authenticated sign-in with roles.
  Source: https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app;
  https://www.microsoft.com/en-us/security/business/microsoft-entra-pricing.
- **FACT** — Microsoft Graph application (unattended, non-delegated)
  permissions such as `Files.Read.All` support a scheduled backend job
  pulling OneDrive/SharePoint content without a signed-in user present, via
  client-credentials flow. Per-app-per-tenant throttling ceilings (1,250–
  6,250 resource units/minute, up to 400 GB/hour) are far above Campo
  Digital's plausible scan frequency, provided the implementation follows
  Microsoft's documented delta-query "scanning application" guidance rather
  than naive full re-scans. Source:
  https://learn.microsoft.com/en-us/sharepoint/dev/general-development/how-to-avoid-getting-throttled-or-blocked-in-sharepoint-online.
- **FACT** — Microsoft's own current documentation explicitly labels
  long-lived service-principal secrets "(Not recommended)" for GitHub
  Actions → Azure, and presents OIDC federated credentials first, with
  mature tooling (`azure/login@v2`). Source:
  https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect.
- **FACT** (real cost model, Chile Central, pay-as-you-go, built from the
  verified unit prices above):
  - **PILOT** (5–10 users, ~10 GB, occasional LiDAR job): Postgres Burstable
    B1ms + 32 GiB storage ≈ $23/mo; Blob (10 GB) ≈ $1/mo; Container Apps
    (one small always-on API replica + occasional job, within the documented
    free monthly grant of 180,000 vCPU-sec/360,000 GiB-sec/2M requests) ≈
    $20/mo; Key Vault + Entra Free ≈ <$1/mo. **Total ≈ $45–55/month.**
  - **PRODUCTION V1** (5–30 users, several concurrent small jobs, backups):
    Postgres General Purpose D2ds_v5 + 100 GiB storage + 100 GB backup ≈
    $211/mo (≈ $393/mo with zone-redundant HA); Blob ≈ $6/mo; Container Apps
    ≈ $52/mo; Key Vault ≈ $1/mo. **Total ≈ $270/month (≈ $450/month with HA).**
  - **GROWTH** (50–200 users, 500 GB–1 TB, multiple concurrent processors):
    Postgres General Purpose 8 vCore + 500 GiB storage + 500 GB backup ≈
    $875/mo (≈ $1,600/mo with HA); Blob ≈ $40/mo; Container Apps ≈ $243/mo;
    Key Vault + egress ≈ $12–17/mo. **Total ≈ $1,170/month (≈ $1,900/month with HA).**

  These figures are built from directly-verified Azure Retail Prices API
  unit prices, not a marketing calculator — they are the most trustworthy
  cost figures in this entire study, though the job-related line items still
  assume no benchmarked LiDAR pipeline resource profile (that remains an
  open question regardless of provider).

### AWS (`sa-east-1`, São Paulo)

- **FACT** — AWS has no Chile region. `sa-east-1` (São Paulo) is the nearest,
  confirmed available for ECS/Fargate, S3, Cognito, Secrets Manager, and AWS
  Batch via AWS's own endpoints/quotas pages. Source:
  https://docs.aws.amazon.com/general/latest/gr/ecs-service.html and
  sibling pages for each service.
- **OPEN QUESTION** — no official AWS page states a specific Santiago↔São
  Paulo latency number or a standardized sa-east-1 price premium; do not
  treat third-party claims of "10–30% higher" as fact.
- **FACT** — ECS Fargate: **no maximum task execution duration** (unlike
  Cloud Run Jobs' 7-day cap or Container Apps Jobs' 24-hour cap); up to 16
  vCPU / 120 GB memory per task; ephemeral storage default 20 GiB, **up to
  200 GiB configurable**. GPU is **not supported on Fargate** — GPU
  workloads require ECS/EKS-on-EC2. Source:
  https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-quotas.html,
  .../fargate-task-storage.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu-specifying.html.
- **STRONG INFERENCE** — of the three cloud providers evaluated, **Fargate's
  ceilings (no timeout cap, up to 200 GiB ephemeral storage) are the most
  generous for the LiDAR compute workload specifically**, with the largest
  margin against the stated "low single-digit GB, unconfirmed upper bound"
  future-file uncertainty. This is a genuine, evidence-based advantage for
  AWS on the narrow "LiDAR compute suitability" axis alone.
- **FACT** — S3 multipart upload: 5 MB–5 GB per part, up to 10,000 parts,
  max object size ~5 TiB (console) / 48.8 TiB (API); presigned URLs are
  standard for direct browser-to-S3 upload. Source:
  https://docs.aws.amazon.com/general/latest/gr/s3.html.
- **FACT** — Cognito brokers Microsoft Entra ID as an external OIDC
  provider, presenting Cognito-issued JWTs to the backend regardless of
  upstream IdP. Source:
  https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-identity-federation.html.
  This is one extra managed layer compared to GCP/Azure's more direct
  OIDC-to-Entra paths.
- **FACT** — GitHub's own documentation and AWS IAM guidance both describe
  OIDC federation (short-lived STS credentials via a trust policy) as the
  current recommended pattern over long-lived IAM access keys. Source:
  https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services.
- **OPEN QUESTION** — exact sa-east-1 RDS/S3/Fargate unit pricing; the
  official pricing calculator pages did not render as text in this session.
  Only cost *drivers* (RDS instance-hour + Multi-AZ = 2x, S3 storage/egress,
  Fargate per-vCPU/GB-second) are established; absolute dollar totals for
  the three scenarios are directional, not verified, and materially less
  trustworthy than the Azure figures above.

### Supabase

- **FACT** — São Paulo (`sa-east-1`) is Supabase's only South American
  region option. Source: https://supabase.com/docs/guides/platform/regions.
- **FACT** — PostGIS is supported (dashboard-enabled extension). Source:
  https://supabase.com/docs/guides/database/extensions/postgis.
- **FACT** — Compute add-on tiers range $10–$3,730/month (Micro 1 GB RAM to
  16XL 256 GB RAM); Supavisor pooler offers session mode (port 5432) and
  transaction-mode-only (port 6543, since 2025-02-28). Source:
  https://supabase.com/pricing.
- **STRONG INFERENCE** — a `SELECT ... FOR UPDATE SKIP LOCKED` job-claim
  query is a single self-contained statement inside one transaction, so it
  is compatible with Supavisor's transaction-mode pooling in principle —
  but no Supabase document explicitly certifies this exact pattern
  (OPEN QUESTION).
- **FACT** — Supabase Storage supports the TUS resumable-upload protocol,
  with per-file limits raised to up to 500 GB on paid plans — comfortably
  covers the measured/plausible LiDAR file sizes. Source: Supabase Storage
  documentation and pricing page.
- **FACT — the decisive limitation** — Supabase Edge Functions have a
  400-second wall-clock execution limit and 200ms active-CPU-time limit;
  there is no first-party Supabase product for arbitrary long-running
  background compute. Source: https://supabase.com/docs/guides/functions/limits.
  **Supabase cannot run the LiDAR/Forestry/Transelec processing jobs
  itself** — it would need to be paired with an external compute provider
  (e.g. AWS Fargate) for that piece specifically, which contradicts its
  core "minimal-ops single-vendor" value proposition for a platform that
  has genuine heavy-compute needs.
- **STRONG INFERENCE** — this confirms and sharpens ADR-001's prior
  "Supabase — no full compute story" rejection with concrete numbers
  (400-second hard cap) rather than a general impression.

---

## Decision-criteria scoring

Scored against the 19 criteria in the task brief. `+` favorable, `~`
neutral/acceptable, `-` unfavorable, `?` open question / unverified.

| Criterion | GCP (Santiago) | Azure (Chile Central) | AWS (São Paulo) | Supabase |
|---|---|---|---|---|
| 1. Chile latency | + (in-region) | + (in-region) | ~ (São Paulo, one hop) | ~ (São Paulo, one hop) |
| 2. PostGIS maturity | + (bundled, PG13–17) | + (bundled, PG16 confirmed) | + (bundled) | + (bundled) |
| 3. Large file ingestion | + | + | + | ~ (needs external compute anyway) |
| 4. Resumable/multipart upload | + | + | + | + (TUS) |
| 5. Object storage | + (5 TiB objects) | + (~190 TiB objects) | + (~48.8 TiB objects) | + (500 GB/file paid tier) |
| 6. LiDAR compute suitability | + (32 GiB/7-day ceiling) | ~ (8 GiB ephemeral ceiling on Consumption is the tightest of the three clouds) | ++ (no timeout, 200 GiB ephemeral) | - (no compute product) |
| 7. Max job CPU/RAM/runtime | + | ~ (24h cap, 8GiB ephemeral) | ++ (no cap) | - |
| 8. Scaling to simultaneous files | + | + | + | ~ (compute is external) |
| 9. OneDrive/Graph integration | ~ (works, no home-field advantage) | ++ (native ecosystem fit) | ~ (works, no home-field advantage) | ~ |
| 10. Auth / Entra compatibility | + (direct OIDC) | ++ (native, Free tier sufficient) | + (via Cognito broker) | + (direct OIDC) |
| 11. Backups | + | + | + | + |
| 12. Observability | + | + | + | ~ (less mature than hyperscaler tooling) |
| 13. Security | + | + | + | + |
| 14. Solo-dev operational burden | + | + | + | ++ (least infra to manage, but see #6/#7) |
| 15. Monthly idle cost | ? (unverified exact numbers) | + (verified: ~$45–55/mo pilot) | ? (unverified exact numbers) | + (Free tier exists but unsuitable at real scale) |
| 16. Pay-per-processing cost | ? | + (verified unit prices) | ? | n/a (no compute product) |
| 17. Future growth | + | + (Batch escalation path) | ++ (Fargate headroom, EC2/Batch beyond) | - (hard ceiling, needs pairing) |
| 18. Vendor lock-in | ~ | ~ | ~ | - (compute must live elsewhere regardless) |
| 19. Local→production adapter mapping | + (ObjectStore/JobExecutor abstractions already local-cloud-neutral) | + | + | ~ |

---

## LiDAR execution decision rule

Per the task brief's own framing:

> If runtime, RAM, CPU, and scratch disk fit comfortably inside serverless-job
> limits: use serverless job compute. Otherwise use Batch / VM-backed
> execution.

Applying that rule with the verified numbers above, **independent of which
provider is chosen for the rest of the platform**:

- **On GCP**: Cloud Run Jobs (32 GiB memory/disk, 7-day timeout) fits the
  measured workload comfortably today and has generous headroom for
  plausible near-future growth. Escalate to GCP Batch only if a benchmarked
  pipeline run exceeds 32 GiB or needs GPU beyond the 1-hour Cloud-Run-GPU
  cap.
- **On Azure**: Container Apps Jobs fits the measured workload today, but
  its 8 GiB ephemeral-storage ceiling (Consumption profile) is the tightest
  margin of any option studied. **Recommendation if Azure is chosen: treat
  Container Apps Jobs as the default, but benchmark the real cubicación
  pipeline's peak scratch-disk usage before committing any file class above
  ~1 GB to it — route anything that doesn't comfortably fit to Azure Batch**
  (same cloud, VM-level control, larger disks), keeping the `ExecutionBackend`
  abstraction the platform already designed (`LocalWorker` /
  `ContainerAppsJob` / `Batch-VM`) exactly as intended for this purpose.
- **On AWS**: Fargate (no timeout, up to 200 GiB ephemeral) fits essentially
  any file size this platform is likely to see for the foreseeable future
  without needing to escalate to Batch/EC2 at all, except for a genuine
  future GPU requirement.

This rule should be re-run with real benchmark numbers (wall-clock, peak
RSS, peak scratch-disk usage for one full cubicación pipeline execution on
the current 315 MB file, then again on the largest file available at the
time) before any production commitment — no such benchmark exists yet
(OPEN QUESTION, inherited from the 2026-08-27 roadmap LIMITATION).

---

## Recommendation

**Proposed (not accepted): Azure, with Chile Central as the primary region,
Microsoft Entra ID as the identity provider, Azure Database for PostgreSQL
Flexible Server + PostGIS, Blob Storage, and Container Apps Jobs for async
processing — with Azure Batch as the explicit, same-cloud escalation path
for any job that a real benchmark shows exceeds Container Apps Jobs'
ceilings.**

This is a change from the prior 2026-08-27 snapshot's GCP lean and from
ADR-001's current "Proposed" GCP direction. The evidence supporting the
change:

1. **Regional parity is no longer a GCP-only advantage.** The 2026-08-27
   snapshot could not have known Azure's Chile Central region reached GA
   (~June 2025) — both GCP and Azure now have genuine in-region hosting for
   Santiago-based users, closing what was previously GCP's clearest
   differentiator.
2. **Campo Digital's actual current source-of-truth is OneDrive/Microsoft
   365.** Azure's OneDrive/Graph and Entra ID integration is a structural
   home-field advantage, not a marketing claim: application-permission
   Graph access for unattended scheduled ingestion is mature and generously
   throttled, and Entra ID provides authenticated sign-in with role claims
   on its **Free tier** — no paid identity tier is required for what this
   platform needs. GCP and AWS can both integrate with Entra ID as an OIDC
   provider, but neither has this ecosystem-native fit.
3. **Azure's pricing is the most trustworthy of the three clouds studied
   here**, because it was verifiable against Microsoft's own public Retail
   Prices API rather than a JavaScript-rendered calculator — this
   materially reduces budgeting risk for a solo-developer-operated
   platform, independent of which number is actually lowest.
4. **The one real technical weakness — Container Apps Jobs' 8 GiB ephemeral
   ceiling — is honestly weaker than GCP's Cloud Run Jobs (32 GiB) and much
   weaker than AWS Fargate (200 GiB, no timeout) on the narrow "LiDAR
   compute headroom" axis.** This is not dismissed: it is why the
   recommendation explicitly pairs Container Apps Jobs with an Azure Batch
   escalation path (same cloud, low added operational burden) rather than
   claiming Container Apps Jobs alone is sufficient indefinitely.

**Why not AWS**, despite having the best raw compute ceiling for LiDAR: AWS
has no Chile region at all (nearest is São Paulo, same as Azure's fallback
and Supabase's only region), no OneDrive/Graph home-field advantage, and
requires Cognito as an extra broker layer for Entra ID federation rather
than a direct integration. AWS's compute-ceiling advantage matters most for
a hypothetical future multi-GB-per-file LiDAR scale that is not yet
confirmed to exist (today's one measured file is 315 MB); it does not
outweigh Azure's ecosystem and identity fit for this platform's actual
current shape. **A hybrid ("Azure/GCP for the platform, AWS Fargate purely
for LiDAR jobs") was considered and rejected for now**: it would add
genuine multi-cloud operational complexity (a second cloud account,
second CI/CD credential path, cross-cloud network egress for job dispatch)
for a benefit that is currently speculative rather than measured. Revisit
this specifically if/when a real benchmark shows a file class that
Container Apps Jobs and Azure Batch both cannot handle.

**Why not GCP**, given it is close: GCP remains a fully viable second choice
— it has in-region hosting, a more generous serverless-job compute ceiling
than Azure, and workable Entra ID federation. It loses to Azure here
specifically on ecosystem fit (#9/#10 in the criteria table) and on pricing
verifiability (#15/#16), not on any disqualifying technical defect. If a
future benchmark reveals the LiDAR pipeline needs Cloud-Run-Jobs-class
headroom that Azure genuinely cannot provide even via Batch, GCP is the
natural fallback, not AWS or Supabase.

**Why not Supabase**: confirmed unsuitable as the *sole* platform — no
product for the LiDAR/Forestry/Transelec processing jobs themselves
(Edge Functions cap at 400 seconds). It remains worth reconsidering only as
a possible database/auth/storage layer paired with external compute, but
that combination does not reduce operational complexity relative to a
single hyperscaler and was not pursued further here.

This recommendation should be recorded as a **Proposed** update
(`ADR-004`), not an accepted change to ADR-001, pending team review and the
outstanding pipeline benchmark.

---

## Open questions carried forward

- No wall-clock/peak-RSS/peak-scratch-disk benchmark of a full cubicación
  pipeline run exists on any provider. This is the single most important
  missing data point for validating the LiDAR execution decision rule above
  — it should be run locally first (cheap), then, if a production
  commitment is imminent, on the actual chosen provider's job compute.
- Exact GCP and AWS unit pricing for the relevant South American regions
  could not be verified in this session (JS-rendered calculators); only
  Azure's figures are pricing-API-verified. Before final budget commitment,
  either re-attempt GCP/AWS pricing verification with a tool that can
  execute their calculator JavaScript, or request a quote/use each
  provider's billing support channel.
- Azure Batch's exact availability in Chile Central was not positively
  confirmed (zero pricing rows returned, which is inconclusive given Batch
  has no separate service fee).
- The real upper bound on future LiDAR file size is unknown — the current
  corpus has exactly one LAS file. This should be revisited as soon as
  Campo Digital's actual LiDAR-classified OneDrive path is confirmed
  (`config/source-catalog.yaml` currently lists it as unconfirmed) and more
  files become available to measure.
- No production identity-provider decision has been made by the team;
  Entra ID's Free-tier sufficiency for this platform's basic auth needs is
  a real finding but still requires a human decision to adopt.
