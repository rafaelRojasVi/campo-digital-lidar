from __future__ import annotations

from typer.testing import CliRunner

from lidar_cli.main import app

runner = CliRunner()


def test_generate_synthetic_and_inspect(tmp_path):
    out = tmp_path / "synth.las"
    result = runner.invoke(
        app, ["generate-synthetic", "cube", str(out), "--n-points", "500", "--seed", "1"]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()

    result2 = runner.invoke(app, ["inspect", str(out), "--json"])
    assert result2.exit_code == 0, result2.output
    assert "point_count" in result2.output


def test_inspect_missing_file():
    result = runner.invoke(app, ["inspect", "/nonexistent/path.las"])
    assert result.exit_code == 1


def test_sections_not_implemented(tmp_path):
    dummy = tmp_path / "x.las"
    dummy.write_bytes(b"")
    result = runner.invoke(app, ["sections", str(dummy)])
    assert result.exit_code == 2


def test_crop_command(tmp_path):
    out = tmp_path / "synth.las"
    runner.invoke(
        app, ["generate-synthetic", "cube", str(out), "--n-points", "1000", "--seed", "2"]
    )
    cropped = tmp_path / "cropped.las"
    result = runner.invoke(
        app,
        [
            "crop",
            str(out),
            str(cropped),
            "--min-x",
            "0.0",
            "--min-y",
            "0.0",
            "--max-x",
            "0.5",
            "--max-y",
            "0.5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert cropped.exists()


def test_analyze_command(tmp_path):
    out = tmp_path / "synth.las"
    generated = runner.invoke(
        app,
        [
            "generate-synthetic",
            "cube",
            str(out),
            "--n-points",
            "100",
            "--seed",
            "4",
        ],
    )
    assert generated.exit_code == 0, generated.output

    result = runner.invoke(app, ["analyze", str(out), "--json"])
    assert result.exit_code == 0, result.output
    assert '"point_count": 100' in result.output
    assert '"gps_time_present": true' in result.output


def _write_synthetic_front_wall(path) -> None:
    import laspy
    import numpy as np

    x_values = np.linspace(
        0.0,
        10.0,
        220,
    )
    z_values = np.linspace(
        0.0,
        2.0,
        300,
    )

    xx, zz = np.meshgrid(
        x_values,
        z_values,
    )

    header = laspy.LasHeader(
        point_format=3,
        version="1.2",
    )

    las = laspy.LasData(header)
    las.x = xx.ravel()
    las.y = np.zeros(xx.size)
    las.z = zz.ravel()

    las.write(path)


def test_volume_without_depth_reports_area_only(tmp_path):
    source = tmp_path / "front_wall.las"
    _write_synthetic_front_wall(source)

    result = runner.invoke(
        app,
        [
            "volume",
            str(source),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Rectangle area" in result.output
    assert "Trapezoid area" in result.output
    assert "not computed" in result.output

    # No cubic result may be invented when depth is absent.
    assert "source-units³" not in result.output


def test_volume_with_explicit_depth_reports_extrusion(tmp_path):
    source = tmp_path / "front_wall.las"
    _write_synthetic_front_wall(source)

    result = runner.invoke(
        app,
        [
            "volume",
            str(source),
            "--depth",
            "2.0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Assumed depth" in result.output
    assert "Extruded volume" in result.output
    assert "source-units³" in result.output
    assert "not inferred or validated" in result.output


def test_volume_rejects_negative_depth(tmp_path):
    source = tmp_path / "front_wall.las"
    _write_synthetic_front_wall(source)

    result = runner.invoke(
        app,
        [
            "volume",
            str(source),
            "--depth",
            "-1",
        ],
    )

    assert result.exit_code == 1
    assert "--depth must be non-negative" in result.output


def test_volume_missing_file():
    result = runner.invoke(
        app,
        [
            "volume",
            "/nonexistent/front-wall.las",
        ],
    )

    assert result.exit_code == 1
    assert "file not found" in result.output.lower()


def test_measure_command_persists_structured_run(tmp_path):
    source = tmp_path / "candidate.las"
    _write_synthetic_front_wall(source)

    output_root = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "measure",
            str(source),
            "--output-root",
            str(output_root),
            "--run-id",
            "cli-test-run",
            "--code-version",
            "test",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Measurement Run: cli-test-run" in result.output
    assert "Selected timber points" in result.output
    assert "Rectangle area" in result.output
    assert "front_profile" in result.output
    assert "front_profile_plot" in result.output
    assert "front_height_profile_plot" in result.output
    assert "pile_depth_not_supplied" in result.output

    run_directory = output_root / "cli-test-run"

    assert (run_directory / "measurement.json").exists()

    assert (run_directory / "front_profile.json").exists()

    assert (run_directory / "front_profile.png").exists()

    assert (run_directory / "front_height_profile.png").exists()


def test_measure_command_missing_file():
    result = runner.invoke(
        app,
        [
            "measure",
            "/nonexistent/candidate.las",
        ],
    )

    assert result.exit_code == 1
    assert "file not found" in result.output.lower()


def test_measure_command_with_explicit_depth_reports_geometric_volume(
    tmp_path,
):
    source = tmp_path / "candidate-depth.las"
    _write_synthetic_front_wall(source)

    output_root = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "measure",
            str(source),
            "--output-root",
            str(output_root),
            "--run-id",
            "cli-depth-run",
            "--code-version",
            "test",
            "--depth",
            "2.5",
            "--depth-source",
            "test_fixture",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Geometric volume" in result.output
    assert "cubic_units_unspecified" in result.output
    assert "Explicit pile depth" in result.output
    assert "2.500000 source units" in result.output
    assert "test_fixture" in result.output
    assert "pile_depth_not_supplied" not in result.output

    measurement_path = output_root / "cli-depth-run" / "measurement.json"

    assert measurement_path.exists()


def test_measure_command_requires_depth_source(
    tmp_path,
):
    source = tmp_path / "candidate-depth-missing-source.las"
    _write_synthetic_front_wall(source)

    result = runner.invoke(
        app,
        [
            "measure",
            str(source),
            "--output-root",
            str(tmp_path / "reports"),
            "--depth",
            "2.5",
        ],
    )

    assert result.exit_code == 1
    assert "depth_source is required" in result.output


def test_compare_command_persists_reference_comparison(
    tmp_path,
):
    source = tmp_path / "compare-candidate.las"
    _write_synthetic_front_wall(source)

    output_root = tmp_path / "reports"

    measured = runner.invoke(
        app,
        [
            "measure",
            str(source),
            "--output-root",
            str(output_root),
            "--run-id",
            "compare-run",
            "--code-version",
            "test",
            "--depth",
            "2.5",
            "--depth-source",
            "synthetic_test_depth",
        ],
    )

    assert measured.exit_code == 0, measured.output

    measurement_path = output_root / "compare-run" / "measurement.json"

    compared = runner.invoke(
        app,
        [
            "compare",
            str(measurement_path),
            "--reference-value",
            "5.0",
            "--reference-unit",
            "cubic_units_unspecified",
            "--reference-method",
            "synthetic_reference",
            "--reference-label",
            "fixture_reference",
            "--comparison-id",
            "comparison-001",
        ],
    )

    assert compared.exit_code == 0, compared.output
    assert "Volume Comparison: comparison-001" in compared.output
    assert "Signed error" in compared.output
    assert "Absolute error" in compared.output
    assert "Percent error" in compared.output
    assert "synthetic_reference" in compared.output

    comparison_path = output_root / "compare-run" / "comparisons" / "comparison-001.json"

    assert comparison_path.exists()


def test_compare_command_rejects_incompatible_units(
    tmp_path,
):
    source = tmp_path / "compare-unit-candidate.las"
    _write_synthetic_front_wall(source)

    output_root = tmp_path / "reports"

    measured = runner.invoke(
        app,
        [
            "measure",
            str(source),
            "--output-root",
            str(output_root),
            "--run-id",
            "compare-unit-run",
            "--depth",
            "2.5",
            "--depth-source",
            "synthetic_test_depth",
        ],
    )

    assert measured.exit_code == 0, measured.output

    measurement_path = output_root / "compare-unit-run" / "measurement.json"

    compared = runner.invoke(
        app,
        [
            "compare",
            str(measurement_path),
            "--reference-value",
            "5.0",
            "--reference-unit",
            "m3",
            "--reference-method",
            "synthetic_reference",
            "--comparison-id",
            "comparison-unit-mismatch",
        ],
    )

    assert compared.exit_code == 1
    assert "units must match exactly" in compared.output

    comparison_path = (
        output_root / "compare-unit-run" / "comparisons" / "comparison-unit-mismatch.json"
    )

    assert not comparison_path.exists()
