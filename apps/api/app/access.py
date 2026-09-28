"""Pure RBAC rules, kept strictly separate from authentication.

Authentication answers "who are you?" (see ``app.dev_auth`` for the local
dev-only adapter). This module only answers "what is this role allowed to
do?" for one product grant at a time. A caller with no grant for a product
must always be denied, never fall through to a default allow.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Platform roles, scoped per product grant."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Action(StrEnum):
    """Actions gated by a product grant's role."""

    VIEW = "view"
    UPLOAD = "upload"
    PROCESS = "process"
    RETRY = "retry"
    # Making an already-validated, immutable version the one a product
    # serves — and reverting to a previous one. Distinct from PROCESS
    # (running work on an upload) because publishing changes what every
    # viewer sees, which is an operational decision, not a pipeline step.
    PUBLISH = "publish"
    MANAGE_ACCESS = "manage_access"


_ALLOWED: frozenset[tuple[Role, Action]] = frozenset(
    {
        (Role.ADMIN, Action.VIEW),
        (Role.ADMIN, Action.UPLOAD),
        (Role.ADMIN, Action.PROCESS),
        (Role.ADMIN, Action.RETRY),
        (Role.ADMIN, Action.PUBLISH),
        (Role.ADMIN, Action.MANAGE_ACCESS),
        (Role.OPERATOR, Action.VIEW),
        (Role.OPERATOR, Action.UPLOAD),
        (Role.OPERATOR, Action.PROCESS),
        (Role.OPERATOR, Action.RETRY),
        (Role.OPERATOR, Action.PUBLISH),
        (Role.VIEWER, Action.VIEW),
    }
)


def can(role: Role | None, action: Action) -> bool:
    """Return whether ``role`` may perform ``action``. ``None`` always denies."""

    if role is None:
        return False
    return (role, action) in _ALLOWED
