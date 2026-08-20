from __future__ import annotations

import struct

from lidar_core.testing import cube
from lidar_io.inspect import inspect_las


def test_scale_offset_roundtrip(tmp_las_path, las_writer):
    points, _ = cube(size=1.0, n_points=500, seed=1)
    scales = (0.0001, 0.0001, 0.0001)
    offsets = (100.0, 200.0, 0.0)
    las_writer(tmp_las_path, points, scales=scales, offsets=offsets)

    meta = inspect_las(tmp_las_path)
    assert meta.scales == scales
    assert meta.offsets == offsets
    assert meta.point_count == 500

    # The header offset only affects internal integer quantization, not
    # the real-world x/y/z values we assigned -- bounds should match the
    # input points directly, within quantization error bounded by scale.
    assert abs(meta.bounds.min_x - points[:, 0].min()) < scales[0] * 2
    assert abs(meta.bounds.max_x - points[:, 0].max()) < scales[0] * 2


def test_crs_missing_is_reported(tmp_las_path, las_writer):
    points, _ = cube(n_points=100, seed=2)
    las_writer(tmp_las_path, points)
    meta = inspect_las(tmp_las_path)
    assert meta.coordinate_metadata.is_explicit is False
    assert any("CRS" in w for w in meta.warnings)


def test_observed_bounds_override_stale_header(tmp_las_path, las_writer):
    points, _ = cube(size=1.0, n_points=500, seed=3)
    scales = (0.0001, 0.0001, 0.0001)

    las_writer(
        tmp_las_path,
        points,
        scales=scales,
        offsets=(100.0, 200.0, 0.0),
    )

    # Deliberately corrupt only the LAS-declared X bounds.
    # LAS 1.x fixed-header offsets:
    # max X = byte 179
    # min X = byte 187
    with open(tmp_las_path, "r+b") as f:
        f.seek(179)
        f.write(struct.pack("<d", 9999.0))

        f.seek(187)
        f.write(struct.pack("<d", -9999.0))

    meta = inspect_las(tmp_las_path)

    assert meta.header_bounds.max_x == 9999.0
    assert meta.header_bounds.min_x == -9999.0

    assert abs(meta.bounds.min_x - points[:, 0].min()) < scales[0] * 2
    assert abs(meta.bounds.max_x - points[:, 0].max()) < scales[0] * 2

    assert meta.header_bounds_match is False
    assert any("header bounds differ" in warning.lower() for warning in meta.warnings)


def _write_crs_fixture(
    path,
    crs_input,
) -> None:
    import laspy
    from pyproj import CRS

    header = laspy.LasHeader(
        point_format=6,
        version="1.4",
    )
    header.add_crs(CRS.from_user_input(crs_input))

    las = laspy.LasData(header)
    las.x = [500000.0, 500001.0, 500002.0]
    las.y = [4700000.0, 4700001.0, 4700002.0]
    las.z = [100.0, 101.0, 102.0]
    las.write(path)


def test_inspect_extracts_metric_horizontal_units_from_crs(
    tmp_path,
):
    source = tmp_path / "metric-crs.las"

    _write_crs_fixture(
        source,
        "EPSG:26915",
    )

    meta = inspect_las(source)
    coordinate = meta.coordinate_metadata

    assert coordinate.is_explicit is True
    assert coordinate.crs_epsg == 26915
    assert coordinate.horizontal_units == "metre"


def test_inspect_extracts_foot_horizontal_units_from_crs(
    tmp_path,
):
    source = tmp_path / "foot-crs.las"

    _write_crs_fixture(
        source,
        "EPSG:6499",
    )

    meta = inspect_las(source)
    coordinate = meta.coordinate_metadata

    assert coordinate.is_explicit is True
    assert coordinate.crs_epsg == 6499
    assert coordinate.horizontal_units == "foot"


def test_compound_crs_preserves_horizontal_units_without_single_epsg(
    tmp_path,
):
    source = tmp_path / "compound-crs.las"

    _write_crs_fixture(
        source,
        "EPSG:6499+8228",
    )

    meta = inspect_las(source)
    coordinate = meta.coordinate_metadata

    assert coordinate.is_explicit is True
    assert coordinate.crs_epsg is None
    assert coordinate.horizontal_units == "foot"
    assert coordinate.crs_wkt is not None
