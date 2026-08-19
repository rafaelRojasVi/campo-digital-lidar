from __future__ import annotations

import numpy as np
import pytest

from lidar_volume.front_cross_section import (
    FrontCrossSectionConfig,
    estimate_front_cross_section,
    extruded_volume,
)


def test_estimates_rectangular_cross_section() -> None:
    x_values = np.linspace(
        0.0,
        10.0,
        201,
    )

    z_values = np.linspace(
        0.0,
        2.0,
        81,
    )

    xx, zz = np.meshgrid(
        x_values,
        z_values,
    )

    xyz = np.column_stack(
        (
            xx.ravel(),
            np.zeros(xx.size),
            zz.ravel(),
        )
    )

    result = estimate_front_cross_section(
        xyz,
        FrontCrossSectionConfig(
            n_bins=50,
            longitudinal_quantile_low=0.0,
            longitudinal_quantile_high=1.0,
            vertical_quantile_low=0.0,
            vertical_quantile_high=1.0,
            min_points_per_bin=100,
        ),
    )

    assert result.longitudinal_span == pytest.approx(
        10.0,
        rel=0.01,
    )

    assert np.median(result.height) == pytest.approx(
        2.0,
        rel=0.01,
    )

    assert result.rectangle_area == pytest.approx(
        20.0,
        rel=0.03,
    )

    assert result.trapezoid_area == pytest.approx(
        20.0,
        rel=0.05,
    )


def test_extruded_volume_uses_area_times_depth() -> None:
    assert extruded_volume(
        20.0,
        3.0,
    ) == pytest.approx(60.0)


def test_extruded_volume_rejects_negative_depth() -> None:
    with pytest.raises(
        ValueError,
        match="depth must be non-negative",
    ):
        extruded_volume(
            20.0,
            -1.0,
        )
