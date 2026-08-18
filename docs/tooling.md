# External tooling inventory

This repo vendors no third-party source. Everything below is an external
reference (package/binary/library), installed via official channels only.

## CLI/headless tools (installable on this WSL2 host)

### PDAL

- Status on this host: **not installed**. `which pdal` found nothing;
  not present in `apt list --installed`.
- Manual install (requires sudo, NOT run automatically by this bootstrap):
  ```
  sudo apt update && sudo apt install -y pdal libpdal-dev
  ```
- We deliberately do **not** install the `python-pdal` bindings via pip --
  they can conflict with a system/apt-installed PDAL's ABI. Instead,
  `src/lidar_io/pdal_wrapper.py` shells out to the `pdal` binary via
  `subprocess`, checking `shutil.which("pdal")` first and raising a clear
  `PdalNotAvailable` error (or letting pytest skip) when absent.
- Reference: https://pdal.io/ , https://github.com/PDAL/PDAL

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

WSL in this repo hosts only CLI/headless tooling (PDAL CLI, LAStools CLI,
Python libraries). If you need to view a point cloud, copy it to the
Windows filesystem (e.g. `/mnt/c/...`) and open it with the Windows
install of CloudCompare.

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
the base dependency set: see the "dependency resolution notes" in the
final bootstrap report for why (both installed fine for Python 3.12 on
this host at bootstrap time, but they are heavy binary wheels not needed
for the currently-implemented numpy-only geometry ops).
