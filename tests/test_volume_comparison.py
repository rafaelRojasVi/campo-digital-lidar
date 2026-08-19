from __future__ import annotations

import pytest

from lidar_core.models import (
    BoundingBox3D,
    ReferenceMeasurement,
    VolumeResult,
    VolumeUnit,
)
from lidar_core.volume_comparison import compare_volume_result


def _estimate(
    volume: float,
    unit: VolumeUnit = VolumeUnit.CUBIC_UNITS_UNSPECIFIED,
) -> VolumeResult:
    return VolumeResult(
        method="test_estimator",
        volume=volume,
        volume_unit=unit,
        point_count_input=1000,
        point_count_used=800,
        bounds=BoundingBox3D(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=10,
            max_y=2,
            max_z=3,
        ),
        runtime_seconds=0.1,
    )


def _reference(
    value: float,
    unit: VolumeUnit = VolumeUnit.CUBIC_UNITS_UNSPECIFIED,
) -> ReferenceMeasurement:
    return ReferenceMeasurement(
        label="test_reference",
        value=value,
        unit=unit,
        method="synthetic_test",
    )


def test_compare_volume_result_exact_match() -> None:
    comparison = compare_volume_result(
        _estimate(100.0),
        _reference(100.0),
    )

    assert comparison.signed_error == 0.0
    assert comparison.absolute_error == 0.0
    assert comparison.relative_error == 0.0
    assert comparison.absolute_relative_error == 0.0
    assert comparison.percent_error == 0.0
    assert comparison.absolute_percent_error == 0.0


def test_compare_volume_result_overestimate() -> None:
    comparison = compare_volume_result(
        _estimate(110.0),
        _reference(100.0),
    )

    assert comparison.signed_error == pytest.approx(10.0)
    assert comparison.absolute_error == pytest.approx(10.0)
    assert comparison.relative_error == pytest.approx(0.10)
    assert comparison.absolute_relative_error == pytest.approx(0.10)
    assert comparison.percent_error == pytest.approx(10.0)
    assert comparison.absolute_percent_error == pytest.approx(10.0)


def test_compare_volume_result_underestimate() -> None:
    comparison = compare_volume_result(
        _estimate(90.0),
        _reference(100.0),
    )

    assert comparison.signed_error == pytest.approx(-10.0)
    assert comparison.absolute_error == pytest.approx(10.0)
    assert comparison.relative_error == pytest.approx(-0.10)
    assert comparison.absolute_relative_error == pytest.approx(0.10)
    assert comparison.percent_error == pytest.approx(-10.0)


def test_compare_volume_result_rejects_unit_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="units must match exactly",
    ):
        compare_volume_result(
            _estimate(
                100.0,
                VolumeUnit.CUBIC_UNITS_UNSPECIFIED,
            ),
            _reference(
                100.0,
                VolumeUnit.CUBIC_METERS,
            ),
        )


def test_compare_volume_result_zero_reference_has_no_relative_error() -> None:
    comparison = compare_volume_result(
        _estimate(10.0),
        _reference(0.0),
    )

    assert comparison.signed_error == 10.0
    assert comparison.absolute_error == 10.0

    assert comparison.relative_error is None
    assert comparison.absolute_relative_error is None
    assert comparison.percent_error is None
    assert comparison.absolute_percent_error is None
