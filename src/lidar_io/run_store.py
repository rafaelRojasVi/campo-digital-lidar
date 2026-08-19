"""Persistence for structured measurement-run records.

Measurement algorithms and adapters do not write files directly. This module
owns the small filesystem boundary used to persist a MeasurementRun as JSON.
"""

from __future__ import annotations

from pathlib import Path

from lidar_core.models import MeasurementRun

MEASUREMENT_FILENAME = "measurement.json"


def _validate_run_id(run_id: str) -> None:
    """Reject run IDs that could escape the configured output directory."""

    if not run_id:
        raise ValueError("run_id must not be empty")

    if Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError("run_id must be a single safe path component")


def measurement_run_path(
    run: MeasurementRun,
    output_root: Path,
) -> Path:
    """Return the canonical JSON path for a measurement run."""

    _validate_run_id(run.run_id)

    return output_root / run.run_id / MEASUREMENT_FILENAME


def write_measurement_run(
    run: MeasurementRun,
    output_root: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Persist a MeasurementRun as formatted UTF-8 JSON.

    Existing run records are immutable by default. Pass ``overwrite=True``
    only when intentionally replacing the same run record.
    """

    path = measurement_run_path(run, output_root)

    if path.exists() and not overwrite:
        raise FileExistsError(f"measurement run already exists: {path}")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = run.model_dump_json(indent=2) + "\n"

    path.write_text(
        payload,
        encoding="utf-8",
    )

    return path


def read_measurement_run(path: Path) -> MeasurementRun:
    """Load and validate a persisted MeasurementRun JSON document."""

    return MeasurementRun.model_validate_json(path.read_text(encoding="utf-8"))
