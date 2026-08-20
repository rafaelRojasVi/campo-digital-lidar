from __future__ import annotations

import laspy
import numpy as np
import pytest

from lidar_io.las_rgb import (
    extract_normalized_las_rgb,
)


def _las_with_rgb(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
) -> laspy.LasData:
    header = laspy.LasHeader(
        point_format=3,
        version="1.2",
    )

    las = laspy.LasData(header)

    point_count = len(red)

    las.x = np.arange(
        point_count,
        dtype=np.float64,
    )
    las.y = np.zeros(
        point_count,
        dtype=np.float64,
    )
    las.z = np.zeros(
        point_count,
        dtype=np.float64,
    )

    las.red = red
    las.green = green
    las.blue = blue

    return las


def test_extract_normalized_las_rgb_returns_none_without_rgb_dimensions() -> None:
    header = laspy.LasHeader(
        point_format=1,
        version="1.2",
    )

    las = laspy.LasData(header)

    las.x = np.array(
        [
            0.0,
            1.0,
        ]
    )
    las.y = np.zeros(2)
    las.z = np.zeros(2)

    assert extract_normalized_las_rgb(las) is None


def test_extract_normalized_las_rgb_returns_none_for_all_zero_rgb() -> None:
    zeros = np.zeros(
        4,
        dtype=np.uint16,
    )

    las = _las_with_rgb(
        zeros,
        zeros,
        zeros,
    )

    assert extract_normalized_las_rgb(las) is None


def test_extract_normalized_las_rgb_detects_eight_bit_payload() -> None:
    las = _las_with_rgb(
        np.array(
            [
                0,
                128,
                255,
            ],
            dtype=np.uint16,
        ),
        np.array(
            [
                10,
                64,
                200,
            ],
            dtype=np.uint16,
        ),
        np.array(
            [
                20,
                32,
                100,
            ],
            dtype=np.uint16,
        ),
    )

    result = extract_normalized_las_rgb(las)

    assert result is not None

    assert result.normalization_mode == "eight_bit_payload_in_las_rgb_fields"

    assert result.normalization_denominator == 255.0

    assert result.payload_min == 0
    assert result.payload_max == 255

    assert result.rgb.shape == (
        3,
        3,
    )

    assert result.rgb[1, 0] == pytest.approx(128.0 / 255.0)

    assert result.rgb.max() == pytest.approx(1.0)


def test_extract_normalized_las_rgb_detects_sixteen_bit_payload() -> None:
    las = _las_with_rgb(
        np.array(
            [
                0,
                32768,
                65535,
            ],
            dtype=np.uint16,
        ),
        np.array(
            [
                1000,
                20000,
                40000,
            ],
            dtype=np.uint16,
        ),
        np.array(
            [
                500,
                10000,
                30000,
            ],
            dtype=np.uint16,
        ),
    )

    result = extract_normalized_las_rgb(las)

    assert result is not None

    assert result.normalization_mode == "sixteen_bit_las_rgb_payload"

    assert result.normalization_denominator == 65535.0

    assert result.payload_min == 0
    assert result.payload_max == 65535

    assert result.rgb[1, 0] == pytest.approx(32768.0 / 65535.0)

    assert result.rgb.max() == pytest.approx(1.0)


def test_extract_normalized_las_rgb_preserves_observed_uint16_storage() -> None:
    las = _las_with_rgb(
        np.array(
            [
                20,
                100,
            ],
            dtype=np.uint16,
        ),
        np.array(
            [
                30,
                110,
            ],
            dtype=np.uint16,
        ),
        np.array(
            [
                40,
                120,
            ],
            dtype=np.uint16,
        ),
    )

    result = extract_normalized_las_rgb(las)

    assert result is not None
    assert result.source_dtype == "uint16"

    assert np.all(result.rgb >= 0.0)

    assert np.all(result.rgb <= 1.0)
