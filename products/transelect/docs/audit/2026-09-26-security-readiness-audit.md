# Transelec security readiness audit (2026-09-26)

## Scope

An independent review ahead of the first real Google Workspace sign-in by
Campo Digital. It covers:

- the Railway deploy branch `feat/transelec-ux-rearchitecture-v1` at
  `ddfe044`;
- PR #59 (`feat/transelec-dashboard-ux-pass`) at `fc71727`, which changes the
  dashboard, CI and a workbook skill, and does not touch the API.

Production checks were read-only. They consisted of about 30 anonymous GET
requests, one of which started a Google sign-in redirect that was never
completed. No scanner was run and no workbook was uploaded or published.
Local tests ran against a disposable PostGIS container and a synthetic
workbook generated from the integration-test fixture.

## What production is running

- **FACT**: the production JS bundle (`/assets/index-Bks9G7gK.js`) has the
  same SHA-256 as a local `npm run build` of `ddfe044`.
- **FACT**: production `/openapi.json` is identical to the schema `ddfe044`
  generates, and differs from the schemas of `af42e83` and `0c45b38`.
- **INFERENCE**: Railway serves `ddfe044`, the merge of PR #58. PR #59 is not
  deployed.

## Verified on Railway (read-only)

| Check | Result |
|---|---|
| `GET /api/auth/google/login` | `302` to Google with `response_type=code`, `scope=openid email profile`, `state`, `nonce`, `code_challenge_method=S256`, `hd=campodigital.cl`, and `redirect_uri=…/api/auth/google/callback` |
| Flow cookie | `HttpOnly; Secure; SameSite=lax; Max-Age=600; Path=/` |
| `/api/auth/dev-login`, `/auth/dev-login` | `404`: dev auth is not mounted |
| `/api/auth/entra/login` | `503`: Entra is not configured |
| Anonymous `/api/auth/me`, `/api/auth/csrf`, `/api/transelec/summary`, `/runs`, `/ingesta/jobs` | `401` |
| `http://` | `301` to `https://` |
| `/health`, `/ready` | `200` |
| Response security headers | **none**: no CSP, `X-Frame-Options`, HSTS, `nosniff` or `Cache-Control` on HTML or API responses |
| `/docs`, `/redoc`, `/openapi.json` | `200` without authentication |

The secure flow cookie and the missing dev-login route together show that
`APP_ENV` is not `development` in production. The Railway environment
variables themselves were not read.

## Findings

Severity reflects this deployment: one client, an authenticated
`campodigital.cl` Workspace, and a per-product grant on every data route.

### Medium: anonymous request bodies were received in full before authentication (fixed)

- **FACT**: FastAPI parses a multipart or JSON body before it resolves a
  route's dependencies. A local anonymous `POST /api/transelec/uploads` with
  a 400 MB file was written to a server temp file in full (peak 396,033,892
  bytes) before the `401`. `/ingesta/upload` and every JSON route behaved
  the same way. The 2 GiB `MAX_UPLOAD_BYTES` check ran only after the spool.
- Impact: anyone on the internet could fill the container's temporary disk or
  memory without an account.
- Fix: `app.http_hardening.RequestBodyLimitMiddleware` does three things:
  - Upload routes resolve the session cookie against `platform.session`
    (the same lookup `get_current_app_user` does) and answer `401` before
    reading the body when it is missing, forged, expired or revoked. The
    route still authenticates the user, checks CSRF and enforces the
    product permission.
  - Bodies are capped by `Content-Length` and while they stream: 64 MiB for a
    Transelec workbook, 2 GiB for `/ingesta/upload`, 1 MiB elsewhere, each
    plus 1 MiB multipart framing where it applies.
  - A body over its cap is answered `413`.
- After the fix, the same 400 MB request is refused in about 1 ms with 0
  bytes accepted.
