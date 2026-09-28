# Entra ID app registration — handoff for Campo Digital tenant admin

## Status

Action required from someone with Global Administrator or Application
Administrator rights in a Campo Digital Entra tenant. **No such tenant
exists yet as of 2026-09-01** — see "Prerequisite: create the tenant"
below before step 1. Platform engineering cannot perform either step.

**Update (2026-09-03)** — the application-side sign-in implementation this
registration feeds is complete and tested against a fake identity provider
(`docs/adr/ADR-008-entra-sign-in-implementation.md`); every step below
remains the genuine external blocker. Once the values in step 7 are
supplied, no further code changes are expected to complete a real sign-in.

## Revision note (2026-09-01)

Opening the canonical Campo Digital OneDrive folder directly proved it is
a **personal** OneDrive (`onedrive.live.com`) shared from a different
personal Microsoft account into Rafael's own OneDrive — not a
SharePoint/Teams document library in a Microsoft 365 tenant, which this
document originally assumed. There is no Campo Digital Microsoft 365
tenant, and the only Entra directories currently visible (Institut
Francais, University of Brighton) are unrelated organizations, not a
Campo Digital tenant. This revision corrects the account-type and
tenant-ownership guidance below; the rest of this document (redirect
URIs, secret handling, what the registration is never used for) is
unaffected.

## Prerequisite: create the tenant

A personal Microsoft account cannot create an Entra tenant directly.
The cheapest working path: sign up for an **Azure free account**
(https://azure.microsoft.com/free) using the Microsoft account that
should administer Campo Digital's platform identity. This requires phone
verification and a non-prepaid credit/debit card for identity
verification only — a temporary authorization hold, not a recurring
charge, as long as no paid Azure resources are provisioned. Signing up
automatically creates a "Default Directory" Entra tenant on the
**Microsoft Entra ID Free** tier, with the signer as Global
Administrator. No Microsoft 365 subscription is needed. Rename the
default directory (Entra admin center → **Overview** → **Manage
tenant** → rename) to something identifiable, e.g. "Campo Digital." This
tenant is what "Campo Digital tenant admin" means for the rest of this
document.

## What this is for

The Campo Digital platform (staging, at
`https://campo-digital-portal-staging.onrender.com`, and local development)
needs to let real Campo Digital users sign in with their Microsoft account,
and — only for users who administer file uploads — browse the shared
OneDrive/SharePoint source material described in
`docs/source-systems/onedrive.md`.

## What to create

1. Azure Portal → **Microsoft Entra ID** → **App registrations** → **New
   registration**.
2. Name: `Campo Digital Platform (staging)`.
3. Supported account types: **Accounts in any organizational directory
   (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft
   accounts (e.g. Skype, Xbox)**. Real Campo Digital users sign in with
   personal Microsoft accounts today (see "Revision note" above) — this
   is the option that includes personal accounts while also preserving a
   clean path to real Campo Digital Microsoft 365 organizational accounts
   later, without re-registering the app. Do not choose "personal
   Microsoft accounts only" — it would block that future path.
4. Redirect URI (platform — Web):
   - `http://localhost:8000/auth/entra/callback` (local development)
   - `https://campo-digital-api-staging.onrender.com/auth/entra/callback`
     (Render staging — confirm this is the API service's actual
     `.onrender.com` hostname per `render.yaml`'s existing caveat before
     entering it)
5. After creation, go to **Certificates & secrets** → **New client
   secret**. Copy the secret **value** immediately (it is shown once).
6. Go to **API permissions** → confirm `Microsoft Graph` →
   `User.Read` (delegated) is present (added by default). Do not add any
   other Graph permission yet — the exact scope is decided later, in
   `docs/source-systems/onedrive.md`, once a discovery step (which needs
   this registration to exist) has run and recorded which OneDrive/SharePoint
   location actually holds Campo Digital's source material.
7. Note down, and return to platform engineering over a secure channel (not
   plain email/chat if avoidable — this is a credential):
   - **Directory (tenant) ID** → becomes `ENTRA_TENANT_ID`
   - **Application (client) ID** → becomes `ENTRA_CLIENT_ID`
   - **Client secret value** from step 5 → becomes `ENTRA_CLIENT_SECRET`

## What happens after this

Platform engineering runs a short, read-only discovery script against a
real sign-in using this registration (no client data is touched — only
Graph metadata calls, e.g. listing the signing-in user's own OneDrive and
following the `remoteItem` for the already-shared Campo Digital folder).
The source material is confirmed to be a **personal OneDrive** shared
into the signing-in user's own OneDrive (not a SharePoint/Teams document
library), so the expected outcome needs only delegated `Files.Read` —
no tenant-admin action beyond this registration itself. Two possible
follow-ups, neither expected but both documented in case discovery finds
otherwise:

- If delegated `Files.Read` genuinely proves insufficient against the
  real shared folder, platform engineering escalates to delegated
  `Files.Read.All` — still no tenant-admin action, since it's a
  user-consentable delegated scope.
- If a *different*, future Campo Digital source turns out to be
  SharePoint/Teams-backed, the tenant admin may separately be asked to
  run a one-time `Sites.Selected` permission grant scoped to exactly one
  site (not every site in the tenant); platform engineering would provide
  the exact `POST /sites/{site-id}/permissions` request body at that
  point. Do not pre-grant broader Graph permissions in anticipation of
  this — it does not apply to the OneDrive source confirmed today.

## What this registration will never be used for

- It is never used to sign in as the app itself (no client-credentials
  flow). Every Graph call uses the signing-in Campo Digital user's own
  delegated permissions.
- It does not grant access to anyone's email, calendar, or Teams data —
  only `openid profile` (sign-in) and, for a small set of upload-capable
  users, read access to the specific OneDrive/SharePoint location
  configured in `config/source-catalog.yaml`.

## Related documentation

[Platform documentation](README.md) ·
[Security model](security-model.md) ·
[ADR-006 — Restrict dev-auth to development](../adr/ADR-006-restrict-dev-auth-to-development.md) ·
[OneDrive source-system boundary](../source-systems/onedrive.md)
