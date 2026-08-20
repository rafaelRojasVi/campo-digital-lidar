"""Machine-readable artifacts produced by measurement runs.

Artifacts contain detailed diagnostic data that is useful for plotting,
inspection, API responses, and future UI work without bloating the primary
MeasurementRun record.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from lidar_core.models import MeasurementArtifact
from lidar_core.visible_log_end_analysis import VisibleLogEndAnalysisResult
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


VISIBLE_LOG_END_ANALYSIS_FILENAME = "visible_log_end_candidates.json"


def _visible_log_end_relative_range_quantiles(
    result: VisibleLogEndAnalysisResult,
) -> dict[str, float | None]:
    values = np.asarray(
        [
            association.relative_diameter_range
            for association in result.resolved_summary.associations
        ],
        dtype=np.float64,
    )

    if len(values) == 0:
        return {
            "q50": None,
            "q75": None,
            "q90": None,
            "q95": None,
            "q99": None,
            "max": None,
        }

    return {
        "q50": float(np.quantile(values, 0.50)),
        "q75": float(np.quantile(values, 0.75)),
        "q90": float(np.quantile(values, 0.90)),
        "q95": float(np.quantile(values, 0.95)),
        "q99": float(np.quantile(values, 0.99)),
        "max": float(values.max()),
    }


def write_visible_log_end_analysis_artifact(
    result: VisibleLogEndAnalysisResult,
    run_directory: Path,
) -> MeasurementArtifact:
    """Persist experimental visible log-end candidate evidence as JSON.

    The artifact records projected candidate geometry and cross-window
    association evidence. It does not represent a confirmed log count,
    validated solid-wood area, timber volume, or commercial cubicacion.
    """

    run_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = run_directory / VISIBLE_LOG_END_ANALYSIS_FILENAME

    observations: list[dict[str, object]] = []

    for index, evidence in enumerate(result.observations):
        area = evidence.candidate.area

        observations.append(
            {
                "index": index,
                "window_index": (result.observation_window_indices[index]),
                "x_px": evidence.candidate.x_px,
                "y_px": evidence.candidate.y_px,
                "radius_px": area.radius_px,
                "horizontal_units_per_pixel": (area.horizontal_units_per_pixel),
                "vertical_units_per_pixel": (area.vertical_units_per_pixel),
                "horizontal_radius_source_units": (area.horizontal_radius_source_units),
                "vertical_radius_source_units": (area.vertical_radius_source_units),
                "projected_area_source_units_squared": (area.projected_area_source_units_squared),
                "equivalent_radius_source_units": (area.equivalent_radius_source_units),
                "equivalent_diameter_source_units": (area.equivalent_diameter_source_units),
                "visible_support_count": (evidence.visible_support_count),
                "visible_source_indices": list(evidence.visible_source_indices),
            }
        )

    associations: list[dict[str, object]] = []

    for index, association in enumerate(result.resolved_summary.associations):
        associations.append(
            {
                "index": index,
                "member_indices": list(association.member_indices),
                "observation_count": (association.observation_count),
                "representative_equivalent_diameter_source_units": (
                    association.representative_equivalent_diameter_source_units
                ),
                "projected_area_source_units_squared": (
                    association.projected_area_source_units_squared
                ),
                "minimum_equivalent_diameter_source_units": (
                    association.minimum_equivalent_diameter_source_units
                ),
                "maximum_equivalent_diameter_source_units": (
                    association.maximum_equivalent_diameter_source_units
                ),
                "relative_diameter_range": (association.relative_diameter_range),
                "visible_source_union_count": (association.visible_source_union_count),
            }
        )

    payload = {
        "schema_version": "1",
        "kind": "visible_log_end_candidate_analysis",
        "coordinate_units": "source_units",
        "quantity": {
            "name": ("association_resolved_projected_log_end_candidate_area"),
            "unit": "source_units_squared",
            "value": (result.resolved_summary.projected_area_sum_source_units_squared),
        },
        "semantics": {
            "confirmed_log_count": False,
            "validated_solid_wood_area": False,
            "timber_volume": False,
            "commercial_cubicacion": False,
            "hidden_log_length_inferred": False,
        },
        "analysis_config": asdict(result.config),
        "detector_config": asdict(result.detector_config),
        "association_config": asdict(result.association_config),
        "summary": {
            "window_count": len(result.windows),
            "observation_count": (result.resolved_summary.observation_count),
            "supported_observation_count": (result.resolved_summary.supported_observation_count),
            "unsupported_observation_count": len(
                result.resolved_summary.unsupported_observation_indices
            ),
            "unsupported_observation_indices": list(
                result.resolved_summary.unsupported_observation_indices
            ),
            "association_hypothesis_count": (result.resolved_summary.association_count),
            "multi_observation_association_count": (
                result.resolved_summary.multi_observation_association_count
            ),
            "representative_method": (result.resolved_summary.representative_method),
            "projected_candidate_area_sum_source_units_squared": (
                result.resolved_summary.projected_area_sum_source_units_squared
            ),
        },
        "qc": {
            "relative_diameter_range_quantiles": (
                _visible_log_end_relative_range_quantiles(result)
            ),
        },
        "windows": [asdict(window) for window in result.windows],
        "observations": observations,
        "associations": associations,
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
        kind="visible_log_end_candidate_analysis",
        path=VISIBLE_LOG_END_ANALYSIS_FILENAME,
        media_type="application/json",
        description=(
            "Experimental visible log-end candidate geometry, "
            "cross-window evidence association, and diameter QC "
            "in source-coordinate units."
        ),
    )
