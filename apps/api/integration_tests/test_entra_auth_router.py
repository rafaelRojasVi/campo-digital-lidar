"""Microsoft Entra sign-in router end-to-end: login redirect, callback
identity resolution, bootstrap-admin grant, encrypted Graph token storage,
and the security-relevant cookie flags — against real PostgreSQL.

app.routers.entra_auth is exercised through real HTTP calls (unlike
app.routers.dev_auth, whose conditional mounting under APP_ENV=development
forces its integration tests to call handlers directly): this router is
mounted unconditionally, like csrf_router, so the integration process's
fixed APP_ENV=test does not change whether it is reachable.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Mapping
from dataclasses import dataclass

import pytest
from app.config import Settings, get_settings
from app.deps import SESSION_COOKIE_NAME, get_entra_oidc_client
from app.entra_auth import AuthorizationRequest, EntraSignIn, EntraSignInError
from app.main import app
from app.token_crypto import decrypt_token
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

_ENCRYPTION_KEY = Fernet.generate_key().decode("utf-8")
_FLOW_COOKIE_NAME = "entra_login_flow"


def _configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_password": "x",
        "entra_client_id": "11111111-1111-1111-1111-111111111111",
        "entra_client_secret": "fake-secret",
        "entra_redirect_base_url": "http://testserver",
        "platform_token_encryption_key": _ENCRYPTION_KEY,
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class FakeEntraOidcClient:
    """A deterministic stand-in for MsalEntraOidcClient: no network, no MSAL."""

    sign_in: EntraSignIn | None = None
    error: EntraSignInError | None = None

    def initiate(self, redirect_uri: str) -> AuthorizationRequest:
        del redirect_uri
        return AuthorizationRequest(
            auth_uri="https://login.microsoftonline.com/common/oauth2/v2.0/authorize?fake=1",
            flow_state=json.dumps({"state": "fixed-state"}),
        )

    def complete(
        self, flow_state: str, callback_params: Mapping[str, str], redirect_uri: str
    ) -> EntraSignIn:
        del flow_state, callback_params, redirect_uri
        if self.error is not None:
            raise self.error
        assert self.sign_in is not None
        return self.sign_in


def _sign_in(**overrides: object) -> EntraSignIn:
    values: dict[str, object] = {
        "tenant_id": "tenant-x",
        "object_id": "oid-javier",
        "display_name": "Javier",
        "email": "javier@example.com",
        "access_token": "raw-access-token",
        "refresh_token": "raw-refresh-token",
        "scope": "openid profile User.Read",
        "expires_in": 3600,
    }
    values.update(overrides)
    return EntraSignIn(**values)


@pytest.fixture
def client(integration_engine: Engine) -> Generator[TestClient, None, None]:
    with TestClient(app, follow_redirects=False) as test_client:
        test_client.engine = integration_engine
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.connect() as conn:
        for table in ("ms_graph_grant", "session", "audit_event", "product_grant", "app_user"):
            conn.execute(text(f"DELETE FROM platform.{table}"))
        conn.commit()


def _login_and_get_flow_cookie(client: TestClient) -> str:
    response = client.get("/auth/entra/login")
    assert response.status_code == 302, response.text
    cookie = response.cookies.get(_FLOW_COOKIE_NAME)
    assert cookie is not None
    return cookie


# ---------------------------------------------------------------------------
# /auth/entra/login
# ---------------------------------------------------------------------------


def test_login_redirects_to_the_microsoft_authorization_uri(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient()

    response = client.get("/auth/entra/login")

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://login.microsoftonline.com/common/")


def test_login_sets_an_httponly_flow_cookie(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient()

    response = client.get("/auth/entra/login")

    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert _FLOW_COOKIE_NAME in set_cookie


def test_login_returns_503_when_entra_client_credentials_are_not_configured(
    client: TestClient,
) -> None:
    # No overrides: the real get_entra_oidc_client runs against the process's
    # actual Settings, which have no ENTRA_CLIENT_ID/SECRET in this test env.
    response = client.get("/auth/entra/login")

    assert response.status_code == 503


def test_login_returns_503_when_the_token_encryption_key_is_missing(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings(
        platform_token_encryption_key=None
    )
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient()

    response = client.get("/auth/entra/login")

    assert response.status_code == 503


def test_login_cookie_is_not_secure_under_development(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings(app_env="development")
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient()

    response = client.get("/auth/entra/login")

    assert "Secure" not in response.headers.get("set-cookie", "")


def test_login_cookie_is_secure_outside_development(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings(app_env="staging")
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient()

    response = client.get("/auth/entra/login")

    assert "Secure" in response.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# /auth/entra/callback
# ---------------------------------------------------------------------------


def test_callback_without_a_flow_cookie_is_rejected(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        sign_in=_sign_in()
    )

    response = client.post("/auth/entra/callback", data={"state": "fixed-state", "code": "abc"})

    assert response.status_code == 400


def test_callback_with_a_tampered_flow_cookie_is_rejected(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        sign_in=_sign_in()
    )
    client.cookies.set(_FLOW_COOKIE_NAME, "not-a-real-encrypted-cookie")

    response = client.post("/auth/entra/callback", data={"state": "fixed-state", "code": "abc"})

    assert response.status_code == 400


def test_callback_returns_401_when_sign_in_fails(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        sign_in=_sign_in()
    )
    flow_cookie = _login_and_get_flow_cookie(client)
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        error=EntraSignInError("User declined consent")
    )
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)

    response = client.post(
        "/auth/entra/callback",
        data={"state": "fixed-state", "error": "access_denied"},
    )

    assert response.status_code == 401


def test_callback_creates_a_user_and_sets_a_real_session_cookie(
    client: TestClient, integration_engine: Engine
) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        sign_in=_sign_in()
    )
    flow_cookie = _login_and_get_flow_cookie(client)
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)

    response = client.post(
        "/auth/entra/callback",
        data={"state": "fixed-state", "code": "abc"},
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/"
    session_cookie = response.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie is not None

    with integration_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT identity_kind, identity_key, display_name, email "
                "FROM platform.app_user WHERE identity_kind = 'entra'"
            )
        ).one()
    assert row.identity_key == "tenant-x:oid-javier"
    assert row.display_name == "Javier"
    assert row.email == "javier@example.com"


def test_callback_deletes_the_flow_cookie_after_success(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        sign_in=_sign_in()
    )
    flow_cookie = _login_and_get_flow_cookie(client)
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)

    response = client.post(
        "/auth/entra/callback",
        data={"state": "fixed-state", "code": "abc"},
    )

    delete_headers = [h for h in response.headers.get_list("set-cookie") if _FLOW_COOKIE_NAME in h]
    assert any("max-age=0" in h.lower() for h in delete_headers)


def test_callback_grants_bootstrap_admin_for_the_configured_identity(
    client: TestClient, integration_engine: Engine
) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings(
        platform_bootstrap_admin_tenant_id="tenant-x",
        platform_bootstrap_admin_object_id="oid-javier",
    )
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        sign_in=_sign_in()
    )
    flow_cookie = _login_and_get_flow_cookie(client)
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)

    response = client.post(
        "/auth/entra/callback",
        data={"state": "fixed-state", "code": "abc"},
    )
    assert response.status_code == 302, response.text

    with integration_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT g.product_key, g.role FROM platform.product_grant g "
                "JOIN platform.app_user u ON u.id = g.app_user_id "
                "WHERE u.identity_key = 'tenant-x:oid-javier'"
            )
        ).all()
    assert {(r.product_key, r.role) for r in rows} == {
        ("lidar", "admin"),
        ("forestry", "admin"),
        ("transelect", "admin"),
    }


def test_callback_stores_the_graph_tokens_encrypted_not_in_plaintext(
    client: TestClient, integration_engine: Engine
) -> None:
    app.dependency_overrides[get_settings] = lambda: _configured_settings()
    app.dependency_overrides[get_entra_oidc_client] = lambda: FakeEntraOidcClient(
        sign_in=_sign_in()
    )
    flow_cookie = _login_and_get_flow_cookie(client)
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)

    response = client.post(
        "/auth/entra/callback",
        data={"state": "fixed-state", "code": "abc"},
    )
    assert response.status_code == 302, response.text

    with integration_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT access_token_encrypted, refresh_token_encrypted, scope "
                "FROM platform.ms_graph_grant g "
                "JOIN platform.app_user u ON u.id = g.app_user_id "
                "WHERE u.identity_key = 'tenant-x:oid-javier'"
            )
        ).one()

    access_ciphertext = bytes(row.access_token_encrypted)
    refresh_ciphertext = bytes(row.refresh_token_encrypted)
    assert b"raw-access-token" not in access_ciphertext
    assert b"raw-refresh-token" not in refresh_ciphertext
    assert decrypt_token(access_ciphertext, key=_ENCRYPTION_KEY) == "raw-access-token"
    assert decrypt_token(refresh_ciphertext, key=_ENCRYPTION_KEY) == "raw-refresh-token"
    assert row.scope == "openid profile User.Read"
