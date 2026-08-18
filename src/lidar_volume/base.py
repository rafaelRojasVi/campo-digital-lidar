"""Common estimator interface for volume algorithms."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np

from lidar_core.geometry import compute_bounding_box
from lidar_core.models import VolumeResult, VolumeUnit


class VolumeEstimator(ABC):
    """Base class for all volume estimators.

    Subclasses implement `_estimate`, and `estimate` wraps it with timing,
    bounds computation, and provenance bookkeeping.
    """

    method_name: str = "unset"

    @abstractmethod
    def _estimate(
        self, points: np.ndarray, **kwargs: object
    ) -> tuple[float, VolumeUnit, dict, list[str]]:
        """Returns (volume, unit, parameters, warnings)."""
        raise NotImplementedError

    def estimate(self, points: np.ndarray, **kwargs: object) -> VolumeResult:
        if len(points) == 0:
            raise ValueError("cannot estimate volume of an empty point set")
        bounds = compute_bounding_box(points)
        start = time.perf_counter()
        volume, unit, parameters, warnings = self._estimate(points, **kwargs)
        elapsed = time.perf_counter() - start
        return VolumeResult(
            method=self.method_name,
            volume=volume,
            volume_unit=unit,
            point_count_input=len(points),
            point_count_used=len(points),
            parameters=parameters,
            bounds=bounds,
            warnings=warnings,
            runtime_seconds=elapsed,
            provenance={"estimator_class": type(self).__name__},
        )
