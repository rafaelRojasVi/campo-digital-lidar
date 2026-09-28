"""Platform-wide CSRF defense for cookie-authenticated, state-changing routes.

This is a shared, cross-product primitive: every product's mutation routes
consume this one mechanism, none gets its own. It is deliberately kept
separate from ``app.deps`` (which answers "who are you?") because CSRF
answers a different question: "did *this* browser context, rather than some
attacker page, deliberately initiate this request?"

Mechanism — a **session-bound, HMAC-signed synchronizer token**, not a plain
double-submit cookie:

- The token is ``<nonce>.<signature>`` where ``nonce`` is a fresh
  ``secrets.token_urlsafe(32)`` (the same generator ``PlatformSessionStore``
  uses for session secrets) and ``signature`` is
  ``HMAC-SHA256(key=SHA-256(session cookie secret), msg=<version>:<nonce>)``.
- The signing key is derived from the caller's own session cookie, which is
  ``HttpOnly`` and unguessable. Nothing new is stored: the server can
  re-derive and verify the signature from the request's own cookie, so this
  needs no table, no column, and no server-side secret in configuration.
- Because the key is the session, a token minted for one session never
  verifies for another. That is what makes this strictly stronger than a
  plain double-submit cookie, which an attacker who can set a cookie on a
  sibling subdomain can forge.
- The token is delivered by ``GET /auth/csrf`` as a normal JSON response
  body (see ``app.routers.csrf``) — never baked into a compiled frontend
  bundle, and never placed in a cookie, so a cross-origin page cannot read
  it (this API configures no CORS middleware, so browsers block the read)
  and cannot replay it from a cookie jar the browser would attach for it.
- Callers echo it back in the ``X-CSRF-Token`` request header. A cross-origin
  HTML form, image, or script tag cannot set a custom request header, so a
  classic CSRF submission never carries a valid one.

**Fail-closed**: ``require_csrf`` denies unless a syntactically valid,
correctly signed, session-bound token is present. There is no
pass-through path — not for a missing header, not for an unrecognized
request shape, not for a safe HTTP method (this dependency is attached
explicitly to mutation routes; attaching it to a read route denies that
read loudly rather than silently allowing a state-changing GET).

``Origin``/``Referer`` validation runs as an independent second layer:
a request that declares a *untrusted* origin is rejected even if its token
verifies. It is defense in depth, not a substitute — a request that declares
no origin at all (a non-browser client, which cannot be CSRF'd) is still
subject to the mandatory token check.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.deps import SESSION_COOKIE_NAME

CSRF_HEADER_NAME = "X-CSRF-Token"

# Bumping this invalidates every already-issued token without touching
# sessions, and keeps signatures from being reusable across a future change
# of token semantics.
_CSRF_TOKEN_VERSION = "campo-csrf-v1"

_TOKEN_SEPARATOR = "."
_NONCE_BYTES = 32

# One generic client-facing message for every rejection reason: an attacker
# probing the boundary learns nothing about *which* check failed.
_CSRF_REJECTED_DETAIL = "CSRF verification failed."

_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})

# Local development and the test suite reach the API through a dev proxy on
# a different loopback port (see apps/portal/vite.config.ts), so the browser
# Origin legitimately differs from the API's own Host there. This relaxation
# is confined to those environments, exactly like app.dev_auth's gate.
_LOOPBACK_TRUSTING_APP_ENVS = frozenset({"development", "test"})


def _signing_key(session_token: str) -> bytes:
    """Derive the HMAC key for a session without using the raw cookie directly."""

    return hashlib.sha256(session_token.encode("utf-8")).digest()


def _sign(nonce: str, session_token: str) -> str:
    digest = hmac.new(
        _signing_key(session_token),
        f"{_CSRF_TOKEN_VERSION}:{nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest


def mint_csrf_token(session_token: str) -> str:
    """Issue a fresh CSRF token bound to ``session_token``.

    Minting is per request: issuing a new token never invalidates one
    already held by another tab of the same session.
    """

    nonce = secrets.token_urlsafe(_NONCE_BYTES)
    return f"{nonce}{_TOKEN_SEPARATOR}{_sign(nonce, session_token)}"


def verify_csrf_token(candidate: str | None, *, session_token: str) -> bool:
    """Return whether ``candidate`` is a valid token for ``session_token``."""

    if not candidate:
        return False

    nonce, separator, signature = candidate.partition(_TOKEN_SEPARATOR)
    if not separator or not nonce or not signature:
        return False
    if _TOKEN_SEPARATOR in signature:
        return False

    return hmac.compare_digest(signature, _sign(nonce, session_token))


def parse_trusted_origins(raw: str | None) -> tuple[str, ...]:
    """Split a comma-separated ``CSRF_TRUSTED_ORIGINS`` value into origins."""

    if not raw:
        return ()
    return tuple(candidate.strip() for candidate in raw.split(",") if candidate.strip())


def _normalize_origin(value: str) -> str | None:
    """Reduce a URL to a comparable ``scheme://netloc``, or None if unusable."""

    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def is_trusted_origin(
    origin: str,
    *,
    request_host: str | None,
    app_env: str,
    trusted_origins: tuple[str, ...],
) -> bool:
    """Return whether a declared browser ``origin`` may drive this request.

    Trusted when the origin is explicitly configured, when it addresses the
    very host this request was sent to, or — outside staging/production only
    — when it is a loopback development origin.

    The self-host comparison deliberately compares host:port and not scheme:
    a TLS-terminating proxy hides the external scheme from this process, so
    requiring a scheme match there would reject every legitimate hosted
    request. Explicitly configured origins *are* compared including scheme.
    """

    normalized = _normalize_origin(origin)
    if normalized is None:
        return False

    normalized_trusted = {
        candidate
        for candidate in (_normalize_origin(entry) for entry in trusted_origins)
        if candidate is not None
    }
    if normalized in normalized_trusted:
        return True

    netloc = normalized.split("://", 1)[1]

    if request_host is not None and netloc == request_host.strip().lower():
        return True

    if app_env in _LOOPBACK_TRUSTING_APP_ENVS:
        hostname = urlsplit(normalized).hostname
        if hostname is not None and hostname.lower() in _LOOPBACK_HOSTNAMES:
            return True

    return False


def _declared_origin(request: Request) -> str | None:
    """Return the request's declared origin, from ``Origin`` or ``Referer``."""

    origin = request.headers.get("origin")
    if origin:
        return origin

    referer = request.headers.get("referer")
    if referer:
        return referer

    return None


def require_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    """Reject any state-changing request without a valid, session-bound token.

    Attach this to every cookie-authenticated mutation route, alongside the
    route's normal ``get_current_app_user`` authentication. It intentionally
    does not authenticate by itself: a request with no session cookie at all
    is answered ``401`` here, exactly as ``get_current_app_user`` would,
    because there is no cookie-authenticated action for an attacker to ride.
    """

    if session_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    declared_origin = _declared_origin(request)
    if declared_origin is not None and not is_trusted_origin(
        declared_origin,
        request_host=request.headers.get("host"),
        app_env=settings.app_env,
        trusted_origins=parse_trusted_origins(settings.csrf_trusted_origins),
    ):
        raise HTTPException(status_code=403, detail=_CSRF_REJECTED_DETAIL)

    if not verify_csrf_token(request.headers.get(CSRF_HEADER_NAME), session_token=session_token):
        raise HTTPException(status_code=403, detail=_CSRF_REJECTED_DETAIL)
