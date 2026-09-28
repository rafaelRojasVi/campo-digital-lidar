"""Google Workspace sign-in router end to end, against real PostgreSQL.

The provider client is faked here for the same reason the Entra tests fake
MSAL: what this file is about is the router's own behaviour -- the flow
cookie, the identity it persists, the session it mints, the Transelec-only
bootstrap, and the fact that a session is not an authorization. The
cryptographic half of Google sign-in is covered without a fake, and without
a network, in apps/api/tests/test_google_id_token.py.
"""

from __future__ import annotations

import json
from collections.abc import Generator, Mapping
from dataclasses import dataclass

import pytest
from app.config import Settings, get_settings
from app.deps import SESSION_COOKIE_NAME, get_google_oidc_client
from app.google_auth import AuthorizationRequest, GoogleSignIn, GoogleSignInError
from app.main import app
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, text

_ENCRYPTION_KEY = Fernet.generate_key().decode("utf-8")
_FLOW_COOKIE_NAME = "google_login_flow"
_BOOTSTRAP_EMAIL = "javier@campodigital.cl"


def _configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_password": "x",
        "google_client_id": "1234567890-abcdef.apps.googleusercontent.com",
        "google_client_secret": "fake-google-secret",
        "google_redirect_base_url": "https://testserver",
        "google_workspace_domain": "campodigital.cl",
        "platform_token_encryption_key": _ENCRYPTION_KEY,
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class FakeGoogleOidcClient:
    """A deterministic stand-in for GoogleOidcSignInClient: no network."""

    sign_in: GoogleSignIn | None = None
    error: GoogleSignInError | None = None
    completed_with: dict[str, str] | None = None

    def initiate(self, redirect_uri: str) -> AuthorizationRequest:
        del redirect_uri
        return AuthorizationRequest(
            auth_uri="https://accounts.google.com/o/oauth2/v2/auth?fake=1",
            flow_state=json.dumps(
                {"state": "fixed-state", "nonce": "fixed-nonce", "code_verifier": "fixed-verifier"}
            ),
        )

    def complete(
        self, flow_state: str, callback_params: Mapping[str, str], redirect_uri: str
    ) -> GoogleSignIn:
        del flow_state, redirect_uri
        self.completed_with = dict(callback_params)
        if self.error is not None:
            raise self.error
        assert self.sign_in is not None
        return self.sign_in


def _sign_in(**overrides: object) -> GoogleSignIn:
    values: dict[str, object] = {
        "subject": "104728391027364518293",
        "email": _BOOTSTRAP_EMAIL,
        "display_name": "Javier Campo",
        "hosted_domain": "campodigital.cl",
    }
    values.update(overrides)
    return GoogleSignIn(**values)


@pytest.fixture
def client(integration_engine: Engine) -> Generator[TestClient, None, None]:
    # https, not http: outside development the session cookie is issued with
    # `Secure`, and a test that then calls an authenticated route over plain
    # http would silently never send it -- proving nothing about RBAC.
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as test_client:
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


def _use(provider: FakeGoogleOidcClient, **settings_overrides: object) -> FakeGoogleOidcClient:
    app.dependency_overrides[get_settings] = lambda: _configured_settings(**settings_overrides)
    app.dependency_overrides[get_google_oidc_client] = lambda: provider
    return provider


def _login_and_get_flow_cookie(client: TestClient) -> str:
    response = client.get("/auth/google/login")
    assert response.status_code == 302, response.text
    cookie = response.cookies.get(_FLOW_COOKIE_NAME)
    assert cookie is not None
    return cookie


def _complete_sign_in(client: TestClient, provider: FakeGoogleOidcClient) -> Response:
    flow_cookie = _login_and_get_flow_cookie(client)
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)
    del provider
    return client.get("/auth/google/callback", params={"state": "fixed-state", "code": "abc"})


# ---------------------------------------------------------------------------
# /auth/google/login
# ---------------------------------------------------------------------------


def test_login_redirects_the_browser_to_google(client: TestClient) -> None:
    _use(FakeGoogleOidcClient())

    response = client.get("/auth/google/login")

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth")


