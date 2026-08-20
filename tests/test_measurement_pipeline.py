from __future__ import annotations

import json

import laspy
import numpy as np

from lidar_core.models import MeasurementRunStatus
from lidar_core.timber_stack import TimberStackDetectionConfig
from lidar_io.measurement_pipeline import run_timber_measurement
from lidar_io.run_store import read_measurement_run
from lidar_volume.front_cross_section import FrontCrossSectionConfig


def test_run_timber_measurement_persists_observable_geometry(
    tmp_path,
) -> None:
    rng = np.random.default_rng(42)

    point_count = 8_000

    x = rng.uniform(
        0.0,
        12.0,
        point_count,
    )
    y = rng.normal(
        0.0,
        0.08,
        point_count,
    )
    z = rng.uniform(
        0.5,
        3.5,
        point_count,
    )

    input_path = tmp_path / "synthetic-timber-wall.las"

    header = laspy.LasHeader(
        point_format=3,
        version="1.2",
    )
    header.scales = np.array([0.001, 0.001, 0.001])

    las = laspy.LasData(header)
    las.x = x
    las.y = y
    las.z = z
    las.write(str(input_path))

    run, output_path = run_timber_measurement(
        input_path,
        tmp_path / "reports",
        run_id="run-synthetic-wall",
        timber_config=TimberStackDetectionConfig(
            longitudinal_bins=24,
            transverse_bins=12,
            vertical_bins=12,
            min_longitudinal_coverage=0.10,
            min_vertical_extent_fraction=0.10,
            ignore_lowest_vertical_fraction=0.0,
            pca_sample_size=10_000,
            seed=42,
        ),
        cross_section_config=FrontCrossSectionConfig(
            n_bins=24,
            min_points_per_bin=20,
        ),
        code_version="test",
    )

    assert run.status == MeasurementRunStatus.COMPLETED
    assert run.source_sha256 is not None

    assert run.timber_stack is not None
    assert run.timber_stack.point_count_input == point_count
    assert run.timber_stack.point_count_selected > 0

    assert run.front_cross_section is not None
    assert run.front_cross_section.longitudinal_span > 0
    assert run.front_cross_section.rectangle_area > 0
    assert run.front_cross_section.trapezoid_area > 0

    assert run.results == []

    assert len(run.artifacts) == 5

    artifacts = {artifact.kind: artifact for artifact in run.artifacts}

    assert set(artifacts) == {
        "front_profile",
        "front_profile_plot",
        "front_height_profile_plot",
        "timber_stack_point_cloud_preview",
        "timber_stack_point_cloud_preview_manifest",
    }

    profile = artifacts["front_profile"]
    assert profile.path == "front_profile.json"
    assert profile.media_type == "application/json"
    assert (output_path.parent / profile.path).exists()

    plot = artifacts["front_profile_plot"]
    assert plot.path == "front_profile.png"
    assert plot.media_type == "image/png"

    plot_path = output_path.parent / plot.path
    assert plot_path.exists()
    assert plot_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    height_plot = artifacts["front_height_profile_plot"]
    assert height_plot.path == "front_height_profile.png"
    assert height_plot.media_type == "image/png"

    height_plot_path = output_path.parent / height_plot.path
    assert height_plot_path.exists()
    assert height_plot_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    preview = artifacts["timber_stack_point_cloud_preview"]
    assert preview.path == "timber_stack_preview.ply"
    assert preview.media_type == "application/octet-stream"

    preview_path = output_path.parent / preview.path
    assert preview_path.exists()
    assert preview_path.read_bytes().startswith(b"ply\n")

    preview_manifest = artifacts["timber_stack_point_cloud_preview_manifest"]
    assert preview_manifest.path == "timber_stack_preview.json"
    assert preview_manifest.media_type == "application/json"

    manifest_payload = json.loads(
        (output_path.parent / preview_manifest.path).read_text(
            encoding="utf-8",
        )
    )

    assert manifest_payload["source_point_count"] == run.timber_stack.point_count_selected
    assert manifest_payload["preview_point_count"] == run.timber_stack.point_count_selected
    assert manifest_payload["coordinate_space"] == "rebased_source_coordinates"
    assert manifest_payload["coordinate_units"] == "source_units"

    warning_codes = {warning.code for warning in run.warnings}

    assert "crs_unconfirmed" in warning_codes
    assert "linear_units_unconfirmed" in warning_codes
    assert "pile_depth_not_supplied" in warning_codes

    assert output_path == tmp_path / "reports" / "run-synthetic-wall" / "measurement.json"

    persisted = read_measurement_run(output_path)

    assert persisted == run


def test_run_timber_measurement_with_explicit_depth_persists_volume(
    tmp_path,
) -> None:
    rng = np.random.default_rng(42)
    point_count = 8_000

    input_path = tmp_path / "synthetic-depth-wall.las"

    header = laspy.LasHeader(
        point_format=3,
        version="1.2",
    )
    header.scales = np.array([0.001, 0.001, 0.001])

    las = laspy.LasData(header)
    las.x = rng.uniform(0.0, 12.0, point_count)
    las.y = rng.normal(0.0, 0.08, point_count)
    las.z = rng.uniform(0.5, 3.5, point_count)
    las.write(str(input_path))

    run, output_path = run_timber_measurement(
        input_path,
        tmp_path / "reports",
        run_id="run-explicit-depth",
        timber_config=TimberStackDetectionConfig(
            longitudinal_bins=24,
            transverse_bins=12,
            vertical_bins=12,
            min_longitudinal_coverage=0.10,
            min_vertical_extent_fraction=0.10,
            ignore_lowest_vertical_fraction=0.0,
            pca_sample_size=10_000,
            seed=42,
        ),
        cross_section_config=FrontCrossSectionConfig(
            n_bins=24,
            min_points_per_bin=20,
        ),
        code_version="test",
        pile_depth=2.5,
        depth_source="test_fixture",
    )

    assert run.front_cross_section is not None
    assert len(run.results) == 1

    result = run.results[0]

    assert result.method == "front_cross_section_rectangle_extrusion"
    assert result.volume == (run.front_cross_section.rectangle_area * 2.5)
    assert result.volume_unit.value == "cubic_units_unspecified"
    assert result.point_count_input == point_count
    assert result.point_count_used > 0
    assert result.parameters["pile_depth"] == 2.5
    assert result.parameters["depth_source"] == "test_fixture"
    assert result.parameters["commercial_cubicacion"] is False

    warning_codes = {warning.code for warning in run.warnings}

    assert "pile_depth_not_supplied" not in warning_codes
    assert "crs_unconfirmed" in warning_codes
    assert "linear_units_unconfirmed" in warning_codes

    persisted = read_measurement_run(output_path)

    assert persisted == run


def test_run_timber_measurement_requires_depth_provenance(
    tmp_path,
) -> None:
    import pytest

    with pytest.raises(
        ValueError,
        match="depth_source is required",
    ):
        run_timber_measurement(
            tmp_path / "unused.las",
            tmp_path / "reports",
            pile_depth=2.5,
        )


def test_run_timber_measurement_rejects_depth_source_without_depth(
    tmp_path,
) -> None:
    import pytest

    with pytest.raises(
        ValueError,
        match="depth_source requires pile_depth",
    ):
        run_timber_measurement(
            tmp_path / "unused.las",
            tmp_path / "reports",
            depth_source="test_fixture",
        )
