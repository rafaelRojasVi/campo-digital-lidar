"""Read projections over the persisted Forestry source substrate.

Every projection is snapshot-scoped arithmetic over persisted source values.
None of these results is a business conclusion: use-field differences are
literal comparisons of the source columns (`Uso2024` vs `Uso2026`,
`Cod_Uso` vs `CodUso_2026`), never "progress", "approved change", or any
workflow semantics, and quality-flag counts are data-quality evidence, not
status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import Connection, Row, text

from app.forestry_persistence import ForestryIngestionError
from forestry_ingestion.snapshot_evidence import (
    FLAG_BLANK_RODAL,
    FLAG_DUPLICATE_GEOMETRY,
    FLAG_DUPLICATE_PREDIO_RODAL_KEY,
    FLAG_INVALID_GEOMETRY,
    FLAG_PREDIO_CODE_NAME_ANOMALY,
    FLAG_TRUNCATED_USE_CODE_2026,
)

UseField = Literal["uso_2024", "uso_2026"]
ChangeFilter = Literal["changed", "unchanged"]

KNOWN_QUALITY_FLAGS: frozenset[str] = frozenset(
    {
        FLAG_BLANK_RODAL,
        FLAG_DUPLICATE_GEOMETRY,
        FLAG_DUPLICATE_PREDIO_RODAL_KEY,
        FLAG_INVALID_GEOMETRY,
        FLAG_PREDIO_CODE_NAME_ANOMALY,
        FLAG_TRUNCATED_USE_CODE_2026,
    }
)

_USE_FIELD_COLUMNS: dict[str, str] = {
    "uso_2024": "uso_2024",
    "uso_2026": "uso_2026",
}

# Source columns filterable by literal equality; keys are filter field names.
_EQUALITY_FILTER_COLUMNS: dict[str, str] = {
    "cod_predial": "cod_predial",
    "nom_predio": "nom_predio",
    "n_rodal": "n_rodal",
    "cod_uso": "cod_uso",
    "uso_2024": "uso_2024",
    "desc_uso": "desc_uso",
    "uso_2026": "uso_2026",
    "cod_uso_2026": "cod_uso_2026",
}

# Literal source-field comparisons filterable as changed/unchanged.
_CHANGE_FILTER_COLUMNS: dict[str, tuple[str, str]] = {
    "uso_2024_vs_uso_2026": ("uso_2024", "uso_2026"),
    "cod_uso_vs_cod_uso_2026": ("cod_uso", "cod_uso_2026"),
}


@dataclass(frozen=True, slots=True)
class ForestrySnapshotRecord:
    """One persisted Forestry snapshot, as listed."""

    shapefile_snapshot_id: int
    layer_name: str
    family_fingerprint: str
    storage_srid: int
    feature_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ForestrySnapshotSummary:
    """Factual per-snapshot aggregates over persisted source evidence."""

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


@dataclass(frozen=True, slots=True)
class PredioDistributionEntry:
    """Feature count and area sums for one source predio code/name pair."""

    cod_predial: str | None
    nom_predio: str | None
    feature_count: int
    sup_ha_total: float
    geometry_area_total: float


@dataclass(frozen=True, slots=True)
class UseDistributionEntry:
    """Feature count and area sums for one source use-class value."""

    value: str | None
    feature_count: int
    sup_ha_total: float
    geometry_area_total: float


@dataclass(frozen=True, slots=True)
class UseFieldChange:
    """One literal source-field difference within a snapshot."""

    feature_ordinal: int
    source_objectid: int | None
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class UseFieldComparison:
    """Literal differences between year-stamped source columns."""

    uso_2024_vs_uso_2026: tuple[UseFieldChange, ...]
    cod_uso_vs_cod_uso_2026: tuple[UseFieldChange, ...]


_SNAPSHOT_RECORD_COLUMNS = """
    id, layer_name, family_fingerprint, storage_srid, feature_count, created_at
