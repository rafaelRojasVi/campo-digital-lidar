"""Product-grant administration: onboarding a signed-in user onto a product.

Every route requires the caller to already hold Action.MANAGE_ACCESS
(Role.ADMIN only, per app.access._ALLOWED) on the target product — granting
access is itself a product-scoped, access-controlled action, not a
platform-wide superadmin capability. A grantee must already have an
app_user row: onboarding creates that (and records their email) at their own
first sign-in (see app.access_repository.resolve_or_create_app_user); this
router only grants a role to an identity that already exists.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection

from app.access import Action, Role
from app.access_repository import (
    AppUser,
    ProductGrantee,
    get_app_user_by_email,
    get_product_role,
    grant_product_role,
    list_grantees_for_product,
)
from app.audit import PRODUCT_GRANT_CHANGED_EVENT, record_audit_event
from app.csrf import require_csrf
from app.deps import ensure_can, get_current_app_user, get_db_connection

router = APIRouter(prefix="/auth/admin", tags=["auth-admin"])


class ProductGranteeView(BaseModel):
    app_user_id: int
    email: str | None
    display_name: str
    role: str


class GrantProductRoleRequest(BaseModel):
    email: str
    role: Role


def _view(grantee: ProductGrantee) -> ProductGranteeView:
    return ProductGranteeView(
        app_user_id=grantee.app_user_id,
        email=grantee.email,
        display_name=grantee.display_name,
        role=grantee.role.value,
    )


def require_manage_access(
    product_key: str,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> Role:
    """Require the caller to hold Action.MANAGE_ACCESS on ``product_key``.

    ``product_key`` is bound from the route's own path parameter of the
    same name — FastAPI resolves a dependency's parameters against the
    request the same way it resolves the endpoint function's.
    """

    return ensure_can(
        connection, app_user_id=user.id, product_key=product_key, action=Action.MANAGE_ACCESS
    )


@router.get("/product-grants/{product_key}", response_model=list[ProductGranteeView])
def list_product_grants(
    product_key: str,
    connection: Annotated[Connection, Depends(get_db_connection)],
    _: Annotated[Role, Depends(require_manage_access)],
) -> list[ProductGranteeView]:
    """List every user currently granted a role on ``product_key``."""

    return [
        _view(grantee) for grantee in list_grantees_for_product(connection, product_key=product_key)
    ]


@router.post(
    "/product-grants/{product_key}",
    response_model=ProductGranteeView,
    dependencies=[Depends(require_csrf)],
)
def grant_product_role_by_email(
    product_key: str,
    payload: GrantProductRoleRequest,
    caller: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    _: Annotated[Role, Depends(require_manage_access)],
) -> ProductGranteeView:
    """Grant ``payload.role`` on ``product_key`` to the user with ``payload.email``.

    Every call records a ``product_grant.changed`` audit event in the same
    transaction, naming who granted what to whom and the role it replaced,
    including a no-op re-grant of the role already held.
    """

    target = get_app_user_by_email(connection, email=payload.email)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail="No user has signed in with that email yet.",
        )

    previous_role = get_product_role(connection, app_user_id=target.id, product_key=product_key)
    grant_product_role(
        connection, app_user_id=target.id, product_key=product_key, role=payload.role
    )
    record_audit_event(
        connection,
        actor_app_user_id=caller.id,
        event_type=PRODUCT_GRANT_CHANGED_EVENT,
        product_key=product_key,
        subject_kind="app_user",
        subject_id=str(target.id),
        metadata={
            "previous_role": previous_role.value if previous_role else None,
            "role": payload.role.value,
            "via": "admin_api",
        },
    )

    return ProductGranteeView(
        app_user_id=target.id,
        email=target.email,
        display_name=target.display_name,
        role=payload.role.value,
    )