def test_login_keeps_the_flow_state_in_an_httponly_cookie_the_browser_cannot_read(
    client: TestClient,
) -> None:
    _use(FakeGoogleOidcClient())

    response = client.get("/auth/google/login")

    set_cookie = response.headers.get("set-cookie", "")
    assert _FLOW_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.replace("samesite", "SameSite")
    # The state, nonce and verifier are encrypted at rest in the cookie.
    assert "fixed-verifier" not in set_cookie
    assert "fixed-nonce" not in set_cookie


def test_login_returns_503_when_google_credentials_are_not_configured(
    client: TestClient,
) -> None:
    # No overrides: the real get_google_oidc_client runs against the process's
    # actual Settings, which carry no GOOGLE_CLIENT_ID/SECRET in this test env.
    response = client.get("/auth/google/login")

    assert response.status_code == 503


def test_login_returns_503_when_the_token_encryption_key_is_missing(client: TestClient) -> None:
    _use(FakeGoogleOidcClient(), platform_token_encryption_key=None)

    response = client.get("/auth/google/login")

    assert response.status_code == 503


def test_login_cookie_is_not_secure_under_development(client: TestClient) -> None:
    _use(FakeGoogleOidcClient(), app_env="development")

    response = client.get("/auth/google/login")

    assert "Secure" not in response.headers.get("set-cookie", "")


def test_login_cookie_is_secure_outside_development(client: TestClient) -> None:
    _use(FakeGoogleOidcClient(), app_env="staging")

    response = client.get("/auth/google/login")

    assert "Secure" in response.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# /auth/google/callback -- the flow cookie
# ---------------------------------------------------------------------------


def test_callback_without_a_flow_cookie_is_rejected(client: TestClient) -> None:
    _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    response = client.get("/auth/google/callback", params={"state": "fixed-state", "code": "abc"})

    assert response.status_code == 400


def test_callback_with_a_tampered_flow_cookie_is_rejected(client: TestClient) -> None:
    _use(FakeGoogleOidcClient(sign_in=_sign_in()))
    client.cookies.set(_FLOW_COOKIE_NAME, "not-a-real-encrypted-cookie")

    response = client.get("/auth/google/callback", params={"state": "fixed-state", "code": "abc"})

    assert response.status_code == 400


def test_a_rejected_flow_cookie_never_reaches_the_provider(client: TestClient) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))
    client.cookies.set(_FLOW_COOKIE_NAME, "not-a-real-encrypted-cookie")

    client.get("/auth/google/callback", params={"state": "fixed-state", "code": "abc"})

    assert provider.completed_with is None


def test_callback_hands_the_provider_the_state_google_returned(client: TestClient) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    _complete_sign_in(client, provider)

    assert provider.completed_with == {"state": "fixed-state", "code": "abc"}


def test_callback_returns_401_and_no_session_when_the_sign_in_is_not_trusted(
    client: TestClient,
) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))
    flow_cookie = _login_and_get_flow_cookie(client)
    _use(FakeGoogleOidcClient(error=GoogleSignInError("hd claim missing")))
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)
    del provider

    response = client.get("/auth/google/callback", params={"state": "fixed-state", "code": "abc"})

    assert response.status_code == 401
    assert response.cookies.get(SESSION_COOKIE_NAME) is None


