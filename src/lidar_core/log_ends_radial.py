"""Radial-symmetry candidate detection for visible timber log ends.

This detector complements the existing DoG detector. It uses image-gradient
directions to vote for possible centres of round-ish log ends, so it is less
dependent on whether a cut face is brighter or darker than its surroundings.

Outputs are candidate centres/radii in raster pixels only. They are not yet
physical timber diameters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class RadialLogEndDetectionConfig:
    """Configuration for radial-symmetry log-end candidate detection."""

    background_threshold: float = 0.985

    gradient_sigma: float = 1.0
    gradient_percentile: float = 75.0
    max_gradient_points: int = 60_000

    min_radius_px: int = 5
    max_radius_px: int = 12
    radius_step_px: int = 1

    vote_sigma: float = 1.0
    response_percentile: float = 98.5
    local_max_size: int = 7

    min_local_observed_fraction: float = 0.35
    nms_distance_factor: float = 0.75

    max_candidates: int = 400


@dataclass(frozen=True)
class RadialLogEndCandidate:
    """One radial-symmetry log-end candidate."""

    x_px: float
    y_px: float
    radius_px: float
    score: float
    observed_fraction: float


@dataclass(frozen=True)
class RadialLogEndDetectionResult:
    """Radial-symmetry detector result and diagnostics."""

    candidates: tuple[RadialLogEndCandidate, ...]
    response: np.ndarray
    gradient_magnitude: np.ndarray
    observed_mask: np.ndarray
    support_mask: np.ndarray
    raw_candidate_count: int


def _as_rgb_float(image: np.ndarray) -> np.ndarray:
    image = np.asarray(image)

    if image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError("image must have shape (H, W, 3) or (H, W, 4)")

    rgb = image[:, :, :3].astype(np.float64)

    if np.issubdtype(image.dtype, np.integer):
        rgb /= float(np.iinfo(image.dtype).max)
    elif rgb.size and rgb.max() > 1.0:
        rgb /= 255.0

    return np.clip(rgb, 0.0, 1.0)


def _to_grayscale(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def _disk_observed_fraction(
    observed_mask: np.ndarray,
    x: int,
    y: int,
    radius: int,
) -> float:
    height, width = observed_mask.shape

    y0 = max(0, y - radius)
    y1 = min(height, y + radius + 1)
    x0 = max(0, x - radius)
    x1 = min(width, x + radius + 1)

    yy, xx = np.ogrid[y0:y1, x0:x1]

    disk = (xx - x) ** 2 + (yy - y) ** 2 <= radius**2

    if not np.any(disk):
        return 0.0

    return float(observed_mask[y0:y1, x0:x1][disk].mean())


def _non_maximum_suppression(
    candidates: list[RadialLogEndCandidate],
    config: RadialLogEndDetectionConfig,
) -> tuple[RadialLogEndCandidate, ...]:
    ordered = sorted(
        candidates,
        key=lambda candidate: candidate.score,
        reverse=True,
    )

    accepted: list[RadialLogEndCandidate] = []

    for candidate in ordered:
        keep = True

        for existing in accepted:
            distance = float(
                np.hypot(
                    candidate.x_px - existing.x_px,
                    candidate.y_px - existing.y_px,
                )
            )

            minimum_distance = config.nms_distance_factor * (
                candidate.radius_px + existing.radius_px
            )

            if distance < minimum_distance:
                keep = False
                break

        if keep:
            accepted.append(candidate)

        if len(accepted) >= config.max_candidates:
            break

    return tuple(accepted)


def detect_radial_log_end_candidates(
    image: np.ndarray,
    config: RadialLogEndDetectionConfig | None = None,
) -> RadialLogEndDetectionResult:
    """Detect round-ish centres using gradient-direction radial voting."""

    if config is None:
        config = RadialLogEndDetectionConfig()

    if config.gradient_sigma <= 0:
        raise ValueError("gradient_sigma must be positive")

    if config.min_radius_px < 1:
        raise ValueError("min_radius_px must be >= 1")

    if config.max_radius_px < config.min_radius_px:
        raise ValueError("max_radius_px must be >= min_radius_px")

    if config.radius_step_px < 1:
        raise ValueError("radius_step_px must be >= 1")

    rgb = _as_rgb_float(image)
    grayscale = _to_grayscale(rgb)

    observed_mask = np.any(
        rgb < config.background_threshold,
        axis=2,
    )

    if not np.any(observed_mask):
        zeros = np.zeros(
            grayscale.shape,
            dtype=np.float64,
        )

        return RadialLogEndDetectionResult(
            candidates=(),
            response=zeros,
            gradient_magnitude=zeros,
            observed_mask=observed_mask,
            support_mask=observed_mask.copy(),
            raw_candidate_count=0,
        )

    observed_float = observed_mask.astype(np.float64)

    # Local observed-data density prevents the exterior white background
    # from becoming a valid centre while allowing small internal LiDAR gaps.
    observed_density = ndimage.uniform_filter(
        observed_float,
        size=9,
        mode="nearest",
    )

    support_mask = observed_density >= config.min_local_observed_fraction

    # Normalized convolution smooths real image data without turning white
    # missing-data holes into artificial high-gradient boundaries.
    numerator = ndimage.gaussian_filter(
        grayscale * observed_float,
        sigma=config.gradient_sigma,
    )

    denominator = ndimage.gaussian_filter(
        observed_float,
        sigma=config.gradient_sigma,
    )

    smoothed = numerator / np.maximum(
        denominator,
        1e-8,
    )

    gradient_y = ndimage.sobel(
        smoothed,
        axis=0,
        mode="nearest",
    )

    gradient_x = ndimage.sobel(
        smoothed,
        axis=1,
        mode="nearest",
    )

    gradient_magnitude = np.hypot(
        gradient_x,
        gradient_y,
    )

    gradient_domain = support_mask & observed_mask

    domain_values = gradient_magnitude[gradient_domain]

    if len(domain_values) == 0:
        zeros = np.zeros_like(grayscale)

        return RadialLogEndDetectionResult(
            candidates=(),
            response=zeros,
            gradient_magnitude=gradient_magnitude,
            observed_mask=observed_mask,
            support_mask=support_mask,
            raw_candidate_count=0,
        )

    gradient_threshold = float(
        np.percentile(
            domain_values,
            config.gradient_percentile,
        )
    )

    edge_mask = gradient_domain & (gradient_magnitude >= gradient_threshold)

    edge_y, edge_x = np.nonzero(edge_mask)

    weights = gradient_magnitude[
        edge_y,
        edge_x,
    ]

    if len(weights) > config.max_gradient_points:
        strongest = np.argpartition(
            weights,
            -config.max_gradient_points,
        )[-config.max_gradient_points :]

        edge_y = edge_y[strongest]
        edge_x = edge_x[strongest]
        weights = weights[strongest]

    safe_weights = np.maximum(
        weights,
        1e-12,
    )

    unit_x = gradient_x[edge_y, edge_x] / safe_weights

    unit_y = gradient_y[edge_y, edge_x] / safe_weights

    height, width = grayscale.shape

    best_response = np.zeros(
        (height, width),
        dtype=np.float64,
    )

    best_radius = np.zeros(
        (height, width),
        dtype=np.int16,
    )

    for radius in range(
        config.min_radius_px,
        config.max_radius_px + 1,
        config.radius_step_px,
    ):
        accumulator = np.zeros(
            (height, width),
            dtype=np.float64,
        )

        # Vote in both gradient directions. This makes the detector
        # insensitive to whether a circular feature is light-on-dark or
        # dark-on-light.
        for sign in (-1, 1):
            target_x = np.rint(edge_x + sign * unit_x * radius).astype(np.int64)

            target_y = np.rint(edge_y + sign * unit_y * radius).astype(np.int64)

            valid = (target_x >= 0) & (target_x < width) & (target_y >= 0) & (target_y < height)

            np.add.at(
                accumulator,
                (
                    target_y[valid],
                    target_x[valid],
                ),
                weights[valid],
            )

        accumulator = ndimage.gaussian_filter(
            accumulator,
            sigma=config.vote_sigma,
        )

        # Larger circumferences naturally contribute more edge pixels.
        # Radius normalization makes scores more comparable across scales.
        accumulator /= float(radius)

        better = accumulator > best_response

        best_response[better] = accumulator[better]

        best_radius[better] = radius

    best_response[~support_mask] = 0.0

    response_values = best_response[support_mask]

    threshold = float(
        np.percentile(
            response_values,
            config.response_percentile,
        )
    )

    local_maxima = best_response == ndimage.maximum_filter(
        best_response,
        size=config.local_max_size,
        mode="nearest",
    )

    candidate_y, candidate_x = np.nonzero(
        local_maxima & support_mask & (best_response >= threshold) & (best_radius > 0)
    )

    raw_candidate_count = len(candidate_x)

    candidates: list[RadialLogEndCandidate] = []

    for y, x in zip(
        candidate_y,
        candidate_x,
        strict=True,
    ):
        radius = int(best_radius[y, x])

        observed_fraction = _disk_observed_fraction(
            observed_mask,
            int(x),
            int(y),
            radius,
        )

        if observed_fraction < config.min_local_observed_fraction:
            continue

        candidates.append(
            RadialLogEndCandidate(
                x_px=float(x),
                y_px=float(y),
                radius_px=float(radius),
                score=float(best_response[y, x]),
                observed_fraction=(observed_fraction),
            )
        )

    accepted = _non_maximum_suppression(
        candidates,
        config,
    )

    return RadialLogEndDetectionResult(
        candidates=accepted,
        response=best_response,
        gradient_magnitude=gradient_magnitude,
        observed_mask=observed_mask,
        support_mask=support_mask,
        raw_candidate_count=raw_candidate_count,
    )
