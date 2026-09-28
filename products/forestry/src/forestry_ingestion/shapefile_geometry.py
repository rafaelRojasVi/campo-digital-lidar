"""Faithful decoding of Forestry `.shp` polygon records into OGC MultiPolygons.

The decoder complements `shapefile_contract` (which validates structure and
attributes but deliberately leaves geometry to this slice). It preserves the
source coordinates exactly: rings are never reordered, repaired, or closed on
the reader's behalf. A record that cannot be represented faithfully raises a
structured error instead of being silently adjusted.

Ring semantics follow the ESRI shapefile specification: clockwise rings are
exteriors, counter-clockwise rings are holes. Each hole is attached to the
smallest exterior ring that contains it; a hole contained by no exterior is
preserved as its own part (the behavior of standard GIS readers) so that no
source ring is ever dropped. Every record is stored as a MultiPolygon (the
standard PostGIS promotion for polygon shapefiles) so single- and multi-part
features share one column type without touching coordinates.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from shapely import to_wkb
from shapely.errors import GEOSException
from shapely.geometry import MultiPolygon, Polygon
from shapely.validation import explain_validity

from forestry_ingestion.shapefile_contract import (
    POLYGON_SHAPE_TYPE,
    ForestryShapefileError,
)

# PostGIS SRID for the contract's pinned CRS declaration (WGS_1984_UTM_Zone_18S).
# The mapping to EPSG:32718 ("WGS 84 / UTM zone 18S") is established by pyproj's
# EPSG registry and guarded by
# test_storage_srid_matches_authoritative_epsg_mapping_of_contract_wkt.
SOURCE_STORAGE_SRID = 32718

NULL_SHAPE_TYPE = 0

Point = tuple[float, float]
Ring = tuple[Point, ...]


class ForestryGeometryError(ForestryShapefileError):
    """Raised when `.shp` geometry records cannot be decoded faithfully."""


@dataclass(frozen=True, slots=True)
class SourceFeatureGeometry:
    """Decoded geometry evidence for one `.shp` record.

    `record_number` is the 1-based `.shp` record number; it aligns with the DBF
    record number and is per-snapshot ordering evidence only.
    """

    record_number: int
    wkb: bytes
    is_valid: bool
    invalid_reason: str | None
    ring_count: int
    part_count: int
    area_source_units: float


def decode_polygon_records(path: str | Path) -> tuple[SourceFeatureGeometry, ...]:
    """Decode every polygon record of a contract-valid `.shp` file, in order."""

    raw = Path(path).read_bytes()

    if len(raw) < 100:
        raise ForestryGeometryError(".shp header is truncated")

    features: list[SourceFeatureGeometry] = []
    offset = 100

    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ForestryGeometryError(".shp record header is truncated")

        record_number, content_words = struct.unpack_from(">2i", raw, offset)
        expected_record_number = len(features) + 1

        if record_number != expected_record_number:
            raise ForestryGeometryError(
                f".shp record numbers are not sequential: expected "
                f"{expected_record_number}, found {record_number}"
            )

        content_start = offset + 8
        content_length = content_words * 2

        if content_start + content_length > len(raw):
            raise ForestryGeometryError(f".shp record {record_number} is truncated")

        rings = _decode_record_rings(
            raw,
            content_start=content_start,
            content_length=content_length,
            record_number=record_number,
        )
        features.append(_build_feature(record_number, rings))

        offset = content_start + content_length

    return tuple(features)


def _decode_record_rings(
    raw: bytes,
    *,
    content_start: int,
    content_length: int,
    record_number: int,
) -> tuple[Ring, ...]:
    if content_length < 4:
        raise ForestryGeometryError(f".shp record {record_number} content is truncated")

    shape_type = struct.unpack_from("<i", raw, content_start)[0]

    if shape_type == NULL_SHAPE_TYPE:
        raise ForestryGeometryError(
            f".shp record {record_number} is a null shape; empty source geometry requires review"
        )

    if shape_type != POLYGON_SHAPE_TYPE:
        raise ForestryGeometryError(
            f".shp record {record_number} has shape type {shape_type}; "
            f"the contract accepts polygon ({POLYGON_SHAPE_TYPE}) only"
        )

    if content_length < 44:
        raise ForestryGeometryError(f".shp record {record_number} content is truncated")

    num_parts, num_points = struct.unpack_from("<2i", raw, content_start + 36)

    if num_parts < 1 or num_points < num_parts:
        raise ForestryGeometryError(
            f".shp record {record_number} declares an invalid part/point layout"
        )

    expected_length = 44 + 4 * num_parts + 16 * num_points

    if content_length != expected_length:
        raise ForestryGeometryError(
            f".shp record {record_number} content length disagrees with its "
            f"declared parts/points: declared={expected_length}; actual={content_length}"
        )

    part_offsets = list(struct.unpack_from(f"<{num_parts}i", raw, content_start + 44))
    boundaries = [*part_offsets, num_points]

    boundary_pairs = list(zip(boundaries, boundaries[1:], strict=False))

    if part_offsets[0] != 0 or any(a >= b for a, b in boundary_pairs):
        raise ForestryGeometryError(
            f".shp record {record_number} declares invalid ring part offsets"
        )

    points_start = content_start + 44 + 4 * num_parts
    flat = struct.unpack_from(f"<{2 * num_points}d", raw, points_start)
    points: list[Point] = list(zip(flat[0::2], flat[1::2], strict=True))

    rings: list[Ring] = []

    for start, stop in boundary_pairs:
        ring = tuple(points[start:stop])

        if len(ring) < 4:
            raise ForestryGeometryError(
                f".shp record {record_number} contains a ring with fewer than 4 points"
            )

        if ring[0] != ring[-1]:
            raise ForestryGeometryError(f".shp record {record_number} contains an unclosed ring")

        rings.append(ring)

    return tuple(rings)


def _signed_area(ring: Ring) -> float:
    total = 0.0

    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        total += x1 * y2 - x2 * y1

    return total / 2.0


def _build_feature(record_number: int, rings: tuple[Ring, ...]) -> SourceFeatureGeometry:
    # ESRI winding: clockwise (negative signed area) rings are exteriors.
    # Degenerate zero-area rings are kept as exteriors so they stay visible
    # as (invalid) evidence instead of being attached somewhere arbitrary.
    exteriors: list[Ring] = []
    holes: list[Ring] = []

    for ring in rings:
        if _signed_area(ring) > 0.0:
            holes.append(ring)
        else:
            exteriors.append(ring)

    shells = [Polygon(exterior) for exterior in exteriors]
    assigned: list[list[Ring]] = [[] for _ in exteriors]
    promoted: list[Ring] = []

    for hole in holes:
        container = _smallest_containing_shell(shells, hole)

        if container is None:
            promoted.append(hole)
        else:
            assigned[container].append(hole)

    polygons = [
        Polygon(exterior, holes=ring_holes)
        for exterior, ring_holes in zip(exteriors, assigned, strict=True)
    ]
    polygons.extend(Polygon(hole) for hole in promoted)

    geometry = MultiPolygon(polygons)
    is_valid = bool(geometry.is_valid)

    return SourceFeatureGeometry(
        record_number=record_number,
        wkb=to_wkb(geometry),
        is_valid=is_valid,
        invalid_reason=None if is_valid else explain_validity(geometry),
        ring_count=len(rings),
        part_count=len(polygons),
        area_source_units=float(geometry.area),
    )


def _smallest_containing_shell(shells: list[Polygon], hole: Ring) -> int | None:
    # Containment is tested against the filled hole polygon, not a sample
    # point: a sample point of a large hole can fall inside an exterior that
    # is itself nested within the hole (lake-with-island records).
    filled_hole = Polygon(hole)
    best_index: int | None = None
    best_area = float("inf")

    for index, shell in enumerate(shells):
        try:
            contains = shell.contains(filled_hole)
        except GEOSException:
            # An invalid exterior can defeat the containment predicate; treat
            # it as non-containing rather than guessing an assignment.
            contains = False

        if contains and shell.area < best_area:
            best_index = index
            best_area = shell.area

    return best_index
