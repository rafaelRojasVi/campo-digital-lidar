"""Google Workspace sign-in adapter (OIDC authorization code + PKCE S256).

This is the identity provider for the Transelec product. Microsoft Entra
(``app.entra_auth``) stays in place for the other products; the two live
side by side and share nothing but the session and grant machinery they both
end in.

Unlike the Entra adapter, which delegates token handling to MSAL, this
module verifies Google's ``id_token`` itself with PyJWT and
``jwt.PyJWKClient``. That is deliberate and is what the verification below
has to earn: signature against Google's published JWKS, a single accepted
algorithm, and then every claim the flow depends on -- ``iss``, ``aud``,
``exp``, ``iat``, ``sub``, the ``nonce`` this flow issued, ``email_verified``
and ``hd``.

``hd`` (hosted domain) is the Workspace membership control, not the email
address. An address that merely ends in ``@campodigital.cl`` can be carried
by an account that is not in the Workspace at all; only ``hd``, asserted by
Google inside the signed token, states which Workspace the account belongs
to. The user is then identified by Google's ``sub``, which is stable across
renames, and never by the email, which is not.

No Google access or refresh token is kept: this flow is sign-in only. The
session it produces is the same ``platform.session`` row every other
provider produces, and authorization remains a separate step decided by
``platform.product_grant`` (see ``app.deps.ensure_can``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt.exceptions import PyJWKClientError, PyJWTError

from app.config import Settings

GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

# Both spellings are documented by Google as valid `iss` values for an
# id_token; accepting exactly these two and nothing else is the point.
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})

# Google signs id_tokens with RS256. Pinning one algorithm is what closes
# the algorithm-confusion family of attacks (an HS256 token whose "key" is
# the public key, or an unsigned `alg: none` token): PyJWT refuses anything
# outside this list before it ever looks at the signature.
ID_TOKEN_ALGORITHM = "RS256"

_REQUIRED_REGISTERED_CLAIMS = ("iss", "aud", "exp", "iat", "sub")


class GoogleNotConfiguredError(RuntimeError):
    """Raised when Google sign-in is used without GOOGLE_CLIENT_ID/SECRET configured."""


class GoogleSignInError(RuntimeError):
    """Raised when a Google sign-in attempt cannot be completed or trusted."""


@dataclass(frozen=True, slots=True)
class GoogleSignIn:
    """One verified Workspace identity. Carries no Google token by design."""

    subject: str
    """Google's stable `sub` claim -- the identity key, not the email."""

    email: str
    display_name: str
    hosted_domain: str


class SigningKeyResolver(Protocol):
    """The slice of ``jwt.PyJWKClient`` this module depends on.

    A ``Protocol`` for the same reason ``EntraOidcClient`` is one: a test can
    publish a locally generated key set and exercise real signature
    verification without reaching Google's key endpoint.
    """

    def get_signing_key_from_jwt(self, token: str) -> Any:
        """Return the published key matching the token's `kid`."""


def verify_id_token(
    id_token: str,
    *,
    keys: SigningKeyResolver,
    client_id: str,
    expected_nonce: str,
    workspace_domain: str,
) -> GoogleSignIn:
    """Verify a Google id_token end to end, or raise ``GoogleSignInError``.

    Every failure mode -- unreachable key set included -- raises, so an
    inability to verify closes access rather than degrading into an
    unverified sign-in.
    """

    try:
        signing_key = keys.get_signing_key_from_jwt(id_token)
    except PyJWKClientError as exc:
        raise GoogleSignInError(
            "Google's token signing keys could not be resolved; sign-in cannot be verified."
        ) from exc

    try:
        claims: dict[str, Any] = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=[ID_TOKEN_ALGORITHM],
            audience=client_id,
            options={"require": list(_REQUIRED_REGISTERED_CLAIMS)},
        )
    except PyJWTError as exc:
        raise GoogleSignInError(f"Google's identity token was rejected: {exc}") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleSignInError("Google's identity token names an unexpected issuer.")

    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not hmac.compare_digest(nonce, expected_nonce):
        raise GoogleSignInError(
            "Google's identity token does not carry the nonce this sign-in issued."
        )

    # Domains are case-insensitive, but membership is not a matter of
    # suffix: this compares the whole asserted domain, never the email's.
    hosted_domain = claims.get("hd")
    if (
        not isinstance(hosted_domain, str)
        or hosted_domain.casefold() != workspace_domain.casefold()
    ):
        raise GoogleSignInError(
            "This account does not belong to the Google Workspace domain allowed to sign in."
        )

    if claims.get("email_verified") is not True:
        raise GoogleSignInError("Google has not verified this account's email address.")

    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise GoogleSignInError("Google's identity token carries no email address.")

    subject = str(claims["sub"])
    name = claims.get("name")
    return GoogleSignIn(
        subject=subject,
        email=email,
        display_name=str(name) if isinstance(name, str) and name else email,
        hosted_domain=hosted_domain,
    )


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Where to send the browser, and the opaque flow state to round-trip."""

    auth_uri: str
    flow_state: str
    """JSON: the `state`, `nonce` and PKCE `code_verifier` of one sign-in."""


class GoogleOidcClient(Protocol):
    """Provider-neutral interface ``app.routers.google_auth`` depends on."""

    def initiate(self, redirect_uri: str) -> AuthorizationRequest:
        """Build the Google sign-in redirect and the flow state to round-trip."""

    def complete(
        self, flow_state: str, callback_params: Mapping[str, str], redirect_uri: str
    ) -> GoogleSignIn:
        """Exchange the callback's parameters for one verified identity."""


