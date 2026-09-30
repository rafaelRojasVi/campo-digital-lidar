"""Rodales upload → review → publish → restore, over HTTP.

Every route sits under ``/api/forestry`` behind the same router-level
``require_forestry_viewer`` as the read API (a session plus a ``forestry``
grant), and each adds its own action check:

- ``GET  /versions``: any forestry role. Viewers see only versions that
  have been published at some point; pending uploads are not theirs to see.
- ``GET  /snapshots/{id}/review``: ``Action.UPLOAD`` (operator, admin).
- ``POST /uploads``: ``Action.UPLOAD`` + CSRF. Stores a *pending* snapshot;
  never changes what the dashboard serves.
- ``POST /snapshots/{id}/publish`` and ``/restore``: ``Action.PUBLISH`` +
  CSRF. The only way the served snapshot changes.

The upload body is bounded before it is read
(``app.http_hardening.RequestBodyLimitMiddleware``, see ``app.main``), and
refused there without a live session.

Client-facing failures are Spanish and structural; technical detail goes to
the audit ledger and the log.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Connection, Engine

from app.access import Action, Role, can
from app.access_repository import AppUser
from app.audit import record_audit_event
from app.csrf import require_csrf
from app.database import get_database_engine
from app.deps import ensure_can, get_current_app_user, get_db_connection, get_object_store
from app.forestry_comparison import (
    ChangeItem,
    ComparisonUnavailableError,
    FeatureRef,
    SnapshotComparison,
    compare_snapshots,
)
from app.forestry_publication import (
    ActivationEventType,
    PublicationConflictError,
    SnapshotNotFoundError,
    activate_snapshot,
    read_published_snapshot_id,
)
from app.forestry_reads import snapshot_summary
from app.forestry_uploads import ForestryUploadRejectedError, accept_forestry_upload
from app.forestry_versions import (
    PublicationEventRecord,
    VersionRecord,
    list_invalid_geometries,
    list_publication_events,
    list_versions,
)
from app.object_store import ObjectStore
from app.routers.forestry import (
    FORESTRY_PRODUCT_KEY,
    ReadConnection,
    SnapshotIdPath,
    require_forestry_viewer,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/forestry",
    tags=["forestry"],
    dependencies=[Depends(require_forestry_viewer)],
)

# The observed Degenfeld ZIP is 2.6 MB; 50 MiB bounds one upload generously.
FORESTRY_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
FORESTRY_UPLOAD_PATH = "/api/forestry/uploads"
_UPLOAD_READ_CHUNK = 1024 * 1024
_MAX_FILENAME_LENGTH = 200

_VERSION_NOT_FOUND = "No se encontró la versión solicitada."
_UPLOAD_TOO_LARGE = (
    f"El archivo supera el máximo de {FORESTRY_MAX_UPLOAD_BYTES // (1024 * 1024)} MiB."
)
_NOT_A_ZIP_NAME = "Cargue la capa como un archivo .zip."
_UPLOAD_FAILED = "No se pudo registrar la carga. La versión publicada no cambió."
_PUBLISH_FAILED = "No se pudo completar la publicación. La versión publicada no cambió."
_REVIEW_NOT_ACKNOWLEDGED = (
    "Esta versión tiene geometrías inválidas o cambios que requieren revisión. Revíselos y "
    "confirme que desea publicarla. La versión publicada no cambió."
)
_CONFLICT_MESSAGES = {
    "review_not_acknowledged": _REVIEW_NOT_ACKNOWLEDGED,
    "stale_review": (
        "La versión publicada cambió mientras usted revisaba. Vuelva a abrir la revisión."
    ),
    "already_published": "Esta versión ya es la publicada.",
    "use_restore": "Esta versión ya fue publicada antes; use «Restaurar».",
    "not_previously_published": (
        "Sólo se puede restaurar una versión publicada anteriormente; use «Publicar»."
    ),
}


def require_forestry_grant(action: Action) -> Callable[..., Role]:
    """A dependency requiring a ``forestry`` grant permitting ``action``."""

    def dependency(
        user: Annotated[AppUser, Depends(get_current_app_user)],
        connection: Annotated[Connection, Depends(get_db_connection)],
    ) -> Role:
        return ensure_can(
            connection, app_user_id=user.id, product_key=FORESTRY_PRODUCT_KEY, action=action
        )

    return dependency


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UploadRecordModel(BaseModel):
    snapshot_upload_id: int
    original_filename: str
    byte_size: int
    content_sha256: str
    uploaded_at: datetime
    uploaded_by_display_name: str


class ImportedSourceModel(BaseModel):
    filename: str
    content_sha256: str
    byte_size: int
    observed_at: datetime


class VersionModel(BaseModel):
    """One snapshot as a version: status, source and headline numbers."""

    shapefile_snapshot_id: int
    status: Literal["published", "pending", "previously_published"]
    layer_name: str
    family_fingerprint: str
    crs_name: str | None
    storage_srid: int
    feature_count: int
    total_sup_ha: float
    total_geometry_area_source_units: float
    geometry_invalid_count: int
    created_at: datetime
    uploads: list[UploadRecordModel]
    imported_source: ImportedSourceModel | None


class PublicationEventModel(BaseModel):
    publication_event_id: int
    shapefile_snapshot_id: int
    event_type: Literal["initial", "publish", "restore"]
    previous_snapshot_id: int | None
    occurred_at: datetime
    actor_display_name: str | None


class VersionsResponse(BaseModel):
    published_snapshot_id: int | None
    versions: list[VersionModel]
    events: list[PublicationEventModel]


class FeatureRefModel(BaseModel):
    feature_ordinal: int
    source_objectid: int | None
    cod_predial: str | None
    nom_predio: str | None
    n_rodal: str | None
    sup_ha: float | None
    geometry_area_source_units: float


class OverlapModel(BaseModel):
    published_ordinal: int
    pending_ordinal: int
    overlap_ratio_of_smaller: float


class ChangeItemModel(BaseModel):
    kind: Literal["same_geometry", "geometry_changed", "uncertain", "added", "removed"]
    published: list[FeatureRefModel]
    pending: list[FeatureRefModel]
    changed_fields: list[str]
    overlaps: list[OverlapModel]
    same_objectid: bool | None


class ComparisonModel(BaseModel):
    """Changes from the published version; see ``app.forestry_comparison``."""

    published_snapshot_id: int
    link_overlap_ratio: float
    counts: dict[str, int]
    unchanged_count: int
    review_required_count: int
    items: list[ChangeItemModel]


class InvalidGeometryModel(BaseModel):
    feature_ordinal: int
    source_objectid: int | None
    cod_predial: str | None
    nom_predio: str | None
    n_rodal: str | None
    reason: str


class ReviewResponse(BaseModel):
    """Everything shown before «Publicar» or «Restaurar»."""

    version: VersionModel
    published_version: VersionModel | None
    quality_flag_counts: dict[str, int]
    invalid_geometries: list[InvalidGeometryModel]
    comparison: ComparisonModel | None
    comparison_unavailable: bool
    review_required: bool
    can_publish: bool
    can_restore: bool


class UploadResponse(BaseModel):
    status: Literal["uploaded", "already_uploaded"]
    shapefile_snapshot_id: int
    version_status: Literal["published", "pending", "previously_published"]
    layer_name: str
    feature_count: int
    content_sha256: str
    byte_size: int


class ActivationRequest(BaseModel):
    """What the reviewer saw: the published id at review time, and the acknowledgement."""

    expected_published_snapshot_id: int | None
    acknowledge_review: bool = False


class ActivationResponse(BaseModel):
    status: Literal["published", "restored"]
    shapefile_snapshot_id: int
    previous_snapshot_id: int | None
    publication_event_id: int
    occurred_at: datetime


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _version_model(record: VersionRecord) -> VersionModel:
    return VersionModel(
        shapefile_snapshot_id=record.shapefile_snapshot_id,
        status=record.status,
        layer_name=record.layer_name,
        family_fingerprint=record.family_fingerprint,
        crs_name=record.crs_name,
        storage_srid=record.storage_srid,
        feature_count=record.feature_count,
        total_sup_ha=record.total_sup_ha,
        total_geometry_area_source_units=record.total_geometry_area_source_units,
        geometry_invalid_count=record.geometry_invalid_count,
        created_at=record.created_at,
        uploads=[
            UploadRecordModel(
                snapshot_upload_id=upload.snapshot_upload_id,
                original_filename=upload.original_filename,
                byte_size=upload.byte_size,
                content_sha256=upload.content_sha256,
                uploaded_at=upload.uploaded_at,
                uploaded_by_display_name=upload.uploaded_by_display_name,
            )
            for upload in record.uploads
        ],
        imported_source=(
            None
            if record.imported_source is None
            else ImportedSourceModel(
                filename=record.imported_source.filename,
                content_sha256=record.imported_source.content_sha256,
                byte_size=record.imported_source.byte_size,
                observed_at=record.imported_source.observed_at,
            )
        ),
    )


def _event_model(record: PublicationEventRecord) -> PublicationEventModel:
    return PublicationEventModel(
        publication_event_id=record.publication_event_id,
        shapefile_snapshot_id=record.shapefile_snapshot_id,
        event_type=record.event_type,
        previous_snapshot_id=record.previous_snapshot_id,
        occurred_at=record.occurred_at,
        actor_display_name=record.actor_display_name,
    )


def _ref_model(ref: FeatureRef) -> FeatureRefModel:
    return FeatureRefModel(
        feature_ordinal=ref.feature_ordinal,
        source_objectid=ref.source_objectid,
        cod_predial=ref.cod_predial,
        nom_predio=ref.nom_predio,
        n_rodal=ref.n_rodal,
        sup_ha=ref.sup_ha,
        geometry_area_source_units=ref.geometry_area_source_units,
    )


def _item_model(item: ChangeItem) -> ChangeItemModel:
    return ChangeItemModel(
        kind=item.kind,
        published=[_ref_model(ref) for ref in item.published],
        pending=[_ref_model(ref) for ref in item.pending],
        changed_fields=list(item.changed_fields),
        overlaps=[
            OverlapModel(
                published_ordinal=overlap.published_ordinal,
                pending_ordinal=overlap.pending_ordinal,
                overlap_ratio_of_smaller=overlap.overlap_ratio_of_smaller,
            )
            for overlap in item.overlaps
        ],
        same_objectid=item.same_objectid,
    )


def _comparison_model(comparison: SnapshotComparison) -> ComparisonModel:
    return ComparisonModel(
        published_snapshot_id=comparison.published_snapshot_id,
        link_overlap_ratio=comparison.link_overlap_ratio,
        counts=comparison.counts,
        unchanged_count=comparison.unchanged_count,
        review_required_count=comparison.review_required_count,
        items=[_item_model(item) for item in comparison.items],
    )


def _single_version(connection: Connection, snapshot_id: int) -> VersionRecord:
    versions = list_versions(connection, include_pending=True, snapshot_id=snapshot_id)
    if not versions:
        raise HTTPException(status_code=404, detail=_VERSION_NOT_FOUND)
    return versions[0]


def _compare_with_published(
    connection: Connection, snapshot_id: int
) -> tuple[int | None, SnapshotComparison | None, bool]:
    """(published id, comparison or None, comparison_unavailable)."""

    published_id = read_published_snapshot_id(connection)
    if published_id is None or published_id == snapshot_id:
        return published_id, None, False
    try:
        return (
            published_id,
            compare_snapshots(connection, published_id=published_id, pending_id=snapshot_id),
            False,
        )
    except ComparisonUnavailableError:
        logger.warning(
            "Forestry comparison unavailable: pending=%s published=%s", snapshot_id, published_id
        )
        return published_id, None, True


def _review_required(
    version: VersionRecord, comparison: SnapshotComparison | None, unavailable: bool
) -> bool:
    return (
        version.geometry_invalid_count > 0
        or unavailable
        or (comparison is not None and comparison.review_required_count > 0)
    )


def _record_failure_audit(
    engine: Engine,
    *,
    actor_app_user_id: int,
    event_type: str,
    subject_kind: str,
    subject_id: str | None,
    metadata: dict[str, object],
) -> None:
    """Audit a refused mutation in its own transaction (the work one rolled back)."""

    try:
        with engine.begin() as audit_connection:
            record_audit_event(
                audit_connection,
                actor_app_user_id=actor_app_user_id,
                event_type=event_type,
                product_key=FORESTRY_PRODUCT_KEY,
                subject_kind=subject_kind,
                subject_id=subject_id,
                metadata=metadata,
            )
    except Exception:  # noqa: BLE001 - auditing a failure must not mask it
        logger.exception("Could not record %s audit event", event_type)


def _safe_filename(raw: str | None) -> str:
    """The client's filename as display data only: last path part, bounded."""

    name = PurePosixPath((raw or "").replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable()).strip()
    return name[:_MAX_FILENAME_LENGTH] or "archivo.zip"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get("/versions", response_model=VersionsResponse)
