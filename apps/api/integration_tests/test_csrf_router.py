"""Platform CSRF mechanism at the HTTP boundary: fail-closed on mutations.

Covers the shared ``app.csrf`` dependency as wired onto the pre-existing
generic ingestion mutations. The identical mechanism protects every
Transelec mutation route; those routes are exercised against the same four
cases in ``test_transelec_router.py``.
"""

from __future__ import annotations

import zipfile
from collections.abc import Generator
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from app.access_repository import (
    grant_product_role,
    list_grants_for_user,
    resolve_or_create_app_user,
)
from app.csrf import CSRF_HEADER_NAME, mint_csrf_token
from app.deps import SESSION_COOKIE_NAME, get_object_store
from app.dev_auth import DEFAULT_SEED_GRANTS, DEV_IDENTITY_KIND, SEEDED_DEV_IDENTITIES
from app.main import app
from app.object_store import LocalObjectStore
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, text

_platform_sessions = PlatformSessionStore()

# TestClient addresses http://testserver, so this is the request's own origin.
_SAME_ORIGIN = "http://testserver"
_ATTACKER_ORIGIN = "https://evil.example"

# Every pre-existing generic mutation route guarded by app.csrf.
GENERIC_MUTATION_KINDS = ("upload", "retry")


@pytest.fixture
def client(integration_engine: Engine, tmp_path: Path) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_object_store] = lambda: LocalObjectStore(tmp_path / "object-store")

    with TestClient(app) as test_client:
        test_client.engine = integration_engine
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.connect() as conn:
        for table in (
            "generated_artifact",
            "processing_attempt",
            "processing_job",
            "ingestion_run",
            "source_observation",
            "source_snapshot",
            "source_asset",
            "source_system",
            "audit_event",
            "session",
            "product_grant",
            "app_user",
        ):
            conn.execute(text(f"DELETE FROM platform.{table}"))
        conn.commit()


def _login(client: TestClient, identity_key: str) -> str:
    """Authenticate as a seeded dev identity; return the raw session secret."""

    engine: Engine = client.engine
    display_name = next(
        (
            identity.display_name
            for identity in SEEDED_DEV_IDENTITIES
            if identity.identity_key == identity_key
        ),
        identity_key,
    )
    with engine.connect() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind=DEV_IDENTITY_KIND,
            identity_key=identity_key,
            display_name=display_name,
        )
        if not list_grants_for_user(connection, app_user_id=user.id):
            for product_key, role in DEFAULT_SEED_GRANTS.get(identity_key, ()):
                grant_product_role(
                    connection, app_user_id=user.id, product_key=product_key, role=role
                )
        raw_secret = _platform_sessions.create_session(
            connection, app_user_id=user.id, ttl=timedelta(hours=8)
        )
        connection.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)
    return raw_secret


def _token(client: TestClient) -> str:
    response = client.get("/auth/csrf")
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def _forestry_zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("predio.shp", b"x")
        archive.writestr("predio.shx", b"y")
        archive.writestr("predio.dbf", b"z")
        archive.writestr("predio.prj", b"w")
    return buffer.getvalue()


def _upload(client: TestClient, **kwargs: Any) -> Response:
    return client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
        **kwargs,
    )


def _queued_job_id(client: TestClient) -> int:
    """Create one job through a fully authorized upload."""

    response = _upload(client, headers={CSRF_HEADER_NAME: _token(client), "Origin": _SAME_ORIGIN})
    assert response.status_code == 200, response.text
    return int(response.json()["job_id"])


def _mutation(client: TestClient, kind: str, **kwargs: Any) -> Response:
    """Issue one generic-ingestion mutation, by route kind."""

    if kind == "upload":
        return _upload(client, **kwargs)
    return client.post(f"/ingesta/jobs/{_queued_job_id(client)}/retry", **kwargs)


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------


def test_csrf_token_requires_authentication(client: TestClient) -> None:
    assert client.get("/auth/csrf").status_code == 401


def test_csrf_token_endpoint_returns_a_token_and_its_header_name(client: TestClient) -> None:
    _login(client, "dev-operator")

    body = client.get("/auth/csrf").json()

    assert body["header_name"] == CSRF_HEADER_NAME
    assert isinstance(body["csrf_token"], str)
    assert body["csrf_token"]


