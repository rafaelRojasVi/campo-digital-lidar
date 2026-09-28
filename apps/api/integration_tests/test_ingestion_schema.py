"""Schema-level checks for the platform ingestion foundation."""

from __future__ import annotations

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError


def _make_snapshot(connection: Connection, *, system_key: str, identity_key: str) -> int:
    system_id = connection.execute(
        text("INSERT INTO platform.source_system (system_key) VALUES (:key) RETURNING id"),
        {"key": system_key},
    ).scalar_one()
    asset_id = connection.execute(
        text(
            "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
            "VALUES (:sid, 'relative_path', :ikey) RETURNING id"
        ),
        {"sid": system_id, "ikey": identity_key},
    ).scalar_one()
    return connection.execute(
        text(
            "INSERT INTO platform.source_snapshot (source_asset_id, content_sha256, byte_size) "
            "VALUES (:aid, repeat('a', 64), 10) RETURNING id"
        ),
        {"aid": asset_id},
    ).scalar_one()


def test_processing_job_rejects_unknown_status(integration_connection: Connection) -> None:
    snapshot_id = _make_snapshot(
        integration_connection, system_key="job_status_test", identity_key="a.xlsx"
    )
    run_id = integration_connection.execute(
        text(
            "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
            "VALUES (:sid, 'transelect') RETURNING id"
        ),
        {"sid": snapshot_id},
    ).scalar_one()

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "INSERT INTO platform.processing_job (ingestion_run_id, product_key, status) "
                "VALUES (:rid, 'transelect', 'paused')"
            ),
            {"rid": run_id},
        )


def test_source_snapshot_object_storage_key_unique_when_present(
    integration_connection: Connection,
) -> None:
    snapshot_a = _make_snapshot(
        integration_connection, system_key="dup_key_test_1", identity_key="a.xlsx"
    )
    integration_connection.execute(
        text(
            "UPDATE platform.source_snapshot SET object_storage_key = 'sha256/dup' WHERE id = :id"
        ),
        {"id": snapshot_a},
    )

    snapshot_b = _make_snapshot(
        integration_connection, system_key="dup_key_test_2", identity_key="b.xlsx"
    )

    with pytest.raises(IntegrityError):
        integration_connection.execute(
            text(
                "UPDATE platform.source_snapshot "
                "SET object_storage_key = 'sha256/dup' WHERE id = :id"
            ),
            {"id": snapshot_b},
        )


def test_source_snapshot_allows_multiple_null_object_storage_keys(
    integration_connection: Connection,
) -> None:
    _make_snapshot(integration_connection, system_key="null_key_test_1", identity_key="a.xlsx")
    _make_snapshot(integration_connection, system_key="null_key_test_2", identity_key="b.xlsx")
