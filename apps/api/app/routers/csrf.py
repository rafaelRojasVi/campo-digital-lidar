"""CSRF token issuance for cookie-authenticated frontends.

Mounted unconditionally (unlike ``app.routers.dev_auth``): every environment
that can authenticate a session must also be able to obtain the token that
``app.csrf.require_csrf`` demands on mutations.

The token is returned in a normal JSON body, never in a cookie and never
compiled into a frontend bundle. A cross-origin page cannot read this
response (this API configures no CORS middleware, so the browser blocks the
read), which is what keeps the token secret from an attacker's page.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends
from pydantic import BaseModel

from app.access_repository import AppUser
from app.csrf import CSRF_HEADER_NAME, mint_csrf_token
from app.deps import SESSION_COOKIE_NAME, get_current_app_user

router = APIRouter(prefix="/auth", tags=["auth"])


class CsrfTokenResponse(BaseModel):
    """A freshly minted CSRF token and the header it must be echoed in."""

    csrf_token: str
    header_name: str


@router.get("/csrf", response_model=CsrfTokenResponse)
def issue_csrf_token(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> CsrfTokenResponse:
    """Issue a CSRF token bound to the caller's current session.

    ``get_current_app_user`` runs first so an expired or unknown session
    never receives a token: it is answered ``401`` before minting. Its
    resolved user is not otherwise needed here — the token is keyed by the
    session secret itself, not by user identity, so that logging out and
    back in cannot reuse an old token.
    """

    del user  # authenticates the call; the token is keyed by the session secret
    assert session_token is not None  # get_current_app_user 401s when it is None

    return CsrfTokenResponse(
        csrf_token=mint_csrf_token(session_token),
        header_name=CSRF_HEADER_NAME,
    )