def test_csrf_token_is_never_placed_in_a_cookie(client: TestClient) -> None:
    """The token is delivered in a normal JSON body only: it is not a
    double-submit cookie, so a cookie jar the browser attaches automatically
    can never carry it for an attacker's page."""

    _login(client, "dev-operator")
    before = set(client.cookies.keys())

    response = client.get("/auth/csrf")

    assert response.status_code == 200
    assert set(client.cookies.keys()) == before
    assert "set-cookie" not in {header.lower() for header in response.headers}


# ---------------------------------------------------------------------------
# Fail-closed on both pre-existing generic mutation routes
#
# The four minimum cases (absent, mismatched, valid + same-origin,
# cross-origin) run against every generic mutation route, matching how
# test_transelec_router.py parametrizes the same cases over the four
# Transelec mutations.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", GENERIC_MUTATION_KINDS)
def test_mutation_without_a_csrf_token_is_forbidden(client: TestClient, kind: str) -> None:
    _login(client, "dev-operator")

    response = _mutation(client, kind)

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF verification failed."


@pytest.mark.parametrize("kind", GENERIC_MUTATION_KINDS)
def test_mutation_with_a_mismatched_csrf_token_is_forbidden(client: TestClient, kind: str) -> None:
    _login(client, "dev-operator")
    valid = _token(client)
    tampered = valid[:-1] + ("A" if valid[-1] != "A" else "B")

    response = _mutation(client, kind, headers={CSRF_HEADER_NAME: tampered})

    assert response.status_code == 403


@pytest.mark.parametrize("kind", GENERIC_MUTATION_KINDS)
def test_mutation_with_a_valid_token_and_same_origin_passes_csrf(
    client: TestClient, kind: str
) -> None:
    """Not 403: the request reaches the route's own logic — 200 for the
    upload boundary, 409 for retry (a freshly queued job is not failed)."""

    _login(client, "dev-operator")

    response = _mutation(
        client, kind, headers={CSRF_HEADER_NAME: _token(client), "Origin": _SAME_ORIGIN}
    )

    assert response.status_code != 403, response.text
    assert response.status_code in (200, 409), response.text


@pytest.mark.parametrize("kind", GENERIC_MUTATION_KINDS)
def test_cross_origin_mutation_is_forbidden_even_with_a_valid_token(
    client: TestClient, kind: str
) -> None:
    """The Origin layer is independent of the token layer: a valid token
    presented from an untrusted origin is still rejected."""

    _login(client, "dev-operator")

    response = _mutation(
        client, kind, headers={CSRF_HEADER_NAME: _token(client), "Origin": _ATTACKER_ORIGIN}
    )

    assert response.status_code == 403


@pytest.mark.parametrize("kind", GENERIC_MUTATION_KINDS)
def test_mutation_without_a_session_is_unauthenticated_not_a_csrf_failure(
    client: TestClient, kind: str
) -> None:
    """No session cookie means no cookie-authenticated action to ride, so the
    answer stays 401 rather than silently becoming a CSRF 403."""

    # The retry variant needs an authorized upload to have created a job
    # first; the session is dropped again before the mutation under test.
    if kind == "retry":
        _login(client, "dev-operator")
        job_id = _queued_job_id(client)
        client.cookies.clear()
        response = client.post(
            f"/ingesta/jobs/{job_id}/retry",
            headers={CSRF_HEADER_NAME: mint_csrf_token("some-other-secret")},
        )
    else:
        response = _mutation(
            client, kind, headers={CSRF_HEADER_NAME: mint_csrf_token("some-other-secret")}
        )

    assert response.status_code == 401


def test_upload_with_a_token_minted_for_another_session_is_forbidden(client: TestClient) -> None:
    """Session binding at the HTTP boundary: an attacker who can obtain a
    perfectly valid token for their *own* session still cannot use it."""

    _login(client, "dev-admin")
    attacker_token = _token(client)

    _login(client, "dev-operator")
    response = _upload(client, headers={CSRF_HEADER_NAME: attacker_token})

    assert response.status_code == 403


def test_cross_origin_referer_is_forbidden_when_no_origin_header_is_sent(
    client: TestClient,
) -> None:
    _login(client, "dev-operator")

    response = _upload(
        client,
        headers={CSRF_HEADER_NAME: _token(client), "Referer": f"{_ATTACKER_ORIGIN}/attack.html"},
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Read routes stay reachable
# ---------------------------------------------------------------------------


def test_read_routes_do_not_require_a_csrf_token(client: TestClient) -> None:
    _login(client, "dev-operator")

    assert client.get("/ingesta/jobs").status_code == 200
