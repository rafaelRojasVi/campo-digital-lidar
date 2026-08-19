"""Domain models for LAS metadata, geometry, and volume measurement.

These models are intentionally explicit about provenance and units. Never
assume a value's unit or CRS implicitly -- carry it as data.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VolumeUnit(StrEnum):
    """Explicit volume units. A VolumeResult must never claim m3 unless
    the input coordinates/scale are known to be metric and the CRS is
    linear-unit-consistent."""

    CUBIC_METERS = "m3"
    CUBIC_UNITS_UNSPECIFIED = "cubic_units_unspecified"


class CoordinateMetadata(BaseModel):
    """CRS/coordinate info for a point cloud. `crs_wkt`/`crs_epsg` are
    None (not guessed) when the source data does not encode a CRS."""

    model_config = ConfigDict(frozen=True)

    crs_wkt: str | None = None
    crs_epsg: int | None = None
    crs_source: str | None = Field(
        default=None,
        description="Where the CRS came from, e.g. 'VLR GeoKeys', 'WKT VLR', 'user-supplied'.",
    )
    is_explicit: bool = Field(
        default=False,
        description="True only if a CRS was actually found/declared. Never set True by inference.",
    )
    vertical_datum: str | None = None
    horizontal_units: str | None = Field(
        default=None, description="e.g. 'metre', 'US survey foot' -- read from source, not assumed."
    )


class BoundingBox3D(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def span_x(self) -> float:
        return self.max_x - self.min_x

    @property
    def span_y(self) -> float:
        return self.max_y - self.min_y

    @property
    def span_z(self) -> float:
        return self.max_z - self.min_z

    @property
    def volume_bbox(self) -> float:
        """Axis-aligned bounding-box volume in the source coordinate units
        (cubed). This is NOT a point-cloud/timber volume estimate."""
        return self.span_x * self.span_y * self.span_z


class PointDimensions(BaseModel):
    """Which dims/fields are present in a LAS file."""

    model_config = ConfigDict(frozen=True)

    standard_dims: list[str] = Field(default_factory=list)
    extra_dims: list[str] = Field(default_factory=list)
    has_rgb: bool = False
    has_intensity: bool = False
    has_gps_time: bool = False
    has_classification: bool = False
    has_return_number: bool = False


class LasMetadata(BaseModel):
    """Forensic metadata for a LAS/LAZ file, obtainable from the header
    and VLRs without loading the full point cloud."""

    model_config = ConfigDict(frozen=True)

    path: str
    file_size_bytes: int
    sha256: str | None = Field(
        default=None, description="Content checksum; None if skipped for very large files."
    )
    las_version_major: int
    las_version_minor: int
    point_format_id: int
    point_count: int
    scales: tuple[float, float, float]
    offsets: tuple[float, float, float]
    bounds: BoundingBox3D = Field(
        description="Observed XYZ bounds recomputed from the actual point records."
    )
    header_bounds: BoundingBox3D = Field(description="XYZ bounds declared in the LAS header.")
    header_bounds_match: bool = Field(
        description=(
            "Whether declared header bounds match observed point bounds "
            "within coordinate-scale tolerance."
        )
    )
    coordinate_metadata: CoordinateMetadata
    dimensions: PointDimensions
    vlr_count: int
    evlr_count: int
    vlr_summaries: list[str] = Field(default_factory=list)
    classification_histogram: dict[int, int] = Field(default_factory=dict)
    return_number_histogram: dict[int, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NumericSummary(BaseModel):
    """Streaming min/max/mean summary for one numeric LAS dimension."""

    model_config = ConfigDict(frozen=True)

    minimum: float
    maximum: float
    mean: float


class ReturnAnalysis(BaseModel):
    """Geometry and intensity summary for one LAS return number."""

    model_config = ConfigDict(frozen=True)

    return_number: int
    point_count: int
    bounds: BoundingBox3D
    intensity: NumericSummary | None = None


class TimestampGroupAnalysis(BaseModel):
    """Diagnostics for contiguous records sharing exactly the same GPS time."""

    model_config = ConfigDict(frozen=True)

    group_count: int
    size_counts: dict[int, int] = Field(default_factory=dict)
    max_group_size: int

    two_record_groups: int
    two_record_return_pattern_counts: dict[str, int] = Field(default_factory=dict)

    two_record_r1_r2_groups: int
    two_record_r1_r2_fraction: float | None = None

    exact_pair_distance: NumericSummary | None = None
    exact_pair_abs_delta_x: NumericSummary | None = None
    exact_pair_abs_delta_y: NumericSummary | None = None
    exact_pair_abs_delta_z: NumericSummary | None = None
    exact_pair_abs_intensity_delta: NumericSummary | None = None


class AcquisitionAnalysis(BaseModel):
    """Streaming diagnostics describing how a LAS point cloud was acquired/exported.

    This is diagnostic metadata, not a reconstructed scanner trajectory and
    not a timber-volume result.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    point_count: int
    observed_bounds: BoundingBox3D | None = None

    gps_time_present: bool
    gps_time_first: float | None = None
    gps_time_last: float | None = None
    gps_time_min: float | None = None
    gps_time_max: float | None = None
    gps_time_span: float | None = None
    gps_time_non_decreasing: bool | None = None
    gps_time_backward_steps: int | None = None
    gps_time_equal_steps: int | None = None
    gps_time_min_positive_step: float | None = None
    gps_time_max_positive_step: float | None = None

    equal_time_adjacent_same_return_pairs: int | None = None
    equal_time_adjacent_cross_return_pairs: int | None = None
    equal_time_adjacent_r1_r2_pairs: int | None = None
    equal_time_adjacent_r1_r2_fraction: float | None = None

    paired_return_distance: NumericSummary | None = None
    paired_return_abs_delta_x: NumericSummary | None = None
    paired_return_abs_delta_y: NumericSummary | None = None
    paired_return_abs_delta_z: NumericSummary | None = None
    paired_return_abs_intensity_delta: NumericSummary | None = None

    timestamp_groups: TimestampGroupAnalysis | None = None

    intensity: NumericSummary | None = None
    rgb: dict[str, NumericSummary] = Field(default_factory=dict)
    scan_angle_rank: NumericSummary | None = None

    return_number_counts: dict[int, int] = Field(default_factory=dict)
    number_of_returns_counts: dict[int, int] = Field(default_factory=dict)
    point_source_id_counts: dict[int, int] = Field(default_factory=dict)
    scan_direction_flag_counts: dict[int, int] = Field(default_factory=dict)
    edge_of_flight_line_counts: dict[int, int] = Field(default_factory=dict)

    return_summaries: list[ReturnAnalysis] = Field(default_factory=list)

    xy_density_points_per_square_source_unit: float | None = Field(
        default=None,
        description=(
            "Whole-cloud point count divided by observed XY bounding-box area. "
            "This is only a coarse global statistic, not local surface density."
        ),
    )

    warnings: list[str] = Field(default_factory=list)


