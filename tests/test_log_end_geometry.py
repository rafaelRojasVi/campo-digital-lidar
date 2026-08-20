from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

import numpy as np
import pytest

from lidar_core.front_view import (
    LocalFrontViewConfig,
    LocalFrontViewProjection,
    build_local_front_view_projection,
)
from lidar_core.log_end_geometry import (
    CandidateEvidenceAssociationConfig,
    ProjectedLogEndCandidate,
    ProjectedLogEndCandidateEvidence,
    associate_projected_log_end_evidence,
    candidate_support_overlap,
    project_log_end_candidate_area,
    project_log_end_candidate_on_front_view,
    project_log_end_candidates,
    project_log_end_candidates_with_support,
    resolve_log_end_candidate_associations,
)


def test_project_log_end_candidate_area_isotropic_pixels() -> None:
    result = project_log_end_candidate_area(
        radius_px=10.0,
        horizontal_units_per_pixel=0.02,
        vertical_units_per_pixel=0.02,
    )

    assert result.radius_px == pytest.approx(10.0)

    assert result.horizontal_radius_source_units == pytest.approx(0.2)
    assert result.vertical_radius_source_units == pytest.approx(0.2)

    assert result.projected_area_source_units_squared == pytest.approx(pi * 0.2 * 0.2)

    assert result.equivalent_radius_source_units == pytest.approx(0.2)
    assert result.equivalent_diameter_source_units == pytest.approx(0.4)


def test_project_log_end_candidate_area_preserves_anisotropic_raster_scale() -> None:
    result = project_log_end_candidate_area(
        radius_px=8.0,
        horizontal_units_per_pixel=0.03,
        vertical_units_per_pixel=0.015,
    )

    horizontal_radius = 8.0 * 0.03
    vertical_radius = 8.0 * 0.015

    expected_area = pi * horizontal_radius * vertical_radius
    expected_equivalent_radius = sqrt(horizontal_radius * vertical_radius)

    assert result.horizontal_radius_source_units == pytest.approx(horizontal_radius)

    assert result.vertical_radius_source_units == pytest.approx(vertical_radius)

    assert result.projected_area_source_units_squared == pytest.approx(expected_area)

    assert result.equivalent_radius_source_units == pytest.approx(expected_equivalent_radius)

    assert result.equivalent_diameter_source_units == pytest.approx(
        2.0 * expected_equivalent_radius
    )


@pytest.mark.parametrize(
    (
        "radius_px",
        "horizontal_units_per_pixel",
        "vertical_units_per_pixel",
    ),
    [
        (0.0, 0.02, 0.02),
        (-1.0, 0.02, 0.02),
        (10.0, 0.0, 0.02),
        (10.0, -0.02, 0.02),
        (10.0, 0.02, 0.0),
        (10.0, 0.02, -0.02),
        (float("nan"), 0.02, 0.02),
        (10.0, float("nan"), 0.02),
        (10.0, 0.02, float("nan")),
        (float("inf"), 0.02, 0.02),
        (10.0, float("inf"), 0.02),
        (10.0, 0.02, float("inf")),
    ],
)
def test_project_log_end_candidate_area_rejects_invalid_values(
    radius_px: float,
    horizontal_units_per_pixel: float,
    vertical_units_per_pixel: float,
) -> None:
    with pytest.raises(ValueError):
        project_log_end_candidate_area(
            radius_px=radius_px,
            horizontal_units_per_pixel=horizontal_units_per_pixel,
            vertical_units_per_pixel=vertical_units_per_pixel,
        )


@dataclass(frozen=True)
class _SyntheticCandidate:
    x_px: float
    y_px: float
    radius_px: float


def _build_calibrated_front_projection() -> LocalFrontViewProjection:
    # A simple 10 x 4 source-unit vertical plane.
    x_values = np.linspace(0.0, 10.0, 51)
    z_values = np.linspace(0.0, 4.0, 21)

    xx, zz = np.meshgrid(
        x_values,
        z_values,
    )

    xyz = np.column_stack(
        (
            xx.ravel(),
            np.zeros(xx.size, dtype=np.float64),
            zz.ravel(),
        )
    )

    return build_local_front_view_projection(
        xyz,
        LocalFrontViewConfig(
            window_index=0,
            yaw_degrees=0.0,
            n_windows=1,
            window_overlap_factor=1.0,
            raster_width=501,
            raster_height=201,
            longitudinal_quantile_low=0.0,
            longitudinal_quantile_high=1.0,
            image_quantile_low=0.0,
            image_quantile_high=1.0,
        ),
    )


