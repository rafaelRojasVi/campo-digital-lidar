from __future__ import annotations

import pytest

from lidar_core.models import (
    ReferenceMeasurement,
    VolumeComparisonRecord,
    VolumeUnit,
)
from lidar_core.volume_comparison import compare_volume_result
from lidar_io.comparison_store import (
    comparison_record_path,
    read_comparison_record,
    write_comparison_record,
)
from test_volume_comparison import _estimate


def _record() -> VolumeComparisonRecord:
    estimate = _estimate(110.0)

    reference = ReferenceMeasurement(
        label="client_reference",
        value=100.0,
        unit=VolumeUnit.CUBIC_UNITS_UNSPECIFIED,
        method="synthetic_test",
    )

    return VolumeComparisonRecord(
        comparison_id="comparison-001",
        run_id="run-001",
        estimate_result_index=0,
        comparison=compare_volume_result(
            estimate,
            reference,
        ),
    )


def test_comparison_record_round_trip(tmp_path) -> None:
    record = _record()

    path = write_comparison_record(
        record,
        tmp_path,
    )

    assert path == (tmp_path / "run-001" / "comparisons" / "comparison-001.json")

    assert path.exists()

    persisted = read_comparison_record(path)

    assert persisted == record


def test_comparison_record_does_not_overwrite_by_default(
    tmp_path,
) -> None:
    record = _record()

    write_comparison_record(
        record,
        tmp_path,
    )

    with pytest.raises(
        FileExistsError,
        match="comparison record already exists",
    ):
        write_comparison_record(
            record,
            tmp_path,
        )


def test_comparison_record_rejects_unsafe_identifier(
    tmp_path,
) -> None:
    record = _record().model_copy(
        update={
            "comparison_id": "../escape",
        }
    )

    with pytest.raises(
        ValueError,
        match="comparison_id must be a single safe path component",
    ):
        comparison_record_path(
            record,
            tmp_path,
        )
