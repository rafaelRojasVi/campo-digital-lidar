"""Persistence adapter for platform access (users and product grants)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, text

from app.access import Role
from app.audit import PRODUCT_GRANT_CHANGED_EVENT, record_audit_event
from app.config import Settings


@dataclass(frozen=True, slots=True)
class AppUser:
    """Identity-mapped platform user."""

    id: int
    identity_kind: str
    identity_key: str
    display_name: str
    email: str | None


@dataclass(frozen=True, slots=True)
class ProductGrant:
    """One user's role for one product."""

    product_key: str
    role: Role


@dataclass(frozen=True, slots=True)
class ProductGrantee:
    """One user holding a grant for one product, as seen from that product's side."""

    app_user_id: int
    email: str | None
    display_name: str
    role: Role


def resolve_or_create_app_user(
    connection: Connection,
    *,
    identity_kind: str,
    identity_key: str,
    display_name: str,
    email: str | None = None,
) -> AppUser:
    """Resolve an existing user by identity, or create one idempotently.

    ``email`` is only recorded on creation (real, non-dev identities have
    one; dev-auth's seeded identities never pass it). It is not updated on
    an existing row: an operator granting access looks a user up by the
    email captured at their first sign-in, so silently changing it on a
    later sign-in would break that lookup.
    """

    parameters = {
        "identity_kind": identity_kind,
        "identity_key": identity_key,
        "display_name": display_name,
        "email": email,
    }

    inserted = connection.execute(
        text(
            """
            INSERT INTO platform.app_user (identity_kind, identity_key, display_name, email)
            VALUES (:identity_kind, :identity_key, :display_name, :email)
            ON CONFLICT (identity_kind, identity_key) DO NOTHING
            RETURNING id, identity_kind, identity_key, display_name, email
            """
        ),
        parameters,
    ).one_or_none()

    row = (
        inserted
        or connection.execute(
            text(
                """
            SELECT id, identity_kind, identity_key, display_name, email
            FROM platform.app_user
            WHERE identity_kind = :identity_kind
              AND identity_key = :identity_key
            """
            ),
            parameters,
        ).one()
    )

    return AppUser(
        id=row.id,
        identity_kind=row.identity_kind,
        identity_key=row.identity_key,
        display_name=row.display_name,
        email=row.email,
    )


def get_app_user_by_email(connection: Connection, *, email: str) -> AppUser | None:
    """Look up a previously-signed-in user by email, or None if unknown.

    Used by product-grant onboarding (``app.routers.access_admin``): an
    operator grants a product role by email, which only resolves after the
    grantee has signed in at least once (their ``app_user`` row, and its
    email, only exist from that point on).
    """

    row = connection.execute(
        text(
            "SELECT id, identity_kind, identity_key, display_name, email "
            "FROM platform.app_user WHERE email = :email"
        ),
        {"email": email},
    ).one_or_none()

    if row is None:
        return None

    return AppUser(
        id=row.id,
        identity_kind=row.identity_kind,
        identity_key=row.identity_key,
        display_name=row.display_name,
        email=row.email,
    )


def grant_product_role(
    connection: Connection,
    *,
    app_user_id: int,
    product_key: str,
    role: Role,
) -> None:
    """Grant (or update) one user's role for one product."""

    connection.execute(
        text(
            """
            INSERT INTO platform.product_grant (app_user_id, product_key, role)
            VALUES (:app_user_id, :product_key, :role)
            ON CONFLICT (app_user_id, product_key)
            DO UPDATE SET role = EXCLUDED.role
            """
        ),
        {
            "app_user_id": app_user_id,
            "product_key": product_key,
            "role": role.value,
        },
    )


def get_product_role(
    connection: Connection,
    *,
    app_user_id: int,
    product_key: str,
) -> Role | None:
    """Return the caller's role for one product, or None if ungranted."""

    role_value = connection.execute(
        text(
            """
            SELECT role
            FROM platform.product_grant
            WHERE app_user_id = :app_user_id
              AND product_key = :product_key
            """
        ),
        {"app_user_id": app_user_id, "product_key": product_key},
    ).scalar_one_or_none()

    return Role(role_value) if role_value is not None else None


