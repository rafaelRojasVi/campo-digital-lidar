"""Dev-only authentication adapter.

This is explicitly NOT a production identity provider. It exists only to
prove the authorization layer (``app.access``) locally, by letting a
developer pick one seeded identity and receive a real session. It must only
run when ``APP_ENV == "development"`` — every entrypoint that constructs a
``DevSessionStore``-backed router must call ``assert_dev_auth_allowed`` first.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.access import Role
from app.config import Settings


class DevAuthDisabledInProductionError(RuntimeError):
    """Raised when dev authentication is constructed under APP_ENV=production."""


@dataclass(frozen=True, slots=True)
class DevIdentity:
    """One seeded local development identity."""

    identity_key: str
    display_name: str


SEEDED_DEV_IDENTITIES: tuple[DevIdentity, ...] = (
    DevIdentity(identity_key="dev-admin", display_name="Dev Admin"),
    DevIdentity(identity_key="dev-operator", display_name="Dev Operator"),
    DevIdentity(identity_key="dev-viewer", display_name="Dev Viewer"),
)

DEV_IDENTITY_KIND = "dev-local"

# First-login default grants for each seeded identity. dev-operator and
# dev-viewer are deliberately scoped to a single, DIFFERENT product each, so
# a fresh local checkout can immediately demonstrate product isolation
# without any manual grant-management step.
DEFAULT_SEED_GRANTS: dict[str, tuple[tuple[str, Role], ...]] = {
    "dev-admin": (
        ("lidar", Role.ADMIN),
        ("forestry", Role.ADMIN),
        ("transelect", Role.ADMIN),
    ),
    "dev-operator": (("forestry", Role.OPERATOR),),
    "dev-viewer": (("transelect", Role.VIEWER),),
}


def assert_dev_auth_allowed(settings: Settings) -> None:
    """Raise unless the configured environment permits dev-only auth."""

    if settings.app_env != "development":
        raise DevAuthDisabledInProductionError(
            "Dev-only authentication must never run outside APP_ENV=development."
        )


class DevSessionStore:
    """In-process opaque-token session store, for local dev only.

    Not durable across process restarts, and not shared across processes —
    acceptable for a single local API process proving authorization behavior.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def create_session(self, identity_key: str) -> str:
        """Issue a new unguessable session token for ``identity_key``."""

        token = secrets.token_urlsafe(32)
        self._sessions[token] = identity_key
        return token

    def resolve_session(self, token: str) -> str | None:
        """Return the identity key for ``token``, or None if unknown."""

        return self._sessions.get(token)

    def clear_session(self, token: str) -> None:
        """Invalidate a session token, if present."""

        self._sessions.pop(token, None)
