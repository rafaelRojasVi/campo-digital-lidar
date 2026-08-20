"""Persistence for dataset robustness matrix records."""

from __future__ import annotations

from pathlib import Path

from lidar_core.dataset_robustness import DatasetRobustnessMatrix


def write_dataset_robustness_matrix(
    matrix: DatasetRobustnessMatrix,
    path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Persist a robustness matrix as formatted UTF-8 JSON.

    Existing records are immutable by default. Pass ``overwrite=True`` only
    when intentionally replacing the requested output artifact.
    """

    if path.exists() and not overwrite:
        raise FileExistsError(f"dataset robustness matrix already exists: {path}")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        matrix.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    return path


def read_dataset_robustness_matrix(
    path: Path,
) -> DatasetRobustnessMatrix:
    """Load and validate a persisted robustness matrix."""

    return DatasetRobustnessMatrix.model_validate_json(path.read_text(encoding="utf-8"))
