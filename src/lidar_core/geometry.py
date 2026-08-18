"""Geometry operations on point clouds represented as numpy (N,3) float arrays.

Open3D is used when available for performance/robustness; otherwise a
numpy-only fallback implements the same operations. Which backend is active
is exposed via `HAS_OPEN3D` so callers/tests can branch or skip.

Expensive ops (RANSAC, DBSCAN, normals) are never run implicitly -- callers
must invoke them explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import DBSCAN

from lidar_core.models import BoundingBox3D

try:
    import open3d as o3d

    HAS_OPEN3D = True
except ImportError:  # pragma: no cover - exercised only when open3d absent
    o3d = None
    HAS_OPEN3D = False


def compute_bounding_box(points: np.ndarray) -> BoundingBox3D:
    if points.size == 0:
        raise ValueError("cannot compute bounding box of empty point array")
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    return BoundingBox3D(
        min_x=float(mins[0]),
        min_y=float(mins[1]),
        min_z=float(mins[2]),
        max_x=float(maxs[0]),
        max_y=float(maxs[1]),
        max_z=float(maxs[2]),
    )


def crop_points(
    points: np.ndarray,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    min_z: float | None = None,
    max_z: float | None = None,
) -> np.ndarray:
    """Deterministic axis-aligned crop. Bounds are inclusive."""
    mask = (
        (points[:, 0] >= min_x)
        & (points[:, 0] <= max_x)
        & (points[:, 1] >= min_y)
        & (points[:, 1] <= max_y)
    )
    if min_z is not None:
        mask &= points[:, 2] >= min_z
    if max_z is not None:
        mask &= points[:, 2] <= max_z
    return points[mask]


def voxel_downsample(points: np.ndarray, voxel_size: float) -> np.ndarray:
    """Deterministic voxel-grid downsample: one centroid point per
    occupied voxel. Works identically regardless of backend availability
    (numpy implementation used directly for determinism)."""
    if voxel_size <= 0:
        raise ValueError("voxel_size must be positive")
    keys = np.floor(points / voxel_size).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    sums = np.zeros((counts.shape[0], 3), dtype=np.float64)
    np.add.at(sums, inverse, points)
    centroids = sums / counts[:, None]
    return centroids


def statistical_outlier_removal(
    points: np.ndarray, k: int = 16, std_ratio: float = 2.0
) -> np.ndarray:
    """Removes points whose mean distance to k nearest neighbors is beyond
    std_ratio standard deviations from the dataset mean."""
    from sklearn.neighbors import NearestNeighbors

    if len(points) <= k:
        return points
    nn = NearestNeighbors(n_neighbors=k + 1).fit(points)
    dists, _ = nn.kneighbors(points)
    mean_dists = dists[:, 1:].mean(axis=1)
    threshold = mean_dists.mean() + std_ratio * mean_dists.std()
    return points[mean_dists <= threshold]


def radius_outlier_removal(points: np.ndarray, radius: float, min_neighbors: int) -> np.ndarray:
    from sklearn.neighbors import NearestNeighbors

    if len(points) == 0:
        return points
    nn = NearestNeighbors(radius=radius).fit(points)
    neighbor_counts = np.array(
        [len(idx) - 1 for idx in nn.radius_neighbors(points, return_distance=False)]
    )
    return points[neighbor_counts >= min_neighbors]


@dataclass(frozen=True)
class PlaneModel:
    """ax + by + cz + d = 0, normalized so (a,b,c) is a unit normal."""

    a: float
    b: float
    c: float
    d: float
    inlier_indices: np.ndarray


def ransac_plane_segmentation(
    points: np.ndarray,
    distance_threshold: float,
    num_iterations: int = 1000,
    seed: int = 0,
) -> PlaneModel:
    """Minimal RANSAC plane fit, deterministic given `seed`."""
    if len(points) < 3:
        raise ValueError("need at least 3 points for plane fit")
    rng = np.random.default_rng(seed)
    best_inliers: np.ndarray = np.array([], dtype=np.int64)
    best_plane = (0.0, 0.0, 1.0, 0.0)
    n = len(points)
    for _ in range(num_iterations):
        idx = rng.choice(n, size=3, replace=False)
        p0, p1, p2 = points[idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(normal)
        if norm < 1e-12:
            continue
        normal = normal / norm
        d = -normal.dot(p0)
        dists = np.abs(points @ normal + d)
        inliers = np.where(dists <= distance_threshold)[0]
        if len(inliers) > len(best_inliers):
            best_inliers = inliers
            best_plane = (float(normal[0]), float(normal[1]), float(normal[2]), float(d))
    return PlaneModel(*best_plane, inlier_indices=best_inliers)


def dbscan_cluster(points: np.ndarray, eps: float, min_samples: int = 10) -> np.ndarray:
    """Returns cluster label per point; -1 is noise (sklearn convention)."""
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(points)
    return labels


def estimate_normals(points: np.ndarray, k: int = 16) -> np.ndarray:
    """Per-point normal estimate via local PCA over k nearest neighbors.
    Sign is not consistently oriented (no viewpoint info available)."""
    from sklearn.neighbors import NearestNeighbors

    if len(points) <= k:
        k = max(len(points) - 1, 1)
    nn = NearestNeighbors(n_neighbors=k + 1).fit(points)
    _, indices = nn.kneighbors(points)
    normals = np.zeros_like(points)
    for i, neighbor_idx in enumerate(indices):
        neighborhood = points[neighbor_idx]
        centered = neighborhood - neighborhood.mean(axis=0)
        cov = centered.T @ centered
        eigvals, eigvecs = np.linalg.eigh(cov)
        normals[i] = eigvecs[:, 0]  # smallest-eigenvalue direction
    return normals


def convex_hull_volume(points: np.ndarray) -> float:
    """Volume of the 3D convex hull, in source coordinate units cubed."""
    from scipy.spatial import ConvexHull

    if len(points) < 4:
        raise ValueError("need at least 4 non-coplanar points for a 3D convex hull")
    hull = ConvexHull(points)
    return float(hull.volume)


@dataclass(frozen=True)
class OrientedBoundingBox:
    center: np.ndarray
    extents: np.ndarray
    rotation: np.ndarray

    @property
    def volume(self) -> float:
        return float(np.prod(self.extents))


def oriented_bounding_box(points: np.ndarray) -> OrientedBoundingBox:
    """PCA-based oriented bounding box (numpy-only, backend-independent)."""
    if len(points) < 3:
        raise ValueError("need at least 3 points for an oriented bounding box")
    mean = points.mean(axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    rotated = centered @ eigvecs
    mins = rotated.min(axis=0)
    maxs = rotated.max(axis=0)
    extents = maxs - mins
    local_center = (mins + maxs) / 2.0
    center = mean + eigvecs @ local_center
    return OrientedBoundingBox(center=center, extents=extents, rotation=eigvecs)