- **FACT**, found in PR review: the first version of this fix only checked
  that a nonempty `campo_session` cookie was present, so
  `campo_session=anything` still bought a full upload-sized spool (up to
  2 GiB on `/ingesta/upload`) before the route's `401`. Local tests in
  `apps/api/integration_tests/test_upload_session_gate.py`, run with 64 KiB
  limits against real session rows, show missing, forged, expired and
  revoked sessions now read 0 body bytes on both upload routes, while a
  valid session still uploads.
- **DECISION**: 64 MiB for a workbook. The largest local `.xlsx` measured
  15.7 MB, so this leaves about 4× headroom.

### Medium: no cache or framing protection on authenticated responses (fixed)

- **FACT**, verified on Railway: API JSON, the CSV export and the dashboard
  shell carry no `Cache-Control`, no `X-Frame-Options` and no CSP
  `frame-ancestors`.
- Impact:
  - Client data may stay in the browser cache or history of a shared computer
    after sign-out.
  - Any site can frame the dashboard. `SameSite=Lax` currently keeps the
    session cookie out of cross-site frames, which limits clickjacking, but
    the dashboard exposes Publish, Restore and access grants, so framing is
    denied explicitly.
- Fix: `app.http_hardening.SecurityHeadersMiddleware` sets these headers:
  - `Cache-Control: no-store` on everything except the content-hashed
    `/assets/*`.
  - `X-Frame-Options: DENY`.
  - `X-Content-Type-Options: nosniff`.
  - `Referrer-Policy: same-origin`.
  - A restrictive `Permissions-Policy`.
  - `Strict-Transport-Security` in staging and production only.
  - A same-origin CSP (`default-src 'self'`, with no `unsafe-inline` and no
    `unsafe-eval`) that includes `frame-ancestors 'none'`.
- **RESULT**: both built dashboards, `ddfe044` and PR #59 `fc71727`, were
  served through the patched API. With Chromium signed in through dev auth
  and a synthetic workbook published, all nine pages loaded with **zero CSP
  violations** and rendered correctly.
- **DECISION**: FastAPI's `/docs` and `/redoc` load Swagger UI from a CDN
  with an inline script, so they get only `frame-ancestors 'none'`.

### Low: `POST /auth/logout` had no CSRF check (fixed)

- **FACT**: it was the only cookie-authenticated mutation without
  `require_csrf`.
- Impact: another site could force a sign-out. `SameSite=Lax` already blocks
  that from cross-site pages.
- Fix: the route now requires the CSRF token. Both frontends already send the
  token on every non-GET request, and a browser run confirmed `403` without
  it and `204` with it.

### Low: CSV formula neutralization missed leading tab and CR (fixed)

- `neutralize_formula_injection` now also prefixes values that begin with
  `\t` or `\r`, completing the OWASP set.

### Low: rejected sign-ins were invisible in logs (fixed)

- **FACT**: the Google callback raised `400` or `401` without logging.
- Fix: a warning is now logged with the reason only. The log never contains
  the email, code, state or token. A test asserts that the code and state are
  absent from the log.

### Low / informational (not changed)

