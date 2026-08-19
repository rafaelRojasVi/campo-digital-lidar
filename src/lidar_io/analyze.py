"""Streaming acquisition diagnostics for LAS/LAZ point clouds.

The analyzer intentionally avoids loading the complete cloud into memory.
It characterizes acquisition/export structure only; it does not claim to
recover scanner pose/trajectory or timber volume.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import laspy
import numpy as np

from lidar_core.models import (
    AcquisitionAnalysis,
    BoundingBox3D,
    NumericSummary,
    ReturnAnalysis,
)

_STREAM_CHUNK = 1_000_000


@dataclass
class _RunningStats:
    minimum: float = float("inf")
    maximum: float = float("-inf")
    total: float = 0.0
    count: int = 0

    def update(self, values: np.ndarray) -> None:
        if values.size == 0:
            return

        finite = np.asarray(values, dtype=np.float64)
        finite = finite[np.isfinite(finite)]
        if finite.size == 0:
            return

        self.minimum = min(self.minimum, float(finite.min()))
        self.maximum = max(self.maximum, float(finite.max()))
        self.total += float(finite.sum(dtype=np.float64))
        self.count += int(finite.size)

    def summary(self) -> NumericSummary | None:
        if self.count == 0:
            return None
        return NumericSummary(
            minimum=self.minimum,
            maximum=self.maximum,
            mean=self.total / self.count,
        )


def _update_counter(counter: Counter[int], values: np.ndarray) -> None:
    if values.size == 0:
        return

    unique, counts = np.unique(values, return_counts=True)
    for value, count in zip(unique, counts, strict=True):
        counter[int(value)] += int(count)


def analyze_las(path: str | Path) -> AcquisitionAnalysis:
    """Stream a LAS/LAZ file and characterize acquisition/export structure."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"LAS/LAZ file not found: {source}")

    warnings: list[str] = []

    global_min = np.array([np.inf, np.inf, np.inf], dtype=np.float64)
    global_max = np.array([-np.inf, -np.inf, -np.inf], dtype=np.float64)

    intensity_stats = _RunningStats()
    rgb_stats = {
        "red": _RunningStats(),
        "green": _RunningStats(),
        "blue": _RunningStats(),
    }
    scan_angle_stats = _RunningStats()
    gps_stats = _RunningStats()

    return_number_counts: Counter[int] = Counter()
    number_of_returns_counts: Counter[int] = Counter()
    point_source_id_counts: Counter[int] = Counter()
    scan_direction_flag_counts: Counter[int] = Counter()
    edge_of_flight_line_counts: Counter[int] = Counter()

    return_min: dict[int, np.ndarray] = {}
    return_max: dict[int, np.ndarray] = {}
    return_intensity: dict[int, _RunningStats] = {}

    point_count = 0

    gps_first: float | None = None
    gps_last: float | None = None
    gps_previous: float | None = None
    gps_backward_steps = 0
    gps_equal_steps = 0
    gps_min_positive_step: float | None = None
    gps_max_positive_step: float | None = None
    gps_nonfinite_count = 0

    with laspy.open(source) as reader:
        header = reader.header
        dim_names = set(header.point_format.dimension_names)

        has_gps = "gps_time" in dim_names
        has_intensity = "intensity" in dim_names
        has_return_number = "return_number" in dim_names
        has_number_of_returns = "number_of_returns" in dim_names
        has_scan_angle = "scan_angle_rank" in dim_names
        has_point_source_id = "point_source_id" in dim_names
        has_scan_direction = "scan_direction_flag" in dim_names
        has_edge_of_flight_line = "edge_of_flight_line" in dim_names
        has_rgb = all(name in dim_names for name in ("red", "green", "blue"))

        for points in reader.chunk_iterator(_STREAM_CHUNK):
            chunk_count = len(points)
            if chunk_count == 0:
                continue

            point_count += chunk_count

            x = np.asarray(points.x, dtype=np.float64)
            y = np.asarray(points.y, dtype=np.float64)
            z = np.asarray(points.z, dtype=np.float64)

            global_min = np.minimum(
                global_min,
                np.array([x.min(), y.min(), z.min()], dtype=np.float64),
            )
            global_max = np.maximum(
                global_max,
                np.array([x.max(), y.max(), z.max()], dtype=np.float64),
            )

            intensity: np.ndarray | None = None
            if has_intensity:
                intensity = np.asarray(points.intensity, dtype=np.float64)
                intensity_stats.update(intensity)

            if has_rgb:
                rgb_stats["red"].update(np.asarray(points.red, dtype=np.float64))
                rgb_stats["green"].update(np.asarray(points.green, dtype=np.float64))
                rgb_stats["blue"].update(np.asarray(points.blue, dtype=np.float64))

            if has_scan_angle:
                scan_angle_stats.update(np.asarray(points.scan_angle_rank, dtype=np.float64))

            if has_point_source_id:
                _update_counter(
                    point_source_id_counts,
                    np.asarray(points.point_source_id),
                )

            if has_scan_direction:
                _update_counter(
                    scan_direction_flag_counts,
                    np.asarray(points.scan_direction_flag),
                )

            if has_edge_of_flight_line:
                _update_counter(
                    edge_of_flight_line_counts,
                    np.asarray(points.edge_of_flight_line),
                )

            if has_number_of_returns:
                _update_counter(
                    number_of_returns_counts,
                    np.asarray(points.number_of_returns),
                )

            if has_return_number:
                return_numbers = np.asarray(points.return_number)
                _update_counter(return_number_counts, return_numbers)

                for raw_return_number in np.unique(return_numbers):
                    return_number = int(raw_return_number)
                    mask = return_numbers == raw_return_number

                    xyz_min = np.array(
                        [x[mask].min(), y[mask].min(), z[mask].min()],
                        dtype=np.float64,
                    )
                    xyz_max = np.array(
                        [x[mask].max(), y[mask].max(), z[mask].max()],
                        dtype=np.float64,
                    )

                    if return_number not in return_min:
                        return_min[return_number] = xyz_min
                        return_max[return_number] = xyz_max
                    else:
                        return_min[return_number] = np.minimum(
                            return_min[return_number],
                            xyz_min,
                        )
                        return_max[return_number] = np.maximum(
                            return_max[return_number],
                            xyz_max,
                        )

                    if intensity is not None:
                        return_intensity.setdefault(
                            return_number,
                            _RunningStats(),
                        ).update(intensity[mask])

            if has_gps:
                gps = np.asarray(points.gps_time, dtype=np.float64)
                finite_mask = np.isfinite(gps)
                gps_nonfinite_count += int((~finite_mask).sum())
                finite_gps = gps[finite_mask]

                if finite_gps.size:
                    gps_stats.update(finite_gps)

                    if gps_first is None:
                        gps_first = float(finite_gps[0])

                    differences = np.diff(finite_gps)
                    if gps_previous is not None:
                        differences = np.concatenate(
                            (
                                np.array(
                                    [float(finite_gps[0]) - gps_previous],
                                    dtype=np.float64,
                                ),
                                differences,
                            )
                        )

                    if differences.size:
                        gps_backward_steps += int((differences < 0).sum())
                        gps_equal_steps += int((differences == 0).sum())

                        positive = differences[differences > 0]
                        if positive.size:
                            chunk_min = float(positive.min())
                            chunk_max = float(positive.max())

                            if gps_min_positive_step is None:
                                gps_min_positive_step = chunk_min
                            else:
                                gps_min_positive_step = min(
                                    gps_min_positive_step,
                                    chunk_min,
                                )

                            if gps_max_positive_step is None:
                                gps_max_positive_step = chunk_max
                            else:
                                gps_max_positive_step = max(
                                    gps_max_positive_step,
                                    chunk_max,
                                )

                    gps_previous = float(finite_gps[-1])
                    gps_last = gps_previous

        header_point_count = int(header.point_count)

    observed_bounds: BoundingBox3D | None
    if point_count:
        observed_bounds = BoundingBox3D(
            min_x=float(global_min[0]),
            min_y=float(global_min[1]),
            min_z=float(global_min[2]),
            max_x=float(global_max[0]),
            max_y=float(global_max[1]),
            max_z=float(global_max[2]),
        )
    else:
        observed_bounds = None
        warnings.append("No point records were streamed from the file.")

    if point_count != header_point_count:
        warnings.append(
            f"LAS header point count ({header_point_count}) differs from "
            f"streamed point count ({point_count})."
        )

    gps_summary = gps_stats.summary()

    if not has_gps:
        warnings.append(
            "GPS time dimension is absent; acquisition-time ordering cannot be assessed."
        )
    elif gps_summary is None:
        warnings.append("GPS time dimension exists but contains no finite values.")
    else:
        if gps_backward_steps:
            warnings.append(
                "GPS time decreases in file order; file order is not strictly "
                "acquisition-time monotonic."
            )
        if gps_summary.maximum == gps_summary.minimum:
            warnings.append(
                "GPS time is constant; temporal acquisition structure cannot be recovered."
            )
        if gps_nonfinite_count:
            warnings.append(f"GPS time contains {gps_nonfinite_count:,} non-finite values.")

    density: float | None = None
    if observed_bounds is not None:
        xy_area = observed_bounds.span_x * observed_bounds.span_y
        if xy_area > 0:
            density = point_count / xy_area
            warnings.append(
                "XY density is a whole-cloud bounding-box average in square source units; "
                "it is not local surface density."
            )

    warnings.append("Coordinate units and CRS are not inferred by acquisition analysis.")

    rgb: dict[str, NumericSummary] = {}
    if has_rgb:
        for channel, stats in rgb_stats.items():
            summary = stats.summary()
            if summary is not None:
                rgb[channel] = summary

    return_summaries: list[ReturnAnalysis] = []
    for return_number in sorted(return_number_counts):
        minimum = return_min[return_number]
        maximum = return_max[return_number]

        return_summaries.append(
            ReturnAnalysis(
                return_number=return_number,
                point_count=return_number_counts[return_number],
                bounds=BoundingBox3D(
                    min_x=float(minimum[0]),
                    min_y=float(minimum[1]),
                    min_z=float(minimum[2]),
                    max_x=float(maximum[0]),
                    max_y=float(maximum[1]),
                    max_z=float(maximum[2]),
                ),
                intensity=(
                    return_intensity[return_number].summary()
                    if return_number in return_intensity
                    else None
                ),
            )
        )

    return AcquisitionAnalysis(
        path=str(source),
        point_count=point_count,
        observed_bounds=observed_bounds,
        gps_time_present=has_gps,
        gps_time_first=gps_first,
        gps_time_last=gps_last,
        gps_time_min=gps_summary.minimum if gps_summary else None,
        gps_time_max=gps_summary.maximum if gps_summary else None,
        gps_time_span=(gps_summary.maximum - gps_summary.minimum if gps_summary else None),
        gps_time_non_decreasing=(gps_backward_steps == 0 if gps_summary is not None else None),
        gps_time_backward_steps=(gps_backward_steps if gps_summary is not None else None),
        gps_time_equal_steps=(gps_equal_steps if gps_summary is not None else None),
        gps_time_min_positive_step=gps_min_positive_step,
        gps_time_max_positive_step=gps_max_positive_step,
        intensity=intensity_stats.summary() if has_intensity else None,
        rgb=rgb,
        scan_angle_rank=scan_angle_stats.summary() if has_scan_angle else None,
        return_number_counts=dict(return_number_counts),
        number_of_returns_counts=dict(number_of_returns_counts),
        point_source_id_counts=dict(point_source_id_counts),
        scan_direction_flag_counts=dict(scan_direction_flag_counts),
        edge_of_flight_line_counts=dict(edge_of_flight_line_counts),
        return_summaries=return_summaries,
        xy_density_points_per_square_source_unit=density,
        warnings=warnings,
    )
