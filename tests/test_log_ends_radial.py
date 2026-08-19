from __future__ import annotations

import numpy as np

from lidar_core.log_ends_radial import (
    RadialLogEndDetectionConfig,
    detect_radial_log_end_candidates,
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


def test_radial_detector_finds_bright_and_dark_log_ends() -> None:
    rng = np.random.default_rng(7)

    image = np.ones(
        (140, 320, 3),
        dtype=np.float64,
    )

    image[20:125, 15:305] = (
        0.25,
        0.18,
        0.12,
    )

    expected = [
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

    for index, (x, y) in enumerate(expected):
        radius = int(rng.integers(7, 10))

        if index % 3 == 0:
            color = (
                0.08,
                0.07,
                0.06,
            )
        else:
            color = (
                0.72 + rng.uniform(-0.04, 0.04),
                0.55 + rng.uniform(-0.04, 0.04),
                0.32 + rng.uniform(-0.04, 0.04),
            )

        _paint_disk(
            image,
            x,
            y,
            radius,
            color,
        )

    result = detect_radial_log_end_candidates(
        image,
        RadialLogEndDetectionConfig(
            response_percentile=98.5,
        ),
    )

    detected = np.array(
        [
            [
                candidate.x_px,
                candidate.y_px,
            ]
            for candidate in result.candidates
        ],
        dtype=float,
    )

    assert len(detected) >= 13

    matched = 0

    for expected_x, expected_y in expected:
        distances = np.hypot(
            detected[:, 0] - expected_x,
            detected[:, 1] - expected_y,
        )

        if distances.min() <= 4.0:
            matched += 1

    assert matched >= 13
