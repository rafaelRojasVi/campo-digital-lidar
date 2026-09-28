"""Execution backend seam: how a queued job actually gets run.

Not a production execution model — see docs/adr/ADR-001 and ADR-004 for the
still-open production compute decision. This exists only so Render staging
(which deploys no separate worker service, per ADR-005) has a way to
actually finish queued jobs, bounded and explicit about what it will not
attempt.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from sqlalchemy import Engine, text

from app.config import Settings
from app.jobs import fail_job_terminal
from app.object_store import ObjectStore
from app.worker import run_one_job

_POLL_INTERVAL_SECONDS = 2.0
_STAGING_WORKER_ID = "staging-inprocess"


class StagingExecutionNotAllowedError(RuntimeError):
    """Raised when InProcessStagingExecutionBackend is used outside staging."""


def job_is_within_staging_limits(
    *, product_key: str, byte_size: int, max_bytes: int
) -> tuple[bool, str | None]:
    """Return (allowed, rejection_reason).

    LiDAR jobs are refused outright — real LiDAR inputs are hundreds of MB
    and full LiDAR processing must never run through this adapter. Everything
    else is capped at ``max_bytes``, well below production upload limits, to
    keep this a metadata/small-file demonstration rather than a real
    workload runner.
    """

    if product_key == "lidar":
        return False, "not processed in staging"
    if byte_size > max_bytes:
        return False, "exceeds staging execution size limit"
    return True, None


class ExecutionBackend(Protocol):
    """Something that keeps queued jobs moving."""

    async def start(self) -> None:
        """Begin processing jobs. Must not block the caller."""

    async def stop(self) -> None:
        """Stop processing jobs, allowing any in-flight attempt to finish."""


class InProcessStagingExecutionBackend:
    """Polls ``run_one_job`` on an interval, inside the FastAPI process itself.

    Explicitly not a production pattern. Usable only when
    ``Settings.app_env == "staging"`` — enforced here at construction, not
    only by whatever wires it up in ``app.main`` — because Render staging
    deploys no separate worker service (ADR-005) and this is a cheap way to
    keep the free deployment demoable, not an acceptable production
    architecture. Blocking DB/inspection work runs via ``asyncio.to_thread``
    so it never blocks the event loop.
    """

    def __init__(self, engine: Engine, store: ObjectStore, settings: Settings) -> None:
        if settings.app_env != "staging":
            raise StagingExecutionNotAllowedError(
                "InProcessStagingExecutionBackend must only run when "
                f"APP_ENV=staging (got app_env={settings.app_env!r})."
            )

        self._engine = engine
        self._store = store
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        """Start the background polling loop as an asyncio task."""

        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Signal the loop to stop and wait for its current iteration to finish."""

        self._stopping.set()
        if self._task is not None:
            await self._task

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            did_work = await asyncio.to_thread(self._run_one_guarded)
            if not did_work:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=_POLL_INTERVAL_SECONDS)

    def _run_one_guarded(self) -> bool:
        """Run one queued job, applying the staging size/product guard first.

        A guard rejection fails the job outright (never claimed via
        ``claim_next_job``, so no lease/attempt is created for it) rather
        than attempting and failing it — the outcome is already known before
        any bytes are touched.
        """

        with self._engine.connect() as connection:
            candidate = connection.execute(
                text(
                    """
                    SELECT j.id, j.product_key, s.byte_size
                    FROM platform.processing_job j
                    JOIN platform.ingestion_run r ON r.id = j.ingestion_run_id
                    JOIN platform.source_snapshot s ON s.id = r.source_snapshot_id
                    WHERE j.status = 'queued'
                    ORDER BY j.created_at
                    LIMIT 1
                    """
                )
            ).one_or_none()

            if candidate is not None:
                allowed, reason = job_is_within_staging_limits(
                    product_key=candidate.product_key,
                    byte_size=candidate.byte_size,
                    max_bytes=self._settings.staging_execution_max_bytes,
                )
                if not allowed:
                    assert reason is not None  # not-allowed always carries a reason
                    fail_job_terminal(
                        connection,
                        job_id=candidate.id,
                        worker_id=_STAGING_WORKER_ID,
                        error_summary=reason,
                    )
                    connection.commit()
                    return True

            return run_one_job(connection, self._store, worker_id=_STAGING_WORKER_ID)
