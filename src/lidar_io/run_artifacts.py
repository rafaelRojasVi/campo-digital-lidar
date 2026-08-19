"""Machine-readable artifacts produced by measurement runs.

Artifacts contain detailed diagnostic data that is useful for plotting,
inspection, API responses, and future UI work without bloating the primary
MeasurementRun record.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lidar_core.models import MeasurementArtifact
from lidar_volume.front_cross_section import FrontCrossSectionEstimate

FRONT_PROFILE_FILENAME = "front_profile.json"


def write_front_profile_artifact(
    estimate: FrontCrossSectionEstimate,
    run_directory: Path,
) -> MeasurementArtifact:
    """Persist per-bin observable front-profile geometry as JSON."""

    run_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = run_directory / FRONT_PROFILE_FILENAME

    bins: list[dict[str, float | int | None]] = []

    for index in range(len(estimate.bin_centres)):
        base_raw = estimate.base_raw[index]
        top_raw = estimate.top_raw[index]

        bins.append(
            {
                "index": index,
                "station": float(estimate.bin_centres[index]),
                "point_count": int(estimate.point_counts[index]),
                "base_raw": (float(base_raw) if np.isfinite(base_raw) else None),
                "top_raw": (float(top_raw) if np.isfinite(top_raw) else None),
                "base": float(estimate.base[index]),
                "top": float(estimate.top[index]),
                "height": float(estimate.height[index]),
            }
        )

    payload = {
        "schema_version": "1",
        "kind": "front_profile",
        "coordinate_units": "source_units",
        "longitudinal_min": estimate.longitudinal_min,
        "longitudinal_max": estimate.longitudinal_max,
        "longitudinal_span": estimate.longitudinal_span,
        "valid_bin_fraction": estimate.valid_bin_fraction,
        "rectangle_area": estimate.rectangle_area,
        "trapezoid_area": estimate.trapezoid_area,
        "bins": bins,
    }

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return MeasurementArtifact(
        kind="front_profile",
        path=FRONT_PROFILE_FILENAME,
        media_type="application/json",
        description=("Per-bin observable timber-stack front profile in source-coordinate units."),
    )


FRONT_PROFILE_PLOT_FILENAME = "front_profile.png"


def write_front_profile_plot_artifact(
    estimate: FrontCrossSectionEstimate,
    run_directory: Path,
) -> MeasurementArtifact:
    """Persist a visual representation of the observable front envelope."""

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    run_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = run_directory / FRONT_PROFILE_PLOT_FILENAME

    figure = Figure(
        figsize=(10, 6),
        dpi=150,
    )
    canvas = FigureCanvasAgg(figure)
    axis = figure.subplots()

    station = np.asarray(
        estimate.bin_centres,
        dtype=np.float64,
    )
    base = np.asarray(
        estimate.base,
        dtype=np.float64,
    )
    top = np.asarray(
        estimate.top,
        dtype=np.float64,
    )

    axis.fill_between(
        station,
        base,
        top,
        alpha=0.25,
        label="Observed front envelope",
    )

    axis.plot(
        station,
        top,
        linewidth=1.2,
        label="Top envelope",
    )
    axis.plot(
        station,
        base,
        linewidth=1.2,
        label="Base envelope",
    )

    axis.set_title("Observable timber-stack front profile")
    axis.set_xlabel("Longitudinal station (source units)")
    axis.set_ylabel("Elevation (source units)")

    axis.grid(
        True,
        alpha=0.2,
    )
    axis.legend()
    figure.tight_layout()

    canvas.print_png(str(path))

    return MeasurementArtifact(
        kind="front_profile_plot",
        path=FRONT_PROFILE_PLOT_FILENAME,
        media_type="image/png",
        description=(
            "Observable timber-stack base and top envelopes plotted "
            "directly from the measured front-profile bins."
        ),
    )


FRONT_HEIGHT_PROFILE_PLOT_FILENAME = "front_height_profile.png"


def write_front_height_profile_plot_artifact(
    estimate: FrontCrossSectionEstimate,
    run_directory: Path,
) -> MeasurementArtifact:
    """Persist observable front-profile height versus longitudinal station."""

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    run_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = run_directory / FRONT_HEIGHT_PROFILE_PLOT_FILENAME

    station = np.asarray(
        estimate.bin_centres,
        dtype=np.float64,
    )
    height = np.asarray(
        estimate.height,
        dtype=np.float64,
    )

    figure = Figure(
        figsize=(10, 5),
        dpi=150,
    )
    canvas = FigureCanvasAgg(figure)
    axis = figure.subplots()

    axis.fill_between(
        station,
        0.0,
        height,
        alpha=0.25,
        label="Observed profile height",
    )

    axis.plot(
        station,
        height,
        linewidth=1.4,
        label="Height",
    )

    median_height = float(np.median(height))

    axis.axhline(
        median_height,
        linewidth=1.0,
        linestyle="--",
        label=f"Median height = {median_height:.3f}",
    )

    axis.set_title("Observable timber-stack height profile")
    axis.set_xlabel("Longitudinal station (source units)")
    axis.set_ylabel("Profile height (source units)")

    axis.set_ylim(
        bottom=0.0,
    )

    axis.grid(
        True,
        alpha=0.2,
    )
    axis.legend()

    figure.tight_layout()

    canvas.print_png(str(path))

    return MeasurementArtifact(
        kind="front_height_profile_plot",
        path=FRONT_HEIGHT_PROFILE_PLOT_FILENAME,
        media_type="image/png",
        description=(
            "Observed timber-stack profile height computed directly as "
            "top envelope minus base envelope for each longitudinal bin."
        ),
    )
