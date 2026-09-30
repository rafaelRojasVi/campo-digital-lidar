"""Read the Rodales version history: snapshots, their sources, and activations.

A "version" is one persisted Forestry snapshot. Its status comes only from
the publication trail (``app.forestry_publication``); its source is either
one or more dashboard uploads (``forestry.snapshot_upload``) or, for a
snapshot written by the controlled CLI import, the platform provenance
observation of the archive it was read from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from app.forestry_publication import (
    VersionStatus,
    ever_published_snapshot_ids,
    read_published_snapshot_id,
)

_PROJCS_NAME = re.compile(r'^PROJCS\["([^"]+)"')


@dataclass(frozen=True, slots=True)
class UploadRecord:
    """One dashboard upload of a snapshot's content."""

    snapshot_upload_id: int
    original_filename: str
    byte_size: int
    content_sha256: str
    uploaded_at: datetime
    uploaded_by_display_name: str


@dataclass(frozen=True, slots=True)
class ImportedSource:
    """The archive a CLI-imported snapshot was read from (provenance only)."""

    filename: str
    content_sha256: str
    byte_size: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class PublicationEventRecord:
    """One activation, newest first in listings."""

    publication_event_id: int
    shapefile_snapshot_id: int
    event_type: str
    previous_snapshot_id: int | None
    occurred_at: datetime
    actor_display_name: str | None


@dataclass(frozen=True, slots=True)
class VersionRecord:
    """One snapshot as a version, with everything the history shows."""

    shapefile_snapshot_id: int
    status: VersionStatus
    layer_name: str
    family_fingerprint: str
    crs_name: str | None
    storage_srid: int
    feature_count: int
    total_sup_ha: float
    total_geometry_area_source_units: float
    geometry_invalid_count: int
    created_at: datetime
    uploads: tuple[UploadRecord, ...]
    imported_source: ImportedSource | None


def crs_name(prj_wkt: str) -> str | None:
    """The projected CRS name declared in a .prj (e.g. ``WGS_1984_UTM_Zone_18S``)."""

    match = _PROJCS_NAME.match(prj_wkt)
    return match.group(1) if match else None


def _uploads_by_snapshot(connection: Connection) -> dict[int, list[UploadRecord]]:
    rows = connection.execute(
        text(
            """
            SELECT u.id, u.shapefile_snapshot_id, u.original_filename, u.byte_size,
                   u.content_sha256, u.uploaded_at, a.display_name
            FROM forestry.snapshot_upload AS u
            JOIN platform.app_user AS a ON a.id = u.uploaded_by_app_user_id
            ORDER BY u.uploaded_at DESC, u.id DESC
            """
        )
    ).all()
    grouped: dict[int, list[UploadRecord]] = {}
    for row in rows:
        grouped.setdefault(row.shapefile_snapshot_id, []).append(
            UploadRecord(
                snapshot_upload_id=row.id,
                original_filename=row.original_filename,
                byte_size=row.byte_size,
                content_sha256=row.content_sha256,
                uploaded_at=row.uploaded_at,
                uploaded_by_display_name=row.display_name,
            )
        )
    return grouped


def _imported_source(row: Any) -> ImportedSource | None:
    if row.observation_filename is None:
        return None
    return ImportedSource(
        filename=row.observation_filename,
        content_sha256=row.content_sha256,
        byte_size=row.byte_size,
        observed_at=row.observed_at,
    )


