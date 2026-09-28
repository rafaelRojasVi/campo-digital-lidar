"""The Google authorization-code flow itself: what we send, what we accept.

The token endpoint is injected rather than mocked at the network layer, and
what it hands back is a token signed by a locally generated key
(``tests/google_tokens.py``), so these tests still exercise the real
verification path -- no Google credentials, no network, no shortcut past the
signature.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from app.config import Settings
from app.google_auth import (
    GoogleNotConfiguredError,
    GoogleOidcSignInClient,
    GoogleSignInError,
)
from google_tokens import CLIENT_ID, WORKSPACE_DOMAIN, LocalJwks, SigningKey, claims

_REDIRECT_URI = "http://testserver/auth/google/callback"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "postgres_password": "x",
        "google_client_id": CLIENT_ID,
        "google_client_secret": "fake-google-secret",
        "google_workspace_domain": WORKSPACE_DOMAIN,
    }
    values.update(overrides)
    return Settings(**values)


class RecordingTokenEndpoint:
    """Stands in for Google's token endpoint; records what it was sent."""

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.received: dict[str, str] | None = None

    def __call__(self, form: Mapping[str, str]) -> Mapping[str, Any]:
        self.received = dict(form)
        return self.response


@pytest.fixture
def key() -> SigningKey:
    return SigningKey(kid="google-signing-key-1")


@pytest.fixture
def jwks(key: SigningKey) -> LocalJwks:
    return LocalJwks(key)


def _query(auth_uri: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlparse(auth_uri).query).items()}


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_requires_a_client_id_and_a_client_secret() -> None:
    with pytest.raises(GoogleNotConfiguredError):
        GoogleOidcSignInClient(_settings(google_client_secret=None))

    with pytest.raises(GoogleNotConfiguredError):
        GoogleOidcSignInClient(_settings(google_client_id=None))


# ---------------------------------------------------------------------------
# /login -- the authorization request
# ---------------------------------------------------------------------------


def test_initiate_sends_the_browser_to_googles_authorization_endpoint() -> None:
    request = GoogleOidcSignInClient(_settings()).initiate(_REDIRECT_URI)

    assert request.auth_uri.startswith("https://accounts.google.com/o/oauth2/v2/auth?")


def test_initiate_requests_an_authorization_code_for_openid_email_and_profile() -> None:
    query = _query(GoogleOidcSignInClient(_settings()).initiate(_REDIRECT_URI).auth_uri)

    assert query["response_type"] == "code"
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == _REDIRECT_URI
    assert set(query["scope"].split()) == {"openid", "email", "profile"}


def test_initiate_binds_the_request_with_pkce_s256_state_and_a_nonce() -> None:
    request = GoogleOidcSignInClient(_settings()).initiate(_REDIRECT_URI)
    query = _query(request.auth_uri)
    flow = json.loads(request.flow_state)

    assert query["code_challenge_method"] == "S256"
    assert query["code_challenge"] == _s256(flow["code_verifier"])
    assert query["state"] == flow["state"]
    assert query["nonce"] == flow["nonce"]


def test_initiate_never_puts_the_verifier_or_the_client_secret_in_the_url() -> None:
    request = GoogleOidcSignInClient(_settings()).initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)

    assert flow["code_verifier"] not in request.auth_uri
    assert "fake-google-secret" not in request.auth_uri


def test_initiate_mints_a_fresh_state_nonce_and_verifier_every_time() -> None:
    client = GoogleOidcSignInClient(_settings())

    first = json.loads(client.initiate(_REDIRECT_URI).flow_state)
    second = json.loads(client.initiate(_REDIRECT_URI).flow_state)

    assert first["state"] != second["state"]
    assert first["nonce"] != second["nonce"]
    assert first["code_verifier"] != second["code_verifier"]


def test_initiate_hints_the_workspace_domain_to_google() -> None:
    query = _query(GoogleOidcSignInClient(_settings()).initiate(_REDIRECT_URI).auth_uri)

    assert query["hd"] == WORKSPACE_DOMAIN


# ---------------------------------------------------------------------------
# /callback -- completing the flow
# ---------------------------------------------------------------------------


def _client(jwks: LocalJwks, endpoint: RecordingTokenEndpoint) -> GoogleOidcSignInClient:
    return GoogleOidcSignInClient(_settings(), keys=jwks, exchange=endpoint)


