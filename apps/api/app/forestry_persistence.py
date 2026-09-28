"""Transactional ingestion of Forestry shapefile snapshots into PostGIS.

The use case runs inside the caller's transaction (the established platform
pattern, see `app.source_provenance`): contract validation, geometry decoding,
and quality-evidence computation all happen before the first write, and a
failure at any point aborts the caller's transaction so a half-imported
snapshot cannot exist.

Identity model:

- The platform provenance foundation records the observed archive
  (system/asset/snapshot/observation) exactly as for any other source file.
- The Forestry snapshot is identified by the deterministic family fingerprint;
  re-ingesting identical family content is idempotent (the repeated
  observation is still appended as platform provenance history, and a
  repackaged archive with identical members resolves to the same Forestry
  snapshot while keeping its original platform snapshot reference).
- Features are identified only as `(shapefile_snapshot_id, feature_ordinal)`;
  `source_objectid` is preserved as evidence, never as a durable identity.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, text

from app.source_discovery import (
    fingerprint_source_file,
    observe_source_file,
)
from app.source_provenance import (
    PersistedSourceProvenance,
    persist_filesystem_source_provenance,
)
from forestry_ingestion.family_archive import extract_family_archive
from forestry_ingestion.shapefile_contract import (
    ForestryShapefileTable,
    load_forestry_shapefile,
)
from forestry_ingestion.shapefile_geometry import (
    SOURCE_STORAGE_SRID,
    SourceFeatureGeometry,
    decode_polygon_records,
)
from forestry_ingestion.snapshot_evidence import compute_quality_flags


class ForestryIngestionError(RuntimeError):
    """Base error for Forestry snapshot ingestion."""


class ForestryIngestionConflictError(ForestryIngestionError):
    """Raised when persisted Forestry state conflicts with the parsed source."""


@dataclass(frozen=True, slots=True)
class ForestrySnapshotIngestion:
    """Result of ingesting one Forestry source archive."""

    provenance: PersistedSourceProvenance
    shapefile_snapshot_id: int
    family_fingerprint: str
    feature_count: int
    already_persisted: bool


def ingest_forestry_snapshot(
    connection: Connection,
    *,
    source_root: Path,
    zip_relative_path: str,
    system_key: str,
) -> ForestrySnapshotIngestion:
    """Validate and persist one Forestry source ZIP inside the caller's transaction."""

    observation = observe_source_file(source_root, zip_relative_path)
    fingerprint = fingerprint_source_file(source_root, zip_relative_path)

    with tempfile.TemporaryDirectory(prefix="forestry-ingest-") as scratch:
        shp_path = extract_family_archive(
            Path(source_root) / zip_relative_path,
            Path(scratch),
        )
        table = load_forestry_shapefile(shp_path)
        geometries = decode_polygon_records(shp_path)

    _require_aligned_records(table, geometries)
    quality_flags = compute_quality_flags(table.rows, geometries)
    feature_parameters = _build_feature_parameters(table, geometries, quality_flags)

    provenance = persist_filesystem_source_provenance(
        connection,
        system_key=system_key,
        observation=observation,
        fingerprint=fingerprint,
    )

    inserted_snapshot_id = _insert_shapefile_snapshot(
        connection,
        table=table,
        source_snapshot_id=provenance.source_snapshot_id,
    )

    if inserted_snapshot_id is None:
        existing_id = _resolve_existing_snapshot(connection, table)

        return ForestrySnapshotIngestion(
            provenance=provenance,
            shapefile_snapshot_id=existing_id,
            family_fingerprint=table.family_fingerprint,
            feature_count=len(table.rows),
            already_persisted=True,
        )

    for parameters in feature_parameters:
        parameters["snapshot_id"] = inserted_snapshot_id

    _insert_source_features(connection, feature_parameters)

    return ForestrySnapshotIngestion(
        provenance=provenance,
        shapefile_snapshot_id=inserted_snapshot_id,
        family_fingerprint=table.family_fingerprint,
        feature_count=len(table.rows),
        already_persisted=False,
    )


def _require_aligned_records(
    table: ForestryShapefileTable,
    geometries: tuple[SourceFeatureGeometry, ...],
) -> None:
    if [row.record_number for row in table.rows] != [
        geometry.record_number for geometry in geometries
    ]:
        raise ForestryIngestionError(
            "Attribute and geometry record streams disagree: "
            f"dbf={len(table.rows)}; shp={len(geometries)}"
        )


