from __future__ import annotations

import numpy as np
import pytest

from lidar_core.log_ends import LogEndDetectionConfig
from lidar_core.visible_log_end_analysis import (
    VisibleLogEndAnalysisConfig,
    analyze_visible_log_end_candidates,
)


def _paint_disk(
    image: np.ndarray,
    center_x: int,
    center_y: int,
    radius: int,
    color: tuple[float, float, float],
) -> None:
    yy, xx = np.ogrid[
        : image.shape[0],
        : image.shape[1],
    ]

    mask = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius**2

    image[mask] = color


def _synthetic_colored_front_face() -> tuple[
    np.ndarray,
    np.ndarray,
]:
    height = 140
    width = 320

    image = np.ones(
        (
            height,
            width,
            3,
        ),
        dtype=np.float64,
    )

    image[
        20:125,
        15:305,
    ] = (
        0.25,
        0.18,
        0.12,
    )

    rng = np.random.default_rng(7)

    centres = [
        (45, 45),
        (80, 45),
        (115, 45),
        (150, 45),
        (185, 45),
        (220, 45),
        (255, 45),
        (290, 45),
        (62, 82),
        (98, 82),
        (134, 82),
        (170, 82),
        (206, 82),
        (242, 82),
        (278, 82),
    ]

    for x, y in centres:
        radius = int(
            rng.integers(
                7,
                10,
            )
        )

        _paint_disk(
            image,
            x,
            y,
            radius,
            (
                0.72
                + rng.uniform(
                    -0.04,
                    0.04,
                ),
                0.55
                + rng.uniform(
                    -0.04,
                    0.04,
                ),
                0.32
                + rng.uniform(
                    -0.04,
                    0.04,
                ),
            ),
        )

    rows, columns = np.indices(
        (
            height,
            width,
        )
    )

    xyz = np.column_stack(
        (
            columns.ravel().astype(np.float64),
            np.zeros(
                height * width,
                dtype=np.float64,
            ),
            (height - 1 - rows.ravel()).astype(np.float64),
        )
    )

    rgb = image.reshape(
        -1,
        3,
    )

    return xyz, rgb


def test_visible_log_end_analysis_runs_full_observation_path() -> None:
    xyz, rgb = _synthetic_colored_front_face()

    result = analyze_visible_log_end_candidates(
        xyz,
        rgb,
        config=VisibleLogEndAnalysisConfig(
            n_windows=1,
            window_overlap_factor=1.0,
            yaw_degrees=0.0,
            raster_width=320,
            raster_height=140,
            longitudinal_quantile_low=0.0,
            longitudinal_quantile_high=1.0,
            image_quantile_low=0.0,
            image_quantile_high=1.0,
        ),
        detector_config=LogEndDetectionConfig(
            candidate_percentile=90.0,
            min_contrast=0.01,
            min_patch_occupancy=0.70,
            mask_erode_iterations=1,
        ),
    )

    assert len(result.windows) == 1

    window = result.windows[0]

    assert window.visible_point_count > 0
    assert window.raw_candidate_count > 0
    assert window.candidate_count >= 12

    assert window.supported_candidate_count == window.candidate_count

    assert len(result.observations) == window.candidate_count

    assert set(result.observation_window_indices) == {0}

    # With one front view, no observation can be a cross-window duplicate.
    assert result.association_summary.association_count == window.candidate_count

    assert result.resolved_summary.association_count == window.candidate_count

    assert result.resolved_summary.projected_area_sum_source_units_squared > 0.0

    assert result.resolved_summary.representative_method == "mean_equivalent_diameter"


@pytest.mark.parametrize(
    ("xyz", "rgb", "message"),
    [
        (
            np.zeros(
                (
                    5,
                    2,
                )
            ),
            np.zeros(
                (
                    5,
                    3,
                )
            ),
            "xyz must have shape",
        ),
        (
            np.zeros(
                (
                    5,
                    3,
                )
            ),
            np.zeros(
                (
                    4,
                    3,
                )
            ),
            "one-to-one",
        ),
        (
            np.zeros(
                (
                    5,
                    3,
                )
            ),
            np.full(
                (
                    5,
                    3,
                ),
                2.0,
            ),
            "normalized",
        ),
    ],
)
def test_visible_log_end_analysis_rejects_invalid_inputs(
    xyz: np.ndarray,
    rgb: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=message,
    ):
        analyze_visible_log_end_candidates(
            xyz,
            rgb,
        )