class CropBounds(BaseModel):
    """Explicit crop region. All bounds must be given in the same CRS/units
    as the source data; no implicit reprojection."""

    model_config = ConfigDict(frozen=True)

    min_x: float
    min_y: float
    max_x: float
    max_y: float
    min_z: float | None = None
    max_z: float | None = None


class SectionDefinition(BaseModel):
    """Defines a single cross-section slab used by CrossSectionVolumeEstimator."""

    model_config = ConfigDict(frozen=True)

    index: int
    station: float = Field(description="Distance along the longitudinal axis, source units.")
    thickness: float
    area: float | None = Field(
        default=None, description="Estimated cross-sectional area, source units squared."
    )
    point_count: int = 0


class ReferenceMeasurement(BaseModel):
    """A ground-truth / commercial measurement to compare estimates against."""

    model_config = ConfigDict(frozen=True)

    label: str
    value: float
    unit: VolumeUnit
    method: str = Field(description="e.g. 'manual tape cubicacion', 'client-provided'")
    recorded_at: datetime | None = None
    notes: str | None = None


class VolumeResult(BaseModel):
    """Result of a volume-estimation algorithm.

    IMPORTANT: `volume` is a *raw geometric* quantity from the chosen
    method. It must not be silently treated as a commercial timber volume
    (cubicacion) -- that requires an explicit, separately-tracked
    conversion rule which is out of scope for this PoC.
    """

    model_config = ConfigDict(frozen=True)

    method: str
    volume: float
    volume_unit: VolumeUnit
    point_count_input: int
    point_count_used: int
    parameters: dict[str, Any] = Field(default_factory=dict)
    bounds: BoundingBox3D
    warnings: list[str] = Field(default_factory=list)
    runtime_seconds: float
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Source file, CRS, code version, timestamp, etc.",
    )


