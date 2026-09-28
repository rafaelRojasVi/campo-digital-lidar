"""InProcessStagingExecutionBackend's DB-backed guard, against a real DB.

Exercises `_run_one_guarded` directly (rather than the async polling loop)
for determinism: the loop itself is a thin `asyncio.to_thread` wrapper with
no branching logic of its own, so testing the synchronous guard method gives
the same coverage without timing flakiness.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

from app.config import Settings
from app.execution import InProcessStagingExecutionBackend
from app.jobs import enqueue_processing_job
from app.object_store import LocalObjectStore
from sqlalchemy import Connection, Engine, text


def _staging_settings(*, max_bytes: int = 25_000_000) -> Settings:
    return Settings(
        _env_file=None,
        postgres_password="x",
        app_env="staging",
        staging_execution_max_bytes=max_bytes,
    )


def _make_ingestion_run(
    connection: Connection, *, system_key: str, product_key: str, byte_size: int
) -> int:
    digest = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    storage_key = f"sha256/{digest[:2]}/{digest[2:]}"

    system_id = connection.execute(
        text("INSERT INTO platform.source_system (system_key) VALUES (:key) RETURNING id"),
        {"key": system_key},
    ).scalar_one()
    asset_id = connection.execute(
        text(
            "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
            "VALUES (:sid, 'relative_path', 'execution_test.bin') RETURNING id"
        ),
        {"sid": system_id},
    ).scalar_one()
    snapshot_id = connection.execute(
        text(
            "INSERT INTO platform.source_snapshot "
            "(source_asset_id, content_sha256, byte_size, object_storage_key) "
            "VALUES (:aid, :sha, :size, :key) RETURNING id"
        ),
        {"aid": asset_id, "sha": digest, "size": byte_size, "key": storage_key},
    ).scalar_one()
    return connection.execute(
        text(
            "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
            "VALUES (:snid, :pk) RETURNING id"
        ),
        {"snid": snapshot_id, "pk": product_key},
    ).scalar_one()


def _cleanup(engine: Engine, *, run_id: int, job_id: int) -> None:
    with engine.connect() as conn:
        snapshot_row = conn.execute(
            text("SELECT source_snapshot_id FROM platform.ingestion_run WHERE id = :id"),
            {"id": run_id},
        ).one()
        asset_row = conn.execute(
            text("SELECT source_asset_id FROM platform.source_snapshot WHERE id = :id"),
            {"id": snapshot_row.source_snapshot_id},
        ).one()
        system_row = conn.execute(
            text("SELECT source_system_id FROM platform.source_asset WHERE id = :id"),
            {"id": asset_row.source_asset_id},
        ).one()

        conn.execute(
            text("DELETE FROM platform.processing_attempt WHERE processing_job_id = :id"),
            {"id": job_id},
        )
        conn.execute(text("DELETE FROM platform.processing_job WHERE id = :id"), {"id": job_id})
        conn.execute(text("DELETE FROM platform.ingestion_run WHERE id = :id"), {"id": run_id})
        conn.execute(
            text("DELETE FROM platform.source_snapshot WHERE id = :id"),
            {"id": snapshot_row.source_snapshot_id},
        )
        conn.execute(
            text("DELETE FROM platform.source_asset WHERE id = :id"),
            {"id": asset_row.source_asset_id},
        )
        conn.execute(
            text("DELETE FROM platform.source_system WHERE id = :id"),
            {"id": system_row.source_system_id},
        )
        conn.commit()


def test_guard_terminally_fails_lidar_job_without_claiming_it(
    integration_engine: Engine, tmp_path: Path
) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(
            setup_conn,
            system_key="exec_test_lidar",
            product_key="lidar",
            byte_size=10,
        )
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="lidar",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    backend = InProcessStagingExecutionBackend(
        integration_engine, LocalObjectStore(tmp_path), _staging_settings()
    )

    try:
        did_work = backend._run_one_guarded()
        assert did_work is True

        with integration_engine.connect() as check_conn:
            row = check_conn.execute(
                text(
                    "SELECT status, error_summary, attempt_count "
                    "FROM platform.processing_job WHERE id = :id"
                ),
                {"id": job_id},
            ).one()
        assert row.status == "failed"
        assert row.error_summary == "not processed in staging"
        # Rejected before claim_next_job ever ran — never leased, never retried.
        assert row.attempt_count == 0
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)


def test_guard_terminally_fails_oversized_job(integration_engine: Engine, tmp_path: Path) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(
            setup_conn,
            system_key="exec_test_oversize",
            product_key="forestry",
            byte_size=100,
        )
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="forestry",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    backend = InProcessStagingExecutionBackend(
        integration_engine, LocalObjectStore(tmp_path), _staging_settings(max_bytes=10)
    )

    try:
        did_work = backend._run_one_guarded()
        assert did_work is True

        with integration_engine.connect() as check_conn:
            row = check_conn.execute(
                text("SELECT status, error_summary FROM platform.processing_job WHERE id = :id"),
                {"id": job_id},
            ).one()
        assert row.status == "failed"
        assert row.error_summary == "exceeds staging execution size limit"
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)


def test_guard_allows_small_non_lidar_job_through_to_run_one_job(
    integration_engine: Engine, tmp_path: Path
) -> None:
    store = LocalObjectStore(tmp_path)
    stored = store.put(
        io.BytesIO(b"placeholder"),
        media_type="application/octet-stream",
    )

    with integration_engine.connect() as setup_conn:
        digest = stored.sha256
        storage_key = stored.key
        system_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_system (system_key) "
                "VALUES ('exec_test_within_limits') RETURNING id"
            )
        ).scalar_one()
        asset_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
                "VALUES (:sid, 'relative_path', 'within_limits.zip') RETURNING id"
            ),
            {"sid": system_id},
        ).scalar_one()
        snapshot_id = setup_conn.execute(
            text(
                "INSERT INTO platform.source_snapshot "
                "(source_asset_id, content_sha256, byte_size, object_storage_key) "
                "VALUES (:aid, :sha, :size, :key) RETURNING id"
            ),
            {"aid": asset_id, "sha": digest, "size": stored.byte_size, "key": storage_key},
        ).scalar_one()
        run_id = setup_conn.execute(
            text(
                "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
                "VALUES (:snid, 'forestry') RETURNING id"
            ),
            {"snid": snapshot_id},
        ).scalar_one()
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="forestry",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    backend = InProcessStagingExecutionBackend(integration_engine, store, _staging_settings())

    try:
        did_work = backend._run_one_guarded()
        assert did_work is True

        with integration_engine.connect() as check_conn:
            row = check_conn.execute(
                text("SELECT status, attempt_count FROM platform.processing_job WHERE id = :id"),
                {"id": job_id},
            ).one()
        # Not a valid forestry ZIP, so the inspector itself fails it — but it
        # got past the staging guard and was actually claimed/attempted,
        # which is what this test is verifying.
        assert row.attempt_count == 1
        assert row.status in ("queued", "failed")
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)
