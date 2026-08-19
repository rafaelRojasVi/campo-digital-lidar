"""Classical-CV candidate detection for visible timber log ends.

The detector operates on a front-surface RGB raster. It intentionally
produces *candidates*, not authoritative log counts or diameters.

No physical unit is assumed here: radii are initially expressed in pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class LogEndDetectionConfig:
    """Configuration for front-face timber/log-end candidate detection."""

    background_threshold: float = 0.985

    mask_close_iterations: int = 2
    mask_open_iterations: int = 1
    mask_erode_iterations: int = 2
    max_small_hole_pixels: int = 48
    min_mask_component_fraction: float = 0.005

    dog_sigma_inner: float = 1.2
    dog_sigma_outer: float = 4.0
    candidate_percentile: float = 95.0
    min_response_component_pixels: int = 6

    min_radius_px: int = 5
    max_radius_px: int = 12
    min_contrast: float = 0.03
    min_patch_occupancy: float = 0.78

    nms_distance_factor: float = 0.85
    max_candidates: int = 2500


@dataclass(frozen=True)
class LogEndCandidate:
    """One possible visible log end in image coordinates."""

    x_px: float
    y_px: float
    radius_px: float
    score: float
    contrast: float


@dataclass(frozen=True)
class LogEndDetectionResult:
    """Outputs and diagnostics from the candidate detector."""

    candidates: tuple[LogEndCandidate, ...]
    timber_mask: np.ndarray
    grayscale: np.ndarray
    response: np.ndarray
    raw_candidate_count: int


def _as_rgb_float(image: np.ndarray) -> np.ndarray:
    image = np.asarray(image)

    if image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError("image must have shape (H, W, 3) or (H, W, 4)")

    rgb = image[:, :, :3].astype(np.float64)

    if np.issubdtype(image.dtype, np.integer):
        max_value = np.iinfo(image.dtype).max
        rgb /= float(max_value)
    elif rgb.size and rgb.max() > 1.0:
        rgb /= 255.0

    return np.clip(rgb, 0.0, 1.0)


def _to_grayscale(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def build_timber_face_mask(
    image: np.ndarray,
    config: LogEndDetectionConfig | None = None,
) -> np.ndarray:
    """Build a coarse binary mask for non-background timber-face pixels."""

    if config is None:
        config = LogEndDetectionConfig()

    rgb = _as_rgb_float(image)

    # The generated raster uses a white background. A pixel is considered
    # occupied if at least one channel is meaningfully below white.
    occupied = np.any(
        rgb < config.background_threshold,
        axis=2,
    )

    structure = np.ones((3, 3), dtype=bool)

    mask = ndimage.binary_closing(
        occupied,
        structure=structure,
        iterations=config.mask_close_iterations,
    )

    if config.mask_open_iterations > 0:
        mask = ndimage.binary_opening(
            mask,
            structure=structure,
            iterations=config.mask_open_iterations,
        )

    labels, component_count = ndimage.label(mask)

    if component_count == 0:
        return np.zeros(mask.shape, dtype=bool)

    component_sizes = np.bincount(labels.ravel())
    component_sizes[0] = 0

    largest = int(component_sizes.max())

    minimum_size = max(
        64,
        int(largest * config.min_mask_component_fraction),
    )

    keep_labels = np.flatnonzero(component_sizes >= minimum_size)

    mask = np.isin(labels, keep_labels)

    # Fill only genuinely small enclosed holes. Large white regions in the
    # LiDAR raster represent missing/occluded observations and must remain
    # excluded from the timber search mask.
    inverse = ~mask
    hole_labels, hole_count = ndimage.label(
        inverse,
        structure=structure,
    )

    if hole_count > 0:
        hole_sizes = np.bincount(hole_labels.ravel())

        border_labels = np.unique(
            np.concatenate(
                (
                    hole_labels[0, :],
                    hole_labels[-1, :],
                    hole_labels[:, 0],
                    hole_labels[:, -1],
                )
            )
        )

        fillable = np.ones(
            len(hole_sizes),
            dtype=bool,
        )
        fillable[0] = False
        fillable[border_labels] = False
        fillable &= hole_sizes <= config.max_small_hole_pixels

        mask |= fillable[hole_labels]

    if config.mask_erode_iterations > 0:
        mask = ndimage.binary_erosion(
            mask,
            structure=structure,
            iterations=config.mask_erode_iterations,
        )

    return np.asarray(mask, dtype=bool)


def _estimate_radius_and_contrast(
    grayscale: np.ndarray,
    mask: np.ndarray,
    y: int,
    x: int,
    config: LogEndDetectionConfig,
) -> tuple[float, float, float]:
    """Estimate a blob radius using centre-vs-annulus intensity contrast."""

    height, width = grayscale.shape

    best_radius = 0.0
    best_contrast = -np.inf
    best_occupancy = 0.0

    max_radius = config.max_radius_px

    y0 = max(0, y - max_radius - 2)
    y1 = min(height, y + max_radius + 3)
    x0 = max(0, x - max_radius - 2)
    x1 = min(width, x + max_radius + 3)

    patch = grayscale[y0:y1, x0:x1]
    patch_mask = mask[y0:y1, x0:x1]

    yy, xx = np.ogrid[y0:y1, x0:x1]
    distance = np.sqrt((yy - y) ** 2 + (xx - x) ** 2)

    for radius in range(
        config.min_radius_px,
        config.max_radius_px + 1,
    ):
        inner = distance <= max(radius * 0.50, 1.0)

        annulus = (distance >= radius * 0.75) & (distance <= radius * 1.25)

        outer = distance <= radius * 1.25

        if not np.any(inner) or not np.any(annulus):
            continue

        inner_values = patch[inner]
        annulus_values = patch[annulus]

        occupancy = float(patch_mask[outer].mean())

        contrast = float(inner_values.mean() - annulus_values.mean())

        if contrast > best_contrast:
            best_radius = float(radius)
            best_contrast = contrast
            best_occupancy = occupancy

    return (
        best_radius,
        float(best_contrast),
        best_occupancy,
    )


def _non_maximum_suppression(
    candidates: list[LogEndCandidate],
    config: LogEndDetectionConfig,
) -> tuple[LogEndCandidate, ...]:
    """Remove strongly overlapping candidate centres."""

    ordered = sorted(
        candidates,
        key=lambda candidate: candidate.score,
        reverse=True,
    )

    accepted: list[LogEndCandidate] = []

    for candidate in ordered:
        keep = True

        for existing in accepted:
            dx = candidate.x_px - existing.x_px
            dy = candidate.y_px - existing.y_px

            distance = float(np.hypot(dx, dy))

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


def detect_log_end_candidates(
    image: np.ndarray,
    config: LogEndDetectionConfig | None = None,
) -> LogEndDetectionResult:
    """Detect round-ish bright log-end candidates on a front-face raster.

    This is deliberately a candidate generator. It should later be validated
    against manually labelled log ends and, if necessary, replaced or
    complemented by a learned detector.
    """

    if config is None:
        config = LogEndDetectionConfig()

    if config.dog_sigma_inner <= 0:
        raise ValueError("dog_sigma_inner must be positive")

    if config.dog_sigma_outer <= config.dog_sigma_inner:
        raise ValueError("dog_sigma_outer must be greater than dog_sigma_inner")

    if not 0.0 < config.candidate_percentile < 100.0:
        raise ValueError("candidate_percentile must be between 0 and 100")

    rgb = _as_rgb_float(image)
    grayscale = _to_grayscale(rgb)

    # Raw observation support. Pure-white raster pixels represent missing
    # or unobserved LiDAR data and must not become log-end candidates.
    observed_mask = np.any(
        rgb < config.background_threshold,
        axis=2,
    )

    timber_mask = build_timber_face_mask(
        rgb,
        config,
    )

    # The cleaned silhouette tells us where the pile is; observed_mask tells
    # us where the raster actually contains measured/colorized point data.
    search_mask = timber_mask & observed_mask

    if not np.any(search_mask):
        return LogEndDetectionResult(
            candidates=(),
            timber_mask=timber_mask,
            grayscale=grayscale,
            response=np.zeros_like(grayscale),
            raw_candidate_count=0,
        )

    # Avoid artificial high-contrast boundaries against the white raster
    # background by replacing out-of-mask pixels with the timber median.
    filtered_input = grayscale.copy()

    median_gray = float(np.median(grayscale[search_mask]))

    # Neutralize missing pixels before DoG filtering so the boundary of a
    # white raster hole does not look like a circular image feature.
    filtered_input[~search_mask] = median_gray

    small_scale = ndimage.gaussian_filter(
        filtered_input,
        sigma=config.dog_sigma_inner,
    )

    large_scale = ndimage.gaussian_filter(
        filtered_input,
        sigma=config.dog_sigma_outer,
    )

    response = small_scale - large_scale
    response[~search_mask] = 0.0

    threshold = float(
        np.percentile(
            response[search_mask],
            config.candidate_percentile,
        )
    )

    # Use connected positive-response regions rather than individual local
    # maxima. Filled or textured log ends can produce a ring of equivalent
    # DoG maxima around their boundary; collapsing each response region to
    # its weighted centroid gives one stable seed per round-ish object.
    active_threshold = max(threshold, 0.0)

    candidate_regions = search_mask & (response > active_threshold)

    labels, component_count = ndimage.label(
        candidate_regions,
        structure=np.ones((3, 3), dtype=np.int8),
    )

    candidate_seeds: list[tuple[int, int, float]] = []

    for component_label in range(
        1,
        int(component_count) + 1,
    ):
        component = labels == component_label
        component_size = int(component.sum())

        if component_size < config.min_response_component_pixels:
            continue

        ys, xs = np.nonzero(component)

        weights = np.clip(
            response[component] - active_threshold,
            0.0,
            None,
        )

        total_weight = float(weights.sum())

        if total_weight <= 0:
            continue

        x = int(
            np.rint(
                np.average(
                    xs,
                    weights=weights,
                )
            )
        )

        y = int(
            np.rint(
                np.average(
                    ys,
                    weights=weights,
                )
            )
        )

        peak_response = float(response[component].max())

        candidate_seeds.append(
            (
                y,
                x,
                peak_response,
            )
        )

    raw_candidate_count = len(candidate_seeds)

    candidates: list[LogEndCandidate] = []

    for y, x, peak_response in candidate_seeds:
        radius, contrast, occupancy = _estimate_radius_and_contrast(
            grayscale,
            observed_mask,
            int(y),
            int(x),
            config,
        )

        if radius <= 0:
            continue

        if contrast < config.min_contrast:
            continue

        if occupancy < config.min_patch_occupancy:
            continue

        score = float(peak_response + contrast)

        candidates.append(
            LogEndCandidate(
                x_px=float(x),
                y_px=float(y),
                radius_px=radius,
                score=score,
                contrast=contrast,
            )
        )

    accepted = _non_maximum_suppression(
        candidates,
        config,
    )

    return LogEndDetectionResult(
        candidates=accepted,
        timber_mask=timber_mask,
        grayscale=grayscale,
        response=response,
        raw_candidate_count=raw_candidate_count,
    )
