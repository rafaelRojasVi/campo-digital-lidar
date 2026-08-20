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
    TimestampGroupAnalysis,
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


def _analyze_timestamp_groups(
    source: Path,
) -> TimestampGroupAnalysis | None:
    """Analyze complete contiguous groups of records with identical GPS time.

    A second streaming pass is intentional: group-boundary logic is kept
    separate from the general acquisition diagnostics and still avoids
    loading the complete cloud into memory.
    """

    group_count = 0
    size_counts: Counter[int] = Counter()
    max_group_size = 0

    two_record_groups = 0
    pattern_counts: Counter[str] = Counter()
    two_record_r1_r2_groups = 0

    distance_stats = _RunningStats()
    abs_dx_stats = _RunningStats()
    abs_dy_stats = _RunningStats()
    abs_dz_stats = _RunningStats()
    abs_intensity_delta_stats = _RunningStats()

    pending_gps = np.empty(0, dtype=np.float64)
    pending_returns = np.empty(0, dtype=np.uint8)
    pending_x = np.empty(0, dtype=np.float64)
    pending_y = np.empty(0, dtype=np.float64)
    pending_z = np.empty(0, dtype=np.float64)
    pending_intensity: np.ndarray | None = None

    def consume_groups(
        starts: np.ndarray,
        ends: np.ndarray,
        returns: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        intensity: np.ndarray | None,
    ) -> None:
        nonlocal group_count
        nonlocal max_group_size
        nonlocal two_record_groups
        nonlocal two_record_r1_r2_groups

        if starts.size == 0:
            return

        sizes = ends - starts

        group_count += int(sizes.size)

        unique_sizes, counts = np.unique(sizes, return_counts=True)
        for size, count in zip(unique_sizes, counts, strict=True):
            size_int = int(size)
            count_int = int(count)
            size_counts[size_int] += count_int
            max_group_size = max(max_group_size, size_int)

        pair_starts = starts[sizes == 2]
        if pair_starts.size == 0:
            return

        two_record_groups += int(pair_starts.size)

        left_returns = returns[pair_starts]
        right_returns = returns[pair_starts + 1]

        pattern_12 = (left_returns == 1) & (right_returns == 2)
        pattern_21 = (left_returns == 2) & (right_returns == 1)
        pattern_11 = (left_returns == 1) & (right_returns == 1)
        pattern_22 = (left_returns == 2) & (right_returns == 2)

        pattern_counts["1->2"] += int(pattern_12.sum())
        pattern_counts["2->1"] += int(pattern_21.sum())
        pattern_counts["1->1"] += int(pattern_11.sum())
        pattern_counts["2->2"] += int(pattern_22.sum())

        recognized = pattern_12 | pattern_21 | pattern_11 | pattern_22
        pattern_counts["other"] += int((~recognized).sum())

        r1_r2 = pattern_12 | pattern_21
        pair_count = int(r1_r2.sum())

        if pair_count == 0:
            return

        two_record_r1_r2_groups += pair_count

        selected_starts = pair_starts[r1_r2]

        dx = x[selected_starts + 1] - x[selected_starts]
        dy = y[selected_starts + 1] - y[selected_starts]
        dz = z[selected_starts + 1] - z[selected_starts]

        distance_stats.update(np.sqrt(dx * dx + dy * dy + dz * dz))
        abs_dx_stats.update(np.abs(dx))
        abs_dy_stats.update(np.abs(dy))
        abs_dz_stats.update(np.abs(dz))

        if intensity is not None:
            intensity_delta = intensity[selected_starts + 1] - intensity[selected_starts]
            abs_intensity_delta_stats.update(np.abs(intensity_delta))

    with laspy.open(source) as reader:
        dim_names = set(reader.header.point_format.dimension_names)

        if "gps_time" not in dim_names or "return_number" not in dim_names:
            return None

        has_intensity = "intensity" in dim_names

        if has_intensity:
            pending_intensity = np.empty(0, dtype=np.float64)

        for points in reader.chunk_iterator(_STREAM_CHUNK):
            if len(points) == 0:
                continue

            gps = np.asarray(points.gps_time, dtype=np.float64)

            # Do not silently manufacture timestamp groups around invalid time
            # records. The primary analyzer already reports non-finite GPS time.
            if not np.all(np.isfinite(gps)):
                return None

            returns = np.asarray(points.return_number, dtype=np.uint8)
            x = np.asarray(points.x, dtype=np.float64)
            y = np.asarray(points.y, dtype=np.float64)
            z = np.asarray(points.z, dtype=np.float64)

            intensity = np.asarray(points.intensity, dtype=np.float64) if has_intensity else None

            if pending_gps.size:
                gps = np.concatenate((pending_gps, gps))
                returns = np.concatenate((pending_returns, returns))
                x = np.concatenate((pending_x, x))
                y = np.concatenate((pending_y, y))
                z = np.concatenate((pending_z, z))

                if intensity is not None and pending_intensity is not None:
                    intensity = np.concatenate((pending_intensity, intensity))

            changes = np.flatnonzero(gps[1:] != gps[:-1]) + 1

            if changes.size == 0:
                pending_gps = gps
                pending_returns = returns
                pending_x = x
                pending_y = y
                pending_z = z
                pending_intensity = intensity
                continue

            starts = np.concatenate(
                (
                    np.array([0], dtype=np.int64),
                    changes.astype(np.int64),
                )
            )
            ends = np.concatenate(
                (
                    changes.astype(np.int64),
                    np.array([len(gps)], dtype=np.int64),
                )
            )

            # The final group may continue in the next LAS chunk.
            complete_starts = starts[:-1]
            complete_ends = ends[:-1]

            consume_groups(
                complete_starts,
                complete_ends,
                returns,
                x,
                y,
                z,
                intensity,
            )

            tail_start = int(starts[-1])

            pending_gps = gps[tail_start:]
            pending_returns = returns[tail_start:]
            pending_x = x[tail_start:]
            pending_y = y[tail_start:]
            pending_z = z[tail_start:]
            pending_intensity = intensity[tail_start:] if intensity is not None else None

    # Flush the final timestamp group.
    if pending_gps.size:
        consume_groups(
            np.array([0], dtype=np.int64),
            np.array([len(pending_gps)], dtype=np.int64),
            pending_returns,
            pending_x,
            pending_y,
            pending_z,
            pending_intensity,
        )

    fraction = two_record_r1_r2_groups / two_record_groups if two_record_groups else None

    return TimestampGroupAnalysis(
        group_count=group_count,
        size_counts=dict(sorted(size_counts.items())),
        max_group_size=max_group_size,
        two_record_groups=two_record_groups,
        two_record_return_pattern_counts=dict(pattern_counts),
        two_record_r1_r2_groups=two_record_r1_r2_groups,
        two_record_r1_r2_fraction=fraction,
        exact_pair_distance=distance_stats.summary(),
        exact_pair_abs_delta_x=abs_dx_stats.summary(),
        exact_pair_abs_delta_y=abs_dy_stats.summary(),
        exact_pair_abs_delta_z=abs_dz_stats.summary(),
        exact_pair_abs_intensity_delta=(abs_intensity_delta_stats.summary()),
    )


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
    scan_angle_rank_stats = _RunningStats()
    scan_angle_degrees_stats = _RunningStats()
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

    equal_time_same_return_pairs = 0
    equal_time_cross_return_pairs = 0
    equal_time_r1_r2_pairs = 0

    pair_distance_stats = _RunningStats()
    pair_abs_dx_stats = _RunningStats()
    pair_abs_dy_stats = _RunningStats()
    pair_abs_dz_stats = _RunningStats()
    pair_abs_intensity_delta_stats = _RunningStats()

    previous_gps: float | None = None
    previous_return_number: int | None = None
    previous_x: float | None = None
    previous_y: float | None = None
    previous_z: float | None = None
    previous_intensity: float | None = None

    with laspy.open(source) as reader:
        header = reader.header
        dim_names = set(header.point_format.dimension_names)

        has_gps = "gps_time" in dim_names
        has_intensity = "intensity" in dim_names
        has_return_number = "return_number" in dim_names
        has_number_of_returns = "number_of_returns" in dim_names
        has_scan_angle_rank = "scan_angle_rank" in dim_names
        has_scan_angle = "scan_angle" in dim_names
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

            if has_scan_angle_rank:
                legacy_scan_angle = np.asarray(
                    points.scan_angle_rank,
                    dtype=np.float64,
                )
                scan_angle_rank_stats.update(legacy_scan_angle)
                scan_angle_degrees_stats.update(legacy_scan_angle)

            elif has_scan_angle:
                modern_scan_angle = np.asarray(
                    points.scan_angle,
                    dtype=np.float64,
                )
                scan_angle_degrees_stats.update(modern_scan_angle * 0.006)

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

            return_numbers: np.ndarray | None = None
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

                # -----------------------------------------------------------
                # Equal-time adjacent return pairing.
                #
                # This deliberately says "adjacent pair", not "pulse pair".
                # Exact equal GPS time + R1/R2 adjacency is evidence of
                # pairing structure, but we do not assume sensor semantics.
                # -----------------------------------------------------------

                if return_numbers is not None:
                    if (
                        previous_gps is not None
                        and previous_return_number is not None
                        and previous_x is not None
                        and previous_y is not None
                        and previous_z is not None
                        and np.isfinite(previous_gps)
                        and np.isfinite(gps[0])
                        and previous_gps == float(gps[0])
                    ):
                        current_return = int(return_numbers[0])

                        if previous_return_number == current_return:
                            equal_time_same_return_pairs += 1
                        else:
                            equal_time_cross_return_pairs += 1

                        if {previous_return_number, current_return} == {1, 2}:
                            equal_time_r1_r2_pairs += 1

                            boundary_dx = float(x[0]) - previous_x
                            boundary_dy = float(y[0]) - previous_y
                            boundary_dz = float(z[0]) - previous_z

                            pair_distance_stats.update(
                                np.array(
                                    [
                                        np.sqrt(
                                            boundary_dx * boundary_dx
                                            + boundary_dy * boundary_dy
                                            + boundary_dz * boundary_dz
                                        )
                                    ],
                                    dtype=np.float64,
                                )
                            )
                            pair_abs_dx_stats.update(np.array([abs(boundary_dx)], dtype=np.float64))
                            pair_abs_dy_stats.update(np.array([abs(boundary_dy)], dtype=np.float64))
                            pair_abs_dz_stats.update(np.array([abs(boundary_dz)], dtype=np.float64))

                            if intensity is not None and previous_intensity is not None:
                                pair_abs_intensity_delta_stats.update(
                                    np.array(
                                        [abs(float(intensity[0]) - previous_intensity)],
                                        dtype=np.float64,
                                    )
                                )

                    if len(gps) > 1:
                        pair_mask = (
                            np.isfinite(gps[:-1]) & np.isfinite(gps[1:]) & (gps[:-1] == gps[1:])
                        )

                        if np.any(pair_mask):
                            left_return = return_numbers[:-1]
                            right_return = return_numbers[1:]

                            same_return = pair_mask & (left_return == right_return)
                            cross_return = pair_mask & (left_return != right_return)
                            r1_r2 = pair_mask & (
                                ((left_return == 1) & (right_return == 2))
                                | ((left_return == 2) & (right_return == 1))
                            )

                            equal_time_same_return_pairs += int(same_return.sum())
                            equal_time_cross_return_pairs += int(cross_return.sum())
                            equal_time_r1_r2_pairs += int(r1_r2.sum())

                            if np.any(r1_r2):
                                dx = x[1:] - x[:-1]
                                dy = y[1:] - y[:-1]
                                dz = z[1:] - z[:-1]

                                selected_dx = dx[r1_r2]
                                selected_dy = dy[r1_r2]
                                selected_dz = dz[r1_r2]

                                pair_distance_stats.update(
                                    np.sqrt(
                                        selected_dx * selected_dx
                                        + selected_dy * selected_dy
                                        + selected_dz * selected_dz
                                    )
                                )
                                pair_abs_dx_stats.update(np.abs(selected_dx))
                                pair_abs_dy_stats.update(np.abs(selected_dy))
                                pair_abs_dz_stats.update(np.abs(selected_dz))

                                if intensity is not None:
                                    intensity_delta = intensity[1:] - intensity[:-1]
                                    pair_abs_intensity_delta_stats.update(
                                        np.abs(intensity_delta[r1_r2])
                                    )

                    previous_gps = float(gps[-1])
                    previous_return_number = int(return_numbers[-1])
                    previous_x = float(x[-1])
                    previous_y = float(y[-1])
                    previous_z = float(z[-1])
                    previous_intensity = float(intensity[-1]) if intensity is not None else None

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

    if has_gps and has_return_number and gps_equal_steps:
        pair_fraction = equal_time_r1_r2_pairs / gps_equal_steps
        warnings.append(
            "Equal-time R1/R2 statistics describe adjacent LAS records only; "
            "they must not be interpreted as confirmed emitted-pulse pairs "
            "without sensor/export provenance."
        )
    else:
        pair_fraction = None

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

    timestamp_groups = _analyze_timestamp_groups(source) if has_gps and has_return_number else None

    if timestamp_groups is not None and timestamp_groups.max_group_size > 2:
        warnings.append(
            "Some exact GPS timestamp groups contain more than two records; "
            "adjacent equal-time R1/R2 records are therefore not equivalent "
            "to complete two-record timestamp groups."
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
        equal_time_adjacent_same_return_pairs=(
            equal_time_same_return_pairs if has_gps and has_return_number else None
        ),
        equal_time_adjacent_cross_return_pairs=(
            equal_time_cross_return_pairs if has_gps and has_return_number else None
        ),
        equal_time_adjacent_r1_r2_pairs=(
            equal_time_r1_r2_pairs if has_gps and has_return_number else None
        ),
        equal_time_adjacent_r1_r2_fraction=pair_fraction,
        paired_return_distance=pair_distance_stats.summary(),
        paired_return_abs_delta_x=pair_abs_dx_stats.summary(),
        paired_return_abs_delta_y=pair_abs_dy_stats.summary(),
        paired_return_abs_delta_z=pair_abs_dz_stats.summary(),
        paired_return_abs_intensity_delta=(pair_abs_intensity_delta_stats.summary()),
        timestamp_groups=timestamp_groups,
        intensity=intensity_stats.summary() if has_intensity else None,
        rgb=rgb,
        scan_angle_rank=(scan_angle_rank_stats.summary() if has_scan_angle_rank else None),
        scan_angle_degrees=(
            scan_angle_degrees_stats.summary() if has_scan_angle_rank or has_scan_angle else None
        ),
        return_number_counts=dict(return_number_counts),
        number_of_returns_counts=dict(number_of_returns_counts),
        point_source_id_counts=dict(point_source_id_counts),
        scan_direction_flag_counts=dict(scan_direction_flag_counts),
        edge_of_flight_line_counts=dict(edge_of_flight_line_counts),
        return_summaries=return_summaries,
        xy_density_points_per_square_source_unit=density,
        warnings=warnings,
    )
