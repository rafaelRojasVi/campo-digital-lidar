from __future__ import annotations

import numpy as np

from lidar_core.front_view import (
    LocalFrontViewConfig,
    backproject_visible_pixel_disk,
    build_local_front_view_projection,
)


def test_local_front_view_preserves_source_indices() -> None:
    x_values = np.linspace(
        0.0,
        20.0,
        101,
    )

    z_values = np.linspace(
        0.0,
        5.0,
        26,
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

    projection = build_local_front_view_projection(
        xyz,
        LocalFrontViewConfig(
            window_index=0,
            yaw_degrees=0.0,
            n_windows=1,
            window_overlap_factor=1.0,
            raster_width=100,
            raster_height=50,
            longitudinal_quantile_low=0.0,
            longitudinal_quantile_high=1.0,
            image_quantile_low=0.0,
            image_quantile_high=1.0,
        ),
    )

    assert len(projection.visible_source_indices) > 0

    assert np.all(projection.visible_source_indices >= 0)

    assert np.all(projection.visible_source_indices < len(xyz))

    occupied = np.argwhere(projection.visible_index_image >= 0)

    assert len(occupied) > 0

    y_px, x_px = occupied[len(occupied) // 2]

    expected_source_index = int(
        projection.visible_index_image[
            y_px,
            x_px,
        ]
    )

    recovered = backproject_visible_pixel_disk(
        projection,
        x_px=float(x_px),
        y_px=float(y_px),
        radius_px=1.0,
    )

    assert expected_source_index in recovered

    recovered_xyz = xyz[expected_source_index]

    assert np.isfinite(recovered_xyz).all()


def test_local_front_view_pixel_scale_is_positive() -> None:
    rng = np.random.default_rng(42)

    xyz = np.column_stack(
        (
            rng.uniform(0, 20, 5000),
            rng.normal(0, 0.5, 5000),
            rng.uniform(0, 5, 5000),
        )
    )

    projection = build_local_front_view_projection(
        xyz,
        LocalFrontViewConfig(
            window_index=3,
            yaw_degrees=-10.0,
        ),
    )

    assert projection.horizontal_units_per_pixel > 0

    assert projection.vertical_units_per_pixel > 0
