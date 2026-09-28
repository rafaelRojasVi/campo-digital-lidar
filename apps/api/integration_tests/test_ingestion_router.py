"""Ingestion router: upload, RBAC, product isolation, IDOR-safe retry, audit gating."""

from __future__ import annotations

import zipfile
from collections.abc import Generator
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pytest
from app.access import Role
from app.access_repository import (
    grant_product_role,
    list_grants_for_user,
    resolve_or_create_app_user,
)
from app.audit import record_audit_event
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
    app.dependency_overrides[get_object_store] = lambda: LocalObjectStore(tmp_path / "object-store")

    with TestClient(app) as test_client:
        # _login mints real sessions against the test DB and needs a live
        # engine — app.routers.dev_auth's /auth/dev-login is only mounted
        # under APP_ENV=development (see app.main), and this suite runs
        # under APP_ENV=test so app.db_safety.require_test_database can
        # prove the DB is disposable, so the HTTP dev-login endpoint is
        # unreachable here. See test_dev_auth_router.py's module docstring.
        test_client.engine = integration_engine
        yield test_client

    app.dependency_overrides.clear()


def _login(client: TestClient, identity_key: str) -> None:
    """Authenticate `client` as a seeded dev identity via a real
    PlatformSessionStore session, mirroring exactly what
    routers/dev_auth.py's dev_login handler does server-side (resolve/create
    the app_user, seed DEFAULT_SEED_GRANTS on first login) — the only
    difference is the minted session is a PlatformSessionStore session
    rather than a DevSessionStore token, because DevSessionStore's fallback
    path in app.deps.get_current_app_user is itself gated to
    APP_ENV=development and this suite runs under APP_ENV=test."""

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
    _refresh_csrf_token(client)


def _refresh_csrf_token(client: TestClient) -> None:
    """Fetch a session-bound CSRF token, exactly as a real client does.

    Every mutation route is CSRF-protected by app.csrf, so an authenticated
    client that never fetches a token is answered 403 — see
    test_csrf_router.py for that fail-closed behavior specifically.
    """

    response = client.get("/auth/csrf")
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER_NAME] = response.json()["csrf_token"]


def _forestry_zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("predio.shp", b"x")
        archive.writestr("predio.shx", b"y")
        archive.writestr("predio.dbf", b"z")
        archive.writestr("predio.prj", b"w")
    return buffer.getvalue()


def _cleanup_all_test_data(engine: Engine) -> None:
    """Wipe everything this test file's requests may have created."""

    with engine.connect() as conn:
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


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    _cleanup_all_test_data(integration_engine)


def test_upload_requires_session(client: TestClient) -> None:
    response = client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
    )
    assert response.status_code == 401


def test_upload_rejects_unknown_product_key(client: TestClient) -> None:
    _login(client, "dev-operator")
    response = client.post(
        "/ingesta/upload",
        data={"product_key": "not_a_real_product"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
    )
    assert response.status_code == 422


def test_viewer_cannot_upload(client: TestClient) -> None:
    _login(client, "dev-viewer")  # default grant: transelect VIEWER only
    response = client.post(
        "/ingesta/upload",
        data={"product_key": "transelect"},
        files={"file": ("wb.xlsx", b"not a real workbook", "application/octet-stream")},
    )
    assert response.status_code == 403


def test_operator_upload_happy_path_forestry(client: TestClient) -> None:
    _login(client, "dev-operator")  # default grant: forestry OPERATOR only
    response = client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] is not None
    assert len(body["sha256"]) == 64
    assert body["validation_evidence"]["has_shp"] is True


def test_forestry_zip_slip_is_rejected_and_not_persisted(client: TestClient) -> None:
    _login(client, "dev-operator")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo("../../etc/passwd"), b"pwned")

    response = client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("evil.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 422

    jobs_response = client.get("/ingesta/jobs")
    assert jobs_response.json() == []


def test_jobs_list_is_scoped_to_granted_products(client: TestClient) -> None:
    _login(client, "dev-operator")  # forestry only
    client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
    )
    jobs = client.get("/ingesta/jobs").json()
    assert all(job["product_key"] == "forestry" for job in jobs)
    assert len(jobs) == 1

    _login(client, "dev-viewer")  # transelect only — must not see the forestry job
    other_jobs = client.get("/ingesta/jobs").json()
    assert other_jobs == []


def test_retry_on_ungranted_product_returns_404_not_403(client: TestClient) -> None:
    _login(client, "dev-operator")  # forestry only
    upload_response = client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
    )
    job_id = upload_response.json()["job_id"]

    _login(client, "dev-viewer")  # transelect only — no grant on forestry at all
    retry_response = client.post(f"/ingesta/jobs/{job_id}/retry")
    assert retry_response.status_code == 404


def test_retry_requires_failed_status(client: TestClient) -> None:
    _login(client, "dev-operator")
    upload_response = client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
    )
    job_id = upload_response.json()["job_id"]  # freshly queued, not failed

    retry_response = client.post(f"/ingesta/jobs/{job_id}/retry")
    assert retry_response.status_code == 409


def test_audit_requires_admin_role(client: TestClient) -> None:
    _login(client, "dev-operator")  # OPERATOR, not ADMIN
    response = client.get("/ingesta/audit")
    assert response.status_code == 403


def test_audit_visible_to_admin(client: TestClient) -> None:
    _login(client, "dev-admin")
    client.post(
        "/ingesta/upload",
        data={"product_key": "forestry"},
        files={"file": ("predio.zip", _forestry_zip_bytes(), "application/zip")},
    )
    response = client.get("/ingesta/audit")
    assert response.status_code == 200
    event_types = {event["event_type"] for event in response.json()}
    assert "upload.completed" in event_types
    assert "processing.requested" in event_types


def test_audit_scoped_to_admin_own_product_excludes_other_products_and_platform_events(
    client: TestClient, integration_engine: Engine
) -> None:
    """A product-scoped admin (Forestry only) must never see LiDAR events,
    Transelec events, or platform-level (product_key IS NULL) events through
    the shared /ingesta/audit endpoint."""

    with integration_engine.connect() as connection:
        forestry_admin = resolve_or_create_app_user(
            connection,
            identity_kind=DEV_IDENTITY_KIND,
            identity_key="forestry-admin-only",
            display_name="Forestry Admin",
        )
        grant_product_role(
            connection,
            app_user_id=forestry_admin.id,
            product_key="forestry",
            role=Role.ADMIN,
        )

        # Platform-level event, e.g. what /auth/dev-login's session.created
        # records — no product_key at all.
        record_audit_event(
            connection,
            actor_app_user_id=forestry_admin.id,
            event_type="session.created",
        )
        # Other-product events the Forestry-only admin must never see.
        record_audit_event(
            connection,
            actor_app_user_id=None,
            event_type="upload.completed",
            product_key="lidar",
            subject_kind="source_snapshot",
            subject_id="1",
        )
        record_audit_event(
            connection,
            actor_app_user_id=None,
            event_type="upload.completed",
            product_key="transelect",
            subject_kind="source_snapshot",
            subject_id="2",
        )
        # In-scope event the admin should still see.
        record_audit_event(
            connection,
            actor_app_user_id=forestry_admin.id,
            event_type="upload.completed",
            product_key="forestry",
            subject_kind="source_snapshot",
            subject_id="3",
        )

        raw_secret = _platform_sessions.create_session(
            connection, app_user_id=forestry_admin.id, ttl=timedelta(hours=8)
        )
        connection.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)

    response = client.get("/ingesta/audit")
    assert response.status_code == 200

    product_keys = {event["product_key"] for event in response.json()}
    assert product_keys == {"forestry"}
