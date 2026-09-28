# Google Workspace OAuth client — handoff for Campo Digital

## Status

**Action required from a Campo Digital Google Workspace administrator**
(Javier), in the Google Cloud console for the `campodigital.cl` Workspace.
Platform engineering cannot perform these steps.

The application side is complete and tested (see
`../adr/ADR-010-google-workspace-sign-in-for-transelec.md`), against
locally-signed tokens and a fake provider. **No real Google sign-in has ever
run.**

**Update (2026-09-25).** The OAuth client exists. Its registered production
redirect URI, as reported by Rafael, is:

```
https://campo-digital-platform-production.up.railway.app/api/auth/google/callback
```

It is correct as registered and **must not be changed**. See
"The redirect URI and `/api`" below for why the `/api` segment belongs
there. The client's audience (Internal or External) has not been read from
the console by platform engineering; see "User type" below.

## Why Google rather than Microsoft

`entra-app-registration-handoff.md` established that no Campo Digital
Microsoft Entra tenant exists, and creating one needs an Azure sign-up with
card verification. Campo Digital already operates Google Workspace on
`campodigital.cl`. For the Transelec pilot, an identity provider that
already exists is worth more than one that is blocked.

## What to create

In the Google Cloud console, in a project owned by the `campodigital.cl`
organization:

1. **APIs & Services → OAuth consent screen** (in newer consoles, **Google
   Auth Platform → Audience**).
   - User type: **Internal** is preferred, and is only available when the
     Cloud project belongs to the `campodigital.cl` organization. It
     restricts sign-in to Workspace accounts at the Google end. **OPEN
     QUESTION (2026-09-25):** which audience the existing client actually
     has. Read it on the Audience page; do not assume Internal. If it is
     **External**, then while its publishing status is "Testing" only the
     test users listed there can sign in, so every colleague would have to be
     listed. Either way, the API independently requires the verified `hd`
     claim to equal `campodigital.cl` (`app.google_auth.verify_id_token`),
     and that is the control this application enforces. The Google-side
     audience is defence in depth, not the boundary.
   - App name: `Campo Digital — Transelec`.
   - Support email and developer contact: a `campodigital.cl` address.
   - Scopes: **`openid`, `email`, `profile` only.** Nothing else. This
     application reads no Google data: no Drive, no Gmail, no Calendar.

2. **APIs & Services → Credentials → Create credentials → OAuth client ID.**
   - Application type: **Web application** (not "Desktop", not "Android/iOS"
     — the flow runs server-side with a client secret).
   - Name: `Campo Digital Transelec API`.
   - **Authorized redirect URIs.** The application sends exactly
     `GOOGLE_REDIRECT_BASE_URL + "/auth/google/callback"`
     (`app.routers.google_auth._redirect_uri`), and Google rejects the
     sign-in unless that string equals a registered URI byte for byte:
     scheme, host, port, path, no trailing slash.
     - Production (registered; keep as is):
       `https://campo-digital-platform-production.up.railway.app/api/auth/google/callback`
     - Local development, if wanted:
       `http://localhost:8000/auth/google/callback`
   - "Authorized JavaScript origins" is not needed and should be left empty:
     no browser code in this application talks to Google.

3. After creation, return to platform engineering **over a secure channel**
   (not plain email or chat — the second value is a credential):
   - **Client ID** → becomes `GOOGLE_CLIENT_ID`
   - **Client secret** → becomes `GOOGLE_CLIENT_SECRET`

## What platform engineering configures with it

| Variable | Value | Notes |
|---|---|---|
| `GOOGLE_CLIENT_ID` | from step 3 | Not a secret, but must match the registered client. |
| `GOOGLE_CLIENT_SECRET` | from step 3 | Secret. Never in the repository, never in a frontend build. |
| `GOOGLE_REDIRECT_BASE_URL` | `https://campo-digital-platform-production.up.railway.app/api` | The redirect URI is this + `/auth/google/callback`, and must equal what step 2 registered. Keep the `/api`. |
| `GOOGLE_WORKSPACE_DOMAIN` | `campodigital.cl` | The `hd` claim an `id_token` must carry, exactly, to be accepted. |
| `PLATFORM_TOKEN_ENCRYPTION_KEY` | a generated Fernet key | Encrypts the short-lived sign-in flow cookie. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `TRANSELEC_BOOTSTRAP_ADMIN_EMAIL` | one `campodigital.cl` address | See "Initial permissions" below. Leave unset to grant nothing automatically. |

## The redirect URI and `/api`

The container mounts every browser-facing router twice, at `/…` and at
`/api/…` (`app.main`, the same-origin `/api/*` alias every dashboard bundle
is built against). So `/auth/google/callback` and
`/api/auth/google/callback` reach the same handler. What differs is the
string Google compares. The API builds the redirect URI from
`GOOGLE_REDIRECT_BASE_URL`, so with the base URL ending in `/api` it sends
`…/api/auth/google/callback`. That is what is registered.

