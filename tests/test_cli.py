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
