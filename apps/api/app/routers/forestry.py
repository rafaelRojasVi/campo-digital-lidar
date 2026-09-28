"""Read-only Forestry HTTP projection over the persisted source substrate.

Every endpoint is a factual, snapshot-scoped projection of persisted source
evidence (`app.forestry_reads`). Nothing here establishes canonical predio or
rodal identity, cross-snapshot feature identity, workflow status, approval,
progress, or authoritative current state; year-stamped comparisons are
literal source-field differences and quality flags are data-quality
evidence, never business status. There are no mutation endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_database_engine
from app.forestry_reads import (
    ChangeFilter,
    ForestrySnapshotRecord,
    SourceFeatureFilters,
    SourceFeatureRecord,
    UseFieldChange,
    get_snapshot_record,
    get_source_feature,
    latest_ingested_snapshot,
    list_feature_geometries,
    list_shapefile_snapshots,
    list_source_features,
    predio_distribution,
    snapshot_summary,
    use_distribution,
    use_field_comparison,
)

router = APIRouter(
    prefix="/api/forestry",
    tags=["forestry"],
)

COMPARISON_SEMANTICS = (
    "literal source-field differences within one snapshot; not workflow transitions"
)

# Established quality-evidence vocabulary (kept in sync with
# forestry_ingestion.snapshot_evidence; guarded by a unit test).
QualityFlag = Literal[
    "blank_rodal",
    "duplicate_geometry",
    "duplicate_predio_rodal_key",
    "invalid_geometry",
    "predio_code_name_anomaly",
    "truncated_use_code_2026",
]

SnapshotIdPath = Annotated[int, Path(ge=1)]
FeatureOrdinalPath = Annotated[int, Path(ge=1)]


def get_forestry_read_connection(
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> Iterator[Connection]:
    """Yield a read connection, mapping database unavailability to 503."""

    try:
        with engine.connect() as connection:
            yield connection
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        ) from exc


ReadConnection = Annotated[Connection, Depends(get_forestry_read_connection)]


class ForestrySnapshotModel(BaseModel):
    """One persisted Forestry snapshot, as listed (ingestion order)."""

    shapefile_snapshot_id: int
    layer_name: str
    family_fingerprint: str
    storage_srid: int
    feature_count: int
    created_at: datetime


class ForestrySnapshotSummaryModel(BaseModel):
    """Factual per-snapshot aggregates, including quality evidence."""

    shapefile_snapshot_id: int
    layer_name: str
    family_fingerprint: str
    storage_srid: int
    bbox: tuple[float, float, float, float]
    feature_count: int
    total_geometry_area_source_units: float
    total_sup_ha: float
    geometry_valid_count: int
    geometry_invalid_count: int
    quality_flag_counts: dict[str, int]
    n_rodal_te_non_blank_count: int
    created_at: datetime


class PredioDistributionModel(BaseModel):
    """Feature count and area sums for one source predio code/name pair."""

    cod_predial: str | None
    nom_predio: str | None
    feature_count: int
    sup_ha_total: float
    geometry_area_total: float


class UseDistributionEntryModel(BaseModel):
    """Feature count and area sums for one source use-class value."""

    value: str | None
    feature_count: int
    sup_ha_total: float
    geometry_area_total: float


class UseDistributionModel(BaseModel):
    """Distribution of one year-stamped source use-class column."""

    shapefile_snapshot_id: int
    field: Literal["uso_2024", "uso_2026"]
    entries: list[UseDistributionEntryModel]


class SourceFieldChangeModel(BaseModel):
    """One literal source-field difference within a snapshot."""

    feature_ordinal: int
    source_objectid: int | None
    before: str | None
    after: str | None


class SourceFieldComparisonSideModel(BaseModel):
    """All literal differences of one source-column pair."""

    changed_feature_count: int
    changes: list[SourceFieldChangeModel]


class SourceFieldComparisonModel(BaseModel):
    """Literal `Uso2024 vs Uso2026` / `Cod_Uso vs CodUso_2026` differences."""

    shapefile_snapshot_id: int
    semantics: str
    uso_2024_vs_uso_2026: SourceFieldComparisonSideModel
    cod_uso_vs_cod_uso_2026: SourceFieldComparisonSideModel


class SourceFeatureModel(BaseModel):
    """One snapshot-local source feature as listed (no geometry payload)."""

    feature_ordinal: int
    source_objectid: int | None
    cod_predial: str | None
    nom_predio: str | None
    n_rodal: str | None
    cod_uso: str | None
    uso_2024: str | None
    desc_uso: str | None
    uso_2026: str | None
    cod_uso_2026: str | None
    sup_ha: float | None
    geometry_is_valid: bool
    geometry_area_source_units: float
    quality_flags: list[str]


class SourceFeaturePageModel(BaseModel):
    """One deterministic page of the snapshot-local feature listing."""

    shapefile_snapshot_id: int
    total_count: int
    limit: int
    offset: int
    features: list[SourceFeatureModel]


class GeoJsonMultiPolygonModel(BaseModel):
    """GeoJSON-encoded stored MultiPolygon in source CRS coordinates."""

    type: Literal["MultiPolygon"]
    coordinates: list[list[list[list[float]]]]


class SourceFeatureDetailModel(SourceFeatureModel):
    """One source feature with its full attribute row and geometry."""

    shapefile_snapshot_id: int
    storage_srid: int
    shape_area: float | None
    geometry_invalid_reason: str | None
    source_attributes: dict[str, Any]
    geometry: GeoJsonMultiPolygonModel


class GeoFeatureModel(BaseModel):
    """GeoJSON-shaped feature; coordinates stay in the source CRS."""

    type: Literal["Feature"]
    properties: SourceFeatureModel
    geometry: GeoJsonMultiPolygonModel


class FeatureCollectionModel(BaseModel):
    """GeoJSON-shaped collection with explicit source-CRS declaration.

    Coordinates are the stored source geometry (EPSG `storage_srid`), not the
    WGS84 lon/lat that RFC 7946 assumes; `storage_srid` is included so
    clients must not misread the coordinates as lon/lat.
    """

    type: Literal["FeatureCollection"]
    shapefile_snapshot_id: int
    storage_srid: int
    feature_count: int
    features: list[GeoFeatureModel]


def feature_filter_query(
    cod_predial: str | None = None,
    nom_predio: str | None = None,
    n_rodal: str | None = None,
    cod_uso: str | None = None,
    uso_2024: str | None = None,
    desc_uso: str | None = None,
    uso_2026: str | None = None,
    cod_uso_2026: str | None = None,
    quality_flag: QualityFlag | None = None,
    geometry_valid: bool | None = None,
    uso_2024_vs_uso_2026: ChangeFilter | None = None,
    cod_uso_vs_cod_uso_2026: ChangeFilter | None = None,
) -> SourceFeatureFilters:
    """Literal source-field filters shared by the feature endpoints."""

    return SourceFeatureFilters(
        cod_predial=cod_predial,
        nom_predio=nom_predio,
        n_rodal=n_rodal,
        cod_uso=cod_uso,
        uso_2024=uso_2024,
        desc_uso=desc_uso,
        uso_2026=uso_2026,
        cod_uso_2026=cod_uso_2026,
        quality_flag=quality_flag,
        geometry_valid=geometry_valid,
        uso_2024_vs_uso_2026=uso_2024_vs_uso_2026,
        cod_uso_vs_cod_uso_2026=cod_uso_vs_cod_uso_2026,
    )


FeatureFilters = Annotated[SourceFeatureFilters, Depends(feature_filter_query)]


def _snapshot_model(record: ForestrySnapshotRecord) -> ForestrySnapshotModel:
    return ForestrySnapshotModel(
        shapefile_snapshot_id=record.shapefile_snapshot_id,
        layer_name=record.layer_name,
        family_fingerprint=record.family_fingerprint,
        storage_srid=record.storage_srid,
        feature_count=record.feature_count,
        created_at=record.created_at,
    )


def _snapshot_or_404(
    connection: Connection,
    shapefile_snapshot_id: int,
) -> ForestrySnapshotRecord:
    record = get_snapshot_record(connection, shapefile_snapshot_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"forestry snapshot {shapefile_snapshot_id} is not persisted",
        )

    return record


def _feature_model(record: SourceFeatureRecord) -> SourceFeatureModel:
    return SourceFeatureModel(
        feature_ordinal=record.feature_ordinal,
        source_objectid=record.source_objectid,
        cod_predial=record.cod_predial,
        nom_predio=record.nom_predio,
        n_rodal=record.n_rodal,
        cod_uso=record.cod_uso,
        uso_2024=record.uso_2024,
        desc_uso=record.desc_uso,
        uso_2026=record.uso_2026,
        cod_uso_2026=record.cod_uso_2026,
        sup_ha=record.sup_ha,
        geometry_is_valid=record.geometry_is_valid,
        geometry_area_source_units=record.geometry_area_source_units,
        quality_flags=list(record.quality_flags),
    )


def _geometry_model(geometry_geojson: str) -> GeoJsonMultiPolygonModel:
    return GeoJsonMultiPolygonModel.model_validate(json.loads(geometry_geojson))


def _comparison_side(
    changes: tuple[UseFieldChange, ...],
) -> SourceFieldComparisonSideModel:
    return SourceFieldComparisonSideModel(
        changed_feature_count=len(changes),
        changes=[
            SourceFieldChangeModel(
                feature_ordinal=change.feature_ordinal,
                source_objectid=change.source_objectid,
                before=change.before,
                after=change.after,
            )
            for change in changes
        ],
    )


@router.get(
    "/snapshots",
    response_model=list[ForestrySnapshotModel],
)
def list_snapshots(connection: ReadConnection) -> list[ForestrySnapshotModel]:
    """List persisted Forestry snapshots in ingestion order."""

    return [_snapshot_model(record) for record in list_shapefile_snapshots(connection)]


@router.get(
    "/snapshots/latest-ingested",
    response_model=ForestrySnapshotModel,
)
def get_latest_ingested_snapshot(connection: ReadConnection) -> ForestrySnapshotModel:
    """Return the most recently ingested snapshot (ingestion order only).

    This is a fact about ingestion order, not an authoritative current
    forest state: supersession semantics are not established.
    """

    record = latest_ingested_snapshot(connection)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="no forestry snapshot is persisted",
        )

    return _snapshot_model(record)


@router.get(
    "/snapshots/{shapefile_snapshot_id}",
    response_model=ForestrySnapshotSummaryModel,
)
def get_snapshot_summary(
    shapefile_snapshot_id: SnapshotIdPath,
    connection: ReadConnection,
) -> ForestrySnapshotSummaryModel:
    """Aggregate persisted evidence for one snapshot, quality flags included."""

    _snapshot_or_404(connection, shapefile_snapshot_id)

    summary = snapshot_summary(connection, shapefile_snapshot_id)

    return ForestrySnapshotSummaryModel(
        shapefile_snapshot_id=summary.shapefile_snapshot_id,
        layer_name=summary.layer_name,
        family_fingerprint=summary.family_fingerprint,
        storage_srid=summary.storage_srid,
        bbox=summary.bbox,
        feature_count=summary.feature_count,
        total_geometry_area_source_units=summary.total_geometry_area_source_units,
        total_sup_ha=summary.total_sup_ha,
        geometry_valid_count=summary.geometry_valid_count,
        geometry_invalid_count=summary.geometry_invalid_count,
        quality_flag_counts=summary.quality_flag_counts,
        n_rodal_te_non_blank_count=summary.n_rodal_te_non_blank_count,
        created_at=summary.created_at,
    )


@router.get(
    "/snapshots/{shapefile_snapshot_id}/predio-distribution",
    response_model=list[PredioDistributionModel],
)
def get_predio_distribution(
    shapefile_snapshot_id: SnapshotIdPath,
    connection: ReadConnection,
) -> list[PredioDistributionModel]:
    """Source predio code/name pairs with counts and area sums.

    Pairs are source values, not canonical predios; anomalous code/name
    pairs appear as their own rows.
    """

    _snapshot_or_404(connection, shapefile_snapshot_id)

    return [
        PredioDistributionModel(
            cod_predial=entry.cod_predial,
            nom_predio=entry.nom_predio,
            feature_count=entry.feature_count,
            sup_ha_total=entry.sup_ha_total,
            geometry_area_total=entry.geometry_area_total,
        )
        for entry in predio_distribution(connection, shapefile_snapshot_id)
    ]


@router.get(
    "/snapshots/{shapefile_snapshot_id}/use-distribution",
    response_model=UseDistributionModel,
)
def get_use_distribution(
    shapefile_snapshot_id: SnapshotIdPath,
    connection: ReadConnection,
    field: Annotated[Literal["uso_2024", "uso_2026"], Query()],
) -> UseDistributionModel:
    """Distribution of one year-stamped source use-class column."""

    _snapshot_or_404(connection, shapefile_snapshot_id)

    entries = use_distribution(connection, shapefile_snapshot_id, field=field)

    return UseDistributionModel(
        shapefile_snapshot_id=shapefile_snapshot_id,
        field=field,
        entries=[
            UseDistributionEntryModel(
                value=entry.value,
                feature_count=entry.feature_count,
                sup_ha_total=entry.sup_ha_total,
                geometry_area_total=entry.geometry_area_total,
            )
            for entry in entries
        ],
    )


@router.get(
    "/snapshots/{shapefile_snapshot_id}/source-field-comparison",
    response_model=SourceFieldComparisonModel,
)
def get_source_field_comparison(
    shapefile_snapshot_id: SnapshotIdPath,
    connection: ReadConnection,
) -> SourceFieldComparisonModel:
    """Literal `Uso2024 vs Uso2026` / `Cod_Uso vs CodUso_2026` differences.

    These are source-field differences within one snapshot; they are not
    workflow transitions, approvals, or progress.
    """

    _snapshot_or_404(connection, shapefile_snapshot_id)

    comparison = use_field_comparison(connection, shapefile_snapshot_id)

    return SourceFieldComparisonModel(
        shapefile_snapshot_id=shapefile_snapshot_id,
        semantics=COMPARISON_SEMANTICS,
        uso_2024_vs_uso_2026=_comparison_side(comparison.uso_2024_vs_uso_2026),
        cod_uso_vs_cod_uso_2026=_comparison_side(comparison.cod_uso_vs_cod_uso_2026),
    )


@router.get(
    "/snapshots/{shapefile_snapshot_id}/features",
    response_model=SourceFeaturePageModel,
)
def list_features(
    shapefile_snapshot_id: SnapshotIdPath,
    connection: ReadConnection,
    filters: FeatureFilters,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourceFeaturePageModel:
    """Paginated snapshot-local feature listing in feature-ordinal order."""

    _snapshot_or_404(connection, shapefile_snapshot_id)

    page = list_source_features(
        connection,
        shapefile_snapshot_id,
        filters=filters,
        limit=limit,
        offset=offset,
    )

    return SourceFeaturePageModel(
        shapefile_snapshot_id=shapefile_snapshot_id,
        total_count=page.total_count,
        limit=page.limit,
        offset=page.offset,
        features=[_feature_model(record) for record in page.features],
    )


@router.get(
    "/snapshots/{shapefile_snapshot_id}/features/{feature_ordinal}",
    response_model=SourceFeatureDetailModel,
)
def get_feature_detail(
    shapefile_snapshot_id: SnapshotIdPath,
    feature_ordinal: FeatureOrdinalPath,
    connection: ReadConnection,
) -> SourceFeatureDetailModel:
    """One source feature: full attribute row, validity evidence, geometry."""

    snapshot = _snapshot_or_404(connection, shapefile_snapshot_id)

    detail = get_source_feature(connection, shapefile_snapshot_id, feature_ordinal)

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"source feature {feature_ordinal} does not exist "
                f"in forestry snapshot {shapefile_snapshot_id}"
            ),
        )

    return SourceFeatureDetailModel(
        **_feature_model(detail.record).model_dump(),
        shapefile_snapshot_id=shapefile_snapshot_id,
        storage_srid=snapshot.storage_srid,
        shape_area=detail.shape_area,
        geometry_invalid_reason=detail.geometry_invalid_reason,
        source_attributes=detail.source_attributes,
        geometry=_geometry_model(detail.geometry_geojson),
    )


@router.get(
    "/snapshots/{shapefile_snapshot_id}/feature-collection",
    response_model=FeatureCollectionModel,
)
def get_feature_collection(
    shapefile_snapshot_id: SnapshotIdPath,
    connection: ReadConnection,
    filters: FeatureFilters,
) -> FeatureCollectionModel:
    """GeoJSON-shaped collection of the filtered snapshot-local features.

    Coordinates are served exactly as stored in the source CRS
    (`storage_srid`); invalid source geometries are included and labeled,
    never repaired.
    """

    snapshot = _snapshot_or_404(connection, shapefile_snapshot_id)

    records = list_feature_geometries(
        connection,
        shapefile_snapshot_id,
        filters=filters,
    )

    return FeatureCollectionModel(
        type="FeatureCollection",
        shapefile_snapshot_id=shapefile_snapshot_id,
        storage_srid=snapshot.storage_srid,
        feature_count=len(records),
        features=[
            GeoFeatureModel(
                type="Feature",
                properties=_feature_model(record.record),
                geometry=_geometry_model(record.geometry_geojson),
            )
            for record in records
        ],
    )
