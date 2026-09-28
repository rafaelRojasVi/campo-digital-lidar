"""Durable PostgreSQL-backed job queue.

No message broker. Concurrency safety comes entirely from
``SELECT ... FOR UPDATE SKIP LOCKED``: two workers racing to claim the same
row never succeed at the same row, because the losing worker's subquery
simply skips a row already locked by the other worker's transaction and
finds nothing (or the next available row) instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """A processing job now leased to the calling worker."""

    id: int
    ingestion_run_id: int
    product_key: str
    attempt_count: int
    source_snapshot_id: int
    object_storage_key: str | None


def enqueue_processing_job(
    connection: Connection,
    *,
    ingestion_run_id: int,
    product_key: str,
    requested_by_app_user_id: int | None,
) -> int:
    """Queue a new processing job for an ingestion run."""

    return connection.execute(
        text(
            """
            INSERT INTO platform.processing_job (
                ingestion_run_id, product_key, requested_by_app_user_id
            )
            VALUES (:ingestion_run_id, :product_key, :requested_by_app_user_id)
            RETURNING id
            """
        ),
        {
            "ingestion_run_id": ingestion_run_id,
            "product_key": product_key,
            "requested_by_app_user_id": requested_by_app_user_id,
        },
    ).scalar_one()


def claim_next_job(
    connection: Connection,
    *,
    worker_id: str,
    lease_seconds: int = 120,
) -> ClaimedJob | None:
    """Atomically claim the next queued (or lease-expired) job, if any."""

    claimed = connection.execute(
        text(
            """
            UPDATE platform.processing_job
            SET status = 'running',
                lease_owner = :worker_id,
                lease_expires_at = now() + make_interval(secs => :lease_seconds),
                started_at = COALESCE(started_at, now()),
                attempt_count = attempt_count + 1
            WHERE id = (
                SELECT id
                FROM platform.processing_job
                WHERE status = 'queued'
                   OR (status = 'running' AND lease_expires_at < now())
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, ingestion_run_id, product_key, attempt_count
            """
        ),
        {"worker_id": worker_id, "lease_seconds": lease_seconds},
    ).one_or_none()

    if claimed is None:
        return None

    snapshot = connection.execute(
        text(
            """
            SELECT s.id AS source_snapshot_id, s.object_storage_key
            FROM platform.ingestion_run r
            JOIN platform.source_snapshot s ON s.id = r.source_snapshot_id
            WHERE r.id = :ingestion_run_id
            """
        ),
        {"ingestion_run_id": claimed.ingestion_run_id},
    ).one()

    connection.execute(
        text(
            """
            INSERT INTO platform.processing_attempt (
                processing_job_id, attempt_number, worker_id, status
            )
            VALUES (:job_id, :attempt_number, :worker_id, 'running')
            ON CONFLICT (processing_job_id, attempt_number) DO NOTHING
            """
        ),
        {
            "job_id": claimed.id,
            "attempt_number": claimed.attempt_count,
            "worker_id": worker_id,
        },
    )

    return ClaimedJob(
        id=claimed.id,
        ingestion_run_id=claimed.ingestion_run_id,
        product_key=claimed.product_key,
        attempt_count=claimed.attempt_count,
        source_snapshot_id=snapshot.source_snapshot_id,
        object_storage_key=snapshot.object_storage_key,
    )


def complete_job(connection: Connection, *, job_id: int, worker_id: str) -> None:
    """Mark a job succeeded and close out its current attempt."""

    connection.execute(
        text(
            """
            UPDATE platform.processing_job
            SET status = 'succeeded',
                finished_at = now(),
                lease_owner = NULL,
                lease_expires_at = NULL
            WHERE id = :job_id
            """
        ),
        {"job_id": job_id},
    )
    connection.execute(
        text(
            """
            UPDATE platform.processing_attempt
            SET status = 'succeeded', finished_at = now()
            WHERE processing_job_id = :job_id
              AND worker_id = :worker_id
              AND status = 'running'
            """
        ),
        {"job_id": job_id, "worker_id": worker_id},
    )


def fail_job(connection: Connection, *, job_id: int, worker_id: str, error_summary: str) -> None:
    """Record a failed attempt; retry if attempts remain, else fail the job."""

    job = connection.execute(
        text("SELECT attempt_count, max_attempts FROM platform.processing_job WHERE id = :job_id"),
        {"job_id": job_id},
    ).one()

    next_status = "failed" if job.attempt_count >= job.max_attempts else "queued"

    connection.execute(
        text(
            """
            UPDATE platform.processing_job
            SET status = :next_status,
                error_summary = :error_summary,
                lease_owner = NULL,
                lease_expires_at = NULL,
                finished_at = CASE WHEN :next_status = 'failed' THEN now() ELSE NULL END
            WHERE id = :job_id
            """
        ),
        {"job_id": job_id, "next_status": next_status, "error_summary": error_summary[:2000]},
    )
    connection.execute(
        text(
            """
            UPDATE platform.processing_attempt
            SET status = 'failed', finished_at = now(), error_summary = :error_summary
            WHERE processing_job_id = :job_id
              AND worker_id = :worker_id
              AND status = 'running'
            """
        ),
        {"job_id": job_id, "worker_id": worker_id, "error_summary": error_summary[:2000]},
    )


def fail_job_terminal(
    connection: Connection, *, job_id: int, worker_id: str, error_summary: str
) -> None:
    """Fail a job immediately, bypassing ``fail_job``'s attempt-count retry.

    For failures that a retry cannot fix — the source object no longer
    resolves in ephemeral storage, or a staging-only execution guard refused
    the job outright — requeueing would just repeat the same failure until
    ``max_attempts`` is exhausted. This marks the job (and, if one is
    in-flight, its current attempt) failed on the spot instead.
    """

    connection.execute(
        text(
            """
            UPDATE platform.processing_job
            SET status = 'failed',
                error_summary = :error_summary,
                lease_owner = NULL,
                lease_expires_at = NULL,
                finished_at = now()
            WHERE id = :job_id
            """
        ),
        {"job_id": job_id, "error_summary": error_summary[:2000]},
    )
    connection.execute(
        text(
            """
            UPDATE platform.processing_attempt
            SET status = 'failed', finished_at = now(), error_summary = :error_summary
            WHERE processing_job_id = :job_id
              AND worker_id = :worker_id
              AND status = 'running'
            """
        ),
        {"job_id": job_id, "worker_id": worker_id, "error_summary": error_summary[:2000]},
    )


def reap_stale_leases(connection: Connection) -> int:
    """Reset expired-lease running jobs back to queued. Returns count reset."""

    result = connection.execute(
        text(
            """
            UPDATE platform.processing_job
            SET status = 'queued', lease_owner = NULL, lease_expires_at = NULL
            WHERE status = 'running' AND lease_expires_at < now()
            """
        )
    )
    return result.rowcount
