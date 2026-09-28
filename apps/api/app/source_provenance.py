"""Persistence adapter for source provenance metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, text

from app.source_discovery import (
    SourceFileFingerprint,
    SourceFileObservation,
)

FILESYSTEM_IDENTITY_KIND = "relative_path"
UPLOAD_IDENTITY_KIND = "content_sha256"
UPLOAD_SYSTEM_KEY = "campo_digital_upload"


class SourceProvenanceError(RuntimeError):
    """Base error for source provenance persistence."""


class SourceProvenanceConflictError(SourceProvenanceError):
    """Raised when persisted provenance conflicts with supplied metadata."""


@dataclass(frozen=True, slots=True)
class PersistedSourceProvenance:
    """Database identities created or resolved for one observation."""

    source_system_id: int
    source_asset_id: int
    source_snapshot_id: int
    source_observation_id: int


def persist_filesystem_source_provenance(
    connection: Connection,
    *,
    system_key: str,
    observation: SourceFileObservation,
    fingerprint: SourceFileFingerprint,
) -> PersistedSourceProvenance:
    """Persist one filesystem observation inside the caller's transaction."""

    _validate_discovery_pair(
        observation,
        fingerprint,
    )

    source_system_id = _resolve_source_system(
        connection,
        system_key=system_key,
    )

    source_asset_id = _resolve_source_asset(
        connection,
        source_system_id=source_system_id,
        identity_kind=FILESYSTEM_IDENTITY_KIND,
        identity_key=observation.relative_path,
    )

    source_snapshot_id = _resolve_source_snapshot(
        connection,
        source_asset_id=source_asset_id,
        content_sha256=fingerprint.content_sha256,
        byte_size=fingerprint.byte_size,
    )

    source_observation_id = connection.execute(
        text(
            """
            INSERT INTO platform.source_observation (
                source_snapshot_id,
                source_path,
                filename,
                observed_at,
                source_modified_at,
                media_type
            )
            VALUES (
                :source_snapshot_id,
                :source_path,
                :filename,
                :observed_at,
                :source_modified_at,
                :media_type
            )
            RETURNING id
            """
        ),
        {
            "source_snapshot_id": source_snapshot_id,
            "source_path": observation.relative_path,
            "filename": observation.filename,
            "observed_at": observation.observed_at,
            "source_modified_at": observation.source_modified_at,
            "media_type": observation.media_type,
        },
    ).scalar_one()

    return PersistedSourceProvenance(
        source_system_id=source_system_id,
        source_asset_id=source_asset_id,
        source_snapshot_id=source_snapshot_id,
        source_observation_id=source_observation_id,
    )


def persist_uploaded_source_provenance(
    connection: Connection,
    *,
    content_sha256: str,
    byte_size: int,
    object_storage_key: str,
    original_filename: str,
    media_type: str | None,
) -> PersistedSourceProvenance:
    """Persist one uploaded file's provenance inside the caller's transaction.

    Uploaded content is identified by its own SHA-256 (identity_kind
    "content_sha256"), under a dedicated "campo_digital_upload" source
    system distinct from the filesystem mirror — so uploading identical
    bytes twice resolves to the same source asset and snapshot, reusing the
    same object_storage_key rather than violating its global uniqueness.
    """

    source_system_id = _resolve_source_system(
        connection,
        system_key=UPLOAD_SYSTEM_KEY,
    )

    source_asset_id = _resolve_source_asset(
        connection,
        source_system_id=source_system_id,
        identity_kind=UPLOAD_IDENTITY_KIND,
        identity_key=content_sha256,
    )

    source_snapshot_id = _resolve_source_snapshot(
        connection,
        source_asset_id=source_asset_id,
        content_sha256=content_sha256,
        byte_size=byte_size,
    )

    connection.execute(
        text(
            """
            UPDATE platform.source_snapshot
            SET object_storage_key = :object_storage_key
            WHERE id = :id AND object_storage_key IS NULL
            """
        ),
        {"object_storage_key": object_storage_key, "id": source_snapshot_id},
    )

    source_observation_id = connection.execute(
        text(
            """
            INSERT INTO platform.source_observation (
                source_snapshot_id,
                source_path,
                filename,
                observed_at,
                source_modified_at,
                media_type
            )
            VALUES (
                :source_snapshot_id,
                :source_path,
                :filename,
                :observed_at,
                NULL,
                :media_type
            )
            RETURNING id
            """
        ),
        {
            "source_snapshot_id": source_snapshot_id,
            "source_path": f"upload://{original_filename}",
            "filename": original_filename,
            "observed_at": datetime.now(UTC),
            "media_type": media_type,
        },
    ).scalar_one()

    return PersistedSourceProvenance(
        source_system_id=source_system_id,
        source_asset_id=source_asset_id,
        source_snapshot_id=source_snapshot_id,
        source_observation_id=source_observation_id,
    )