**DECISION (2026-09-25):** production keeps
`GOOGLE_REDIRECT_BASE_URL=https://campo-digital-platform-production.up.railway.app/api`
and the registered callback with `/api`. Dropping `/api` from only one of
the two would make every production sign-in fail with a Google
`redirect_uri_mismatch`, and changing both gains nothing. Nobody needs to
edit the Google client.

The flow cookie is issued with the default path `/`, so it reaches the
callback under either prefix.

## Initial permissions

Signing in does not grant access to anything. A verified `campodigital.cl`
account with no grant for the Transelec product receives a session and then
`403` from every Transelec route.

Access is opened in two steps:

1. **The first administrator.** The single address in
   `TRANSELEC_BOOTSTRAP_ADMIN_EMAIL` receives the `ADMIN` role on
   `transelect` — and on no other product — at its first sign-in, and only
   while it holds no grant at all. It can never grant anything on LiDAR or
   Gestión Predial Forestal. If that account is later demoted, a subsequent
   sign-in does not restore it.

2. **Everyone else** is onboarded by that administrator through the existing
   product-grant endpoints (`app.routers.access_admin`), by email. A grant
   can only be created for someone who has **already signed in at least
   once**: their `app_user` row, and the email it is looked up by, only
   exist from that point on. So the practical order is: each colleague signs
   in once (and sees a `403`), then the administrator grants them the role
   they need — `viewer` for read-only access to the dashboard, `operator` or
   `admin` to import spreadsheets and publish or restore versions.

   The dashboard's **Datos → Accesos** form offers only `viewer` and
   `operator`, on purpose. Making someone a second **administrator** goes
   through the same API the form uses, which accepts `admin`. See the next
   section.

### Handing administration to a second named account

This procedure is covered end to end by
`apps/api/integration_tests/test_google_auth_router.py::test_bootstrap_admin_grants_admin_to_a_named_account_through_the_api`.

1. **Keep `TRANSELEC_BOOTSTRAP_ADMIN_EMAIL` set to Javier's address** until
   his own admin grant is established. It fires once, at his first sign-in.
2. Javier signs in. **Confirm the grant exists** before anything else: the
   **Datos → Accesos** pane opens for him and lists him as `admin`, or
   `GET /api/auth/admin/product-grants/transelect` returns `200` with his row.
3. The named account (Rafael's `campodigital.cl` Workspace account) signs in
   once. It is authenticated but has no grant, so it receives `403`. The
   bootstrap does not apply, because its address is not the configured one.
4. Javier, signed in on the dashboard, grants it `admin` from his browser's
   developer console. That runs on the dashboard's own origin, with his
   session cookie and a CSRF token, exactly as the Accesos form does:

   ```js
   const { csrf_token } = await (await fetch("/api/auth/csrf")).json();
   const response = await fetch("/api/auth/admin/product-grants/transelect", {
     method: "POST",
     headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf_token },
     body: JSON.stringify({ email: "<named-account>@campodigital.cl", role: "admin" }),
   });
   console.log(response.status, await response.json());
   ```

   Expect `200` and `"role": "admin"`. A `404` means that account has not
   signed in yet (step 3).
5. The named account reloads the dashboard. It now administers Transelec
   only, not LiDAR or Forestal. Javier keeps his own grant.

Every role change is recorded in `platform.audit_event` as
`event_type = 'product_grant.changed'`, with the granted account as the
subject and `{previous_role, role, via}` as metadata. `via` is
`bootstrap_email` for the configuration grant (no actor) and `admin_api`
for a grant made by a signed-in administrator (who is the actor).

After step 2 the bootstrap variable has done its job. Leaving it set is
harmless while Javier holds any Transelec grant. It would fire again only
for that address holding no grant at all.

## What this client will never be used for

- It never signs in as the application itself: there is no service account
  and no client-credentials flow.
- It never reads Google data. No Drive, Gmail, Calendar or directory access
  is requested, and no Google access or refresh token is stored anywhere —
  the token is discarded as soon as the identity token is verified.
- No Google token, client secret or identity token ever reaches the browser.
  The browser gets one `HttpOnly` session cookie issued by this platform.

## Still pending after this handoff

- The client's actual audience (Internal or External, and if External its
  publishing status and test users).
- One real end-to-end sign-in with a `campodigital.cl` account, which is the
  only thing that can confirm the `hd` claim arrives as expected and that
  the bootstrap grant lands on `transelect` alone.

## Related documentation

[Platform documentation](README.md) ·
[Security model](security-model.md) ·
[ADR-010 — Google Workspace sign-in for Transelec](../adr/ADR-010-google-workspace-sign-in-for-transelec.md) ·
[Entra app registration handoff](entra-app-registration-handoff.md)
