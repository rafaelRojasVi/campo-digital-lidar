# ADR-006 — Restrict dev-auth to development

## Status

Accepted. Supersedes ADR-005's "`APP_ENV=staging` and dev-auth" section
specifically. ADR-005 is not otherwise superseded — its staging-deployment
architecture (Blueprint shape, region choice, migration execution, object
storage, health check, etc.) stands.

## Context

ADR-005 deliberately left dev-auth enabled in `APP_ENV=staging`: at the time,
there was no managed identity provider decision yet
(`../platform/security-model.md` listed "session/token strategy" and
"production identity provider" as open), and `DevSessionStore` (in-process,
in-memory, seeded fixed dev identities) was the only session mechanism that
existed.

The Secure File Access slice (this slice) adds a real, Postgres-backed
session store (`platform.session`, migration `0007`,
`apps/api/app/session_store.py`'s `PlatformSessionStore`) that hashes session
secrets with SHA-256 and never persists the raw value — a durable mechanism
suitable for real (non-dev-auth) identities. It also adds the Entra
ID/Microsoft Graph settings and app-registration handoff
(`../platform/entra-app-registration-handoff.md`) needed for a later,
externally-gated task to wire up real Entra ID sign-in.

Dev-auth (`app.dev_auth`) lets any caller who can reach the API assume one of
a small set of fixed, seeded identities (including a bootstrap-admin-capable
one) with no credential check beyond an `identity_key` string. Leaving that
reachable on any deployment other than a local developer's own machine —
including a public staging URL — is an authentication bypass on that
deployment, not a convenience. Now that a real session mechanism exists, this
is a self-inflicted and no-longer-necessary exposure specifically in staging.

## Decision

1. `app.dev_auth.assert_dev_auth_allowed` now rejects every `APP_ENV` value
   except `"development"` (previously it rejected only `"production"`).
   Staging and test are now treated the same as production for dev-auth
   purposes.
2. The dev-auth router (`app.routers.dev_auth`) is mounted by `app.main` only
   when `APP_ENV == "development"` (previously: any value other than
   `"production"`).
3. The tests this changes:
   - `test_dev_auth_allowed_in_staging` -> `test_dev_auth_rejected_in_staging`
   - `test_dev_auth_routes_mounted_in_staging` ->
     `test_dev_auth_routes_not_mounted_in_staging`

## Consequences

- **Until real Entra ID sign-in lands, Render staging has no way to
  authenticate at all.** This is a known, accepted, temporary trade-off, not
  a mitigated gap — no fallback authentication mechanism exists for staging
  today. `GET /auth/me` and any endpoint requiring
  `app.deps.get_current_app_user` will 401 for every caller on staging until
  Entra sign-in is wired up. This is deliberately preferred over leaving a
  fixed-identity bypass reachable on a public URL.
- Local development is unaffected: `APP_ENV=development` still gets dev-auth
  exactly as before.
- Real sessions (`platform.session`, `PlatformSessionStore`) work today for
  any code path that can mint one, independent of dev-auth's fate — this
  decision only removes the dev-auth bypass, it does not add sign-in.
- Entra ID sign-in landing is a later, externally-gated task (it needs the
  tenant admin action described in
  `../platform/entra-app-registration-handoff.md`); this ADR does not depend
  on that task and does not assume a timeline for it.

## Related

- `ADR-005-render-staging-experiment.md` — the staging deployment this
  decision amends (dev-auth section only).
- `../platform/security-model.md` — "Session and token strategy" (now
  decided) and "Open decisions" (production identity provider, still open).
- `../platform/entra-app-registration-handoff.md` — the tenant-admin
  prerequisite for the follow-up Entra sign-in task.