def get_versions(
    connection: ReadConnection,
    role: Annotated[Role, Depends(require_forestry_viewer)],
) -> VersionsResponse:
    """Every version with its source and status, plus the activation trail."""

    include_pending = can(role, Action.UPLOAD)
    versions = list_versions(connection, include_pending=include_pending)
    visible = frozenset(version.shapefile_snapshot_id for version in versions)
    return VersionsResponse(
        published_snapshot_id=read_published_snapshot_id(connection),
        versions=[_version_model(version) for version in versions],
        events=[
            _event_model(event)
            for event in list_publication_events(connection, visible_snapshot_ids=visible)
        ],
    )


@router.get(
    "/snapshots/{shapefile_snapshot_id}/review",
    response_model=ReviewResponse,
    dependencies=[Depends(require_forestry_grant(Action.UPLOAD))],
)
def get_review(
    shapefile_snapshot_id: SnapshotIdPath,
    connection: ReadConnection,
) -> ReviewResponse:
    """Source details, quality evidence and changes from the published version."""

    version = _single_version(connection, shapefile_snapshot_id)
    published_id, comparison, unavailable = _compare_with_published(
        connection, shapefile_snapshot_id
    )
    published_version = (
        None
        if published_id is None or published_id == shapefile_snapshot_id
        else _single_version(connection, published_id)
    )
    summary = snapshot_summary(connection, shapefile_snapshot_id)

    return ReviewResponse(
        version=_version_model(version),
        published_version=None if published_version is None else _version_model(published_version),
        quality_flag_counts={name: count for name, count in summary.quality_flag_counts.items()},
        invalid_geometries=[
            InvalidGeometryModel(
                feature_ordinal=record.feature_ordinal,
                source_objectid=record.source_objectid,
                cod_predial=record.cod_predial,
                nom_predio=record.nom_predio,
                n_rodal=record.n_rodal,
                reason=record.reason,
            )
            for record in list_invalid_geometries(connection, shapefile_snapshot_id)
        ],
        comparison=None if comparison is None else _comparison_model(comparison),
        comparison_unavailable=unavailable,
        review_required=_review_required(version, comparison, unavailable),
        can_publish=version.status == "pending",
        can_restore=version.status == "previously_published",
    )