TokenExchange = Callable[[Mapping[str, str]], Mapping[str, Any]]
"""Posts the token-endpoint form and returns Google's parsed JSON response."""

_TOKEN_ENDPOINT_TIMEOUT_SECONDS = 10

# RFC 7636 allows 43..128 characters; 64 random URL-safe bytes lands in that
# range with far more entropy than the 256 bits the spec asks for.
_CODE_VERIFIER_BYTES = 64
_STATE_BYTES = 32
_NONCE_BYTES = 32

_SCOPES = "openid email profile"


def _post_to_google_token_endpoint(form: Mapping[str, str]) -> Mapping[str, Any]:
    """Exchange the authorization code at Google's token endpoint.

    Uses the standard library rather than adding an HTTP client dependency:
    this is one POST to one fixed HTTPS URL, and ``jwt.PyJWKClient`` already
    fetches Google's key set the same way.
    """

    request = urllib.request.Request(  # noqa: S310 -- fixed https:// constant, not caller input
        GOOGLE_TOKEN_ENDPOINT,
        data=urllib.parse.urlencode(dict(form)).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=_TOKEN_ENDPOINT_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        # Deliberately does not surface Google's response body: it can echo
        # the authorization code and client_id back into an error message.
        raise GoogleSignInError(
            "Google's token endpoint could not complete the authorization code exchange."
        ) from exc

    if not isinstance(payload, dict):
        raise GoogleSignInError("Google's token endpoint returned an unexpected response.")
    return payload


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _require_credential_settings(settings: Settings) -> tuple[str, str]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleNotConfiguredError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured to sign in."
        )
    return settings.google_client_id, settings.google_client_secret.get_secret_value()


class GoogleOidcSignInClient:
    """Real ``GoogleOidcClient``: authorization code + PKCE S256, sign-in only.

    ``keys`` and ``exchange`` are injectable for exactly one reason: a test
    must be able to publish its own key set and its own token endpoint and
    still traverse the real verification path. Neither default reaches the
    network at construction time.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        keys: SigningKeyResolver | None = None,
        exchange: TokenExchange | None = None,
    ) -> None:
        self._client_id, self._client_secret = _require_credential_settings(settings)
        self._workspace_domain = settings.google_workspace_domain
        self._keys: SigningKeyResolver = keys or jwt.PyJWKClient(GOOGLE_JWKS_URI)
        self._exchange: TokenExchange = exchange or _post_to_google_token_endpoint

    def initiate(self, redirect_uri: str) -> AuthorizationRequest:
        state = secrets.token_urlsafe(_STATE_BYTES)
        nonce = secrets.token_urlsafe(_NONCE_BYTES)
        code_verifier = secrets.token_urlsafe(_CODE_VERIFIER_BYTES)

        query = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": _SCOPES,
                "state": state,
                "nonce": nonce,
                "code_challenge": _pkce_challenge(code_verifier),
                "code_challenge_method": "S256",
                # A hint only: it pre-selects the Workspace account chooser.
                # Google does not enforce it, which is why the `hd` claim is
                # re-checked on the way back (see verify_id_token).
                "hd": self._workspace_domain,
            }
        )
        return AuthorizationRequest(
            auth_uri=f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}",
            flow_state=json.dumps({"state": state, "nonce": nonce, "code_verifier": code_verifier}),
        )

    def complete(
        self, flow_state: str, callback_params: Mapping[str, str], redirect_uri: str
    ) -> GoogleSignIn:
        flow = self._load_flow(flow_state)

        returned_state = callback_params.get("state")
        if not returned_state or not hmac.compare_digest(returned_state, flow["state"]):
            raise GoogleSignInError("This sign-in did not come back from the request we started.")

        # Only after the state matches: an error or a missing code is now
        # attributable to our own flow rather than to an unsolicited callback.
        if "error" in callback_params:
            raise GoogleSignInError(
                f"Google did not complete the sign-in: {callback_params['error']}"
            )

        code = callback_params.get("code")
        if not code:
            raise GoogleSignInError("Google's callback carried no authorization code.")

        token_response = self._exchange(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": flow["code_verifier"],
                "redirect_uri": redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )

        id_token = token_response.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise GoogleSignInError("Google's token response carried no identity token.")

        return verify_id_token(
            id_token,
            keys=self._keys,
            client_id=self._client_id,
            expected_nonce=flow["nonce"],
            workspace_domain=self._workspace_domain,
        )

    @staticmethod
    def _load_flow(flow_state: str) -> dict[str, str]:
        try:
            flow = json.loads(flow_state)
        except ValueError as exc:
            raise GoogleSignInError("The sign-in state could not be read.") from exc

        if not isinstance(flow, dict) or not all(
            isinstance(flow.get(name), str) and flow.get(name)
            for name in ("state", "nonce", "code_verifier")
        ):
            raise GoogleSignInError("The sign-in state is incomplete.")
        return flow
