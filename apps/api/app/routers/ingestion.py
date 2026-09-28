"""Intake/ingestion HTTP adapter: upload, job listing, retry, audit trail.

Product is always an explicit form field, never inferred from filename or
extension. Job/audit visibility is always scoped to the caller's own product
grants, never leaking existence of jobs/events for ungranted products.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.access import Action, Role, can
from app.access_repository import AppUser, get_product_role, list_grants_for_user
from app.audit import record_audit_event
from app.csrf import require_csrf
from app.deps import ensure_can, get_current_app_user, get_db_connection, get_object_store
from app.inspection.forestry_inspector import ForestryInspectionError
from app.jobs import enqueue_processing_job
from app.object_store import ObjectStore
from app.source_provenance import persist_uploaded_source_provenance
from app.worker import dispatch_inspection

router = APIRouter(prefix="/ingesta", tags=["ingesta"])

PRODUCT_KEYS = ("lidar", "forestry", "transelect")
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB; bounded, not unlimited
_UPLOAD_READ_CHUNK = 1024 * 1024


class UploadResponse(BaseModel):
    source_snapshot_id: int
    sha256: str
    byte_size: int
    validation_evidence: dict[str, object]
    job_id: int


class JobView(BaseModel):
    id: int
    product_key: str
    status: str
    attempt_count: int
    created_at: str
    error_summary: str | None


class AuditEventView(BaseModel):
    id: int
    occurred_at: str
    actor_app_user_id: int | None
    event_type: str
    product_key: str | None
    subject_kind: str | None
    subject_id: str | None


@router.post(
    "/upload",
    response_model=UploadResponse,
    dependencies=[Depends(require_csrf)],
)
async def upload(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    product_key: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> UploadResponse:
    """Accept one file for one explicit product, validate, store, and queue processing."""

    if product_key not in PRODUCT_KEYS:
        raise HTTPException(status_code=422, detail="Unknown product_key.")

    ensure_can(connection, app_user_id=user.id, product_key=product_key, action=Action.UPLOAD)

    temp_path = Path(tempfile.gettempdir()) / f"campo-upload-{uuid.uuid4().hex}"
    total_bytes = 0

    try:
        with temp_path.open("wb") as sink:
            while chunk := await file.read(_UPLOAD_READ_CHUNK):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413, detail="Upload exceeds the maximum allowed size."
                    )
                sink.write(chunk)

        validation_evidence: dict[str, object]
        try:
            validation_evidence = dispatch_inspection(product_key, temp_path)
        except ForestryInspectionError as exc:
            # Security-relevant archive rejection: never persist a rejected upload.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - a non-security inspection failure is evidence, not a rejection
            validation_evidence = {"error": str(exc)}

        with temp_path.open("rb") as handle:
            stored = store.put(handle, media_type=file.content_type)

        provenance = persist_uploaded_source_provenance(
            connection,
            content_sha256=stored.sha256,
            byte_size=stored.byte_size,
            object_storage_key=stored.key,
            original_filename=file.filename or "unnamed",
            media_type=file.content_type,
        )

        run_id = connection.execute(
            text(
                "INSERT INTO platform.ingestion_run "
                "(source_snapshot_id, product_key, requested_by_app_user_id) "
                "VALUES (:snapshot_id, :product_key, :user_id) RETURNING id"
            ),
            {
                "snapshot_id": provenance.source_snapshot_id,
                "product_key": product_key,
                "user_id": user.id,
            },
        ).scalar_one()

        job_id = enqueue_processing_job(
            connection,
            ingestion_run_id=run_id,
            product_key=product_key,
            requested_by_app_user_id=user.id,
        )

        record_audit_event(
            connection,
            actor_app_user_id=user.id,
            event_type="upload.completed",
            product_key=product_key,
            subject_kind="source_snapshot",
            subject_id=str(provenance.source_snapshot_id),
            metadata={"original_filename": file.filename, "byte_size": stored.byte_size},
        )
        record_audit_event(
            connection,
            actor_app_user_id=user.id,
            event_type="processing.requested",
            product_key=product_key,
            subject_kind="processing_job",
            subject_id=str(job_id),
        )
    finally:
        temp_path.unlink(missing_ok=True)

    return UploadResponse(
        source_snapshot_id=provenance.source_snapshot_id,
        sha256=stored.sha256,
        byte_size=stored.byte_size,
        validation_evidence=validation_evidence,
        job_id=job_id,
    )


def _granted_products(connection: Connection, *, app_user_id: int, action: Action) -> list[str]:
    grants = list_grants_for_user(connection, app_user_id=app_user_id)
    return [grant.product_key for grant in grants if can(grant.role, action)]


@router.get("/jobs", response_model=list[JobView])
def list_jobs(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> list[JobView]:
    """List processing jobs for products the caller may view — never others."""

    granted_products = _granted_products(connection, app_user_id=user.id, action=Action.VIEW)
    if not granted_products:
        return []

    rows = connection.execute(
        text(
            """
            SELECT id, product_key, status, attempt_count, created_at, error_summary
            FROM platform.processing_job
            WHERE product_key = ANY(:products)
            ORDER BY created_at DESC
            LIMIT 200
            """
        ),
        {"products": granted_products},
    ).all()

    return [
        JobView(
            id=row.id,
            product_key=row.product_key,
            status=row.status,
            attempt_count=row.attempt_count,
            created_at=row.created_at.isoformat(),
            error_summary=row.error_summary,
        )
        for row in rows
    ]


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobView,
    dependencies=[Depends(require_csrf)],
)
def retry_job(
    job_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> JobView:
    """Retry a failed job, granting one additional bounded attempt."""

    row = connection.execute(
        text(
            """
            SELECT id, product_key, status, attempt_count, max_attempts, created_at, error_summary
            FROM platform.processing_job
            WHERE id = :id
            """
        ),
        {"id": job_id},
    ).one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    role = get_product_role(connection, app_user_id=user.id, product_key=row.product_key)
    if role is None:
        # Ungranted product: 404, not 403 — never reveal a job exists for a
        # product the caller has no grant on.
        raise HTTPException(status_code=404, detail="Job not found.")
    if not can(role, Action.RETRY):
        raise HTTPException(status_code=403, detail="Not permitted for this product.")

    if row.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed jobs can be retried.")

    connection.execute(
        text(
            """
            UPDATE platform.processing_job
            SET status = 'queued', error_summary = NULL, max_attempts = max_attempts + 1
            WHERE id = :id
            """
        ),
        {"id": job_id},
    )
    record_audit_event(
        connection,
        actor_app_user_id=user.id,
        event_type="processing.retry_requested",
        product_key=row.product_key,
        subject_kind="processing_job",
        subject_id=str(job_id),
    )

    updated = connection.execute(
        text(
            """
            SELECT id, product_key, status, attempt_count, created_at, error_summary
            FROM platform.processing_job
            WHERE id = :id
            """
        ),
        {"id": job_id},
    ).one()

    return JobView(
        id=updated.id,
        product_key=updated.product_key,
        status=updated.status,
        attempt_count=updated.attempt_count,
        created_at=updated.created_at.isoformat(),
        error_summary=updated.error_summary,
    )


@router.get("/audit", response_model=list[AuditEventView])
def audit_log(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> list[AuditEventView]:
    """Admin-only cross-event audit trail, scoped to the caller's admin products.

    Never includes platform-level (product_key IS NULL) events: there is no
    platform-admin concept yet, so no caller is entitled to see those through
    this product-scoped endpoint.
    """

    grants = list_grants_for_user(connection, app_user_id=user.id)
    admin_products = [grant.product_key for grant in grants if grant.role is Role.ADMIN]

    if not admin_products:
        raise HTTPException(status_code=403, detail="Admin access required.")

    rows = connection.execute(
        text(
            """
            SELECT id, occurred_at, actor_app_user_id, event_type,
                   product_key, subject_kind, subject_id
            FROM platform.audit_event
            WHERE product_key = ANY(:products)
            ORDER BY occurred_at DESC
            LIMIT 200
            """
        ),
        {"products": admin_products},
    ).all()

    return [
        AuditEventView(
            id=row.id,
            occurred_at=row.occurred_at.isoformat(),
            actor_app_user_id=row.actor_app_user_id,
            event_type=row.event_type,
            product_key=row.product_key,
            subject_kind=row.subject_kind,
            subject_id=row.subject_id,
        )
        for row in rows
    ]