def test_a_rejected_sign_in_is_logged_with_its_reason_and_no_identity(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed real login must be visible in the platform logs on the day
    it happens, without writing the account, code or state into them."""

    _use(FakeGoogleOidcClient(sign_in=_sign_in()))
    flow_cookie = _login_and_get_flow_cookie(client)
    _use(FakeGoogleOidcClient(error=GoogleSignInError("hd claim missing")))
    client.cookies.set(_FLOW_COOKIE_NAME, flow_cookie)

    with caplog.at_level("WARNING", logger="app.routers.google_auth"):
        client.get("/auth/google/callback", params={"state": "fixed-state", "code": "secret-code"})
        client.cookies.delete(_FLOW_COOKIE_NAME)
        client.get("/auth/google/callback", params={"state": "fixed-state", "code": "abc"})

    messages = [record.getMessage() for record in caplog.records]
    assert any("hd claim missing" in message for message in messages)
    assert any("flow cookie missing" in message for message in messages)
    assert not any("secret-code" in message or "fixed-state" in message for message in messages)


# ---------------------------------------------------------------------------
# /auth/google/callback -- the identity and the session
# ---------------------------------------------------------------------------


def test_callback_starts_a_real_session_and_lands_on_the_dashboard(
    client: TestClient,
) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    response = _complete_sign_in(client, provider)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/"
    assert response.cookies.get(SESSION_COOKIE_NAME) is not None


def test_callback_records_the_user_under_googles_subject_not_their_email(
    client: TestClient, integration_engine: Engine
) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    _complete_sign_in(client, provider)

    with integration_engine.connect() as connection:
        row = connection.execute(
            text("SELECT identity_kind, identity_key, display_name, email FROM platform.app_user")
        ).one()
    assert row.identity_kind == "google"
    assert row.identity_key == "104728391027364518293"
    assert row.display_name == "Javier Campo"
    assert row.email == _BOOTSTRAP_EMAIL


def test_a_second_sign_in_reuses_the_same_user(
    client: TestClient, integration_engine: Engine
) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    _complete_sign_in(client, provider)
    _complete_sign_in(client, provider)

    with integration_engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM platform.app_user")).scalar_one()
    assert count == 1


def test_the_session_cookie_is_httponly_and_the_flow_cookie_is_cleared(
    client: TestClient,
) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    response = _complete_sign_in(client, provider)

    session_cookies = [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(SESSION_COOKIE_NAME)
    ]
    assert session_cookies and all("HttpOnly" in value for value in session_cookies)
    assert response.cookies.get(_FLOW_COOKIE_NAME) in (None, "")


def test_sign_in_stores_no_google_token_anywhere(
    client: TestClient, integration_engine: Engine
) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    _complete_sign_in(client, provider)

    with integration_engine.connect() as connection:
        grants = connection.execute(
            text("SELECT count(*) FROM platform.ms_graph_grant")
        ).scalar_one()
    assert grants == 0


# ---------------------------------------------------------------------------
# Authentication is not authorization
# ---------------------------------------------------------------------------


def test_a_valid_workspace_account_without_a_transelec_grant_is_forbidden(
    client: TestClient,
) -> None:
    provider = _use(
        FakeGoogleOidcClient(
            sign_in=_sign_in(subject="sub-sin-permisos", email="otro@campodigital.cl")
        ),
        transelec_bootstrap_admin_email=_BOOTSTRAP_EMAIL,
    )

    sign_in_response = _complete_sign_in(client, provider)
    assert sign_in_response.status_code == 302

    # Authenticated -- the session resolves, /auth/me answers.
    assert client.get("/auth/me").status_code == 200
    # ...and still not authorized for this product.
    assert client.get("/transelec/summary").status_code == 403


def test_a_signed_in_account_with_no_grant_holds_no_product_grants_at_all(
    client: TestClient,
) -> None:
    provider = _use(
        FakeGoogleOidcClient(
            sign_in=_sign_in(subject="sub-sin-permisos", email="otro@campodigital.cl")
        ),
        transelec_bootstrap_admin_email=_BOOTSTRAP_EMAIL,
    )

    _complete_sign_in(client, provider)

    assert client.get("/auth/me").json()["product_grants"] == []


# ---------------------------------------------------------------------------
# The Transelec-only bootstrap
# ---------------------------------------------------------------------------


def test_the_configured_address_receives_admin_on_transelec_only(
    client: TestClient,
) -> None:
    provider = _use(
        FakeGoogleOidcClient(sign_in=_sign_in()),
        transelec_bootstrap_admin_email=_BOOTSTRAP_EMAIL,
    )

    _complete_sign_in(client, provider)

    assert client.get("/auth/me").json()["product_grants"] == [
        {"product_key": "transelect", "role": "admin"}
    ]


def test_the_bootstrap_never_grants_lidar_or_forestry(
    client: TestClient, integration_engine: Engine
) -> None:
    provider = _use(
        FakeGoogleOidcClient(sign_in=_sign_in()),
        transelec_bootstrap_admin_email=_BOOTSTRAP_EMAIL,
    )

    _complete_sign_in(client, provider)

    with integration_engine.connect() as connection:
        products = (
            connection.execute(text("SELECT product_key FROM platform.product_grant"))
            .scalars()
            .all()
        )
    assert set(products) == {"transelect"}


def test_no_bootstrap_at_all_when_no_address_is_configured(client: TestClient) -> None:
    provider = _use(FakeGoogleOidcClient(sign_in=_sign_in()))

    _complete_sign_in(client, provider)

    assert client.get("/auth/me").json()["product_grants"] == []


def test_the_bootstrap_grant_is_audited_as_a_configuration_grant(
    client: TestClient, integration_engine: Engine
) -> None:
    provider = _use(
        FakeGoogleOidcClient(sign_in=_sign_in()),
        transelec_bootstrap_admin_email=_BOOTSTRAP_EMAIL,
    )

    _complete_sign_in(client, provider)

    with integration_engine.connect() as connection:
        events = connection.execute(
            text(
                """
                SELECT actor_app_user_id, product_key, subject_id, metadata
                FROM platform.audit_event
                WHERE event_type = 'product_grant.changed'
                """
            )
        ).all()
        user_id = connection.execute(
            text("SELECT id FROM platform.app_user WHERE email = :email"),
            {"email": _BOOTSTRAP_EMAIL},
        ).scalar_one()
    assert [tuple(event) for event in events] == [
        (
            None,
            "transelect",
            str(user_id),
            {"previous_role": None, "role": "admin", "via": "bootstrap_email"},
        )
    ]


# ---------------------------------------------------------------------------
# Admin handoff: the bootstrap admin makes a named account a second admin
# ---------------------------------------------------------------------------

_SECOND_ADMIN_EMAIL = "second-admin@campodigital.cl"


def _new_browser() -> TestClient:
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def test_bootstrap_admin_grants_admin_to_a_named_account_through_the_api(
    client: TestClient, integration_engine: Engine
) -> None:
    # 1. The bootstrap address signs in and becomes Transelec admin.
    provider = _use(
        FakeGoogleOidcClient(sign_in=_sign_in()),
        transelec_bootstrap_admin_email=_BOOTSTRAP_EMAIL,
    )
    _complete_sign_in(client, provider)
    assert client.get("/api/auth/me").json()["product_grants"] == [
        {"product_key": "transelect", "role": "admin"}
    ]

    # 2. The named account signs in once, in its own browser: authenticated,
    #    not authorized, and not bootstrapped (it is not the configured email).
    with _new_browser() as second:
        provider.sign_in = _sign_in(
            subject="sub-second-admin", email=_SECOND_ADMIN_EMAIL, display_name="Second Admin"
        )
        assert _complete_sign_in(second, provider).status_code == 302
        assert second.get("/api/auth/me").json()["product_grants"] == []
        assert second.get("/api/auth/admin/product-grants/transelect").status_code == 403

        # 3. The bootstrap admin grants it admin through the same-origin API,
        #    exactly as a browser session would: session cookie + CSRF token.
        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        response = client.post(
            "/api/auth/admin/product-grants/transelect",
            json={"email": _SECOND_ADMIN_EMAIL, "role": "admin"},
            headers={"X-CSRF-Token": csrf, "Origin": "https://testserver"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["role"] == "admin"

        # 4. The named account now administers Transelec -- and only Transelec.
        assert second.get("/api/auth/me").json()["product_grants"] == [
            {"product_key": "transelect", "role": "admin"}
        ]
        grants = second.get("/api/auth/admin/product-grants/transelect")
        assert grants.status_code == 200
        assert {(g["email"], g["role"]) for g in grants.json()} == {
            (_BOOTSTRAP_EMAIL, "admin"),
            (_SECOND_ADMIN_EMAIL, "admin"),
        }

    # 5. The bootstrap admin keeps its grant, and both changes are audited.
    assert client.get("/api/auth/me").json()["product_grants"] == [
        {"product_key": "transelect", "role": "admin"}
    ]
    with integration_engine.connect() as connection:
        vias = (
            connection.execute(
                text(
                    """
                    SELECT metadata->>'via' FROM platform.audit_event
                    WHERE event_type = 'product_grant.changed' ORDER BY id
                    """
                )
            )
            .scalars()
            .all()
        )
    assert vias == ["bootstrap_email", "admin_api"]
