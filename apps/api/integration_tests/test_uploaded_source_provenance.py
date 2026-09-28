"""Integration tests for upload-originated source provenance persistence."""

from __future__ import annotations

import hashlib

from app.source_provenance import persist_uploaded_source_provenance
from sqlalchemy import Connection, text


def test_persist_uploaded_source_provenance_sets_storage_key(
    integration_connection: Connection,
) -> None:
    content_sha256 = hashlib.sha256(b"upload test content").hexdigest()
    result = persist_uploaded_source_provenance(
        integration_connection,
        content_sha256=content_sha256,
        byte_size=20,
        object_storage_key=f"sha256/{content_sha256[:2]}/{content_sha256[2:]}",
        original_filename="planilla.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    row = integration_connection.execute(
        text("SELECT object_storage_key FROM platform.source_snapshot WHERE id = :id"),
        {"id": result.source_snapshot_id},
    ).one()
    assert row.object_storage_key == f"sha256/{content_sha256[:2]}/{content_sha256[2:]}"


def test_repeated_upload_of_identical_content_reuses_snapshot(
    integration_connection: Connection,
) -> None:
    content_sha256 = hashlib.sha256(b"same content twice").hexdigest()
    storage_key = f"sha256/{content_sha256[:2]}/{content_sha256[2:]}"

    first = persist_uploaded_source_provenance(
        integration_connection,
        content_sha256=content_sha256,
        byte_size=19,
        object_storage_key=storage_key,
        original_filename="first_name.xlsx",
        media_type=None,
    )
    second = persist_uploaded_source_provenance(
        integration_connection,
        content_sha256=content_sha256,
        byte_size=19,
        object_storage_key=storage_key,
        original_filename="second_name.xlsx",
        media_type=None,
    )

    assert first.source_snapshot_id == second.source_snapshot_id
    assert first.source_observation_id != second.source_observation_id
