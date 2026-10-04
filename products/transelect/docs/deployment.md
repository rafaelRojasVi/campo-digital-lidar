# Transelec production container packaging

## Status

Container packaging: **built and locally verified** (this document).

- **FACT (2026-09-28):** Railway production
  (`campo-digital-platform-production.up.railway.app`) serves the
  `feat/transelec-ux-rearchitecture-v1` tip `829099a` (PRs #59 and #60).
  The served bundle name and the #60 security headers were checked from
  outside. Railway HTTP logs from 2026-09-26 show a Campo Digital user
  signing in with Google and uploading, validating and publishing a
  workbook, all answered `200`.
- **FACT (2026-10-04):** production serves `main` at `802fa3f` (PR #71),
  deployed 2026-10-03 13:22 UTC (Railway deployment list). The migration
  head is `0011` (read-only query, 2026-10-04), so parser `@3` from PR #70
  is live. `/health` and `/ready` answer `200`, the deploy log starts with
  the `campo-entrypoint` line, and the forestry and Transelec API routes
  answer `401` signed out.
- Railway auto-deploy is off, so deploys are manual. Since 2026-09-28 the
  service deploys from `main`.
- **DECISION (2026-09-28):** no backups. The Hobby plan has no scheduled
  backups (Pro only), and Rafael accepted the risk: published workbook data
  can be rebuilt by re-importing, grants and audit history cannot. A manual
  `pg_dump` can be taken on demand (see "Manual database backup"); it does
  not change this decision.

Read first, and treat as authoritative over this document if they disagree:

- [`docs/platform/production-platform-v1.md`](../../../docs/platform/production-platform-v1.md)
- [`docs/platform/environments-and-costs.md`](../../../docs/platform/environments-and-costs.md)
- [`docs/platform/security-model.md`](../../../docs/platform/security-model.md)

## Architecture

One container runs the shared platform API together with the Transelec
dashboard's static build:

```text
Browser
  |
  v
FastAPI (apps/api/app/main.py)
  |-- GET  /                    -> React production build (same origin)
  |-- GET/POST /transelec/*     -> real Transelec read/write API
  |-- GET/POST /api/transelec/* -> same API, the prefix the dashboard's
  |                                own bundle calls (see api.ts)
  |-- GET/POST /auth/*, /api/auth/* -> session, CSRF, and (dev-only) dev-auth
  |-- GET /health, GET /ready
  |
  +-- PostgreSQL/PostGIS -- platform.transelec_import, transelec_pmf_row,
                             transelec_publish_event, transelec_dashboard_state
```

`app.dashboard_static.mount_dashboard` mounts the built dashboard as a
same-origin SPA fallback (no CORS surface) — see that module's docstring.
The `/api/*` alias duplicates ROUTING ONLY for the CSRF, dev-auth, and
Transelec routers: same router objects, same dependencies, same RBAC. It
exists because every frontend on this platform is compiled once against a
same-origin `/api/*` convention and normally reaches the API through an
external rewrite (the Vite dev proxy locally, Render's static-site rewrite
in staging — see `render.yaml`); a bare container has no such external layer
in front of it, so `app.main` provides that alias itself.

Both LiDAR and Transelec routers are mounted in the same FastAPI process
(the platform's modular monolith), so this image ships the full platform
dependency stack (numpy/scipy/pandas/laspy/matplotlib for LiDAR) even though
it only serves Transelec's frontend. **LIMITATION**: this makes the image
large (~1.06 GB at the time of writing) and rebuilds on any LiDAR dependency
bump. Splitting the composition root by product is a reasonable future
optimization, not attempted here.

## URL layout (unified platform)

**DECISION (2026-09-28):** one origin serves the Campo Digital front door
and each hosted product
([design](../../../docs/superpowers/specs/2026-09-28-unified-platform-design.md)):

| Path | Serves | Built with |
|---|---|---|
| `/` | Front door (`apps/portal`): Google sign-in, project picker | `VITE_CAMPO_ENV=production` |
| `/transelec/...` | Transelec dashboard (Vite `base` `/transelec/`) | `VITE_PLATFORM_FRONT_DOOR=true` |
| `/api/...` | Platform API | n/a |

- `app.dashboard_static.mount_dashboards` serves both builds. The portal
  build comes from `CAMPO_PORTAL_DIST` (default `apps/portal/dist`), and
  Transelec's from `CAMPO_TRANSELEC_DASHBOARD_DIST` (default
  `products/transelect/dashboard/dist`).
- Only exact Transelec page paths get Transelec's shell, with or without a
  trailing slash. Any other unknown top-level path gets the front door.
  `/api`, `/health`, `/docs` and the other reserved segments answer `404`.
- `/assets/` and `/transelec/assets/` are the only cacheable paths.
- A signed-out visit to any Transelec page is sent to `/`. The Google
  callback lands on `/`, with no `next=` parameter.
- On the platform, Transelec's right-hand bar button is **Proyectos**, back
  to the front door, which owns "Cerrar sesión".
- **FACT (2026-09-28):** the image built from this branch, run with
  `APP_ENV=production`, answers `200` for `/`, `/transelec`, `/transelec/`
  and `/transelec/pendientes`. It answers `404` for `/docs`,
  `/api/forestry/snapshots` and unknown `/transelec/...` paths.
- **LIMITATION:** the image does not contain `products/forestry/src`.
  Rodales can go online only once the image includes it (step 3 of the
  design).

## Auth

This container runs the platform's real session/CSRF/RBAC stack — the same
one Tasks 2–4 built and tested — not a bespoke Transelec credential. There
is no `CAMPO_TRANSELEC_ADMIN_TOKEN` or equivalent product-specific auth.

**OPEN QUESTION / LIMITATION**: outside `APP_ENV=development`, the only
session-creation route currently mounted is dev-auth's `/auth/dev-login`,
and `app.main` gates that route to development only (see
`apps/api/tests/test_main_dev_auth_gate.py`). A real identity provider
(Entra ID; `msal` is already a dependency) is Task 7's scope, not this
task's. **This means a container run with `APP_ENV=production` or
`APP_ENV=staging` today has no way for anyone to create a session at all** —
`platform.PlatformSessionStore`-backed sessions exist and are checked first
by `get_current_app_user`, but nothing in this codebase yet issues one
outside dev-auth. This is expected and is exactly the gap Task 7 closes; it
is not a defect in this packaging work.

**Update (2026-09-17) — this gap is now closed for Transelec.** The product
signs in with Google Workspace: `GET /auth/google/login` and
`GET /auth/google/callback` are mounted in every `APP_ENV`
(`apps/api/app/routers/google_auth.py`,
`docs/adr/ADR-010-google-workspace-sign-in-for-transelec.md`), so a
container run with `APP_ENV=staging` or `APP_ENV=production` can issue a
real `platform.session`. It needs `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_BASE_URL`,
`GOOGLE_WORKSPACE_DOMAIN` and `PLATFORM_TOKEN_ENCRYPTION_KEY`; without
them each route answers `503` rather than 404ing, and under
`APP_ENV=production` the process refuses to start at all. Microsoft Entra
remains the provider for the other products. The remaining external gates
were the OAuth client itself and the final public domain — see
`../../../docs/platform/google-workspace-oauth-handoff.md`. As of
2026-09-25 the client exists, with the production redirect URI
`https://campo-digital-platform-production.up.railway.app/api/auth/google/callback`,
which requires `GOOGLE_REDIRECT_BASE_URL` to end in `/api`. No real Google
sign-in has been performed yet.

### HTTP hardening

`apps/api/app/http_hardening.py` wraps the whole app in two middlewares.
Both are wired in `app.main`.

- **Request-body limits.**
  - An upload route whose session cookie is missing, forged, expired or
    revoked is answered `401` before any of the body is read. The session
    is resolved against `platform.session` there, not just checked for
    presence.
  - Bodies are capped at 64 MiB for a Transelec workbook, 2 GiB for
    `/ingesta/upload`, and 1 MiB for everything else, and are answered `413`
    past the cap.
  - This runs before FastAPI parses the body, which it otherwise does before
    authentication.
- **Security headers.**
  - Every response gets `X-Frame-Options: DENY`, `X-Content-Type-Options:
    nosniff`, `Referrer-Policy: same-origin` and a same-origin CSP with
    `frame-ancestors 'none'`.
  - Everything except `/assets/*` gets `Cache-Control: no-store`.
  - Staging and production add HSTS.
  - The dashboard needs no inline script or style and no third-party origin.
    If a change to it adds one, the CSP in that module has to change with it.
- **No API docs in production.** Under `APP_ENV=production`, `app.main`
  mounts neither `/docs`, `/redoc` nor `/openapi.json`, and the SPA fallback
  answers them `404` rather than `index.html`. Every other environment keeps
  them (`apps/api/tests/test_main_docs_exposure.py`).

See the [2026-09-26 security readiness audit](audit/2026-09-26-security-readiness-audit.md)
for the evidence behind both.

## Container image

`Dockerfile` (repo root) is a two-stage build, adapted from the *shape* of
the superseded `feat/transelec-hosted-pilot-v1` branch's Dockerfile (see
`docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-design.md`,
where that branch is referenced as prior art, "PR #47") — not copied: that
draft predates this branch's real session/CSRF/RBAC work, used a
`CAMPO_TRANSELEC_ADMIN_TOKEN` this branch does not have, and installed a
Cloud Storage SDK layer this branch's `app.object_store` has no backend for
yet (omitted here as speculative runtime weight).

1. `node:24.19.0-slim` builds `products/transelect/dashboard` into static
   assets (`npm ci && npm run build`).
2. `python:3.12-slim` installs locked dependencies with `uv sync --frozen
   --no-dev --extra api --extra transelec` (matches `render.yaml`'s own
   buildCommand for the shared platform API service), copies the built
   dashboard assets into `products/transelect/dashboard/dist`, and runs as
   a non-root `campo` user (uid/gid 999).

The container listens on `0.0.0.0:$PORT` (defaults to `8080`).

### Build and run locally

```bash
docker build -t campo-digital-transelec:local .

# Without a reachable database — /health is still up, /ready fails closed:
docker run --rm -d --name transelec-smoke -p 18080:8080 \
  -e APP_ENV=development -e POSTGRES_PASSWORD=local-only \
  campo-digital-transelec:local

docker exec transelec-smoke whoami   # -> campo
docker exec transelec-smoke id       # -> uid=999(campo) gid=999(campo)
curl -s http://127.0.0.1:18080/health   # -> {"status":"ok"}       (200)
curl -s http://127.0.0.1:18080/ready    # -> {"status":"not_ready"} (503)
docker stop transelec-smoke
```

**RESULT** (recorded during Task 6, 2026-09-02): built and run exactly as
above, then re-run with `--network host` and `POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5433` (this repo's disposable `postgres-test` compose service,
migrated to head) to exercise the full path: `/ready` returned `200`; `/`
served the dashboard shell; `/transelec/summary` and `/api/transelec/summary`
both returned `401 {"detail":"Not authenticated."}` without a session;
`POST /api/auth/dev-login {"identity_key":"dev-admin"}` set a session cookie
and returned the seeded `transelect: admin` grant; the same cookie against
`/api/transelec/summary` reached real business logic and returned
`404 {"detail":"No hay una versión publicada de Transelec."}` — the correct
response for a fresh database with nothing imported yet, not an error.
`whoami`/`id` confirmed the process runs as the non-root `campo` user.

## Database

Use the shared platform PostgreSQL/PostGIS instance and the `platform`
schema already established by earlier migrations — do not provision a
Transelec-specific database server (see
[`production-platform-v1.md`](../../../docs/platform/production-platform-v1.md)).
This container does not run migrations on startup, by design (see that same
document, "no implicit destructive migration on app startup"); apply
`alembic upgrade head` as a separate release step against this image before
routing traffic to it.

### PostGIS image

**FACT (2026-10-04, read-only query and the Railway API):** the production
PostGIS service runs the image `postgis/postgis:16-master`, a tag built from
PostGIS's development branch. It holds PostgreSQL 16.15 with PostGIS
`3.7.0dev` (`3.6.0rc2-620-gb8c7b0142`) and GEOS `3.15.0dev`. The `postgis`
and `postgis_topology` extensions are both at `3.7.0dev`, and the database
is 19 MB.

TLS comes from `POSTGRES_INITDB_ARGS` (`ssl=on` with the image's Debian
snakeoil certificate), and the app connects with `sslmode=require`
(observed: TLSv1.3).

**FACT:** CI (`persistence-ci.yml`) and `compose.yaml` test against
`postgis/postgis:17-3.5@sha256:624f5195…` (PostgreSQL 17.5, PostGIS 3.5.2).
That image ships the snakeoil certificate at the same paths (checked
locally). So production differs from what is tested in both the PostgreSQL
major and the PostGIS version.

**FACT (Docker Hub, 2026-10-04):** no stable `16-3.6` or `16-3.7` tag
exists. PostGIS 3.6 is published only for PostgreSQL 17 (alpine) and 18,
and 3.7 is unreleased. `16-master` was last pushed on 2026-08-31 (index
digest `sha256:afaf08e1937d753762cfdb943c69ed46296bf50faa80c5f89494e2d0d12980de`),
before the PostGIS deploy of 2026-09-17. **INFERENCE:** production runs
that digest, and a PostGIS redeploy after the tag moves would pull a newer
development build under the existing extension catalog.

**PROPOSAL (not decided):** move production to the CI image. It cannot be
done in place: 16 → 17 is a major upgrade, and 3.7.0dev → 3.5.2 is an
extension downgrade. At 19 MB, a dump and restore is the simple path.

0. Optional stop-gap: set the PostGIS image to
   `postgis/postgis@sha256:afaf08e1…` (the digest above). The bits stay the
   same, but PostGIS restarts.
1. Rehearse locally. Take a dump ("Manual database backup", below; it is
   client data), restore it with `pg_restore --no-owner` into the
   `compose.yaml` database, read every `pg_restore` warning, check that
   `alembic current` says `0011`, and run the app against it.
2. On Railway, create a new service from the pinned 17-3.5 image with the
   same `POSTGRES_INITDB_ARGS` and a new volume.
3. Announce a short write freeze to Campo Digital. Take the final dump,
   restore it into the new service, compare row counts of
   `platform.transelec_resumen_row`, `platform.product_grant` and
   `platform.audit_event`, and point the app's `POSTGRES_*` variables at
   the new service. Deploy, then run the smoke checks and a real sign-in.
4. Rollback: leave the old service and its volume untouched and point the
   variables back. Anything written after the cutover is lost on rollback.
5. Delete the old service only as a separate, later decision.

**RESULT (rehearsal of step 1, 2026-10-04).** The production dump was taken
inside the PostGIS container (see "Without the TCP proxy" below). It was
161,224 bytes, with its sha256 verified on both ends. It was restored into
a throwaway container from the pinned 17-3.5 image, started with
production's `POSTGRES_INITDB_ARGS`, so TLS came up `on`.

- A plain `pg_restore` reports two errors, both from PostGIS topology. The
  image's init script already created the `topology` schema, and 3.7.0dev's
  `topology.topology` has a `useslargeids` column that 3.5.2 lacks. Both
  topology tables are empty in production, and no migration or app code
  uses topology. **DECISION:** restore with those entries filtered out:

  ```sh
  pg_restore --list prod.dump | grep -v -E " topology | SCHEMA - topology" > toc.list
  pg_restore --no-owner --no-privileges -L toc.list -d <db> prod.dump   # exit 0, no errors
  ```

  The target database must come from `template_postgis`, or have
  `CREATE EXTENSION postgis` run first.
- All 27 tables matched production's row counts exactly, including
  `platform.transelec_resumen_row` (2,187), `platform.audit_event` and
  `platform.product_grant`.
- Against the restored database, `alembic current` reports `0011 (head)`
  and `upgrade head` has nothing to do. The API's `/health` and `/ready`
  answer `200`, and with a dev session `/api/transelec/summary` answers
  `200` with its full structure.

**LIMITATION:** the rehearsal ran locally, not on Railway, and with dev
auth rather than Google sign-in. Steps 2–3 still have to prove the Railway
side.

## Manual database backup

The 2026-09-28 decision above stands: nothing backs up production on a
schedule. `scripts/backup_prod_db.sh` is the on-demand substitute. It copies
the production PostgreSQL database to this machine with `pg_dump`, run by
hand by someone with Railway access, for example before a migration or a
risky deploy.

It dumps the whole database, so it includes the grants
(`platform.product_grant`) and audit history (`platform.audit_event`) that
the decision says cannot be rebuilt. **LIMITATION:** it does not copy the
uploaded workbook files on the `/data` volume (see "Object storage").

1. On Railway, enable the PostGIS service's TCP proxy. This exposes the
   database on a public host and port while it is on.
2. Build the public URL and pass it through the environment only, never as
   an argument or in a file. **FACT (2026-10-04):** the PostGIS service
   defines no `DATABASE_PUBLIC_URL`. Its `DATABASE_URL` and
   `DATABASE_PRIVATE_URL` point at the private network. Compose it from the
   TCP proxy's host and port and the service's `POSTGRES_USER`,
   `POSTGRES_PASSWORD` and `POSTGRES_DB`, as
   `postgresql://USER:PASSWORD@HOST:PORT/DB`. The server accepts the
   script's `PGSSLMODE=require` (see "PostGIS image"), and `pg_dump` must
   be version 16 or newer:

   ```sh
   read -rs DATABASE_PUBLIC_URL && export DATABASE_PUBLIC_URL
   scripts/backup_prod_db.sh
   unset DATABASE_PUBLIC_URL
   ```

3. Disable the TCP proxy again.

**Without the TCP proxy** (used on 2026-10-04, no Railway setting changed):
run `pg_dump` inside the PostGIS container over `railway ssh`. Use the local
socket (`-h /var/run/postgresql`), because the container's `PGHOST` points
at the private network. Write the dump to a temp file, print its sha256, and
stream it back base64-encoded, deleting the temp file in the same command.
Decode it locally into `~/campo-digital-backups` (mode `600`) and compare
the checksum. No password leaves the container, and the database is never
exposed publicly. Its `pg_dump` is the server's own version.

What the script guarantees, from its own code:

- it refuses to run without `DATABASE_PUBLIC_URL`;
- it requires TLS (`PGSSLMODE=require` unless already set), because the
  proxy crosses the public internet;
- it writes to `$CAMPO_BACKUP_DIR` (default `~/campo-digital-backups`,
  directory mode `700`, files `600`), outside the repository;
- it writes `<name>.partial` and renames it only after `pg_restore --list`
  reads the archive back, so a file without `.partial` is complete.

`pg_dump` and `pg_restore` must be on the `PATH`, at a major version no older
than the server's: `pg_dump` refuses to dump a newer server.

**LIMITATION:** no restore of one of these dumps has been tested.
`pg_restore --list` proves the archive is readable, not that it restores
cleanly; the target database needs PostGIS.

The dumps are client data. Keep them out of the repository and out of the
OneDrive source root.

## Object storage

`app.object_store` currently ships only `LocalObjectStore`. Outside
production, `CAMPO_OBJECT_STORE_ROOT` defaults to the relative
`.local/object-store`. **DECISION (2026-09-25):** in `APP_ENV=production`
it must be set explicitly to an **absolute** path, in practice the mount
point of a persistent volume. Without it, uploads answer `503` and
`GET /ready` answers `503 not_ready` (`app.object_store.resolve_object_store_root`).
The relative default resolved inside the container's writable layer, which
the host discards on every redeploy. Uploaded workbooks would have vanished
while their database rows survived.

`GET /ready` also writes and removes a probe file under the store root, so a
volume the process cannot write to fails readiness instead of failing the
first real upload.

**DECISION (2026-09-25):** an absolute, writable path is not enough either.
When the container starts as root (below), the entrypoint's
`mkdir -p /data/object-store` succeeds with **no volume attached**, straight
onto the container layer, and the probe then passes. So in production the
root must also lie under a mount point other than `/` that is not `tmpfs`
or `ramfs`, read from `/proc/self/mountinfo`
(`app.object_store.require_persistent_mount`). Otherwise uploads answer
`503` and `/ready` answers `503 not_ready`, and the check runs before the
store creates any directory. **LIMITATION:** this proves that a filesystem
is mounted there. It does not prove the host keeps that filesystem across
deploys. Only the host's volume configuration does that.

### Persistent volume ownership

The image runs as the non-root `campo` user (uid 999). Hosts such as Railway
mount volumes owned by root, which `campo` cannot write. The image's
entrypoint (`scripts/container/entrypoint.sh`) handles this: when the
container is started as root, and only then, it creates
`CAMPO_OBJECT_STORE_ROOT`, hands it to `campo`, and drops privileges with
`setpriv` before the API starts. Under the default user it only execs the
command. The API process never runs as root.

**RESULT** (local Docker, 2026-09-25, not Railway): with a root-owned named
volume at `/data` and `CAMPO_OBJECT_STORE_ROOT=/data/object-store`:

- started as `campo`: `/ready` returned `503` (store not writable);
- started as root: uvicorn ran as uid 999, `/data/object-store` was owned by
  `campo`, and `/ready` returned `200` (under `APP_ENV=staging`; production
  additionally requires TLS to PostgreSQL, which the local test database
  does not offer);
- a harmless probe object written through `app.deps.get_object_store()`
  was read back byte-identical from a **new** container on the same volume;
- `APP_ENV=production` with no `CAMPO_OBJECT_STORE_ROOT`: `/ready` `503`.

**RESULT** (local Docker, 2026-09-25, not Railway; image built from this
branch). `APP_ENV=production` with the complete Google configuration, a
PostgreSQL that accepts TLS (`sslmode=require`), started as root, and
`CAMPO_OBJECT_STORE_ROOT=/data/object-store`:

- **no volume attached:** the entrypoint created `/data/object-store`
  (owned by `campo`) on the container layer, with no `/data` entry in
  `/proc/self/mountinfo`. The API started, and `/ready` returned
  `503 {"status":"not_ready"}`;
- **named volume at `/data`:** `/ready` returned `200`, and PID 1 was `uv`
  (which runs uvicorn) at uid 999;
- **`railway.json`'s start command** passed as the container's whole
  command with the image entrypoint cleared, which is what Railway does
  with a start command: the entrypoint log line appeared, PID 1 ran at
  uid 999, and `/ready` returned `200`.

### Railway build and start

Railway replaces the image's `ENTRYPOINT` with a service's custom start
command ("the start command overrides the image's `ENTRYPOINT` in exec
form", docs.railway.com/guides/start-command, read 2026-09-25). The service
runs as root (`RAILWAY_RUN_UID=0`) so the entrypoint can take ownership of
the volume. A start command that skipped the entrypoint would therefore run
the API **as root**, and would never chown the volume.

**DECISION (2026-09-25), superseded 2026-10-04:** `railway.json` (config as
code, which Railway applies over dashboard values) pinned the values below.
They are now declared in `.railway/railway.ts` (see "Railway Infrastructure
as Code" below) and stored on the service, and `railway.json` is removed:

- `build.builder = DOCKERFILE`, `build.dockerfilePath = Dockerfile`;
- `deploy.startCommand` = the entrypoint followed by the image's own `CMD`,
  so an override is harmless whatever the dashboard says;
- `deploy.healthcheckPath = /ready`.

`apps/api/tests/test_railway_config.py` fails if the start command stops
being exactly `ENTRYPOINT + CMD` from the `Dockerfile`.

**What is and is not verified about the current Railway build.**
**INFERENCE:** production (deployment of `0c45b38`, 2026-09-17) was built
from the `Dockerfile`, because it serves the compiled dashboard from the API
process (`GET /transelec` answers `200 text/html`), and only the
Dockerfile's first stage builds that into the image. **Not verified** from
the repository: the builder recorded in the Railway service, and whether
the service has a custom start command. Railway's build log names the
builder. After this change, **each deploy log must start with a
`campo-entrypoint: started as root; …; dropping to campo` line**. If it is
missing, the entrypoint did not run.

### Railway settings

On the Railway service that runs this image:

| Setting | Value |
|---|---|
| Volume mount path | `/data` |
| `CAMPO_OBJECT_STORE_ROOT` | `/data/object-store` |
| `RAILWAY_RUN_UID` | `0` (Railway's documented setting for a non-root image with a volume; the entrypoint drops back to `campo`) |
| Healthcheck path | `/ready` (stored on the service; declared in `.railway/railway.ts`) |
| Custom start command | the entrypoint + the image's `CMD` (stored on the service; declared in `.railway/railway.ts`) |
| Pre-deploy command | `.venv/bin/alembic upgrade head` (stored on the service; declared in `.railway/railway.ts`) |
| Builder | `RAILPACK` stored, with `dockerfilePath = /Dockerfile`, which makes Railway build the Dockerfile (see below) |
| Config file path | none (`railwayConfigFile` is `null`) |

**LIMITATION:** a Railway volume is a single-instance disk. The service must
stay at one replica, and the volume is not a backup. A managed object-store
backend remains future work.

### Railway Infrastructure as Code: `.railway/railway.ts`

**FACT (Railway CLI 5.63.1, 2026-10-04):** Config as Code (`railway.json`)
is deprecated, and Railway stops reading it on **2026-12-01**.
`.railway/railway.ts` is its replacement. It declares the app service: its
GitHub source, the Dockerfile builder, the start command, `/ready`, the
pre-deploy migration (until now set only in the dashboard), the `/data`
volume, and every variable through `preserve()`, which keeps the value in
Railway and out of the repository. PostGIS is not declared and is left
alone.

Railway does not read `.railway/` when it deploys. The file changes nothing
until someone runs `railway config apply`.

**RESULT (2026-10-04, `railway config plan` against production):** with
the file as committed, the plan reports no changes. An earlier draft that
declared only the start command, healthcheck and pre-deploy planned to
**delete all 15 production variables** (database credentials, the Google
client secret, `PLATFORM_TOKEN_ENCRYPTION_KEY`), detach the `/data` volume
and clear the source and builder. Once the service is declared, an apply
treats the file as the whole truth for it. Anything left out is removed,
not left alone.

So a variable added in the dashboard must also be added to the file as
`preserve()`, or the next apply deletes it. `apps/api/tests/test_railway_config.py`
keeps the start command equal to the Dockerfile's and fails if a variable
value is ever written into the file. It cannot see Railway, so the plan is
the only check that the variable list is complete.

**Rollout (2026-10-04):**

1. `railway config plan --detailed-exit-code` against production exited
   `0` ("already up to date").
2. `railway config apply --yes` reported the same and **wrote nothing**.
   **FACT:** `railway config partials list` still shows "No named partial
   ownership". A zero-change apply records no ownership; the first apply
   that changes something will.
3. `railway.json` and its tests were removed. The tests now check the same
   guarantees against `.railway/railway.ts`.

**FACT (Railway API `serviceInstance`, 2026-10-04):** the start command, the
`/ready` healthcheck and the pre-deploy command are stored on the service,
so they do not depend on `railway.json`. The stored builder is `RAILPACK`,
with `dockerfilePath = /Dockerfile`, and Railway's `Builder` enum has no
Dockerfile value (only `HEROKU`, `NIXPACKS`, `PAKETO`, `RAILPACK`).
**INFERENCE:** the Dockerfile is chosen by `dockerfilePath`, not by the
builder enum, so builds stay Dockerfile builds without `railway.json`.

**RESULT (deploy `2193f7d5` of `58e8e68`, the first without `railway.json`,
2026-10-04):** the build log shows the Dockerfile's stages (`[runtime 15/16]
COPY scripts/container/entrypoint.sh`, …) and no Railpack, which confirms the
inference above. The deploy log starts with the `campo-entrypoint … dropping
to campo` line, `/ready` answers `200`, and the service still stores the
`/ready` healthcheck, the pre-deploy migration and the entrypoint start
command. `railway config plan` still reports no changes. The 2026-12-01
cutoff no longer affects this service.

### Before the first redeploy: files already in the container

**OPEN QUESTION (2026-09-25):** whether the running production container
holds uploaded workbooks. Deployments up to `0c45b38` stored uploads under
`CAMPO_OBJECT_STORE_ROOT`, defaulting to `/app/.local/object-store` in the
container layer. The next deployment starts from a fresh layer, so those
files are lost unless copied out first. Their database rows, and the
published dashboard data, which lives in PostgreSQL rows, survive either
way. Platform engineering has no Railway or production database access, so
this has to be run by someone who does, **before** redeploying:

1. In a shell on the **running** service (for example `railway ssh` from the
   Railway CLI):

   ```sh
   echo "root=${CAMPO_OBJECT_STORE_ROOT:-<unset: /app/.local/object-store>}"
   root="${CAMPO_OBJECT_STORE_ROOT:-/app/.local/object-store}"
   grep " /data " /proc/self/mountinfo || echo "no volume at /data"
   find "$root" -type f ! -path "*/_tmp/*" | wc -l
   du -sh "$root" 2>/dev/null
   ```

2. Against the production database (read-only):

   ```sql
   -- rows that expect a stored file
   SELECT id, object_storage_key
   FROM platform.source_snapshot
   WHERE object_storage_key IS NOT NULL
   ORDER BY id;
   -- the active published workbook, if any
   SELECT active_import_id, active_source_snapshot_id, updated_at
   FROM platform.transelec_dashboard_state;
   SELECT import_id, event_type, occurred_at
   FROM platform.transelec_publish_event
   ORDER BY id DESC LIMIT 5;
   ```

3. If step 1 finds files, copy the whole store out before redeploying, for
   example `tar -C "$root" -czf - . > object-store.tgz` streamed through the
   same shell. Restore it into `/data/object-store` once the volume is
   attached, keeping the `sha256/xx/…` layout, which is the object key. Then
   check that every `object_storage_key` from step 2 exists under the new
   root.

The copy is client data. Keep it out of the repository and out of the
OneDrive source root.

## Deployment classification

Per the design doc's required classification (local operational use /
synthetic staging / private real-data deployment), and per this task's own
scope (does not provision infrastructure, does not deploy anywhere, does not
put real Transelec data anywhere):

- **Ready for local operational use**: yes — build, run, health/readiness,
  non-root, and the full authenticated read path were all verified locally
  against a real (disposable, synthetic-schema-only) database, per the
  RESULT above.
- **Ready for synthetic staging**: not attempted here. `render.yaml`
  deliberately does not add a hosted deployment for this app (see Task 5's
  report §8.4 and ADR-007's classification of Transelec as blocked for
  public staging) — nothing in this task changes that.
- **Ready for a private real-data deployment**: no. This container has no
  way to authenticate anyone outside `APP_ENV=development` (see "Auth"
  above) — real per-user sign-in (Entra ID) is Task 7's scope. No cloud
  infrastructure was provisioned or priced by this task.

## Related documentation

[Transelec product overview](../README.md) ·
[Transelec dashboard](../dashboard/README.md) ·
[Source Contract V1](source-contract-v1.md) ·
[Platform documentation](../../../docs/platform/README.md)
