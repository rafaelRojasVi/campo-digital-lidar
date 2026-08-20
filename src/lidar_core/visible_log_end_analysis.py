"""Multi-window analysis of visible timber log-end candidates.

This module orchestrates existing front-view projection, candidate detection,
LAS-point evidence backprojection, cross-window association, and candidate
geometry resolution.

Inputs are already-selected timber points and normalized RGB values.

The result remains candidate geometry:
- it is not a confirmed log count,
- it is not validated solid-wood area,
- it does not infer hidden log length,
- it is not timber volume or commercial cubicacion,
- it does not assume source coordinate units are metres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lidar_core.front_view import (
    LocalFrontViewConfig,
    build_local_front_view_projection,
    render_visible_rgb,
)
from lidar_core.log_end_geometry import (
    CandidateEvidenceAssociationConfig,
    CandidateEvidenceAssociationSummary,
    ProjectedLogEndCandidateEvidence,
    ResolvedLogEndCandidateAssociationSummary,
    associate_projected_log_end_evidence,
    project_log_end_candidates_with_support,
    resolve_log_end_candidate_associations,
)
from lidar_core.log_ends import (
    LogEndDetectionConfig,
    detect_log_end_candidates,
)


@dataclass(frozen=True)
class VisibleLogEndAnalysisConfig:
    """Configuration for the reproducible local front-view sweep."""

    n_windows: int = 8
    window_overlap_factor: float = 1.35
    yaw_degrees: float = 0.0

    raster_width: int = 480
    raster_height: int = 260

    longitudinal_quantile_low: float = 0.01
    longitudinal_quantile_high: float = 0.99

    image_quantile_low: float = 0.01
    image_quantile_high: float = 0.99

    use_min_depth: bool = True


@dataclass(frozen=True)
class VisibleLogEndWindowSummary:
    """Diagnostics for one local front-view observation."""

    window_index: int
    visible_point_count: int

    raw_candidate_count: int
    candidate_count: int
    supported_candidate_count: int

    candidate_area_sum_source_units_squared: float
    visible_source_union_count: int

    horizontal_units_per_pixel: float
    vertical_units_per_pixel: float


@dataclass(frozen=True)
class VisibleLogEndAnalysisResult:
    """Multi-window candidate analysis with explicit evidence provenance."""

    config: VisibleLogEndAnalysisConfig
    detector_config: LogEndDetectionConfig
    association_config: CandidateEvidenceAssociationConfig

    windows: tuple[VisibleLogEndWindowSummary, ...]

    observations: tuple[ProjectedLogEndCandidateEvidence, ...]
    observation_window_indices: tuple[int, ...]

    association_summary: CandidateEvidenceAssociationSummary
    resolved_summary: ResolvedLogEndCandidateAssociationSummary


def _validate_inputs(
    xyz: np.ndarray,
    rgb: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    resolved_xyz = np.asarray(
        xyz,
        dtype=np.float64,
    )

    resolved_rgb = np.asarray(
        rgb,
        dtype=np.float64,
    )

    if resolved_xyz.ndim != 2 or resolved_xyz.shape[1] != 3:
        raise ValueError("xyz must have shape (N, 3)")

    if len(resolved_xyz) < 3:
        raise ValueError("xyz must contain at least 3 points")

    if not np.all(np.isfinite(resolved_xyz)):
        raise ValueError("xyz must contain only finite values")

    if resolved_rgb.ndim != 2 or resolved_rgb.shape[1] != 3:
        raise ValueError("rgb must have shape (N, 3)")

    if len(resolved_rgb) != len(resolved_xyz):
        raise ValueError("rgb must correspond one-to-one with xyz")

    if not np.all(np.isfinite(resolved_rgb)):
        raise ValueError("rgb must contain only finite values")

    if np.any(resolved_rgb < 0.0) or np.any(resolved_rgb > 1.0):
        raise ValueError("rgb must be normalized to the interval [0, 1]")

    return resolved_xyz, resolved_rgb


def _validate_config(
    config: VisibleLogEndAnalysisConfig,
) -> None:
    if config.n_windows < 1:
        raise ValueError("n_windows must be >= 1")

    if config.window_overlap_factor <= 0:
        raise ValueError("window_overlap_factor must be positive")

    if config.raster_width < 2:
        raise ValueError("raster_width must be >= 2")

    if config.raster_height < 2:
        raise ValueError("raster_height must be >= 2")


def analyze_visible_log_end_candidates(
    xyz: np.ndarray,
    rgb: np.ndarray,
    *,
    config: VisibleLogEndAnalysisConfig | None = None,
    detector_config: LogEndDetectionConfig | None = None,
    association_config: CandidateEvidenceAssociationConfig | None = None,
) -> VisibleLogEndAnalysisResult:
    """Analyze visible log-end candidates across overlapping front views.

    ``rgb`` must already be normalized to floating-point values in ``[0, 1]``.
    Source indices attached to candidate evidence always refer to rows of the
    supplied ``xyz`` array.

    Association is constrained so one resolved association contains at most
    one observation from each front-view window.
    """

    resolved_xyz, resolved_rgb = _validate_inputs(
        xyz,
        rgb,
    )

    resolved_config = config if config is not None else VisibleLogEndAnalysisConfig()

    resolved_detector_config = (
        detector_config if detector_config is not None else LogEndDetectionConfig()
    )

    resolved_association_config = (
        association_config
        if association_config is not None
        else CandidateEvidenceAssociationConfig()
    )

    _validate_config(resolved_config)

    observations: list[ProjectedLogEndCandidateEvidence] = []

    observation_window_indices: list[int] = []

    window_summaries: list[VisibleLogEndWindowSummary] = []

    for window_index in range(resolved_config.n_windows):
        projection = build_local_front_view_projection(
            resolved_xyz,
            LocalFrontViewConfig(
                window_index=window_index,
                yaw_degrees=resolved_config.yaw_degrees,
                n_windows=resolved_config.n_windows,
                window_overlap_factor=(resolved_config.window_overlap_factor),
                raster_width=resolved_config.raster_width,
                raster_height=resolved_config.raster_height,
                longitudinal_quantile_low=(resolved_config.longitudinal_quantile_low),
                longitudinal_quantile_high=(resolved_config.longitudinal_quantile_high),
                image_quantile_low=(resolved_config.image_quantile_low),
                image_quantile_high=(resolved_config.image_quantile_high),
                use_min_depth=resolved_config.use_min_depth,
            ),
        )

        image = render_visible_rgb(
            resolved_rgb,
            projection,
        )

        detection = detect_log_end_candidates(
            image,
            resolved_detector_config,
        )

        evidence = project_log_end_candidates_with_support(
            detection.candidates,
            projection,
        )

        observations.extend(evidence.candidates)

        observation_window_indices.extend([window_index] * evidence.candidate_count)

        window_summaries.append(
            VisibleLogEndWindowSummary(
                window_index=window_index,
                visible_point_count=len(projection.visible_source_indices),
                raw_candidate_count=(detection.raw_candidate_count),
                candidate_count=(evidence.candidate_count),
                supported_candidate_count=(evidence.candidates_with_visible_support),
                candidate_area_sum_source_units_squared=(
                    evidence.candidate_area_sum_source_units_squared
                ),
                visible_source_union_count=(evidence.visible_source_union_count),
                horizontal_units_per_pixel=(projection.horizontal_units_per_pixel),
                vertical_units_per_pixel=(projection.vertical_units_per_pixel),
            )
        )

    observation_tuple = tuple(observations)

    window_index_tuple = tuple(observation_window_indices)

    association_summary = associate_projected_log_end_evidence(
        observation_tuple,
        resolved_association_config,
        observation_group_ids=(window_index_tuple),
    )

    resolved_summary = resolve_log_end_candidate_associations(
        observation_tuple,
        association_summary,
    )

    return VisibleLogEndAnalysisResult(
        config=resolved_config,
        detector_config=resolved_detector_config,
        association_config=(resolved_association_config),
        windows=tuple(window_summaries),
        observations=observation_tuple,
        observation_window_indices=(window_index_tuple),
        association_summary=association_summary,
        resolved_summary=resolved_summary,
    )
