"""LAS forensic inspection using laspy header/streaming reads.

Never loads the full point cloud into RAM just for metadata: header fields
come from `laspy.open(...).header` without reading points, and histograms
(which do require visiting every point's classification/return-number) are
computed via chunked streaming reads.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from collections import Counter
from pathlib import Path

import laspy
import numpy as np

from lidar_core.models import (
    BoundingBox3D,
    CoordinateMetadata,
    LasMetadata,
    PointDimensions,
)

_STREAM_CHUNK = 1_000_000
_CHECKSUM_SIZE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB; skip sha256 above this


def _sha256_of_file(path: Path) -> str | None:
    size = path.stat().st_size
    if size > _CHECKSUM_SIZE_LIMIT_BYTES:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_crs(las_reader_header: laspy.LasHeader) -> CoordinateMetadata:
    try:
        crs = las_reader_header.parse_crs()
    except Exception:
        crs = None
    if crs is None:
        return CoordinateMetadata(is_explicit=False)
    epsg = None
    with contextlib.suppress(Exception):
        epsg = crs.to_epsg()
    return CoordinateMetadata(
        crs_wkt=crs.to_wkt() if hasattr(crs, "to_wkt") else None,
        crs_epsg=epsg,
        crs_source="VLR/EVLR CRS (laspy parse_crs)",
        is_explicit=True,
    )


def _point_dimensions(header: laspy.LasHeader) -> PointDimensions:
    point_format = header.point_format
    dim_names = list(point_format.dimension_names)
    standard = list(point_format.standard_dimension_names)
    extra = [d for d in dim_names if d not in standard]
    return PointDimensions(
        standard_dims=standard,
        extra_dims=extra,
        has_rgb="red" in dim_names and "green" in dim_names and "blue" in dim_names,
        has_intensity="intensity" in dim_names,
        has_gps_time="gps_time" in dim_names,
        has_classification="classification" in dim_names,
        has_return_number="return_number" in dim_names,
    )


def inspect_las(path: str | os.PathLike[str], compute_checksum: bool = True) -> LasMetadata:
    """Produce a LasMetadata report for a LAS/LAZ file.

    Header fields (version, point format, count, scale/offset, bounds, CRS,
    VLRs, dims) are read without touching point data. Classification and
    return-number histograms require a streaming pass over points, done in
    chunks so full point cloud is never resident in memory at once.
    """
    p = Path(path)
    warnings: list[str] = []
    if not p.exists():
        raise FileNotFoundError(f"LAS/LAZ file not found: {p}")

    file_size = p.stat().st_size
    checksum = _sha256_of_file(p) if compute_checksum else None

    with laspy.open(p) as reader:
        header = reader.header
        bounds = BoundingBox3D(
            min_x=header.mins[0],
            min_y=header.mins[1],
            min_z=header.mins[2],
            max_x=header.maxs[0],
            max_y=header.maxs[1],
            max_z=header.maxs[2],
        )
        crs_meta = _extract_crs(header)
        if not crs_meta.is_explicit:
            warnings.append("CRS missing/ambiguous: no CRS encoded in VLRs/EVLRs.")

        dims = _point_dimensions(header)
        vlr_summaries = [
            f"{vlr.user_id}/{vlr.record_id}: {getattr(vlr, 'description', '')}"[:120]
            for vlr in header.vlrs
        ]
        evlr_count = len(header.evlrs) if header.evlrs is not None else 0

        classification_counter: Counter[int] = Counter()
        return_number_counter: Counter[int] = Counter()
        has_class = dims.has_classification
        has_return = dims.has_return_number
        if has_class or has_return:
            for points in reader.chunk_iterator(_STREAM_CHUNK):
                if has_class:
                    classification_counter.update(
                        Counter(np.asarray(points.classification, dtype=int).tolist())
                    )
                if has_return:
                    return_number_counter.update(
                        Counter(np.asarray(points.return_number, dtype=int).tolist())
                    )

        point_count = header.point_count

    if point_count == 0:
        warnings.append("Point count is zero.")

    return LasMetadata(
        path=str(p),
        file_size_bytes=file_size,
        sha256=checksum,
        las_version_major=header.version.major,
        las_version_minor=header.version.minor,
        point_format_id=header.point_format.id,
        point_count=point_count,
        scales=tuple(float(s) for s in header.scales),  # type: ignore[arg-type]
        offsets=tuple(float(o) for o in header.offsets),  # type: ignore[arg-type]
        bounds=bounds,
        coordinate_metadata=crs_meta,
        dimensions=dims,
        vlr_count=len(header.vlrs),
        evlr_count=evlr_count,
        vlr_summaries=vlr_summaries,
        classification_histogram=dict(classification_counter),
        return_number_histogram=dict(return_number_counter),
        warnings=warnings,
    )
