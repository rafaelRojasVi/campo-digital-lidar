from __future__ import annotations

import laspy
import numpy as np
import pytest

from lidar_io.analyze import analyze_las


def test_acquisition_analysis_detects_time_order_and_returns(
    tmp_las_path,
    las_writer,
):
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 1.0],
            [2.0, 1.0, 2.0],
            [3.0, 1.0, 3.0],
            [4.0, 2.0, 4.0],
            [5.0, 2.0, 5.0],
        ],
        dtype=float,
    )
    las_writer(tmp_las_path, points)

    las = laspy.read(tmp_las_path)
    las.gps_time = np.array([10.0, 10.1, 10.1, 10.3, 10.2, 10.4])
    las.intensity = np.array([10, 20, 30, 40, 50, 60], dtype=np.uint16)
    las.return_number = np.array([1, 2, 1, 2, 1, 2], dtype=np.uint8)
    las.number_of_returns = np.array([2, 2, 2, 2, 2, 2], dtype=np.uint8)
    las.scan_angle_rank = np.array([0, 1, 2, 3, 4, 5], dtype=np.int8)
    las.point_source_id = np.array([7, 7, 7, 7, 7, 7], dtype=np.uint16)
    las.red = np.array([1, 2, 3, 4, 5, 6], dtype=np.uint16)
    las.green = np.array([11, 12, 13, 14, 5, 16], dtype=np.uint16)
    las.blue = np.array([21, 22, 23, 24, 25, 26], dtype=np.uint16)
    las.write(tmp_las_path)

    result = analyze_las(tmp_las_path)

    assert result.point_count == 6
    assert result.gps_time_present is True
    assert result.gps_time_min == pytest.approx(10.0)
    assert result.gps_time_max == pytest.approx(10.4)
    assert result.gps_time_span == pytest.approx(0.4)
    assert result.gps_time_backward_steps == 1
    assert result.gps_time_equal_steps == 1
    assert result.gps_time_non_decreasing is False
    assert result.gps_time_min_positive_step == pytest.approx(0.1)
    assert result.gps_time_max_positive_step == pytest.approx(0.2)

    assert result.intensity is not None
    assert result.intensity.minimum == pytest.approx(10.0)
    assert result.intensity.maximum == pytest.approx(60.0)
    assert result.intensity.mean == pytest.approx(35.0)

    assert result.return_number_counts == {1: 3, 2: 3}
    assert result.number_of_returns_counts == {2: 6}
    assert result.point_source_id_counts == {7: 6}
    assert len(result.return_summaries) == 2

    assert result.xy_density_points_per_square_source_unit == pytest.approx(0.6)
    assert any("not strictly" in warning for warning in result.warnings)


def test_acquisition_analysis_missing_file():
    with pytest.raises(FileNotFoundError):
        analyze_las("/definitely/not/here.las")
