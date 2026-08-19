"""Adapters from algorithm outputs to persistent measurement-run summaries.

This module contains no filesystem persistence and runs no measurement
algorithms itself. It only converts already-computed algorithm results into
the stable Pydantic reporting schema.
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from lidar_core.log_ends_radial import (
    RadialLogEndDetectionConfig,
    RadialLogEndDetectionResult,
)
from lidar_core.models import (
    FrontCrossSectionSummary,
    LogDetectionSummary,
    TimberStackSummary,
)
from lidar_core.timber_stack import (
    TimberStackDetectionConfig,
    TimberStackDetectionResult,
)
from lidar_volume.front_cross_section import (
    FrontCrossSectionConfig,
    FrontCrossSectionEstimate,
)


def _config_parameters(
    config: (
        TimberStackDetectionConfig | FrontCrossSectionConfig | RadialLogEndDetectionConfig | None
    ),
) -> dict[str, object]:
    """Serialize an explicitly supplied dataclass configuration.

    An omitted configuration is recorded as unknown rather than silently
    replaced with current library defaults.
    """

    if config is None:
        return {}

    return asdict(config)


def summarize_timber_stack(
    result: TimberStackDetectionResult,
    *,
    point_count_input: int,
    config: TimberStackDetectionConfig | None = None,
) -> TimberStackSummary:
    """Convert timber-stack localization diagnostics to run schema."""

    if point_count_input < 0:
        raise ValueError("point_count_input must be non-negative")

    return TimberStackSummary(
        point_count_input=point_count_input,
        point_count_selected=result.selected_point_count,
        selected_fraction=result.selected_point_fraction,
        detected_components=result.component_count,
        longitudinal_coverage=result.longitudinal_coverage,
        vertical_extent_fraction=result.vertical_extent_fraction,
        transverse_extent_fraction=result.transverse_extent_fraction,
        parameters=_config_parameters(config),
    )


def summarize_front_cross_section(
    result: FrontCrossSectionEstimate,
    *,
    config: FrontCrossSectionConfig | None = None,
) -> FrontCrossSectionSummary:
    """Convert observable front-wall geometry to run schema."""

    height = np.asarray(result.height, dtype=np.float64)
    finite_height = height[np.isfinite(height)]

    if finite_height.size == 0:
        raise ValueError("front cross-section contains no finite height values")

    return FrontCrossSectionSummary(
        longitudinal_span=result.longitudinal_span,
        median_height=float(np.median(finite_height)),
        maximum_height=float(np.max(finite_height)),
        rectangle_area=result.rectangle_area,
        trapezoid_area=result.trapezoid_area,
        valid_bin_fraction=result.valid_bin_fraction,
        parameters=_config_parameters(config),
    )


def summarize_radial_log_detection(
    result: RadialLogEndDetectionResult,
    *,
    config: RadialLogEndDetectionConfig | None = None,
    method: str = "radial",
) -> LogDetectionSummary:
    """Convert visible-log detector output to run schema."""

    parameters = _config_parameters(config)

    # This is a runtime diagnostic, not detector benchmark precision/recall.
    parameters["raw_candidate_count"] = result.raw_candidate_count

    return LogDetectionSummary(
        method=method,
        candidate_count=len(result.candidates),
        parameters=parameters,
    )
