# Secure File Access Slice — Design

## Status

Proposed. Approved in principle by the user on 2026-09-01, pending this
written spec's review.

## Purpose

The Render staging demo (ADR-005) proved the API/portal/Postgres stack
deploys, but exposed a real product gap: dev-auth identities are not
acceptable for real client files, `/ingesta` is an undiscoverable
engineering screen, and there is no path from "a file lives in Campo
Digital's OneDrive" to "it's in the ingestion pipeline" other than a manual
browser file picker.

This slice turns the platform from an engineering demo into a usable
private platform: real sign-in, a discoverable `Archivos` area, real
OneDrive browsing feeding the existing ingestion pipeline, and role-scoped
visibility — without provisioning paid infrastructure and without importing
real client binaries into Render's ephemeral storage.

## Non-goals (explicit)

- No Google Drive connector.
- No Microsoft Graph delta sync (roadmap Phase 7).
- No completion of product-module hosting.
- No production compute/provider decision (ADR-001/ADR-004 remain open).
- No paid Render resources.
- No import of real client OneDrive file *bodies* into Render's ephemeral
  object store (see "Ephemeral storage" below) — browsing and selecting
  real files is in scope; fetching their bytes into ingestion is
  feature-flagged off until durable object storage exists.

## 1. Identity and session model

### Revision (2026-09-01): Microsoft account model corrected

New evidence changed a prerequisite this section originally assumed. The
canonical Campo Digital OneDrive folder was opened directly and its URL
proves it is a **personal OneDrive** (`onedrive.live.com`, a `remoteItem`
shared from a different personal Microsoft account's `/personal/` drive
root into Rafael's own OneDrive as an added shared folder) — not a
SharePoint/Teams document library, and not hosted in any Microsoft 365
tenant. There is no Campo Digital Microsoft 365 tenant today, and the only
Entra directories Rafael currently sees (Institut Francais, University of
Brighton) are unrelated organizations he is a guest in, not a Campo Digital
tenant he can register an app under. The paragraphs below replace the
original single-tenant/Microsoft-365-tenant assumption; everything else in
this document (session hashing, token encryption, zero-grant bootstrap,
the intersection authorization rule in section 3) is unaffected.

### Entra ID app registration

- **Campo Digital needs its own dedicated Entra tenant** to own this app
  registration — not an unrelated existing tenant (Institut Francais,
  University of Brighton) and not a personal Microsoft account's implicit
  identity. A personal Microsoft account cannot create an Entra tenant
  directly; the practical, cheapest path is signing up for an **Azure free
  account** (requires phone verification and a non-prepaid credit/debit
  card for identity verification — a temporary authorization hold only, no
  recurring charge as long as no paid resources are provisioned), which
  automatically provisions a "Default Directory" Entra tenant on the
  **Microsoft Entra ID Free** tier with the signer as Global Administrator.
  That default tenant can be renamed (e.g. "Campo Digital") and is where
  the app registration lives. No Microsoft 365 subscription is required —
  Entra ID Free is sufficient for app registrations, delegated OAuth
  flows, and the bootstrap-admin config pair below.
- **Supported account types: "Accounts in any organizational directory
  (Any Microsoft Entra ID tenant) and personal Microsoft accounts."** Not
  single-tenant (the shared source material lives on a personal Microsoft
  account, so real Campo Digital users signing in with personal accounts
  must be supported today), and not "personal Microsoft accounts only"
  either — the wider option preserves a clean, no-re-registration path to
  real Campo Digital Microsoft 365 organizational accounts later, should
  Campo Digital ever adopt one, without narrowing what can sign in today.
  This choice only widens the identity-provider audience; it does not
  weaken Campo's own authorization posture — `app.access.can()` still
  denies every product action by default regardless of how someone
  authenticated (see "First-admin bootstrap" below and section 3).
- MSAL authority for this account-type combination is the `common`
  endpoint (`https://login.microsoftonline.com/common`), not an
  authority pinned to the app registration's home tenant ID — pinning to
  the home tenant would silently exclude personal accounts and any other
  organization's accounts. `ENTRA_TENANT_ID` is still recorded (the
  tenant that owns the app registration, used for admin-center reference
  and as one half of the bootstrap-admin match below), but it is no
  longer the authority segment.
