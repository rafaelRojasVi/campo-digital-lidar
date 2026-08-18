"""Cross-section (sectional-area x integration) volume estimator.

Divides the oriented ROI into regular slabs along a longitudinal axis,
estimates each slab's cross-sectional area (2D convex hull of the
projected points in that slab), and integrates area * thickness along the
axis (composite trapezoidal-like summation). This is a standard forestry
cubicacion technique (analogous to Smalian/Huber sectional methods) applied
generically -- it does NOT encode any Campo Digital-specific commercial
rule.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull, QhullError

from lidar_core.models import SectionDefinition, VolumeUnit
from lidar_volume.base import VolumeEstimator


def _section_area(points_2d: np.ndarray) -> float:
    """2D convex-hull area of a slab's points projected onto the plane
    perpendicular to the longitudinal axis. Returns 0 if too few/degenerate
    points to form a hull."""
    if len(points_2d) < 3:
        return 0.0
    try:
        hull = ConvexHull(points_2d)
    except QhullError:
        return 0.0
    return float(hull.volume)  # for 2D input, ConvexHull.volume is the area


def compute_sections(points: np.ndarray, axis: int, n_sections: int) -> list[SectionDefinition]:
    """Splits points into n_sections equal-thickness slabs along `axis`
    (0=x, 1=y, 2=z) and computes each slab's cross-sectional area."""
    axis_values = points[:, axis]
    lo, hi = axis_values.min(), axis_values.max()
    if hi <= lo:
        raise ValueError("degenerate extent along chosen axis; cannot section")
    edges = np.linspace(lo, hi, n_sections + 1)
    other_axes = [a for a in (0, 1, 2) if a != axis]
    sections: list[SectionDefinition] = []
    for i in range(n_sections):
        lo_i, hi_i = edges[i], edges[i + 1]
        mask = (axis_values >= lo_i) & (axis_values <= hi_i)
        slab_points = points[mask]
        area = _section_area(slab_points[:, other_axes]) if len(slab_points) else 0.0
        sections.append(
            SectionDefinition(
                index=i,
                station=float((lo_i + hi_i) / 2),
                thickness=float(hi_i - lo_i),
                area=area,
                point_count=int(len(slab_points)),
            )
        )
    return sections


class CrossSectionVolumeEstimator(VolumeEstimator):
    """Integrates cross-sectional area along a longitudinal axis.

    kwargs:
        axis: int, 0/1/2 for x/y/z longitudinal direction (default 0)
        n_sections: int, number of slabs (default 20)
        volume_unit: VolumeUnit -- caller must confirm this is justified by
            the source CRS/scale; defaults to CUBIC_UNITS_UNSPECIFIED.
    """

    method_name = "cross_section_integration"

    def _estimate(
        self, points: np.ndarray, **kwargs: object
    ) -> tuple[float, VolumeUnit, dict, list[str]]:
        axis = int(kwargs.get("axis", 0))  # type: ignore[call-overload]
        n_sections = int(kwargs.get("n_sections", 20))  # type: ignore[call-overload]
        unit = kwargs.get("volume_unit", VolumeUnit.CUBIC_UNITS_UNSPECIFIED)
        if not isinstance(unit, VolumeUnit):
            unit = VolumeUnit.CUBIC_UNITS_UNSPECIFIED

        warnings: list[str] = []
        sections = compute_sections(points, axis=axis, n_sections=n_sections)
        empty_sections = sum(1 for s in sections if s.point_count == 0)
        if empty_sections:
            warnings.append(f"{empty_sections}/{n_sections} sections had zero points.")

        volume = sum((s.area or 0.0) * s.thickness for s in sections)
        parameters = {
            "axis": axis,
            "n_sections": n_sections,
            "sections": [s.model_dump() for s in sections],
        }
        return volume, unit, parameters, warnings
