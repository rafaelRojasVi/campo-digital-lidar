"""Browser-safe point-cloud preview artifacts for measurement runs.

The preview is derived from the already-selected timber-stack points.
It is intentionally bounded in size, deterministic, rebased around a
local origin, and stored only under the ignored measurement-output tree.

It is an inspection artifact, not a new measurement result.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lidar_core.models import MeasurementArtifact
from lidar_volume.front_cross_section import FrontCrossSectionEstimate

TIMBER_STACK_PREVIEW_FILENAME = "timber_stack_preview.ply"
TIMBER_STACK_PREVIEW_MANIFEST_FILENAME = "timber_stack_preview.json"

DEFAULT_MAX_PREVIEW_POINTS = 120_000
DEFAULT_PREVIEW_SEED = 42


def _validate_xyz(xyz: np.ndarray) -> np.ndarray:
    points = np.asarray(
        xyz,
        dtype=np.float64,
    )

    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("xyz must have shape (N, 3)")

    if len(points) == 0:
        raise ValueError("xyz must contain at least one point")

    if not np.isfinite(points).all():
        raise ValueError("xyz must contain only finite values")

    return points


def _sample_points(
    xyz: np.ndarray,
    *,
    max_points: int,
    seed: int,
) -> np.ndarray:
    if max_points < 1:
        raise ValueError("max_points must be >= 1")

    if len(xyz) <= max_points:
        return xyz

    rng = np.random.default_rng(seed)

    indices = rng.choice(
        len(xyz),
        size=max_points,
        replace=False,
    )
    indices.sort()

    return xyz[indices]


def _bounds_payload(xyz: np.ndarray) -> dict[str, list[float]]:
    return {
        "min": xyz.min(axis=0).astype(float).tolist(),
        "max": xyz.max(axis=0).astype(float).tolist(),
    }


def _write_binary_ply(
    path: Path,
    local_xyz: np.ndarray,
) -> None:
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment Campo Digital LiDAR measurement preview\n"
        f"element vertex {len(local_xyz)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    ).encode("ascii")

    positions = np.asarray(
        local_xyz,
        dtype="<f4",
    )

    with path.open("wb") as handle:
        handle.write(header)
        handle.write(positions.tobytes(order="C"))


def write_timber_stack_preview_artifacts(
    xyz: np.ndarray,
    estimate: FrontCrossSectionEstimate,
    run_directory: Path,
    *,
    max_points: int = DEFAULT_MAX_PREVIEW_POINTS,
    seed: int = DEFAULT_PREVIEW_SEED,
) -> tuple[MeasurementArtifact, MeasurementArtifact]:
    """Persist a bounded deterministic PLY preview and its metadata."""

    points = _validate_xyz(xyz)

    sampled = _sample_points(
        points,
        max_points=max_points,
        seed=seed,
    )

    run_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_min = points.min(axis=0)
    source_max = points.max(axis=0)

    # Centering the local representation minimizes float32 magnitude while
    # preserving the source-space origin explicitly in the manifest.
    origin = (source_min + source_max) / 2.0

    local_sampled = sampled - origin

    ply_path = run_directory / TIMBER_STACK_PREVIEW_FILENAME
    manifest_path = run_directory / TIMBER_STACK_PREVIEW_MANIFEST_FILENAME

    _write_binary_ply(
        ply_path,
        local_sampled,
    )

    longitudinal_axis = np.asarray(
        estimate.longitudinal_axis,
        dtype=np.float64,
    )

    transverse_axis = np.array(
        [
            -longitudinal_axis[1],
            longitudinal_axis[0],
        ],
        dtype=np.float64,
    )

    manifest = {
        "schema_version": "1",
        "kind": "timber_stack_point_cloud_preview",
        "ply_path": TIMBER_STACK_PREVIEW_FILENAME,
        "source_point_count": int(len(points)),
        "preview_point_count": int(len(sampled)),
        "sampling": {
            "method": "uniform_without_replacement",
            "max_points": int(max_points),
            "seed": int(seed),
        },
        "coordinate_units": "source_units",
        "coordinate_space": "rebased_source_coordinates",
        "position_encoding": "float32",
        "ply_encoding": "binary_little_endian",
        "origin_source_coordinates": origin.astype(float).tolist(),
        "source_bounds": _bounds_payload(points),
        "preview_local_bounds": _bounds_payload(local_sampled),
        "measurement_frame": {
            "center_xy_source": (
                np.asarray(
                    estimate.center_xy,
                    dtype=np.float64,
                )
                .astype(float)
                .tolist()
            ),
            "longitudinal_axis_xy": longitudinal_axis.astype(float).tolist(),
            "transverse_axis_xy": transverse_axis.astype(float).tolist(),
        },
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    ply_artifact = MeasurementArtifact(
        kind="timber_stack_point_cloud_preview",
        path=TIMBER_STACK_PREVIEW_FILENAME,
        media_type="application/octet-stream",
        description=(
            "Deterministically sampled and locally rebased timber-stack "
            "point cloud for read-only 3D inspection."
        ),
    )

    manifest_artifact = MeasurementArtifact(
        kind="timber_stack_point_cloud_preview_manifest",
        path=TIMBER_STACK_PREVIEW_MANIFEST_FILENAME,
        media_type="application/json",
        description=(
            "Coordinate, sampling, bounds, and measurement-frame metadata "
            "for the timber-stack 3D preview."
        ),
    )

    return ply_artifact, manifest_artifact
