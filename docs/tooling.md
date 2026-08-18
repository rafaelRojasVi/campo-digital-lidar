# External tooling inventory

This repo vendors no third-party source. Everything below is an external
reference (package/binary/library), installed via official channels only.

## CLI/headless tools (WSL2 host)

### PDAL

#### Validated local setup

PDAL is installed and operational on the current WSL2 development host.
The host is Ubuntu 24.04.2 LTS (`noble`). The configured APT sources do
not currently expose `pdal` or `libpdal-dev`, so PDAL is kept outside the
project's `uv` environment in a dedicated Micromamba environment.

Validated versions on 2026-08-18:

- Micromamba: `2.9.0`
- environment: `pdal-cli`
- PDAL: `2.10.2` (`git-version: e8618b`)
- PDAL executable: `/home/rafael/micromamba/envs/pdal-cli/bin/pdal`
- project Python remains managed independently by `uv` / `.venv`

Micromamba itself is installed at `~/.local/bin/micromamba`, with root
prefix `~/micromamba`, and shell initialization is recorded in `~/.zshrc`.

Installation used:

```bash
# Run outside the project's activated Python .venv.
deactivate  # if the project .venv is active

"${SHELL}" <(curl -L micro.mamba.pm/install.sh)
source ~/.zshrc

micromamba create -y \
  -n pdal-cli \
  -c conda-forge \
  pdal

micromamba activate pdal-cli
```

For later shells:

```bash
source ~/.zshrc
micromamba activate pdal-cli
cd /home/rafael/dev/freelance/campo-digital-lidar
```

The repository deliberately uses the PDAL **CLI** boundary:
`src/lidar_io/pdal_wrapper.py` shells out to `pdal` via `subprocess` and
checks `shutil.which("pdal")`. This keeps the project's Python 3.12 `uv`
environment independent from PDAL's native dependency stack.

Note: the Conda Forge transaction selected a Python runtime and
`python-pdal` inside the isolated `pdal-cli` environment as package
dependencies. The application does not import or depend on those bindings;
they are not part of the project's `.venv` or `pyproject.toml` contract.

#### Validation

The installation was validated from the repository root with:

```bash
which pdal
pdal --version
pdal --drivers | head -40
uv run pytest tests/test_pdal_pipelines.py -v
uv run pytest
```

Observed result:

```text
PDAL 2.10.2
8/8 PDAL pipeline tests passed
27/27 repository tests passed
0 skipped
```

This proves the repo's PDAL JSON pipeline templates are accepted by the
installed PDAL CLI and that the previously skipped PDAL tests execute
successfully when the `pdal-cli` Micromamba environment is active.

#### Known optional-plugin warning

`pdal --drivers` currently emits load errors for these optional plugins:

- `libpdal_plugin_reader_hdf.so`
- `libpdal_plugin_reader_icebridge.so`

Both report a missing `libhdf5_cpp.so.320` shared library. Core PDAL is
still operational and all repository PDAL tests pass. Treat this as an
explicit environment caveat rather than evidence that the installation is
fully warning-free. Do not depend on the HDF or IceBridge readers until
that native-library mismatch is resolved and revalidated.

No CUDA-specific PDAL functionality is currently required by this PoC.
The large Conda environment and CUDA-related packages selected by the
solver are implementation details of this isolated external runtime, not
project runtime requirements.

References:

- https://pdal.io/
- https://github.com/PDAL/PDAL
- https://mamba.readthedocs.io/

### LAStools / LASlib / LASzip

- Status on this host: **not installed**. `which lasinfo` found nothing.
- LASzip (the compression library PDAL/laspy's `lazrs`/`laszip` backends
  use) and LASlib are open-source (LGPL); the full **LAStools** CLI suite
  bundles both free tools and separately-licensed commercial tools
  (e.g. `lasground`, `lasclassify` in unlicensed mode are demo/watermarked
  or restricted). Do not install commercially-licensed LAStools components
  without Campo Digital's/your own license.
- Free/open components: obtain via https://github.com/LASzip/LASzip and
  https://rapidlasso.de/downloads/ (LAStools free/open subset).
- We rely on `laspy[lazrs]` (pure Python + Rust LAZ codec) for LAS/LAZ I/O
  in this repo instead of requiring LAStools at all.

## GUI tools -- install on the WINDOWS HOST, not in WSL

WSL2 has no reliable GUI stack for these; do not attempt to install them
here.

- **CloudCompare** (point cloud viewing/editing): download the Windows
  installer from https://www.danielgm.net/cc/ (or
  https://github.com/CloudCompare/CloudCompare releases).
- **QGIS** (GIS/CRS work): download the Windows installer from
  https://qgis.org/en/site/forusers/download.html

WSL in this repo hosts CLI/headless tooling (PDAL CLI and Python
libraries). If you need to view a point cloud, use the Windows-host GUI;
files under the WSL filesystem are also reachable from Windows through the
WSL network share, or can be copied to `/mnt/c/...` when convenient.

## Python libraries (installed via `uv sync`, see pyproject.toml)

| Library | Purpose | Reference |
|---|---|---|
| numpy | array ops | https://numpy.org/ |
| scipy | ConvexHull, spatial | https://scipy.org/ |
| pandas | tabular data | https://pandas.pydata.org/ |
| laspy[lazrs] | LAS/LAZ I/O | https://github.com/laspy/laspy |
| pyproj | CRS transforms | https://pyproj4.github.io/pyproj/ |
| shapely | 2D geometry | https://shapely.readthedocs.io/ |
| scikit-learn | DBSCAN, NearestNeighbors | https://scikit-learn.org/ |
| trimesh | mesh utilities (future mesh estimator) | https://trimesh.org/ |
| pydantic | typed domain models | https://docs.pydantic.dev/ |
| typer | CLI framework | https://typer.tiangolo.com/ |
| rich | terminal output | https://rich.readthedocs.io/ |
| matplotlib | plotting | https://matplotlib.org/ |
| jupyterlab | notebooks | https://jupyter.org/ |
| open3d (optional, `geometry-extra` extra) | point-cloud ops/viz | https://www.open3d.org/ |
| pyvista (optional, `geometry-extra` extra) | 3D viz | https://pyvista.org/ |
| fastapi / uvicorn (optional, `api` extra) | future API | https://fastapi.tiangolo.com/ |

`COPC` (cloud-optimized point cloud) is a **format spec**, not a library
here -- referenced for future use: https://copc.io/

open3d/pyvista are kept in an optional `geometry-extra` extra rather than
the base dependency set: see the architecture/dependency notes for why
(they are heavy binary wheels not needed for the currently-implemented
numpy-only geometry ops).
