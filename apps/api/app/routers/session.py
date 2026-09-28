"""Session inspection and termination, mounted in every APP_ENV.

Login differs by identity provider (``app.routers.dev_auth`` in development
only, ``app.routers.entra_auth`` everywhere), but once a session exists,
inspecting or ending it does not depend on how it was created — both
``get_current_app_user`` and the two session stores already resolve either
kind uniformly. This is why ``/me`` and ``/logout`` live here rather than in
``app.routers.dev_auth``: mounting them only in development (as before)
left no way to inspect or end a real session anywhere else, even though the
frontend (``apps/portal/src/lib/platformApi.ts``,
``products/transelect/dashboard/src/api.ts``) already calls both paths
unconditionally.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel
from sqlalchemy import Connection

from app.access_repository import AppUser, list_grants_for_user
from app.csrf import require_csrf
from app.deps import (
    SESSION_COOKIE_NAME,
    get_current_app_user,
    get_current_identity_key,
    get_db_connection,
    get_platform_session_store,
    get_session_store,
)
from app.dev_auth import DevSessionStore
from app.session_store import PlatformSessionStore

router = APIRouter(prefix="/auth", tags=["auth"])


class ProductGrantView(BaseModel):
    product_key: str
    role: str


class MeResponse(BaseModel):
    identity_key: str
    display_name: str
    product_grants: list[ProductGrantView]


@router.get("/me", response_model=MeResponse)
def me(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> MeResponse:
    """Return the current session's identity and product grants."""

    grants = list_grants_for_user(connection, app_user_id=user.id)
    return MeResponse(
        identity_key=user.identity_key,
        display_name=user.display_name,
        product_grants=[
            ProductGrantView(product_key=grant.product_key, role=grant.role.value)
            for grant in grants
        ],
    )


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(
    response: Response,
    session_store: Annotated[DevSessionStore, Depends(get_session_store)],
    platform_sessions: Annotated[PlatformSessionStore, Depends(get_platform_session_store)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    identity_key: Annotated[str, Depends(get_current_identity_key)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    """Clear the current session, both server-side and via the cookie.

    ``get_current_identity_key`` (via ``get_current_app_user``) already
    proved a session resolved, from either ``PlatformSessionStore`` or
    ``DevSessionStore`` — but not which one. Clearing on both stores is
    safe: each ``clear_session`` call is a no-op delete against a hash/token
    that won't match rows it doesn't own.

    CSRF-protected like every other mutation: ending a session changes
    state, and another site must not be able to sign a user out. Both
    frontends already send the token on every non-GET request.
    """

    del identity_key  # authenticates the call; the token itself is read via the cookie
    if session_token is not None:
        platform_sessions.clear_session(connection, session_token)
        session_store.clear_session(session_token)
    response.delete_cookie(SESSION_COOKIE_NAME)
