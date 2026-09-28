"""Job durability: enqueue, SKIP LOCKED claim exclusivity, retry, stale lease reap."""

from __future__ import annotations

from app.jobs import (
    claim_next_job,
    complete_job,
    enqueue_processing_job,
    fail_job,
    reap_stale_leases,
)
from sqlalchemy import Connection, Engine, text


def _make_ingestion_run(
    connection: Connection, *, system_key: str, product_key: str = "transelect"
) -> int:
    system_id = connection.execute(
        text("INSERT INTO platform.source_system (system_key) VALUES (:key) RETURNING id"),
        {"key": system_key},
    ).scalar_one()
    asset_id = connection.execute(
        text(
            "INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key) "
            "VALUES (:sid, 'relative_path', 'jobs_test.xlsx') RETURNING id"
        ),
        {"sid": system_id},
    ).scalar_one()
    content_sha256 = format(abs(hash(system_key)) % (16**64), "064x")
    storage_key = f"sha256/{content_sha256[:2]}/{content_sha256[2:]}"
    snapshot_id = connection.execute(
        text(
            "INSERT INTO platform.source_snapshot "
            "(source_asset_id, content_sha256, byte_size, object_storage_key) "
            "VALUES (:aid, :sha, 5, :key) RETURNING id"
        ),
        {"aid": asset_id, "sha": content_sha256, "key": storage_key},
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


def test_two_workers_never_claim_the_same_job(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn, system_key="jobs_test_exclusivity")
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as conn_a, integration_engine.connect() as conn_b:
            claimed_a = claim_next_job(conn_a, worker_id="worker-a")
            conn_a.commit()
            claimed_b = claim_next_job(conn_b, worker_id="worker-b")
            conn_b.commit()

        assert claimed_a is not None
        assert claimed_a.id == job_id
        assert claimed_b is None
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)


def test_claimed_job_carries_snapshot_and_storage_key(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn, system_key="jobs_test_carry")
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as conn:
            claimed = claim_next_job(conn, worker_id="worker-a")
            conn.commit()
        assert claimed is not None
        assert claimed.object_storage_key is not None
        assert claimed.object_storage_key.startswith("sha256/")
        assert claimed.attempt_count == 1
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)


def test_stale_lease_is_reclaimed(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn, system_key="jobs_test_stale")
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        claim_next_job(setup_conn, worker_id="worker-crashed", lease_seconds=0)
        setup_conn.commit()

    try:
        with integration_engine.connect() as reap_conn:
            reset_count = reap_stale_leases(reap_conn)
            reap_conn.commit()
        assert reset_count >= 1

        with integration_engine.connect() as retry_conn:
            claimed = claim_next_job(retry_conn, worker_id="worker-b")
            retry_conn.commit()
        assert claimed is not None
        assert claimed.id == job_id
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)


def test_fail_job_retries_until_max_attempts_then_fails(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn, system_key="jobs_test_retry")
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as conn:
            for _ in range(3):
                claimed = claim_next_job(conn, worker_id="retry-worker")
                assert claimed is not None
                fail_job(conn, job_id=job_id, worker_id="retry-worker", error_summary="boom")
                conn.commit()

            status = conn.execute(
                text("SELECT status, attempt_count FROM platform.processing_job WHERE id = :id"),
                {"id": job_id},
            ).one()
        assert status.status == "failed"
        assert status.attempt_count == 3
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)


def test_complete_job_marks_succeeded(integration_engine: Engine) -> None:
    with integration_engine.connect() as setup_conn:
        run_id = _make_ingestion_run(setup_conn, system_key="jobs_test_complete")
        job_id = enqueue_processing_job(
            setup_conn,
            ingestion_run_id=run_id,
            product_key="transelect",
            requested_by_app_user_id=None,
        )
        setup_conn.commit()

    try:
        with integration_engine.connect() as conn:
            claimed = claim_next_job(conn, worker_id="worker-a")
            assert claimed is not None
            complete_job(conn, job_id=job_id, worker_id="worker-a")
            conn.commit()

            status = conn.execute(
                text("SELECT status FROM platform.processing_job WHERE id = :id"), {"id": job_id}
            ).one()
        assert status.status == "succeeded"
    finally:
        _cleanup(integration_engine, run_id=run_id, job_id=job_id)


def test_claim_returns_none_when_queue_is_empty(integration_engine: Engine) -> None:
    with integration_engine.connect() as conn:
        claimed = claim_next_job(conn, worker_id="idle-worker")
        conn.commit()
    assert claimed is None
