"""Platform CSRF primitive: token minting, verification, and origin trust.

These are pure-logic tests for ``app.csrf``. The HTTP-level fail-closed
behavior of the ``require_csrf`` dependency (missing token, mismatched
token, cross-origin request) is exercised end-to-end against a real session
in ``apps/api/integration_tests/test_csrf_router.py``.
"""

from __future__ import annotations

import pytest
from app.csrf import (
    CSRF_HEADER_NAME,
    is_trusted_origin,
    mint_csrf_token,
    parse_trusted_origins,
    verify_csrf_token,
)


def test_header_name_is_the_documented_one() -> None:
    assert CSRF_HEADER_NAME == "X-CSRF-Token"


def test_minted_token_verifies_against_its_own_session() -> None:
    session_token = "session-secret-a"
    token = mint_csrf_token(session_token)

    assert verify_csrf_token(token, session_token=session_token) is True


def test_two_mints_for_the_same_session_are_different_and_both_valid() -> None:
    """Tokens are minted per request, not derived deterministically, so an
    already-issued token is never invalidated by issuing another one."""

    session_token = "session-secret-a"
    first = mint_csrf_token(session_token)
    second = mint_csrf_token(session_token)

    assert first != second
    assert verify_csrf_token(first, session_token=session_token) is True
    assert verify_csrf_token(second, session_token=session_token) is True


def test_token_minted_for_one_session_is_rejected_for_another() -> None:
    """Session binding: a valid token stolen from (or minted by) a different
    session must not authorize a mutation on this one."""

    token = mint_csrf_token("attacker-session")

    assert verify_csrf_token(token, session_token="victim-session") is False


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "not-a-token",
        "nonce-without-signature.",
        ".signature-without-nonce",
        "a.b.c",
        "   ",
    ],
)
def test_malformed_tokens_are_rejected(candidate: str) -> None:
    assert verify_csrf_token(candidate, session_token="session-secret-a") is False


def test_tampered_signature_is_rejected() -> None:
    session_token = "session-secret-a"
    nonce, _, signature = mint_csrf_token(session_token).partition(".")
    tampered = f"{nonce}.{signature[:-1]}{'A' if signature[-1] != 'A' else 'B'}"

    assert verify_csrf_token(tampered, session_token=session_token) is False


def test_tampered_nonce_is_rejected() -> None:
    session_token = "session-secret-a"
    nonce, _, signature = mint_csrf_token(session_token).partition(".")

    assert verify_csrf_token(f"{nonce}x.{signature}", session_token=session_token) is False


def test_token_does_not_leak_the_session_secret() -> None:
    session_token = "session-secret-a"
    token = mint_csrf_token(session_token)

    assert session_token not in token


def test_parse_trusted_origins_splits_and_strips() -> None:
    assert parse_trusted_origins(" https://a.example , https://b.example ,, ") == (
        "https://a.example",
        "https://b.example",
    )


def test_parse_trusted_origins_of_none_is_empty() -> None:
    assert parse_trusted_origins(None) == ()


def test_explicitly_configured_origin_is_trusted() -> None:
    assert (
        is_trusted_origin(
            "https://portal.example",
            request_host="api.example",
            app_env="production",
            trusted_origins=("https://portal.example",),
        )
        is True
    )


def test_unconfigured_origin_is_not_trusted_in_production() -> None:
    assert (
        is_trusted_origin(
            "https://evil.example",
            request_host="api.example",
            app_env="production",
            trusted_origins=("https://portal.example",),
        )
        is False
    )


def test_request_own_host_is_trusted_without_configuration() -> None:
    """Same-origin requests (browser Origin equals the host the request was
    addressed to) stay trusted with no configuration at all."""

    assert (
        is_trusted_origin(
            "https://api.example",
            request_host="api.example",
            app_env="production",
            trusted_origins=(),
        )
        is True
    )


def test_localhost_is_trusted_only_outside_production_and_staging() -> None:
    for app_env in ("development", "test"):
        assert (
            is_trusted_origin(
                "http://localhost:5100",
                request_host="127.0.0.1:8000",
                app_env=app_env,
                trusted_origins=(),
            )
            is True
        )

    for app_env in ("staging", "production"):
        assert (
            is_trusted_origin(
                "http://localhost:5100",
                request_host="127.0.0.1:8000",
                app_env=app_env,
                trusted_origins=(),
            )
            is False
        )


def test_a_lookalike_host_suffix_is_not_trusted() -> None:
    assert (
        is_trusted_origin(
            "https://evil-api.example",
            request_host="api.example",
            app_env="production",
            trusted_origins=(),
        )
        is False
    )


def test_missing_host_never_makes_an_origin_trusted() -> None:
    assert (
        is_trusted_origin(
            "https://api.example",
            request_host=None,
            app_env="production",
            trusted_origins=(),
        )
        is False
    )


def test_unparseable_origin_is_not_trusted() -> None:
    assert (
        is_trusted_origin(
            "null",
            request_host="api.example",
            app_env="development",
            trusted_origins=(),
        )
        is False
    )