# ---------------------------------------------------------------------------
# Mutations (OPERATOR/ADMIN, CSRF-protected)
# ---------------------------------------------------------------------------


@router.post(
    "/uploads",
    response_model=UploadResponse,
    dependencies=[Depends(require_csrf), Depends(require_forestry_grant(Action.UPLOAD))],
)
async def upload_shapefile_zip(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    file: Annotated[UploadFile, File()],
) -> UploadResponse | JSONResponse:
    """Store one shapefile ZIP as a pending version. Never publishes."""

    filename = _safe_filename(file.filename)
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail=_NOT_A_ZIP_NAME)

    temp_path = Path(tempfile.gettempdir()) / f"forestry-upload-{uuid.uuid4().hex}.zip"
    total_bytes = 0
    try:
        with temp_path.open("wb") as sink:
            while chunk := await file.read(_UPLOAD_READ_CHUNK):
                total_bytes += len(chunk)
                if total_bytes > FORESTRY_MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=_UPLOAD_TOO_LARGE)
                sink.write(chunk)

        try:
            with engine.begin() as connection:
                accepted = accept_forestry_upload(
                    connection,
                    zip_path=temp_path,
                    original_filename=filename,
                    store=store,
                    uploaded_by_app_user_id=user.id,
                )
                record_audit_event(
                    connection,
                    actor_app_user_id=user.id,
                    event_type="forestry.snapshot.uploaded",
                    product_key=FORESTRY_PRODUCT_KEY,
                    subject_kind="forestry_snapshot",
                    subject_id=str(accepted.shapefile_snapshot_id),
                    metadata={
                        "status": accepted.status,
                        "original_filename": filename,
                        "byte_size": accepted.byte_size,
                        "content_sha256": accepted.content_sha256,
                        "feature_count": accepted.feature_count,
                        "snapshot_upload_id": accepted.snapshot_upload_id,
                    },
                )
        except ForestryUploadRejectedError as error:
            _record_failure_audit(
                engine,
                actor_app_user_id=user.id,
                event_type="forestry.snapshot.upload_rejected",
                subject_kind="forestry_upload",
                subject_id=None,
                metadata={
                    "reason": error.reason,
                    "original_filename": filename,
                    "byte_size": total_bytes,
                },
            )
            return JSONResponse(
                status_code=409 if error.reason == "conflicting_layer" else 422,
                content={"detail": str(error), "reason": error.reason},
            )
        except Exception as error:
            logger.exception("Forestry upload failed")
            _record_failure_audit(
                engine,
                actor_app_user_id=user.id,
                event_type="forestry.snapshot.upload_rejected",
                subject_kind="forestry_upload",
                subject_id=None,
                metadata={"reason": "internal_error", "detail": type(error).__name__},
            )
            raise HTTPException(status_code=500, detail=_UPLOAD_FAILED) from error
    finally:
        temp_path.unlink(missing_ok=True)

    return UploadResponse(
        status=accepted.status,
        shapefile_snapshot_id=accepted.shapefile_snapshot_id,
        version_status=accepted.version_status,
        layer_name=accepted.layer_name,
        feature_count=accepted.feature_count,
        content_sha256=accepted.content_sha256,
        byte_size=accepted.byte_size,
    )


