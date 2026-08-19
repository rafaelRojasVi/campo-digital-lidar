"""Reproducible local front-view projection and 2D -> 3D backprojection.

The projection reproduces the local-view geometry used for the timber-stack
front-view sweep. It preserves original source point indices so image-space
detections can be mapped back to the original 3D LAS points.

No coordinate unit is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LocalFrontViewConfig:
    """Configuration for one local timber-stack front view."""

    window_index: int
    yaw_degrees: float

    n_windows: int = 8
    window_overlap_factor: float = 1.35

    raster_width: int = 480
    raster_height: int = 260

    longitudinal_quantile_low: float = 0.01
    longitudinal_quantile_high: float = 0.99

    image_quantile_low: float = 0.01
    image_quantile_high: float = 0.99

    use_min_depth: bool = True


@dataclass(frozen=True)
class LocalFrontViewProjection:
    """Projection state required to reproduce and invert a local raster."""

    source_indices: np.ndarray

    pixel_x: np.ndarray
    pixel_y: np.ndarray
    depth: np.ndarray

    visible_source_indices: np.ndarray
    visible_pixel_x: np.ndarray
    visible_pixel_y: np.ndarray

    visible_index_image: np.ndarray

    longitudinal_axis: np.ndarray
    view_axis: np.ndarray
    horizontal_axis: np.ndarray

    xy_center: np.ndarray

    window_start: float
    window_end: float

    horizontal_min: float
    horizontal_max: float
    vertical_min: float
    vertical_max: float

    horizontal_units_per_pixel: float
    vertical_units_per_pixel: float

    raster_width: int
    raster_height: int


def _validate_config(config: LocalFrontViewConfig) -> None:
    if config.n_windows < 1:
        raise ValueError("n_windows must be >= 1")

    if not 0 <= config.window_index < config.n_windows:
        raise ValueError("window_index must satisfy 0 <= window_index < n_windows")

    if config.window_overlap_factor <= 0:
        raise ValueError("window_overlap_factor must be positive")

    if config.raster_width < 2:
        raise ValueError("raster_width must be >= 2")

    if config.raster_height < 2:
        raise ValueError("raster_height must be >= 2")

    if not (0.0 <= config.longitudinal_quantile_low < config.longitudinal_quantile_high <= 1.0):
        raise ValueError("invalid longitudinal quantile interval")

    if not (0.0 <= config.image_quantile_low < config.image_quantile_high <= 1.0):
        raise ValueError("invalid image quantile interval")


def _principal_longitudinal_axis(
    xy_centered: np.ndarray,
) -> np.ndarray:
    cov = np.cov(xy_centered.T)

    eigvals, eigvecs = np.linalg.eigh(cov)

    axis = eigvecs[
        :,
        np.argmax(eigvals),
    ].astype(np.float64)

    if axis[0] < 0:
        axis = -axis

    axis /= np.linalg.norm(axis)

    return axis


def build_local_front_view_projection(
    xyz: np.ndarray,
    config: LocalFrontViewConfig,
) -> LocalFrontViewProjection:
    """Build one deterministic local front-view projection.

    `xyz` must contain the same ordered points that will later be used for
    backprojection. Returned source indices refer directly to rows of `xyz`.
    """

    _validate_config(config)

    xyz = np.asarray(
        xyz,
        dtype=np.float64,
    )

    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError("xyz must have shape (N, 3)")

    if len(xyz) < 3:
        raise ValueError("xyz must contain at least 3 points")

    xy = xyz[:, :2]

    xy_center = np.median(
        xy,
        axis=0,
    )

    xy_centered = xy - xy_center

    longitudinal_axis = _principal_longitudinal_axis(xy_centered)

    base_view_axis = np.array(
        [
            -longitudinal_axis[1],
            longitudinal_axis[0],
        ],
        dtype=np.float64,
    )

    longitudinal = xy_centered @ longitudinal_axis

    longitudinal_min, longitudinal_max = np.quantile(
        longitudinal,
        [
            config.longitudinal_quantile_low,
            config.longitudinal_quantile_high,
        ],
    )

    longitudinal_span = longitudinal_max - longitudinal_min

    if longitudinal_span <= 0:
        raise ValueError("longitudinal span must be positive")

    step = longitudinal_span / config.n_windows

    window_center = longitudinal_min + (config.window_index + 0.5) * step

    window_width = step * config.window_overlap_factor

    window_start = window_center - window_width / 2.0

    window_end = window_center + window_width / 2.0

    window_mask = (longitudinal >= window_start) & (longitudinal <= window_end)

    window_source_indices = np.flatnonzero(window_mask)

    if len(window_source_indices) == 0:
        raise ValueError("selected window contains no points")

    local_xyz = xyz[window_source_indices]

    local_xy = local_xyz[:, :2] - xy_center

    theta = np.deg2rad(config.yaw_degrees)

    rotation = np.array(
        [
            [
                np.cos(theta),
                -np.sin(theta),
            ],
            [
                np.sin(theta),
                np.cos(theta),
            ],
        ],
        dtype=np.float64,
    )

    view_axis = rotation @ base_view_axis

    view_axis /= np.linalg.norm(view_axis)

    horizontal_axis = np.array(
        [
            view_axis[1],
            -view_axis[0],
        ],
        dtype=np.float64,
    )

    horizontal = local_xy @ horizontal_axis

    depth = local_xy @ view_axis

    vertical = local_xyz[:, 2]

    horizontal_min, horizontal_max = np.quantile(
        horizontal,
        [
            config.image_quantile_low,
            config.image_quantile_high,
        ],
    )

    vertical_min, vertical_max = np.quantile(
        vertical,
        [
            config.image_quantile_low,
            config.image_quantile_high,
        ],
    )

    horizontal_span = horizontal_max - horizontal_min

    vertical_span = vertical_max - vertical_min

    if horizontal_span <= 0:
        raise ValueError("horizontal image span must be positive")

    if vertical_span <= 0:
        raise ValueError("vertical image span must be positive")

    valid = (
        (horizontal >= horizontal_min)
        & (horizontal <= horizontal_max)
        & (vertical >= vertical_min)
        & (vertical <= vertical_max)
    )

    source_indices = window_source_indices[valid]

    horizontal = horizontal[valid]
    vertical = vertical[valid]
    depth = depth[valid]

    pixel_x = np.floor(
        (horizontal - horizontal_min) / horizontal_span * (config.raster_width - 1)
    ).astype(np.int64)

    pixel_y = np.floor(
        (vertical - vertical_min) / vertical_span * (config.raster_height - 1)
    ).astype(np.int64)

    pixel_y = config.raster_height - 1 - pixel_y

    pixel_id = pixel_y * config.raster_width + pixel_x

    depth_key = depth if config.use_min_depth else -depth

    order = np.lexsort(
        (
            depth_key,
            pixel_id,
        )
    )

    sorted_pixel = pixel_id[order]

    first = np.empty(
        len(order),
        dtype=bool,
    )

    first[0] = True
    first[1:] = sorted_pixel[1:] != sorted_pixel[:-1]

    chosen = order[first]

    visible_source_indices = source_indices[chosen]

    visible_pixel_x = pixel_x[chosen]

    visible_pixel_y = pixel_y[chosen]

    visible_index_image = np.full(
        (
            config.raster_height,
            config.raster_width,
        ),
        -1,
        dtype=np.int64,
    )

    visible_index_image[
        visible_pixel_y,
        visible_pixel_x,
    ] = visible_source_indices

    return LocalFrontViewProjection(
        source_indices=source_indices,
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        depth=depth,
        visible_source_indices=(visible_source_indices),
        visible_pixel_x=(visible_pixel_x),
        visible_pixel_y=(visible_pixel_y),
        visible_index_image=(visible_index_image),
        longitudinal_axis=(longitudinal_axis),
        view_axis=view_axis,
        horizontal_axis=(horizontal_axis),
        xy_center=xy_center,
        window_start=float(window_start),
        window_end=float(window_end),
        horizontal_min=float(horizontal_min),
        horizontal_max=float(horizontal_max),
        vertical_min=float(vertical_min),
        vertical_max=float(vertical_max),
        horizontal_units_per_pixel=(float(horizontal_span / (config.raster_width - 1))),
        vertical_units_per_pixel=(float(vertical_span / (config.raster_height - 1))),
        raster_width=(config.raster_width),
        raster_height=(config.raster_height),
    )


def backproject_visible_pixel_disk(
    projection: LocalFrontViewProjection,
    x_px: float,
    y_px: float,
    radius_px: float,
) -> np.ndarray:
    """Return original source indices visible inside an image-space disk."""

    if radius_px <= 0:
        raise ValueError("radius_px must be positive")

    width = projection.raster_width
    height = projection.raster_height

    x0 = max(
        0,
        int(np.floor(x_px - radius_px)),
    )

    x1 = min(
        width,
        int(np.ceil(x_px + radius_px)) + 1,
    )

    y0 = max(
        0,
        int(np.floor(y_px - radius_px)),
    )

    y1 = min(
        height,
        int(np.ceil(y_px + radius_px)) + 1,
    )

    if x0 >= x1 or y0 >= y1:
        return np.empty(
            0,
            dtype=np.int64,
        )

    yy, xx = np.ogrid[
        y0:y1,
        x0:x1,
    ]

    disk = (xx - x_px) ** 2 + (yy - y_px) ** 2 <= radius_px**2

    indices = projection.visible_index_image[
        y0:y1,
        x0:x1,
    ][disk]

    indices = indices[indices >= 0]

    return np.unique(indices)


def render_visible_rgb(
    rgb: np.ndarray,
    projection: LocalFrontViewProjection,
) -> np.ndarray:
    """Render the exact visible-point raster for verification."""

    rgb = np.asarray(
        rgb,
        dtype=np.float64,
    )

    if rgb.ndim != 2 or rgb.shape[1] != 3:
        raise ValueError("rgb must have shape (N, 3)")

    if len(rgb) == 0 or projection.visible_source_indices.max() >= len(rgb):
        raise ValueError("rgb does not correspond to projection source points")

    image = np.ones(
        (
            projection.raster_height,
            projection.raster_width,
            3,
        ),
        dtype=np.float64,
    )

    image[
        projection.visible_pixel_y,
        projection.visible_pixel_x,
    ] = rgb[projection.visible_source_indices]

    return image
