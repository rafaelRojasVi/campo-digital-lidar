"""LAS RGB capability detection and explicit normalization.

LAS RGB dimensions are nominally unsigned 16-bit values, but some exporters
store 8-bit payloads directly in those fields. Normalization therefore records
the observed payload convention instead of assuming every LAS uses the full
16-bit range.

This module does not interpret RGB values as calibrated radiometry.
"""

from __future__ import annotations

from dataclasses import dataclass

import laspy
import numpy as np


@dataclass(frozen=True)
class NormalizedLasRgb:
    """Normalized LAS RGB plus explicit payload provenance."""

    rgb: np.ndarray
    source_dtype: str

    payload_min: int
    payload_max: int

    normalization_denominator: float
    normalization_mode: str


def extract_normalized_las_rgb(
    las: laspy.LasData,
) -> NormalizedLasRgb | None:
    """Return normalized RGB when usable LAS color values are present.

    Returns ``None`` when RGB dimensions are absent or when all RGB values are
    zero. All-zero RGB is treated as an unpopulated color payload rather than
    valid evidence for image-based log-end analysis.

    Normalization heuristic:
    - observed payload maximum <= 255: divide by 255
    - observed payload maximum > 255: divide by 65535

    The selected mode is returned explicitly because the <=255 distinction is
    based on observed exporter payload, not on a sensor-calibration claim.
    """

    dimension_names = set(las.point_format.dimension_names)

    if not {
        "red",
        "green",
        "blue",
    }.issubset(dimension_names):
        return None

    raw = np.column_stack(
        (
            np.asarray(las.red),
            np.asarray(las.green),
            np.asarray(las.blue),
        )
    )

    if len(raw) == 0:
        return None

    payload_min = int(raw.min())
    payload_max = int(raw.max())

    if payload_max == 0:
        return None

    if payload_max <= 255:
        denominator = 255.0
        mode = "eight_bit_payload_in_las_rgb_fields"
    else:
        denominator = 65535.0
        mode = "sixteen_bit_las_rgb_payload"

    normalized = (
        raw.astype(
            np.float64,
            copy=False,
        )
        / denominator
    )

    return NormalizedLasRgb(
        rgb=normalized,
        source_dtype=str(raw.dtype),
        payload_min=payload_min,
        payload_max=payload_max,
        normalization_denominator=denominator,
        normalization_mode=mode,
    )
