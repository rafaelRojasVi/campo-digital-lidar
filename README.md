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
(grid-2.5D, mesh) that are stubbed pending validated real-data methodology.

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

## Real-data forensic baseline

A real Campo Digital LAS dataset has now been inspected locally without
committing the point cloud itself. The first baseline is documented at
`docs/datasets/v01_MG_23jun2026.md` and records:

- source ZIP and extracted LAS SHA-256 hashes
- archive safety/inventory checks
- LAS 1.2 / point-format-3 structure and point count
- independent `lidar inspect` and PDAL metadata/statistics checks
- missing CRS/unit status
- a material discrepancy between LAS-header bounds and extents recomputed
  from the actual points
- attribute statistics, provenance caveats, and CloudCompare visual baseline

No volume result from this real dataset is considered meaningful yet: CRS/units,
source/export provenance, a reproducible timber ROI, and an authoritative
reference measurement for the same physical region are still unresolved.

## Point-cloud pipeline

`pipelines/pdal/*.json` are PDAL pipeline templates (info, crop,
reprojection, decimation, ground filtering, height normalization,
LAS->LAZ). PDAL 2.10.2 is installed on the current WSL2 development host
in an isolated Micromamba environment named `pdal-cli`; the project itself
continues to use its independent `uv` / Python 3.12 environment.

Activate PDAL before running PDAL-backed workflows or tests:

```bash
source ~/.zshrc
micromamba activate pdal-cli
```

The PDAL pipeline suite currently validates successfully (`8/8` tests),
and the complete repository suite passes `33/33` with no skipped tests.
See `docs/tooling.md` for the exact installation, validation commands, and
the known warning affecting the optional HDF/IceBridge reader plugins.

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
PDAL-backed tests require the `pdal` executable to be visible in `PATH`;
on the current development host that means activating `pdal-cli` first.

## Data privacy

**Never commit real point-cloud data.** `.gitignore` excludes
`*.las *.laz *.copc.laz *.e57 *.ply *.pcd *.bin *.tif *.tiff *.zip` and the
contents of `data/raw/`, `data/interim/`, `data/reference/private/`
(only `.gitkeep` placeholders are tracked). If you need to share sample
data with a collaborator, use an out-of-band channel, never `git add -f`.

Sanitized forensic metadata (hashes, LAS structure/statistics, commands,
methodology observations) may be documented under `docs/datasets/`; raw client
points and derived point-level exports remain local/private.

## Accuracy terminology

Range precision, point-cloud thickness, relative/local precision, absolute
XYZ accuracy, registration accuracy, repeatability, and final volume error
are distinct, non-interchangeable concepts -- see `docs/accuracy.md`.
Never label a result "accurate" without specifying which of these it
refers to.

## Current limitations

- Real Campo Digital data has been inspected locally, but no raw/private point
  cloud is present in Git.
- The first real LAS has no encoded CRS or unit metadata, so `m3` results are
  explicitly blocked until units are confirmed.
- The exact source sensor/export pipeline and target timber ROI for the first
  dataset are not yet confirmed.
- Grid-2.5D and mesh volume estimators are unimplemented stubs.
- CloudCompare is installed and validated on the Windows host; QGIS and
  LAStools CLI are not yet installed.
- PDAL core/pipeline validation is operational, but the optional HDF and
  IceBridge readers currently emit a missing `libhdf5_cpp.so.320` warning;
  they are not required by the current LAS workflow.
- No commercial cubicación conversion rule is implemented anywhere.
- No CRS is ever assumed; files without an encoded CRS report
  "CRS missing/ambiguous" rather than a guess.

## Roadmap (not built here)

Resolve real-dataset CRS/provenance; identify and persist a reproducible timber
ROI; obtain a reference result for the same physical region; then validate
cross-section, voxel, grid-2.5D and mesh methods against real data. Later work
may include a real viewer app; API persistence (PostgreSQL/PostGIS via
SQLAlchemy/Alembic), object storage, job queue; and ties to Campo Digital's
commercial cubicación rules once specified.


## Current technical findings

- [Cubicación accuracy: current technical findings](docs/findings/cubicacion_accuracy_problem.md)
