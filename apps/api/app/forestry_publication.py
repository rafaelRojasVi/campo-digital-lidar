"""Which Forestry snapshot the Rodales dashboard serves, and how that changes.

The same shape as ``app.transelec_publication``: a singleton state row
(``forestry.publication_state``, migration 0010) and an append-only event
per activation (``forestry.publication_event``). Activation is one short
transaction that locks the state row, so two concurrent publish/restore
calls serialize.

Forestry is stricter than Transelec in two ways:

- ``publish`` only accepts a snapshot that has never been published, and
  ``restore`` only one that has. The trail then says plainly whether a new
  version was made visible or an old one was brought back.
- The caller states which snapshot it believes is published
  (``expected_published_snapshot_id``). A review compares a pending upload
  against the published version; if someone else published in between,
  that review is stale, and the activation is refused instead of silently
  publishing over a version the reviewer never saw.

This module decides nothing about authorization (the router gates on
``Action.PUBLISH``) and never parses a source file.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection, text

_STATE_ID = 1

ActivationEventType = Literal["publish", "restore"]
VersionStatus = Literal["published", "pending", "previously_published"]


class ForestryPublicationError(RuntimeError):
    """Base error for a Forestry activation attempt."""


class SnapshotNotFoundError(ForestryPublicationError):
    """No such Forestry snapshot."""


class PublicationConflictError(ForestryPublicationError):
    """The activation does not apply to the snapshot's current status."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ActivationResult:
    """Outcome of one publish/restore."""

    shapefile_snapshot_id: int
    event_type: ActivationEventType
    publication_event_id: int
    occurred_at: dt.datetime
    previous_snapshot_id: int | None


def read_published_snapshot_id(connection: Connection) -> int | None:
    """The snapshot the dashboard serves, or None."""

    return connection.execute(
        text("SELECT published_snapshot_id FROM forestry.publication_state WHERE id = :id"),
        {"id": _STATE_ID},
    ).scalar_one()


def ever_published_snapshot_ids(connection: Connection) -> frozenset[int]:
    """Every snapshot that has been visible at some point."""

    return frozenset(
        connection.execute(
            text("SELECT DISTINCT shapefile_snapshot_id FROM forestry.publication_event")
        ).scalars()
    )


def version_status(connection: Connection, shapefile_snapshot_id: int) -> VersionStatus:
    """``published``, ``previously_published`` or ``pending`` (never published)."""

    if read_published_snapshot_id(connection) == shapefile_snapshot_id:
        return "published"
    if shapefile_snapshot_id in ever_published_snapshot_ids(connection):
        return "previously_published"
    return "pending"


def activate_snapshot(
    connection: Connection,
    *,
    shapefile_snapshot_id: int,
    actor_app_user_id: int,
    event_type: ActivationEventType,
    expected_published_snapshot_id: int | None,
) -> ActivationResult:
    """Make ``shapefile_snapshot_id`` the served snapshot, inside the caller's transaction."""

    previous = connection.execute(
        text(
            """
            SELECT published_snapshot_id
            FROM forestry.publication_state
            WHERE id = :id
            FOR UPDATE
            """
        ),
        {"id": _STATE_ID},
    ).scalar_one()

    exists = connection.execute(
        text("SELECT 1 FROM forestry.shapefile_snapshot WHERE id = :id"),
        {"id": shapefile_snapshot_id},
    ).scalar_one_or_none()
    if exists is None:
        raise SnapshotNotFoundError(f"No forestry snapshot with id={shapefile_snapshot_id}.")

    if previous != expected_published_snapshot_id:
        raise PublicationConflictError(
            "stale_review",
            "The published snapshot changed after this review was prepared.",
        )
    if previous == shapefile_snapshot_id:
        raise PublicationConflictError("already_published", "The snapshot is already published.")

    was_published = shapefile_snapshot_id in ever_published_snapshot_ids(connection)
    if event_type == "publish" and was_published:
        raise PublicationConflictError(
            "use_restore", "The snapshot was published before; restore it instead."
        )
    if event_type == "restore" and not was_published:
        raise PublicationConflictError(
            "not_previously_published", "Only a previously published snapshot can be restored."
        )

    connection.execute(
        text(
            """
            UPDATE forestry.publication_state
            SET published_snapshot_id = :snapshot_id, updated_at = now()
            WHERE id = :id
            """
        ),
        {"snapshot_id": shapefile_snapshot_id, "id": _STATE_ID},
    )
    event = connection.execute(
        text(
            """
            INSERT INTO forestry.publication_event (
                shapefile_snapshot_id, event_type, previous_snapshot_id, actor_app_user_id
            )
            VALUES (:snapshot_id, :event_type, :previous, :actor)
            RETURNING id, occurred_at
            """
        ),
        {
            "snapshot_id": shapefile_snapshot_id,
            "event_type": event_type,
            "previous": previous,
            "actor": actor_app_user_id,
        },
    ).one()

    return ActivationResult(
        shapefile_snapshot_id=shapefile_snapshot_id,
        event_type=event_type,
        publication_event_id=event.id,
        occurred_at=event.occurred_at,
        previous_snapshot_id=previous,
    )


def publish_initial_if_unpublished(connection: Connection, *, shapefile_snapshot_id: int) -> bool:
    """Publish ``shapefile_snapshot_id`` as ``initial`` only when nothing is published.

    Used by the controlled CLI import (``scripts/forestry_snapshot_import.py``),
    which has no signed-in actor. Returns whether it published.
    """

    previous = connection.execute(
        text(
            "SELECT published_snapshot_id FROM forestry.publication_state WHERE id = :id FOR UPDATE"
        ),
        {"id": _STATE_ID},
    ).scalar_one()
    if previous is not None:
        return False

    connection.execute(
        text(
            "UPDATE forestry.publication_state "
            "SET published_snapshot_id = :snapshot_id, updated_at = now() WHERE id = :id"
        ),
        {"snapshot_id": shapefile_snapshot_id, "id": _STATE_ID},
    )
    connection.execute(
        text(
            "INSERT INTO forestry.publication_event (shapefile_snapshot_id, event_type) "
            "VALUES (:snapshot_id, 'initial')"
        ),
        {"snapshot_id": shapefile_snapshot_id},
    )
    return True