class MeasurementRunStatus(StrEnum):
    """Lifecycle state for one persisted measurement run."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class MeasurementWarningSeverity(StrEnum):
    """Severity of a structured run-level warning."""

    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class MeasurementWarning(BaseModel):
    """Machine-readable warning suitable for CLI/API/UI presentation."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: MeasurementWarningSeverity = MeasurementWarningSeverity.WARNING
    message: str


class MeasurementArtifact(BaseModel):
    """Output artifact produced by a measurement run."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(description="Logical artifact type, e.g. front_profile or sensitivity_plot.")
    path: str
    media_type: str | None = None
    description: str | None = None


class TimberStackSummary(BaseModel):
    """Structured diagnostics from timber-stack localization."""

    model_config = ConfigDict(frozen=True)

    point_count_input: int
    point_count_selected: int
    selected_fraction: float

    detected_components: int | None = None
    longitudinal_coverage: float | None = None
    vertical_extent_fraction: float | None = None
    transverse_extent_fraction: float | None = None

    parameters: dict[str, Any] = Field(default_factory=dict)


class FrontCrossSectionSummary(BaseModel):
    """Observable front-wall geometry in source-coordinate units."""

    model_config = ConfigDict(frozen=True)

    longitudinal_span: float
    median_height: float
    maximum_height: float

    rectangle_area: float
    trapezoid_area: float
    valid_bin_fraction: float

    parameters: dict[str, Any] = Field(default_factory=dict)


class LogDetectionSummary(BaseModel):
    """Runtime summary for one visible-log detection pass."""

    model_config = ConfigDict(frozen=True)

    method: str
    candidate_count: int
    parameters: dict[str, Any] = Field(default_factory=dict)


class MeasurementRun(BaseModel):
    """Persistable record for one end-to-end measurement run.

    The record distinguishes directly observed geometry, optional volume
    estimates, diagnostics, warnings, artifacts, and provenance.

    It does not imply that source-coordinate units are metres and does not
    imply that a raw geometric volume is commercial timber cubicacion.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1"

    run_id: str
    source_path: str
    source_sha256: str | None = None

    status: MeasurementRunStatus = MeasurementRunStatus.STARTED

    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    code_version: str | None = None
    coordinate_metadata: CoordinateMetadata | None = None

    timber_stack: TimberStackSummary | None = None
    front_cross_section: FrontCrossSectionSummary | None = None
    log_detection: LogDetectionSummary | None = None

    results: list[VolumeResult] = Field(default_factory=list)
    reference: ReferenceMeasurement | None = None

    warnings: list[MeasurementWarning] = Field(default_factory=list)
    artifacts: list[MeasurementArtifact] = Field(default_factory=list)

    provenance: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


def new_run_id() -> str:
    return f"run-{int(time.time() * 1000)}"
