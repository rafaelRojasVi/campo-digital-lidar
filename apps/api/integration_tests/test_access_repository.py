"""Integration tests for access repository persistence."""

from __future__ import annotations

from app.access import Role
from app.access_repository import (
    get_app_user_by_email,
    get_product_role,
    grant_product_role,
    list_grantees_for_product,
    list_grants_for_user,
    maybe_grant_bootstrap_admin,
    maybe_grant_transelec_bootstrap_admin,
    resolve_or_create_app_user,
)
from app.config import Settings
from sqlalchemy import Connection


def test_resolve_or_create_is_idempotent(integration_connection: Connection) -> None:
    first = resolve_or_create_app_user(
        integration_connection,
        identity_kind="dev-local",
        identity_key="alice",
        display_name="Alice",
    )
    second = resolve_or_create_app_user(
        integration_connection,
        identity_kind="dev-local",
        identity_key="alice",
        display_name="Alice",
    )
    assert first.id == second.id


def test_resolve_or_create_app_user_persists_email_on_creation(
    integration_connection: Connection,
) -> None:
    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-email",
        display_name="Javier",
        email="javier@example.com",
    )

    assert user.email == "javier@example.com"


def test_get_app_user_by_email_finds_a_signed_in_user(
    integration_connection: Connection,
) -> None:
    resolve_or_create_app_user(
        integration_connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-lookup",
        display_name="Javier",
        email="javier@example.com",
    )

    found = get_app_user_by_email(integration_connection, email="javier@example.com")

    assert found is not None
    assert found.email == "javier@example.com"


def test_get_app_user_by_email_returns_none_for_an_unknown_email(
    integration_connection: Connection,
) -> None:
    assert get_app_user_by_email(integration_connection, email="nobody@example.com") is None


def test_list_grantees_for_product_returns_only_that_products_grants(
    integration_connection: Connection,
) -> None:
    admin = resolve_or_create_app_user(
        integration_connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-admin",
        display_name="Rafael",
        email="rafael@example.com",
    )
    viewer = resolve_or_create_app_user(
        integration_connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-viewer",
        display_name="Javier",
        email="javier2@example.com",
    )
    grant_product_role(
        integration_connection, app_user_id=admin.id, product_key="transelect", role=Role.ADMIN
    )
    grant_product_role(
        integration_connection, app_user_id=viewer.id, product_key="transelect", role=Role.VIEWER
    )
    grant_product_role(
        integration_connection, app_user_id=admin.id, product_key="lidar", role=Role.ADMIN
    )

    grantees = list_grantees_for_product(integration_connection, product_key="transelect")

    assert {(g.app_user_id, g.role) for g in grantees} == {
        (admin.id, Role.ADMIN),
        (viewer.id, Role.VIEWER),
    }


def test_grant_and_get_product_role_round_trip(integration_connection: Connection) -> None:
    user = resolve_or_create_app_user(
        integration_connection, identity_kind="dev-local", identity_key="bob", display_name="Bob"
    )
    grant_product_role(
        integration_connection, app_user_id=user.id, product_key="forestry", role=Role.OPERATOR
    )

    assert (
        get_product_role(integration_connection, app_user_id=user.id, product_key="forestry")
        is Role.OPERATOR
    )
    assert (
        get_product_role(integration_connection, app_user_id=user.id, product_key="lidar") is None
    )


def test_grant_product_role_is_idempotent_and_updates_role(
    integration_connection: Connection,
) -> None:
    user = resolve_or_create_app_user(
        integration_connection, identity_kind="dev-local", identity_key="eve", display_name="Eve"
    )
    grant_product_role(
        integration_connection, app_user_id=user.id, product_key="lidar", role=Role.VIEWER
    )
    grant_product_role(
        integration_connection, app_user_id=user.id, product_key="lidar", role=Role.ADMIN
    )

    assert (
        get_product_role(integration_connection, app_user_id=user.id, product_key="lidar")
        is Role.ADMIN
    )


def test_product_isolation_grant_on_one_product_does_not_leak(
    integration_connection: Connection,
) -> None:
    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind="dev-local",
        identity_key="carol",
        display_name="Carol",
    )
    grant_product_role(
        integration_connection, app_user_id=user.id, product_key="lidar", role=Role.VIEWER
    )

    assert (
        get_product_role(integration_connection, app_user_id=user.id, product_key="transelect")
        is None
    )
    grants = list_grants_for_user(integration_connection, app_user_id=user.id)
    assert {g.product_key for g in grants} == {"lidar"}


def _bootstrap_settings() -> Settings:
    return Settings(
        postgres_password="x",
        platform_bootstrap_admin_tenant_id="tenant-x",
        platform_bootstrap_admin_object_id="oid-y",
    )


def test_bootstrap_grants_admin_on_all_products_for_matching_identity(
    integration_connection: Connection,
) -> None:
    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-y",
        display_name="Bootstrap Admin",
    )

    granted = maybe_grant_bootstrap_admin(
        integration_connection,
        settings=_bootstrap_settings(),
        tenant_id="tenant-x",
        object_id="oid-y",
        app_user_id=user.id,
    )

    assert granted is True
    grants = {
        g.product_key: g.role.value
        for g in list_grants_for_user(integration_connection, app_user_id=user.id)
    }
    assert grants == {"lidar": "admin", "forestry": "admin", "transelect": "admin"}


