"""Shared FastAPI dependencies for platform access and object storage.

Kept separate from ``app.main`` so routers can depend on these without a
circular import, and so tests can override them cleanly via
``app.dependency_overrides``.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import Connection, Engine, text

from app.access import Action, Role, can
from app.access_repository import AppUser, get_product_role, resolve_or_create_app_user
from app.config import Settings, get_settings
from app.database import get_database_engine
from app.dev_auth import (
    DEV_IDENTITY_KIND,
    SEEDED_DEV_IDENTITIES,
    DevAuthDisabledInProductionError,
    DevSessionStore,
    assert_dev_auth_allowed,
)
from app.entra_auth import EntraOidcClient, MsalEntraOidcClient
from app.google_auth import GoogleOidcClient, GoogleOidcSignInClient
from app.object_store import LocalObjectStore, ObjectStore, open_configured_object_store
from app.session_store import PlatformSessionStore

SESSION_COOKIE_NAME = "campo_session"

_session_store = DevSessionStore()
_platform_session_store = PlatformSessionStore()
_object_store: LocalObjectStore | None = None
_entra_oidc_client: EntraOidcClient | None = None
_google_oidc_client: GoogleOidcClient | None = None


def get_session_store() -> DevSessionStore:
    """Return the process-level dev session store."""

    return _session_store


def get_platform_session_store() -> PlatformSessionStore:
    """Return the process-level Postgres-backed session store."""

    return _platform_session_store


def get_object_store() -> ObjectStore:
    """Return the process-level local object store.

    Raises ``app.object_store.ObjectStoreNotConfiguredError`` (mapped to 503
    by ``app.main``) in production without an absolute
    ``CAMPO_OBJECT_STORE_ROOT`` on a mounted volume, and stays uncached in
    that case so a later request succeeds once the configuration arrives.
    """

    global _object_store
    if _object_store is None:
        _object_store = open_configured_object_store(
            os.environ.get("APP_ENV"), os.environ.get("CAMPO_OBJECT_STORE_ROOT")
        )
    return _object_store


def get_entra_oidc_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EntraOidcClient:
    """Return the process-level Entra OIDC client.

    Raises ``app.entra_auth.EntraNotConfiguredError`` (mapped to 503 by
    ``app.main``) if ``ENTRA_CLIENT_ID``/``ENTRA_CLIENT_SECRET`` are unset —
    left uncached in that case, so a later request retries construction
    rather than staying permanently broken from one early failed attempt.
    """

    global _entra_oidc_client
    if _entra_oidc_client is None:
        _entra_oidc_client = MsalEntraOidcClient(settings)
    return _entra_oidc_client


def get_google_oidc_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GoogleOidcClient:
    """Return the process-level Google OIDC client.

    Raises ``app.google_auth.GoogleNotConfiguredError`` (mapped to 503 by
    ``app.main``) if ``GOOGLE_CLIENT_ID``/``GOOGLE_CLIENT_SECRET`` are unset,
    and stays uncached in that case for the same reason
    ``get_entra_oidc_client`` does: one early failed attempt must not leave
    sign-in permanently broken once the configuration arrives.
    """

    global _google_oidc_client
    if _google_oidc_client is None:
        _google_oidc_client = GoogleOidcSignInClient(settings)
    return _google_oidc_client


def get_db_connection(
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> Generator[Connection, None, None]:
    """Yield a request-scoped connection, committing on success."""

    with engine.connect() as connection:
        yield connection
        connection.commit()


def get_current_app_user(
    settings: Annotated[Settings, Depends(get_settings)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    platform_sessions: Annotated[PlatformSessionStore, Depends(get_platform_session_store)],
    dev_sessions: Annotated[DevSessionStore, Depends(get_session_store)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AppUser:
    """Resolve the caller's app_user row: real session first, dev-auth fallback."""

    if session_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    app_user_id = platform_sessions.resolve_session(connection, session_token)
    if app_user_id is not None:
        return _load_app_user(connection, app_user_id)

    try:
        assert_dev_auth_allowed(settings)
    except DevAuthDisabledInProductionError as exc:
        raise HTTPException(status_code=401, detail="Not authenticated.") from exc

    identity_key = dev_sessions.resolve_session(session_token)
    if identity_key is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    display_name = next(
        (i.display_name for i in SEEDED_DEV_IDENTITIES if i.identity_key == identity_key),
        identity_key,
    )
    return resolve_or_create_app_user(
        connection,
        identity_kind=DEV_IDENTITY_KIND,
        identity_key=identity_key,
        display_name=display_name,
    )


def has_active_session(session_token: str) -> bool:
    """Whether ``session_token`` would authenticate in ``get_current_app_user``.

    Used by ``app.http_hardening.RequestBodyLimitMiddleware`` to refuse an
    upload before reading its body, where FastAPI dependencies have not run
    yet -- hence the process-level engine, settings and stores rather than
    ``Depends``. Mirrors ``get_current_app_user``'s resolution order: a live
    platform session, then (development only) a dev-auth token. It creates
    no app_user row; the route still resolves the user itself.
    """

    with get_database_engine().connect() as connection:
        app_user_id = _platform_session_store.resolve_session(connection, session_token)
        connection.commit()
    if app_user_id is not None:
        return True

    try:
        assert_dev_auth_allowed(get_settings())
    except DevAuthDisabledInProductionError:
        return False
    return _session_store.resolve_session(session_token) is not None


def _load_app_user(connection: Connection, app_user_id: int) -> AppUser:
    row = connection.execute(
        text(
            "SELECT id, identity_kind, identity_key, display_name, email "
            "FROM platform.app_user WHERE id = :id"
        ),
        {"id": app_user_id},
    ).one()
    return AppUser(
        id=row.id,
        identity_kind=row.identity_kind,
        identity_key=row.identity_key,
        display_name=row.display_name,
        email=row.email,
    )


def get_current_identity_key(
    user: Annotated[AppUser, Depends(get_current_app_user)],
) -> str:
    """Resolve the caller's identity key via the same session resolution as
    `get_current_app_user`, so dev-auth's `/auth/logout` can authenticate the
    call without duplicating session-lookup logic in a second place."""

    return user.identity_key


def ensure_can(
    connection: Connection, *, app_user_id: int, product_key: str, action: Action
) -> Role:
    """Raise 403 unless the caller's grant for ``product_key`` permits ``action``."""

    role = get_product_role(connection, app_user_id=app_user_id, product_key=product_key)
    if not can(role, action):
        raise HTTPException(status_code=403, detail="Not permitted for this product.")
    assert role is not None  # can() returning True implies a grant exists
    return role
