# campo-digital-lidar

Engineering proof-of-concept for LiDAR/point-cloud-based timber-stack
volume measurement, built for Campo Digital (Chile).

## Problem

Campo Digital needs to estimate the volume of stacked timber ("cubicación")
from point clouds captured by several sensors. This repo is an engineering
PoC: it does not encode Campo Digital's proprietary commercial cubicación
rules, and it does not claim to produce production-ready volume figures.
It scaffolds the data pipeline, LAS tooling, geometry primitives, and two
honestly-implemented raw geometric volume methods (cross-section
integration and voxel occupancy), plus interfaces for two more
(grid-2.5D, mesh) that are stubbed pending real data.

## Campo Digital technical context

Three sensors, all producing LAS as a common interchange format:

- **XGRIDS Lixel K2** -- handheld/backpack SLAM LiDAR; can also output
  mesh and 3D Gaussian Splatting (3DGS).
- **GeoSun GS-100G** -- terrestrial/backpack SLAM LiDAR.
- **DJI Zenmuse L2** -- aerial LiDAR payload for drones, RTK-aided.

See `configs/sensors/*.yaml` for what's documented about each (unknowns
are left as explicit `null`/TODO, never guessed), and `docs/sensors.md` /
`docs/accuracy.md` for accuracy terminology.

## Architecture

Single Python project, `src/`-layout, four importable packages plus a thin
CLI and a FastAPI scaffold. See `docs/architecture.md` for the full
rationale (including why this is not a multi-package uv workspace).

```
lidar_core    - domain models, geometry primitives, synthetic test fixtures
lidar_io      - LAS forensic inspection (laspy) + PDAL subprocess pipelines
lidar_volume  - volume estimator interface + implementations
lidar_cli     - `lidar` Typer CLI
apps/api      - FastAPI scaffold (/health only)
apps/viewer   - placeholder, no app yet
```

## Supported data

LAS 1.2-1.4, point formats as produced by the sensors above. LAZ is
supported for reading via laspy's `lazrs` backend. No point-cloud data is
stored in this repository (see Data Privacy below).

## Quickstart

```bash
uv sync --all-extras --dev
uv run lidar --help
uv run lidar generate-synthetic cube /tmp/synth.las --n-points 5000
uv run lidar inspect /tmp/synth.las
```

## LAS inspection usage

```bash
uv run lidar inspect path/to/file.las           # rich table
uv run lidar inspect path/to/file.las --json     # full JSON report
uv run lidar inspect path/to/file.las --no-checksum   # skip sha256 for huge files
```

Reads only the header/VLRs for most fields (no full point-cloud load);
classification/return-number histograms stream the file in chunks.

## Point-cloud pipeline

`pipelines/pdal/*.json` are PDAL pipeline templates (info, crop,
reprojection, decimation, ground filtering, height normalization,
LAS->LAZ). PDAL CLI is **not installed on this dev host** -- see
`docs/tooling.md` for the exact install command. `lidar_io.pdal_wrapper`
calls PDAL via subprocess and fails gracefully (clear error, or
pytest-skip in tests) when it's absent.

## Volume experiments

`lidar_volume` implements a common `VolumeEstimator` interface:

- `CrossSectionVolumeEstimator` -- fully implemented; divides an ROI into
  regular cross-section slabs along a chosen axis and integrates
  area x thickness. Validated against analytic prism/cylinder volumes in
  `tests/test_volume_estimators.py`.
- `VoxelVolumeEstimator` -- fully implemented; reports occupied-voxel
  count x voxel volume as an explicitly-labeled raw geometric statistic,
  **not** a commercial volume figure.
- `Grid25DVolumeEstimator`, `MeshVolumeEstimator` -- interface-only stubs;
  raise `NotImplementedError` with an explanation. Implementing these
  correctly requires validated rasterization/meshing decisions not yet
  made for this PoC.

`VolumeResult.volume_unit` defaults to `cubic_units_unspecified` and is
only ever `m3` when the caller explicitly confirms the source CRS/scale
justifies it.

## Testing

```bash
uv run pytest
```

All tests run on synthetic, deterministically-generated point clouds
(`lidar_core.testing`) -- no real/private data required, no network calls.

## Data privacy

**Never commit real point-cloud data.** `.gitignore` excludes
`*.las *.laz *.copc.laz *.e57 *.ply *.pcd *.bin *.tif *.tiff *.zip` and the
contents of `data/raw/`, `data/interim/`, `data/reference/private/`
(only `.gitkeep` placeholders are tracked). If you need to share sample
data with a collaborator, use an out-of-band channel, never `git add -f`.

## Accuracy terminology

Range precision, point-cloud thickness, relative/local precision, absolute
XYZ accuracy, registration accuracy, repeatability, and final volume error
are distinct, non-interchangeable concepts -- see `docs/accuracy.md`.
Never label a result "accurate" without specifying which of these it
refers to.

## Current limitations

- No real Campo Digital data has been used or is present in this repo.
- Grid-2.5D and mesh volume estimators are unimplemented stubs.
- PDAL, CloudCompare, QGIS, and LAStools CLI are not installed on this
  dev host (see `docs/tooling.md` for exact manual steps).
- No commercial cubicación conversion rule is implemented anywhere.
- No CRS is ever assumed; files without an encoded CRS report
  "CRS missing/ambiguous" rather than a guess.

## Roadmap (not built here)

Grid-2.5D and mesh volume estimators against real data; ROI
selection/segmentation workflow; a real viewer app; API persistence
(PostgreSQL/PostGIS via SQLAlchemy/Alembic), object storage, job queue;
ties to Campo Digital's commercial cubicación rules once specified.
