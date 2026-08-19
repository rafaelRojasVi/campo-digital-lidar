"""Automatic geometric localization of elongated timber-stack regions.

This module deliberately operates in source coordinate units. It does not
assume a CRS, metres, timber volume, or a sensor model.

The v1 detector searches for a structure that is simultaneously:
- longitudinally persistent,
- vertically extended,
- spatially connected in transverse/vertical space.

It does not use a manually labelled ROI or hard-coded client coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class TimberStackDetectionConfig:
    """Dimensionless/grid parameters for geometric stack localization."""

    longitudinal_bins: int = 120
    transverse_bins: int = 48
    vertical_bins: int = 48
    min_longitudinal_coverage: float = 0.15
    min_vertical_extent_fraction: float = 0.15
    ignore_lowest_vertical_fraction: float = 0.08
    pca_sample_size: int = 300_000
    seed: int = 42


@dataclass(frozen=True)
class TimberStackDetectionResult:
    """Result of geometric timber-stack localization."""

    mask: np.ndarray
    center_xy: np.ndarray
    longitudinal_axis: np.ndarray
    transverse_axis: np.ndarray
    selected_point_count: int
    selected_point_fraction: float
    longitudinal_coverage: float
    vertical_extent_fraction: float
    transverse_extent_fraction: float
    score: float
    component_count: int


def _principal_xy_axes(
    points: np.ndarray,
    *,
    sample_size: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Estimate deterministic longitudinal/transverse XY axes with PCA."""

    rng = np.random.default_rng(seed)

    if len(points) > sample_size:
        sample_idx = rng.choice(len(points), size=sample_size, replace=False)
        xy = points[sample_idx, :2]
    else:
        xy = points[:, :2]

    center = xy.mean(axis=0)
    centered = xy - center
    covariance = np.cov(centered.T)

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    longitudinal = eigenvectors[:, np.argmax(eigenvalues)]

    # PCA eigenvector signs are arbitrary. Make the orientation deterministic.
    if longitudinal[0] < 0 or (np.isclose(longitudinal[0], 0.0) and longitudinal[1] < 0):
        longitudinal = -longitudinal

    transverse = np.array([-longitudinal[1], longitudinal[0]])

    return center, longitudinal, transverse


def _bin_indices(
    values: np.ndarray,
    minimum: float,
    maximum: float,
    bins: int,
) -> np.ndarray:
    span = maximum - minimum
    if span <= 0:
        return np.zeros(len(values), dtype=np.int64)

    normalized = (values - minimum) / span
    indices = np.floor(normalized * bins).astype(np.int64)
    return np.clip(indices, 0, bins - 1)