def _validate_discovery_pair(
    observation: SourceFileObservation,
    fingerprint: SourceFileFingerprint,
) -> None:
    if observation.relative_path != fingerprint.relative_path:
        raise SourceProvenanceConflictError(
            "Observation and fingerprint refer to different source paths",
        )

    if observation.byte_size != fingerprint.byte_size:
        raise SourceProvenanceConflictError(
            "Observation and fingerprint disagree on source byte size",
        )


def _resolve_source_system(
    connection: Connection,
    *,
    system_key: str,
) -> int:
    inserted_id = connection.execute(
        text(
            """
            INSERT INTO platform.source_system (system_key)
            VALUES (:system_key)
            ON CONFLICT (system_key) DO NOTHING
            RETURNING id
            """
        ),
        {"system_key": system_key},
    ).scalar_one_or_none()

    if inserted_id is not None:
        return inserted_id

    return connection.execute(
        text(
            """
            SELECT id
            FROM platform.source_system
            WHERE system_key = :system_key
            """
        ),
        {"system_key": system_key},
    ).scalar_one()


def _resolve_source_asset(
    connection: Connection,
    *,
    source_system_id: int,
    identity_kind: str,
    identity_key: str,
) -> int:
    parameters = {
        "source_system_id": source_system_id,
        "identity_kind": identity_kind,
        "identity_key": identity_key,
    }

    inserted_id = connection.execute(
        text(
            """
            INSERT INTO platform.source_asset (
                source_system_id,
                identity_kind,
                identity_key
            )
            VALUES (
                :source_system_id,
                :identity_kind,
                :identity_key
            )
            ON CONFLICT (
                source_system_id,
                identity_kind,
                identity_key
            )
            DO NOTHING
            RETURNING id
            """
        ),
        parameters,
    ).scalar_one_or_none()

    if inserted_id is not None:
        return inserted_id

    return connection.execute(
        text(
            """
            SELECT id
            FROM platform.source_asset
            WHERE source_system_id = :source_system_id
              AND identity_kind = :identity_kind
              AND identity_key = :identity_key
            """
        ),
        parameters,
    ).scalar_one()


def _resolve_source_snapshot(
    connection: Connection,
    *,
    source_asset_id: int,
    content_sha256: str,
    byte_size: int,
) -> int:
    parameters = {
        "source_asset_id": source_asset_id,
        "content_sha256": content_sha256,
        "byte_size": byte_size,
    }

    inserted_id = connection.execute(
        text(
            """
            INSERT INTO platform.source_snapshot (
                source_asset_id,
                content_sha256,
                byte_size
            )
            VALUES (
                :source_asset_id,
                :content_sha256,
                :byte_size
            )
            ON CONFLICT (
                source_asset_id,
                content_sha256
            )
            DO NOTHING
            RETURNING id
            """
        ),
        parameters,
    ).scalar_one_or_none()

    if inserted_id is not None:
        return inserted_id

    existing = connection.execute(
        text(
            """
            SELECT id, byte_size
            FROM platform.source_snapshot
            WHERE source_asset_id = :source_asset_id
              AND content_sha256 = :content_sha256
            """
        ),
        parameters,
    ).one()

    existing_id = int(existing.id)
    existing_byte_size = int(existing.byte_size)

    if existing_byte_size != byte_size:
        raise SourceProvenanceConflictError(
            "Existing source snapshot has conflicting byte size",
        )

    return existing_id
