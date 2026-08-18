from __future__ import annotations

import laspy
import numpy as np
import pytest


def write_las(
    path: str, points: np.ndarray, scales=(0.001, 0.001, 0.001), offsets=(0.0, 0.0, 0.0)
) -> None:
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = list(scales)
    header.offsets = list(offsets)
    las = laspy.LasData(header)
    las.x = points[:, 0]
    las.y = points[:, 1]
    las.z = points[:, 2]
    las.write(path)


@pytest.fixture
def tmp_las_path(tmp_path):
    return str(tmp_path / "synthetic.las")


@pytest.fixture
def las_writer():
    return write_las
