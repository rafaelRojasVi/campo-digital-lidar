from __future__ import annotations

import numpy as np

from lidar_core.log_ends import (
    LogEndDetectionConfig,
    detect_log_end_candidates,
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


def test_detect_log_end_candidates_on_synthetic_face() -> None:
    rng = np.random.default_rng(7)

    image = np.ones(
        (140, 320, 3),
        dtype=np.float64,
    )

    # Dark timber-stack background.
    image[20:125, 15:305] = (
        0.25,
        0.18,
        0.12,
    )

    expected_centres = [
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

    for x, y in expected_centres:
        radius = int(rng.integers(7, 10))

        _paint_disk(
            image,
            x,
            y,
            radius,
            (
                0.72 + rng.uniform(-0.04, 0.04),
                0.55 + rng.uniform(-0.04, 0.04),
                0.32 + rng.uniform(-0.04, 0.04),
            ),
        )

    result = detect_log_end_candidates(
        image,
        LogEndDetectionConfig(
            candidate_percentile=90.0,
            min_contrast=0.01,
            min_patch_occupancy=0.70,
            mask_erode_iterations=1,
        ),
    )

    detected = np.array(
        [[candidate.x_px, candidate.y_px] for candidate in result.candidates],
        dtype=float,
    )

    assert len(detected) >= 12

    matched = 0

    for expected_x, expected_y in expected_centres:
        distances = np.hypot(
            detected[:, 0] - expected_x,
            detected[:, 1] - expected_y,
        )

        if distances.min() <= 5.0:
            matched += 1

    assert matched >= 12
