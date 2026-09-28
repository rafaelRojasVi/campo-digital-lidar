# Campo Digital Platform Security Model

## Status

Foundation-level security contract.

This document defines security principles that should hold locally and in a future managed environment. It does not yet select the final identity provider or final business roles.

## Security objectives

The platform may contain private client files, geospatial data, spreadsheets, project status, generated reports, source history, and measurement results. The system must prevent accidental public exposure and preserve traceability of important changes.

## Trust boundary

```text
Internet / users
      |
      v
authenticated application
      |
      v
FastAPI authorization boundary
      |
      +-- PostgreSQL/PostGIS
      +-- private object storage
      +-- ingestion/jobs
      |
      v
external source adapters
      |
      v
OneDrive / Microsoft Graph
```

Users must not connect directly to PostgreSQL. Private objects must not use permanent public bucket URLs.

## Local development

- no public DB port forwarding;
- local credentials stay in ignored environment files;
- private source files and generated private artifacts stay outside Git;
- OneDrive access is read-only by default;
- local admin tools never become public production services.

## Authentication

Do not build a custom password system unless a real requirement forces it. Prefer a managed identity provider. Microsoft Entra ID is worth evaluating because the company already uses Microsoft/OneDrive collaboration, but it is not yet an accepted decision.

## Authorization

Authentication answers who the user is; authorization answers what they may do. Product authorization must be explicit and enforced server-side. Final roles must come from actual company workflows, not infrastructure assumptions.

## Database security

- no anonymous/public DB access;
- least-privilege application DB identity;
- controlled migration path;
- no implicit destructive migration on app startup;
- backups and restores tested;
- DB credentials never shipped to frontend code.

## Object security

Source snapshots and private generated artifacts are private by default. Browser delivery should use application authorization and time-limited signed access where appropriate.

## Secrets

Local: ignored environment/configuration files. Production candidate: managed
secret storage such as Secret Manager. Secrets never belong in Git,
documentation, browser bundles, or normal logs.

Repository history is scanned with Gitleaks using its maintained default rule
set. The scanner version and downloaded release checksum are pinned by
`scripts/check_secrets.sh`. Findings are redacted so detected credential values
are not copied into CI logs.

A real secret finding must be treated as a credential incident: rotate or
revoke the credential and assess whether repository-history remediation is
required. A false positive may be allowlisted only after inspection, and the
allowlist must be scoped as narrowly as practical.

**RESULT (2026-08-27)** — the initial full-history baseline scanned 61 commits
(approximately 2.09 MB) with Gitleaks 8.30.1 and found no leaks. Therefore the
repository begins automated secret scanning without an allowlist.

Live dependency-advisory checks are intentionally separate from this repository
quality gate because they depend on external vulnerability databases.

## Dependency vulnerability scanning

Supported runtime dependency graphs are checked separately from deterministic
repository quality gates.

The current blocking audit surface is:

- the locked Python base runtime plus API and Transelec extras;
- the locked optional geometry stack;
- production dependencies of the LiDAR dashboard.

Python dependency versions come from `uv.lock`; `pip-audit` inspects an exported
locked graph rather than resolving an independent application dependency graph.
The audit tool version is pinned by
`scripts/check_dependency_vulnerabilities.sh`.

Dashboard production dependencies are audited from the committed npm lockfile.

These checks depend on live vulnerability advisory services, so their results
may change without a repository change. They therefore run in dedicated
Security CI, including a scheduled weekly scan, and are intentionally excluded
from the deterministic `make check` gate.

Notebook tooling is an explicit `analysis` extra rather than part of the normal
application runtime dependency surface.

**RESULT (2026-08-27)** — the initial Python runtime/API, optional geometry, and
LiDAR dashboard production dependency baselines reported no known
vulnerabilities.

## Auditability

The platform should be able to answer which source snapshot produced a state, which ingestion run processed it, which user made an important operational change, when it happened, and which artifacts were generated from it.

## Environment isolation

LOCAL, STAGING, and PRODUCTION must not share credentials. Staging uses synthetic, sanitized, or explicitly approved data.

## AI-assisted engineering

Claude/AI tooling is not a runtime security component. It must respect private-data, architecture, permission, and evidence rules exactly like human engineering work.

## Session and token strategy

Decided: real (non-dev-auth) sessions are hashed-cookie, Postgres-backed
(`platform.session`, migration `0007`). The server issues a
`secrets.token_urlsafe(32)` raw secret as the session cookie value and
persists only its SHA-256 hash — the raw secret itself is never stored. See
`apps/api/app/session_store.py` (`PlatformSessionStore`) and
`../adr/ADR-006-restrict-dev-auth-to-development.md`.

