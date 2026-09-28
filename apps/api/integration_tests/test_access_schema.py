"""Schema-level checks for the platform access foundation."""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError


def test_product_grant_rejects_unknown_role(integration_connection: Connection) -> None:
    user_id = integration_connection.execute(
        text(
            "INSERT INTO platform.app_user (identity_kind, identity_key, display_name) "
            "VALUES ('dev-local', 'alice', 'Alice') RETURNING id"
        )
    ).scalar_one()

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "INSERT INTO platform.product_grant (app_user_id, product_key, role) "
                "VALUES (:user_id, 'lidar', 'superadmin')"
            ),
            {"user_id": user_id},
        )


def test_product_grant_unique_per_user_and_product(integration_connection: Connection) -> None:
    user_id = integration_connection.execute(
        text(
            "INSERT INTO platform.app_user (identity_kind, identity_key, display_name) "
            "VALUES ('dev-local', 'bob', 'Bob') RETURNING id"
        )
    ).scalar_one()

    integration_connection.execute(
        text(
            "INSERT INTO platform.product_grant (app_user_id, product_key, role) "
            "VALUES (:user_id, 'forestry', 'operator')"
        ),
        {"user_id": user_id},
    )

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "INSERT INTO platform.product_grant (app_user_id, product_key, role) "
                "VALUES (:user_id, 'forestry', 'viewer')"
            ),
            {"user_id": user_id},
        )


def test_audit_event_allows_null_actor(integration_connection: Connection) -> None:
    event_id = integration_connection.execute(
        text(
            "INSERT INTO platform.audit_event (actor_app_user_id, event_type) "
            "VALUES (NULL, 'worker.started') RETURNING id"
        )
    ).scalar_one()
    assert event_id > 0
