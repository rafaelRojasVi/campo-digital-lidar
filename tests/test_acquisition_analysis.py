from __future__ import annotations

import laspy
import numpy as np
import pytest

import lidar_io.analyze as analyze_module
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


def test_equal_time_return_pairing(tmp_las_path, las_writer):
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [5.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    las_writer(tmp_las_path, points)

    las = laspy.read(tmp_las_path)
    las.gps_time = np.array([1.0, 1.0, 2.0, 2.0, 2.0, 3.0])
    las.return_number = np.array([1, 2, 1, 1, 2, 2], dtype=np.uint8)
    las.number_of_returns = np.array([2, 2, 2, 2, 2, 2], dtype=np.uint8)
    las.intensity = np.array([10, 20, 30, 40, 55, 60], dtype=np.uint16)
    las.write(tmp_las_path)

    result = analyze_las(tmp_las_path)

    assert result.gps_time_equal_steps == 3
    assert result.equal_time_adjacent_same_return_pairs == 1
    assert result.equal_time_adjacent_cross_return_pairs == 2
    assert result.equal_time_adjacent_r1_r2_pairs == 2
    assert result.equal_time_adjacent_r1_r2_fraction == pytest.approx(2 / 3)

    assert result.paired_return_distance is not None
    assert result.paired_return_distance.minimum == pytest.approx(1.0)
    assert result.paired_return_distance.mean == pytest.approx(1.0)
    assert result.paired_return_distance.maximum == pytest.approx(1.0)

    assert result.paired_return_abs_delta_x is not None
    assert result.paired_return_abs_delta_x.mean == pytest.approx(1.0)

    assert result.paired_return_abs_delta_y is not None
    assert result.paired_return_abs_delta_y.mean == pytest.approx(0.0)

    assert result.paired_return_abs_delta_z is not None
    assert result.paired_return_abs_delta_z.mean == pytest.approx(0.0)

    assert result.paired_return_abs_intensity_delta is not None
    assert result.paired_return_abs_intensity_delta.mean == pytest.approx(12.5)


def test_timestamp_groups_survive_chunk_boundary(
    tmp_las_path,
    las_writer,
    monkeypatch,
):
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    las_writer(tmp_las_path, points)

    las = laspy.read(tmp_las_path)
    las.gps_time = np.array([1.0, 1.0, 2.0, 2.0, 3.0])
    las.return_number = np.array(
        [1, 2, 1, 2, 1],
        dtype=np.uint8,
    )
    las.number_of_returns = np.array(
        [2, 2, 2, 2, 2],
        dtype=np.uint8,
    )
    las.intensity = np.array(
        [10, 20, 30, 40, 50],
        dtype=np.uint16,
    )
    las.write(tmp_las_path)

    # GPS=2 is deliberately split across a LAS streaming boundary.
    monkeypatch.setattr(analyze_module, "_STREAM_CHUNK", 3)

    result = analyze_module.analyze_las(tmp_las_path)

    assert result.timestamp_groups is not None
    groups = result.timestamp_groups

    assert groups.group_count == 3
    assert groups.size_counts == {1: 1, 2: 2}
    assert groups.max_group_size == 2

    assert groups.two_record_groups == 2
    assert groups.two_record_r1_r2_groups == 2
    assert groups.two_record_r1_r2_fraction == pytest.approx(1.0)

    assert groups.two_record_return_pattern_counts["1->2"] == 2
    assert groups.two_record_return_pattern_counts["2->1"] == 0
    assert groups.two_record_return_pattern_counts["1->1"] == 0
    assert groups.two_record_return_pattern_counts["2->2"] == 0

    assert groups.exact_pair_distance is not None
    assert groups.exact_pair_distance.minimum == pytest.approx(1.0)
    assert groups.exact_pair_distance.mean == pytest.approx(1.0)
    assert groups.exact_pair_distance.maximum == pytest.approx(1.0)


def test_legacy_scan_angle_rank_is_also_reported_in_degrees(
    tmp_path,
):
    path = tmp_path / "legacy-scan-angle.las"

    header = laspy.LasHeader(
        point_format=3,
        version="1.2",
    )

    las = laspy.LasData(header)
    las.x = np.array([0.0, 1.0, 2.0])
    las.y = np.zeros(3)
    las.z = np.zeros(3)

    las.gps_time = np.array([1.0, 2.0, 3.0])
    las.return_number = np.ones(3, dtype=np.uint8)
    las.number_of_returns = np.ones(3, dtype=np.uint8)

    las.scan_angle_rank = np.array(
        [-10, 0, 10],
        dtype=np.int8,
    )

    las.write(path)

    result = analyze_las(path)

    assert result.scan_angle_rank is not None
    assert result.scan_angle_rank.minimum == pytest.approx(-10.0)
    assert result.scan_angle_rank.mean == pytest.approx(0.0)
    assert result.scan_angle_rank.maximum == pytest.approx(10.0)

    assert result.scan_angle_degrees is not None
    assert result.scan_angle_degrees.minimum == pytest.approx(-10.0)
    assert result.scan_angle_degrees.mean == pytest.approx(0.0)
    assert result.scan_angle_degrees.maximum == pytest.approx(10.0)


def test_las14_scan_angle_is_normalized_to_degrees(
    tmp_path,
):
    path = tmp_path / "las14-scan-angle.las"

    header = laspy.LasHeader(
        point_format=6,
        version="1.4",
    )

    las = laspy.LasData(header)
    las.x = np.array([0.0, 1.0, 2.0])
    las.y = np.zeros(3)
    las.z = np.zeros(3)

    las.gps_time = np.array([1.0, 2.0, 3.0])
    las.return_number = np.ones(3, dtype=np.uint8)
    las.number_of_returns = np.ones(3, dtype=np.uint8)

    las.scan_angle = np.array(
        [-1000, 0, 1000],
        dtype=np.int16,
    )

    las.write(path)

    result = analyze_las(path)

    # LAS 1.4 formats 6-10 do not expose legacy scan_angle_rank.
    assert result.scan_angle_rank is None

    assert result.scan_angle_degrees is not None
    assert result.scan_angle_degrees.minimum == pytest.approx(-6.0)
    assert result.scan_angle_degrees.mean == pytest.approx(0.0)
    assert result.scan_angle_degrees.maximum == pytest.approx(6.0)
