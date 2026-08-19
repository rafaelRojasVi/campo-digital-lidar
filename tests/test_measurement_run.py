from __future__ import annotations

from lidar_core.models import (
    CoordinateMetadata,
    FrontCrossSectionSummary,
    LogDetectionSummary,
    MeasurementArtifact,
    MeasurementRun,
    MeasurementRunStatus,
    MeasurementWarning,
    MeasurementWarningSeverity,
    TimberStackSummary,
)


def test_measurement_run_remains_backwards_compatible() -> None:
    run = MeasurementRun(
        run_id="run-test",
        source_path="/data/example.las",
    )

    assert run.schema_version == "1"
    assert run.status == MeasurementRunStatus.STARTED
    assert run.results == []
    assert run.warnings == []
    assert run.artifacts == []


def test_measurement_run_serializes_structured_pipeline_state() -> None:
    run = MeasurementRun(
        run_id="run-real-001",
        source_path="/data/timber.las",
        source_sha256="abc123",
        code_version="34363a0",
        status=MeasurementRunStatus.COMPLETED,
        coordinate_metadata=CoordinateMetadata(
            is_explicit=False,
        ),
        timber_stack=TimberStackSummary(
            point_count_input=4_074_894,
            point_count_selected=1_342_183,
            selected_fraction=1_342_183 / 4_074_894,
            detected_components=3,
            longitudinal_coverage=0.81667,
            vertical_extent_fraction=0.77083,
            transverse_extent_fraction=0.20833,
        ),
        front_cross_section=FrontCrossSectionSummary(
            longitudinal_span=61.361422,
            median_height=3.688422,
            maximum_height=4.632758,
            rectangle_area=217.176317,
            trapezoid_area=216.434772,
            valid_bin_fraction=1.0,
            parameters={
                "n_bins": 160,
                "vertical_quantile_low": 0.02,
                "vertical_quantile_high": 0.98,
            },
        ),
        log_detection=LogDetectionSummary(
            method="radial-v5",
            candidate_count=204,
        ),
        warnings=[
            MeasurementWarning(
                code="crs_unconfirmed",
                severity=MeasurementWarningSeverity.BLOCKER,
                message="CRS and physical coordinate units are not confirmed.",
            ),
            MeasurementWarning(
                code="pile_depth_unobserved",
                severity=MeasurementWarningSeverity.BLOCKER,
                message="No coherent rear timber wall was observed.",
            ),
        ],
        artifacts=[
            MeasurementArtifact(
                kind="front_profile",
                path="reports/out/run-real-001/front-profile.png",
                media_type="image/png",
            )
        ],
    )

    payload = run.model_dump(mode="json")

    assert payload["schema_version"] == "1"
    assert payload["status"] == "completed"

    assert payload["timber_stack"]["point_count_selected"] == 1_342_183

    assert payload["front_cross_section"]["rectangle_area"] == 217.176317

    assert payload["log_detection"]["method"] == "radial-v5"
    assert payload["log_detection"]["candidate_count"] == 204

    assert payload["warnings"][0]["code"] == "crs_unconfirmed"
    assert payload["warnings"][0]["severity"] == "blocker"

    assert payload["artifacts"][0]["kind"] == "front_profile"


def test_measurement_run_does_not_infer_coordinate_units() -> None:
    run = MeasurementRun(
        run_id="run-no-units",
        source_path="/data/example.las",
        coordinate_metadata=CoordinateMetadata(
            is_explicit=False,
        ),
    )

    assert run.coordinate_metadata is not None
    assert run.coordinate_metadata.horizontal_units is None
    assert run.coordinate_metadata.crs_epsg is None
