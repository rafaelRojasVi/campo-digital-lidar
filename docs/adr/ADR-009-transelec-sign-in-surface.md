# ADR-009 — The Transelec dashboard's sign-in surface, and its demo boundary

## Status

Accepted; point 4 superseded for Transelec by
`ADR-010-google-workspace-sign-in-for-transelec.md`. Extends
`ADR-006-restrict-dev-auth-to-development.md` and
`ADR-008-entra-sign-in-implementation.md` to the browser side. Neither is
superseded: the server-side gates both describe remain the authority, and
this decision adds no authentication mechanism.

## Context

The Transelec dashboard rendered a single generic "Sesión requerida" block on
any `401` from `GET /auth/me`, instructing the visitor to sign in through the
Campo Digital portal and come back. Locally that instruction was not
actionable from the page at all: the only way to obtain a session for
`/transelec` was to paste a `fetch()` call against `POST /auth/dev-login`
into the browser console. There was also no way to end a session from the
dashboard, so switching between an administrator and a viewer meant clearing
a cookie by hand.

That is workable for a developer and unusable in front of a stakeholder. The
product needs a sign-in screen of its own — but the seeded identities it
would offer (`dev-admin`, `dev-viewer`) are precisely the fixed-identity
bypass ADR-006 removed from every deployed environment, so the boundary
deciding whether to offer them carries real weight.

The obvious candidate boundary was the one `apps/portal` already uses:
`getCampoEnvironment()`, reading the build-time `VITE_CAMPO_ENV` variable.
It was rejected. That function treats *unset* as `'local'`, which is correct
for what it drives there (module copy and iframe URLs) but fails **open**
here: a hosted build whose environment variable was missing or mistyped
would advertise the seeded identities on a public URL.

## Decision

1. A `401` from `GET /auth/me` is treated as the signed-out state and renders
   a `LoginCard`, not a failure block. Every other session failure — an
   unreachable platform included — keeps its existing failure block, so an
   outage is never presented to a stakeholder as "please sign in".

2. The demo boundary is **Vite's own build mode**, `import.meta.env.DEV`,
   surfaced through `products/transelect/dashboard/src/runtime/environment.ts`.
   It is true only under `vite dev` and is replaced with the literal `false`
   in every `vite build` artifact — and every deployable artifact of this
   dashboard is produced by `vite build` (the `dashboard-build` stage of the
   root `Dockerfile`; `app.dashboard_static` serves only that `dist/`
   output). There is no configuration step that could be forgotten or
   overridden, because there is no variable to set.

3. The demo panel is **eliminated from deployed bundles, not merely hidden**.
   `LoginCard` tests `import.meta.env.DEV` as a literal so the bundler can
   fold it, and the entire demo branch — every seeded identity key, the
   dev-login path, the demo copy — lives in one module
   (`components/DemoSignIn.tsx`) that a production build therefore drops.
   Identity keys are written as literals inside that module rather than read
   from a shared constant: a top-level property read counts as a possible
   side effect, so Rollup would preserve it and leave `dev-admin` and
   `dev-viewer` as the sole survivors of an otherwise eliminated module.
   `DemoIdentityKey` stays in `api.ts` as a *type*, which TypeScript erases.

4. **Superseded for Transelec by
   `ADR-010-google-workspace-sign-in-for-transelec.md` (2026-09-17): the
   action is now `Continuar con Google`, routed to
   `GET /auth/google/login`, and the Microsoft panel has been removed from
   this bundle. Everything else in this decision — including the demo
   boundary and the no-fallback rule — is unchanged and still in force.**
   As originally decided: every non-development build instead offers
   `Continuar con Microsoft`, routed to the existing
   `GET /auth/entra/login` (ADR-008). When that
   endpoint answers `503` (tenant not configured) the panel says so and
   stops. There is deliberately **no fallback to demo sign-in**: outside
   development no such identity exists on the server either.

5. Sign-out is available wherever a session exists, through
   `POST /auth/logout` and the shared API client — so it carries the
   session-bound CSRF token `GET /auth/csrf` issues, like every other
   state-changing call in this application. It is labelled
   `Cambiar usuario` in local development and `Cerrar sesión` elsewhere;
   the label is the only thing that differs.

6. Session state is re-read from `GET /auth/me` after every sign-in and
   sign-out. Nothing is inferred from the login response body, so a session
   that did not actually take can never render as one that did, and no
   browser reload is needed to switch identity.

## Consequences

- The demo boundary is verified against the shipped bytes, not the source:
  `products/transelect/dashboard/tests/bundle/production-bundle.test.ts`
  runs `vite build` and asserts that no seeded identity key, dev-login path
  or demo string appears in the output, and that the Entra action does. The
  test was confirmed to fail when the build-time gate is removed.
- Role-based hiding of `Importar planilla` and `Versiones` remains
  presentation only. The server is unchanged and still answers `403` to a
  viewer's mutation attempt even with a valid CSRF token.
- No session material reaches `localStorage`, `sessionStorage`, a
  script-readable cookie, or the bundle. The session stays in the HttpOnly
  `campo_session` cookie; the CSRF token stays in module memory and is
  dropped on both sides of a sign-in and after a sign-out, because it is
  keyed by the session secret.
- A development build pointed at a hosted API renders the demo buttons and
  gets `404` from `POST /auth/dev-login`, which the panel reports as "no
  disponible en este entorno" rather than as a bare `Not Found`.

## Known gap, not addressed here

`POST /auth/logout` (`app/routers/session.py`) carries no
`Depends(require_csrf)`, unlike every other state-changing route in this API
(`routers/transelec.py`, `routers/ingestion.py`, `routers/access_admin.py`).
Confirmed against the running development API: a `POST` with a valid session
cookie and no token returns `204` and ends the session. A third-party page
can therefore force a sign-out. Both frontend clients already send the token,
so adding the dependency would be a one-line change — deliberately deferred
rather than made alongside a UI slice, since the integration tests covering
the session router could not be run in this worktree (see below). Tracked as
an open item.

## Related evidence

- `ADR-006-restrict-dev-auth-to-development.md` — the server-side gate this
  mirrors; `/auth/dev-login` is mounted only under `APP_ENV=development`.
- `ADR-008-entra-sign-in-implementation.md` — the identity provider every
  deployed build offers.
- `../platform/security-model.md` — session strategy and CSRF.
- Tests: `apps/api/tests/test_main_dev_auth_gate.py` (server side),
  `products/transelect/dashboard/tests/bundle/production-bundle.test.ts`
  (shipped artifact), `products/transelect/dashboard/src/App.test.tsx`,
  `products/transelect/dashboard/src/components/LoginCard.test.tsx`,
  `products/transelect/dashboard/src/runtime/environment.test.ts`,
  `apps/api/integration_tests/test_transelec_router.py`
  (`test_viewer_is_forbidden_on_every_mutation_route`).
