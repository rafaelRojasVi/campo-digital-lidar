"""LiDAR intake inspection, wrapping the existing LAS/LAZ forensic reader.

LIMITATION: ``lidar_io.inspect.inspect_las`` does not load the full point
cloud into RAM at once (it streams in chunks), but it does stream through
every point once to recompute observed bounds — matching the LiDAR product's
own ADR-001 decision not to trust stale header bounds. This is therefore
proportional to file size, not true O(1) header-only inspection. For the
current measured local corpus (~315 MB / ~9.7M points) this is acceptable
for a synchronous upload-time check; a much larger future file may need this
moved off the synchronous upload path and left entirely to the async job.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lidar_io.inspect import inspect_las


@dataclass(frozen=True, slots=True)
class LidarInspectionResult:
    """Safety-checked evidence about an uploaded LAS/LAZ file."""

    point_count: int
    las_version: str
    point_format_id: int
    bounds: tuple[float, float, float, float, float, float]
    crs_is_explicit: bool


def inspect_lidar_file(path: Path) -> LidarInspectionResult:
    """Report point count, version, bounds, and CRS evidence for a LAS/LAZ file.

    SHA-256 checksum computation is disabled: the object store already
    establishes content identity independently, so re-hashing here would be
    redundant work on potentially very large files.
    """

    metadata = inspect_las(path, compute_checksum=False)
    bounds = metadata.bounds

    return LidarInspectionResult(
        point_count=metadata.point_count,
        las_version=f"{metadata.las_version_major}.{metadata.las_version_minor}",
        point_format_id=metadata.point_format_id,
        bounds=(
            bounds.min_x,
            bounds.min_y,
            bounds.min_z,
            bounds.max_x,
            bounds.max_y,
            bounds.max_z,
        ),
        crs_is_explicit=metadata.coordinate_metadata.is_explicit,
    )
