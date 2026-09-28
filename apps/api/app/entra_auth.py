"""Microsoft Entra ID sign-in adapter (OIDC authorization code + PKCE).

Wraps ``msal.ConfidentialClientApplication`` so ``app.routers.entra_auth``
depends only on this module's small interface, not on MSAL's dict-shaped
API directly -- the same adapter-boundary rule ``app.object_store``
documents for storage, and the same reason ``EntraOidcClient`` is a
``Protocol``: a router test can inject a fake without a live tenant.

The authority is always the fixed multitenant + personal-account "common"
endpoint, never a single ``ENTRA_TENANT_ID``, because the app registration's
audience is "any organizational directory and personal Microsoft accounts"
per ``docs/platform/entra-app-registration-handoff.md``. Scoping the
authority to one tenant would silently break sign-in for every account type
that audience is supposed to allow.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import msal

from app.config import Settings

_AUTHORITY = "https://login.microsoftonline.com/common"

# MSAL adds openid, profile, and offline_access (for a refresh token)
# automatically. User.Read is the one scope the app registration is granted
# by default (see the handoff doc) -- sufficient for sign-in with a display
# name and email; Files.Read is a documented, deliberately separate later
# escalation, not requested here.
_SCOPES = ["User.Read"]


class EntraNotConfiguredError(RuntimeError):
    """Raised when Entra sign-in is used without ENTRA_CLIENT_ID/SECRET configured."""


class EntraSignInError(RuntimeError):
    """Raised when Microsoft Entra rejects or cannot complete a sign-in attempt."""


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Where to send the browser, and the opaque flow state to round-trip."""

    auth_uri: str
    flow_state: str
    """JSON-serialized MSAL auth-code-flow dict (state, PKCE verifier, ...)."""


@dataclass(frozen=True, slots=True)
class EntraSignIn:
    """One completed sign-in's identity and (optional) Graph grant."""

    tenant_id: str
    object_id: str
    display_name: str
    email: str | None
    access_token: str | None
    refresh_token: str | None
    scope: str | None
    expires_in: int | None


class EntraOidcClient(Protocol):
    """Provider-neutral interface ``app.routers.entra_auth`` depends on."""

    def initiate(self, redirect_uri: str) -> AuthorizationRequest:
        """Build the Microsoft sign-in redirect and the flow state to round-trip."""

    def complete(
        self, flow_state: str, callback_params: Mapping[str, str], redirect_uri: str
    ) -> EntraSignIn:
        """Exchange the callback's parameters for a completed sign-in."""


def _require_credential_settings(settings: Settings) -> tuple[str, str]:
    if not settings.entra_client_id or not settings.entra_client_secret:
        raise EntraNotConfiguredError(
            "ENTRA_CLIENT_ID and ENTRA_CLIENT_SECRET must be configured to sign in."
        )
    return settings.entra_client_id, settings.entra_client_secret.get_secret_value()


class MsalEntraOidcClient:
    """Real ``EntraOidcClient``, backed by ``msal.ConfidentialClientApplication``."""

    def __init__(self, settings: Settings) -> None:
        client_id, client_secret = _require_credential_settings(settings)
        self._app = msal.ConfidentialClientApplication(
            client_id, client_credential=client_secret, authority=_AUTHORITY
        )

    def initiate(self, redirect_uri: str) -> AuthorizationRequest:
        # form_post (rather than MSAL's query-string default) is MSAL's own
        # recommended response_mode: Microsoft POSTs the authorization code
        # to the callback instead of appending it to the redirect URL, which
        # keeps it out of browser history and Referer headers. The callback
        # router reads it as a form body accordingly (see
        # app.routers.entra_auth.entra_callback).
        flow = self._app.initiate_auth_code_flow(
            scopes=_SCOPES, redirect_uri=redirect_uri, response_mode="form_post"
        )
        return AuthorizationRequest(auth_uri=flow["auth_uri"], flow_state=json.dumps(flow))

    def complete(
        self, flow_state: str, callback_params: Mapping[str, str], redirect_uri: str
    ) -> EntraSignIn:
        del redirect_uri  # already embedded in flow_state; MSAL re-validates it via `state`
        flow = json.loads(flow_state)
        try:
            result = self._app.acquire_token_by_auth_code_flow(flow, dict(callback_params))
        except ValueError as exc:
            raise EntraSignInError(str(exc)) from exc

        if "error" in result:
            raise EntraSignInError(str(result.get("error_description") or result["error"]))

        claims: Mapping[str, object] = result.get("id_token_claims") or {}
        tenant_id = claims.get("tid")
        object_id = claims.get("oid")
        if not tenant_id or not object_id:
            raise EntraSignInError("Sign-in response is missing tenant/object identity claims.")

        scope = result.get("scope")
        return EntraSignIn(
            tenant_id=str(tenant_id),
            object_id=str(object_id),
            display_name=str(claims.get("name") or claims.get("preferred_username") or object_id),
            email=(str(claims["preferred_username"]) if claims.get("preferred_username") else None),
            access_token=result.get("access_token"),
            refresh_token=result.get("refresh_token"),
            scope=" ".join(scope) if isinstance(scope, list) else scope,
            expires_in=result.get("expires_in"),
        )
