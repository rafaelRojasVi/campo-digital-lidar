from __future__ import annotations

import json

import pytest
from app.config import Settings
from app.entra_auth import (
    EntraNotConfiguredError,
    EntraSignInError,
    MsalEntraOidcClient,
)

_REDIRECT_URI = "http://localhost:8000/auth/entra/callback"


def _configured_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="development",
        postgres_password="x",
        entra_client_id="11111111-1111-1111-1111-111111111111",
        entra_client_secret="fake-secret",
    )


def test_msal_client_requires_client_id_and_secret() -> None:
    settings = Settings(_env_file=None, app_env="development", postgres_password="x")

    with pytest.raises(EntraNotConfiguredError):
        MsalEntraOidcClient(settings)


def test_initiate_targets_the_common_multitenant_and_personal_account_authority() -> None:
    client = MsalEntraOidcClient(_configured_settings())

    request = client.initiate(_REDIRECT_URI)

    assert request.auth_uri.startswith(
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    )


def test_initiate_flow_state_carries_a_state_and_pkce_verifier() -> None:
    client = MsalEntraOidcClient(_configured_settings())

    request = client.initiate(_REDIRECT_URI)
    flow = json.loads(request.flow_state)

    assert flow["state"]
    assert flow["code_verifier"]


def test_complete_rejects_a_mismatched_state() -> None:
    client = MsalEntraOidcClient(_configured_settings())
    request = client.initiate(_REDIRECT_URI)

    with pytest.raises(EntraSignInError):
        client.complete(
            request.flow_state,
            {"state": "not-the-real-state", "code": "irrelevant"},
            _REDIRECT_URI,
        )


def test_complete_surfaces_a_server_reported_error_without_a_network_call() -> None:
    client = MsalEntraOidcClient(_configured_settings())
    request = client.initiate(_REDIRECT_URI)
    real_state = json.loads(request.flow_state)["state"]

    with pytest.raises(EntraSignInError, match="User declined consent"):
        client.complete(
            request.flow_state,
            {
                "state": real_state,
                "error": "access_denied",
                "error_description": "User declined consent",
            },
            _REDIRECT_URI,
        )