def _build_feature_parameters(
    table: ForestryShapefileTable,
    geometries: tuple[SourceFeatureGeometry, ...],
    quality_flags: dict[int, tuple[str, ...]],
) -> list[dict[str, object]]:
    parameters: list[dict[str, object]] = []

    for row, geometry in zip(table.rows, geometries, strict=True):
        parameters.append(
            {
                "feature_ordinal": row.record_number,
                "source_objectid": row.objectid,
                "wkb": geometry.wkb,
                "srid": SOURCE_STORAGE_SRID,
                "geometry_is_valid": geometry.is_valid,
                "geometry_invalid_reason": geometry.invalid_reason,
                "geometry_area_source_units": geometry.area_source_units,
                "source_attributes": json.dumps(row.values, ensure_ascii=False),
                "nom_predio": row.nom_predio,
                "cod_predial": row.cod_predial,
                "n_rodal": row.n_rodal,
                "cod_uso": row.values["cod_uso"],
                "uso_2024": row.values["uso_2024"],
                "desc_uso": row.values["desc_uso"],
                "uso_2026": row.values["uso_2026"],
                "cod_uso_2026": row.values["cod_uso_2026"],
                "sup_ha": row.sup_ha,
                "shape_area": row.values["shape_area"],
                "quality_flags": list(quality_flags[row.record_number]),
            }
        )

    return parameters


def _insert_shapefile_snapshot(
    connection: Connection,
    *,
    table: ForestryShapefileTable,
    source_snapshot_id: int,
) -> int | None:
    result = connection.execute(
        text(
            """
            INSERT INTO forestry.shapefile_snapshot (
                source_snapshot_id,
                family_fingerprint,
                layer_name,
                member_sha256,
                prj_wkt,
                storage_srid,
                encoding,
                shape_type,
                bbox_x_min,
                bbox_y_min,
                bbox_x_max,
                bbox_y_max,
                feature_count
            )
            VALUES (
                :source_snapshot_id,
                :family_fingerprint,
                :layer_name,
                CAST(:member_sha256 AS jsonb),
                :prj_wkt,
                :storage_srid,
                :encoding,
                :shape_type,
                :bbox_x_min,
                :bbox_y_min,
                :bbox_x_max,
                :bbox_y_max,
                :feature_count
            )
            ON CONFLICT (family_fingerprint) DO NOTHING
            RETURNING id
            """
        ),
        {
            "source_snapshot_id": source_snapshot_id,
            "family_fingerprint": table.family_fingerprint,
            "layer_name": table.source_shp_path.stem,
            "member_sha256": json.dumps(table.member_sha256),
            "prj_wkt": table.prj_wkt,
            "storage_srid": SOURCE_STORAGE_SRID,
            "encoding": table.encoding,
            "shape_type": table.shape_type,
            "bbox_x_min": table.bbox[0],
            "bbox_y_min": table.bbox[1],
            "bbox_x_max": table.bbox[2],
            "bbox_y_max": table.bbox[3],
            "feature_count": len(table.rows),
        },
    ).scalar_one_or_none()

    return None if result is None else int(result)


def _resolve_existing_snapshot(
    connection: Connection,
    table: ForestryShapefileTable,
) -> int:
    existing = connection.execute(
        text(
            """
            SELECT id, layer_name, feature_count
            FROM forestry.shapefile_snapshot
            WHERE family_fingerprint = :family_fingerprint
            """
        ),
        {"family_fingerprint": table.family_fingerprint},
    ).one()

    if existing.layer_name != table.source_shp_path.stem or existing.feature_count != len(
        table.rows
    ):
        raise ForestryIngestionConflictError(
            "Existing Forestry snapshot with the same family fingerprint "
            "disagrees with the parsed source content"
        )

    return int(existing.id)


def _insert_source_features(
    connection: Connection,
    feature_parameters: list[dict[str, object]],
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO forestry.source_feature (
                shapefile_snapshot_id,
                feature_ordinal,
                source_objectid,
                geometry,
                geometry_is_valid,
                geometry_invalid_reason,
                geometry_area_source_units,
                source_attributes,
                nom_predio,
                cod_predial,
                n_rodal,
                cod_uso,
                uso_2024,
                desc_uso,
                uso_2026,
                cod_uso_2026,
                sup_ha,
                shape_area,
                quality_flags
            )
            VALUES (
                :snapshot_id,
                :feature_ordinal,
                :source_objectid,
                ST_GeomFromWKB(:wkb, :srid),
                :geometry_is_valid,
                :geometry_invalid_reason,
                :geometry_area_source_units,
                CAST(:source_attributes AS jsonb),
                :nom_predio,
                :cod_predial,
                :n_rodal,
                :cod_uso,
                :uso_2024,
                :desc_uso,
                :uso_2026,
                :cod_uso_2026,
                :sup_ha,
                :shape_area,
                :quality_flags
            )
            """
        ),
        feature_parameters,
    )
