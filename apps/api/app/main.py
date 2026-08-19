"""Read-only FastAPI surface for persisted LiDAR measurement runs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

from lidar_core.models import MeasurementRun, VolumeComparisonRecord
from lidar_io.comparison_store import read_comparison_record
from lidar_io.run_store import MEASUREMENT_FILENAME, read_measurement_run

app = FastAPI(
    title="Campo Digital LiDAR API",
    version="0.2.0",
)

DEFAULT_OUTPUT_ROOT = Path("reports/out")


def get_output_root() -> Path:
    """Return the configured local measurement-output root."""

    configured = os.environ.get(
        "CAMPO_LIDAR_OUTPUT_ROOT",
        str(DEFAULT_OUTPUT_ROOT),
    )
    return Path(configured)


def _safe_component(value: str, *, field: str) -> str:
    """Reject identifiers that could escape the reports directory."""

    if not value:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must not be empty",
        )

    if Path(value).name != value or value in {".", ".."}:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be a single safe path component",
        )

    return value


def _run_directory(
    output_root: Path,
    run_id: str,
) -> Path:
    safe_run_id = _safe_component(
        run_id,
        field="run_id",
    )
    return output_root / safe_run_id


def _measurement_path(
    output_root: Path,
    run_id: str,
) -> Path:
    return (
        _run_directory(
            output_root,
            run_id,
        )
        / MEASUREMENT_FILENAME
    )


def _read_run_or_404(
    output_root: Path,
    run_id: str,
) -> MeasurementRun:
    path = _measurement_path(
        output_root,
        run_id,
    )

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="measurement run not found",
        )

    try:
        return read_measurement_run(path)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="measurement run could not be read",
        ) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/runs",
    response_model=list[MeasurementRun],
)
def list_runs(
    output_root: Annotated[Path, Depends(get_output_root)],
) -> list[MeasurementRun]:
    """List valid persisted measurement runs."""

    if not output_root.is_dir():
        return []

    runs: list[MeasurementRun] = []

    for measurement_path in sorted(output_root.glob(f"*/{MEASUREMENT_FILENAME}")):
        try:
            run = read_measurement_run(measurement_path)
        except (OSError, ValueError):
            continue

        runs.append(run)

    runs.sort(
        key=lambda run: run.started_at,
        reverse=True,
    )

    return runs


@app.get(
    "/runs/{run_id}",
    response_model=MeasurementRun,
)
def get_run(
    run_id: str,
    output_root: Annotated[Path, Depends(get_output_root)],
) -> MeasurementRun:
    """Return one persisted measurement run."""

    return _read_run_or_404(
        output_root,
        run_id,
    )


@app.get(
    "/runs/{run_id}/comparisons",
    response_model=list[VolumeComparisonRecord],
)
def list_comparisons(
    run_id: str,
    output_root: Annotated[Path, Depends(get_output_root)],
) -> list[VolumeComparisonRecord]:
    """List persisted comparison records for one measurement run."""

    _read_run_or_404(
        output_root,
        run_id,
    )

    comparisons_directory = (
        _run_directory(
            output_root,
            run_id,
        )
        / "comparisons"
    )

    if not comparisons_directory.is_dir():
        return []

    records: list[VolumeComparisonRecord] = []

    for path in sorted(comparisons_directory.glob("*.json")):
        try:
            records.append(read_comparison_record(path))
        except (OSError, ValueError):
            continue

    records.sort(
        key=lambda record: record.created_at,
        reverse=True,
    )

    return records


@app.get(
    "/runs/{run_id}/comparisons/{comparison_id}",
    response_model=VolumeComparisonRecord,
)
def get_comparison(
    run_id: str,
    comparison_id: str,
    output_root: Annotated[Path, Depends(get_output_root)],
) -> VolumeComparisonRecord:
    """Return one persisted volume-comparison record."""

    _read_run_or_404(
        output_root,
        run_id,
    )

    safe_comparison_id = _safe_component(
        comparison_id,
        field="comparison_id",
    )

    path = (
        _run_directory(
            output_root,
            run_id,
        )
        / "comparisons"
        / f"{safe_comparison_id}.json"
    )

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="comparison record not found",
        )

    try:
        return read_comparison_record(path)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="comparison record could not be read",
        ) from exc


@app.get(
    "/runs/{run_id}/artifacts/{artifact_path:path}",
    response_class=FileResponse,
)
def get_artifact(
    run_id: str,
    artifact_path: str,
    output_root: Annotated[Path, Depends(get_output_root)],
) -> FileResponse:
    """Serve only artifacts explicitly registered by the measurement run."""

    run = _read_run_or_404(
        output_root,
        run_id,
    )

    artifact = next(
        (candidate for candidate in run.artifacts if candidate.path == artifact_path),
        None,
    )

    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail="artifact is not registered for this measurement run",
        )

    run_directory = _run_directory(
        output_root,
        run_id,
    ).resolve()

    path = (run_directory / artifact.path).resolve()

    if not path.is_relative_to(run_directory):
        raise HTTPException(
            status_code=400,
            detail="artifact path escapes measurement run directory",
        )

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="artifact file not found",
        )

    return FileResponse(
        path=path,
        media_type=artifact.media_type,
    )
