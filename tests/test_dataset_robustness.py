from __future__ import annotations

from lidar_core.dataset_robustness import (
    derive_rgb_payload_capability,
)
from lidar_core.models import (
    AcquisitionAnalysis,
    BoundingBox3D,
    CoordinateMetadata,
    LasMetadata,
    NumericSummary,
    PointDimensions,
)


def _metadata(
    *,
    has_rgb: bool,
) -> LasMetadata:
    bounds = BoundingBox3D(
        min_x=0.0,
        min_y=0.0,
        min_z=0.0,
        max_x=1.0,
        max_y=1.0,
        max_z=1.0,
    )

    return LasMetadata(
        path="fixture.las",
        file_size_bytes=100,
        las_version_major=1,
        las_version_minor=2,
        point_format_id=3 if has_rgb else 1,
        point_count=10,
        scales=(0.001, 0.001, 0.001),
        offsets=(0.0, 0.0, 0.0),
        bounds=bounds,
        header_bounds=bounds,
        header_bounds_match=True,
        coordinate_metadata=CoordinateMetadata(),
        dimensions=PointDimensions(
            has_rgb=has_rgb,
        ),
        vlr_count=0,
        evlr_count=0,
    )


def _acquisition(
    rgb: dict[str, NumericSummary],
) -> AcquisitionAnalysis:
    return AcquisitionAnalysis(
        path="fixture.las",
        point_count=10,
        gps_time_present=False,
        rgb=rgb,
    )


def test_rgb_capability_is_unknown_without_acquisition_analysis() -> None:
    result = derive_rgb_payload_capability(
        _metadata(has_rgb=True),
        None,
    )

    assert result.dimensions_present is True
    assert result.analyzed is False
    assert result.usable_for_image_analysis is None
    assert result.normalization_mode is None


def test_rgb_capability_detects_unpopulated_payload() -> None:
    zero = NumericSummary(
        minimum=0.0,
        maximum=0.0,
        mean=0.0,
    )

    result = derive_rgb_payload_capability(
        _metadata(has_rgb=True),
        _acquisition(
            {
                "red": zero,
                "green": zero,
                "blue": zero,
            }
        ),
    )

    assert result.analyzed is True
    assert result.usable_for_image_analysis is False
    assert result.observed_max == 0.0
    assert result.normalization_mode is None


def test_rgb_capability_detects_eight_bit_payload() -> None:
    result = derive_rgb_payload_capability(
        _metadata(has_rgb=True),
        _acquisition(
            {
                "red": NumericSummary(
                    minimum=0.0,
                    maximum=255.0,
                    mean=100.0,
                ),
                "green": NumericSummary(
                    minimum=5.0,
                    maximum=210.0,
                    mean=90.0,
                ),
                "blue": NumericSummary(
                    minimum=10.0,
                    maximum=190.0,
                    mean=80.0,
                ),
            }
        ),
    )

    assert result.usable_for_image_analysis is True
    assert result.observed_min == 0.0
    assert result.observed_max == 255.0
    assert result.normalization_denominator == 255.0
    assert result.normalization_mode == "eight_bit_payload_in_las_rgb_fields"


def test_rgb_capability_detects_sixteen_bit_payload() -> None:
    result = derive_rgb_payload_capability(
        _metadata(has_rgb=True),
        _acquisition(
            {
                "red": NumericSummary(
                    minimum=0.0,
                    maximum=65535.0,
                    mean=30000.0,
                ),
                "green": NumericSummary(
                    minimum=100.0,
                    maximum=40000.0,
                    mean=20000.0,
                ),
                "blue": NumericSummary(
                    minimum=50.0,
                    maximum=30000.0,
                    mean=15000.0,
                ),
            }
        ),
    )

    assert result.usable_for_image_analysis is True
    assert result.observed_max == 65535.0
    assert result.normalization_denominator == 65535.0
    assert result.normalization_mode == "sixteen_bit_las_rgb_payload"


def test_rgb_capability_records_absent_dimensions() -> None:
    result = derive_rgb_payload_capability(
        _metadata(has_rgb=False),
        _acquisition({}),
    )

    assert result.dimensions_present is False
    assert result.analyzed is True
    assert result.usable_for_image_analysis is False
