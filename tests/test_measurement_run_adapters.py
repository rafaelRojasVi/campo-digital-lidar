from __future__ import annotations

import numpy as np

from lidar_core.log_ends_radial import (
    RadialLogEndCandidate,
    RadialLogEndDetectionConfig,
    RadialLogEndDetectionResult,
)
from lidar_core.measurement_run import (
    summarize_front_cross_section,
    summarize_radial_log_detection,
    summarize_timber_stack,
)
from lidar_core.timber_stack import (
    TimberStackDetectionConfig,
    TimberStackDetectionResult,
)
from lidar_volume.front_cross_section import (
    FrontCrossSectionConfig,
    FrontCrossSectionEstimate,
)


def test_summarize_timber_stack_preserves_result_and_config() -> None:
    result = TimberStackDetectionResult(
        mask=np.array([True, True, False, False, False]),
        center_xy=np.array([10.0, 20.0]),
        longitudinal_axis=np.array([1.0, 0.0]),
        transverse_axis=np.array([0.0, 1.0]),
        selected_point_count=2,
        selected_point_fraction=0.4,
        longitudinal_coverage=0.82,
        vertical_extent_fraction=0.77,
        transverse_extent_fraction=0.21,
        score=0.084,
        component_count=3,
    )

    config = TimberStackDetectionConfig(
        longitudinal_bins=80,
        transverse_bins=32,
        vertical_bins=40,
    )

    summary = summarize_timber_stack(
        result,
        point_count_input=5,
        config=config,
    )

    assert summary.point_count_input == 5
    assert summary.point_count_selected == 2
    assert summary.selected_fraction == 0.4
    assert summary.detected_components == 3
    assert summary.longitudinal_coverage == 0.82
    assert summary.vertical_extent_fraction == 0.77
    assert summary.transverse_extent_fraction == 0.21

    assert summary.parameters["longitudinal_bins"] == 80
    assert summary.parameters["transverse_bins"] == 32
    assert summary.parameters["vertical_bins"] == 40


def test_summarize_front_cross_section_uses_finite_height_statistics() -> None:
    result = FrontCrossSectionEstimate(
        center_xy=np.array([0.0, 0.0]),
        longitudinal_axis=np.array([1.0, 0.0]),
        longitudinal_min=-2.0,
        longitudinal_max=2.0,
        longitudinal_span=4.0,
        bin_edges=np.array([-2.0, -1.0, 0.0, 1.0, 2.0]),
        bin_centres=np.array([-1.5, -0.5, 0.5, 1.5]),
        point_counts=np.array([300, 320, 310, 305]),
        base_raw=np.array([0.0, 0.1, np.nan, 0.0]),
        top_raw=np.array([2.0, 2.5, np.nan, 3.0]),
        base=np.array([0.0, 0.1, 0.1, 0.0]),
        top=np.array([2.0, 2.5, 2.5, 3.0]),
        height=np.array([2.0, 2.4, np.nan, 3.0]),
        valid_bin_fraction=0.75,
        rectangle_area=9.2,
        trapezoid_area=8.9,
    )

    config = FrontCrossSectionConfig(
        n_bins=4,
        vertical_quantile_low=0.05,
        vertical_quantile_high=0.95,
        min_points_per_bin=250,
    )

    summary = summarize_front_cross_section(
        result,
        config=config,
    )

    assert summary.longitudinal_span == 4.0
    assert summary.median_height == 2.4
    assert summary.maximum_height == 3.0
    assert summary.rectangle_area == 9.2
    assert summary.trapezoid_area == 8.9
    assert summary.valid_bin_fraction == 0.75

    assert summary.parameters["n_bins"] == 4
    assert summary.parameters["vertical_quantile_low"] == 0.05
    assert summary.parameters["vertical_quantile_high"] == 0.95


def test_summarize_radial_log_detection_records_runtime_counts() -> None:
    candidates = (
        RadialLogEndCandidate(
            x_px=10.0,
            y_px=20.0,
            radius_px=7.0,
            score=0.9,
            observed_fraction=0.8,
        ),
        RadialLogEndCandidate(
            x_px=30.0,
            y_px=40.0,
            radius_px=8.0,
            score=0.85,
            observed_fraction=0.75,
        ),
    )

    result = RadialLogEndDetectionResult(
        candidates=candidates,
        response=np.zeros((8, 8), dtype=np.float64),
        gradient_magnitude=np.zeros((8, 8), dtype=np.float64),
        observed_mask=np.ones((8, 8), dtype=bool),
        support_mask=np.ones((8, 8), dtype=bool),
        raw_candidate_count=7,
    )

    config = RadialLogEndDetectionConfig(
        min_radius_px=5,
        max_radius_px=10,
        max_candidates=200,
    )

    summary = summarize_radial_log_detection(
        result,
        config=config,
        method="radial-v5",
    )

    assert summary.method == "radial-v5"
    assert summary.candidate_count == 2
    assert summary.parameters["raw_candidate_count"] == 7
    assert summary.parameters["min_radius_px"] == 5
    assert summary.parameters["max_radius_px"] == 10
    assert summary.parameters["max_candidates"] == 200