- **`/docs`, `/redoc` and `/openapi.json` are public in production.** They
  expose the route list, not data. Disabling them is a product decision; see
  the open questions.
  - **DECISION (2026-09-28):** they are disabled under `APP_ENV=production`,
    because production users need only the dashboard. Other environments
    keep them. See [deployment](../deployment.md#http-hardening).
- **Uvicorn access logs record the callback query string**, which includes
  the one-time authorization `code`. The code is single-use and bound to the
  PKCE verifier, which never leaves the server.
- **Sessions have an absolute 8-hour TTL and no idle timeout.** The cookie
  has no `Max-Age`, so it ends when the browser closes. Authorization is
  re-read from `platform.product_grant` on every request, so a changed grant
  applies immediately. A suspended Workspace account keeps its session until
  that session expires.
- **An admin can grant `admin` through the API.** Nothing prevents an admin
  from demoting the last admin. This is by design for the Javier → Rafael
  handoff.
- **A Transelec admin can also reach `/ingesta/upload`, `/runs` and the
  LiDAR routes, which production still mounts.** Each is gated by its own
  product grant.
- **Workbooks are parsed by `python-calamine`.** Its Rust XML reader does not
  process DTDs or entities, so XXE does not apply. A decompression bomb from
  an authenticated operator remains a **LIMITATION**, bounded only by the
  64 MiB compressed cap.
- **A user who is not in `campodigital.cl` sees a raw JSON `401` page** after
  Google redirects back. This is a UX gap, not a security issue.

## Verified in code and tests (no change needed)

- **OIDC:**
  - The flow is authorization code with PKCE S256, 64 random bytes of
    verifier, and a constant-time `state` check before any `error` or `code`
    is handled.
  - The `id_token` signature is checked against Google's JWKS with RS256
    only. `iss`, `aud`, `exp`, `iat` and `sub` are required.
  - `nonce` is compared in constant time.
  - `hd` must equal the configured domain exactly; the email suffix is not
    used.
  - `email_verified` must be `true`.
  - Users are identified by `sub`, never by email.
  - No Google token is stored.
- **Dev auth:**
  - The router is mounted only when `APP_ENV=development`. An unset or
    unknown `APP_ENV` fails at import.
  - `get_current_app_user` refuses dev sessions outside development.
  - Production refuses to start without a complete identity provider and
    `PLATFORM_TOKEN_ENCRYPTION_KEY`.
- **Sessions:**
  - 32-byte random secrets.
  - Only a SHA-256 hash is stored.
  - The cookie is `HttpOnly; Secure; SameSite=Lax`.
  - A new secret is issued on every sign-in.
  - Logout deletes the server row.
- **CSRF:**
  - The token is an HMAC keyed by the session.
  - It is required on every mutation, and now on logout too.
  - Declared `Origin`/`Referer` values are checked against the request host.
  - There is no CORS middleware.
- **RBAC** (a route-by-route map of the production app):
  - Every Transelec read requires `VIEW`.
  - `validate-and-project` and the import report require `PROCESS`.
  - Publish and restore require `PUBLISH`.
  - Upload requires `UPLOAD`.
  - Grant administration requires `MANAGE_ACCESS`, which only `admin` holds.
  - `/ingesta/audit` is limited to admins.
  - LiDAR routes require LiDAR `VIEW`.
  - A run that belongs to another product answers `404`.
- **XSS:** the dashboard has no `dangerouslySetInnerHTML`, `innerHTML`,
  `eval` or `href` built from data. The import report is downloaded as a
  `text/plain` Blob.
- **Dependencies and secrets:**
  - `scripts/check_dependency_vulnerabilities.sh` reports no known
    vulnerabilities in Python or either dashboard.
  - `scripts/check_secrets.sh` (gitleaks over `--all`, 235 commits,
    including PR #59) found no leaks.
  - No `.xlsx`, `.las`, `.laz`, `.zip` or `.csv` is tracked at either commit.
- **Audit trail:** `session.created`, `upload.completed`,
  `processing.requested`, `import.validated`, `import.validation.failed`,
  `import.published`, `import.restored`, `import.publish.failed` and every
  `product_grant.changed` are recorded. Logout and CSV export are not
  audited.

## Open questions

- ~~Should `/docs`, `/redoc` and `/openapi.json` be disabled under
  `APP_ENV=production`?~~ Yes, decided 2026-09-28 (see above).
- Should CSV exports be audited as an access event?
- Is the Google OAuth client *Internal* to the Workspace? This was not
  verified. It is not required for security, because `hd` is enforced
  server-side.

## Related documentation

[Transelec deployment](../deployment.md) ·
[Google Workspace sign-in (ADR-010)](../../../../docs/adr/ADR-010-google-workspace-sign-in-for-transelec.md) ·
[Security policy](../../../../SECURITY.md)
