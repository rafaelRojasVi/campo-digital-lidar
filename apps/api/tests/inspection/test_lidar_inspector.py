"""LiDAR inspector: wraps the existing header/bounds forensic inspection."""

from __future__ import annotations

from pathlib import Path

import laspy
import numpy as np
from app.inspection.lidar_inspector import inspect_lidar_file


def _make_minimal_las(path: Path) -> Path:
    header = laspy.LasHeader(point_format=3, version="1.2")
    las = laspy.LasData(header)
    las.x = np.array([0.0, 1.0, 2.0])
    las.y = np.array([0.0, 1.0, 2.0])
    las.z = np.array([0.0, 1.0, 2.0])
    las.write(path)
    return path


def test_reports_point_count_and_version(tmp_path: Path) -> None:
    las_path = _make_minimal_las(tmp_path / "sample.las")
    result = inspect_lidar_file(las_path)
    assert result.point_count == 3
    assert result.las_version == "1.2"
    assert result.point_format_id == 3


def test_reports_bounds_tuple_of_six_floats(tmp_path: Path) -> None:
    las_path = _make_minimal_las(tmp_path / "sample2.las")
    result = inspect_lidar_file(las_path)
    assert len(result.bounds) == 6


def test_reports_crs_explicit_flag(tmp_path: Path) -> None:
    las_path = _make_minimal_las(tmp_path / "sample3.las")
    result = inspect_lidar_file(las_path)
    assert result.crs_is_explicit is False
