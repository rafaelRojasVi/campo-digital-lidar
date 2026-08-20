"""Build structured LAS/LAZ dataset robustness reports.

The robustness path characterizes file compatibility and available evidence.
It deliberately does not run timber localization, log-end analysis, or volume
estimation.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

from laspy.errors import LaspyException

from lidar_core.dataset_robustness import (
    DatasetCapabilities,
    DatasetRobustnessFailure,
    DatasetRobustnessMatrix,
    DatasetRobustnessReport,
    derive_rgb_payload_capability,
)
from lidar_io.analyze import analyze_las
from lidar_io.inspect import inspect_las

_SUPPORTED_SUFFIXES = {
    ".las",
    ".laz",
}


def _combined_warnings(
    metadata_warnings: list[str],
    acquisition_warnings: list[str] | None,
) -> list[str]:
    """Combine warnings while preserving order and removing duplicates."""

    combined: list[str] = []
    seen: set[str] = set()

    for warning in [
        *metadata_warnings,
        *(acquisition_warnings or []),
    ]:
        if warning in seen:
            continue

        seen.add(warning)
        combined.append(warning)

    return combined


def build_dataset_robustness_report(
    path: str | Path,
    *,
    deep: bool = False,
    compute_checksum: bool = False,
) -> DatasetRobustnessReport:
    """Build a compatibility report for one LAS/LAZ dataset.

    ``deep=False`` performs the existing forensic inspection path only.

    ``deep=True`` additionally executes the streaming acquisition analysis,
    including GPS-time, return, intensity, RGB, and timestamp-group
    diagnostics where those dimensions are available.

    Checksum calculation defaults to off because robustness/stress runs may
    involve multi-gigabyte datasets and content hashing is a separate I/O
    concern from point-cloud compatibility.
    """

    source = Path(path)

    suffix = source.suffix.lower()

    if suffix not in _SUPPORTED_SUFFIXES:
        raise ValueError("dataset robustness currently supports only LAS/LAZ files")

    inspect_started = perf_counter()

    metadata = inspect_las(
        source,
        compute_checksum=compute_checksum,
    )

    inspect_runtime_seconds = perf_counter() - inspect_started

    acquisition = None
    acquisition_runtime_seconds = None

    if deep:
        acquisition_started = perf_counter()

        acquisition = analyze_las(source)

        acquisition_runtime_seconds = perf_counter() - acquisition_started

    rgb = derive_rgb_payload_capability(
        metadata,
        acquisition,
    )

    capabilities = DatasetCapabilities(
        acquisition_analysis=(acquisition is not None),
        crs_explicit=(metadata.coordinate_metadata.is_explicit),
        horizontal_units_explicit=(metadata.coordinate_metadata.horizontal_units is not None),
        gps_time_present=(metadata.dimensions.has_gps_time),
        classification_present=(metadata.dimensions.has_classification),
        return_number_present=(metadata.dimensions.has_return_number),
        rgb_dimensions_present=(metadata.dimensions.has_rgb),
        usable_rgb_payload=(rgb.usable_for_image_analysis),
    )

    warnings = _combined_warnings(
        metadata.warnings,
        (acquisition.warnings if acquisition is not None else None),
    )

    if acquisition is not None and acquisition.point_count != metadata.point_count:
        warnings.append(
            "Forensic inspection and acquisition analysis reported different point counts."
        )

    return DatasetRobustnessReport(
        path=str(source),
        file_suffix=suffix,
        metadata=metadata,
        acquisition=acquisition,
        rgb=rgb,
        capabilities=capabilities,
        inspect_runtime_seconds=(inspect_runtime_seconds),
        acquisition_runtime_seconds=(acquisition_runtime_seconds),
        warnings=warnings,
    )


def build_dataset_robustness_matrix(
    paths: Sequence[str | Path],
    *,
    deep: bool = False,
    compute_checksum: bool = False,
) -> DatasetRobustnessMatrix:
    """Build robustness reports for a corpus with per-dataset failure isolation."""

    started = perf_counter()

    reports: list[DatasetRobustnessReport] = []
    failures: list[DatasetRobustnessFailure] = []

    for path in paths:
        source = Path(path)

        try:
            report = build_dataset_robustness_report(
                source,
                deep=deep,
                compute_checksum=compute_checksum,
            )
        except (
            FileNotFoundError,
            ValueError,
            OSError,
            LaspyException,
        ) as exc:
            failures.append(
                DatasetRobustnessFailure(
                    path=str(source),
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            )
            continue

        reports.append(report)

    return DatasetRobustnessMatrix(
        deep=deep,
        compute_checksum=compute_checksum,
        reports=reports,
        failures=failures,
        total_datasets=len(paths),
        successful_datasets=len(reports),
        failed_datasets=len(failures),
        total_runtime_seconds=perf_counter() - started,
    )
