from __future__ import annotations

import json
from math import pi

import pytest

from lidar_core.log_end_geometry import (
    CandidateEvidenceAssociation,
    CandidateEvidenceAssociationConfig,
    CandidateEvidenceAssociationSummary,
    ProjectedLogEndCandidate,
    ProjectedLogEndCandidateEvidence,
    project_log_end_candidate_area,
    resolve_log_end_candidate_associations,
)
from lidar_core.log_ends import LogEndDetectionConfig
from lidar_core.visible_log_end_analysis import (
    VisibleLogEndAnalysisConfig,
    VisibleLogEndAnalysisResult,
    VisibleLogEndWindowSummary,
)
from lidar_io.run_artifacts import (
    VISIBLE_LOG_END_ANALYSIS_FILENAME,
    write_visible_log_end_analysis_artifact,
)


def _analysis_result() -> VisibleLogEndAnalysisResult:
    area = project_log_end_candidate_area(
        radius_px=5.0,
        horizontal_units_per_pixel=0.02,
        vertical_units_per_pixel=0.02,
    )

    evidence = ProjectedLogEndCandidateEvidence(
        candidate=ProjectedLogEndCandidate(
            x_px=100.0,
            y_px=80.0,
            area=area,
        ),
        visible_source_indices=(
            10,
            11,
            12,
        ),
        visible_support_count=3,
    )

    association = CandidateEvidenceAssociationSummary(
        associations=(
            CandidateEvidenceAssociation(
                member_indices=(0,),
                member_count=1,
                visible_source_union_count=3,
            ),
        ),
        candidate_count=1,
        supported_candidate_count=1,
        unsupported_candidate_indices=(),
        association_count=1,
        multi_candidate_association_count=0,
    )

    resolved = resolve_log_end_candidate_associations(
        (evidence,),
        association,
    )

    return VisibleLogEndAnalysisResult(
        config=VisibleLogEndAnalysisConfig(
            n_windows=1,
        ),
        detector_config=LogEndDetectionConfig(),
        association_config=(CandidateEvidenceAssociationConfig()),
        windows=(
            VisibleLogEndWindowSummary(
                window_index=0,
                visible_point_count=100,
                raw_candidate_count=1,
                candidate_count=1,
                supported_candidate_count=1,
                candidate_area_sum_source_units_squared=(area.projected_area_source_units_squared),
                visible_source_union_count=3,
                horizontal_units_per_pixel=0.02,
                vertical_units_per_pixel=0.02,
            ),
        ),
        observations=(evidence,),
        observation_window_indices=(0,),
        association_summary=association,
        resolved_summary=resolved,
    )


def test_write_visible_log_end_analysis_artifact(
    tmp_path,
) -> None:
    result = _analysis_result()

    artifact = write_visible_log_end_analysis_artifact(
        result,
        tmp_path,
    )

    assert artifact.kind == "visible_log_end_candidate_analysis"

    assert artifact.path == VISIBLE_LOG_END_ANALYSIS_FILENAME

    assert artifact.media_type == "application/json"

    path = tmp_path / artifact.path

    payload = json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )

    assert payload["schema_version"] == "1"
    assert payload["coordinate_units"] == "source_units"

    assert payload["semantics"]["confirmed_log_count"] is False

    assert payload["semantics"]["validated_solid_wood_area"] is False

    assert payload["semantics"]["timber_volume"] is False

    assert payload["semantics"]["commercial_cubicacion"] is False

    assert payload["semantics"]["hidden_log_length_inferred"] is False

    assert payload["summary"]["observation_count"] == 1

    assert payload["summary"]["association_hypothesis_count"] == 1

    assert payload["summary"]["representative_method"] == "mean_equivalent_diameter"

    expected_area = pi * 0.1**2

    assert payload["quantity"]["value"] == pytest.approx(expected_area)

    assert payload["quantity"]["unit"] == "source_units_squared"

    observation = payload["observations"][0]

    assert observation["window_index"] == 0
    assert observation["visible_support_count"] == 3

    assert observation["visible_source_indices"] == [
        10,
        11,
        12,
    ]

    association = payload["associations"][0]

    assert association["member_indices"] == [0]
    assert association["observation_count"] == 1
    assert association["relative_diameter_range"] == pytest.approx(0.0)

    qc = payload["qc"]["relative_diameter_range_quantiles"]

    assert qc["q50"] == pytest.approx(0.0)
    assert qc["max"] == pytest.approx(0.0)


def test_visible_log_end_artifact_handles_empty_analysis(
    tmp_path,
) -> None:
    association = CandidateEvidenceAssociationSummary(
        associations=(),
        candidate_count=0,
        supported_candidate_count=0,
        unsupported_candidate_indices=(),
        association_count=0,
        multi_candidate_association_count=0,
    )

    resolved = resolve_log_end_candidate_associations(
        (),
        association,
    )

    result = VisibleLogEndAnalysisResult(
        config=VisibleLogEndAnalysisConfig(
            n_windows=1,
        ),
        detector_config=LogEndDetectionConfig(),
        association_config=(CandidateEvidenceAssociationConfig()),
        windows=(),
        observations=(),
        observation_window_indices=(),
        association_summary=association,
        resolved_summary=resolved,
    )

    artifact = write_visible_log_end_analysis_artifact(
        result,
        tmp_path,
    )

    payload = json.loads(
        (tmp_path / artifact.path).read_text(
            encoding="utf-8",
        )
    )

    assert payload["quantity"]["value"] == 0.0
    assert payload["observations"] == []
    assert payload["associations"] == []

    qc = payload["qc"]["relative_diameter_range_quantiles"]

    assert qc == {
        "q50": None,
        "q75": None,
        "q90": None,
        "q95": None,
        "q99": None,
        "max": None,
    }
