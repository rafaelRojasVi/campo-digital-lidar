"""FastAPI composition root for Campo Digital platform services."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from app.config import get_settings
from app.dashboard_static import (
    DEFAULT_PORTAL_DIST,
    DEFAULT_TRANSELEC_DIST,
    PORTAL_DIST_ENV,
    TRANSELEC_DIST_ENV,
    PrefixedDashboard,
    dist_dir_from_environment,
    mount_dashboards,
)
from app.database import (
    DatabaseUnavailableError,
    check_database_connection,
    get_database_engine,
)
from app.deps import SESSION_COOKIE_NAME, get_object_store, has_active_session
from app.entra_auth import EntraNotConfiguredError
from app.execution import ExecutionBackend, InProcessStagingExecutionBackend
from app.google_auth import GoogleNotConfiguredError
from app.http_hardening import RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from app.identity_safety import require_production_identity_configuration
from app.object_store import LocalObjectStore, ObjectStoreError, ObjectStoreNotConfiguredError
from app.routers.access_admin import router as access_admin_router
from app.routers.csrf import router as csrf_router
from app.routers.entra_auth import router as entra_auth_router
from app.routers.google_auth import router as google_auth_router
from app.routers.ingestion import MAX_UPLOAD_BYTES as INGESTION_MAX_UPLOAD_BYTES
from app.routers.ingestion import router as ingestion_router
from app.routers.lidar import router as lidar_router
from app.routers.session import router as session_router
from app.routers.transelec import TRANSELEC_MAX_UPLOAD_BYTES
from app.routers.transelec import router as transelec_router

_execution_backend: ExecutionBackend | None = None

_SUPPORTED_APP_ENVS = ("development", "test", "staging", "production")


def _resolve_app_env() -> str:
    """Read and strictly validate APP_ENV from the raw process environment.

    Mirrors ``Settings.app_env``'s allowed values without requiring the full
    ``Settings`` model (and its database credentials) to resolve, so this
    module can decide dev-auth mounting and lifespan behavior at import time.
    Security-sensitive environment selection must fail closed: an unset or
    unrecognized value is rejected rather than silently defaulting to
    development, which would otherwise mount dev-only authentication.
    """

    value = os.environ.get("APP_ENV")
    if value not in _SUPPORTED_APP_ENVS:
        raise RuntimeError(
            f"APP_ENV must be explicitly set to one of {_SUPPORTED_APP_ENVS}; got {value!r}."
        )
    return value


APP_ENV = _resolve_app_env()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the staging-only in-process execution backend, if applicable."""

    # Gated on APP_ENV alone, not inside require_production_identity_configuration
    # itself: get_settings() needs full DB credentials to resolve at all, and
    # every other environment's lifespan must stay startable without them
    # (see app.main's router-mounting comment above, and
    # test_lidar_api.py's DB-free TestClient fixture, which this would
    # otherwise break for every APP_ENV, not just production).
    if APP_ENV == "production":
        require_production_identity_configuration(get_settings())

    global _execution_backend
    if APP_ENV == "staging":
        _execution_backend = InProcessStagingExecutionBackend(
            get_database_engine(), get_object_store(), get_settings()
        )
        await _execution_backend.start()

    try:
        yield
    finally:
        if _execution_backend is not None:
            await _execution_backend.stop()


# Swagger UI, ReDoc and the OpenAPI schema describe every route to anonymous
# callers; production users only need the dashboard, so it serves none of them.
_SERVE_API_DOCS = APP_ENV != "production"

app = FastAPI(
    title="Campo Digital LiDAR API",
    version="0.2.0",
    lifespan=_lifespan,
    docs_url="/docs" if _SERVE_API_DOCS else None,
    redoc_url="/redoc" if _SERVE_API_DOCS else None,
    openapi_url="/openapi.json" if _SERVE_API_DOCS else None,
)

