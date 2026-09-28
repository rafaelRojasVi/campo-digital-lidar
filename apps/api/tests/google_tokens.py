"""Locally-signed Google id_token fixtures: real RSA, real JWKS, no network.

The point of this helper is that ``app.google_auth`` is exercised against
tokens it must actually verify cryptographically, not against dictionaries
of claims handed to it directly. Keys are generated per test run, the JWKS
is served from memory through PyJWT's own ``PyJWKSet``, and the resolver
below mirrors ``jwt.PyJWKClient.get_signing_key_from_jwt`` -- same kid
lookup, same ``PyJWKClientError`` on an unknown key -- so a test never needs
Google's credentials, Google's domain, or a network route to reach it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK, PyJWKSet
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import PyJWKClientError

ISSUER = "https://accounts.google.com"
CLIENT_ID = "1234567890-abcdef.apps.googleusercontent.com"
WORKSPACE_DOMAIN = "campodigital.cl"
NONCE = "nonce-from-the-flow-cookie"


@dataclass
class SigningKey:
    """One RSA keypair, usable both to sign a token and to publish a JWK."""

    kid: str
    private_key: rsa.RSAPrivateKey = field(
        default_factory=lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )

    def jwk(self) -> dict[str, Any]:
        published = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        published.update(kid=self.kid, alg="RS256", use="sig")
        return published

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid})


class LocalJwks:
    """A ``SigningKeyResolver`` over an in-memory JWKS of published keys."""

    def __init__(self, *keys: SigningKey) -> None:
        self._jwks = PyJWKSet.from_dict({"keys": [key.jwk() for key in keys]})

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        for key in self._jwks.keys:
            if key.key_id == kid:
                return key
        raise PyJWKClientError(f"Unable to find a signing key that matches: {kid}")


class UnreachableJwks:
    """A resolver standing in for Google's key endpoint being unreachable."""

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        del token
        raise PyJWKClientError("Fail to fetch data from the url, err: connection refused")


def claims(**overrides: Any) -> dict[str, Any]:
    """A well-formed Workspace id_token payload, before any tampering."""

    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "104728391027364518293",
        "iat": now,
        "exp": now + 3600,
        "nonce": NONCE,
        "email": "javier@campodigital.cl",
        "email_verified": True,
        "hd": WORKSPACE_DOMAIN,
        "name": "Javier Campo",
    }
    payload.update(overrides)
    return {key: value for key, value in payload.items() if value is not _ABSENT}


_ABSENT = object()
ABSENT: Any = _ABSENT
"""Sentinel for ``claims(hd=ABSENT)``: the claim is omitted, not set to None."""
