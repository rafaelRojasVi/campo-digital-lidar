"""`lidar` CLI entry point.

Genuinely functional: inspect, analyze, info, crop, generate-synthetic, volume.
Explicit "not yet implemented" stubs: sections, compare.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import laspy
import numpy as np
import typer
from rich.console import Console
from rich.table import Table

from lidar_core.testing import cube, cylinder, rectangular_prism
from lidar_io.analyze import analyze_las
from lidar_io.inspect import inspect_las
from lidar_volume.front_cross_section import (
    FrontCrossSectionConfig,
    estimate_front_cross_section,
    extruded_volume,
)

app = typer.Typer(add_completion=False, help="Campo Digital LiDAR engineering CLI.")
console = Console()


@app.command()
def inspect(
    path: Annotated[Path, typer.Argument(help="Path to a LAS/LAZ file.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of a table.")
    ] = False,
    no_checksum: Annotated[
        bool, typer.Option("--no-checksum", help="Skip sha256 computation.")
    ] = False,
) -> None:
    """Forensic inspection of a LAS/LAZ file's header/metadata."""
    try:
        meta = inspect_las(path, compute_checksum=not no_checksum)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        print(meta.model_dump_json(indent=2))
        return

    table = Table(title=f"LAS Inspection: {meta.path}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("File size", f"{meta.file_size_bytes:,} bytes")
    table.add_row("SHA256", meta.sha256 or "(skipped)")
    table.add_row("LAS version", f"{meta.las_version_major}.{meta.las_version_minor}")
    table.add_row("Point format", str(meta.point_format_id))
    table.add_row("Point count", f"{meta.point_count:,}")
    table.add_row("Scales", str(meta.scales))
    table.add_row("Offsets", str(meta.offsets))
    b = meta.bounds
    table.add_row(
        "Observed bounds",
        f"X[{b.min_x:.3f},{b.max_x:.3f}] Y[{b.min_y:.3f},{b.max_y:.3f}] "
        f"Z[{b.min_z:.3f},{b.max_z:.3f}]",
    )

    hb = meta.header_bounds
    table.add_row(
        "Header bounds",
        f"X[{hb.min_x:.3f},{hb.max_x:.3f}] Y[{hb.min_y:.3f},{hb.max_y:.3f}] "
        f"Z[{hb.min_z:.3f},{hb.max_z:.3f}]",
    )
    table.add_row("Header bounds match", str(meta.header_bounds_match))
    table.add_row(
        "Observed spans",
        f"dx={b.span_x:.3f} dy={b.span_y:.3f} dz={b.span_z:.3f}",
    )
    crs = meta.coordinate_metadata
    table.add_row(
        "CRS",
        f"EPSG:{crs.crs_epsg}" if crs.is_explicit and crs.crs_epsg else "MISSING/AMBIGUOUS",
    )
    table.add_row("Standard dims", ", ".join(meta.dimensions.standard_dims))
    table.add_row("Extra dims", ", ".join(meta.dimensions.extra_dims) or "(none)")
    table.add_row("RGB", str(meta.dimensions.has_rgb))
    table.add_row("Intensity", str(meta.dimensions.has_intensity))
    table.add_row("GPS time", str(meta.dimensions.has_gps_time))
    table.add_row("VLRs", str(meta.vlr_count))
    table.add_row("EVLRs", str(meta.evlr_count))
    table.add_row("Classification histogram", str(meta.classification_histogram) or "(none)")
    table.add_row("Return-number histogram", str(meta.return_number_histogram) or "(none)")
    if meta.warnings:
        table.add_row("[yellow]Warnings[/yellow]", "\n".join(meta.warnings))
    console.print(table)


@app.command()
def analyze(
    path: Annotated[Path, typer.Argument(help="Path to a LAS/LAZ file.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of a table.")
    ] = False,
) -> None:
    """Stream acquisition/export diagnostics from a LAS/LAZ file."""
    try:
        result = analyze_las(path)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        print(result.model_dump_json(indent=2))
        return

    def fmt(value: float | None) -> str:
        return "(n/a)" if value is None else f"{value:.9g}"

    table = Table(title=f"LAS Acquisition Analysis: {result.path}")
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("Point count", f"{result.point_count:,}")

    if result.observed_bounds is not None:
        b = result.observed_bounds
        table.add_row(
            "Observed bounds",
            f"X[{b.min_x:.3f},{b.max_x:.3f}] "
            f"Y[{b.min_y:.3f},{b.max_y:.3f}] "
            f"Z[{b.min_z:.3f},{b.max_z:.3f}]",
        )

    table.add_row("GPS time present", str(result.gps_time_present))
    table.add_row(
        "GPS time range",
        f"{fmt(result.gps_time_min)} -> {fmt(result.gps_time_max)} "
        f"(span={fmt(result.gps_time_span)})",
    )
    table.add_row(
        "GPS file-order endpoints",
        f"first={fmt(result.gps_time_first)} last={fmt(result.gps_time_last)}",
    )
    table.add_row(
        "GPS non-decreasing",
        str(result.gps_time_non_decreasing),
    )
    table.add_row(
        "GPS order steps",
        f"backward={result.gps_time_backward_steps} equal={result.gps_time_equal_steps}",
    )
    table.add_row(
        "GPS positive step",
        f"min={fmt(result.gps_time_min_positive_step)} "
        f"max={fmt(result.gps_time_max_positive_step)}",
    )

    table.add_row(
        "Equal-time same-return",
        str(result.equal_time_adjacent_same_return_pairs),
    )
    table.add_row(
        "Equal-time cross-return",
        str(result.equal_time_adjacent_cross_return_pairs),
    )
    table.add_row(
        "Equal-time R1/R2",
        (
            f"{result.equal_time_adjacent_r1_r2_pairs} "
            f"(fraction={fmt(result.equal_time_adjacent_r1_r2_fraction)})"
        ),
    )

    if result.paired_return_distance is not None:
        s = result.paired_return_distance
        table.add_row(
            "R1/R2 3D separation",
            f"min={fmt(s.minimum)} mean={fmt(s.mean)} max={fmt(s.maximum)}",
        )

    for axis, summary in (
        ("X", result.paired_return_abs_delta_x),
        ("Y", result.paired_return_abs_delta_y),
        ("Z", result.paired_return_abs_delta_z),
    ):
        if summary is not None:
            table.add_row(
                f"R1/R2 |delta {axis}|",
                (f"min={fmt(summary.minimum)} mean={fmt(summary.mean)} max={fmt(summary.maximum)}"),
            )

    if result.paired_return_abs_intensity_delta is not None:
        s = result.paired_return_abs_intensity_delta
        table.add_row(
            "R1/R2 |intensity delta|",
            f"min={fmt(s.minimum)} mean={fmt(s.mean)} max={fmt(s.maximum)}",
        )

    if result.timestamp_groups is not None:
        groups = result.timestamp_groups

        table.add_row(
            "Timestamp groups",
            (
                f"count={groups.group_count:,} "
                f"max-size={groups.max_group_size} "
                f"sizes={groups.size_counts}"
            ),
        )

        table.add_row(
            "2-record patterns",
            str(groups.two_record_return_pattern_counts),
        )

        table.add_row(
            "Exact 2-record R1/R2",
            (
                f"{groups.two_record_r1_r2_groups:,}/"
                f"{groups.two_record_groups:,} "
                f"(fraction={fmt(groups.two_record_r1_r2_fraction)})"
            ),
        )

        if groups.exact_pair_distance is not None:
            summary = groups.exact_pair_distance
            table.add_row(
                "Exact-pair 3D separation",
                (f"min={fmt(summary.minimum)} mean={fmt(summary.mean)} max={fmt(summary.maximum)}"),
            )

        for axis, summary in (
            ("X", groups.exact_pair_abs_delta_x),
            ("Y", groups.exact_pair_abs_delta_y),
            ("Z", groups.exact_pair_abs_delta_z),
        ):
            if summary is not None:
                table.add_row(
                    f"Exact-pair |delta {axis}|",
                    (
                        f"min={fmt(summary.minimum)} "
                        f"mean={fmt(summary.mean)} "
                        f"max={fmt(summary.maximum)}"
                    ),
                )

        if groups.exact_pair_abs_intensity_delta is not None:
            summary = groups.exact_pair_abs_intensity_delta
            table.add_row(
                "Exact-pair |intensity delta|",
                (f"min={fmt(summary.minimum)} mean={fmt(summary.mean)} max={fmt(summary.maximum)}"),
            )

    if result.intensity is not None:
        s = result.intensity
        table.add_row(
            "Intensity",
            f"min={fmt(s.minimum)} mean={fmt(s.mean)} max={fmt(s.maximum)}",
        )

    for channel in ("red", "green", "blue"):
        if channel in result.rgb:
            s = result.rgb[channel]
            table.add_row(
                f"RGB {channel}",
                f"min={fmt(s.minimum)} mean={fmt(s.mean)} max={fmt(s.maximum)}",
            )

    if result.scan_angle_rank is not None:
        s = result.scan_angle_rank
        table.add_row(
            "Scan angle rank",
            f"min={fmt(s.minimum)} mean={fmt(s.mean)} max={fmt(s.maximum)}",
        )

    table.add_row("Return-number counts", str(result.return_number_counts))
    table.add_row("Number-of-returns counts", str(result.number_of_returns_counts))
    table.add_row("Point-source IDs", str(result.point_source_id_counts))
    table.add_row("Scan-direction flags", str(result.scan_direction_flag_counts))
    table.add_row("Edge-of-flight-line flags", str(result.edge_of_flight_line_counts))

    table.add_row(
        "Global XY density",
        (
            "(n/a)"
            if result.xy_density_points_per_square_source_unit is None
            else (f"{result.xy_density_points_per_square_source_unit:.6f} points/source-unit²")
        ),
    )

    for return_summary in result.return_summaries:
        b = return_summary.bounds
        intensity_mean = (
            "(n/a)" if return_summary.intensity is None else fmt(return_summary.intensity.mean)
        )
        table.add_row(
            f"Return {return_summary.return_number}",
            f"{return_summary.point_count:,} points; "
            f"X[{b.min_x:.3f},{b.max_x:.3f}] "
            f"Y[{b.min_y:.3f},{b.max_y:.3f}] "
            f"Z[{b.min_z:.3f},{b.max_z:.3f}]; "
            f"intensity mean={intensity_mean}",
        )

    if result.warnings:
        table.add_row(
            "[yellow]Warnings[/yellow]",
            "\n".join(result.warnings),
        )

    console.print(table)


@app.command()
def info(path: Annotated[Path, typer.Argument(help="Path to a LAS/LAZ file.")]) -> None:
    """Alias for a concise `inspect` summary (JSON)."""
    try:
        meta = inspect_las(path)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    print(
        json.dumps(
            {
                "path": meta.path,
                "point_count": meta.point_count,
                "las_version": f"{meta.las_version_major}.{meta.las_version_minor}",
                "point_format": meta.point_format_id,
                "crs_explicit": meta.coordinate_metadata.is_explicit,
                "warnings": meta.warnings,
            },
            indent=2,
        )
    )


@app.command()
def crop(
    input_path: Annotated[Path, typer.Argument(help="Input LAS/LAZ file.")],
    output_path: Annotated[Path, typer.Argument(help="Output LAS file.")],
    min_x: Annotated[float, typer.Option()],
    min_y: Annotated[float, typer.Option()],
    max_x: Annotated[float, typer.Option()],
    max_y: Annotated[float, typer.Option()],
    min_z: Annotated[float | None, typer.Option()] = None,
    max_z: Annotated[float | None, typer.Option()] = None,
) -> None:
    """Deterministic axis-aligned crop of a LAS file (laspy-based, no PDAL required)."""
    if not input_path.exists():
        console.print(f"[red]Error:[/red] input file not found: {input_path}")
        raise typer.Exit(code=1)

    las = laspy.read(str(input_path))
    points = np.column_stack([las.x, las.y, las.z])
    mask = (
        (points[:, 0] >= min_x)
        & (points[:, 0] <= max_x)
        & (points[:, 1] >= min_y)
        & (points[:, 1] <= max_y)
    )
    if min_z is not None:
        mask &= points[:, 2] >= min_z
    if max_z is not None:
        mask &= points[:, 2] <= max_z

    cropped = las.points[mask]
    out = laspy.LasData(header=las.header)
    out.points = cropped
    out.write(str(output_path))
    console.print(f"Cropped {mask.sum():,}/{len(points):,} points -> [green]{output_path}[/green]")


_SYNTHETIC_GENERATORS: dict[str, Callable[..., tuple[np.ndarray, float]]] = {
    "cube": cube,
    "prism": rectangular_prism,
    "cylinder": cylinder,
}


@app.command("generate-synthetic")
def generate_synthetic(
    shape: Annotated[str, typer.Argument(help="One of: cube, prism, cylinder.")],
    output_path: Annotated[Path, typer.Argument(help="Output LAS file.")],
    n_points: Annotated[int, typer.Option(help="Number of points to sample.")] = 2000,
    seed: Annotated[int, typer.Option(help="RNG seed for reproducibility.")] = 0,
) -> None:
    """Generate a synthetic LAS file for testing/demo purposes (no real data)."""
    if shape not in _SYNTHETIC_GENERATORS:
        console.print(
            f"[red]Error:[/red] unknown shape '{shape}'. Choose from {list(_SYNTHETIC_GENERATORS)}."
        )
        raise typer.Exit(code=1)

    points, volume = _SYNTHETIC_GENERATORS[shape](n_points=n_points, seed=seed)

    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = [0.001, 0.001, 0.001]
    header.offsets = [0.0, 0.0, 0.0]
    las = laspy.LasData(header)
    las.x = points[:, 0]
    las.y = points[:, 1]
    las.z = points[:, 2]
    las.write(str(output_path))
    console.print(
        f"Wrote {len(points):,} synthetic '{shape}' points to [green]{output_path}[/green] "
        f"(analytic volume = {volume:.6f} cubic source-units; CRS intentionally unset)."
    )


@app.command()
def sections(input_path: Annotated[Path, typer.Argument()]) -> None:
    """NOT YET IMPLEMENTED: sectional decomposition CLI."""
    console.print(
        "[yellow]Not yet implemented.[/yellow] "
        "Use lidar_volume.cross_section.compute_sections directly."
    )
    raise typer.Exit(code=2)


@app.command()
def volume(
    input_path: Annotated[
        Path,
        typer.Argument(
            help="Path to a LAS/LAZ timber-front ROI.",
        ),
    ],
    depth: Annotated[
        float | None,
        typer.Option(
            "--depth",
            help=(
                "Explicit extrusion depth in source-coordinate units. "
                "If omitted, no cubic volume is computed."
            ),
        ),
    ] = None,
    bins: Annotated[
        int,
        typer.Option(
            "--bins",
            help="Number of longitudinal bins for the front-wall profile.",
        ),
    ] = 160,
) -> None:
    """Measure observable timber-front area and optional extrusion volume."""

    if not input_path.is_file():
        console.print(f"[red]Error:[/red] LAS/LAZ file not found: {input_path}")
        raise typer.Exit(code=1)

    if bins < 2:
        console.print("[red]Error:[/red] --bins must be >= 2.")
        raise typer.Exit(code=1)

    if depth is not None and depth < 0:
        console.print("[red]Error:[/red] --depth must be non-negative.")
        raise typer.Exit(code=1)

    las = laspy.read(input_path)

    xyz = np.column_stack(
        (
            np.asarray(las.x),
            np.asarray(las.y),
            np.asarray(las.z),
        )
    )

    try:
        estimate = estimate_front_cross_section(
            xyz,
            FrontCrossSectionConfig(
                n_bins=bins,
            ),
        )
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title=f"Timber Front Measurement: {input_path}")

    table.add_column("Field")
    table.add_column("Value")

    table.add_row(
        "Point count",
        f"{len(xyz):,}",
    )

    table.add_row(
        "Longitudinal span",
        f"{estimate.longitudinal_span:.6f} source units",
    )

    table.add_row(
        "Valid bins",
        f"{estimate.valid_bin_fraction:.3%}",
    )

    table.add_row(
        "Median height",
        f"{np.median(estimate.height):.6f} source units",
    )

    table.add_row(
        "Maximum height",
        f"{np.max(estimate.height):.6f} source units",
    )

    table.add_row(
        "Rectangle area",
        f"{estimate.rectangle_area:.6f} source-units²",
    )

    table.add_row(
        "Trapezoid area",
        f"{estimate.trapezoid_area:.6f} source-units²",
    )

    if depth is None:
        table.add_row(
            "Extruded volume",
            "(not computed; provide --depth)",
        )
    else:
        volume_value = extruded_volume(
            estimate.rectangle_area,
            depth,
        )

        table.add_row(
            "Assumed depth",
            f"{depth:.6f} source units",
        )

        table.add_row(
            "Extruded volume",
            f"{volume_value:.6f} source-units³",
        )

    console.print(table)

    console.print()
    console.print(
        "[yellow]Units:[/yellow] Results remain in source-coordinate "
        "units. This command does not infer metres from LAS scale, "
        "offsets, or missing/ambiguous CRS metadata."
    )

    if depth is not None:
        console.print(
            "[yellow]Model:[/yellow] Cubic volume is the geometric "
            "extrusion A_front × depth. The supplied depth is not "
            "inferred or validated from the current LAS."
        )


@app.command()
def compare(inputs: Annotated[list[str], typer.Argument()]) -> None:
    """NOT YET IMPLEMENTED: multi-method/multi-run comparison CLI."""
    console.print("[yellow]Not yet implemented.[/yellow]")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
