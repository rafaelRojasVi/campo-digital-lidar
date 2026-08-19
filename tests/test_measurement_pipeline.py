from __future__ import annotations

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

    warning_codes = {warning.code for warning in run.warnings}

    assert "crs_unconfirmed" in warning_codes
    assert "linear_units_unconfirmed" in warning_codes
    assert "pile_depth_not_supplied" in warning_codes

    assert output_path == tmp_path / "reports" / "run-synthetic-wall" / "measurement.json"

    persisted = read_measurement_run(output_path)

    assert persisted == run