def list_versions(
    connection: Connection, *, include_pending: bool, snapshot_id: int | None = None
) -> list[VersionRecord]:
    """Every snapshot, newest first; ``include_pending=False`` hides never-published ones."""

    published_id = read_published_snapshot_id(connection)
    ever_published = ever_published_snapshot_ids(connection)
    uploads = _uploads_by_snapshot(connection)

    rows = connection.execute(
        text(
            """
            SELECT
                s.id, s.layer_name, s.family_fingerprint, s.prj_wkt, s.storage_srid,
                s.feature_count, s.created_at,
                agg.total_sup_ha, agg.total_area, agg.invalid_count,
                ps.content_sha256, ps.byte_size,
                obs.filename AS observation_filename, obs.observed_at
            FROM forestry.shapefile_snapshot AS s
            JOIN platform.source_snapshot AS ps ON ps.id = s.source_snapshot_id
            CROSS JOIN LATERAL (
                SELECT
                    COALESCE(sum(f.sup_ha), 0) AS total_sup_ha,
                    COALESCE(sum(f.geometry_area_source_units), 0) AS total_area,
                    count(*) FILTER (WHERE NOT f.geometry_is_valid) AS invalid_count
                FROM forestry.source_feature AS f
                WHERE f.shapefile_snapshot_id = s.id
            ) AS agg
            LEFT JOIN LATERAL (
                SELECT o.filename, o.observed_at
                FROM platform.source_observation AS o
                WHERE o.source_snapshot_id = s.source_snapshot_id
                ORDER BY o.observed_at ASC, o.id ASC
                LIMIT 1
            ) AS obs ON TRUE
            WHERE (CAST(:snapshot_id AS bigint) IS NULL OR s.id = :snapshot_id)
            ORDER BY s.id DESC
            """
        ),
        {"snapshot_id": snapshot_id},
    ).all()

    versions: list[VersionRecord] = []
    for row in rows:
        status: VersionStatus
        if row.id == published_id:
            status = "published"
        elif row.id in ever_published:
            status = "previously_published"
        else:
            status = "pending"
        if status == "pending" and not include_pending:
            continue
        snapshot_uploads = tuple(uploads.get(row.id, ()))
        versions.append(
            VersionRecord(
                shapefile_snapshot_id=row.id,
                status=status,
                layer_name=row.layer_name,
                family_fingerprint=row.family_fingerprint,
                crs_name=crs_name(row.prj_wkt),
                storage_srid=row.storage_srid,
                feature_count=row.feature_count,
                total_sup_ha=float(row.total_sup_ha),
                total_geometry_area_source_units=float(row.total_area),
                geometry_invalid_count=int(row.invalid_count),
                created_at=row.created_at,
                uploads=snapshot_uploads,
                # A snapshot first written by the CLI import has no upload;
                # its provenance observation names the archive instead.
                imported_source=None if snapshot_uploads else _imported_source(row),
            )
        )
    return versions


def list_publication_events(
    connection: Connection, *, visible_snapshot_ids: frozenset[int] | None = None
) -> list[PublicationEventRecord]:
    """The activation trail, newest first."""

    rows = connection.execute(
        text(
            """
            SELECT e.id, e.shapefile_snapshot_id, e.event_type, e.previous_snapshot_id,
                   e.occurred_at, a.display_name
            FROM forestry.publication_event AS e
            LEFT JOIN platform.app_user AS a ON a.id = e.actor_app_user_id
            ORDER BY e.occurred_at DESC, e.id DESC
            """
        )
    ).all()
    return [
        PublicationEventRecord(
            publication_event_id=row.id,
            shapefile_snapshot_id=row.shapefile_snapshot_id,
            event_type=row.event_type,
            previous_snapshot_id=row.previous_snapshot_id,
            occurred_at=row.occurred_at,
            actor_display_name=row.display_name,
        )
        for row in rows
        if visible_snapshot_ids is None or row.shapefile_snapshot_id in visible_snapshot_ids
    ]


@dataclass(frozen=True, slots=True)
class InvalidGeometryRecord:
    """One feature whose stored geometry fails OGC validity."""

    feature_ordinal: int
    source_objectid: int | None
    cod_predial: str | None
    nom_predio: str | None
    n_rodal: str | None
    reason: str


def list_invalid_geometries(
    connection: Connection, snapshot_id: int
) -> list[InvalidGeometryRecord]:
    """The snapshot's invalid geometries with the recorded GEOS reason."""

    rows = connection.execute(
        text(
            """
            SELECT feature_ordinal, source_objectid, cod_predial, nom_predio, n_rodal,
                   geometry_invalid_reason
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id AND NOT geometry_is_valid
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": snapshot_id},
    ).all()
    return [
        InvalidGeometryRecord(
            feature_ordinal=row.feature_ordinal,
            source_objectid=row.source_objectid,
            cod_predial=row.cod_predial,
            nom_predio=row.nom_predio,
            n_rodal=row.n_rodal,
            reason=row.geometry_invalid_reason,
        )
        for row in rows
    ]