"""


def _snapshot_record(row: Row[Any]) -> ForestrySnapshotRecord:
    return ForestrySnapshotRecord(
        shapefile_snapshot_id=int(row.id),
        layer_name=row.layer_name,
        family_fingerprint=row.family_fingerprint,
        storage_srid=int(row.storage_srid),
        feature_count=int(row.feature_count),
        created_at=row.created_at,
    )


def list_shapefile_snapshots(
    connection: Connection,
) -> tuple[ForestrySnapshotRecord, ...]:
    """List persisted Forestry snapshots in ingestion order."""

    rows = connection.execute(
        text(
            f"""
            SELECT {_SNAPSHOT_RECORD_COLUMNS}
            FROM forestry.shapefile_snapshot
            ORDER BY id
            """
        )
    ).all()

    return tuple(_snapshot_record(row) for row in rows)


def get_snapshot_record(
    connection: Connection,
    shapefile_snapshot_id: int,
) -> ForestrySnapshotRecord | None:
    """Return one persisted snapshot record, or None when not persisted."""

    row = connection.execute(
        text(
            f"""
            SELECT {_SNAPSHOT_RECORD_COLUMNS}
            FROM forestry.shapefile_snapshot
            WHERE id = :snapshot_id
            """
        ),
        {"snapshot_id": shapefile_snapshot_id},
    ).one_or_none()

    return None if row is None else _snapshot_record(row)


def latest_ingested_snapshot(
    connection: Connection,
) -> ForestrySnapshotRecord | None:
    """Return the most recently ingested snapshot (ingestion order).

    "Latest ingested" is a deterministic fact about ingestion order only; it
    carries no authoritative current-state or supersession semantics, which
    remain unestablished.
    """

    row = connection.execute(
        text(
            f"""
            SELECT {_SNAPSHOT_RECORD_COLUMNS}
            FROM forestry.shapefile_snapshot
            ORDER BY id DESC
            LIMIT 1
            """
        )
    ).one_or_none()

    return None if row is None else _snapshot_record(row)


def snapshot_summary(
    connection: Connection,
    shapefile_snapshot_id: int,
) -> ForestrySnapshotSummary:
    """Aggregate persisted evidence for one snapshot."""

    snapshot = connection.execute(
        text(
            """
            SELECT
                id,
                layer_name,
                family_fingerprint,
                storage_srid,
                bbox_x_min,
                bbox_y_min,
                bbox_x_max,
                bbox_y_max,
                created_at
            FROM forestry.shapefile_snapshot
            WHERE id = :snapshot_id
            """
        ),
        {"snapshot_id": shapefile_snapshot_id},
    ).one_or_none()

    if snapshot is None:
        raise ForestryIngestionError(f"Forestry snapshot {shapefile_snapshot_id} does not exist")

    aggregates = connection.execute(
        text(
            """
            SELECT
                count(*) AS feature_count,
                COALESCE(SUM(geometry_area_source_units), 0) AS total_geometry_area,
                COALESCE(SUM(sup_ha), 0) AS total_sup_ha,
                count(*) FILTER (WHERE geometry_is_valid) AS valid_count,
                count(*) FILTER (WHERE NOT geometry_is_valid) AS invalid_count,
                count(*) FILTER (
                    WHERE source_attributes ->> 'n_rodal_te' IS NOT NULL
                ) AS n_rodal_te_non_blank_count
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            """
        ),
        {"snapshot_id": shapefile_snapshot_id},
    ).one()

    flag_rows = connection.execute(
        text(
            """
            SELECT flag, count(*) AS flag_count
            FROM forestry.source_feature,
                 unnest(quality_flags) AS flag
            WHERE shapefile_snapshot_id = :snapshot_id
            GROUP BY flag
            ORDER BY flag
            """
        ),
        {"snapshot_id": shapefile_snapshot_id},
    ).all()

    return ForestrySnapshotSummary(
        shapefile_snapshot_id=int(snapshot.id),
        layer_name=snapshot.layer_name,
        family_fingerprint=snapshot.family_fingerprint,
        storage_srid=int(snapshot.storage_srid),
        bbox=(
            float(snapshot.bbox_x_min),
            float(snapshot.bbox_y_min),
            float(snapshot.bbox_x_max),
            float(snapshot.bbox_y_max),
        ),
        feature_count=int(aggregates.feature_count),
        total_geometry_area_source_units=float(aggregates.total_geometry_area),
        total_sup_ha=float(aggregates.total_sup_ha),
        geometry_valid_count=int(aggregates.valid_count),
        geometry_invalid_count=int(aggregates.invalid_count),
        quality_flag_counts={row.flag: int(row.flag_count) for row in flag_rows},
        n_rodal_te_non_blank_count=int(aggregates.n_rodal_te_non_blank_count),
        created_at=snapshot.created_at,
    )


def predio_distribution(
    connection: Connection,
    shapefile_snapshot_id: int,
) -> tuple[PredioDistributionEntry, ...]:
    """Source predio code/name values with feature counts and area sums."""

    rows = connection.execute(
        text(
            """
            SELECT
                cod_predial,
                nom_predio,
                count(*) AS feature_count,
                COALESCE(SUM(sup_ha), 0) AS sup_ha_total,
                COALESCE(SUM(geometry_area_source_units), 0) AS geometry_area_total
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            GROUP BY cod_predial, nom_predio
            ORDER BY cod_predial NULLS LAST, nom_predio NULLS LAST
            """
        ),
        {"snapshot_id": shapefile_snapshot_id},
    ).all()

    return tuple(
        PredioDistributionEntry(
            cod_predial=row.cod_predial,
            nom_predio=row.nom_predio,
            feature_count=int(row.feature_count),
            sup_ha_total=float(row.sup_ha_total),
            geometry_area_total=float(row.geometry_area_total),
        )
        for row in rows
    )


def use_distribution(
    connection: Connection,
    shapefile_snapshot_id: int,
    *,
    field: UseField,
) -> tuple[UseDistributionEntry, ...]:
    """Distribution of one year-stamped source use-class column."""

    column = _USE_FIELD_COLUMNS.get(field)

    if column is None:
        raise ForestryIngestionError(f"Unsupported use field: {field!r}")

    rows = connection.execute(
        text(
            f"""
            SELECT
                {column} AS value,
                count(*) AS feature_count,
                COALESCE(SUM(sup_ha), 0) AS sup_ha_total,
                COALESCE(SUM(geometry_area_source_units), 0) AS geometry_area_total
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            GROUP BY {column}
            ORDER BY feature_count DESC, value NULLS LAST
            """
        ),
        {"snapshot_id": shapefile_snapshot_id},
    ).all()

    return tuple(
        UseDistributionEntry(
            value=row.value,
            feature_count=int(row.feature_count),
            sup_ha_total=float(row.sup_ha_total),
            geometry_area_total=float(row.geometry_area_total),
        )
        for row in rows
    )


def use_field_comparison(
    connection: Connection,
    shapefile_snapshot_id: int,
) -> UseFieldComparison:
    """Literal snapshot-internal differences between year-stamped source columns.

    The result compares source fields only (`Uso2024` vs `Uso2026`,
    `Cod_Uso` vs `CodUso_2026`). The semantics of individual code values are
    partially unconfirmed; these differences carry no workflow meaning.
    """

    return UseFieldComparison(
        uso_2024_vs_uso_2026=_field_differences(
            connection,
            shapefile_snapshot_id,
            before_column="uso_2024",
            after_column="uso_2026",
        ),
        cod_uso_vs_cod_uso_2026=_field_differences(
            connection,
            shapefile_snapshot_id,
            before_column="cod_uso",
            after_column="cod_uso_2026",
        ),
    )


@dataclass(frozen=True, slots=True)
class SourceFeatureFilters:
    """Deterministic snapshot-local filters over persisted source fields.

    Every filter is a literal condition on stored source values: equality on
    a source column, membership in the persisted quality-flag evidence,
    stored geometry validity, or a literal changed/unchanged comparison of
    the year-stamped source columns. No filter carries business semantics.
    """

    cod_predial: str | None = None
    nom_predio: str | None = None
    n_rodal: str | None = None
    cod_uso: str | None = None
    uso_2024: str | None = None
    desc_uso: str | None = None
    uso_2026: str | None = None
    cod_uso_2026: str | None = None
    quality_flag: str | None = None
    geometry_valid: bool | None = None
    uso_2024_vs_uso_2026: ChangeFilter | None = None
    cod_uso_vs_cod_uso_2026: ChangeFilter | None = None


@dataclass(frozen=True, slots=True)
class SourceFeatureRecord:
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
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceFeaturePage:
    """One deterministic page of the snapshot-local feature listing."""

    total_count: int
    limit: int
    offset: int
    features: tuple[SourceFeatureRecord, ...]


@dataclass(frozen=True, slots=True)
class SourceFeatureDetail:
    """One source feature with its full attribute row and geometry."""

    record: SourceFeatureRecord
    shape_area: float | None
    geometry_invalid_reason: str | None
    source_attributes: dict[str, Any]
    geometry_geojson: str


@dataclass(frozen=True, slots=True)
class FeatureGeometryRecord:
    """Listing fields plus faithful GeoJSON-encoded stored geometry."""

    record: SourceFeatureRecord
    geometry_geojson: str


_FEATURE_RECORD_COLUMNS = """
    feature_ordinal,
    source_objectid,
    cod_predial,
    nom_predio,
    n_rodal,
    cod_uso,
    uso_2024,
    desc_uso,
    uso_2026,
    cod_uso_2026,
    sup_ha,
    geometry_is_valid,
    geometry_area_source_units,
    quality_flags
