"""Cryptographic verification of a Google Workspace id_token.

Every test here signs a real RS256 token with a locally generated key and
publishes that key through a real ``PyJWKSet`` (``tests.google_tokens``), so
the assertions are about what ``verify_id_token`` actually verifies, not
about a claims dictionary handed to it pre-parsed. Nothing here reaches
Google, and nothing here needs a client secret.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from app.google_auth import GoogleSignIn, GoogleSignInError, SigningKeyResolver, verify_id_token
from google_tokens import (
    ABSENT,
    CLIENT_ID,
    NONCE,
    WORKSPACE_DOMAIN,
    LocalJwks,
    SigningKey,
    UnreachableJwks,
    claims,
)


@pytest.fixture
def key() -> SigningKey:
    return SigningKey(kid="google-signing-key-1")


@pytest.fixture
def jwks(key: SigningKey) -> LocalJwks:
    return LocalJwks(key)


def _verify(token: str, jwks: SigningKeyResolver, **overrides: Any) -> GoogleSignIn:
    arguments: dict[str, Any] = {
        "keys": jwks,
        "client_id": CLIENT_ID,
        "expected_nonce": NONCE,
        "workspace_domain": WORKSPACE_DOMAIN,
    }
    arguments.update(overrides)
    return verify_id_token(token, **arguments)


# ---------------------------------------------------------------------------
# The accepted case
# ---------------------------------------------------------------------------


def test_accepts_a_correctly_signed_workspace_token(key: SigningKey, jwks: LocalJwks) -> None:
    sign_in = _verify(key.sign(claims()), jwks)

    assert sign_in.subject == "104728391027364518293"
    assert sign_in.email == "javier@campodigital.cl"
    assert sign_in.display_name == "Javier Campo"
    assert sign_in.hosted_domain == WORKSPACE_DOMAIN


def test_identifies_the_user_by_googles_subject_not_by_their_email(
    key: SigningKey, jwks: LocalJwks
) -> None:
    sign_in = _verify(key.sign(claims(sub="a-different-subject")), jwks)

    assert sign_in.subject == "a-different-subject"


def test_falls_back_to_the_email_when_the_token_carries_no_display_name(
    key: SigningKey, jwks: LocalJwks
) -> None:
    sign_in = _verify(key.sign(claims(name=ABSENT)), jwks)

    assert sign_in.display_name == "javier@campodigital.cl"


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------


def test_rejects_a_token_signed_by_a_key_that_is_not_the_published_one(
    jwks: LocalJwks,
) -> None:
    impostor = SigningKey(kid="google-signing-key-1")  # same kid, different key

    with pytest.raises(GoogleSignInError):
        _verify(impostor.sign(claims()), jwks)


def test_rejects_a_token_whose_signing_key_is_unknown_to_the_key_set(
    jwks: LocalJwks,
) -> None:
    stranger = SigningKey(kid="a-kid-google-never-published")

    with pytest.raises(GoogleSignInError):
        _verify(stranger.sign(claims()), jwks)


def test_rejects_a_tampered_payload_under_an_otherwise_valid_signature(
    key: SigningKey, jwks: LocalJwks
) -> None:
    token = key.sign(claims())
    header, _, signature = token.split(".")
    forged_payload = jwt.utils.base64url_encode(
        b'{"iss":"https://accounts.google.com","aud":"'
        + CLIENT_ID.encode()
        + b'","sub":"impostor","hd":"campodigital.cl"}'
    ).decode()

    with pytest.raises(GoogleSignInError):
        _verify(f"{header}.{forged_payload}.{signature}", jwks)


def test_rejects_an_unsigned_token(jwks: LocalJwks) -> None:
    unsigned = jwt.encode(claims(), key=None, algorithm="none")  # type: ignore[arg-type]

    with pytest.raises(GoogleSignInError):
        _verify(unsigned, jwks)


def test_rejects_a_symmetrically_signed_token_even_with_a_matching_kid(
    jwks: LocalJwks,
) -> None:
    # The classic algorithm-confusion attempt: HS256 where RS256 is expected.
    forged = jwt.encode(
        claims(), key="a" * 32, algorithm="HS256", headers={"kid": "google-signing-key-1"}
    )

    with pytest.raises(GoogleSignInError):
        _verify(forged, jwks)


def test_rejects_every_token_when_the_key_set_cannot_be_fetched(key: SigningKey) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims()), UnreachableJwks())


# ---------------------------------------------------------------------------
# Registered claims
# ---------------------------------------------------------------------------


def test_rejects_a_token_issued_for_another_client(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(aud="another-client.apps.googleusercontent.com")), jwks)


def test_rejects_a_token_from_an_unexpected_issuer(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(iss="https://accounts.evil.example")), jwks)


def test_accepts_googles_second_documented_issuer_spelling(
    key: SigningKey, jwks: LocalJwks
) -> None:
    sign_in = _verify(key.sign(claims(iss="accounts.google.com")), jwks)

    assert sign_in.subject == "104728391027364518293"


def test_rejects_an_expired_token(key: SigningKey, jwks: LocalJwks) -> None:
    expired = claims(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600)

    with pytest.raises(GoogleSignInError):
        _verify(key.sign(expired), jwks)


def test_rejects_a_token_with_no_expiry_at_all(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(exp=ABSENT)), jwks)


def test_rejects_a_token_with_no_subject(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(sub=ABSENT)), jwks)


# ---------------------------------------------------------------------------
# Nonce
# ---------------------------------------------------------------------------


def test_rejects_a_token_whose_nonce_is_not_the_one_this_flow_issued(
    key: SigningKey, jwks: LocalJwks
) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(nonce="a-nonce-from-some-other-flow")), jwks)


def test_rejects_a_token_carrying_no_nonce(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(nonce=ABSENT)), jwks)


# ---------------------------------------------------------------------------
# Workspace membership and email
# ---------------------------------------------------------------------------


def test_rejects_a_consumer_account_that_carries_no_hosted_domain_claim(
    key: SigningKey, jwks: LocalJwks
) -> None:
    # A personal @gmail.com account: no `hd` at all.
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(hd=ABSENT, email="javier@gmail.com")), jwks)


def test_rejects_a_token_whose_hosted_domain_is_another_workspace(
    key: SigningKey, jwks: LocalJwks
) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(hd="otraempresa.cl")), jwks)


def test_a_campodigital_email_alone_does_not_prove_workspace_membership(
    key: SigningKey, jwks: LocalJwks
) -> None:
    # The whole reason `hd` is the control: any account can carry an address
    # that merely *ends in* the domain.
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(hd=ABSENT, email="impostor@campodigital.cl")), jwks)


def test_rejects_an_unverified_email(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(email_verified=False)), jwks)


def test_rejects_a_token_with_no_email_verified_claim(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(email_verified=ABSENT)), jwks)


def test_rejects_a_token_with_no_email(key: SigningKey, jwks: LocalJwks) -> None:
    with pytest.raises(GoogleSignInError):
        _verify(key.sign(claims(email=ABSENT)), jwks)
