"""Persistence for immutable volume-comparison records."""

from __future__ import annotations

from pathlib import Path

from lidar_core.models import VolumeComparisonRecord


def _validate_identifier(value: str, *, field: str) -> None:
    if not value:
        raise ValueError(f"{field} must not be empty")

    if Path(value).name != value or value in {".", ".."}:
        raise ValueError(f"{field} must be a single safe path component")


def comparison_record_path(
    record: VolumeComparisonRecord,
    output_root: Path,
) -> Path:
    """Return the canonical JSON path for a comparison record."""

    _validate_identifier(
        record.run_id,
        field="run_id",
    )
    _validate_identifier(
        record.comparison_id,
        field="comparison_id",
    )

    return output_root / record.run_id / "comparisons" / f"{record.comparison_id}.json"


def write_comparison_record(
    record: VolumeComparisonRecord,
    output_root: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Persist one comparison without replacing existing data by default."""

    path = comparison_record_path(
        record,
        output_root,
    )

    if path.exists() and not overwrite:
        raise FileExistsError(f"comparison record already exists: {path}")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        record.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    return path


def read_comparison_record(
    path: Path,
) -> VolumeComparisonRecord:
    """Load and validate a persisted comparison record."""

    return VolumeComparisonRecord.model_validate_json(path.read_text(encoding="utf-8"))
