"""Upload routes resolve the session before reading a single body byte.

``app.http_hardening.RequestBodyLimitMiddleware`` must refuse an upload
whose session cookie is missing, forged, expired or revoked *before* the
server receives the body -- a cookie that merely exists is not enough. These
tests use the real ``app.main`` stack and real ``platform.session`` rows,
with the upload body limits shrunk to 64 KiB so no test sends a large body.

Rejections are driven through raw ASGI calls, which count the bytes the
server read; TestClient buffers the whole request first and cannot show
that. The valid-session paths go through TestClient, as a browser would.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator, MutableMapping
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from app.access import Role
from app.access_repository import grant_product_role, resolve_or_create_app_user
from app.csrf import CSRF_HEADER_NAME
from app.deps import SESSION_COOKIE_NAME, get_object_store, has_active_session
from app.dev_auth import DEV_IDENTITY_KIND
from app.http_hardening import RequestBodyLimitMiddleware
from app.main import app
from app.object_store import LocalObjectStore
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

_platform_sessions = PlatformSessionStore()

_SAME_ORIGIN = "http://testserver"
SMALL_LIMIT = 64 * 1024

# Both upload boundaries: the generic intake and the Transelec wrapper.
UPLOAD_ROUTES = ("/ingesta/upload", "/transelec/uploads")

Message = MutableMapping[str, Any]


@pytest.fixture
def small_upload_limits() -> Generator[None, None, None]:
    """Rebuild app.main's middleware stack with 64 KiB upload limits."""

    limiter = next(m for m in app.user_middleware if m.cls is RequestBodyLimitMiddleware)
    original = limiter.kwargs
    assert original["session_validator"] is has_active_session
    limiter.kwargs = {
        **original,
        "path_limits": {path: SMALL_LIMIT for path in original["path_limits"]},
    }
    app.middleware_stack = None
    try:
        yield
    finally:
        limiter.kwargs = original
        app.middleware_stack = None


@pytest.fixture
def client(
    integration_engine: Engine, tmp_path: Path, small_upload_limits: None
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_object_store] = lambda: LocalObjectStore(tmp_path / "object-store")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.begin() as conn:
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


def _session(engine: Engine, role: Role = Role.OPERATOR, *, ttl: timedelta) -> str:
    """Mint a real platform session for a user granted ``role`` on Transelec."""

    with engine.begin() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind=DEV_IDENTITY_KIND,
            identity_key=f"upload-gate-{role}",
            display_name="Upload gate",
        )
        grant_product_role(connection, app_user_id=user.id, product_key="transelect", role=role)
        return _platform_sessions.create_session(connection, app_user_id=user.id, ttl=ttl)


def _revoked_session(engine: Engine) -> str:
    raw_secret = _session(engine, ttl=timedelta(hours=8))
    with engine.begin() as connection:
        _platform_sessions.clear_session(connection, raw_secret)
    return raw_secret


def _multipart(payload_size: int, *, product_key: bool) -> tuple[bytes, bytes]:
    boundary = b"gateboundary"
    body = b""
    if product_key:
        body += (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="product_key"\r\n\r\n'
            b"transelect\r\n"
        )
    body += (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="wb.xlsx"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + b"x" * payload_size
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )
    return body, b"multipart/form-data; boundary=" + boundary


def _post_raw(path: str, cookie: str | None) -> tuple[int, Any, int]:
    """POST a 32 KiB upload (under the limit) to app.main over raw ASGI.

    Returns (status, JSON body, bytes of the request body the server read).
    """

    body, content_type = _multipart(32 * 1024, product_key=path == "/ingesta/upload")
    chunks = [body[i : i + 4096] for i in range(0, len(body), 4096)]
    read = 0
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal read
        if not chunks:
            return {"type": "http.disconnect"}
        piece = chunks.pop(0)
        read += len(piece)
        return {"type": "http.request", "body": piece, "more_body": bool(chunks)}

    async def send(message: Message) -> None:
        sent.append(message)

    headers = [
        (b"content-type", content_type),
        (b"content-length", str(len(body)).encode()),
        (b"origin", _SAME_ORIGIN.encode()),
    ]
    if cookie is not None:
        headers.append((b"cookie", f"{SESSION_COOKIE_NAME}={cookie}".encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1, sent
    payload = json.loads(b"".join(m.get("body", b"") for m in sent[1:]))
    return int(starts[0]["status"]), payload, read


@pytest.mark.parametrize("path", UPLOAD_ROUTES)
@pytest.mark.parametrize("session_kind", ["missing", "forged", "expired", "revoked"])
def test_unauthenticated_upload_reads_zero_bytes(
    integration_engine: Engine, small_upload_limits: None, path: str, session_kind: str
) -> None:
    cookie = {
        "missing": lambda: None,
        "forged": lambda: "anything",
        "expired": lambda: _session(integration_engine, ttl=timedelta(seconds=-1)),
        "revoked": lambda: _revoked_session(integration_engine),
    }[session_kind]()

    status, payload, read = _post_raw(path, cookie)

    assert status == 401
    assert payload == {"detail": "Not authenticated."}
    assert read == 0


def _authenticate(client: TestClient, raw_secret: str) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)
    response = client.get("/auth/csrf")
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER_NAME] = response.json()["csrf_token"]
    client.headers["Origin"] = _SAME_ORIGIN


def _upload(client: TestClient, path: str, content: bytes) -> Any:
    data = {"product_key": "transelect"} if path == "/ingesta/upload" else None
    return client.post(
        path, data=data, files={"file": ("wb.xlsx", content, "application/octet-stream")}
    )


@pytest.mark.parametrize("path", UPLOAD_ROUTES)
def test_valid_session_still_uploads(
    client: TestClient, integration_engine: Engine, path: str
) -> None:
    _authenticate(client, _session(integration_engine, ttl=timedelta(hours=8)))

    response = _upload(client, path, b"not a real workbook")

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", UPLOAD_ROUTES)
def test_valid_session_is_still_bound_by_the_upload_limit(
    client: TestClient, integration_engine: Engine, path: str
) -> None:
    _authenticate(client, _session(integration_engine, ttl=timedelta(hours=8)))

    response = _upload(client, path, b"x" * (SMALL_LIMIT + 1))

    assert response.status_code == 413


@pytest.mark.parametrize("path", UPLOAD_ROUTES)
def test_valid_session_without_upload_permission_is_still_refused(
    client: TestClient, integration_engine: Engine, path: str
) -> None:
    # The middleware only decides whether the body is worth reading; the
    # route's own product permission check still runs.
    _authenticate(client, _session(integration_engine, Role.VIEWER, ttl=timedelta(hours=8)))

    response = _upload(client, path, b"not a real workbook")

    assert response.status_code == 403
