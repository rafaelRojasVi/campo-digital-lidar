# Unified Campo Digital platform: one sign-in, then choose a project

Date: 2026-09-28. Status: approved in conversation with Rafael. Step 1 (front
door) is implemented on `feat/unified-platform` and not yet deployed
([plan](../plans/2026-09-28-unified-platform-front-door.md)). On the platform,
Transelec's bar button is "Proyectos", back to the front door, in place of
"Cerrar sesión": a separate link did not fit the admin bar at laptop widths.

## Goal

Campo Digital users open one address, sign in once with Google Workspace, and
choose the project they work on (Transelec, Rodales, and later LiDAR). Each
project keeps its own frontend, API and data model (see
[product boundaries](../../platform/product-boundaries.md)); only the front
door, the session and access management are shared.

Priority: show Javier the Rodales work that already exists as soon as it is
safe, then make the Rodales backend as robust as Transelec's (import with
review and publish, versions, audit).

## Evidence (FACT, verified 2026-09-28)

- Railway production serves one FastAPI container. It serves the Transelec
  build from the same process (`app/dashboard_static.py`), with Google
  Workspace sign-in (ADR-010), sessions, CSRF, security headers and audit.
- The Google callback already redirects to `/` (`_POST_LOGIN_REDIRECT_PATH`).
- `/` currently answers with the Transelec `index.html`, and Transelec's build
  uses base `/`, so its assets live at `/assets/*`.
- `platform.product_grant` already allows `lidar`, `forestry`, `transelect`.
- The Transelec bootstrap admin grants only `transelect`, and only to a user
  holding no grant at all (`access_repository.maybe_grant_transelec_bootstrap_admin`).
- The forestry read API has no authentication and is mounted only under
  `APP_ENV=development` (`test_main_forestry_gate.py`).
- The Rodales map loads tiles from `tile.openstreetmap.org` and
  `services.arcgisonline.com`; the production CSP is `img-src 'self'`.
- `apps/portal/` is a local/staging company portal that composes products in
  iframes; the production CSP forbids framing (`frame-ancestors 'none'`).
- Forestry data is ingested today from `CAMPO_DIGITAL_SOURCE_ROOT` (OneDrive),
  which does not exist on Railway.

## Design

### URL layout (one origin)

| Path | Serves | Vite `base` |
|---|---|---|
| `/` | Front door (sign-in, project picker, Accesos) | `/` |
| `/transelec/...` | Transelec dashboard | `/transelec/` (was `/`) |
| `/rodales/...` | Rodales dashboard | `/rodales/` |
| `/api/...` | Platform API (unchanged prefix) | n/a |

Each build owns its asset prefix (`/assets`, `/transelec/assets`,
`/rodales/assets`), so the three builds cannot collide. The API serves the
three `dist` directories; each app gets its own SPA fallback limited to its own
prefix, and `/api`, `/health`, `/ready` stay reserved. Only the three asset
prefixes are cacheable; everything else keeps `Cache-Control: no-store`.

DECISION: navigation, not iframes. Each project is its own page on the same
origin; the session cookie (path `/`) is shared. This keeps
`frame-ancestors 'none'` and needs no cross-origin configuration.

### Front door (`apps/portal`, new production mode)

- Signed out: Campo Digital brand and "Iniciar sesión con Google"
  (`/api/auth/google/login`). In development, the existing dev sign-in.
- Signed in: "Hola, <nombre>", one card per product the user holds a grant for
  (from `GET /api/auth/me`), "Cerrar sesión". LiDAR shows as "Próximamente"
  only if the user holds a `lidar` grant; it links nowhere.
- Admins of any product see "Accesos".
- The local/staging iframe modes stay as they are for `make campo-demo`; the
  production mode is selected at build time like the existing
  `VITE_CAMPO_ENV`.

Inside each product, the header gets a "Cambiar proyecto" link to `/`. A
product page that receives `401` sends the browser to `/` instead of showing
its own sign-in form (Transelec's local dev sign-in buttons stay available in
development only).

### Accesos for every project

