from __future__ import annotations

import numpy as np

from lidar_core.timber_stack import (
    TimberStackDetectionConfig,
    detect_timber_stack,
)


def test_detect_timber_stack_finds_elongated_vertical_wall() -> None:
    rng = np.random.default_rng(7)

    # Synthetic timber wall:
    # long in X, narrow in Y, vertically extended in Z.
    stack_count = 40_000
    stack = np.column_stack(
        (
            rng.uniform(-25.0, 25.0, stack_count),
            rng.normal(3.0, 0.12, stack_count),
            rng.uniform(1.0, 6.0, stack_count),
        )
    )

    # Flat ground:
    # very long, but with almost no vertical extent.
    ground_count = 30_000
    ground = np.column_stack(
        (
            rng.uniform(-25.0, 25.0, ground_count),
            rng.uniform(-5.0, 5.0, ground_count),
            rng.normal(0.0, 0.02, ground_count),
        )
    )

    # Tall compact clutter:
    # vertically extended, but not longitudinally persistent.
    clutter_count = 8_000
    clutter = np.column_stack(
        (
            rng.normal(0.0, 0.35, clutter_count),
            rng.normal(-3.0, 0.25, clutter_count),
            rng.uniform(0.5, 6.0, clutter_count),
        )
    )

    points = np.vstack((stack, ground, clutter))

    result = detect_timber_stack(
        points,
        TimberStackDetectionConfig(
            longitudinal_bins=80,
            transverse_bins=40,
            vertical_bins=40,
            min_longitudinal_coverage=0.15,
            min_vertical_extent_fraction=0.20,
            ignore_lowest_vertical_fraction=0.08,
            pca_sample_size=100_000,
            seed=42,
        ),
    )

    stack_selected = result.mask[:stack_count]
    non_stack_selected = result.mask[stack_count:]

    recall = float(stack_selected.mean())
    contamination = float(non_stack_selected.sum() / max(result.selected_point_count, 1))

    assert recall > 0.90
    assert contamination < 0.05
    assert result.longitudinal_coverage > 0.80
    assert result.vertical_extent_fraction > 0.50
    assert result.selected_point_count > 0
