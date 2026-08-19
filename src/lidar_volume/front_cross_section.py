"""Front-wall cross-sectional measurement for timber stacks.

This module estimates the observable longitudinal/vertical cross-sectional
area of a timber-stack face from 3D points.

The result is expressed only in source-coordinate units. No CRS or physical
unit is inferred.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FrontCrossSectionConfig:
    """Configuration for robust front-wall cross-section estimation."""

    n_bins: int = 160

    longitudinal_quantile_low: float = 0.01
    longitudinal_quantile_high: float = 0.99

    vertical_quantile_low: float = 0.02
    vertical_quantile_high: float = 0.98

    min_points_per_bin: int = 250


@dataclass(frozen=True)
class FrontCrossSectionEstimate:
    """Observable cross-sectional geometry in source-coordinate units."""

    center_xy: np.ndarray
    longitudinal_axis: np.ndarray

    longitudinal_min: float
    longitudinal_max: float
    longitudinal_span: float

    bin_edges: np.ndarray
    bin_centres: np.ndarray
    point_counts: np.ndarray

    base_raw: np.ndarray
    top_raw: np.ndarray

    base: np.ndarray
    top: np.ndarray
    height: np.ndarray

    valid_bin_fraction: float

    rectangle_area: float
    trapezoid_area: float


def _validate_config(
    config: FrontCrossSectionConfig,
) -> None:
    if config.n_bins < 2:
        raise ValueError("n_bins must be >= 2")

    if config.min_points_per_bin < 1:
        raise ValueError("min_points_per_bin must be >= 1")

    if not (0.0 <= config.longitudinal_quantile_low < config.longitudinal_quantile_high <= 1.0):
        raise ValueError("invalid longitudinal quantile interval")

    if not (0.0 <= config.vertical_quantile_low < config.vertical_quantile_high <= 1.0):
        raise ValueError("invalid vertical quantile interval")


def _principal_longitudinal_axis(
    xy_centered: np.ndarray,
) -> np.ndarray:
    covariance = np.cov(xy_centered.T)

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)

    axis = eigenvectors[
        :,
        np.argmax(eigenvalues),
    ].astype(np.float64)

    if axis[0] < 0:
        axis = -axis

    axis /= np.linalg.norm(axis)

    return axis


def estimate_front_cross_section(
    xyz: np.ndarray,
    config: FrontCrossSectionConfig | None = None,
) -> FrontCrossSectionEstimate:
    """Estimate the observable front-wall cross-sectional area."""

    if config is None:
        config = FrontCrossSectionConfig()

    _validate_config(config)

    xyz = np.asarray(
        xyz,
        dtype=np.float64,
    )

    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError("xyz must have shape (N, 3)")

    if len(xyz) < 3:
        raise ValueError("xyz must contain at least 3 points")

    if not np.isfinite(xyz).all():
        raise ValueError("xyz must contain only finite values")

    center_xy = np.median(
        xyz[:, :2],
        axis=0,
    )

    xy_centered = xyz[:, :2] - center_xy

    longitudinal_axis = _principal_longitudinal_axis(xy_centered)

    longitudinal = xy_centered @ longitudinal_axis

    z = xyz[:, 2]

    longitudinal_min, longitudinal_max = np.quantile(
        longitudinal,
        [
            config.longitudinal_quantile_low,
            config.longitudinal_quantile_high,
        ],
    )

    longitudinal_span = float(longitudinal_max - longitudinal_min)

    if longitudinal_span <= 0:
        raise ValueError("longitudinal span must be positive")

    bin_edges = np.linspace(
        longitudinal_min,
        longitudinal_max,
        config.n_bins + 1,
    )

    bin_centres = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    point_counts = np.zeros(
        config.n_bins,
        dtype=np.int64,
    )

    base_raw = np.full(
        config.n_bins,
        np.nan,
        dtype=np.float64,
    )

    top_raw = np.full(
        config.n_bins,
        np.nan,
        dtype=np.float64,
    )

    for index in range(config.n_bins):
        if index == config.n_bins - 1:
            mask = (longitudinal >= bin_edges[index]) & (longitudinal <= bin_edges[index + 1])
        else:
            mask = (longitudinal >= bin_edges[index]) & (longitudinal < bin_edges[index + 1])

        values = z[mask]

        point_counts[index] = len(values)

        if len(values) < config.min_points_per_bin:
            continue

        base_z, top_z = np.quantile(
            values,
            [
                config.vertical_quantile_low,
                config.vertical_quantile_high,
            ],
        )

        base_raw[index] = base_z
        top_raw[index] = top_z

    valid = np.isfinite(base_raw) & np.isfinite(top_raw)

    if valid.sum() < 2:
        raise ValueError("fewer than two valid longitudinal bins")

    base = np.interp(
        bin_centres,
        bin_centres[valid],
        base_raw[valid],
    )

    top = np.interp(
        bin_centres,
        bin_centres[valid],
        top_raw[valid],
    )

    height = np.maximum(
        top - base,
        0.0,
    )

    bin_width = float(bin_edges[1] - bin_edges[0])

    rectangle_area = float(np.sum(height * bin_width))

    trapezoid_area = float(
        np.trapezoid(
            height,
            bin_centres,
        )
    )

    return FrontCrossSectionEstimate(
        center_xy=center_xy,
        longitudinal_axis=longitudinal_axis,
        longitudinal_min=float(longitudinal_min),
        longitudinal_max=float(longitudinal_max),
        longitudinal_span=longitudinal_span,
        bin_edges=bin_edges,
        bin_centres=bin_centres,
        point_counts=point_counts,
        base_raw=base_raw,
        top_raw=top_raw,
        base=base,
        top=top,
        height=height,
        valid_bin_fraction=float(valid.mean()),
        rectangle_area=rectangle_area,
        trapezoid_area=trapezoid_area,
    )


def extruded_volume(
    cross_section_area: float,
    depth: float,
) -> float:
    """Return geometric extrusion volume A × depth in source-units³."""

    if cross_section_area < 0:
        raise ValueError("cross_section_area must be non-negative")

    if depth < 0:
        raise ValueError("depth must be non-negative")

    return float(cross_section_area * depth)
