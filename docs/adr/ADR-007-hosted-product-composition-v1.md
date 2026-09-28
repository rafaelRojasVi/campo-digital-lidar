# ADR-007 — Hosted product composition V1

## Status

Accepted. Extends the STAGING deployment established by
`ADR-005-render-staging-experiment.md` (unaffected) and respects
`ADR-006-restrict-dev-auth-to-development.md` (dev-auth stays
development-only; not touched here).

## Context

The portal (`docs/platform/company-portal-v1.md`) was built as a local demo
shell: its runtime status ("Demo no iniciada", "Estado del entorno local",
`/estado`'s "Iniciado por Campo Demo" column) all describe a local process
launcher (`scripts/campo_demo.py`), and its module iframe safety check
(`apps/portal/src/lib/safeUrl.ts`'s `isSafeLocalUrl`) only ever trusted
loopback hosts. Once `feat/render-staging-v1` gave the platform a real public
STAGING URL, that copy became actively misleading there: a public visitor
would see "not started locally" language for a service that was never meant
to run on their machine, and no code path existed to show a module as
genuinely hosted.

Separately, three product frontends exist in this monorepo or its sibling
worktrees (LiDAR, Forestry, Transelec), and the task motivating this ADR
asked which of them, if any, could be hosted publicly at $0 without exposing
real/private client data.

## Decision

### Portal: explicit LOCAL/STAGING environment

`apps/portal/src/runtime/environment.ts` adds `CampoEnvironment = 'local' |
'staging'`, resolved once at Vite build time from `VITE_CAMPO_ENV` (set by
`render.yaml` for the STAGING portal build only; unset locally, so
`npm run dev` / `make campo-demo` are unaffected). `CampoRuntimeConfig` now
carries this as an explicit `environment` field.

LOCAL keeps fetching the gitignored, launcher-written
`apps/portal/public/campo-runtime.json` exactly as before —
`buildStagingRuntimeConfig()` (new) is never called on that path, and every
pre-existing portal test passes unmodified, which is the verification that
LOCAL behavior did not regress.

STAGING never fetches anything: there is no server behind a static site to
generate a dynamic file, so `apps/portal/src/runtime/hostedModules.ts`
supplies a small, closed, build-time module-URL registry
(`VITE_LIDAR_HOSTED_URL` today; Forestry/Transelec keys are deliberately
absent, not merely empty — see Classification below), and
`buildStagingRuntimeConfig()` turns that into a `CampoRuntimeConfig`
synchronously. `Estado`, `StatusBadge`, and `Module`'s unavailable-state copy
all branch on `config.environment`: STAGING never shows "Demo no iniciada" or
"Iniciado por Campo Demo" (meaningless off a developer's machine), showing
instead an honest hosted-availability or not-yet-hosted message.

### Safe iframe/link URLs: closed allowlist, not a wildcard

`isSafeIframeUrl(candidate, environment)` extends the existing loopback-only
LOCAL check with a STAGING check that accepts only `https://` URLs whose
hostname is *exactly* `campo-digital-lidar-staging.onrender.com` — not a
`*.onrender.com` wildcard. The STAGING runtime config is build-time-trusted
(Task 2's registry, not user input), so this is defense-in-depth: a future
config mistake supplying some other onrender.com hostname can never become
an iframe/open-redirect target, since Render's `onrender.com` subdomain
namespace is shared across unrelated Render customers.

### `/archivos`: renamed nav entry, honest STAGING sign-in state

`/ingesta` (component `Ingesta`) is renamed to `/archivos` (component
`Archivos`) and added to the Home footer as a first-class nav link. No
change to `apps/portal/src/lib/platformApi.ts`, `app.access`, or any RBAC
check — this is a rename plus one new environment-gated branch in the
logged-out view. Since ADR-006 means the dev-auth router is not mounted
outside `APP_ENV=development`, `POST /api/auth/dev-login` 404s on STAGING;
rather than show dead identity buttons that silently fail, the STAGING
logged-out state shows: "El inicio de sesión de plataforma aún no está
disponible en este entorno (queda pendiente la integración con Entra ID)."

### Product hosting classification

**LiDAR — B (small integration/composition work).**
`apps/api/app/routers/lidar.py` has no DB dependency (mounted unconditionally
in `apps/api/app/main.py`, before any DB-gated route) and its
`get_output_root()` → `lidar_io.output_root_discovery.resolve_report_root`
already resolves to `SOURCE_NONE` → `GET /runs` → `[]` on a fresh Render
checkout (no sibling worktrees, no `CAMPO_LIDAR_OUTPUT_ROOT`). Verified
directly: running the shared API locally with `CAMPO_LIDAR_OUTPUT_ROOT`
pointed at an empty directory (simulating the fresh-checkout case Render
will actually run) returns `[]`, and the dashboard
(`products/lidar/dashboard`) renders a clean "No hay medición seleccionada"
empty state with no console errors and no broken assets — its one real-photo
asset (`/local-demo/field-reference.jpeg`) only renders inside a selected-run
detail view that an empty run list never reaches. **No LiDAR product code
was changed.** The only new work is composition: a new Render static site
(`campo-digital-lidar-staging`, see `render.yaml`) reusing the
already-deployed `campo-digital-api-staging` service via the same
same-origin `/api/*` rewrite pattern the portal already uses, and the portal
wiring described above.

Also verified, and worth recording precisely because it is easy to get
wrong: running the shared API locally **without** an explicit
`CAMPO_LIDAR_OUTPUT_ROOT` on a real developer machine auto-discovered real,
client-derived measurement data from a sibling local git worktree (per
`output_root_discovery.py`'s documented precedence). That data was never
displayed in a browser, never left `127.0.0.1`, and was not committed
anywhere — it is exactly the behavior `output_root_discovery.py` already
documents (developer-machine convenience, safe on a fresh CI/Render clone
because no sibling worktrees exist there). `render.yaml` deliberately never
sets `CAMPO_LIDAR_OUTPUT_ROOT` for `campo-digital-api-staging`, which is what
keeps the deployed behavior at the safe, verified `[]` case rather than the
developer-machine case.

**DECISION (pre-deploy hardening, QA finding).** The paragraph above relied
on environmental happenstance — "safe because no sibling worktrees exist on
Render" — rather than a code-level guarantee. QA correctly flagged that as
insufficient: any hosted `APP_ENV` (`staging`, `production`) that ever did
have sibling worktree paths reachable on disk would silently serve their
report data. `resolve_report_root` now takes an `app_env` parameter
(`apps/api/app/routers/lidar.py:get_output_root` passes
`os.environ.get("APP_ENV", "development")` straight through, matching the
raw-env-read pattern already used in `app/main.py`): local/worktree
auto-discovery (current-worktree and sibling-worktree probing, including the
`git worktree list` subprocess call) now only runs when `app_env ==
"development"`. In every other environment, with no explicit
`CAMPO_LIDAR_OUTPUT_ROOT`, it returns the same `[]`-producing fallback
directly (tagged `SOURCE_DISCOVERY_DISABLED`), without ever listing worktrees
or probing any directory. This makes the STAGING/production `[]` behavior an
enforced invariant rather than a fact about the current Render checkout
layout — see `products/lidar/tests/test_output_root_discovery.py` and
`apps/api/tests/test_output_root_resolution.py` for the regression coverage,
including an end-to-end case where real sibling measurement data exists on
disk and is proven both unreturned and untouched.

**Forestry — B on paper, deferred (honest not-yet-hosted) this slice.** The
dashboard (worktree `feat/forestry-dashboard-v1`) has no static/offline data
path — `src/api.ts` always calls `/api/forestry/*` — so hosting it would
require hand-building a synthetic `FeatureCollection`/`SnapshotSummary`
matching its types and a new static-data branch in `api.ts`. Real Degenfeld
data is confirmed never committed to git (only local Postgres, sourced from
an external, gitignored ZIP via `CAMPO_DIGITAL_SOURCE_ROOT`), so there is no
leak risk either way, but *inventing* forestry polygon geometry for public
display risks exactly the speculative-business-semantics problem this task
was told to avoid, and the branch itself is not merged here. The honest
answer for this slice is "not yet hosted."

**Transelec — C (architecturally blocked as designed).** The hosted-pilot
branch's `/api/transelec/*` routes require a live Postgres + object store
even to serve their degraded/error state; Render's $0 tier has no additional
free persistent Postgres beyond the one already-provisioned staging DB, and
that branch's own deployment runbook
(`products/transelect/docs/deployment.md`) explicitly designs for
IAP-gated, non-public access — not open staging. A public $0 deployment
would need a from-scratch UI extraction plus a fabricated dataset, which is
out of scope for the same data-fabrication reason as Forestry.

## Consequences

- STAGING cost is unchanged at $0/month: `campo-digital-lidar-staging` is a
  Render free static site (same tier as `campo-digital-portal-staging`), and
  it adds no new database, no new backend service, and no new object
  storage.
- Forestry and Transelec show an honest "not yet available publicly" card in
  STAGING rather than a fake green status. Extending either to Category A/B
  requires a follow-up task explicitly scoped to build a synthetic dataset —
  not implied by this ADR.
- `render.yaml`'s `branch:` for all three services now points at
  `feat/hosted-composition-v1` (the branch containing this work) instead of
  `feat/render-staging-v1`. `render blueprints validate` cannot fully
  validate against a local, unpushed branch (documented in ADR-005); it was
  confirmed schema-valid, including the new service, by substituting an
  already-remote branch name for validation only (not committed).
- This ADR does not authorize provisioning or pushing. Applying the
  Blueprint remains a manual Render Dashboard action, as ADR-005 states.

## Related

- `ADR-005-render-staging-experiment.md` — the staging deployment this
  extends.
- `ADR-006-restrict-dev-auth-to-development.md` — why `/archivos` cannot
  offer sign-in in STAGING yet.
- `../platform/company-portal-v1.md` — portal architecture, updated
  alongside this ADR.
- `../platform/product-boundaries.md` — why Forestry/Transelec business
  semantics are not reproduced here even synthetically without a scoped
  follow-up.