"""


def _feature_record(row: Row[Any]) -> SourceFeatureRecord:
    return SourceFeatureRecord(
        feature_ordinal=int(row.feature_ordinal),
        source_objectid=(None if row.source_objectid is None else int(row.source_objectid)),
        cod_predial=row.cod_predial,
        nom_predio=row.nom_predio,
        n_rodal=row.n_rodal,
        cod_uso=row.cod_uso,
        uso_2024=row.uso_2024,
        desc_uso=row.desc_uso,
        uso_2026=row.uso_2026,
        cod_uso_2026=row.cod_uso_2026,
        sup_ha=(None if row.sup_ha is None else float(row.sup_ha)),
        geometry_is_valid=bool(row.geometry_is_valid),
        geometry_area_source_units=float(row.geometry_area_source_units),
        quality_flags=tuple(row.quality_flags),
    )


def _filter_conditions(
    filters: SourceFeatureFilters,
) -> tuple[str, dict[str, object]]:
    """Build whitelisted SQL conditions and binds for the feature filters."""

    conditions: list[str] = []
    binds: dict[str, object] = {}

    for field_name, column in _EQUALITY_FILTER_COLUMNS.items():
        value = getattr(filters, field_name)

        if value is not None:
            conditions.append(f"{column} = :filter_{field_name}")
            binds[f"filter_{field_name}"] = value

    if filters.quality_flag is not None:
        if filters.quality_flag not in KNOWN_QUALITY_FLAGS:
            raise ForestryIngestionError(f"Unsupported quality flag: {filters.quality_flag!r}")

        conditions.append(":filter_quality_flag = ANY(quality_flags)")
        binds["filter_quality_flag"] = filters.quality_flag

    if filters.geometry_valid is not None:
        conditions.append("geometry_is_valid = :filter_geometry_valid")
        binds["filter_geometry_valid"] = filters.geometry_valid

    for field_name, (before_column, after_column) in _CHANGE_FILTER_COLUMNS.items():
        value = getattr(filters, field_name)

        if value is None:
            continue

        if value == "changed":
            conditions.append(f"{before_column} IS DISTINCT FROM {after_column}")
        elif value == "unchanged":
            conditions.append(f"{before_column} IS NOT DISTINCT FROM {after_column}")
        else:
            raise ForestryIngestionError(f"Unsupported change filter value: {value!r}")

    clause = "".join(f" AND {condition}" for condition in conditions)

    return clause, binds


def list_source_features(
    connection: Connection,
    shapefile_snapshot_id: int,
    *,
    filters: SourceFeatureFilters | None = None,
    limit: int,
    offset: int,
) -> SourceFeaturePage:
    """List snapshot-local source features in feature-ordinal order."""

    if limit < 1 or offset < 0:
        raise ForestryIngestionError("limit must be >= 1 and offset must be >= 0")

    clause, binds = _filter_conditions(filters or SourceFeatureFilters())
    binds["snapshot_id"] = shapefile_snapshot_id

    total_count = connection.execute(
        text(
            f"""
            SELECT count(*)
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id{clause}
            """
        ),
        binds,
    ).scalar_one()

    rows = connection.execute(
        text(
            f"""
            SELECT {_FEATURE_RECORD_COLUMNS}
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id{clause}
            ORDER BY feature_ordinal
            LIMIT :limit OFFSET :offset
            """
        ),
        {**binds, "limit": limit, "offset": offset},
    ).all()

    return SourceFeaturePage(
        total_count=int(total_count),
        limit=limit,
        offset=offset,
        features=tuple(_feature_record(row) for row in rows),
    )


def get_source_feature(
    connection: Connection,
    shapefile_snapshot_id: int,
    feature_ordinal: int,
) -> SourceFeatureDetail | None:
    """Return one source feature with attributes and faithful geometry."""

    row = connection.execute(
        text(
            f"""
            SELECT {_FEATURE_RECORD_COLUMNS},
                shape_area,
                geometry_invalid_reason,
                source_attributes,
                ST_AsGeoJSON(geometry) AS geometry_geojson
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
              AND feature_ordinal = :feature_ordinal
            """
        ),
        {
            "snapshot_id": shapefile_snapshot_id,
            "feature_ordinal": feature_ordinal,
        },
    ).one_or_none()

    if row is None:
        return None

    return SourceFeatureDetail(
        record=_feature_record(row),
        shape_area=(None if row.shape_area is None else float(row.shape_area)),
        geometry_invalid_reason=row.geometry_invalid_reason,
        source_attributes=dict(row.source_attributes),
        geometry_geojson=row.geometry_geojson,
    )


def list_feature_geometries(
    connection: Connection,
    shapefile_snapshot_id: int,
    *,
    filters: SourceFeatureFilters | None = None,
) -> tuple[FeatureGeometryRecord, ...]:
    """List filtered features with GeoJSON-encoded stored geometry.

    Geometry is serialized exactly as stored (source CRS coordinates, invalid
    geometries included); nothing is reprojected or repaired.
    """

    clause, binds = _filter_conditions(filters or SourceFeatureFilters())
    binds["snapshot_id"] = shapefile_snapshot_id

    rows = connection.execute(
        text(
            f"""
            SELECT {_FEATURE_RECORD_COLUMNS},
                ST_AsGeoJSON(geometry) AS geometry_geojson
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id{clause}
            ORDER BY feature_ordinal
            """
        ),
        binds,
    ).all()

    return tuple(
        FeatureGeometryRecord(
            record=_feature_record(row),
            geometry_geojson=row.geometry_geojson,
        )
        for row in rows
    )


def _field_differences(
    connection: Connection,
    shapefile_snapshot_id: int,
    *,
    before_column: str,
    after_column: str,
) -> tuple[UseFieldChange, ...]:
    if {before_column, after_column} - {"uso_2024", "uso_2026", "cod_uso", "cod_uso_2026"}:
        raise ForestryIngestionError("Unsupported comparison columns")

    rows = connection.execute(
        text(
            f"""
            SELECT
                feature_ordinal,
                source_objectid,
                {before_column} AS before_value,
                {after_column} AS after_value
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
              AND {before_column} IS DISTINCT FROM {after_column}
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": shapefile_snapshot_id},
    ).all()

    return tuple(
        UseFieldChange(
            feature_ordinal=int(row.feature_ordinal),
            source_objectid=(None if row.source_objectid is None else int(row.source_objectid)),
            before=row.before_value,
            after=row.after_value,
        )
        for row in rows
    )