def test_complete_exchanges_the_code_with_pkce_and_returns_the_verified_identity(
    key: SigningKey, jwks: LocalJwks
) -> None:
    endpoint = RecordingTokenEndpoint({"id_token": "placeholder", "access_token": "at"})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)
    endpoint.response = {
        "id_token": key.sign(claims(nonce=flow["nonce"])),
        "access_token": "a-google-access-token",
    }

    sign_in = client.complete(
        request.flow_state, {"state": flow["state"], "code": "the-code"}, _REDIRECT_URI
    )

    assert sign_in.email == "javier@campodigital.cl"
    assert endpoint.received == {
        "grant_type": "authorization_code",
        "code": "the-code",
        "code_verifier": flow["code_verifier"],
        "redirect_uri": _REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": "fake-google-secret",
    }


def test_complete_returns_no_google_token_to_its_caller(key: SigningKey, jwks: LocalJwks) -> None:
    endpoint = RecordingTokenEndpoint({})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)
    endpoint.response = {
        "id_token": key.sign(claims(nonce=flow["nonce"])),
        "access_token": "a-google-access-token",
        "refresh_token": "a-google-refresh-token",
    }

    sign_in = client.complete(
        request.flow_state, {"state": flow["state"], "code": "the-code"}, _REDIRECT_URI
    )

    assert "a-google-access-token" not in repr(sign_in)
    assert "a-google-refresh-token" not in repr(sign_in)


def test_complete_rejects_a_callback_whose_state_is_not_the_flows_state(jwks: LocalJwks) -> None:
    endpoint = RecordingTokenEndpoint({})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)

    with pytest.raises(GoogleSignInError):
        client.complete(
            request.flow_state, {"state": "forged-state", "code": "the-code"}, _REDIRECT_URI
        )

    assert endpoint.received is None, "the code must never be exchanged after a state mismatch"


def test_complete_rejects_a_callback_carrying_no_state_at_all(jwks: LocalJwks) -> None:
    endpoint = RecordingTokenEndpoint({})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)

    with pytest.raises(GoogleSignInError):
        client.complete(request.flow_state, {"code": "the-code"}, _REDIRECT_URI)


def test_complete_rejects_a_flow_state_that_is_not_the_one_we_wrote(jwks: LocalJwks) -> None:
    client = _client(jwks, RecordingTokenEndpoint({}))

    with pytest.raises(GoogleSignInError):
        client.complete("not-json-at-all", {"state": "x", "code": "y"}, _REDIRECT_URI)


def test_complete_surfaces_a_user_declined_consent_without_exchanging_anything(
    jwks: LocalJwks,
) -> None:
    endpoint = RecordingTokenEndpoint({})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)

    with pytest.raises(GoogleSignInError, match="access_denied"):
        client.complete(
            request.flow_state,
            {"state": flow["state"], "error": "access_denied"},
            _REDIRECT_URI,
        )

    assert endpoint.received is None


def test_complete_rejects_a_callback_with_a_valid_state_but_no_code(jwks: LocalJwks) -> None:
    endpoint = RecordingTokenEndpoint({})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)

    with pytest.raises(GoogleSignInError):
        client.complete(request.flow_state, {"state": flow["state"]}, _REDIRECT_URI)


def test_complete_rejects_a_token_response_that_carries_no_id_token(jwks: LocalJwks) -> None:
    endpoint = RecordingTokenEndpoint({"access_token": "at"})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)

    with pytest.raises(GoogleSignInError):
        client.complete(
            request.flow_state, {"state": flow["state"], "code": "the-code"}, _REDIRECT_URI
        )


def test_complete_rejects_an_id_token_minted_for_a_different_flows_nonce(
    key: SigningKey, jwks: LocalJwks
) -> None:
    endpoint = RecordingTokenEndpoint({})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)
    # A token that is perfectly valid -- for somebody else's sign-in.
    endpoint.response = {"id_token": key.sign(claims(nonce="another-flows-nonce"))}

    with pytest.raises(GoogleSignInError):
        client.complete(
            request.flow_state, {"state": flow["state"], "code": "the-code"}, _REDIRECT_URI
        )


def test_complete_rejects_an_account_outside_the_configured_workspace(
    key: SigningKey, jwks: LocalJwks
) -> None:
    endpoint = RecordingTokenEndpoint({})
    client = _client(jwks, endpoint)
    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)
    endpoint.response = {"id_token": key.sign(claims(nonce=flow["nonce"], hd="otraempresa.cl"))}

    with pytest.raises(GoogleSignInError):
        client.complete(
            request.flow_state, {"state": flow["state"], "code": "the-code"}, _REDIRECT_URI
        )
