from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.main import app  # noqa: E402
from app.routers.lidar import get_output_root, require_lidar_view  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from lidar_core.models import (  # noqa: E402
    MeasurementArtifact,
    MeasurementRun,
    MeasurementRunStatus,
    ReferenceMeasurement,
    VolumeComparison,
    VolumeComparisonRecord,
    VolumeUnit,
)
from lidar_io.comparison_store import write_comparison_record  # noqa: E402
from lidar_io.run_store import write_measurement_run  # noqa: E402


@pytest.fixture
def client(tmp_path: Path):
    app.dependency_overrides[get_output_root] = lambda: tmp_path
    # RBAC on this router is covered end-to-end (real sessions + product
    # grants against a real database) by
    # integration_tests/test_lidar_router_rbac.py. This file has no database
    # and exercises path/artifact-safety behavior only, so it bypasses RBAC
    # here rather than faking a user/session for every test.
    app.dependency_overrides[require_lidar_view] = lambda: None

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _write_run(
    output_root: Path,
    *,
    run_id: str = "run-001",
    with_artifact: bool = False,
) -> MeasurementRun:
    artifacts = []

    if with_artifact:
        artifacts.append(
            MeasurementArtifact(
                kind="front_profile",
                path="front_profile.json",
                media_type="application/json",
                description="Synthetic API fixture.",
            )
        )

    run = MeasurementRun(
        run_id=run_id,
        source_path="/private/source/example.las",
        status=MeasurementRunStatus.COMPLETED,
        artifacts=artifacts,
    )

    write_measurement_run(
        run,
        output_root,
    )

    if with_artifact:
        artifact_path = output_root / run_id / "front_profile.json"
        artifact_path.write_text(
            '{"kind":"front_profile"}\n',
            encoding="utf-8",
        )

    return run


def _write_comparison(
    output_root: Path,
    *,
    run_id: str = "run-001",
    comparison_id: str = "comparison-001",
) -> VolumeComparisonRecord:
    reference = ReferenceMeasurement(
        label="synthetic_reference",
        value=100.0,
        unit=VolumeUnit.CUBIC_UNITS_UNSPECIFIED,
        method="synthetic_test",
    )

    comparison = VolumeComparison(
        estimate_method="synthetic_estimator",
        estimate_value=110.0,
        reference=reference,
        unit=VolumeUnit.CUBIC_UNITS_UNSPECIFIED,
        signed_error=10.0,
        absolute_error=10.0,
        relative_error=0.1,
        absolute_relative_error=0.1,
        percent_error=10.0,
        absolute_percent_error=10.0,
    )

    record = VolumeComparisonRecord(
        comparison_id=comparison_id,
        run_id=run_id,
        estimate_result_index=0,
        comparison=comparison,
    )

    write_comparison_record(
        record,
        output_root,
    )

    return record


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_runs_returns_persisted_measurements(
    client: TestClient,
    tmp_path: Path,
) -> None:
    older = _write_run(
        tmp_path,
        run_id="run-001",
    )
    newer = _write_run(
        tmp_path,
        run_id="run-002",
    )

    response = client.get("/runs")

    assert response.status_code == 200

    payload = response.json()

    assert {item["run_id"] for item in payload} == {
        older.run_id,
        newer.run_id,
    }


def test_get_run_returns_measurement(
    client: TestClient,
    tmp_path: Path,
) -> None:
    run = _write_run(tmp_path)

    response = client.get(f"/runs/{run.run_id}")

    assert response.status_code == 200
    assert response.json()["run_id"] == run.run_id
    assert response.json()["status"] == "completed"


def test_get_run_returns_404_when_missing(
    client: TestClient,
) -> None:
    response = client.get("/runs/missing-run")

    assert response.status_code == 404


def test_list_comparisons_returns_persisted_records(
    client: TestClient,
    tmp_path: Path,
) -> None:
    run = _write_run(tmp_path)
    record = _write_comparison(
        tmp_path,
        run_id=run.run_id,
    )

    response = client.get(f"/runs/{run.run_id}/comparisons")

    assert response.status_code == 200

    payload = response.json()

    assert len(payload) == 1
    assert payload[0]["comparison_id"] == record.comparison_id


def test_get_comparison_returns_record(
    client: TestClient,
    tmp_path: Path,
) -> None:
    run = _write_run(tmp_path)
    record = _write_comparison(
        tmp_path,
        run_id=run.run_id,
    )

    response = client.get(f"/runs/{run.run_id}/comparisons/{record.comparison_id}")

    assert response.status_code == 200
    assert response.json()["comparison_id"] == record.comparison_id
    assert response.json()["comparison"]["signed_error"] == 10.0


def test_get_artifact_serves_registered_file(
    client: TestClient,
    tmp_path: Path,
) -> None:
    run = _write_run(
        tmp_path,
        with_artifact=True,
    )

    response = client.get(f"/runs/{run.run_id}/artifacts/front_profile.json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"kind": "front_profile"}


def test_get_artifact_rejects_unregistered_file(
    client: TestClient,
    tmp_path: Path,
) -> None:
    run = _write_run(tmp_path)

    secret_path = tmp_path / run.run_id / "not-an-artifact.txt"
    secret_path.write_text(
        "must not be exposed",
        encoding="utf-8",
    )

    response = client.get(f"/runs/{run.run_id}/artifacts/not-an-artifact.txt")

    assert response.status_code == 404


def test_get_artifact_rejects_registered_path_escape(
    client: TestClient,
    tmp_path: Path,
) -> None:
    run = MeasurementRun(
        run_id="run-escape",
        source_path="/private/source/example.las",
        status=MeasurementRunStatus.COMPLETED,
        artifacts=[
            MeasurementArtifact(
                kind="malicious_fixture",
                path="../outside.txt",
                media_type="text/plain",
            )
        ],
    )

    write_measurement_run(
        run,
        tmp_path,
    )

    outside = tmp_path / "outside.txt"
    outside.write_text(
        "must not be exposed",
        encoding="utf-8",
    )

    response = client.get("/runs/run-escape/artifacts/../outside.txt")

    assert response.status_code in {
        400,
        404,
    }
    assert response.text != "must not be exposed"