def test_project_candidate_uses_front_view_calibration() -> None:
    projection = _build_calibrated_front_projection()

    assert projection.horizontal_units_per_pixel == pytest.approx(0.02)
    assert projection.vertical_units_per_pixel == pytest.approx(0.02)

    projected = project_log_end_candidate_on_front_view(
        radius_px=10.0,
        projection=projection,
    )

    assert projected.horizontal_radius_source_units == pytest.approx(0.2)
    assert projected.vertical_radius_source_units == pytest.approx(0.2)

    assert projected.projected_area_source_units_squared == pytest.approx(pi * 0.2**2)


def test_project_candidate_set_reports_explicit_candidate_area_sum() -> None:
    projection = _build_calibrated_front_projection()

    candidates = (
        _SyntheticCandidate(
            x_px=100.0,
            y_px=80.0,
            radius_px=5.0,
        ),
        _SyntheticCandidate(
            x_px=200.0,
            y_px=90.0,
            radius_px=10.0,
        ),
    )

    result = project_log_end_candidates(
        candidates,
        projection,
    )

    assert result.candidate_count == 2
    assert len(result.candidates) == 2

    expected_area = pi * 0.1**2 + pi * 0.2**2

    assert result.candidate_area_sum_source_units_squared == pytest.approx(expected_area)

    assert result.candidates[0].x_px == pytest.approx(100.0)
    assert result.candidates[0].y_px == pytest.approx(80.0)
    assert result.candidates[0].area.equivalent_diameter_source_units == pytest.approx(0.2)

    assert result.candidates[1].area.equivalent_diameter_source_units == pytest.approx(0.4)


def test_project_empty_candidate_set_is_zero_not_missing() -> None:
    projection = _build_calibrated_front_projection()

    result = project_log_end_candidates(
        (),
        projection,
    )

    assert result.candidate_count == 0
    assert result.candidates == ()
    assert result.candidate_area_sum_source_units_squared == pytest.approx(0.0)


def test_project_candidate_with_support_preserves_source_indices() -> None:
    projection = _build_calibrated_front_projection()

    visible_position = len(projection.visible_source_indices) // 2

    candidate = _SyntheticCandidate(
        x_px=float(projection.visible_pixel_x[visible_position]),
        y_px=float(projection.visible_pixel_y[visible_position]),
        radius_px=5.0,
    )

    result = project_log_end_candidates_with_support(
        (candidate,),
        projection,
    )

    assert result.candidate_count == 1
    assert result.candidates_with_visible_support == 1

    evidence = result.candidates[0]

    assert evidence.visible_support_count > 0
    assert evidence.visible_support_count == len(evidence.visible_source_indices)

    visible_indices = set(int(index) for index in projection.visible_source_indices)

    assert set(evidence.visible_source_indices) <= visible_indices

    assert result.visible_source_union_count == evidence.visible_support_count


def test_supported_candidate_union_does_not_double_count_shared_points() -> None:
    projection = _build_calibrated_front_projection()

    visible_position = len(projection.visible_source_indices) // 2

    x_px = float(projection.visible_pixel_x[visible_position])
    y_px = float(projection.visible_pixel_y[visible_position])

    candidates = (
        _SyntheticCandidate(
            x_px=x_px,
            y_px=y_px,
            radius_px=6.0,
        ),
        _SyntheticCandidate(
            x_px=x_px + 2.0,
            y_px=y_px,
            radius_px=6.0,
        ),
    )

    result = project_log_end_candidates_with_support(
        candidates,
        projection,
    )

    assert result.candidate_count == 2
    assert result.candidates_with_visible_support == 2

    summed_support = sum(candidate.visible_support_count for candidate in result.candidates)

    assert result.visible_source_union_count > 0
    assert result.visible_source_union_count < summed_support

    # The geometric candidate-area sum is intentionally still not deduplicated.
    assert result.candidate_area_sum_source_units_squared > 0.0


def test_candidate_without_visible_support_is_retained_explicitly() -> None:
    projection = _build_calibrated_front_projection()

    candidate = _SyntheticCandidate(
        x_px=-100.0,
        y_px=-100.0,
        radius_px=5.0,
    )

    result = project_log_end_candidates_with_support(
        (candidate,),
        projection,
    )

    assert result.candidate_count == 1
    assert result.candidates_with_visible_support == 0
    assert result.visible_source_union_count == 0

    evidence = result.candidates[0]

    assert evidence.visible_source_indices == ()
    assert evidence.visible_support_count == 0

    # Projection geometry still exists even though there is no observed LAS
    # support at the supplied image location.
    assert evidence.candidate.area.projected_area_source_units_squared > 0.0