## Cross-site request forgery (CSRF)

**FACT (before this change)** — no CSRF protection existed anywhere in this
repository: cookie-authenticated state-changing routes were guarded by the
`campo_session` cookie plus RBAC alone.

**DECISION** — one shared, cross-product mechanism lives in
`apps/api/app/csrf.py`. Every product's mutation routes consume it; none
gets its own.

Mechanism: a **session-bound, HMAC-signed synchronizer token**.
`GET /auth/csrf` mints `<nonce>.<signature>`, where `nonce` is a fresh
`secrets.token_urlsafe(32)` and `signature` is
`HMAC-SHA256(key=SHA-256(session cookie secret), msg=<version>:<nonce>)`.
Clients echo it in the `X-CSRF-Token` request header on every mutation.

Rationale for this over a plain double-submit cookie:

- the signing key is the caller's own `HttpOnly` session secret, so a token
  minted for one session never verifies for another — an attacker who can
  write a cookie on a sibling subdomain still cannot forge one;
- verification needs no new table, column, or configured server secret,
  because the key is re-derived per request from the cookie already present;
- the token is delivered only in a JSON response body, never in a cookie and
  never compiled into a frontend bundle. This API configures no CORS
  middleware, so a cross-origin page cannot read that response, and a
  cross-origin form/image/script cannot set a custom request header.

Properties:

- **fail-closed** — a missing, malformed, mismatched, or wrong-session token
  is `403`. There is no pass-through path, including for safe HTTP methods:
  the dependency is attached explicitly to mutation routes.
- `Origin`/`Referer` validation is an **independent second layer**. A
  declared origin must be the request's own host, an entry in
  `CSRF_TRUSTED_ORIGINS`, or — only under `APP_ENV=development`/`test` — a
  loopback development origin. A request declaring no origin at all (a
  non-browser client, which cannot be CSRF'd) is still subject to the
  mandatory token check.
- a request with no session cookie is answered `401`, not `403`: there is no
  cookie-authenticated action for an attacker to ride.
- `CSRF_TRUSTED_ORIGINS` must be configured wherever the frontend reaches
  the API through a proxy/rewrite that forwards the browser `Origin` but
  rewrites `Host` — the hosted `/api/*` rewrite does exactly this.

Session cookies stay `HttpOnly` and `SameSite=Lax`. `SameSite=Lax` reduces
but does not eliminate CSRF risk for state-changing `POST` routes, which is
precisely why the token check above is mandatory rather than belt-and-braces.

**RESOLVED (ADR-008, ADR-010)** — both real login flows' cookies
(`app.routers.entra_auth`'s and `app.routers.google_auth`'s session and
flow-state cookies) set `secure=True` whenever `APP_ENV != "development"`.
`apps/api/app/routers/dev_auth.py`'s own cookie is unaffected and
deliberately stays non-`Secure`: it only ever runs over plain-HTTP local
development, where a `Secure` cookie would never be sent at all.

## Open decisions

- **production identity provider — decided and implemented, now two of
  them**:
  - **Transelec: Google Workspace**
    (`ADR-010-google-workspace-sign-in-for-transelec.md`) — OIDC
    authorization code + PKCE S256, `id_token` verified with PyJWT against
    Google's JWKS, accepted only for the verified `hd` claim
    `campodigital.cl`, sign-in only (no Google token is stored). Chosen
    because the Entra gate below has never opened and this Workspace
    already exists. Application-side work is complete and tested against
    locally-signed tokens; the OAuth client and the final redirect URI are
    still external gates
    (`../platform/google-workspace-oauth-handoff.md`), and no real Google
    sign-in has run yet.
  - **LiDAR and Forestal: Microsoft Entra ID**
    (`ADR-008-entra-sign-in-implementation.md`), multitenant +
    personal-account audience, delegated `User.Read` only. Application-side
    work is complete; the tenant/app registration itself is still an
    external gate (`../platform/entra-app-registration-handoff.md`).

  Production startup requires `PLATFORM_TOKEN_ENCRYPTION_KEY` plus at least
  one *completely* configured provider; a half-configured provider fails
  closed (`app.identity_safety`).
- final user/role model;
- **production network topology / production cloud provider — still
  open**: `ADR-004-revisit-production-cloud-provider-choice.md` (Proposed:
  Azure) vs. `ADR-001-managed-production-platform.md` (Proposed: GCP);
  neither is accepted.
- signed-object delivery implementation;
- audit retention;
- backup retention and recovery objectives.
