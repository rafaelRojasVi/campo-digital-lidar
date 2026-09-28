# ADR-005 — Render STAGING experiment

## Status

Accepted for an experimental staging/demo deployment only. Does not
supersede ADR-001 or ADR-004 and does not decide the production cloud
provider, which remains open.

## Context

The local platform (established by ADR-001–ADR-003 and the local
ingestion/access foundation) already has Alembic migrations through head, a
shared FastAPI app, the portal, ingestion/access/RBAC, a filesystem object
store, a PostgreSQL-queue worker, and dev-only local auth. Campo Digital
wants a reachable staging/demo instance of this stack without committing to
a production provider or paying for infrastructure yet.

Render was chosen for this experiment specifically because it offers a
Blueprint (`render.yaml`) model that maps cleanly onto the platform's
existing local shape (one Postgres, one API process, one static frontend)
and a genuinely free tier for all three, which fits the platform's stated
cost philosophy of not paying for infrastructure before it's needed (see
`../platform/environments-and-costs.md`).

## Decision

Deploy the smallest practical stack as a single root `render.yaml`
Blueprint, all in one Render region, on free-tier resources:

- `campo-digital-api-staging` — Python web service running the shared
  FastAPI app (`apps/api/app/main.py`) via `uv sync --extra api --extra
  transelec`.
- `campo-digital-portal-staging` — static build of `apps/portal`.
- `campo-digital-db-staging` — free Render PostgreSQL 17.

**RESULT** — `uv sync --extra api --no-dev` alone is not sufficient to
import `app.main`: `app.main` imports `app.routers.ingestion`, which
imports `app.worker` (to reuse `dispatch_inspection`), which imports
`app.inspection.transelec_inspector` unconditionally, which imports
`python_calamine` — a dependency of the `transelec` extra, not `api`. This
was caught by running `apps/api/tests` against a Blueprint-equivalent
`uv sync --extra api --no-dev` environment before committing this render.yaml;
without `--extra transelec` too, the API process would have failed to start
on Render with `ModuleNotFoundError: No module named 'python_calamine'`
despite `uv sync` succeeding and passing local checks that happened to
already have the full dev environment (`--all-extras --dev`) installed.

No background worker (`app.worker`) is deployed. Uploaded jobs will queue in
Postgres (`app.jobs`) but nothing will claim and process them. Adding a
worker is explicitly out of scope for this experiment and was excluded by
the task that produced this ADR ("Do NOT add a paid background worker yet")
— Render free-tier background workers do not exist (`worker` type services
require a paid plan), so enabling processing later requires a paid resource
decision, not just a config change.

