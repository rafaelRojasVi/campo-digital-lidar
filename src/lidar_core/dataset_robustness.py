"""Dataset-level compatibility models for LAS/LAZ robustness testing.

These models describe what evidence a point-cloud dataset exposes to the
existing pipeline. They do not claim that the scene contains timber and do
not run timber detection, log-end analysis, or volume estimation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lidar_core.models import (
    AcquisitionAnalysis,
    LasMetadata,
)


class RgbPayloadCapability(BaseModel):
    """Observed RGB capability derived from streaming acquisition evidence."""

    model_config = ConfigDict(frozen=True)

    dimensions_present: bool
    analyzed: bool

    usable_for_image_analysis: bool | None = None

    observed_min: float | None = None
    observed_max: float | None = None

    normalization_denominator: float | None = None
    normalization_mode: str | None = None


class DatasetCapabilities(BaseModel):
    """Dataset capabilities without claiming semantic scene applicability."""

    model_config = ConfigDict(frozen=True)

    metadata_inspection: bool = True
    acquisition_analysis: bool

    crs_explicit: bool
    horizontal_units_explicit: bool

    gps_time_present: bool
    classification_present: bool
    return_number_present: bool

    rgb_dimensions_present: bool
    usable_rgb_payload: bool | None


class DatasetRobustnessReport(BaseModel):
    """Structured compatibility report for one LAS/LAZ dataset."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1"

    path: str
    file_suffix: str

    metadata: LasMetadata
    acquisition: AcquisitionAnalysis | None = None

    rgb: RgbPayloadCapability
    capabilities: DatasetCapabilities

    inspect_runtime_seconds: float
    acquisition_runtime_seconds: float | None = None

    warnings: list[str]


def derive_rgb_payload_capability(
    metadata: LasMetadata,
    acquisition: AcquisitionAnalysis | None,
) -> RgbPayloadCapability:
    """Classify RGB evidence without loading the complete RGB payload."""

    dimensions_present = metadata.dimensions.has_rgb

    if acquisition is None:
        return RgbPayloadCapability(
            dimensions_present=dimensions_present,
            analyzed=False,
        )

    if not dimensions_present:
        return RgbPayloadCapability(
            dimensions_present=False,
            analyzed=True,
            usable_for_image_analysis=False,
        )

    if not acquisition.rgb:
        return RgbPayloadCapability(
            dimensions_present=True,
            analyzed=True,
            usable_for_image_analysis=False,
        )

    summaries = tuple(acquisition.rgb.values())

    observed_min = min(summary.minimum for summary in summaries)
    observed_max = max(summary.maximum for summary in summaries)

    if observed_max <= 0.0:
        return RgbPayloadCapability(
            dimensions_present=True,
            analyzed=True,
            usable_for_image_analysis=False,
            observed_min=observed_min,
            observed_max=observed_max,
        )

    if observed_max <= 255.0:
        denominator = 255.0
        mode = "eight_bit_payload_in_las_rgb_fields"
    else:
        denominator = 65535.0
        mode = "sixteen_bit_las_rgb_payload"

    return RgbPayloadCapability(
        dimensions_present=True,
        analyzed=True,
        usable_for_image_analysis=True,
        observed_min=observed_min,
        observed_max=observed_max,
        normalization_denominator=denominator,
        normalization_mode=mode,
    )


class DatasetRobustnessFailure(BaseModel):
    """Failure recorded for one dataset without aborting the matrix."""

    model_config = ConfigDict(frozen=True)

    path: str
    error_type: str
    message: str


class DatasetRobustnessMatrix(BaseModel):
    """Results from applying one robustness profile to multiple datasets."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1"

    deep: bool
    compute_checksum: bool

    reports: list[DatasetRobustnessReport]
    failures: list[DatasetRobustnessFailure]

    total_datasets: int
    successful_datasets: int
    failed_datasets: int

    total_runtime_seconds: float
