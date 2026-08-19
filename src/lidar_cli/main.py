"""`lidar` CLI entry point.

Genuinely functional: inspect, info, crop, generate-synthetic.
Explicit "not yet implemented" stubs: sections, volume, compare.
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
from lidar_io.inspect import inspect_las

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
def volume(input_path: Annotated[Path, typer.Argument()]) -> None:
    """NOT YET IMPLEMENTED: end-to-end volume CLI (ROI selection not wired up)."""
    console.print(
        "[yellow]Not yet implemented.[/yellow] "
        "Use lidar_volume estimators directly on a numpy array."
    )
    raise typer.Exit(code=2)


@app.command()
def compare(inputs: Annotated[list[str], typer.Argument()]) -> None:
    """NOT YET IMPLEMENTED: multi-method/multi-run comparison CLI."""
    console.print("[yellow]Not yet implemented.[/yellow]")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
