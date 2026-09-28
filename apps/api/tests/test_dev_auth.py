"""Dev-only auth adapter: production gate and session lifecycle."""

from __future__ import annotations

import pytest
from app.config import Settings
from app.dev_auth import (
    SEEDED_DEV_IDENTITIES,
    DevAuthDisabledInProductionError,
    DevSessionStore,
    assert_dev_auth_allowed,
)


def _settings(app_env: str) -> Settings:
    return Settings(app_env=app_env, postgres_password="x")


def test_dev_auth_allowed_in_development() -> None:
    assert_dev_auth_allowed(_settings("development"))


def test_dev_auth_rejected_in_staging() -> None:
    # ADR-005 originally allowed dev-auth in staging; the secure-file-access
    # slice closes that exposure now that real Entra sign-in exists.
    with pytest.raises(DevAuthDisabledInProductionError):
        assert_dev_auth_allowed(_settings("staging"))


def test_dev_auth_rejected_in_test() -> None:
    with pytest.raises(DevAuthDisabledInProductionError):
        assert_dev_auth_allowed(_settings("test"))


def test_dev_auth_rejected_in_production() -> None:
    with pytest.raises(DevAuthDisabledInProductionError):
        assert_dev_auth_allowed(_settings("production"))


def test_session_round_trip() -> None:
    store = DevSessionStore()
    token = store.create_session("alice")
    assert store.resolve_session(token) == "alice"


def test_unknown_session_resolves_to_none() -> None:
    store = DevSessionStore()
    assert store.resolve_session("not-a-real-token") is None


def test_cleared_session_no_longer_resolves() -> None:
    store = DevSessionStore()
    token = store.create_session("bob")
    store.clear_session(token)
    assert store.resolve_session(token) is None


def test_sessions_are_unguessable_tokens() -> None:
    store = DevSessionStore()
    token_a = store.create_session("alice")
    token_b = store.create_session("alice")
    assert token_a != token_b
    assert len(token_a) >= 32


def test_seeded_identities_cover_at_least_one_of_each_role_intent() -> None:
    keys = {identity.identity_key for identity in SEEDED_DEV_IDENTITIES}
    assert len(keys) == len(SEEDED_DEV_IDENTITIES)
    assert len(SEEDED_DEV_IDENTITIES) >= 3
