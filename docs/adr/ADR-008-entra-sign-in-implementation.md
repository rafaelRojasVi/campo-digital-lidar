# ADR-008 — Microsoft Entra ID sign-in implementation

## Status

Accepted. Application-side implementation only — see "What remains
externally gated" below for what still requires a tenant administrator.

## Context

`ADR-006-restrict-dev-auth-to-development.md` removed the dev-auth bypass
from every non-development environment and added the durable session
mechanism (`platform.session`, `PlatformSessionStore`) a real identity
provider needs, but explicitly left "Entra ID sign-in landing" as a later,
externally-gated task. Until this ADR, no environment other than
development had any way to authenticate at all — `docs/platform/
entra-app-registration-handoff.md` already specified the tenant/app-
registration shape (multitenant + personal Microsoft accounts, minimal
`User.Read` scope, no client-credentials flow), and `app.config.Settings`
already carried the `ENTRA_*`/`PLATFORM_TOKEN_ENCRYPTION_KEY`/
`PLATFORM_BOOTSTRAP_ADMIN_*` fields, and `platform.ms_graph_grant`
(migration `0007`) already existed to store encrypted Graph tokens — but no
code used any of it.

Separately, auditing the existing auth surface for this task surfaced a
real production-integration defect unrelated to Entra itself: `GET
/auth/me` and `POST /auth/logout` lived in `app.routers.dev_auth`, mounted
only under `APP_ENV=="development"`. The frontend
(`apps/portal/src/lib/platformApi.ts`,
`products/transelect/dashboard/src/api.ts`) already calls both paths
unconditionally, and `ADR-006` itself asserted `/auth/me` would "401 for
every caller on staging" — which was not true; it would 404, since the
route did not exist there at all. A real (Entra) session would have had no
way to be inspected or ended outside development.

## Decision

1. **`app.entra_auth`** wraps `msal.ConfidentialClientApplication` behind a
   small `EntraOidcClient` protocol (`initiate`/`complete`), so
   `app.routers.entra_auth` depends on this module's interface rather than
   MSAL's dict-shaped API directly — the same adapter-boundary rule
   `app.object_store` uses for storage, and what lets the router's tests
   inject a fake client without a live tenant. The authority is the fixed
   `https://login.microsoftonline.com/common` endpoint, never a specific
   `ENTRA_TENANT_ID` — the app registration's audience is multitenant plus
   personal accounts, and scoping the authority to one tenant would
   silently break sign-in for every other account type that audience is
   meant to allow. `response_mode="form_post"` is used (MSAL's own
   recommended mode over the query-string default), so the callback is a
   `POST`, not a `GET`.
2. **`app.routers.entra_auth`** adds `GET /auth/entra/login` (redirects to
   Microsoft, storing PKCE/state in a short-lived, Fernet-encrypted,
   HttpOnly cookie — not server memory, since a real deployment may run
   more than one replica) and `POST /auth/entra/callback` (completes the
   flow, resolves/creates the `platform.app_user` row via
   `identity_kind="entra"`, `identity_key=f"{tenant_id}:{object_id}"`, runs
   `maybe_grant_bootstrap_admin`, stores any Graph access/refresh token
   pair encrypted in `platform.ms_graph_grant`, and mints a real
   `platform.session`). Mounted unconditionally, like `app.routers.csrf`:
   every non-development environment has no other way to authenticate.
   Missing `ENTRA_CLIENT_ID`/`ENTRA_CLIENT_SECRET` or
   `PLATFORM_TOKEN_ENCRYPTION_KEY` produce a `503` (an intentionally
   unavailable state), not a crash or a `404`.
3. **`app.token_crypto`** provides Fernet-based `encrypt_token`/
   `decrypt_token`, keyed by `PLATFORM_TOKEN_ENCRYPTION_KEY`. Used both for
   the login flow-state cookie and for `platform.ms_graph_grant`'s stored
   tokens — nothing sensitive is ever written to a cookie or a database
   column unencrypted.
