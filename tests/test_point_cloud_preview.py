from __future__ import annotations

import json

import numpy as np
import pytest

from lidar_io.point_cloud_preview import (
    write_timber_stack_preview_artifacts,
)
from lidar_volume.front_cross_section import FrontCrossSectionEstimate


def _estimate() -> FrontCrossSectionEstimate:
    return FrontCrossSectionEstimate(
        center_xy=np.array([105.0, 202.5]),
        longitudinal_axis=np.array([1.0, 0.0]),
        longitudinal_min=-5.0,
        longitudinal_max=5.0,
        longitudinal_span=10.0,
        bin_edges=np.array([-5.0, 0.0, 5.0]),
        bin_centres=np.array([-2.5, 2.5]),
        point_counts=np.array([500, 500]),
        base_raw=np.array([10.0, 10.0]),
        top_raw=np.array([14.0, 14.0]),
        base=np.array([10.0, 10.0]),
        top=np.array([14.0, 14.0]),
        height=np.array([4.0, 4.0]),
        valid_bin_fraction=1.0,
        rectangle_area=40.0,
        trapezoid_area=20.0,
    )


def _points() -> np.ndarray:
    rng = np.random.default_rng(7)

    return np.column_stack(
        [
            rng.uniform(100.0, 110.0, 1_000),
            rng.uniform(200.0, 205.0, 1_000),
            rng.uniform(10.0, 14.0, 1_000),
        ]
    )


def _read_ply_positions(path) -> np.ndarray:
    payload = path.read_bytes()
    header, body = payload.split(b"end_header\n", 1)

    vertex_line = next(
        line for line in header.decode("ascii").splitlines() if line.startswith("element vertex ")
    )
    count = int(vertex_line.split()[-1])

    positions = np.frombuffer(
        body,
        dtype="<f4",
    )

    return positions.reshape(count, 3)


def test_preview_artifacts_are_bounded_and_rebased(tmp_path) -> None:
    ply_artifact, manifest_artifact = write_timber_stack_preview_artifacts(
        _points(),
        _estimate(),
        tmp_path,
        max_points=100,
        seed=123,
    )

    assert ply_artifact.kind == "timber_stack_point_cloud_preview"
    assert ply_artifact.path == "timber_stack_preview.ply"
    assert ply_artifact.media_type == "application/octet-stream"

    assert manifest_artifact.kind == "timber_stack_point_cloud_preview_manifest"
    assert manifest_artifact.path == "timber_stack_preview.json"
    assert manifest_artifact.media_type == "application/json"

    manifest = json.loads(
        (tmp_path / manifest_artifact.path).read_text(
            encoding="utf-8",
        )
    )

    assert manifest["schema_version"] == "1"
    assert manifest["source_point_count"] == 1_000
    assert manifest["preview_point_count"] == 100
    assert manifest["coordinate_units"] == "source_units"
    assert manifest["coordinate_space"] == "rebased_source_coordinates"
    assert manifest["position_encoding"] == "float32"
    assert manifest["sampling"] == {
        "method": "uniform_without_replacement",
        "max_points": 100,
        "seed": 123,
    }

    positions = _read_ply_positions(
        tmp_path / ply_artifact.path,
    )

    assert positions.shape == (100, 3)
    assert np.isfinite(positions).all()

    # Rebasing should keep browser-side float32 coordinates local rather
    # than retaining large absolute source-coordinate magnitudes.
    assert np.abs(positions).max() < 10.0


def test_preview_generation_is_deterministic(tmp_path) -> None:
    points = _points()

    first = tmp_path / "first"
    second = tmp_path / "second"

    first_ply, first_manifest = write_timber_stack_preview_artifacts(
        points,
        _estimate(),
        first,
        max_points=125,
        seed=42,
    )
    second_ply, second_manifest = write_timber_stack_preview_artifacts(
        points,
        _estimate(),
        second,
        max_points=125,
        seed=42,
    )

    assert (
        first.joinpath(first_ply.path).read_bytes() == second.joinpath(second_ply.path).read_bytes()
    )
    assert (
        first.joinpath(first_manifest.path).read_bytes()
        == second.joinpath(second_manifest.path).read_bytes()
    )


def test_preview_keeps_all_points_when_under_limit(tmp_path) -> None:
    points = _points()[:25]

    ply_artifact, manifest_artifact = write_timber_stack_preview_artifacts(
        points,
        _estimate(),
        tmp_path,
        max_points=100,
    )

    manifest = json.loads(
        (tmp_path / manifest_artifact.path).read_text(
            encoding="utf-8",
        )
    )

    assert manifest["source_point_count"] == 25
    assert manifest["preview_point_count"] == 25
    assert _read_ply_positions(tmp_path / ply_artifact.path).shape == (25, 3)


@pytest.mark.parametrize(
    "points",
    [
        np.empty((0, 3)),
        np.array([[1.0, 2.0]]),
        np.array([[1.0, 2.0, np.nan]]),
    ],
)
def test_preview_rejects_invalid_point_arrays(
    tmp_path,
    points,
) -> None:
    with pytest.raises(ValueError):
        write_timber_stack_preview_artifacts(
            points,
            _estimate(),
            tmp_path,
        )


def test_preview_rejects_non_positive_limit(tmp_path) -> None:
    with pytest.raises(
        ValueError,
        match="max_points must be >= 1",
    ):
        write_timber_stack_preview_artifacts(
            _points(),
            _estimate(),
            tmp_path,
            max_points=0,
        )