def _candidate_evidence(
    source_indices: tuple[int, ...],
    *,
    x_px: float = 100.0,
    radius_px: float = 5.0,
    horizontal_units_per_pixel: float = 0.02,
    vertical_units_per_pixel: float = 0.02,
) -> ProjectedLogEndCandidateEvidence:
    area = project_log_end_candidate_area(
        radius_px=radius_px,
        horizontal_units_per_pixel=horizontal_units_per_pixel,
        vertical_units_per_pixel=vertical_units_per_pixel,
    )

    candidate = ProjectedLogEndCandidate(
        x_px=x_px,
        y_px=80.0,
        area=area,
    )

    return ProjectedLogEndCandidateEvidence(
        candidate=candidate,
        visible_source_indices=source_indices,
        visible_support_count=len(source_indices),
    )


def test_candidate_support_overlap_uses_smaller_support_fraction() -> None:
    left = _candidate_evidence(
        tuple(range(0, 10)),
    )

    right = _candidate_evidence(
        tuple(range(5, 15)),
    )

    shared_count, overlap_fraction = candidate_support_overlap(
        left,
        right,
    )

    assert shared_count == 5
    assert overlap_fraction == pytest.approx(0.5)


def test_associate_candidate_evidence_groups_shared_source_support() -> None:
    candidates = (
        _candidate_evidence(
            tuple(range(0, 10)),
            x_px=100.0,
        ),
        _candidate_evidence(
            tuple(range(5, 15)),
            x_px=105.0,
        ),
        _candidate_evidence(
            tuple(range(100, 110)),
            x_px=220.0,
        ),
        _candidate_evidence(
            (),
            x_px=300.0,
        ),
    )

    result = associate_projected_log_end_evidence(
        candidates,
        CandidateEvidenceAssociationConfig(
            min_shared_source_points=3,
            min_smaller_support_fraction=0.4,
        ),
    )

    assert result.candidate_count == 4
    assert result.supported_candidate_count == 3
    assert result.unsupported_candidate_indices == (3,)

    assert result.association_count == 2
    assert result.multi_candidate_association_count == 1

    assert result.associations[0].member_indices == (
        0,
        1,
    )

    assert result.associations[0].member_count == 2

    assert result.associations[0].visible_source_union_count == 15

    assert result.associations[1].member_indices == (2,)


def test_candidate_association_rejects_weak_overlap() -> None:
    candidates = (
        _candidate_evidence(
            tuple(range(0, 10)),
        ),
        _candidate_evidence(
            tuple(range(9, 19)),
        ),
    )

    result = associate_projected_log_end_evidence(
        candidates,
        CandidateEvidenceAssociationConfig(
            min_shared_source_points=2,
            min_smaller_support_fraction=0.3,
        ),
    )

    assert result.association_count == 2
    assert result.multi_candidate_association_count == 0


def test_candidate_association_is_connected_component_based() -> None:
    # A overlaps B, B overlaps C, while A and C do not overlap directly.
    candidates = (
        _candidate_evidence(
            tuple(range(0, 10)),
        ),
        _candidate_evidence(
            tuple(range(5, 15)),
        ),
        _candidate_evidence(
            tuple(range(10, 20)),
        ),
    )

    result = associate_projected_log_end_evidence(
        candidates,
        CandidateEvidenceAssociationConfig(
            min_shared_source_points=5,
            min_smaller_support_fraction=0.5,
        ),
    )

    assert result.association_count == 1
    assert result.multi_candidate_association_count == 1

    assert result.associations[0].member_indices == (
        0,
        1,
        2,
    )


@pytest.mark.parametrize(
    "config",
    [
        CandidateEvidenceAssociationConfig(
            min_shared_source_points=0,
        ),
        CandidateEvidenceAssociationConfig(
            min_smaller_support_fraction=0.0,
        ),
        CandidateEvidenceAssociationConfig(
            min_smaller_support_fraction=1.01,
        ),
    ],
)
def test_candidate_association_rejects_invalid_config(
    config: CandidateEvidenceAssociationConfig,
) -> None:
    with pytest.raises(ValueError):
        associate_projected_log_end_evidence(
            (),
            config,
        )


