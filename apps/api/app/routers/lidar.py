"""LiDAR HTTP adapter for persisted measurement runs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import Connection

from app.access import Action
from app.access_repository import AppUser
from app.deps import ensure_can, get_current_app_user, get_db_connection
from lidar_core.models import MeasurementRun, VolumeComparisonRecord
from lidar_io.comparison_store import read_comparison_record
from lidar_io.output_root_discovery import resolve_report_root
from lidar_io.run_store import (
    MEASUREMENT_FILENAME,
    discover_measurement_paths,
    read_measurement_run,
)

LIDAR_PRODUCT_KEY = "lidar"


def require_lidar_view(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
) -> None:
    """Require an authenticated caller with a LiDAR VIEW-capable grant.

    Reuses the same access primitives (app.access.can, app.deps.ensure_can)
    already used by app.routers.ingestion — no new authorization layer.
    """

    ensure_can(
        connection,
        app_user_id=user.id,
        product_key=LIDAR_PRODUCT_KEY,
        action=Action.VIEW,
    )


router = APIRouter(dependencies=[Depends(require_lidar_view)])

REPO_ROOT = Path(__file__).resolve().parents[4]


def get_output_root() -> Path:
    """Return the local measurement-output root to serve.

    An explicit ``CAMPO_LIDAR_OUTPUT_ROOT`` always wins; otherwise, only in
    ``APP_ENV=development``, the report store is discovered automatically
    across local git worktrees. In any other ``APP_ENV`` (staging,
    production, ...) that discovery is disabled — a hosted API process must
    never inspect sibling worktrees or implicitly trust local report state —
    and this falls back to the same "no report source configured" state the
    API already handles safely. See ``lidar_io.output_root_discovery`` for
    the full precedence rules.

    Read straight from the process environment, like the ``APP_ENV`` checks
    in ``app.main``, so resolving this never requires the full
    ``app.config.Settings`` (and its database credentials) to be configured.
    """

    resolution = resolve_report_root(
        REPO_ROOT,
        env_value=os.environ.get("CAMPO_LIDAR_OUTPUT_ROOT"),
        app_env=os.environ.get("APP_ENV", "development"),
    )
    return resolution.path


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


@router.get(
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

    for measurement_path in discover_measurement_paths(output_root):
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


@router.get(
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


@router.get(
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


@router.get(
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


@router.get(
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