4. **`app.identity_safety.require_production_identity_configuration`**
   fails `APP_ENV=="production"` startup closed if
   `ENTRA_CLIENT_ID`/`ENTRA_CLIENT_SECRET`/`PLATFORM_TOKEN_ENCRYPTION_KEY`
   are not all set — "no way to authenticate anyone in production" is a
   startup error, not a confusing `503` discovered on the first real
   sign-in attempt. Every other `APP_ENV` is unaffected (mirrors
   `app.db_safety`'s shape).
5. **`app.routers.access_admin`** adds product-grant onboarding:
   `GET`/`POST /auth/admin/product-grants/{product_key}`, gated by
   `Action.MANAGE_ACCESS` (`Role.ADMIN`) on that same product. Granting is
   by email (`app.access_repository.get_app_user_by_email`), because an
   operator does not know a grantee's Entra `tenant_id:object_id` — a
   grantee must already have signed in once (their `app_user` row, and its
   email, are created at that point by
   `resolve_or_create_app_user`'s new optional `email` parameter). This is
   the mechanism for Rafael to grant Javier `VIEWER` on `transelect`.
6. **`app.database.build_engine`** now passes `connect_args={"sslmode":
   "require"}` under `APP_ENV=="production"` only — a managed Postgres
   provider is reached over a network Campo Digital does not control,
   unlike local/staging Postgres on a private Docker network or container.
7. **`app.routers.session`** (new) takes over `GET /auth/me` and `POST
   /auth/logout` from `app.routers.dev_auth`, mounted unconditionally.
   Both cookies (`platform.session`/`campo_session` in the callback, the
   flow-state cookie in `/login`) now set `secure=` conditional on
   `APP_ENV != "development"` — the `security-model.md` "OPEN QUESTION"
   about the session cookie never carrying `Secure` is resolved for this
   real-session path (`app.routers.dev_auth`'s own cookie is unaffected: it
   only ever runs over local plain HTTP, where `Secure` would break it).

## What remains externally gated

Everything above is exercised by the test suite against a fake
`EntraOidcClient` — no live tenant exists yet. Per
`docs/platform/entra-app-registration-handoff.md`, still required from a
tenant administrator: create the Azure free account/Entra tenant; create
the app registration with the real production redirect URI; generate the
client secret; hand `ENTRA_TENANT_ID`/`ENTRA_CLIENT_ID`/
`ENTRA_CLIENT_SECRET` to platform engineering over a secure channel; do the
first real sign-in; set `PLATFORM_BOOTSTRAP_ADMIN_TENANT_ID`/
`_OBJECT_ID` from that sign-in's claims; then grant Javier's account
`VIEWER` on `transelect` via `POST /auth/admin/product-grants/transelect`.

## Consequences

### Positive

- Production/staging now have a real, non-dev-auth path to sign in, with
  no code path left that can authenticate a production caller without one.
- Token storage is encrypted at rest and never touches a cookie or the
  frontend build.
- The session-inspection/termination gap (`/auth/me`, `/auth/logout`
  unreachable outside development) is fixed platform-wide, not just for
  Entra — dev-auth-issued sessions still resolve through the same routes.

### Negative / trade-offs

- `PLATFORM_TOKEN_ENCRYPTION_KEY` is a new, must-not-be-lost secret: losing
  it makes every stored Graph grant permanently undecryptable (sessions
  are unaffected — they are hashed, not encrypted, and are simply
  reissued on the next sign-in).
- The Graph access/refresh token pair is stored even though Transelec's
  V1 pilot does not use OneDrive/Graph beyond sign-in (`User.Read` only) —
  deliberate, so the documented `Files.Read` escalation path needs no new
  storage/encryption code, only a scope change and re-consent.

## Related evidence

- `docs/platform/entra-app-registration-handoff.md` — the tenant/app-
  registration specification this implements against.
- `docs/adr/ADR-006-restrict-dev-auth-to-development.md` — the dev-auth
  removal and session mechanism this builds on.
- `docs/platform/security-model.md` — "Session and token strategy",
  "Cross-site request forgery", and "Open decisions".
- Tests: `apps/api/tests/test_entra_auth.py`,
  `apps/api/tests/test_token_crypto.py`,
  `apps/api/tests/test_identity_safety.py`,
  `apps/api/tests/test_main_production_identity_gate.py`,
  `apps/api/integration_tests/test_entra_auth_router.py`,
  `apps/api/integration_tests/test_access_admin_router.py`,
  `apps/api/integration_tests/test_session_router.py`,
  `apps/api/integration_tests/test_graph_grant_repository.py`.