def test_bootstrap_does_not_fire_for_non_matching_identity(
    integration_connection: Connection,
) -> None:
    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind="entra",
        identity_key="tenant-x:someone-else",
        display_name="Regular User",
    )

    granted = maybe_grant_bootstrap_admin(
        integration_connection,
        settings=_bootstrap_settings(),
        tenant_id="tenant-x",
        object_id="someone-else",
        app_user_id=user.id,
    )

    assert granted is False
    assert list_grants_for_user(integration_connection, app_user_id=user.id) == ()


def test_bootstrap_does_not_fire_if_user_already_has_a_grant(
    integration_connection: Connection,
) -> None:
    user = resolve_or_create_app_user(
        integration_connection,
        identity_kind="entra",
        identity_key="tenant-x:oid-y",
        display_name="Bootstrap Admin",
    )
    grant_product_role(
        integration_connection, app_user_id=user.id, product_key="forestry", role=Role.VIEWER
    )

    granted = maybe_grant_bootstrap_admin(
        integration_connection,
        settings=_bootstrap_settings(),
        tenant_id="tenant-x",
        object_id="oid-y",
        app_user_id=user.id,
    )

    assert granted is False
    grants = {
        g.product_key: g.role.value
        for g in list_grants_for_user(integration_connection, app_user_id=user.id)
    }
    assert grants == {"forestry": "viewer"}


# ---------------------------------------------------------------------------
# Transelec bootstrap (Google Workspace sign-in)
# ---------------------------------------------------------------------------
#
# A separate bootstrap from maybe_grant_bootstrap_admin above, and
# deliberately narrower: it can only ever produce ADMIN on `transelect`. The
# Transelec pilot is hosted for one client, and the account that opens it
# must not thereby become an administrator of LiDAR or Forestal.


def _transelec_bootstrap_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "postgres_password": "x",
        "transelec_bootstrap_admin_email": "javier@campodigital.cl",
    }
    values.update(overrides)
    return Settings(**values)


def _google_user(connection: Connection, email: str) -> int:
    return resolve_or_create_app_user(
        connection,
        identity_kind="google",
        identity_key=f"google-sub-for-{email}",
        display_name=email,
        email=email,
    ).id


def test_transelec_bootstrap_grants_admin_on_transelec_and_on_nothing_else(
    integration_connection: Connection,
) -> None:
    app_user_id = _google_user(integration_connection, "javier@campodigital.cl")

    granted = maybe_grant_transelec_bootstrap_admin(
        integration_connection,
        settings=_transelec_bootstrap_settings(),
        email="javier@campodigital.cl",
        app_user_id=app_user_id,
    )

    assert granted is True
    grants = list_grants_for_user(integration_connection, app_user_id=app_user_id)
    assert [(grant.product_key, grant.role) for grant in grants] == [("transelect", Role.ADMIN)]


def test_transelec_bootstrap_never_grants_lidar_or_forestry(
    integration_connection: Connection,
) -> None:
    app_user_id = _google_user(integration_connection, "javier@campodigital.cl")

    maybe_grant_transelec_bootstrap_admin(
        integration_connection,
        settings=_transelec_bootstrap_settings(),
        email="javier@campodigital.cl",
        app_user_id=app_user_id,
    )

    for product_key in ("lidar", "forestry"):
        assert (
            get_product_role(
                integration_connection, app_user_id=app_user_id, product_key=product_key
            )
            is None
        )


def test_transelec_bootstrap_does_not_fire_for_any_other_address(
    integration_connection: Connection,
) -> None:
    app_user_id = _google_user(integration_connection, "otra.persona@campodigital.cl")

    granted = maybe_grant_transelec_bootstrap_admin(
        integration_connection,
        settings=_transelec_bootstrap_settings(),
        email="otra.persona@campodigital.cl",
        app_user_id=app_user_id,
    )

    assert granted is False
    assert list_grants_for_user(integration_connection, app_user_id=app_user_id) == ()


def test_transelec_bootstrap_does_not_fire_when_no_address_is_configured(
    integration_connection: Connection,
) -> None:
    app_user_id = _google_user(integration_connection, "javier@campodigital.cl")

    granted = maybe_grant_transelec_bootstrap_admin(
        integration_connection,
        settings=_transelec_bootstrap_settings(transelec_bootstrap_admin_email=None),
        email="javier@campodigital.cl",
        app_user_id=app_user_id,
    )

    assert granted is False
    assert list_grants_for_user(integration_connection, app_user_id=app_user_id) == ()


def test_transelec_bootstrap_matches_the_address_case_insensitively(
    integration_connection: Connection,
) -> None:
    app_user_id = _google_user(integration_connection, "Javier@CampoDigital.cl")

    granted = maybe_grant_transelec_bootstrap_admin(
        integration_connection,
        settings=_transelec_bootstrap_settings(),
        email="Javier@CampoDigital.cl",
        app_user_id=app_user_id,
    )

    assert granted is True


def test_transelec_bootstrap_is_one_time_and_never_re_escalates(
    integration_connection: Connection,
) -> None:
    # An operator later demoted this account to VIEWER. A second sign-in must
    # not silently hand ADMIN back.
    app_user_id = _google_user(integration_connection, "javier@campodigital.cl")
    grant_product_role(
        integration_connection,
        app_user_id=app_user_id,
        product_key="transelect",
        role=Role.VIEWER,
    )

    granted = maybe_grant_transelec_bootstrap_admin(
        integration_connection,
        settings=_transelec_bootstrap_settings(),
        email="javier@campodigital.cl",
        app_user_id=app_user_id,
    )

    assert granted is False
    assert (
        get_product_role(integration_connection, app_user_id=app_user_id, product_key="transelect")
        is Role.VIEWER
    )
