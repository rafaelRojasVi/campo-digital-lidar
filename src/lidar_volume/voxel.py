"""Voxel-baseline volume estimator.

Voxelizes the ROI at a fixed voxel size and reports occupied_voxel_count *
voxel_volume as a clearly-labeled geometric statistic. This is explicitly
NOT claimed to equal commercial timber volume -- gaps between logs, bark,
and occlusion all bias this estimate, and no correction is applied here.
"""

from __future__ import annotations

import numpy as np

from lidar_core.models import VolumeUnit
from lidar_volume.base import VolumeEstimator


class VoxelVolumeEstimator(VolumeEstimator):
    """kwargs:
    voxel_size: float, edge length of a cubic voxel (source units)
    volume_unit: VolumeUnit, caller-confirmed
    """

    method_name = "voxel_occupancy_baseline"

    def _estimate(
        self, points: np.ndarray, **kwargs: object
    ) -> tuple[float, VolumeUnit, dict, list[str]]:
        voxel_size = float(kwargs.get("voxel_size", 0.05))  # type: ignore[arg-type]
        if voxel_size <= 0:
            raise ValueError("voxel_size must be positive")
        unit = kwargs.get("volume_unit", VolumeUnit.CUBIC_UNITS_UNSPECIFIED)
        if not isinstance(unit, VolumeUnit):
            unit = VolumeUnit.CUBIC_UNITS_UNSPECIFIED

        keys = np.floor(points / voxel_size).astype(np.int64)
        occupied = np.unique(keys, axis=0)
        n_occupied = len(occupied)
        voxel_volume = voxel_size**3
        volume = n_occupied * voxel_volume

        warnings = [
            "Voxel occupancy is a raw geometric statistic, NOT a validated "
            "commercial timber-volume figure. It is sensitive to voxel_size "
            "and does not account for gaps/bark/occlusion."
        ]
        parameters = {
            "voxel_size": voxel_size,
            "occupied_voxel_count": n_occupied,
            "voxel_volume": voxel_volume,
        }
        return volume, unit, parameters, warnings