def test_resolve_single_observation_preserves_candidate_geometry() -> None:
    candidate = _candidate_evidence(
        tuple(range(10)),
        radius_px=5.0,
    )

    association = associate_projected_log_end_evidence(
        (candidate,),
    )

    result = resolve_log_end_candidate_associations(
        (candidate,),
        association,
    )

    assert result.observation_count == 1
    assert result.supported_observation_count == 1
    assert result.association_count == 1
    assert result.multi_observation_association_count == 0
    assert result.representative_method == "mean_equivalent_diameter"

    resolved = result.associations[0]

    expected_diameter = candidate.candidate.area.equivalent_diameter_source_units

    assert resolved.representative_equivalent_diameter_source_units == pytest.approx(
        expected_diameter
    )

    assert resolved.projected_area_source_units_squared == pytest.approx(
        candidate.candidate.area.projected_area_source_units_squared
    )

    assert resolved.relative_diameter_range == pytest.approx(0.0)


def test_resolve_duplicate_uses_mean_equivalent_diameter() -> None:
    left = _candidate_evidence(
        tuple(range(0, 10)),
        radius_px=5.0,
    )

    right = _candidate_evidence(
        tuple(range(5, 15)),
        radius_px=7.0,
    )

    association = associate_projected_log_end_evidence(
        (left, right),
        CandidateEvidenceAssociationConfig(
            min_shared_source_points=3,
            min_smaller_support_fraction=0.30,
        ),
    )

    result = resolve_log_end_candidate_associations(
        (left, right),
        association,
    )

    assert result.association_count == 1
    assert result.multi_observation_association_count == 1

    resolved = result.associations[0]

    left_diameter = left.candidate.area.equivalent_diameter_source_units

    right_diameter = right.candidate.area.equivalent_diameter_source_units

    expected_diameter = (left_diameter + right_diameter) / 2.0

    expected_area = pi * (expected_diameter / 2.0) ** 2

    assert resolved.representative_equivalent_diameter_source_units == pytest.approx(
        expected_diameter
    )

    assert resolved.projected_area_source_units_squared == pytest.approx(expected_area)

    assert resolved.relative_diameter_range == pytest.approx(
        abs(right_diameter - left_diameter) / expected_diameter
    )

    assert result.projected_area_sum_source_units_squared == pytest.approx(expected_area)


def test_resolve_propagates_unsupported_observations_without_area() -> None:
    supported = _candidate_evidence(
        tuple(range(10)),
    )

    unsupported = _candidate_evidence(
        (),
        x_px=300.0,
    )

    association = associate_projected_log_end_evidence(
        (
            supported,
            unsupported,
        ),
    )

    result = resolve_log_end_candidate_associations(
        (
            supported,
            unsupported,
        ),
        association,
    )

    assert result.observation_count == 2
    assert result.supported_observation_count == 1
    assert result.unsupported_observation_indices == (1,)
    assert result.association_count == 1

    assert result.projected_area_sum_source_units_squared == pytest.approx(
        supported.candidate.area.projected_area_source_units_squared
    )


def test_resolver_rejects_mismatched_association_summary() -> None:
    candidate = _candidate_evidence(
        tuple(range(10)),
    )

    association = associate_projected_log_end_evidence(
        (candidate,),
    )

    with pytest.raises(ValueError):
        resolve_log_end_candidate_associations(
            (),
            association,
        )


def test_candidate_association_can_exclude_same_observation_group() -> None:
    candidates = (
        _candidate_evidence(
            tuple(range(0, 10)),
            x_px=100.0,
        ),
        _candidate_evidence(
            tuple(range(5, 15)),
            x_px=105.0,
        ),
        _candidate_evidence(
            tuple(range(5, 15)),
            x_px=105.0,
        ),
    )

    result = associate_projected_log_end_evidence(
        candidates,
        CandidateEvidenceAssociationConfig(
            min_shared_source_points=3,
            min_smaller_support_fraction=0.30,
        ),
        observation_group_ids=(
            0,
            0,
            1,
        ),
    )

    assert result.association_count == 2

    member_sets = {association.member_indices for association in result.associations}

    assert (0, 2) in member_sets
    assert (1,) in member_sets


def test_candidate_association_rejects_mismatched_observation_groups() -> None:
    candidate = _candidate_evidence(
        tuple(range(10)),
    )

    with pytest.raises(
        ValueError,
        match="observation_group_ids length",
    ):
        associate_projected_log_end_evidence(
            (candidate,),
            observation_group_ids=(),
        )