def detect_timber_stack(
    points: np.ndarray,
    config: TimberStackDetectionConfig | None = None,
) -> TimberStackDetectionResult:
    """Locate the strongest elongated, vertically extended structure.

    Parameters
    ----------
    points:
        ``(N, 3)`` XYZ array in the source coordinate system.
    config:
        Grid/detection configuration. Parameters are dimensionless and do not
        imply metres or any other physical unit.

    Returns
    -------
    TimberStackDetectionResult
        Boolean point mask plus diagnostic geometry.

    Notes
    -----
    This is a localization experiment, not a timber classifier and not a
    volume/cubicacion estimator.
    """

    if config is None:
        config = TimberStackDetectionConfig()

    points = np.asarray(points, dtype=np.float64)

    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points must have shape (N, 3)")

    if len(points) < 100:
        raise ValueError("at least 100 points are required")

    if config.longitudinal_bins < 2:
        raise ValueError("longitudinal_bins must be >= 2")
    if config.transverse_bins < 2:
        raise ValueError("transverse_bins must be >= 2")
    if config.vertical_bins < 2:
        raise ValueError("vertical_bins must be >= 2")

    center_xy, longitudinal_axis, transverse_axis = _principal_xy_axes(
        points,
        sample_size=config.pca_sample_size,
        seed=config.seed,
    )

    centered_xy = points[:, :2] - center_xy
    longitudinal = centered_xy @ longitudinal_axis
    transverse = centered_xy @ transverse_axis
    vertical = points[:, 2]

    long_min = float(longitudinal.min())
    long_max = float(longitudinal.max())
    transverse_min = float(transverse.min())
    transverse_max = float(transverse.max())
    vertical_min = float(vertical.min())
    vertical_max = float(vertical.max())

    long_idx = _bin_indices(
        longitudinal,
        long_min,
        long_max,
        config.longitudinal_bins,
    )
    transverse_idx = _bin_indices(
        transverse,
        transverse_min,
        transverse_max,
        config.transverse_bins,
    )
    vertical_idx = _bin_indices(
        vertical,
        vertical_min,
        vertical_max,
        config.vertical_bins,
    )

    # One occupied (longitudinal, transverse, vertical) voxel counts once.
    flat_voxel = (
        long_idx * config.transverse_bins + transverse_idx
    ) * config.vertical_bins + vertical_idx
    occupied_voxels = np.unique(flat_voxel)

    transverse_vertical_size = config.transverse_bins * config.vertical_bins

    occupied_transverse = (occupied_voxels % transverse_vertical_size) // config.vertical_bins
    occupied_vertical = occupied_voxels % config.vertical_bins

    # Number of distinct longitudinal bins represented at each transverse/Z
    # location. High values mean the surface persists along the scene.
    tv_flat = occupied_transverse * config.vertical_bins + occupied_vertical
    coverage_counts = np.bincount(
        tv_flat,
        minlength=transverse_vertical_size,
    ).reshape(config.transverse_bins, config.vertical_bins)

    coverage = coverage_counts / config.longitudinal_bins
    support = coverage >= config.min_longitudinal_coverage

    # Suppress the very lowest part of the scene during candidate discovery.
    # This is relative to scene height, not a physical-distance threshold.
    low_bins = int(np.floor(config.vertical_bins * config.ignore_lowest_vertical_fraction))
    if low_bins > 0:
        support[:, :low_bins] = False

    labels, component_count = ndimage.label(
        support,
        structure=np.ones((3, 3), dtype=np.int8),
    )

    if component_count == 0:
        raise RuntimeError("no longitudinally persistent geometric component was detected")

    point_component_labels = labels[transverse_idx, vertical_idx]

    best_label: int | None = None
    best_score = -np.inf
    best_stats: tuple[float, float, float, int] | None = None

    for component_label in range(1, component_count + 1):
        component_cells = labels == component_label

        transverse_cells = np.flatnonzero(component_cells.any(axis=1))
        vertical_cells = np.flatnonzero(component_cells.any(axis=0))

        if len(transverse_cells) == 0 or len(vertical_cells) == 0:
            continue

        vertical_extent_fraction = len(vertical_cells) / config.vertical_bins
        if vertical_extent_fraction < config.min_vertical_extent_fraction:
            continue

        point_mask = point_component_labels == component_label
        point_count = int(point_mask.sum())
        if point_count == 0:
            continue

        unique_longitudinal_bins = np.unique(long_idx[point_mask])
        longitudinal_coverage = len(unique_longitudinal_bins) / config.longitudinal_bins

        transverse_extent_fraction = len(transverse_cells) / config.transverse_bins
        point_fraction = point_count / len(points)

        mean_cell_coverage = float(coverage[component_cells].mean())

        # A timber-wall candidate should simultaneously persist along the
        # long axis, occupy meaningful vertical extent, and contain a
        # substantial number of points.
        score = (
            longitudinal_coverage
            * vertical_extent_fraction
            * np.sqrt(point_fraction)
            * mean_cell_coverage
        )

        if score > best_score:
            best_score = float(score)
            best_label = component_label
            best_stats = (
                float(longitudinal_coverage),
                float(vertical_extent_fraction),
                float(transverse_extent_fraction),
                point_count,
            )

    if best_label is None or best_stats is None:
        raise RuntimeError("components were found, but none met the timber-stack criteria")

    mask = point_component_labels == best_label

    (
        longitudinal_coverage,
        vertical_extent_fraction,
        transverse_extent_fraction,
        selected_point_count,
    ) = best_stats

    return TimberStackDetectionResult(
        mask=mask,
        center_xy=center_xy,
        longitudinal_axis=longitudinal_axis,
        transverse_axis=transverse_axis,
        selected_point_count=selected_point_count,
        selected_point_fraction=selected_point_count / len(points),
        longitudinal_coverage=longitudinal_coverage,
        vertical_extent_fraction=vertical_extent_fraction,
        transverse_extent_fraction=transverse_extent_fraction,
        score=best_score,
        component_count=int(component_count),
    )
