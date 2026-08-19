"""Pure comparison logic for estimated and reference timber volumes.

This module performs no filesystem I/O and makes no unit conversions.
Estimate and reference units must already match exactly.
"""

from __future__ import annotations

import math

from lidar_core.models import (
    ReferenceMeasurement,
    VolumeComparison,
    VolumeResult,
)


def compare_volume_result(
    estimate: VolumeResult,
    reference: ReferenceMeasurement,
) -> VolumeComparison:
    """Compare one geometric volume estimate against one reference value.

    The estimate and reference must use exactly the same VolumeUnit. No unit
    conversion or physical-unit inference is performed.

    Relative metrics are undefined for a zero-valued reference and are
    therefore returned as None in that case.
    """

    if estimate.volume_unit != reference.unit:
        raise ValueError("estimate and reference volume units must match exactly")

    if not math.isfinite(estimate.volume):
        raise ValueError("estimate volume must be finite")

    if not math.isfinite(reference.value):
        raise ValueError("reference value must be finite")

    if estimate.volume < 0:
        raise ValueError("estimate volume must be non-negative")

    if reference.value < 0:
        raise ValueError("reference value must be non-negative")

    signed_error = estimate.volume - reference.value
    absolute_error = abs(signed_error)

    if reference.value == 0:
        relative_error = None
        absolute_relative_error = None
        percent_error = None
        absolute_percent_error = None
    else:
        relative_error = signed_error / reference.value
        absolute_relative_error = absolute_error / reference.value
        percent_error = relative_error * 100.0
        absolute_percent_error = absolute_relative_error * 100.0

    return VolumeComparison(
        estimate_method=estimate.method,
        estimate_value=estimate.volume,
        reference=reference,
        unit=estimate.volume_unit,
        signed_error=signed_error,
        absolute_error=absolute_error,
        relative_error=relative_error,
        absolute_relative_error=absolute_relative_error,
        percent_error=percent_error,
        absolute_percent_error=absolute_percent_error,
    )