# Multipart framing (boundaries, part headers, the product_key field) on top
# of the file itself.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
UPLOAD_BODY_LIMITS: dict[str, int] = {
    "/transelec/uploads": TRANSELEC_MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/api/transelec/uploads": TRANSELEC_MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES,
    "/ingesta/upload": INGESTION_MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES,
}
# Every other route takes, at most, a small JSON body.
DEFAULT_MAX_BODY_BYTES = 1024 * 1024

# Added before SecurityHeadersMiddleware so it sits inside it: the 401/413
# answers it produces carry the security headers too.
app.add_middleware(
    RequestBodyLimitMiddleware,
    default_limit=DEFAULT_MAX_BODY_BYTES,
    path_limits=UPLOAD_BODY_LIMITS,
    session_cookie_name=SESSION_COOKIE_NAME,
    session_validator=has_active_session,
    session_required=UPLOAD_BODY_LIMITS.keys(),
)
app.add_middleware(SecurityHeadersMiddleware, app_env=APP_ENV)


@app.exception_handler(EntraNotConfiguredError)
async def _entra_not_configured(request: object, exc: EntraNotConfiguredError) -> JSONResponse:
    """An unconfigured Entra sign-in is an intentionally unavailable state
    (missing ENTRA_CLIENT_ID/SECRET), not a server error."""

    del request, exc
    return JSONResponse(status_code=503, content={"detail": "Entra sign-in is not configured."})


@app.exception_handler(GoogleNotConfiguredError)
async def _google_not_configured(request: object, exc: GoogleNotConfiguredError) -> JSONResponse:
    """An unconfigured Google sign-in is an intentionally unavailable state
    (missing GOOGLE_CLIENT_ID/SECRET), not a server error."""

    del request, exc
    return JSONResponse(status_code=503, content={"detail": "Google sign-in is not configured."})


@app.exception_handler(ObjectStoreNotConfiguredError)
async def _object_store_not_configured(
    request: object, exc: ObjectStoreNotConfiguredError
) -> JSONResponse:
    """Production without a persistent object-store root refuses uploads
    rather than writing them into a container layer the next deploy erases."""

    del request, exc
    return JSONResponse(status_code=503, content={"detail": "File storage is not configured."})


@app.get("/health")
def health() -> dict[str, str]:
    """Process liveness probe with no external dependencies."""

    return {"status": "ok"}


@app.get("/ready")
def readiness(
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> JSONResponse:
    """Dependency readiness probe for the platform database and file storage."""

    try:
        check_database_connection(engine)
        _check_object_store_writable()
    except (DatabaseUnavailableError, ObjectStoreError, OSError):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ready"},
    )


def _check_object_store_writable() -> None:
    store = get_object_store()
    if isinstance(store, LocalObjectStore):
        store.check_writable()


app.include_router(lidar_router)
app.include_router(ingestion_router)
app.include_router(transelec_router)

# Always mounted, in every APP_ENV: any environment that can authenticate a
# session must also be able to obtain the CSRF token app.csrf.require_csrf
# demands on every mutation route.
app.include_router(csrf_router)

# Always mounted, in every APP_ENV: onboarding a signed-in user onto a
# product is itself access-controlled per route (Action.MANAGE_ACCESS), the
# same way every other product router is — not conditioned on dev-auth.
app.include_router(access_admin_router)

# Always mounted, in every APP_ENV: this is the real (non-dev-auth) identity
# provider and the only way to authenticate at all outside development (see
# ADR-006). Each route 503s (via the exception handler above) rather than
# 404ing or crashing when ENTRA_CLIENT_ID/SECRET are unset.
app.include_router(entra_auth_router)

# Always mounted, in every APP_ENV, for the same reasons as the Entra router
# above: this is the Transelec product's real identity provider (see
# ADR-010), and each route 503s rather than 404ing when GOOGLE_CLIENT_ID/
# SECRET are unset. Mounting both providers unconditionally is deliberate --
# a deployment chooses a provider by configuring it, not by being rebuilt.
app.include_router(google_auth_router)

