"""app.http_hardening: request-body limits and response security headers.

The body-limit tests drive the middleware through raw ASGI calls rather
than TestClient, because what they must prove is how much of the body the
server *read*: TestClient buffers the whole request before the app runs, so
it cannot show that an oversized or anonymous upload was refused unread.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any

from app.deps import SESSION_COOKIE_NAME
from app.http_hardening import (
    DASHBOARD_CONTENT_SECURITY_POLICY,
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.main import DEFAULT_MAX_BODY_BYTES, UPLOAD_BODY_LIMITS
from app.main import app as main_app
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Scope

UPLOAD_PATH = "/upload"
LIMIT = 1000
VALID_SESSION = "valid-session-secret"

Message = MutableMapping[str, Any]


def _upload_app() -> FastAPI:
    app = FastAPI()

    @app.post(UPLOAD_PATH)
    async def upload(file: UploadFile = File()) -> dict[str, int]:  # noqa: B008
        return {"size": len(await file.read())}

    @app.post("/json")
    async def echo(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    return app


class _Sessions:
    """Stand-in for app.deps.has_active_session: only VALID_SESSION is live."""

    def __init__(self) -> None:
        self.checked: list[str] = []

    def __call__(self, token: str) -> bool:
        self.checked.append(token)
        return token == VALID_SESSION


def _limited(app: FastAPI, sessions: _Sessions | None = None) -> RequestBodyLimitMiddleware:
    return RequestBodyLimitMiddleware(
        app,
        default_limit=100,
        path_limits={UPLOAD_PATH: LIMIT},
        session_cookie_name=SESSION_COOKIE_NAME,
        session_validator=sessions or _Sessions(),
        session_required=(UPLOAD_PATH,),
    )


def _session_cookie(value: str = VALID_SESSION) -> tuple[bytes, bytes]:
    return (b"cookie", f"{SESSION_COOKIE_NAME}={value}".encode())


def _multipart(payload_size: int) -> tuple[bytes, bytes]:
    boundary = b"testboundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="w.xlsx"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + b"x" * payload_size
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )
    return body, b"multipart/form-data; boundary=" + boundary


class _Exchange:
    """One raw ASGI request, streamed in chunks, recording what was read."""

    def __init__(self, body: bytes, *, chunk: int = 64) -> None:
        self.chunks = [body[i : i + chunk] for i in range(0, len(body), chunk)] or [b""]
        self.chunks_read = 0
        self.bytes_read = 0
        self.sent: list[Message] = []

    async def receive(self) -> Message:
        index = self.chunks_read
        if index >= len(self.chunks):
            return {"type": "http.disconnect"}
        piece = self.chunks[index]
        self.chunks_read += 1
        self.bytes_read += len(piece)
        return {
            "type": "http.request",
            "body": piece,
            "more_body": index + 1 < len(self.chunks),
        }

    async def send(self, message: Message) -> None:
        self.sent.append(message)

    def run(self, app: ASGIApp, *, path: str, headers: list[tuple[bytes, bytes]]) -> None:
        scope: Scope = {
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

        async def exchange() -> None:
            await app(scope, self.receive, self.send)

        asyncio.run(exchange())

    @property
    def status(self) -> int:
        starts = [m for m in self.sent if m["type"] == "http.response.start"]
        assert len(starts) == 1, self.sent
        return int(starts[0]["status"])

    @property
    def json(self) -> Any:
        return json.loads(b"".join(m.get("body", b"") for m in self.sent[1:]))


def test_anonymous_upload_is_refused_before_any_body_is_read() -> None:
    body, content_type = _multipart(50_000)
    exchange = _Exchange(body)

    exchange.run(
        _limited(_upload_app()),
        path=UPLOAD_PATH,
        headers=[(b"content-type", content_type)],  # no Content-Length, no cookie
    )

    assert exchange.status == 401
    assert exchange.bytes_read == 0


def test_unresolvable_session_cookie_is_refused_before_any_body_is_read() -> None:
    body, content_type = _multipart(50_000)
    for value in ("anything", ""):
        sessions = _Sessions()
        exchange = _Exchange(body)

        exchange.run(
            _limited(_upload_app(), sessions),
            path=UPLOAD_PATH,
            headers=[(b"content-type", content_type), _session_cookie(value)],
        )

        assert exchange.status == 401, value
        assert exchange.json == {"detail": "Not authenticated."}
        assert exchange.bytes_read == 0, value


def test_session_check_sees_the_cookie_the_route_will_authenticate() -> None:
    # Starlette merges every Cookie header, later values winning; a valid
    # cookie followed by a forged one must be judged on the forged one.
    body, content_type = _multipart(500)
    sessions = _Sessions()
    exchange = _Exchange(body)

    exchange.run(
        _limited(_upload_app(), sessions),
        path=UPLOAD_PATH,
        headers=[
            (b"content-type", content_type),
            _session_cookie(),
            _session_cookie("forged"),
        ],
    )

    assert sessions.checked == ["forged"]
    assert exchange.status == 401
    assert exchange.bytes_read == 0


def test_session_is_only_checked_on_upload_paths() -> None:
    sessions = _Sessions()
    exchange = _Exchange(b"{}")

    exchange.run(
        _limited(_upload_app(), sessions),
        path="/json",
        headers=[(b"content-type", b"application/json"), _session_cookie("forged")],
    )

    assert exchange.status == 200
    assert sessions.checked == []


def test_declared_oversized_upload_is_refused_before_any_body_is_read() -> None:
    body, content_type = _multipart(50_000)
    exchange = _Exchange(body)

    exchange.run(
        _limited(_upload_app()),
        path=UPLOAD_PATH,
        headers=[
            (b"content-type", content_type),
            (b"content-length", str(len(body)).encode()),
            _session_cookie(),
        ],
    )

    assert exchange.status == 413
    assert exchange.bytes_read == 0


def test_undeclared_oversized_upload_is_cut_off_at_the_limit() -> None:
    body, content_type = _multipart(50_000)
    exchange = _Exchange(body, chunk=100)

    exchange.run(
        _limited(_upload_app()),
        path=UPLOAD_PATH,
        headers=[
            (b"content-type", content_type),
            _session_cookie(),
        ],
    )

    assert exchange.status == 413
    assert exchange.json == {"detail": "Request body exceeds the maximum allowed size."}
    # Stopped within one chunk of the limit, not after the whole 50 kB.
    assert exchange.bytes_read <= LIMIT + 100


def test_upload_within_the_limit_reaches_the_route() -> None:
    body, content_type = _multipart(500)
    exchange = _Exchange(body)

    exchange.run(
        _limited(_upload_app()),
        path=UPLOAD_PATH,
        headers=[
            (b"content-type", content_type),
            (b"content-length", str(len(body)).encode()),
            _session_cookie(),
        ],
    )

    assert exchange.status == 200
    assert exchange.json == {"size": 500}


def test_non_upload_routes_get_the_small_default_limit() -> None:
    exchange = _Exchange(b"{" + b" " * 500 + b"}")

    exchange.run(
        _limited(_upload_app()),
        path="/json",
        headers=[(b"content-type", b"application/json")],
    )

    assert exchange.status == 413
    assert exchange.bytes_read <= 100 + 64


def test_malformed_content_length_is_rejected() -> None:
    exchange = _Exchange(b"{}")

    exchange.run(
        _limited(_upload_app()),
        path="/json",
        headers=[(b"content-length", b"not-a-number")],
    )

    assert exchange.status == 400
    assert exchange.bytes_read == 0


def test_main_app_bounds_every_upload_route_and_defaults_small() -> None:
    assert DEFAULT_MAX_BODY_BYTES == 1024 * 1024
    assert set(UPLOAD_BODY_LIMITS) == {
        "/transelec/uploads",
        "/api/transelec/uploads",
        "/ingesta/upload",
    }
    # A Transelec workbook is bounded far below the LiDAR ingestion limit.
    assert UPLOAD_BODY_LIMITS["/api/transelec/uploads"] < 100 * 1024 * 1024


def test_main_app_refuses_anonymous_transelec_upload_without_reading_it() -> None:
    body, content_type = _multipart(50_000)
    for path in ("/api/transelec/uploads", "/transelec/uploads", "/ingesta/upload"):
        exchange = _Exchange(body)

        exchange.run(main_app, path=path, headers=[(b"content-type", content_type)])

        assert exchange.status == 401, path
        assert exchange.bytes_read == 0, path


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def _headers_app(app_env: str) -> TestClient:
    app = FastAPI()

    @app.get("/api/transelec/summary")
    def summary() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/assets/index-abc.js")
    def asset() -> PlainTextResponse:
        return PlainTextResponse("console.log(1)")

    @app.get("/explicit")
    def explicit() -> JSONResponse:
        return JSONResponse({}, headers={"Cache-Control": "max-age=60"})

    return TestClient(SecurityHeadersMiddleware(app, app_env=app_env))


def test_api_responses_are_not_stored_and_cannot_be_framed() -> None:
    response = _headers_app("production").get("/api/transelec/summary")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_dashboard_policy_allows_only_same_origin_resources() -> None:
    directives = dict(
        directive.split(" ", 1) for directive in DASHBOARD_CONTENT_SECURITY_POLICY.split("; ")
    )

    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["style-src"] == "'self'"
    assert directives["connect-src"] == "'self'"
    assert directives["object-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert "unsafe-inline" not in DASHBOARD_CONTENT_SECURITY_POLICY
    assert "unsafe-eval" not in DASHBOARD_CONTENT_SECURITY_POLICY


def test_hashed_static_assets_stay_cacheable() -> None:
    response = _headers_app("production").get("/assets/index-abc.js")

    assert "cache-control" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_route_set_header_is_not_overwritten() -> None:
    response = _headers_app("production").get("/explicit")

    assert response.headers["cache-control"] == "max-age=60"


def test_hsts_only_where_the_service_is_https_only() -> None:
    for app_env in ("staging", "production"):
        response = _headers_app(app_env).get("/api/transelec/summary")
        assert response.headers["strict-transport-security"].startswith("max-age=31536000")

    for app_env in ("development", "test"):
        response = _headers_app(app_env).get("/api/transelec/summary")
        assert "strict-transport-security" not in response.headers


def test_main_app_sends_security_headers_on_every_response() -> None:
    client = TestClient(main_app)

    for response in (
        client.get("/health"),
        client.get("/api/no-such-route"),  # an error answer
        client.post("/api/transelec/uploads"),  # refused by the body limiter
    ):
        assert response.headers["cache-control"] == "no-store", response.request.url
        assert response.headers["x-frame-options"] == "DENY", response.request.url
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_interactive_docs_keep_only_the_framing_restriction() -> None:
    response = TestClient(main_app).get("/docs")

    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
