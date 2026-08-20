"""Projected geometry for visible log-end candidates.

This module converts image-space candidate geometry into the coordinate scale
of a calibrated front-view raster.

The result remains candidate geometry:

- it does not confirm that a detection is a real log end;
- it does not infer hidden log length;
- it does not calculate timber volume;
- it does not assume that source-coordinate units are metres.

A circular candidate in pixel coordinates becomes an ellipse when horizontal
and vertical raster scales differ.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Protocol

from lidar_core.front_view import (
    LocalFrontViewProjection,
    backproject_visible_pixel_disk,
)


@dataclass(frozen=True)
class ProjectedLogEndArea:
    """Projected area of one circular image-space log-end candidate."""

    radius_px: float

    horizontal_units_per_pixel: float
    vertical_units_per_pixel: float

    horizontal_radius_source_units: float
    vertical_radius_source_units: float

    projected_area_source_units_squared: float

    equivalent_radius_source_units: float
    equivalent_diameter_source_units: float


def project_log_end_candidate_area(
    radius_px: float,
    horizontal_units_per_pixel: float,
    vertical_units_per_pixel: float,
) -> ProjectedLogEndArea:
    """Project one circular image-space candidate into source-coordinate units.

    The raster candidate is circular in pixel space. If the raster's physical
    horizontal and vertical pixel scales differ, that circle maps to an
    ellipse in source-coordinate space.

    The projected ellipse area is:

        pi * (radius_px * horizontal_scale)
           * (radius_px * vertical_scale)

    The equivalent radius/diameter are area-preserving circular equivalents;
    they are convenience diagnostics, not validated physical log diameters.
    """

    values = {
        "radius_px": radius_px,
        "horizontal_units_per_pixel": horizontal_units_per_pixel,
        "vertical_units_per_pixel": vertical_units_per_pixel,
    }

    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

        if value <= 0:
            raise ValueError(f"{name} must be positive")

    horizontal_radius = radius_px * horizontal_units_per_pixel
    vertical_radius = radius_px * vertical_units_per_pixel

    projected_area = pi * horizontal_radius * vertical_radius

    equivalent_radius = sqrt(projected_area / pi)

    return ProjectedLogEndArea(
        radius_px=float(radius_px),
        horizontal_units_per_pixel=float(horizontal_units_per_pixel),
        vertical_units_per_pixel=float(vertical_units_per_pixel),
        horizontal_radius_source_units=float(horizontal_radius),
        vertical_radius_source_units=float(vertical_radius),
        projected_area_source_units_squared=float(projected_area),
        equivalent_radius_source_units=float(equivalent_radius),
        equivalent_diameter_source_units=float(2.0 * equivalent_radius),
    )


class LogEndCandidateLike(Protocol):
    """Minimal read-only image-space geometry required from a detector."""

    @property
    def x_px(self) -> float: ...

    @property
    def y_px(self) -> float: ...

    @property
    def radius_px(self) -> float: ...


@dataclass(frozen=True)
class ProjectedLogEndCandidate:
    """One detector candidate with its calibrated projected geometry."""

    x_px: float
    y_px: float
    area: ProjectedLogEndArea


@dataclass(frozen=True)
class ProjectedLogEndCandidateSummary:
    """Projected candidate geometry before validation or deduplication."""

    candidates: tuple[ProjectedLogEndCandidate, ...]
    candidate_count: int
    candidate_area_sum_source_units_squared: float


def project_log_end_candidate_on_front_view(
    radius_px: float,
    projection: LocalFrontViewProjection,
) -> ProjectedLogEndArea:
    """Project one image-space radius using a front-view calibration."""

    return project_log_end_candidate_area(
        radius_px=radius_px,
        horizontal_units_per_pixel=projection.horizontal_units_per_pixel,
        vertical_units_per_pixel=projection.vertical_units_per_pixel,
    )


def project_log_end_candidates(
    candidates: Sequence[LogEndCandidateLike],
    projection: LocalFrontViewProjection,
) -> ProjectedLogEndCandidateSummary:
    """Project one detector candidate set into source-coordinate area.

    This sum is deliberately called a candidate-area sum. Candidates may be
    false positives or overlap with each other, and candidates from different
    front-view windows may refer to the same physical log end.

    No deduplication, timber-volume inference, or commercial cubicación rule is
    applied here.
    """

    projected = tuple(
        ProjectedLogEndCandidate(
            x_px=float(candidate.x_px),
            y_px=float(candidate.y_px),
            area=project_log_end_candidate_on_front_view(
                candidate.radius_px,
                projection,
            ),
        )
        for candidate in candidates
    )

    area_sum = sum(candidate.area.projected_area_source_units_squared for candidate in projected)

    return ProjectedLogEndCandidateSummary(
        candidates=projected,
        candidate_count=len(projected),
        candidate_area_sum_source_units_squared=float(area_sum),
    )


@dataclass(frozen=True)
class ProjectedLogEndCandidateEvidence:
    """Projected candidate plus visible LAS-point support."""

    candidate: ProjectedLogEndCandidate
    visible_source_indices: tuple[int, ...]
    visible_support_count: int


@dataclass(frozen=True)
class ProjectedLogEndEvidenceSummary:
    """Candidate geometry with explicit point-level observation support."""

    candidates: tuple[ProjectedLogEndCandidateEvidence, ...]
    candidate_count: int
    candidates_with_visible_support: int
    candidate_area_sum_source_units_squared: float
    visible_source_union_count: int


def project_log_end_candidates_with_support(
    candidates: Sequence[LogEndCandidateLike],
    projection: LocalFrontViewProjection,
) -> ProjectedLogEndEvidenceSummary:
    """Project candidates and attach visible source-point evidence.

    Candidate areas are still summed without deduplication. The returned source
    indices provide the evidence needed for later cross-window association.

    A candidate with no visible source support is retained rather than silently
    removed.
    """

    projected_summary = project_log_end_candidates(
        candidates,
        projection,
    )

    evidence: list[ProjectedLogEndCandidateEvidence] = []
    source_union: set[int] = set()
    supported_count = 0

    for candidate in projected_summary.candidates:
        source_indices_array = backproject_visible_pixel_disk(
            projection,
            x_px=candidate.x_px,
            y_px=candidate.y_px,
            radius_px=candidate.area.radius_px,
        )

        source_indices = tuple(int(index) for index in source_indices_array)

        if source_indices:
            supported_count += 1
            source_union.update(source_indices)

        evidence.append(
            ProjectedLogEndCandidateEvidence(
                candidate=candidate,
                visible_source_indices=source_indices,
                visible_support_count=len(source_indices),
            )
        )

    return ProjectedLogEndEvidenceSummary(
        candidates=tuple(evidence),
        candidate_count=len(evidence),
        candidates_with_visible_support=supported_count,
        candidate_area_sum_source_units_squared=(
            projected_summary.candidate_area_sum_source_units_squared
        ),
        visible_source_union_count=len(source_union),
    )


@dataclass(frozen=True)
class CandidateEvidenceAssociationConfig:
    """Thresholds for associating candidate observations by LAS support."""

    min_shared_source_points: int = 3
    min_smaller_support_fraction: float = 0.30


@dataclass(frozen=True)
class CandidateEvidenceAssociation:
    """Connected group of candidate observations sharing source evidence."""

    member_indices: tuple[int, ...]
    member_count: int
    visible_source_union_count: int


@dataclass(frozen=True)
class CandidateEvidenceAssociationSummary:
    """Association result without claiming unique physical log identity."""

    associations: tuple[CandidateEvidenceAssociation, ...]
    candidate_count: int
    supported_candidate_count: int
    unsupported_candidate_indices: tuple[int, ...]
    association_count: int
    multi_candidate_association_count: int


def candidate_support_overlap(
    left: ProjectedLogEndCandidateEvidence,
    right: ProjectedLogEndCandidateEvidence,
) -> tuple[int, float]:
    """Return shared-point count and overlap relative to smaller support.

    The overlap fraction is:

        |A ∩ B| / min(|A|, |B|)

    This is intentionally more appropriate here than Jaccard overlap because
    two projections of the same visible feature may backproject disks of
    different sizes.

    Both evidence objects must refer to the same ordered source point cloud.
    """

    left_support = set(left.visible_source_indices)
    right_support = set(right.visible_source_indices)

    if not left_support or not right_support:
        return 0, 0.0

    shared_count = len(left_support.intersection(right_support))

    smaller_support_count = min(
        len(left_support),
        len(right_support),
    )

    overlap_fraction = shared_count / smaller_support_count

    return shared_count, float(overlap_fraction)


def associate_projected_log_end_evidence(
    candidates: Sequence[ProjectedLogEndCandidateEvidence],
    config: CandidateEvidenceAssociationConfig | None = None,
    *,
    observation_group_ids: Sequence[int] | None = None,
) -> CandidateEvidenceAssociationSummary:
    """Associate candidate observations using shared source-point evidence.

    This creates connected components in an evidence-overlap graph. A group is
    an association hypothesis only; it is not yet a confirmed unique log end.

    Unsupported candidates remain explicit and are not silently discarded.
    """

    if config is None:
        config = CandidateEvidenceAssociationConfig()

    if config.min_shared_source_points < 1:
        raise ValueError("min_shared_source_points must be >= 1")

    if not (0.0 < config.min_smaller_support_fraction <= 1.0):
        raise ValueError("min_smaller_support_fraction must be in (0, 1]")

    candidate_count = len(candidates)

    resolved_group_ids: tuple[int, ...] | None = None

    if observation_group_ids is not None:
        if len(observation_group_ids) != candidate_count:
            raise ValueError("observation_group_ids length must match candidates")

        resolved_group_ids = tuple(int(group_id) for group_id in observation_group_ids)

    parent = list(range(candidate_count))

    component_group_ids: list[set[int]] | None = None

    if resolved_group_ids is not None:
        component_group_ids = [{group_id} for group_id in resolved_group_ids]

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]

        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)

        if left_root == right_root:
            return

        if component_group_ids is not None:
            left_groups = component_group_ids[left_root]
            right_groups = component_group_ids[right_root]

            if left_groups.intersection(right_groups):
                return

        parent[right_root] = left_root

        if component_group_ids is not None:
            component_group_ids[left_root].update(component_group_ids[right_root])

    supported_indices = [
        index for index, candidate in enumerate(candidates) if candidate.visible_support_count > 0
    ]

    unsupported_indices = tuple(
        index for index, candidate in enumerate(candidates) if candidate.visible_support_count == 0
    )

    for left_position, left_index in enumerate(supported_indices):
        for right_index in supported_indices[left_position + 1 :]:
            if (
                resolved_group_ids is not None
                and resolved_group_ids[left_index] == resolved_group_ids[right_index]
            ):
                continue

            shared_count, overlap_fraction = candidate_support_overlap(
                candidates[left_index],
                candidates[right_index],
            )

            if (
                shared_count >= config.min_shared_source_points
                and overlap_fraction >= config.min_smaller_support_fraction
            ):
                union(
                    left_index,
                    right_index,
                )

    grouped: dict[int, list[int]] = {}

    for candidate_index in supported_indices:
        root = find(candidate_index)

        grouped.setdefault(
            root,
            [],
        ).append(candidate_index)

    associations: list[CandidateEvidenceAssociation] = []

    for member_indices_list in grouped.values():
        member_indices = tuple(sorted(member_indices_list))

        source_union: set[int] = set()

        for member_index in member_indices:
            source_union.update(candidates[member_index].visible_source_indices)

        associations.append(
            CandidateEvidenceAssociation(
                member_indices=member_indices,
                member_count=len(member_indices),
                visible_source_union_count=len(source_union),
            )
        )

    associations.sort(key=lambda association: association.member_indices[0])

    association_tuple = tuple(associations)

    return CandidateEvidenceAssociationSummary(
        associations=association_tuple,
        candidate_count=candidate_count,
        supported_candidate_count=len(supported_indices),
        unsupported_candidate_indices=(unsupported_indices),
        association_count=len(association_tuple),
        multi_candidate_association_count=sum(
            association.member_count > 1 for association in association_tuple
        ),
    )


@dataclass(frozen=True)
class ResolvedLogEndCandidateAssociation:
    """Association-resolved candidate geometry.

    Multiple observations associated through shared LAS evidence are summarized
    by their mean equivalent diameter. This remains candidate geometry, not a
    confirmed physical log-end measurement.
    """

    member_indices: tuple[int, ...]
    observation_count: int

    representative_equivalent_diameter_source_units: float
    projected_area_source_units_squared: float

    minimum_equivalent_diameter_source_units: float
    maximum_equivalent_diameter_source_units: float
    relative_diameter_range: float

    visible_source_union_count: int


@dataclass(frozen=True)
class ResolvedLogEndCandidateAssociationSummary:
    """Association-resolved projected candidate geometry."""

    associations: tuple[ResolvedLogEndCandidateAssociation, ...]

    observation_count: int
    supported_observation_count: int
    unsupported_observation_indices: tuple[int, ...]

    association_count: int
    multi_observation_association_count: int

    projected_area_sum_source_units_squared: float
    representative_method: str


def resolve_log_end_candidate_associations(
    candidates: Sequence[ProjectedLogEndCandidateEvidence],
    association_summary: CandidateEvidenceAssociationSummary,
) -> ResolvedLogEndCandidateAssociationSummary:
    """Resolve associated observations using mean equivalent diameter.

    The input associations are evidence-based candidate hypotheses. This
    function does not confirm unique physical logs and does not calculate
    timber volume or commercial cubicación.

    Unsupported observations remain explicit and are excluded from the
    association-resolved projected-area sum.
    """

    if association_summary.candidate_count != len(candidates):
        raise ValueError("association summary candidate_count does not match candidates")

    resolved: list[ResolvedLogEndCandidateAssociation] = []

    projected_area_sum = 0.0

    for association in association_summary.associations:
        if not association.member_indices:
            raise ValueError("association must contain at least one member")

        member_indices = tuple(association.member_indices)

        if len(set(member_indices)) != len(member_indices):
            raise ValueError("association member indices must be unique")

        for member_index in member_indices:
            if not 0 <= member_index < len(candidates):
                raise ValueError("association member index is out of range")

        diameters = tuple(
            candidates[member_index].candidate.area.equivalent_diameter_source_units
            for member_index in member_indices
        )

        representative_diameter = sum(diameters) / len(diameters)

        minimum_diameter = min(diameters)
        maximum_diameter = max(diameters)

        relative_diameter_range = (maximum_diameter - minimum_diameter) / representative_diameter

        projected_area = pi * (representative_diameter / 2.0) ** 2

        resolved.append(
            ResolvedLogEndCandidateAssociation(
                member_indices=member_indices,
                observation_count=len(member_indices),
                representative_equivalent_diameter_source_units=float(representative_diameter),
                projected_area_source_units_squared=float(projected_area),
                minimum_equivalent_diameter_source_units=float(minimum_diameter),
                maximum_equivalent_diameter_source_units=float(maximum_diameter),
                relative_diameter_range=float(relative_diameter_range),
                visible_source_union_count=(association.visible_source_union_count),
            )
        )

        projected_area_sum += projected_area

    resolved_tuple = tuple(resolved)

    return ResolvedLogEndCandidateAssociationSummary(
        associations=resolved_tuple,
        observation_count=len(candidates),
        supported_observation_count=(association_summary.supported_candidate_count),
        unsupported_observation_indices=(association_summary.unsupported_candidate_indices),
        association_count=len(resolved_tuple),
        multi_observation_association_count=sum(
            association.observation_count > 1 for association in resolved_tuple
        ),
        projected_area_sum_source_units_squared=float(projected_area_sum),
        representative_method=("mean_equivalent_diameter"),
    )