The front door lists users and their role per product, using the existing
admin product-grant endpoints (`POST /api/auth/admin/product-grants/{product}`)
and grant listing. An admin can change roles only for products they
administer (`Action.MANAGE_ACCESS` per product, enforced server-side as today).

Bootstrap, generalized: a configured list of `product:email` pairs
(`PLATFORM_BOOTSTRAP_ADMINS`, for example `forestry:javier@campodigital.cl`)
grants ADMIN on that product at sign-in **only if that user holds no grant for
that product**. It is recorded as an audit event with no actor. The existing
Transelec variable keeps working.

### Rodales online

- Every `/api/forestry/*` route requires a session and a `forestry` grant
  (`Action.VIEW`), through one router-level dependency. A test enumerates every
  forestry route and asserts `401` without a session and `403` with a grant for
  another product only. The router is then mounted in every environment.
- The dashboard is served at `/rodales/` with the Campo Digital header.
- CSP: `img-src` adds exactly `https://tile.openstreetmap.org` and
  `https://services.arcgisonline.com`. The tile providers see which map area
  is viewed; rodal geometries and attributes never leave the platform. "Sin
  fondo" requests no tiles.
- **Importar shapefile** (admin/operator with `Action.UPLOAD`, CSRF):
  1. Upload a `.zip`. The pre-auth body limit applies before reading.
  2. The ZIP is read in memory, never extracted by member name. Limits: member
     count, total uncompressed size and per-member ratio (zip-bomb guard); only
     the expected `.shp/.shx/.dbf/.prj/.cpg` members of one layer are accepted.
  3. The existing forestry ingestion validates and stores it as a snapshot
     **pending review**. The page shows the summary (features, hectares, CRS,
     invalid geometries).
  4. "Publicar" makes it the snapshot the dashboard shows. Uploading the same
     content again is recognised by its fingerprint.
  Every step is audited (`forestry.snapshot.uploaded`, `.published`).

  The dashboard today shows the "latest ingested" snapshot. It will show the
  **published** snapshot, which needs a published marker (migration `0010`,
  expand-only).

### Security summary

- Authorization is server-side for every product route; the front door only
  hides what the server already refuses.
- The OAuth callback always lands on `/`; there is no `next=` parameter, so the
  sign-in cannot be used as an open redirect.
- One session: "Cerrar sesión" anywhere ends it everywhere.
- API responses stay `no-store`; only hashed build assets are cacheable.
- No backups exist on the current Railway plan (accepted 2026-09-28). Rodales
  can be restored by re-importing the shapefile; grants and audit cannot.

## Delivery steps (each deployable on its own)

1. **Front door**: URL layout, portal production mode, "Cambiar proyecto" and
   the `401` redirect in Transelec. Transelec keeps working.
2. **Accesos for every project**, plus generalized bootstrap.
3. **Rodales online**: protected API, `/rodales` serving, CSP tiles, Importar
   shapefile with review and Publicar.
4. Later, separate spec: saving cuts (versions, history, export), as agreed on
   2026-09-28.

## Testing

- API: route-enumeration auth tests for forestry; static serving and SPA
  fallback per prefix; bootstrap per product; ZIP limits (oversized, too many
  members, zip bomb, path-like names, missing members); import, review and
  publish integration tests against PostGIS; CSP header contents.
- Frontends: vitest for the front door states (signed out, signed in with 0, 1
  or 2 products, admin), "Cambiar proyecto", the `401` redirect.
- A browser check of the three prefixes against a production-like build.
- UI work goes through the design-taste-frontend pass and the
  web-design-guidelines review.

## OPEN QUESTIONS (for Campo Digital)

- Who should be admin of Rodales at first (bootstrap email)?
- Is showing map tiles from OpenStreetMap/Esri acceptable for their estate
  views? (Assumed yes on 2026-09-28; "Sin fondo" remains available.)
- The Rodales workflow questions in
  `products/forestry/docs/es/preguntas-campo-digital.md` still apply.

## Out of scope

LiDAR hosting, approvals for geometry edits, cross-snapshot identity of rodales,
backups, a custom domain.