- Confidential client (server-side authorization-code flow), so a client
  secret (or certificate) is required — stored the same way other
  production-candidate secrets are (local: ignored env file; Render:
  Render's environment variable store).

### Stable identity, never email

`platform.app_user` already generalizes identity via
(`identity_kind`, `identity_key`) — see `app.access_repository`. Entra
identities use:

```
identity_kind = "entra"
identity_key  = f"{tenant_id}:{oid}"   # both from the validated ID token
```

`oid` (object ID) is the stable, non-reassignable per-user identifier
Microsoft documents for this purpose; email/UPN can change (rename,
domain change) and must never be used as the identity key. `email` /
`display_name` are still stored on `app_user` as denormalized display
data, refreshed on each login, exactly as today.

Documented caveat for personal Microsoft accounts, not yet verified
against a real token: for a personal (MSA) sign-in through an app
registration that supports personal accounts, Microsoft's identity
platform reportedly issues `tid = 9188040d-6c67-4c5b-b112-36a304b66dad` —
a fixed, well-known placeholder shared by every personal-account sign-in,
not a per-organization tenant ID — while `oid` remains a per-user object
ID. `tid:oid` should still be collision-safe as an identity key (a
constant `tid` for all personal accounts, combined with an `oid` that is
itself already close to globally unique, does not introduce collisions
with real organizational tenants' `tid:oid` pairs), but this is an
inference from public documentation, not something this codebase has
observed. Task 6's discovery run must print the actual `tid`/`oid`
claims from a real sign-in and confirm this before Task 8 relies on it —
do not treat the shape above as settled without that confirmation.

### Two-step consent: sign-in vs. file access

A user who only needs to *view* Campo Digital must not be forced through
a OneDrive permission prompt. Two separate token acquisitions:

1. **Sign-in** — `openid profile` only (no Graph resource scopes). This is
   what every login does. It proves identity and nothing else.
2. **Graph file consent** — requested only when a user who holds an
   `UPLOAD`-capable grant (admin/operator on at least one product) opens
   the "Desde OneDrive" panel for the first time. This is a second,
   incremental authorization-code round trip (Microsoft identity platform
   supports incremental consent) requesting exactly the Graph scope
   decided in section 2. A viewer-only user never triggers this.

### Session storage: hash, not token

`platform.session` (new table, migration `0007`):

| column | notes |
|---|---|
| `id` | bigint identity PK |
| `session_secret_hash` | `sha256(raw_secret)`, unique, indexed |
| `app_user_id` | FK → `app_user.id` |
| `created_at`, `last_seen_at`, `expires_at` | timestamptz |

The cookie carries the raw, unguessable secret (`secrets.token_urlsafe`,
same generation as today's `DevSessionStore`). The server hashes the
incoming cookie value and looks up by hash — the raw secret is never
persisted, mirroring how the codebase would want an API key stored, and
meaning a DB read alone (e.g. a backup leak) cannot mint sessions. This
replaces `DevSessionStore`'s in-process dict for real identities; it also
happens to fix ADR-005's "session dies on every free-tier spin-down"
problem, since Postgres (unlike the local filesystem) survives Render's
ephemeral-instance cycling.

Dev-auth (`app.dev_auth`) keeps its existing in-process store — it is
**further restricted** to `APP_ENV == "development"` only (today it also
runs in `staging`; that is exactly the exposure this slice closes). Test
env keeps whatever `app.dev_auth` already allows for `pytest`.

### Microsoft tokens stored separately from sessions

`platform.ms_graph_grant` (new table, migration `0007`):

| column | notes |
|---|---|
| `id` | bigint identity PK |
| `app_user_id` | FK → `app_user.id`, unique |
| `access_token_encrypted`, `refresh_token_encrypted` | Fernet-encrypted bytes |
| `scope` | text, granted scope string |
| `expires_at` | timestamptz |
| `granted_at` | timestamptz |

Encrypted at rest with a symmetric key from `PLATFORM_TOKEN_ENCRYPTION_KEY`
(new env var; local: ignored env file, Render: environment variable —
no Secret Manager needed at this scale, consistent with "no paid
infrastructure unless necessary"). Never sent to the browser. Used only
server-side to make Graph calls on the user's behalf. New dependencies:
`msal` (Microsoft's own library — correctly implements PKCE, token
refresh, and cache; hand-rolling OAuth token refresh is exactly the kind
of place not to save a dependency) and `cryptography` (Fernet).

### First-admin bootstrap — explicit, not implicit

A fresh Entra login gets **zero product grants** by default — this is
the RBAC invariant `app.access.can()` already enforces (`None` role always
denies) and must not be quietly weakened.

Bootstrap is one explicit, reviewable config pair:

```
PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID
PLATFORM_BOOTSTRAP_ADMIN_OBJECT_ID
```

On login, if (and only if) the resolved identity's `(tid, oid)` exactly
matches this configured pair, and that identity currently holds **no**
grants at all, grant ADMIN on all three products once. This is a
narrow, one-time, config-driven seam — never "first login ever" and never
domain/email-based, both of which were explicitly rejected because they
create an implicit, unreviewable privilege-escalation path.

## 2. Source type discovery (must run before choosing a Graph scope)

### Revision (2026-09-01): source location is now confirmed as personal OneDrive

Opening the canonical Campo Digital folder directly (browser, URL
inspection) confirms `00 Hub Digital CampoDigital` is **not** a
SharePoint/Teams document library: it is a **personal** OneDrive
(`onedrive.live.com`) owned by a different personal Microsoft account,
appearing in Rafael's own OneDrive as an added shared folder — Graph
represents this as a `remoteItem` whose `parentReference.driveId`/`id`
point at the owner's drive, not Rafael's. This replaces the "most likely
SharePoint" framing the original spec and the tenant-admin handoff
document both carried; the decision tree below is narrowed accordingly,
and Step 0 must still run to get the exact stable IDs, but the drive-type
branch of the decision is no longer open.

Two further corrections from the same evidence pass:

- **Do not build discovery around `GET /me/drive/sharedWithMe`.**
  Microsoft has deprecated this endpoint; it already returns degraded
  results and is documented to stop returning data entirely after
  November 2026. It must not become a load-bearing part of Step 0.
- **Test the least-privilege route first, using the fact that the shared
  folder already appears as a `remoteItem` in Rafael's own OneDrive**,
  rather than searching for it: enumerate Rafael's own OneDrive root
  (`GET /me/drive/root/children`), find the child whose `remoteItem`
  facet is present, read `remoteItem.parentReference.driveId` +
  `remoteItem.id` from it, and enumerate that item's contents via
  `GET /drives/{drive-id}/items/{item-id}/children`. Public Microsoft
  Graph documentation states that delegated `Files.Read` (and
  `Files.ReadWrite`) on a **personal** Microsoft account "also grant
  access to files shared with the signed-in user" — i.e. `Files.Read`
  is documented to be sufficient for exactly this remoteItem shape, with
  no `.All` variant needed. Step 0 must still confirm this against a
  real token rather than trust the documentation alone; if delegated
  `Files.Read` genuinely proves insufficient against the real remoteItem
  (e.g. a 403 resolving the remote drive), only then escalate, and only
  to `Files.Read.All`, never straight to a broader/Sites-shaped
  permission that does not apply to a personal-OneDrive source.

**Step 0 of implementation** is a short, throwaway discovery script run
against a real Campo Digital sign-in (not client data, just Graph
metadata calls): request delegated `Files.Read` only, list
`/me/drive/root/children`, locate the `remoteItem`-shaped entry for
`00 Hub Digital CampoDigital`, and walk `children` from its resolved
`driveId`/`itemId`, to record the stable `driveId`/`itemId` Step 7
(`config/source-catalog.yaml`) needs.

Decision tree from that result (narrowed from the original three-way
split, since the drive type is now known; kept as a tree rather than a
single hard-coded scope because Step 0 must still verify it against a
real token, not assume it):

- **Personal OneDrive shared into the signing-in user's own OneDrive as a
  `remoteItem`** (the confirmed case here) → delegated `Files.Read` (not
  `.All`) — per the documented personal-account behavior above. This is
  the expected outcome; Step 0 exists to confirm it, not to choose among
  equally-likely branches.
- **Delegated `Files.Read` proves insufficient in the real Step 0 run**
  (e.g. Graph cannot resolve the remote drive/item with that scope) →
  escalate to delegated `Files.Read.All`, and record in the RESULT entry
  exactly what failed under `Files.Read` that justified the escalation.
- **SharePoint/Teams-backed document library** — ruled out by the URL
  evidence above; the `Sites.Selected` branch from the original spec is
  retained in the handoff document only as a documented fallback in case
  a *different* Campo Digital source later turns out to be
  SharePoint-backed, not as an expected outcome for this source.

Record the outcome (drive/site type, chosen scope, and the stable IDs) as
a short **RESULT** entry in `docs/source-systems/onedrive.md` once known
— this is exactly the kind of durable finding the documentation policy
asks to capture.

## 3. Server-side Graph authorization

Every OneDrive-sourced action must satisfy, server-side, the intersection
of:

```
Microsoft-accessible ∩ configured product source root ∩ Campo product grant
```

Concretely:

- **Microsoft-accessible**: every Graph call uses the signing-in user's
  own delegated token (never an app-only/client-credentials token), so
  Graph itself enforces what that person can see. No "act as the app"
  fallback.
- **Configured product source root**: `config/source-catalog.yaml` gains,
  once Step 0 resolves them, stable `drive_id`/`site_id` + root `item_id`
  per project (replacing the current `source_paths` human path strings for
  the Graph-backed lookup — paths remain for the local filesystem-mirror
  discovery, which is unaffected). The backend resolves a browsed/selected
  item's `parentReference` chain and rejects anything whose ancestry does
  not include the configured root `item_id` for that product. A client
  never gets to assert "this item belongs under product X" — the server
  proves it via Graph's own parent chain, the same trust posture
  `source_discovery._resolve_source_file` already applies to local
  filesystem paths (reject anything that doesn't verifiably resolve
  beneath the configured root).
- **Campo product grant**: the existing `Action.UPLOAD` check
  (`ensure_can`) for anything that would enter the ingestion pipeline;
  `Action.VIEW` for browsing.

Stable Graph IDs (`driveId`+`itemId`, or `siteId`+`itemId`) are used
throughout — never a human path string — because paths can be renamed
out from under a reference; IDs are what Graph itself treats as stable.

## 4. Portal: `Archivos`

`/ingesta` is renamed in the navigation to `/archivos` ("Archivos"),
linked from the Home header/nav — not a hidden route. The engineering
framing ("Ingesta local (dev)") is replaced with product-facing copy.
`/ingesta` may 301-redirect to `/archivos` for continuity; no separate
engineering screen remains linked from anywhere in normal navigation.

The page keeps its existing shape (login gate → session → per-product
scoped view) but reorganizes into:

- **Mis archivos** — today's job list, extended with the source
  filename (already captured in `source_observation.filename`) so it
  reads as a file list with status, not a bare job-ID table.
- **Subir archivo** — today's manual upload panel, unchanged.
- **Desde OneDrive** — new. Visible only to users with an `UPLOAD`-capable
  grant on at least one product. Triggers the incremental Graph consent
  (section 1) on first use, then shows a folder/file browser scoped to
  *only* the product(s) the user is granted on, backed by the
  intersection rule in section 3. Selecting a file requires the same
  explicit product selection the upload panel already requires — never
  inferred.
- **Audit** — unchanged (admin-only).

A minimal **grants** panel (admin-only, gated by `Action.MANAGE_ACCESS`)
lists real Entra identities that have ever logged in and lets an admin
set/change their per-product role. Without this, a bootstrap admin has no
way to onboard a second real user — see section 1.

## 5. Ingestion wiring: browse/select is metadata-only for now

`Desde OneDrive` lets a user authenticate, browse, and *select* a real
file — all metadata-only Graph calls (`children`, `search`, item
properties). The step that would fetch bytes
(`GET /drives/{id}/items/{id}/content`) and hand them to the existing
`object_store.put` → `persist_uploaded_source_provenance` →
`enqueue_processing_job` pipeline is implemented but sits behind a
feature flag, **off by default**:

```
ENABLE_ONEDRIVE_IMPORT=false
```

Rationale (section "Ephemeral storage" explains the mechanism): Render's
free-tier object store is ephemeral, and this slice must not be the thing
that first pipes real client binaries into a store that can silently
lose them. Manual upload already carries this exact risk today and is
already documented as accepted in ADR-005 — this slice does not make that
worse, but it also must not extend the same unresolved risk to a second,
larger, real-external-data source. When durable object storage exists
(a later, separate decision — GCS/Azure Blob/S3-compatible, whichever
production provider is accepted), flip the flag; no pipeline code
changes, since it's the same `object_store.put` call regardless of byte
source.

A new source-system row (`campo_digital_graph`, analogous to today's
`campo_digital_upload` in `app.source_provenance`) distinguishes
Graph-sourced snapshots from browser uploads in provenance, once the flag
is on.

## 6. Execution: staging-only in-process adapter, not a production model

ADR-005 deploys no worker, so queued jobs never complete on Render
staging today. Fix this cheaply, but do not blur it into a production
decision:

- Introduce an explicit `ExecutionBackend` interface (`app/execution.py`)
  with one method roughly like `submit(job) -> None`. `app.worker.run_one_job`
  becomes the shared implementation logic called by any backend.
- `InProcessStagingExecutionBackend`: a FastAPI startup task that polls
  `run_one_job` on an interval. Guarded explicitly by
  `APP_ENV == "staging"` (a distinct check from dev-auth's — staging
  chose this specifically to keep the free deployment demoable, not
  because it's an acceptable production pattern). It:
  - runs blocking DB + inspection work via `asyncio.to_thread` /
    `run_in_executor`, never directly on the event loop;
  - enforces a staging-specific size cap well below
    `MAX_UPLOAD_BYTES` (2 GiB): default **25 MB**, configurable via a new
    `STAGING_EXECUTION_MAX_BYTES` env var, suitable for metadata/small-file
    demonstration, not real workloads — a job over the cap stays queued
    with `error_summary = "exceeds staging execution size limit"` rather
    than being attempted;
  - explicitly refuses `lidar` product jobs (real LiDAR inputs are
    hundreds of MB and the point of this guard is that full LiDAR
    processing must never run this way) — jobs for that product stay
    queued with a clear "not processed in staging" status rather than
    being attempted and failing confusingly.
- The production execution model remains the open question it already
  is (Cloud Run Jobs / Container Apps Jobs per ADR-001/ADR-004) — this
  slice adds the interface seam, not the production implementation.

## 7. Ephemeral storage: visible, not silent

A `processing_job` row can now outlive the local object it references —
Render's free web service gets a fresh ephemeral filesystem on every
redeploy or idle spin-down/wake, but Postgres rows persist. When the
in-process adapter (or a future worker) goes to claim a job whose
`object_storage_key` no longer resolves in `LocalObjectStore`, it must
fail that job with a distinct, visible status/error summary (e.g.
`error_summary = "source object unavailable (ephemeral storage cycled)"`)
rather than crashing or silently retrying forever. This state must be
what the "Mis archivos" list actually shows for such a job — this
slice must not claim source preservation it cannot back up. This is a
genuine, expected outcome on the free tier, not a bug to be hidden.

## Sequencing (implementation order)

1. **Discovery spike** (section 2) — determine drive/site type and the
   least-privileged Graph scope against a real Campo Digital sign-in.
   Record the RESULT in `docs/source-systems/onedrive.md`. No app code.
2. **Entra app registration handoff doc** — write the exact steps for
   Campo Digital's tenant admin (dedicated Campo Digital Entra tenant,
   app supporting any organizational directory + personal Microsoft
   accounts, redirect URIs for local + Render staging, the scope chosen
   in step 1, `Sites.Selected` grant only if a future SharePoint-backed
   source needs it). Blocks nothing else in parallel, but real
   end-to-end testing needs it done.
3. **Session hardening** — migration `0007` (`platform.session`,
   `platform.ms_graph_grant`), swap dev-auth's in-process session for the
   hashed-cookie Postgres-backed store; restrict `assert_dev_auth_allowed`
   to `development` only. (Independently valuable and low-risk — do this
   before Entra lands.)
4. **Entra sign-in** — `msal`-backed authorization-code + PKCE login
   flow, `identity_kind="entra"` resolution, bootstrap-admin check,
   two-step consent scaffolding (Graph consent request wired but unused
   until step 6).
5. **Grants management** — minimal admin endpoint/UI using
   `Action.MANAGE_ACCESS`.
6. **Archivos navigation** — rename/move `/ingesta` → `/archivos`,
   reorganize into Mis archivos / Subir archivo / Audit (OneDrive panel
   deferred to step 7).
7. **OneDrive browse/select** — Graph client, source-catalog stable-ID
   config, the intersection authorization check (section 3), "Desde
   OneDrive" panel wired to metadata-only calls. `ENABLE_ONEDRIVE_IMPORT`
   stays `false`.
8. **Staging execution adapter** — `ExecutionBackend` interface,
   `InProcessStagingExecutionBackend`, ephemeral-object-missing handling
   (section 7).
9. **Deploy + verify on Render staging**, dev-auth confirmed unreachable
   there, real Entra login exercised end-to-end, OneDrive browse
   exercised end-to-end (import flag still off).

Flipping `ENABLE_ONEDRIVE_IMPORT` to `true` is explicitly **not** part of
this slice — it's gated on a separate durable-object-storage decision.

## Related documents

- `docs/adr/ADR-005-render-staging-experiment.md`
- `docs/platform/security-model.md`
- `docs/platform/source-ingestion.md`
- `docs/source-systems/onedrive.md`
- `config/source-catalog.yaml`
