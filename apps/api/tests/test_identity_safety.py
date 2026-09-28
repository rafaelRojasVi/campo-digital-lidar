from __future__ import annotations

import pytest
from app.config import Settings
from app.identity_safety import (
    ProductionIdentityNotConfiguredError,
    require_production_identity_configuration,
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "production",
        "postgres_password": "x",
    }
    values.update(overrides)
    return Settings(**values)


def test_rejects_production_with_no_identity_configuration_at_all() -> None:
    with pytest.raises(ProductionIdentityNotConfiguredError):
        require_production_identity_configuration(_settings())


def test_rejects_production_missing_only_the_token_encryption_key() -> None:
    settings = _settings(
        entra_client_id="11111111-1111-1111-1111-111111111111",
        entra_client_secret="fake-secret",
    )

    with pytest.raises(ProductionIdentityNotConfiguredError):
        require_production_identity_configuration(settings)


def test_allows_production_with_full_identity_configuration() -> None:
    settings = _settings(
        entra_client_id="11111111-1111-1111-1111-111111111111",
        entra_client_secret="fake-secret",
        platform_token_encryption_key="fake-key",
    )

    require_production_identity_configuration(settings)  # must not raise


@pytest.mark.parametrize("app_env", ["development", "test", "staging"])
def test_allows_incomplete_identity_configuration_outside_production(app_env: str) -> None:
    require_production_identity_configuration(_settings(app_env=app_env))  # must not raise


# ---------------------------------------------------------------------------
# Two providers, one requirement
# ---------------------------------------------------------------------------
#
# Transelec signs in with Google Workspace (ADR-009) while the other
# products stay on Entra, so "production can authenticate somebody" is no
# longer "Entra is configured". It is: a token encryption key, plus at least
# one COMPLETE provider. A half-configured provider is rejected outright
# rather than ignored -- a deployment that set GOOGLE_CLIENT_ID and forgot
# the secret has a broken sign-in button, and should learn that at startup.


def _google(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "google_client_id": "1234567890-abcdef.apps.googleusercontent.com",
        "google_client_secret": "fake-google-secret",
        "platform_token_encryption_key": "fake-key",
    }
    values.update(overrides)
    return _settings(**values)


def test_allows_a_production_deployment_that_only_offers_google_sign_in() -> None:
    require_production_identity_configuration(_google())  # must not raise


def test_rejects_production_with_a_google_client_id_but_no_secret() -> None:
    with pytest.raises(ProductionIdentityNotConfiguredError, match="GOOGLE_CLIENT_SECRET"):
        require_production_identity_configuration(_google(google_client_secret=None))


def test_rejects_production_with_a_google_secret_but_no_client_id() -> None:
    with pytest.raises(ProductionIdentityNotConfiguredError, match="GOOGLE_CLIENT_ID"):
        require_production_identity_configuration(_google(google_client_id=None))


def test_rejects_production_with_an_entra_client_id_but_no_secret() -> None:
    settings = _settings(
        entra_client_id="11111111-1111-1111-1111-111111111111",
        platform_token_encryption_key="fake-key",
    )

    with pytest.raises(ProductionIdentityNotConfiguredError, match="ENTRA_CLIENT_SECRET"):
        require_production_identity_configuration(settings)


def test_rejects_production_that_offers_google_but_no_token_encryption_key() -> None:
    with pytest.raises(ProductionIdentityNotConfiguredError, match="PLATFORM_TOKEN_ENCRYPTION_KEY"):
        require_production_identity_configuration(_google(platform_token_encryption_key=None))


def test_allows_a_production_deployment_that_offers_both_providers() -> None:
    require_production_identity_configuration(
        _google(
            entra_client_id="11111111-1111-1111-1111-111111111111",
            entra_client_secret="fake-secret",
        )
    )  # must not raise
