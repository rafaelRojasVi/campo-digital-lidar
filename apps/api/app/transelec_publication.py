"""Steps C and D of the Transelec ingestion lifecycle: publish and restore.

Activation is one short, explicit transaction that is never a side effect of
validation succeeding. Publish (Step C) and restore (Step D) are the *same*
primitive with different targets and event types: restore does not
re-validate, because an invalid import is never committed by Step B, so
there is never a bad version to skip validating.

This module owns only the activation write. It deliberately does not parse
workbooks, project rows, or decide authorization — the router gates on
``Action.PUBLISH`` before calling in, and Step B
(``transelec_ingestion.import_projection``) already committed the immutable
version being activated.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection, text

TRANSELEC_PRODUCT_KEY = "transelect"

# platform.transelec_dashboard_state is a singleton row, pinned by
# CHECK (id = 1) in migration 0004 and seeded there.
_DASHBOARD_STATE_ID = 1

ActivationEventType = Literal["publish", "restore"]


class PublicationError(RuntimeError):
    """Base error for an activation attempt."""


class ImportNotFoundError(PublicationError):
    """The requested import does not exist, so there is nothing to activate."""


@dataclass(frozen=True, slots=True)
class ActivationResult:
    """Outcome of one publish/restore activation."""

    import_id: int
    event_type: ActivationEventType
    publish_event_id: int
    occurred_at: dt.datetime
    previous_import_id: int | None


def read_active_import_id(connection: Connection) -> int | None:
    """Return the import the dashboard currently serves, if any."""

    return connection.execute(
        text("SELECT active_import_id FROM platform.transelec_dashboard_state WHERE id = :id"),
        {"id": _DASHBOARD_STATE_ID},
    ).scalar_one()


def activate_import(
    connection: Connection,
    *,
    import_id: int,
    actor_user_id: int,
    event_type: ActivationEventType,
) -> ActivationResult:
    """Atomically make ``import_id`` the active version, inside the caller's transaction.

    Locks the singleton dashboard-state row first, so two concurrent
    publish/restore calls serialize rather than interleaving a state flip
    with another call's event insert. The caller owns COMMIT.
    """

    previous_import_id = connection.execute(
        text(
            """
            SELECT active_import_id
            FROM platform.transelec_dashboard_state
            WHERE id = :id
            FOR UPDATE
            """
        ),
        {"id": _DASHBOARD_STATE_ID},
    ).scalar_one()

    target_exists = connection.execute(
        text("SELECT 1 FROM platform.transelec_import WHERE id = :import_id"),
        {"import_id": import_id},
    ).scalar_one_or_none()

    if target_exists is None:
        raise ImportNotFoundError(f"No committed transelec_import with id={import_id}.")

    connection.execute(
        text(
            """
            UPDATE platform.transelec_dashboard_state
            SET active_import_id = :import_id, updated_at = now()
            WHERE id = :id
            """
        ),
        {"import_id": import_id, "id": _DASHBOARD_STATE_ID},
    )

    event = connection.execute(
        text(
            """
            INSERT INTO platform.transelec_publish_event (import_id, event_type, actor_user_id)
            VALUES (:import_id, :event_type, :actor_user_id)
            RETURNING id, occurred_at
            """
        ),
        {"import_id": import_id, "event_type": event_type, "actor_user_id": actor_user_id},
    ).one()

    return ActivationResult(
        import_id=import_id,
        event_type=event_type,
        publish_event_id=event.id,
        occurred_at=event.occurred_at,
        previous_import_id=previous_import_id,
    )
