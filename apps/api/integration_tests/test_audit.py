"""Integration tests for the audit event ledger."""

from __future__ import annotations

from app.access_repository import resolve_or_create_app_user
from app.audit import record_audit_event
from sqlalchemy import Connection, text


def test_record_audit_event_persists_row(integration_connection: Connection) -> None:
    user = resolve_or_create_app_user(
        integration_connection, identity_kind="dev-local", identity_key="dana", display_name="Dana"
    )

    event_id = record_audit_event(
        integration_connection,
        actor_app_user_id=user.id,
        event_type="session.created",
        metadata={"identity_kind": "dev-local"},
    )

    row = integration_connection.execute(
        text("SELECT event_type, actor_app_user_id FROM platform.audit_event WHERE id = :id"),
        {"id": event_id},
    ).one()
    assert row.event_type == "session.created"
    assert row.actor_app_user_id == user.id


def test_record_audit_event_allows_null_actor_for_system_events(
    integration_connection: Connection,
) -> None:
    event_id = record_audit_event(
        integration_connection, actor_app_user_id=None, event_type="worker.started"
    )
    assert event_id > 0


def test_record_audit_event_defaults_metadata_to_empty_object(
    integration_connection: Connection,
) -> None:
    event_id = record_audit_event(
        integration_connection, actor_app_user_id=None, event_type="worker.idle"
    )
    row = integration_connection.execute(
        text("SELECT metadata FROM platform.audit_event WHERE id = :id"),
        {"id": event_id},
    ).one()
    assert row.metadata == {}


def test_record_audit_event_with_product_and_subject(integration_connection: Connection) -> None:
    event_id = record_audit_event(
        integration_connection,
        actor_app_user_id=None,
        event_type="processing.requested",
        product_key="forestry",
        subject_kind="processing_job",
        subject_id="42",
    )
    row = integration_connection.execute(
        text(
            "SELECT product_key, subject_kind, subject_id FROM platform.audit_event WHERE id = :id"
        ),
        {"id": event_id},
    ).one()
    assert row.product_key == "forestry"
    assert row.subject_kind == "processing_job"
    assert row.subject_id == "42"