def list_grants_for_user(
    connection: Connection,
    *,
    app_user_id: int,
) -> tuple[ProductGrant, ...]:
    """Return every product grant held by a user."""

    rows = connection.execute(
        text(
            """
            SELECT product_key, role
            FROM platform.product_grant
            WHERE app_user_id = :app_user_id
            ORDER BY product_key
            """
        ),
        {"app_user_id": app_user_id},
    ).all()

    return tuple(ProductGrant(product_key=row.product_key, role=Role(row.role)) for row in rows)


def list_grantees_for_product(
    connection: Connection,
    *,
    product_key: str,
) -> tuple[ProductGrantee, ...]:
    """Return every user holding a grant for ``product_key``."""

    rows = connection.execute(
        text(
            """
            SELECT u.id AS app_user_id, u.email, u.display_name, g.role
            FROM platform.product_grant g
            JOIN platform.app_user u ON u.id = g.app_user_id
            WHERE g.product_key = :product_key
            ORDER BY u.display_name
            """
        ),
        {"product_key": product_key},
    ).all()

    return tuple(
        ProductGrantee(
            app_user_id=row.app_user_id,
            email=row.email,
            display_name=row.display_name,
            role=Role(row.role),
        )
        for row in rows
    )


_BOOTSTRAP_PRODUCT_KEYS = ("lidar", "forestry", "transelect")


def maybe_grant_bootstrap_admin(
    connection: Connection,
    *,
    settings: Settings,
    tenant_id: str,
    object_id: str,
    app_user_id: int,
) -> bool:
    """Grant one-time bootstrap ADMIN if this identity matches config and holds no grants."""

    configured_tenant = settings.platform_bootstrap_admin_tenant_id
    configured_object = settings.platform_bootstrap_admin_object_id
    if not configured_tenant or not configured_object:
        return False
    if configured_tenant != tenant_id or configured_object != object_id:
        return False
    if list_grants_for_user(connection, app_user_id=app_user_id):
        return False

    for product_key in _BOOTSTRAP_PRODUCT_KEYS:
        grant_product_role(
            connection, app_user_id=app_user_id, product_key=product_key, role=Role.ADMIN
        )
    return True


TRANSELEC_PRODUCT_KEY = "transelect"


def maybe_grant_transelec_bootstrap_admin(
    connection: Connection,
    *,
    settings: Settings,
    email: str,
    app_user_id: int,
) -> bool:
    """Grant one-time ADMIN on Transelec -- and only Transelec -- by email.

    The counterpart of ``maybe_grant_bootstrap_admin`` for Google Workspace
    sign-in, kept separate rather than parameterised because the difference
    is the point: that one opens all three products to a platform operator;
    this one can only ever open ``transelect``. The Transelec pilot is hosted
    for one client, and the account that first opens it must not thereby
    become an administrator of LiDAR or Forestal.

    It is one-time in the same sense as well: it fires only for a user who
    holds no product grant at all, so an operator who later demotes this
    account does not have that decision undone by the next sign-in.

    ``email`` is compared case-insensitively because mailbox domains are
    case-insensitive and Workspace addresses are routinely written either
    way; it is never compared by suffix. Membership of the Workspace is
    established upstream by the verified ``hd`` claim
    (``app.google_auth.verify_id_token``), not here.
    """

    configured = settings.transelec_bootstrap_admin_email
    if not configured:
        return False
    if configured.strip().casefold() != email.strip().casefold():
        return False
    if list_grants_for_user(connection, app_user_id=app_user_id):
        return False

    grant_product_role(
        connection,
        app_user_id=app_user_id,
        product_key=TRANSELEC_PRODUCT_KEY,
        role=Role.ADMIN,
    )
    # No actor: configuration granted this, not a signed-in administrator.
    record_audit_event(
        connection,
        actor_app_user_id=None,
        event_type=PRODUCT_GRANT_CHANGED_EVENT,
        product_key=TRANSELEC_PRODUCT_KEY,
        subject_kind="app_user",
        subject_id=str(app_user_id),
        metadata={"previous_role": None, "role": Role.ADMIN.value, "via": "bootstrap_email"},
    )
    return True
