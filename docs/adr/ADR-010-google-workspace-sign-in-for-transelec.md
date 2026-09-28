# ADR-010 — Google Workspace sign-in for Transelec

## Status

Accepted, and implemented against a locally-signed key set. It has **not**
been exercised against real Google credentials or a final public domain —
see "What remains unproven" below.

Supersedes point 4 of `ADR-009-transelec-sign-in-surface.md` (which routed
the Transelec dashboard's only sign-in action to Microsoft Entra) for the
Transelec product alone. `ADR-008-entra-sign-in-implementation.md` is not
superseded: Entra remains implemented, mounted, and the intended provider
for LiDAR and Gestión Predial Forestal.

## Context

`ADR-008` chose Microsoft Entra ID as the platform's identity provider,
reasoning from Campo Digital's use of Microsoft/OneDrive collaboration.
`docs/platform/entra-app-registration-handoff.md` then established, on
2026-09-01, that **no Campo Digital Entra tenant exists**: the shared source
material is a personal OneDrive (`onedrive.live.com`), not a Microsoft 365
tenant, and creating a tenant requires an Azure sign-up with card
verification by someone at Campo Digital. That handoff has been the blocking
external gate ever since — the Entra sign-in implementation is complete and
has never authenticated a real person.

Campo Digital does, however, already operate a Google Workspace on the
`campodigital.cl` domain. For the Transelec hosted pilot — a single client
product with a small, known set of Campo Digital users — an identity
provider that already exists is worth more than one that is better-matched
in theory and blocked in practice.

## Decision

1. **Transelec signs in with Google Workspace.** The browser action in every
   non-development Transelec build is `Continuar con Google`, routed to
   `GET /auth/google/login`. Microsoft Entra stays mounted and unchanged for
   the other products; neither provider's configuration implies the other's,
   and a deployment chooses by configuring, not by being rebuilt.

2. **Authorization code flow with PKCE S256, run server-side.** `state`,
   `nonce` and the PKCE `code_verifier` are minted per sign-in and
   round-tripped in a short-lived (10 min), encrypted, `HttpOnly` flow
   cookie — the same mechanism `app.routers.entra_auth` uses, and for the
   same reason: a deployment may run more than one replica, so the login and
   callback requests are not guaranteed to reach the same process.

3. **The `id_token` is verified cryptographically, in our own code.** PyJWT
   with `jwt.PyJWKClient` against Google's published JWKS, declared as a
   direct dependency of the `api` extra. Verification pins exactly one
   algorithm (`RS256`) and requires, in order: a signing key resolvable from
   the key set; a valid signature; `iss` in Google's two documented
   spellings; `aud` equal to our client ID; `exp`/`iat`/`sub` present and
   `exp` unexpired; `nonce` equal to the one this flow issued; `hd` equal to
   the configured Workspace domain; `email_verified` exactly `true`; and a
   non-empty `email`. Every failure — including an unreachable key endpoint —
   raises, so an inability to verify closes access rather than degrading
   into an unverified sign-in.

4. **`hd` is the Workspace membership control, not the email address.** An
   address that merely ends in `@campodigital.cl` proves nothing: only the
   `hd` claim, asserted by Google inside the signed token, states which
   Workspace the account belongs to. The `hd` parameter sent on the
   authorization request is a *hint* that pre-selects the account chooser;
   Google does not enforce it, which is exactly why the claim is re-checked
   on the way back.

5. **The user is identified by Google's `sub`**, stored as
   `platform.app_user.identity_key` with `identity_kind = "google"`. The
   email is recorded for operator lookup (unchanged behaviour: it is written
   at creation and never updated), but it is not the identity — it can be
   renamed; `sub` cannot.

6. **No Google token is kept.** This flow is sign-in only. The access token
   is dropped the moment the `id_token` is verified, no refresh token is
   requested, nothing is written to `platform.ms_graph_grant`, and nothing
   Google-issued reaches the browser. The browser receives one `HttpOnly`
   `campo_session` cookie, exactly as before.

7. **Authentication is not authorization.** A verified `campodigital.cl`
   account with no `platform.product_grant` for `transelect` gets a session
   and a `403` from every Transelec route. Nothing in this flow changes
   `app.deps.ensure_can`.

8. **The bootstrap grant is Transelec-only.**
   `maybe_grant_transelec_bootstrap_admin` grants `ADMIN` on `transelect`,
   and on no other product, to the single address in
   `TRANSELEC_BOOTSTRAP_ADMIN_EMAIL`, and only while that user holds no
   product grant at all. It is deliberately a separate function from
   `maybe_grant_bootstrap_admin` (which opens all three products to a
   platform operator) rather than a parameterisation of it: the Transelec
   pilot is hosted for one client, and the account that first opens it must
   not thereby become an administrator of LiDAR or Forestal. Being one-time
   also means an operator who later demotes that account does not have the
   decision undone by the next sign-in.

9. **Production startup requires a token-encryption key plus at least one
   COMPLETE provider**, rather than "Entra is configured". A half-configured
   provider fails closed even when the other is complete: an operator who
   set `GOOGLE_CLIENT_ID` and forgot the secret has shipped a button that
   can only answer `503`, and should learn that at startup.

10. **Microsoft is removed from the Transelec bundle**, not merely
    de-emphasised. `components/EntraSignIn.tsx` is deleted and the
    production-bundle guard now asserts both that `Continuar con Google` and
    `/api/auth/google/login` are present and that `Continuar con Microsoft`
    and `/api/auth/entra/login` are absent. Two entrances would make the
    shipped artifact contradict the one the client is told to use. The demo
    boundary of `ADR-009` is untouched: seeded identities remain compiled out
    of every deployed build, and an unconfigured Google environment shows a
    clear state rather than falling back to dev-login.

## Rationale for verifying the token ourselves

The alternative was a Google client library that hides verification. Doing
it with PyJWT keeps the accepted algorithm, the accepted issuers, and every
required claim visible in one readable function — and, more importantly,
testable: `apps/api/tests/test_google_id_token.py` signs real RS256 tokens
with locally generated keys, publishes them through a real `PyJWKSet`, and
asserts on what verification actually rejects. Those tests cover a wrong
key, an unknown `kid`, a tampered payload under a valid signature, `alg:
none`, HS256 algorithm confusion, an unreachable key set, a wrong `aud`, a
wrong `iss`, expiry, a missing `exp`/`sub`, a wrong and a missing `nonce`, a
wrong and a missing `hd`, an unverified email and a missing email. None of
them needs Google credentials, Google's domain, or a network route.

## Consequences

- Campo Digital can open the Transelec pilot without creating an Entra
  tenant. The Entra handoff stays open for the other products.
- The platform now runs two identity providers. `app.routers.session`
  already resolved sessions provider-agnostically, so `/auth/me` and
  `/auth/logout` needed no change.
- `PLATFORM_TOKEN_ENCRYPTION_KEY` is now load-bearing for a provider that is
  actually used, not only for one that is blocked.
- The token endpoint is called with the standard library rather than a new
  HTTP client dependency: one POST to one fixed HTTPS URL, the same way
  `jwt.PyJWKClient` already fetches the key set.
- Google's error body is deliberately not surfaced to the caller — it can
  echo the authorization code and client ID back into a message.

## What remains unproven

**LIMITATION.** Every test in this change runs against a fake provider or a
locally generated key set. Nothing here has talked to Google. A real
sign-in still requires, and has not had:

- the OAuth client Javier must create (see
  `../platform/google-workspace-oauth-handoff.md`);
- the final public domain, which fixes the exact redirect URI — that URI
  cannot be registered until the domain is decided;
- one end-to-end sign-in with a real `campodigital.cl` account, confirming
  the `hd` claim arrives as expected and that the configured bootstrap
  address receives `ADMIN` on `transelect` alone.

Until that run happens, "Google sign-in works" is a hypothesis supported by
unit and integration evidence, not a confirmed fact.

## Related evidence

- `ADR-008-entra-sign-in-implementation.md` — the provider retained for the
  other products.
- `ADR-009-transelec-sign-in-surface.md` — the demo boundary this preserves;
  its point 4 is superseded here for Transelec.
- `../platform/google-workspace-oauth-handoff.md` — what Javier must create.
- `../platform/entra-app-registration-handoff.md` — the blocked gate that
  motivated this decision.
- `../platform/security-model.md` — session strategy and CSRF.
- Tests: `apps/api/tests/test_google_id_token.py`,
  `apps/api/tests/test_google_auth_client.py`,
  `apps/api/tests/test_identity_safety.py`,
  `apps/api/tests/test_main_production_identity_gate.py`,
  `apps/api/integration_tests/test_google_auth_router.py`,
  `apps/api/integration_tests/test_access_repository.py`,
  `products/transelect/dashboard/src/components/GoogleSignIn.test.tsx`,
  `products/transelect/dashboard/tests/bundle/production-bundle.test.ts`.