# Always mounted, in every APP_ENV: inspecting (`/me`) or ending
# (`/logout`) a session applies uniformly regardless of which identity
# provider created it, and the frontend already calls both unconditionally
# — see app.routers.session for the gap this closes.
app.include_router(session_router)

# Router mounting must not require full DB configuration to resolve (unlike
# app.config.get_settings(), which requires POSTGRES_PASSWORD) — this decision
# is made from APP_ENV alone, straight from the process environment, so that
# importing this module never depends on unrelated database credentials being
# configured. app.dev_auth.assert_dev_auth_allowed still runs per-request
# inside the /auth/dev-login handler as defense in depth.
if APP_ENV == "development":
    from app.routers.dev_auth import router as dev_auth_router

    app.include_router(dev_auth_router)
    app.include_router(dev_auth_router, prefix="/api")

# The forestry read API has no authentication or product grant yet, and this
# app is the one deployed to staging and production; until it gets both, it
# exists only where nothing is deployed (local development and CI's "test").
if APP_ENV in ("development", "test"):
    from app.routers.forestry import router as forestry_router

    app.include_router(forestry_router)

# Second mount under /api for the routers a browser bundle actually calls at
# that prefix (see products/transelect/dashboard/src/api.ts). Every frontend
# on this platform is built once against a same-origin `/api/*` convention
# and reaches this API through an external rewrite that strips that prefix —
# the Vite dev proxy locally, Render's static-site rewrite in staging (see
# render.yaml). A container that serves the dashboard from this same process
# (see mount_dashboard below) has no such external layer in front of it, so
# it must provide that `/api/*` alias itself. This duplicates ROUTING only:
# same router objects, same dependencies, same RBAC — no new endpoint, no
# new behavior, and no Transelec-specific exception to any of that.
app.include_router(csrf_router, prefix="/api")
app.include_router(access_admin_router, prefix="/api")
app.include_router(entra_auth_router, prefix="/api")
app.include_router(google_auth_router, prefix="/api")
app.include_router(session_router, prefix="/api")
app.include_router(transelec_router, prefix="/api")

# Serves the built frontends from this same process when production builds
# are present (see app.dashboard_static): the Campo Digital front door at "/"
# and Transelec under "/transelec/". A no-op in local dev and in every
# test/CI environment, where no dist directories exist. Must stay last: it
# registers a catch-all route that would otherwise shadow the routers above.
TRANSELEC_SPA_PAGE_PATHS = frozenset(
    {
        "transelec",
        "transelec/explorador",
        "transelec/pendientes",
        # Not "transelec/aef": that is the read API's own path.
        "transelec/seguimiento-aef",
        "transelec/calidad",
        "transelec/datos",
        "transelec/importar",
        "transelec/versiones",
        "transelec/accesos",
    }
)

_transelec_dist = dist_dir_from_environment(TRANSELEC_DIST_ENV, DEFAULT_TRANSELEC_DIST)

mount_dashboards(
    app,
    root_dist=dist_dir_from_environment(PORTAL_DIST_ENV, DEFAULT_PORTAL_DIST),
    # TRANSELEC_SPA_PAGE_PATHS must match ROUTES in
    # products/transelect/dashboard/src/router.tsx (enforced by
    # test_dashboard_static.py): the frontend's own page paths, which share
    # the "transelec" first segment with the real API prefix.
    prefixed=(
        [PrefixedDashboard("transelec", _transelec_dist, TRANSELEC_SPA_PAGE_PATHS)]
        if _transelec_dist is not None
        else []
    ),
    reserved_root_segments=frozenset(
        {
            "health",
            "ready",
            "runs",
            "ingesta",
            "auth",
            "transelec",
            "api",
            # Reserved even where unmounted (production), so they 404
            # instead of falling through to the portal.
            "docs",
            "redoc",
            "openapi.json",
        }
    ),
)
