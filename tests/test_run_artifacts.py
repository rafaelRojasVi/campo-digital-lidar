from __future__ import annotations

import json

import numpy as np

from lidar_io.run_artifacts import write_front_profile_artifact
from lidar_volume.front_cross_section import FrontCrossSectionEstimate


def _estimate() -> FrontCrossSectionEstimate:
    return FrontCrossSectionEstimate(
        center_xy=np.array([0.0, 0.0]),
        longitudinal_axis=np.array([1.0, 0.0]),
        longitudinal_min=-1.0,
        longitudinal_max=1.0,
        longitudinal_span=2.0,
        bin_edges=np.array([-1.0, 0.0, 1.0]),
        bin_centres=np.array([-0.5, 0.5]),
        point_counts=np.array([300, 280]),
        base_raw=np.array([1.0, np.nan]),
        top_raw=np.array([3.0, np.nan]),
        base=np.array([1.0, 1.0]),
        top=np.array([3.0, 3.5]),
        height=np.array([2.0, 2.5]),
        valid_bin_fraction=0.5,
        rectangle_area=4.5,
        trapezoid_area=2.25,
    )


def test_write_front_profile_artifact_persists_plot_ready_data(
    tmp_path,
) -> None:
    artifact = write_front_profile_artifact(
        _estimate(),
        tmp_path,
    )

    assert artifact.kind == "front_profile"
    assert artifact.path == "front_profile.json"
    assert artifact.media_type == "application/json"

    path = tmp_path / artifact.path
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1"
    assert payload["coordinate_units"] == "source_units"
    assert payload["longitudinal_span"] == 2.0
    assert payload["rectangle_area"] == 4.5

    assert len(payload["bins"]) == 2

    first = payload["bins"][0]
    assert first["station"] == -0.5
    assert first["point_count"] == 300
    assert first["base_raw"] == 1.0
    assert first["top_raw"] == 3.0
    assert first["height"] == 2.0

    second = payload["bins"][1]
    assert second["base_raw"] is None
    assert second["top_raw"] is None
    assert second["base"] == 1.0
    assert second["top"] == 3.5
    assert second["height"] == 2.5


def test_front_profile_json_contains_no_nonstandard_nan(
    tmp_path,
) -> None:
    artifact = write_front_profile_artifact(
        _estimate(),
        tmp_path,
    )

    text = (tmp_path / artifact.path).read_text(encoding="utf-8")

    assert "NaN" not in text


def test_write_front_profile_plot_artifact_creates_png(
    tmp_path,
) -> None:
    from lidar_io.run_artifacts import (
        write_front_profile_plot_artifact,
    )

    artifact = write_front_profile_plot_artifact(
        _estimate(),
        tmp_path,
    )

    assert artifact.kind == "front_profile_plot"
    assert artifact.path == "front_profile.png"
    assert artifact.media_type == "image/png"

    path = tmp_path / artifact.path

    assert path.exists()
    assert path.stat().st_size > 1_000
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_write_front_height_profile_plot_artifact_creates_png(
    tmp_path,
) -> None:
    from lidar_io.run_artifacts import (
        write_front_height_profile_plot_artifact,
    )

    artifact = write_front_height_profile_plot_artifact(
        _estimate(),
        tmp_path,
    )

    assert artifact.kind == "front_height_profile_plot"
    assert artifact.path == "front_height_profile.png"
    assert artifact.media_type == "image/png"

    path = tmp_path / artifact.path

    assert path.exists()
    assert path.stat().st_size > 1_000
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
