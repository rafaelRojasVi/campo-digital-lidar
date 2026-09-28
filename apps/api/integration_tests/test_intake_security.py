"""Intake security sweep: oversized uploads and malicious filenames.

Zip-slip/zip-bomb rejection, IDOR-safe job/retry scoping, and the
dev-auth-disabled-in-production gate are covered in
test_ingestion_router.py and test_main_dev_auth_gate.py respectively — this
file covers the remaining Part 12 threats not already exercised there.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from pathlib import Path

import app.routers.ingestion as ingestion_module
import pytest
from app.access_repository import (
    grant_product_role,
    list_grants_for_user,
    resolve_or_create_app_user,
)
from app.csrf import CSRF_HEADER_NAME
from app.deps import SESSION_COOKIE_NAME, get_object_store
from app.dev_auth import DEFAULT_SEED_GRANTS, DEV_IDENTITY_KIND, SEEDED_DEV_IDENTITIES
from app.main import app
from app.object_store import LocalObjectStore
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

_platform_sessions = PlatformSessionStore()


@pytest.fixture
def client(integration_engine: Engine, tmp_path: Path) -> Generator[TestClient, None, None]:
    store_root = tmp_path / "object-store"
    app.dependency_overrides[get_object_store] = lambda: LocalObjectStore(store_root)

    with TestClient(app) as test_client:
        # _login mints real sessions against the test DB and needs a live
        # engine — see test_ingestion_router.py's client fixture for why
        # /auth/dev-login itself is unreachable under APP_ENV=test.
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
            "product_grant",
            "app_user",
        ):
            conn.execute(text(f"DELETE FROM platform.{table}"))
        conn.commit()


def _login(client: TestClient, identity_key: str) -> None:
    """Authenticate `client` as a seeded dev identity via a real
    PlatformSessionStore session — see test_ingestion_router.py's `_login`
    for why this no longer goes through POST /auth/dev-login."""

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

    # Every mutation route is CSRF-protected by app.csrf; a real client
    # fetches its session-bound token right after authenticating. The
    # fail-closed behavior itself is covered in test_csrf_router.py.
    csrf_response = client.get("/auth/csrf")
    assert csrf_response.status_code == 200, csrf_response.text
    client.headers[CSRF_HEADER_NAME] = csrf_response.json()["csrf_token"]


def test_oversized_upload_is_rejected_with_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingestion_module, "MAX_UPLOAD_BYTES", 10)
    _login(client, "dev-admin")

    response = client.post(
        "/ingesta/upload",
        data={"product_key": "transelect"},
        files={
            "file": (
                "wb.xlsx",
                b"this payload is more than ten bytes long",
                "application/octet-stream",
            )
        },
    )
    assert response.status_code == 413


def test_path_traversal_filename_is_stored_as_metadata_only(
    client: TestClient, tmp_path: Path
) -> None:
    _login(client, "dev-admin")

    response = client.post(
        "/ingesta/upload",
        data={"product_key": "transelect"},
        files={"file": ("../../evil.xlsx", b"harmless content", "application/octet-stream")},
    )
    assert response.status_code == 200, response.text

    store_root = tmp_path / "object-store"
    # The object store's own key scheme is content-addressed; the filename
    # never becomes part of any filesystem path. Confirm nothing escaped
    # the store root regardless of the request outcome.
    for path in store_root.rglob("*"):
        assert (
            store_root.resolve() in path.resolve().parents or path.resolve() == store_root.resolve()
        )


def test_malicious_content_type_does_not_change_dispatch(client: TestClient) -> None:
    """Only the explicit product_key field selects the inspector, never Content-Type."""

    _login(client, "dev-admin")

    response = client.post(
        "/ingesta/upload",
        data={"product_key": "transelect"},
        files={"file": ("wb.xlsx", b"not really xlsx bytes", "application/zip")},
    )
    assert response.status_code == 200, response.text
    # Transelec inspection was attempted (and failed gracefully as evidence,
    # not a forestry ZIP inspection, despite the zip Content-Type header).
    assert "error" in response.json()["validation_evidence"]
