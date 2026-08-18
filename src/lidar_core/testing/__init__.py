"""Deterministic synthetic point-cloud generators with analytically known
volumes, used for tests and for `lidar generate-synthetic`.

All generators accept a `seed` and are fully reproducible.
"""

from __future__ import annotations

import numpy as np


def cube(size: float = 1.0, n_points: int = 2000, seed: int = 0) -> tuple[np.ndarray, float]:
    """Solid-sampled cube (points filling the volume). Analytic volume = size**3."""
    rng = np.random.default_rng(seed)
    pts = rng.uniform(0, size, size=(n_points, 3))
    return pts, size**3


def rectangular_prism(
    dx: float = 2.0, dy: float = 1.0, dz: float = 0.5, n_points: int = 2000, seed: int = 0
) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    pts = rng.uniform([0, 0, 0], [dx, dy, dz], size=(n_points, 3))
    return pts, dx * dy * dz


def cylinder(
    radius: float = 0.5, height: float = 2.0, n_points: int = 4000, seed: int = 0
) -> tuple[np.ndarray, float]:
    """Solid-sampled cylinder, axis along Z. Analytic volume = pi r^2 h."""
    rng = np.random.default_rng(seed)
    r = radius * np.sqrt(rng.uniform(0, 1, n_points))
    theta = rng.uniform(0, 2 * np.pi, n_points)
    x = r * np.cos(theta)
    y = r * np.sin(theta)
    z = rng.uniform(0, height, n_points)
    pts = np.column_stack([x, y, z])
    volume = np.pi * radius**2 * height
    return pts, volume


def sloped_plane(
    width: float = 2.0, length: float = 2.0, slope: float = 0.2, n_points: int = 2000, seed: int = 0
) -> np.ndarray:
    """Points on a tilted planar surface z = slope * x. No enclosed volume
    (surface only) -- returned without an analytic volume."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, width, n_points)
    y = rng.uniform(0, length, n_points)
    z = slope * x
    return np.column_stack([x, y, z])


def noisy_plane(
    width: float = 2.0,
    length: float = 2.0,
    noise_std: float = 0.01,
    n_points: int = 2000,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, width, n_points)
    y = rng.uniform(0, length, n_points)
    z = rng.normal(0, noise_std, n_points)
    return np.column_stack([x, y, z])


def partially_occluded_cube(
    size: float = 1.0,
    n_points: int = 2000,
    occlusion_fraction: float = 0.4,
    seed: int = 0,
) -> tuple[np.ndarray, float]:
    """A cube with one octant's worth of points removed to simulate
    occlusion. Returns points and the TRUE (unoccluded) analytic volume --
    callers must not expect volume estimators to recover it exactly, only
    within a documented degraded tolerance."""
    pts, true_volume = cube(size=size, n_points=n_points, seed=seed)
    keep_mask = ~(
        (pts[:, 0] > size * (1 - occlusion_fraction))
        & (pts[:, 1] > size * (1 - occlusion_fraction))
        & (pts[:, 2] > size * (1 - occlusion_fraction))
    )
    return pts[keep_mask], true_volume
