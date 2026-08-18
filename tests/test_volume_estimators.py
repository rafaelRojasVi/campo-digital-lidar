from __future__ import annotations

import pytest

from lidar_core.models import VolumeUnit
from lidar_core.testing import cylinder, partially_occluded_cube, rectangular_prism
from lidar_volume.cross_section import CrossSectionVolumeEstimator
from lidar_volume.stubs import Grid25DVolumeEstimator, MeshVolumeEstimator
from lidar_volume.voxel import VoxelVolumeEstimator


def test_cross_section_accuracy_vs_analytic_prism():
    points, true_volume = rectangular_prism(dx=2.0, dy=1.0, dz=0.5, n_points=20000, seed=10)
    estimator = CrossSectionVolumeEstimator()
    result = estimator.estimate(
        points, axis=0, n_sections=40, volume_unit=VolumeUnit.CUBIC_UNITS_UNSPECIFIED
    )
    # convex-hull-per-slab underestimates a rectangular cross-section
    # somewhat due to finite point sampling; tolerance reflects that, not
    # a bug being papered over.
    relative_error = abs(result.volume - true_volume) / true_volume
    assert relative_error < 0.1
    assert result.point_count_input == 20000
    assert result.volume_unit == VolumeUnit.CUBIC_UNITS_UNSPECIFIED


def test_cross_section_accuracy_vs_analytic_cylinder():
    points, true_volume = cylinder(radius=0.5, height=2.0, n_points=40000, seed=11)
    estimator = CrossSectionVolumeEstimator()
    result = estimator.estimate(points, axis=2, n_sections=30)
    relative_error = abs(result.volume - true_volume) / true_volume
    assert relative_error < 0.1


def test_cross_section_partial_occlusion_degrades_but_bounded():
    points, true_volume = partially_occluded_cube(
        size=1.0, n_points=20000, occlusion_fraction=0.4, seed=12
    )
    estimator = CrossSectionVolumeEstimator()
    result = estimator.estimate(points, axis=0, n_sections=20)
    # occlusion should reduce the estimate below the true unoccluded volume
    assert result.volume < true_volume
    assert result.volume > 0


def test_voxel_size_sensitivity():
    points, _ = rectangular_prism(dx=1.0, dy=1.0, dz=1.0, n_points=20000, seed=13)
    estimator = VoxelVolumeEstimator()
    coarse = estimator.estimate(points, voxel_size=0.2)
    fine = estimator.estimate(points, voxel_size=0.05)
    # finer voxels should track the true occupied region more tightly;
    # different voxel sizes must produce different (not necessarily
    # monotonic in one direction, but distinct) volumes -- sensitivity.
    assert coarse.volume != fine.volume
    assert "raw geometric statistic" in coarse.warnings[0]


def test_volume_unit_never_defaults_to_m3():
    points, _ = rectangular_prism(n_points=1000, seed=14)
    result = VoxelVolumeEstimator().estimate(points, voxel_size=0.1)
    assert result.volume_unit == VolumeUnit.CUBIC_UNITS_UNSPECIFIED


def test_grid25d_and_mesh_are_explicit_stubs():
    points, _ = rectangular_prism(n_points=100, seed=15)
    with pytest.raises(NotImplementedError):
        Grid25DVolumeEstimator().estimate(points)
    with pytest.raises(NotImplementedError):
        MeshVolumeEstimator().estimate(points)
