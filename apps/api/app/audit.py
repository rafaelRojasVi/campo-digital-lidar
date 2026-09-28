"""Persistence adapter for the platform audit event ledger.

Callers are responsible for never passing secrets or raw source content in
``metadata`` — this helper only persists whatever it is given.
"""

from __future__ import annotations

import json

from sqlalchemy import Connection, text

# One event type for every change to a product role, whoever makes it, so a
# user's role history is one query. ``metadata.via`` says which path made it.
PRODUCT_GRANT_CHANGED_EVENT = "product_grant.changed"


def record_audit_event(
    connection: Connection,
    *,
    actor_app_user_id: int | None,
    event_type: str,
    product_key: str | None = None,
    subject_kind: str | None = None,
    subject_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> int:
    """Persist one audit event row and return its id."""

    return connection.execute(
        text(
            """
            INSERT INTO platform.audit_event (
                actor_app_user_id,
                event_type,
                product_key,
                subject_kind,
                subject_id,
                metadata
            )
            VALUES (
                :actor_app_user_id,
                :event_type,
                :product_key,
                :subject_kind,
                :subject_id,
                CAST(:metadata AS JSONB)
            )
            RETURNING id
            """
        ),
        {
            "actor_app_user_id": actor_app_user_id,
            "event_type": event_type,
            "product_key": product_key,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "metadata": json.dumps(metadata or {}),
        },
    ).scalar_one()
