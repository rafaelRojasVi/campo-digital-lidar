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

import laspy
import numpy as np

from lidar_core.measurement_run import (
    summarize_front_cross_section,
    summarize_timber_stack,
)
from lidar_core.models import (
    MeasurementRun,
    MeasurementRunStatus,
    MeasurementWarning,
    MeasurementWarningSeverity,
    new_run_id,
)
from lidar_core.timber_stack import (
    TimberStackDetectionConfig,
    detect_timber_stack,
)
from lidar_io.inspect import inspect_las
from lidar_io.run_store import write_measurement_run
from lidar_volume.front_cross_section import (
    FrontCrossSectionConfig,
    estimate_front_cross_section,
)


def run_timber_measurement(
    input_path: Path,
    output_root: Path,
    *,
    run_id: str | None = None,
    timber_config: TimberStackDetectionConfig | None = None,
    cross_section_config: FrontCrossSectionConfig | None = None,
    code_version: str | None = None,
) -> tuple[MeasurementRun, Path]:
    """Run the observable whole-stack measurement path on one LAS/LAZ file.

    The input is expected to be a candidate region containing the timber
    stack. Timber localization is still performed automatically inside that
    candidate region.

    No cubic volume is produced because this function has no validated pile
    depth input.
    """

    started_at = datetime.now(UTC)

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
        run_id=run_id or new_run_id(),
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
        warnings=warnings,
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
