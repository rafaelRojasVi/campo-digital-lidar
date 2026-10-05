# Rodales hosted release V1

## Status

Implemented 2026-09-29 on branch `feat/rodales-hosted-v1` (from `main` at
`c19fe1b`) and merged the same day (PR #67). This document is the runbook
for deploying it, importing the snapshot and granting the first admin, in
that order.

- **FACT (2026-10-05, checked from outside):** step 1 is done. Production
  answers `200` on `/rodales/`, with a bundle identical to one built from
  `main` at `f984e18`, and `401` on `/api/forestry/snapshots` signed out.
- **FACT (production dump of 2026-10-04 13:30 UTC):** steps 2 and 3 are
  not. Every `forestry` table is empty and no account holds a `forestry`
  grant, so the front door shows no Rodales card to anyone.
- **FACT (2026-10-05, the Railway variable and the same dump):**
  `PLATFORM_BOOTSTRAP_ADMINS` names a `forestry` address that is not the
  email Javier Guerra's Google account signs in with. The match is exact
  (`maybe_grant_configured_product_admins`), so his sign-ins never granted
  anything. Against the restored dump, locally: the configured value grants
  nothing; his sign-in address grants `forestry` ADMIN, and the Rodales card
  and the «Sin versión publicada» page appear.
- **DECISION (2026-10-05):** set the variable to his sign-in address
  (step 3). **RESULT (2026-10-05 12:30 UTC):** Rafael set it. Railway
  redeployed the same commit as deployment `96946275` (`SUCCESS`, pre-deploy
  ran no upgrade, the app started, which also validates the value, and
  `/ready` answers `200`). The grant is created at his next sign-in; whether
  that happened is not recorded here. Once he holds the grant,
  the snapshot can also be loaded with «Cargar versión»
  ([Upload, review, publish V1](upload-review-publish-v1.md), deployed)
  instead of the import script in step 2.

It is step 3 of the
[unified platform design](../../../docs/superpowers/specs/2026-09-28-unified-platform-design.md),
reduced to the smallest safe release: the existing read-only
[Dashboard V1](dashboard-v1.md) and [Read API V1](read-api-v1.md), served
under `/rodales/` behind the platform's Google Workspace sign-in and a
`forestry` product grant. The shapefile upload, review and "Publicar"
workflow (migration `0010`) is a later PR.

## What changed

| Area | Change |
|---|---|
| API access | Every `/api/forestry/*` route requires a platform session and a `forestry` grant (`Action.VIEW`, any role), via one router-level dependency (`require_forestry_viewer`). No session: `401`. Session without a forestry grant (e.g. Transelec only): `403`. The router is now mounted in every `APP_ENV`. |
| First admin | `PLATFORM_BOOTSTRAP_ADMINS` (`product:email` pairs) grants ADMIN at Google sign-in, see below. |
| Serving | The image builds `products/forestry/dashboard` with base `/rodales/` and serves it from the same FastAPI process (`app.dashboard_static`), next to the front door (`/`) and Transelec (`/transelec/`). `/rodales/assets/*` is cacheable; everything else stays `no-store`. |
| Front door | The "Rodales" card links to `/rodales/`. Cards are shown only for products the session holds a grant for, so only forestry grantees see it. |
| Dashboard | `401` sends the browser to the front door (platform build) or offers the development identities (local build). `403` shows "Sin acceso a Rodales". The header gets a "Proyectos" link on the platform. |
| CSP | Only on `/rodales` paths: `img-src 'self' data: https://tile.openstreetmap.org https://services.arcgisonline.com`. Every other directive, and every other path, is unchanged. |
| Snapshot import | `scripts/forestry_snapshot_import.py`: pinned archive, verify-before-commit, dry run by default, audited. |
| Image | Adds `products/forestry/src` and the Rodales build. `.dockerignore` now excludes `*.zip`, shapefile members, `*.xlsx`, `*.las/laz`, so client data cannot enter the build context. No snapshot is in the image. |

### Security model (DECISION)

- Authorization is server-side. The front door and the dashboard only hide
  what the API already refuses. `apps/api/integration_tests/test_forestry_route_access.py`
  enumerates every forestry route (including `feature-collection`, which
  carries all geometry, and `features/{ordinal}`, which carries the full
  source row) and proves `401` (anonymous, forged cookie), `403` (Transelec
  only, no grant) and `200` (forestry viewer, operator, admin).
- Every forestry role can read. There is nothing to write yet; upload and
  publish will require `Action.UPLOAD`/`Action.PUBLISH` in the later PR.
- `/rodales/` itself (the HTML/JS shell) is public, like `/transelec/`: it
  contains no client data. The data is only in `/api/forestry/*`.

### First Forestry admin (DECISION)

`PLATFORM_BOOTSTRAP_ADMINS=forestry:<email>` grants ADMIN on `forestry` to
that Google Workspace address when it signs in, only if:

1. the address matches (case-insensitive, exact, never by suffix);
2. that user holds **no** `forestry` grant yet (an existing grant of any role
   is never changed); and
3. **no one** holds ADMIN on `forestry` yet.

Other products and existing grants are untouched, so a Transelec admin gains
nothing on Rodales unless named for `forestry`. Once any forestry admin
exists the entry is inert, and should be removed. Each grant is audited as
`product_grant.changed` with `actor_app_user_id = NULL` and
`metadata.via = "bootstrap_config"`. A malformed value (unknown product,
missing `@`) fails the service at startup instead of silently granting
nothing. After that, the forestry admin grants others with the existing
`POST /api/auth/admin/product-grants/forestry` (audited, CSRF-protected);
there is no Accesos screen for Rodales yet.

The older Entra bootstrap (`PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID`/`_OBJECT_ID`)
grants **all** products. It must stay unset in Railway.

### Map tiles (FACT / LIMITATION)

- The map draws rodal geometry from `/api/forestry` on a canvas. Only the
  basemap tiles come from third parties: OpenStreetMap
  (`tile.openstreetmap.org`, "Mapa") or Esri World Imagery
  (`services.arcgisonline.com`, "Satelital"). "Sin fondo" requests no tiles.
- What a tile provider receives: the viewer's IP address, the tile
  coordinates (so, approximately which area of the estate is being looked
  at) and, for OpenStreetMap, the platform origin as `Referer`
  (`referrerPolicy: 'strict-origin'` on the tile layer: origin only, never
  the page path). No rodal attribute or geometry is sent.
- Why a `Referer` at all: the platform sends `Referrer-Policy: same-origin`,
  which would strip it, and OpenStreetMap's tile usage policy requires one.
- Why `data:` in `img-src` on `/rodales` only: Leaflet cancels off-screen
  tile downloads by assigning a hard-coded 1×1 `data:` GIF (a closure
  constant, not configurable). Without `data:` every pan logged CSP
  violations. Images cannot execute script; `script-src`, `style-src`,
  `connect-src` and `frame-ancestors` are unchanged.

## Differences between the deploy branch and main (FACT, 2026-09-29)

The request named `feat/transelec-ux-rearchitecture-v1` as the branch
Railway deploys. `origin/feat/transelec-ux-rearchitecture-v1` (`2a89842`) is
0 commits ahead of and 32 behind `origin/main` (`c19fe1b`). `main` has
everything that branch has plus #63–#66: the forestry merge (#64), the front
door at `/` with Transelec moved to `/transelec/` (#65) and the redesigned
sign-in (#66). On 2026-09-28 Railway was switched to deploy from `main` and
production was observed serving `c19fe1b`. This work therefore branches
from, and targets, `main`. Deploying the old branch would roll production
back to before the front door. (Railway settings cannot be read from this
repository; confirm in the Railway UI which branch the service tracks.)

## Verification done (RESULT, 2026-09-29, local only)

- Python: full unit suite (899 passed), full integration suite against an
  isolated PostGIS 17-3.5 container (384 passed), `migration_check.py`,
  ruff, ruff format, mypy (254 files).
- Frontends: Rodales vitest 86 passed, tsc, oxlint; portal vitest 79
  passed, tsc.
- The Docker image builds; it contains the Rodales build and
  `forestry_ingestion`, and no `.zip/.shp/.dbf/.xlsx/.las` file.
- The image was run with `APP_ENV=staging` (the same headers as production,
  including HSTS) against the isolated database holding the real snapshot
  (imported with the script below), in Chromium:
  - a forestry viewer sees the Rodales card, opens `/rodales/`, and the map
    shows 1,568 polygons, 10,422.61 ha, 7 invalid geometries, 72 code
    differences; OSM and Esri tiles load; "Sin fondo" loads none; **0
    console errors or CSP violations**;
  - a Transelec-only admin sees no Rodales card, and `/rodales/` shows
    "Sin acceso a Rodales";
  - an anonymous visitor to `/rodales/` is sent to `/`;
  - `/api/forestry/snapshots` answers `401` anonymously.
- `make forestry-dev` works locally at `http://127.0.0.1:<port>/rodales/`:
  development sign-in as Dev Admin shows the local Degenfeld snapshot;
  Dev Viewer (Transelec only) gets "Sin acceso a Rodales".
- The import script against the isolated database with the real archive:
  wrong host refused (exit 2); another archive refused by SHA-256 before
  connecting (exit 2); dry run verified all ten checks and wrote 0 rows;
  `--commit` wrote 1 snapshot / 1,568 features and one
  `forestry.snapshot.imported` event; a second `--commit` was idempotent.

Not verified: the production Google sign-in round trip to `/rodales/`,
Railway itself, and the production PostGIS connection (TLS through a Railway
TCP proxy). No production system was touched.

## Runbook: deploy, import, grant

Every step is manual and is Rafael's to run. Do them in order.

### 1. Merge and deploy (no data yet)

1. Review and merge the PR into `main`. It has **no migration**; the
   Railway pre-deploy `alembic upgrade head` is a no-op.
2. In Railway, confirm the service deploys `main`, and that
   `PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID` / `PLATFORM_BOOTSTRAP_ADMIN_OBJECT_ID`
   are **unset**. Do not set `PLATFORM_BOOTSTRAP_ADMINS` yet.
3. Deploy. Then check from outside:

   ```sh
   BASE=https://campo-digital-platform-production.up.railway.app
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/api/forestry/snapshots  # 401
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/rodales/                 # 200
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/transelec/               # 200
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/docs                     # 404
   curl -sI $BASE/rodales/ | grep -i content-security-policy  # includes the two tile origins
   curl -sI $BASE/transelec/ | grep -i content-security-policy  # img-src 'self' only
   ```

   Nobody holds a `forestry` grant yet, so nobody sees a Rodales card and
   no data is readable.

### 2. Import the snapshot (verified before it is written)

Runs from Rafael's machine, where the private ZIP lives (OneDrive). The ZIP
never goes to GitHub, to the image, or to Railway's disk: only the parsed
rows reach the database.

1. In Railway, enable a **TCP proxy** on the PostGIS service (temporary).
   Note its public host and port, and the database name, user and password
   from the PostGIS service variables.
2. From the repository root (this branch or `main` after merge):

   ```sh
   export APP_ENV=production            # forces sslmode=require
   export POSTGRES_HOST=<proxy host> POSTGRES_PORT=<proxy port>
   export POSTGRES_DB=<db> POSTGRES_USER=<user>
   read -rs POSTGRES_PASSWORD && export POSTGRES_PASSWORD   # not in shell history
   export CAMPO_DIGITAL_SOURCE_ROOT="/mnt/c/Users/Rafael/OneDrive/00 Hub Digital CampoDigital"

   # Dry run: verifies everything, writes nothing.
   uv run --extra api python scripts/forestry_snapshot_import.py --expect-host "$POSTGRES_HOST"
   ```

   Expected: ten `ok` lines (fingerprint `19beaed5…60bd1`, layer
   `Gdb_Degenfeld2026_mv`, EPSG 32718, 1568 features, 10422.61 ha,
   104226106.7 source units², 7 invalid, flags
   143/32/8/7/2/2, 1 class difference, 72 code differences) and
   `DRY RUN OK`. Any other outcome: stop; nothing was written.
3. Write it:

   ```sh
   uv run --extra api python scripts/forestry_snapshot_import.py --expect-host "$POSTGRES_HOST" --commit
   ```

   Expected: the same ten `ok` lines and `COMMITTED: snapshot id <n> (new),
   verified.`
4. **Disable the TCP proxy.** Then rotate the PostGIS password (it was
   exposed through the proxy and was previously pasted into a chat on
   2026-09-28), and make sure the app service's `POSTGRES_PASSWORD` follows
   (check whether it is a Railway variable reference or a literal copy).
   Redeploy/restart the app and confirm `/ready` answers 200.

If the connection fails on TLS: stop. Do not retry without TLS over a public
proxy; ask first.

### 3. Grant the first Rodales admin

1. Set `PLATFORM_BOOTSTRAP_ADMINS=forestry:<email of the first Rodales
   admin>` on the app service (OPEN QUESTION: who; see below). Restart.
2. That person signs in at `/`. The "Rodales" card appears; `/rodales/`
   shows the map with 1.568 polígonos and 10.422,61 ha.
3. Remove `PLATFORM_BOOTSTRAP_ADMINS` (it is inert from now on, but should
   not linger) and restart.
4. The admin grants other people (who must have signed in once) with
   `POST /api/auth/admin/product-grants/forestry` `{"email": …, "role":
   "viewer"}`, the same API Transelec admins use.

### Rollback

- Code: redeploy the previous `main` commit (`c19fe1b`). The imported rows
  stay in the database but are unreachable, because that version does not
  mount the forestry API in production.
- Access: there is no revoke endpoint yet; to remove a forestry grant,
  delete its `platform.product_grant` row (and record why).
- Data: the snapshot can be re-imported at any time with the script (it is
  idempotent). No backups exist on the current plan (accepted 2026-09-28).

## LIMITATIONS

- (Superseded by [Upload, review, publish V1](upload-review-publish-v1.md):
  the dashboard now shows the *published* snapshot.) The dashboard shows the *latest ingested* snapshot. That is why the import
  script refuses a database holding any other Forestry snapshot. A second
  snapshot needs the publish marker (later PR).
- `feature-collection` returns about 9 MB of uncompressed JSON on every
  page load; there is no response compression yet.
- Rodales has no Accesos screen; grants are managed through the API.

## OPEN QUESTIONS (for Campo Digital / Rafael)

- Who is the first Rodales admin (the `PLATFORM_BOOTSTRAP_ADMINS` email)?
- Esri World Imagery terms for this use: the satellite basemap is used
  without an ArcGIS account. Confirm it is acceptable, or offer only
  OpenStreetMap and "Sin fondo".
- Is sending tile requests (viewer IP + map area) to OpenStreetMap/Esri
  acceptable to Campo Digital for the Degenfeld estate? (Assumed yes on
  2026-09-28; "Sin fondo" avoids it.)

## Related documentation

[Forestry product](../README.md) ·
[Dashboard V1](dashboard-v1.md) ·
[Read API V1](read-api-v1.md) ·
[Ingestion Substrate V1](ingestion-substrate-v1.md) ·
[Resumen en español](es/rodales-en-linea.md)
