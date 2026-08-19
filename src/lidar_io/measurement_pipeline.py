"""End-to-end orchestration for observable timber-stack measurement.

This module owns the I/O and orchestration boundary:

LAS input
    -> metadata inspection
    -> timber-stack localization
    -> observable front cross-section
    -> structured MeasurementRun
    -> persisted measurement.json

It does not infer coordinate units, hidden pile depth, or commercial
cubicacion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import laspy
import numpy as np

from lidar_core.measurement_run import (
    summarize_front_cross_section,
    summarize_timber_stack,
)
from lidar_core.models import (
    BoundingBox3D,
    MeasurementRun,
    MeasurementRunStatus,
    MeasurementWarning,
    MeasurementWarningSeverity,
    VolumeResult,
    VolumeUnit,
    new_run_id,
)
from lidar_core.timber_stack import (
    TimberStackDetectionConfig,
    detect_timber_stack,
)
from lidar_io.inspect import inspect_las
from lidar_io.run_artifacts import (
    write_front_height_profile_plot_artifact,
    write_front_profile_artifact,
    write_front_profile_plot_artifact,
)
from lidar_io.run_store import write_measurement_run
from lidar_volume.front_cross_section import (
    FrontCrossSectionConfig,
    estimate_front_cross_section,
    extruded_volume,
)


def run_timber_measurement(
    input_path: Path,
    output_root: Path,
    *,
    run_id: str | None = None,
    timber_config: TimberStackDetectionConfig | None = None,
    cross_section_config: FrontCrossSectionConfig | None = None,
    code_version: str | None = None,
    pile_depth: float | None = None,
    depth_source: str | None = None,
) -> tuple[MeasurementRun, Path]:
    """Run the observable whole-stack measurement path on one LAS/LAZ file.

    The input is expected to be a candidate region containing the timber
    stack. Timber localization is still performed automatically inside that
    candidate region.

    Cubic volume is produced only when an explicit pile depth and its
    provenance are supplied. The result remains a geometric extrusion in
    unspecified source-coordinate cubic units; it is not commercial
    cubicacion.
    """

    if pile_depth is not None and pile_depth < 0:
        raise ValueError("pile_depth must be non-negative")

    if pile_depth is None and depth_source is not None:
        raise ValueError("depth_source requires pile_depth")

    if pile_depth is not None and (depth_source is None or not depth_source.strip()):
        raise ValueError("depth_source is required when pile_depth is supplied")

    resolved_depth_source = depth_source.strip() if depth_source is not None else None

    started_at = datetime.now(UTC)
    resolved_run_id = run_id or new_run_id()

    metadata = inspect_las(
        input_path,
        compute_checksum=True,
    )

    las = laspy.read(str(input_path))

    xyz = np.column_stack(
        [
            np.asarray(las.x),
            np.asarray(las.y),
            np.asarray(las.z),
        ]
    ).astype(
        np.float64,
        copy=False,
    )

    resolved_timber_config = (
        timber_config if timber_config is not None else TimberStackDetectionConfig()
    )

    timber_result = detect_timber_stack(
        xyz,
        config=resolved_timber_config,
    )

    timber_xyz = xyz[timber_result.mask]

    if len(timber_xyz) < 3:
        raise ValueError("timber-stack localization produced fewer than 3 points")

    resolved_cross_section_config = (
        cross_section_config if cross_section_config is not None else FrontCrossSectionConfig()
    )

    cross_section_result = estimate_front_cross_section(
        timber_xyz,
        config=resolved_cross_section_config,
    )

    volume_results: list[VolumeResult] = []

    if pile_depth is not None:
        volume_started = perf_counter()

        volume_value = extruded_volume(
            cross_section_result.rectangle_area,
            pile_depth,
        )

        volume_runtime_seconds = perf_counter() - volume_started

        selected_bounds = BoundingBox3D(
            min_x=float(timber_xyz[:, 0].min()),
            min_y=float(timber_xyz[:, 1].min()),
            min_z=float(timber_xyz[:, 2].min()),
            max_x=float(timber_xyz[:, 0].max()),
            max_y=float(timber_xyz[:, 1].max()),
            max_z=float(timber_xyz[:, 2].max()),
        )

        volume_results.append(
            VolumeResult(
                method="front_cross_section_rectangle_extrusion",
                volume=volume_value,
                volume_unit=VolumeUnit.CUBIC_UNITS_UNSPECIFIED,
                point_count_input=len(xyz),
                point_count_used=len(timber_xyz),
                parameters={
                    "front_area_method": "rectangle",
                    "front_area": cross_section_result.rectangle_area,
                    "pile_depth": pile_depth,
                    "depth_source": resolved_depth_source,
                    "linear_units": "source_units",
                    "commercial_cubicacion": False,
                },
                bounds=selected_bounds,
                warnings=[
                    (
                        "Geometric A_front × depth extrusion only; "
                        "this is not commercial timber cubicacion."
                    )
                ],
                runtime_seconds=volume_runtime_seconds,
                provenance={
                    "source_sha256": metadata.sha256,
                    "code_version": code_version,
                    "depth_source": resolved_depth_source,
                },
            )
        )

    run_directory = output_root / resolved_run_id

    front_profile_artifact = write_front_profile_artifact(
        cross_section_result,
        run_directory,
    )

    front_profile_plot_artifact = write_front_profile_plot_artifact(
        cross_section_result,
        run_directory,
    )

    front_height_profile_plot_artifact = write_front_height_profile_plot_artifact(
        cross_section_result,
        run_directory,
    )

    warnings: list[MeasurementWarning] = []

    coordinate_metadata = metadata.coordinate_metadata

    if not coordinate_metadata.is_explicit:
        warnings.append(
            MeasurementWarning(
                code="crs_unconfirmed",
                severity=MeasurementWarningSeverity.BLOCKER,
                message=(
                    "The input file does not contain an explicitly confirmed "
                    "coordinate reference system."
                ),
            )
        )

    if coordinate_metadata.horizontal_units is None:
        warnings.append(
            MeasurementWarning(
                code="linear_units_unconfirmed",
                severity=MeasurementWarningSeverity.BLOCKER,
                message=(
                    "Physical horizontal coordinate units are not confirmed; "
                    "reported geometry remains in source-coordinate units."
                ),
            )
        )

    if pile_depth is None:
        warnings.append(
            MeasurementWarning(
                code="pile_depth_not_supplied",
                severity=MeasurementWarningSeverity.BLOCKER,
                message=("No validated pile depth was supplied, so cubic volume was not computed."),
            )
        )

    warnings.extend(
        MeasurementWarning(
            code="las_metadata_warning",
            severity=MeasurementWarningSeverity.WARNING,
            message=message,
        )
        for message in metadata.warnings
    )

    run = MeasurementRun(
        run_id=resolved_run_id,
        source_path=str(input_path),
        source_sha256=metadata.sha256,
        status=MeasurementRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        code_version=code_version,
        coordinate_metadata=coordinate_metadata,
        timber_stack=summarize_timber_stack(
            timber_result,
            point_count_input=len(xyz),
            config=resolved_timber_config,
        ),
        front_cross_section=summarize_front_cross_section(
            cross_section_result,
            config=resolved_cross_section_config,
        ),
        results=volume_results,
        warnings=warnings,
        artifacts=[
            front_profile_artifact,
            front_profile_plot_artifact,
            front_height_profile_plot_artifact,
        ],
        provenance={
            "las_version": (f"{metadata.las_version_major}.{metadata.las_version_minor}"),
            "point_format_id": metadata.point_format_id,
            "input_point_count": metadata.point_count,
            "header_bounds_match": metadata.header_bounds_match,
        },
    )

    output_path = write_measurement_run(
        run,
        output_root,
    )

    return run, output_path
