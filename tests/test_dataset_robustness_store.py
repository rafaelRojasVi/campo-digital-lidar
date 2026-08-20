from __future__ import annotations

import pytest

from lidar_core.dataset_robustness import (
    DatasetRobustnessFailure,
    DatasetRobustnessMatrix,
)
from lidar_io.dataset_robustness_store import (
    read_dataset_robustness_matrix,
    write_dataset_robustness_matrix,
)


def _matrix() -> DatasetRobustnessMatrix:
    return DatasetRobustnessMatrix(
        deep=False,
        compute_checksum=False,
        reports=[],
        failures=[
            DatasetRobustnessFailure(
                path="missing.las",
                error_type="FileNotFoundError",
                message="fixture failure",
            )
        ],
        total_datasets=1,
        successful_datasets=0,
        failed_datasets=1,
        total_runtime_seconds=0.25,
    )


def test_write_and_read_dataset_robustness_matrix(
    tmp_path,
) -> None:
    matrix = _matrix()
    path = tmp_path / "nested" / "matrix.json"

    written = write_dataset_robustness_matrix(
        matrix,
        path,
    )

    assert written == path
    assert path.exists()
    assert path.read_text(encoding="utf-8").endswith("\n")

    loaded = read_dataset_robustness_matrix(path)

    assert loaded == matrix


def test_write_dataset_robustness_matrix_is_immutable_by_default(
    tmp_path,
) -> None:
    matrix = _matrix()
    path = tmp_path / "matrix.json"

    write_dataset_robustness_matrix(
        matrix,
        path,
    )

    with pytest.raises(
        FileExistsError,
        match="already exists",
    ):
        write_dataset_robustness_matrix(
            matrix,
            path,
        )


def test_write_dataset_robustness_matrix_can_overwrite_explicitly(
    tmp_path,
) -> None:
    matrix = _matrix()
    path = tmp_path / "matrix.json"

    write_dataset_robustness_matrix(
        matrix,
        path,
    )

    written = write_dataset_robustness_matrix(
        matrix,
        path,
        overwrite=True,
    )

    assert written == path
    assert read_dataset_robustness_matrix(path) == matrix