**Update**: a later, separately-scoped task added
`app.execution.InProcessStagingExecutionBackend`, which claims and processes
small, non-LiDAR jobs from inside this same web service process (still no
separate worker service — this ADR's paid-worker constraint is unaffected).
See `docs/superpowers/specs/2026-09-01-secure-file-access-slice-design.md`
section 6 for the current behavior; the paragraph above and the
"jobs visibly queue but never complete" consequence below describe this
ADR's original scope only.

### Region

Render's currently supported regions are Oregon, Ohio, Virginia (all US),
Frankfurt, and Singapore — none are in South America. **Virginia (US East)**
was chosen for both the API service and the database because US-East is the
best-connected of Render's regions to South American networks in practice
(most South America-to-US backbone/peering runs through the US East
coast/Florida), clearly ahead of US West (Oregon), Frankfurt, or Singapore
(effectively antipodal to Chile) for this use case. This is a network-path
judgment, not a documented Render latency guarantee — re-benchmark before
relying on it for anything latency-sensitive. A single region is used for
both API and DB per the task constraint, so there is no cross-region DB
round-trip.

### Migration execution

Render's free-plan services do not support `preDeployCommand`
(`render blueprints validate` rejects it with "pre-deploy command is not
supported for free tier services"). `alembic upgrade head` therefore runs as
the last step of `buildCommand` instead of as a gated pre-deploy step. This
runs once per deploy (not on every process boot/wake), and is safe to
re-run because Alembic migrations are idempotent at head. This includes
migration `0001`'s `CREATE EXTENSION IF NOT EXISTS postgis`, so PostGIS is
enabled automatically on first deploy — no manual `psql` step is required.

If/when this stack moves to a paid plan, moving this command back to
`preDeployCommand` is the natural follow-up (it gates traffic cutover on
migration success, which a build-step migration does not).

### `APP_ENV=staging` and dev-auth

**Superseded by `ADR-006-restrict-dev-auth-to-development.md`.** This
section is kept as the historical record of the original decision; dev-auth
is no longer enabled in staging — see ADR-006 for the current behavior and
rationale. The rest of this ADR (staging deployment architecture, region,
migration execution, object storage, health check) is unaffected.

`app.config.Settings.app_env` was extended from
`Literal["development", "test", "production"]` to
`Literal["development", "test", "staging", "production"]`. This was the one
platform code change made for this deployment, and it is additive: the two
places that branch on `app_env` are `app.dev_auth.assert_dev_auth_allowed`
(`== "production"`) and `app.db_safety.require_test_database`
(`!= "test"`), and `app.main`'s dev-auth router-mounting check reads
`APP_ENV` from the raw process environment rather than through `Settings`.
Adding `"staging"` does not change behavior for any existing value and was
verified not to require touching either check: staging correctly gets
dev-auth (like development) and is correctly rejected by
`require_test_database` (like development), since neither check special-cases
`"staging"` — it simply isn't `"production"` or `"test"`.

Using `APP_ENV=staging` (a real, distinct, explicit value) rather than
reusing `APP_ENV=development` was preferred because it is honest about what
this deployment is — `Settings.app_env` is visible in error messages
(`db_safety`) and worth not misrepresenting — at the cost of one Literal
member and three small tests
(`test_dev_auth_allowed_in_staging`,
`test_dev_auth_routes_mounted_in_staging`,
`test_staging_environment_is_rejected`).

Dev-auth is deliberately left enabled in staging: there is no managed
identity provider decision yet (`../platform/security-model.md` lists
"production identity provider" as an open decision), and this is a
staging/demo environment. `DevSessionStore` is in-process, in-memory
per `apps/api/app/deps.py`, so sessions do not survive a redeploy or a
free-tier spin-down/spin-up (see Limitations).

### Portal → API: same-origin rewrite instead of CORS

`apps/portal/src/lib/platformApi.ts` already calls a relative `/api/*` path
with `credentials: 'include'`, and `apps/portal/vite.config.ts` already
proxies `/api/*` to the platform API locally, stripping the `/api` prefix.
The Render static site for the portal reproduces this with a Blueprint
`routes` rewrite rule (`/api/*` → the API service's `.onrender.com` origin,
prefix stripped), rather than adding CORS middleware to the FastAPI app.

This was preferred over CORS because it keeps the browser's view of the
portal and API as one origin, so the dev-auth session cookie
(`app.routers.dev_auth`, `samesite="lax"`) stays a normal first-party
cookie. Adding CORS would have required `allow_credentials=True` scoped to
an exact origin plus relying on cross-site cookie delivery
(`SameSite=None; Secure`), which is both more code and a weaker security
posture for no benefit here — so no CORS code was added to `app.main`.

**Caveat**: the rewrite destination hardcodes
`https://campo-digital-api-staging.onrender.com`, assuming Render grants
that service its literal name as the default hostname (no collision with
another Render account's service). Blueprint `routes` destinations are
static strings — they cannot reference `fromService`-style values. Verify
the API service's actual `.onrender.com` URL after first deploy and update
`render.yaml` if it differs.

### Object storage stays local-filesystem, and stays ephemeral

`app.object_store.LocalObjectStore` (`CAMPO_OBJECT_STORE_ROOT`, default
`.local/object-store`) is used unmodified, with no Render Disk attached.
Render free-tier web services have no persistent disk option (disks require
a paid instance), and the task this ADR accompanies explicitly said not to
hide that limitation behind an unexplained default. Recording it here
instead of adding code: **uploaded file content will not survive a
redeploy or a free-tier idle spin-down/spin-up** (Render moves a free
service to a new ephemeral filesystem on each cold start). Ingestion
metadata in Postgres (jobs, audit events, source-provenance rows) does
survive; the underlying object bytes referenced by `object_storage_key`
generally will not. This is acceptable for a single-session demo and not
acceptable for anything meant to persist — do not point real client uploads
at this deployment.

### Health check

`healthCheckPath: /health` (pure liveness, no DB dependency) was used
instead of `/ready`. `/ready` legitimately returns 503 during a transient
DB hiccup; using it as the Render health check would restart-loop the
instance for a condition that should instead surface as a 503 to callers.

## Consequences

- Free Render Postgres expires 30 days after creation (14-day grace period
  before deletion) and is capped at 1 GB, with no backups. This is fine for
  a short-lived experiment and wrong for anything meant to persist — if this
  staging environment is still valued after ~3–4 weeks, it needs to move to
  a paid DB plan before it silently disappears.
- No worker means ingestion jobs visibly queue but never complete in this
  environment — expected, not a bug, until a worker/background-service
  decision is made. **Update**: since the in-process adapter noted above was
  added, this is only true for LiDAR jobs and jobs over the staging size
  limit, which are now terminally failed with an explicit rejection reason
  rather than left queued forever.
- `render blueprints validate render.yaml` requires the target branch to
  exist on the remote. It could not be run against `feat/render-staging-v1`
  itself without pushing (explicitly out of scope for the task that produced
  this ADR); it was verified structurally valid against an existing branch
  instead. Full validation against the real branch is the first manual step
  after this branch is pushed.
- This ADR does not authorize provisioning. Applying this Blueprint is a
  manual Render Dashboard action.

## Related

- `../platform/environments-and-costs.md` — production cost philosophy and
  GCP planning baseline (unaffected by this staging experiment).
- `ADR-004-revisit-production-cloud-provider-choice.md` — the still-open
  production provider question.
- `../platform/security-model.md` — "Open decisions" (identity provider),
  which is why dev-auth is still in use here.
