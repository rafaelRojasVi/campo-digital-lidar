"""Interface-only stub estimators.

Grid2.5D (rasterize to a height-field grid and integrate cell volumes) and
mesh-based (reconstruct a surface mesh, e.g. Poisson/alpha-shape, and take
its enclosed volume) estimators are architecturally scaffolded but not
implemented -- doing so correctly requires ROI/meshing decisions that
should be validated against real Campo Digital data first.
"""

from __future__ import annotations

import numpy as np

from lidar_core.models import VolumeUnit
from lidar_volume.base import VolumeEstimator


class Grid25DVolumeEstimator(VolumeEstimator):
    """Stub: would rasterize the ROI to a 2.5D height grid (DSM-like) and
    integrate cell_area * height per cell."""

    method_name = "grid_2_5d"

    def _estimate(
        self, points: np.ndarray, **kwargs: object
    ) -> tuple[float, VolumeUnit, dict, list[str]]:
        raise NotImplementedError(
            "Grid25DVolumeEstimator is not yet implemented. It requires a "
            "validated rasterization/interpolation strategy (cell size, "
            "fill-gap policy) that has not been agreed for this PoC."
        )


class MeshVolumeEstimator(VolumeEstimator):
    """Stub: would reconstruct a watertight surface mesh (e.g. Poisson or
    alpha-shape reconstruction) and compute its enclosed volume."""

    method_name = "mesh_reconstruction"

    def _estimate(
        self, points: np.ndarray, **kwargs: object
    ) -> tuple[float, VolumeUnit, dict, list[str]]:
        raise NotImplementedError(
            "MeshVolumeEstimator is not yet implemented. It requires a "
            "chosen mesh-reconstruction algorithm and watertightness "
            "validation strategy that has not been agreed for this PoC."
        )
