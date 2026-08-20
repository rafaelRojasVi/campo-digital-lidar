from __future__ import annotations

import laspy
import numpy as np
import pytest

from lidar_io.dataset_robustness import (
    build_dataset_robustness_report,
)


def _write_rgb_fixture(
    path,
) -> None:
    point_count = 20

    header = laspy.LasHeader(
        point_format=3,
        version="1.2",
    )
    header.scales = np.array(
        [
            0.001,
            0.001,
            0.001,
        ]
    )

    las = laspy.LasData(header)

    las.x = np.linspace(
        0.0,
        10.0,
        point_count,
    )
    las.y = np.linspace(
        0.0,
        2.0,
        point_count,
    )
    las.z = np.linspace(
        1.0,
        3.0,
        point_count,
    )

    las.red = np.linspace(
        0,
        255,
        point_count,
        dtype=np.uint16,
    )
    las.green = np.linspace(
        10,
        200,
        point_count,
        dtype=np.uint16,
    )
    las.blue = np.linspace(
        20,
        180,
        point_count,
        dtype=np.uint16,
    )

    las.gps_time = np.arange(
        point_count,
        dtype=np.float64,
    )

    las.write(path)


def test_build_report_inspection_only(
    tmp_path,
) -> None:
    path = tmp_path / "fixture.las"

    _write_rgb_fixture(path)

    report = build_dataset_robustness_report(
        path,
    )

    assert report.schema_version == "1"
    assert report.path == str(path)
    assert report.file_suffix == ".las"

    assert report.metadata.point_count == 20
    assert report.metadata.sha256 is None

    assert report.acquisition is None
    assert report.acquisition_runtime_seconds is None

    assert report.capabilities.metadata_inspection is True
    assert report.capabilities.acquisition_analysis is False

    assert report.rgb.dimensions_present is True
    assert report.rgb.analyzed is False
    assert report.rgb.usable_for_image_analysis is None

    assert report.inspect_runtime_seconds >= 0.0


def test_build_deep_report_classifies_rgb_payload(
    tmp_path,
) -> None:
    path = tmp_path / "fixture.las"

    _write_rgb_fixture(path)

    report = build_dataset_robustness_report(
        path,
        deep=True,
    )

    assert report.acquisition is not None
    assert report.acquisition.point_count == 20

    assert report.capabilities.acquisition_analysis is True
    assert report.capabilities.rgb_dimensions_present is True
    assert report.capabilities.usable_rgb_payload is True

    assert report.rgb.analyzed is True
    assert report.rgb.usable_for_image_analysis is True
    assert report.rgb.observed_min == 0.0
    assert report.rgb.observed_max == 255.0
    assert report.rgb.normalization_denominator == 255.0
    assert report.rgb.normalization_mode == "eight_bit_payload_in_las_rgb_fields"

    assert report.acquisition_runtime_seconds is not None
    assert report.acquisition_runtime_seconds >= 0.0


def test_build_report_can_compute_checksum(
    tmp_path,
) -> None:
    path = tmp_path / "fixture.las"

    _write_rgb_fixture(path)

    report = build_dataset_robustness_report(
        path,
        compute_checksum=True,
    )

    assert report.metadata.sha256 is not None
    assert len(report.metadata.sha256) == 64


def test_build_report_rejects_unsupported_suffix(
    tmp_path,
) -> None:
    path = tmp_path / "fixture.xyz"
    path.write_text(
        "0 0 0\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="only LAS/LAZ",
    ):
        build_dataset_robustness_report(
            path,
        )


def test_build_report_propagates_missing_file(
    tmp_path,
) -> None:
    with pytest.raises(
        FileNotFoundError,
    ):
        build_dataset_robustness_report(
            tmp_path / "missing.las",
        )


def test_build_matrix_collects_multiple_reports(
    tmp_path,
) -> None:
    first = tmp_path / "first.las"
    second = tmp_path / "second.las"

    _write_rgb_fixture(first)
    _write_rgb_fixture(second)

    from lidar_io.dataset_robustness import (
        build_dataset_robustness_matrix,
    )

    matrix = build_dataset_robustness_matrix(
        [first, second],
    )

    assert matrix.total_datasets == 2
    assert matrix.successful_datasets == 2
    assert matrix.failed_datasets == 0

    assert len(matrix.reports) == 2
    assert matrix.failures == []

    assert matrix.deep is False
    assert matrix.compute_checksum is False
    assert matrix.total_runtime_seconds >= 0.0


def test_build_matrix_isolates_dataset_failures(
    tmp_path,
) -> None:
    valid = tmp_path / "valid.las"
    missing = tmp_path / "missing.las"
    unsupported = tmp_path / "unsupported.xyz"

    _write_rgb_fixture(valid)

    unsupported.write_text(
        "0 0 0\n",
        encoding="utf-8",
    )

    from lidar_io.dataset_robustness import (
        build_dataset_robustness_matrix,
    )

    matrix = build_dataset_robustness_matrix(
        [
            valid,
            missing,
            unsupported,
        ],
    )

    assert matrix.total_datasets == 3
    assert matrix.successful_datasets == 1
    assert matrix.failed_datasets == 2

    assert len(matrix.reports) == 1
    assert len(matrix.failures) == 2

    assert {failure.error_type for failure in matrix.failures} == {
        "FileNotFoundError",
        "ValueError",
    }


def test_build_deep_matrix_propagates_profile(
    tmp_path,
) -> None:
    path = tmp_path / "fixture.las"

    _write_rgb_fixture(path)

    from lidar_io.dataset_robustness import (
        build_dataset_robustness_matrix,
    )

    matrix = build_dataset_robustness_matrix(
        [path],
        deep=True,
    )

    assert matrix.deep is True
    assert matrix.successful_datasets == 1

    report = matrix.reports[0]

    assert report.acquisition is not None
    assert report.rgb.usable_for_image_analysis is True


def test_build_matrix_isolates_corrupt_las(
    tmp_path,
) -> None:
    corrupt = tmp_path / "corrupt.las"
    corrupt.write_bytes(b"this is not a LAS file")

    from lidar_io.dataset_robustness import (
        build_dataset_robustness_matrix,
    )

    matrix = build_dataset_robustness_matrix(
        [corrupt],
    )

    assert matrix.total_datasets == 1
    assert matrix.successful_datasets == 0
    assert matrix.failed_datasets == 1

    assert len(matrix.reports) == 0
    assert len(matrix.failures) == 1

    failure = matrix.failures[0]

    assert failure.path == str(corrupt)
    assert failure.error_type == "LaspyException"
    assert "Invalid file signature" in failure.message
