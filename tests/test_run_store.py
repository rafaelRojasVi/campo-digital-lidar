from __future__ import annotations

import json

import pytest

from lidar_core.models import (
    MeasurementRun,
    MeasurementRunStatus,
    MeasurementWarning,
)
from lidar_io.run_store import (
    measurement_run_path,
    read_measurement_run,
    write_measurement_run,
)


def test_write_measurement_run_uses_canonical_path(tmp_path) -> None:
    run = MeasurementRun(
        run_id="run-test-001",
        source_path="/data/example.las",
        status=MeasurementRunStatus.COMPLETED,
        warnings=[
            MeasurementWarning(
                code="crs_unconfirmed",
                message="CRS is not confirmed.",
            )
        ],
    )

    path = write_measurement_run(
        run,
        tmp_path,
    )

    assert path == (tmp_path / "run-test-001" / "measurement.json")
    assert path.exists()

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["run_id"] == "run-test-001"
    assert payload["status"] == "completed"
    assert payload["warnings"][0]["code"] == "crs_unconfirmed"


def test_measurement_run_round_trip(tmp_path) -> None:
    run = MeasurementRun(
        run_id="run-roundtrip",
        source_path="/data/timber.las",
        source_sha256="abc123",
        code_version="34363a0",
    )

    path = write_measurement_run(
        run,
        tmp_path,
    )

    loaded = read_measurement_run(path)

    assert loaded == run


def test_existing_measurement_run_is_not_overwritten_by_default(
    tmp_path,
) -> None:
    run = MeasurementRun(
        run_id="run-existing",
        source_path="/data/example.las",
    )

    path = write_measurement_run(
        run,
        tmp_path,
    )

    with pytest.raises(
        FileExistsError,
        match="measurement run already exists",
    ):
        write_measurement_run(
            run,
            tmp_path,
        )

    assert read_measurement_run(path) == run


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        ".",
        "..",
        "../escape",
        "nested/run",
    ],
)
def test_measurement_run_path_rejects_unsafe_run_ids(
    tmp_path,
    run_id,
) -> None:
    run = MeasurementRun(
        run_id=run_id,
        source_path="/data/example.las",
    )

    with pytest.raises(ValueError):
        measurement_run_path(
            run,
            tmp_path,
        )
