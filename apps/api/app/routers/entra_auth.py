"""Microsoft Entra ID sign-in: the real (non-dev-auth) identity provider.

``GET /auth/entra/login`` redirects the browser to Microsoft; Microsoft
posts back to ``POST /auth/entra/callback`` (form_post response_mode, see
``app.entra_auth``), which completes the sign-in and mints a real
``platform.session`` row — the only way to authenticate outside development
(see ADR-006). Mounted unconditionally, like ``app.routers.csrf``: any
non-development environment has no other way to authenticate at all.

PKCE/state round-trips in a short-lived, encrypted, HttpOnly cookie rather
than server-side memory: ``DevSessionStore``'s in-process dict is explicitly
documented as unsuitable beyond a single local process, and a real
deployment may run more than one replica, where the login and callback
requests are not guaranteed to land on the same one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import Connection

from app.access_repository import maybe_grant_bootstrap_admin, resolve_or_create_app_user
from app.audit import record_audit_event
from app.config import Settings, get_settings
from app.deps import (
    SESSION_COOKIE_NAME,
    get_db_connection,
    get_entra_oidc_client,
    get_platform_session_store,
)
from app.entra_auth import EntraOidcClient, EntraSignInError
from app.graph_grant_repository import upsert_graph_grant
from app.session_store import PlatformSessionStore
from app.token_crypto import TokenDecryptionError, decrypt_token, encrypt_token

router = APIRouter(prefix="/auth/entra", tags=["auth"])

_FLOW_COOKIE_NAME = "entra_login_flow"
# Enough for one interactive sign-in round trip; this cookie carries no
# identity, only PKCE/state, so a short TTL bounds a stolen/replayed flow
# cookie's usefulness without needing revocation.
_FLOW_COOKIE_MAX_AGE_SECONDS = 600
_SESSION_TTL = timedelta(hours=8)
_POST_LOGIN_REDIRECT_PATH = "/"


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.entra_redirect_base_url}/auth/entra/callback"


def _require_encryption_key(settings: Settings) -> str:
    if settings.platform_token_encryption_key is None:
        raise HTTPException(status_code=503, detail="Entra sign-in is not fully configured.")
    return settings.platform_token_encryption_key.get_secret_value()


def _cookie_is_secure(settings: Settings) -> bool:
    # Every non-development environment is HTTPS-only; development runs
    # plain HTTP on localhost, where a Secure cookie would never be sent.
    return settings.app_env != "development"


@router.get("/login")
def entra_login(
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[EntraOidcClient, Depends(get_entra_oidc_client)],
) -> RedirectResponse:
    """Redirect the browser to Microsoft's sign-in page."""

    encryption_key = _require_encryption_key(settings)
    authorization_request = client.initiate(_redirect_uri(settings))

    response = RedirectResponse(authorization_request.auth_uri, status_code=302)
    response.set_cookie(
        _FLOW_COOKIE_NAME,
        encrypt_token(authorization_request.flow_state, key=encryption_key).decode("utf-8"),
        httponly=True,
        samesite="lax",
        secure=_cookie_is_secure(settings),
        max_age=_FLOW_COOKIE_MAX_AGE_SECONDS,
    )
    return response


@router.post("/callback")
async def entra_callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[EntraOidcClient, Depends(get_entra_oidc_client)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    platform_sessions: Annotated[PlatformSessionStore, Depends(get_platform_session_store)],
    flow_cookie: Annotated[str | None, Cookie(alias=_FLOW_COOKIE_NAME)] = None,
) -> RedirectResponse:
    """Complete the sign-in Microsoft posted back, and start a real session."""

    encryption_key = _require_encryption_key(settings)
    if flow_cookie is None:
        raise HTTPException(status_code=400, detail="Missing or expired sign-in state.")

    try:
        flow_state = decrypt_token(flow_cookie.encode("utf-8"), key=encryption_key)
    except TokenDecryptionError as exc:
        raise HTTPException(status_code=400, detail="Sign-in state could not be verified.") from exc

    form = await request.form()
    callback_params = {key: str(value) for key, value in form.items()}

    try:
        sign_in = client.complete(flow_state, callback_params, _redirect_uri(settings))
    except EntraSignInError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = resolve_or_create_app_user(
        connection,
        identity_kind="entra",
        identity_key=f"{sign_in.tenant_id}:{sign_in.object_id}",
        display_name=sign_in.display_name,
        email=sign_in.email,
    )
    maybe_grant_bootstrap_admin(
        connection,
        settings=settings,
        tenant_id=sign_in.tenant_id,
        object_id=sign_in.object_id,
        app_user_id=user.id,
    )

    if sign_in.access_token and sign_in.refresh_token and sign_in.expires_in is not None:
        upsert_graph_grant(
            connection,
            app_user_id=user.id,
            access_token_encrypted=encrypt_token(sign_in.access_token, key=encryption_key),
            refresh_token_encrypted=encrypt_token(sign_in.refresh_token, key=encryption_key),
            scope=sign_in.scope or "",
            expires_at=datetime.now(UTC) + timedelta(seconds=sign_in.expires_in),
        )

    raw_secret = platform_sessions.create_session(connection, app_user_id=user.id, ttl=_SESSION_TTL)
    record_audit_event(connection, actor_app_user_id=user.id, event_type="session.created")

    response = RedirectResponse(_POST_LOGIN_REDIRECT_PATH, status_code=302)
    response.delete_cookie(_FLOW_COOKIE_NAME)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_secret,
        httponly=True,
        samesite="lax",
        secure=_cookie_is_secure(settings),
    )
    return response
