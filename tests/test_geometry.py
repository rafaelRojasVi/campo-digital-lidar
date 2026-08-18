from __future__ import annotations

import numpy as np

from lidar_core.geometry import (
    compute_bounding_box,
    convex_hull_volume,
    crop_points,
    oriented_bounding_box,
    ransac_plane_segmentation,
    voxel_downsample,
)
from lidar_core.testing import cube, rectangular_prism, sloped_plane


def test_deterministic_crop():
    points, _ = cube(size=2.0, n_points=1000, seed=3)
    cropped = crop_points(points, 0.5, 0.5, 1.5, 1.5, min_z=0.0, max_z=2.0)
    assert np.all(cropped[:, 0] >= 0.5) and np.all(cropped[:, 0] <= 1.5)
    assert np.all(cropped[:, 1] >= 0.5) and np.all(cropped[:, 1] <= 1.5)
    # re-running is identical (determinism)
    cropped2 = crop_points(points, 0.5, 0.5, 1.5, 1.5, min_z=0.0, max_z=2.0)
    assert np.array_equal(cropped, cropped2)


def test_bounding_box_matches_extent():
    points, _ = cube(size=1.0, n_points=2000, seed=4)
    bbox = compute_bounding_box(points)
    assert bbox.min_x == points[:, 0].min()
    assert bbox.max_x == points[:, 0].max()
    assert bbox.span_x <= 1.0


def test_voxel_downsample_reduces_count_and_is_deterministic():
    points, _ = cube(size=1.0, n_points=5000, seed=5)
    down1 = voxel_downsample(points, voxel_size=0.1)
    down2 = voxel_downsample(points, voxel_size=0.1)
    assert len(down1) < len(points)
    assert np.array_equal(down1, down2)


def test_ransac_plane_recovers_flat_surface():
    points = sloped_plane(width=2.0, length=2.0, slope=0.0, n_points=1000, seed=6)
    plane = ransac_plane_segmentation(points, distance_threshold=1e-6, num_iterations=200, seed=0)
    # near-flat z=0 plane -> normal should be close to +-Z
    assert abs(abs(plane.c) - 1.0) < 1e-3
    assert len(plane.inlier_indices) > 900


def test_convex_hull_volume_close_to_cube():
    points, true_volume = cube(size=1.0, n_points=20000, seed=7)
    hull_volume = convex_hull_volume(points)
    # hull of uniformly sampled cube slightly underestimates due to finite
    # sampling near corners/edges; tolerance is generous but bounded.
    assert hull_volume <= true_volume
    assert hull_volume > true_volume * 0.85


def test_oriented_bounding_box_extents_match_axis_aligned_prism():
    # A cube is a degenerate case for PCA-based OBB: its covariance is
    # isotropic, so the principal axes (and thus the "oriented" box) are
    # essentially arbitrary/noisy -- not a bug, just PCA's known limit for
    # symmetric point sets. Use an elongated prism, where PCA reliably
    # recovers the true axes, to validate OBB tightness instead.
    points, true_volume = rectangular_prism(dx=3.0, dy=1.0, dz=0.5, n_points=8000, seed=8)
    obb = oriented_bounding_box(points)
    assert obb.volume >= true_volume * 0.95
    assert obb.volume <= true_volume * 1.2
