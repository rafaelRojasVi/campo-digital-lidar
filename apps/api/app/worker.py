"""Local job worker: claim one job, run its product inspection, record evidence.

No message broker — the queue lives entirely in PostgreSQL (see ``app.jobs``).
Multiple worker processes may run this loop concurrently and safely, since
``claim_next_job`` uses ``SELECT ... FOR UPDATE SKIP LOCKED``.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from app.audit import record_audit_event
from app.config import get_settings
from app.database import build_engine
from app.inspection.forestry_inspector import inspect_forestry_zip
from app.inspection.lidar_inspector import inspect_lidar_file
from app.inspection.transelec_inspector import inspect_transelec_workbook
from app.jobs import ClaimedJob, claim_next_job, complete_job, fail_job, fail_job_terminal
from app.object_store import LocalObjectStore, ObjectStore, open_configured_object_store

_IDLE_SLEEP_SECONDS = 2.0


def dispatch_inspection(product_key: str, local_path: Path) -> dict[str, Any]:
    """Route to the product's inspector; return JSON-serializable evidence."""

    if product_key == "lidar":
        return dataclasses.asdict(inspect_lidar_file(local_path))
    if product_key == "forestry":
        return dataclasses.asdict(inspect_forestry_zip(local_path))
    if product_key == "transelect":
        return dataclasses.asdict(inspect_transelec_workbook(local_path))

    raise ValueError(f"Unknown product_key for inspection dispatch: {product_key!r}.")


def run_one_job(connection: Connection, store: ObjectStore, *, worker_id: str) -> bool:
    """Claim and process one job. Returns False if nothing was queued."""

    claimed: ClaimedJob | None = claim_next_job(connection, worker_id=worker_id)
    connection.commit()

    if claimed is None:
        return False

    if claimed.object_storage_key is None:
        fail_job(
            connection,
            job_id=claimed.id,
            worker_id=worker_id,
            error_summary="Source snapshot has no object_storage_key.",
        )
        connection.commit()
        return True

    if not store.exists(claimed.object_storage_key):
        # Render's free-tier filesystem is ephemeral: a job row can outlive
        # the local object it references across a redeploy or spin-down/wake
        # cycle. Retrying would just hit the same missing object forever, so
        # this fails the job terminally on the spot rather than through
        # fail_job's attempt-count-based requeue.
        fail_job_terminal(
            connection,
            job_id=claimed.id,
            worker_id=worker_id,
            error_summary="source object unavailable (ephemeral storage cycled)",
        )
        connection.commit()
        return True

    temp_path = Path(tempfile.gettempdir()) / f"campo-worker-{uuid.uuid4().hex}"

    try:
        with store.open(claimed.object_storage_key) as source, temp_path.open("wb") as sink:
            sink.write(source.read())

        evidence = dispatch_inspection(claimed.product_key, temp_path)

        evidence_bytes = json.dumps(evidence, default=str).encode("utf-8")
        stored_artifact = store.put(io.BytesIO(evidence_bytes), media_type="application/json")

        connection.execute(
            text(
                """
                INSERT INTO platform.generated_artifact (
                    processing_job_id, artifact_kind, storage_key, byte_size, media_type
                )
                VALUES (:job_id, 'inspection_report', :key, :size, 'application/json')
                """
            ),
            {
                "job_id": claimed.id,
                "key": stored_artifact.key,
                "size": stored_artifact.byte_size,
            },
        )
        complete_job(connection, job_id=claimed.id, worker_id=worker_id)
        record_audit_event(
            connection,
            actor_app_user_id=None,
            event_type="artifact.produced",
            product_key=claimed.product_key,
            subject_kind="processing_job",
            subject_id=str(claimed.id),
        )
    except Exception as exc:  # noqa: BLE001 - any inspector failure must fail the job, not crash the worker
        fail_job(connection, job_id=claimed.id, worker_id=worker_id, error_summary=str(exc))
        record_audit_event(
            connection,
            actor_app_user_id=None,
            event_type="processing.failed",
            product_key=claimed.product_key,
            subject_kind="processing_job",
            subject_id=str(claimed.id),
        )
    finally:
        temp_path.unlink(missing_ok=True)

    connection.commit()
    return True


def main() -> None:
    """Run the worker loop: repeatedly claim and process jobs until interrupted."""

    settings = get_settings()
    engine = build_engine(settings)
    store: ObjectStore = _build_store_from_env()
    worker_id = f"worker-{uuid.uuid4().hex[:8]}"

    print(f"[platform-worker] starting as {worker_id}")

    try:
        while True:
            with engine.connect() as connection:
                did_work = run_one_job(connection, store, worker_id=worker_id)
            if not did_work:
                time.sleep(_IDLE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        print(f"[platform-worker] {worker_id} stopping")


def _build_store_from_env() -> LocalObjectStore:
    return open_configured_object_store(
        os.environ.get("APP_ENV"), os.environ.get("CAMPO_OBJECT_STORE_ROOT")
    )


if __name__ == "__main__":
    main()