def _activate(
    shapefile_snapshot_id: int,
    request: ActivationRequest,
    *,
    user: AppUser,
    engine: Engine,
    event_type: ActivationEventType,
) -> ActivationResponse:
    audit_type = (
        "forestry.snapshot.published" if event_type == "publish" else ("forestry.snapshot.restored")
    )
    extra: dict[str, object] = {}

    try:
        if event_type == "publish":
            # The acknowledgement is checked against a fresh comparison, not
            # against whatever the reviewer's page computed earlier.
            with engine.connect() as read_connection:
                version = _single_version(read_connection, shapefile_snapshot_id)
                _, comparison, unavailable = _compare_with_published(
                    read_connection, shapefile_snapshot_id
                )
            required = _review_required(version, comparison, unavailable)
            if required and not request.acknowledge_review:
                raise PublicationConflictError(
                    "review_not_acknowledged", "The review was not acknowledged."
                )
            extra = {
                "review_required": required,
                "review_acknowledged": required and request.acknowledge_review,
                "geometry_invalid_count": version.geometry_invalid_count,
                "comparison_counts": None if comparison is None else comparison.counts,
            }

        with engine.begin() as connection:
            result = activate_snapshot(
                connection,
                shapefile_snapshot_id=shapefile_snapshot_id,
                actor_app_user_id=user.id,
                event_type=event_type,
                expected_published_snapshot_id=request.expected_published_snapshot_id,
            )
            record_audit_event(
                connection,
                actor_app_user_id=user.id,
                event_type=audit_type,
                product_key=FORESTRY_PRODUCT_KEY,
                subject_kind="forestry_snapshot",
                subject_id=str(shapefile_snapshot_id),
                metadata={
                    "previous_snapshot_id": result.previous_snapshot_id,
                    "publication_event_id": result.publication_event_id,
                    **extra,
                },
            )
    except HTTPException:
        raise
    except (SnapshotNotFoundError, PublicationConflictError) as error:
        reason = error.reason if isinstance(error, PublicationConflictError) else "not_found"
        _record_failure_audit(
            engine,
            actor_app_user_id=user.id,
            event_type="forestry.snapshot.publish_refused",
            subject_kind="forestry_snapshot",
            subject_id=str(shapefile_snapshot_id),
            metadata={"event_type": event_type, "reason": reason},
        )
        if isinstance(error, SnapshotNotFoundError):
            raise HTTPException(status_code=404, detail=_VERSION_NOT_FOUND) from error
        raise HTTPException(status_code=409, detail=_CONFLICT_MESSAGES[reason]) from error
    except Exception as error:
        logger.exception("Forestry %s failed for snapshot %s", event_type, shapefile_snapshot_id)
        _record_failure_audit(
            engine,
            actor_app_user_id=user.id,
            event_type="forestry.snapshot.publish_refused",
            subject_kind="forestry_snapshot",
            subject_id=str(shapefile_snapshot_id),
            metadata={"event_type": event_type, "reason": "internal_error"},
        )
        raise HTTPException(status_code=500, detail=_PUBLISH_FAILED) from error

    return ActivationResponse(
        status="published" if event_type == "publish" else "restored",
        shapefile_snapshot_id=result.shapefile_snapshot_id,
        previous_snapshot_id=result.previous_snapshot_id,
        publication_event_id=result.publication_event_id,
        occurred_at=result.occurred_at,
    )


@router.post(
    "/snapshots/{shapefile_snapshot_id}/publish",
    response_model=ActivationResponse,
    dependencies=[Depends(require_csrf), Depends(require_forestry_grant(Action.PUBLISH))],
)
def publish_snapshot(
    shapefile_snapshot_id: SnapshotIdPath,
    request: ActivationRequest,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> ActivationResponse:
    """«Publicar»: make a pending version the one every viewer sees."""

    return _activate(shapefile_snapshot_id, request, user=user, engine=engine, event_type="publish")


@router.post(
    "/snapshots/{shapefile_snapshot_id}/restore",
    response_model=ActivationResponse,
    dependencies=[Depends(require_csrf), Depends(require_forestry_grant(Action.PUBLISH))],
)
def restore_snapshot(
    shapefile_snapshot_id: SnapshotIdPath,
    request: ActivationRequest,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> ActivationResponse:
    """«Restaurar»: make a previously published version the one viewers see again."""

    return _activate(shapefile_snapshot_id, request, user=user, engine=engine, event_type="restore")
