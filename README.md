# campo-digital-lidar

[English](#english) · [Español ↓](#espanol) · [Roadmap](#roadmap) · [Documentation](docs/README.md)

<a id="english"></a>

## English

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

<a id="roadmap"></a>

## Roadmap

The PoC is being developed in evidence-driven phases. A phase is considered
complete only when its claims are supported by reproducible code, tests,
dataset evidence, or confirmed Campo Digital information.

### Phase A — LAS forensic correctness ✅

- ingest real LAS safely
- preserve client data outside Git
- distinguish observed point bounds from stale header bounds
- preserve missing CRS/units instead of guessing
- establish reproducible PDAL / laspy / CloudCompare tooling

### Phase B — Acquisition diagnostics ✅

- analyze GPS-time ordering
- characterize return-number structure
- reconstruct exact timestamp groups in streaming mode
- quantify exact R1/R2 pair geometry
- document acquisition/export limitations
- establish the first real-data forensic baseline

### Phase C — Deterministic timber-stack ROI ← NEXT

- identify the visible timber-stack region
- define the ROI reproducibly in configuration/code
- generate a local `data/interim/` timber crop
- verify the crop visually in CloudCompare
- avoid undocumented manual-only selection

### Phase D — Front-face and log-end geometry

- estimate the local orientation of the timber face
- normalize the face into a stable coordinate frame
- separate timber-end geometry from vegetation/background
- detect full and partial log ends
- fit circle/ellipse/robust diameter models
- attach QC/uncertainty to detections
- validate log count and diameter stability

### Phase E — Cubicación and reference validation

- determine what Campo Digital defines as the target cubicación
- obtain the same-pile reference measurement and ROI
- confirm CRS and physical units
- determine how log length / stack depth is provided
- compare geometric methods against the accepted reference
- quantify error and repeatability
- reject unsupported m³ accuracy claims

### Phase F — Field pilot and productization

Only after the geometric PoC is validated:

- field capture workflow
- operator UX
- offline-first operation
- FastAPI service
- PostgreSQL/PostGIS metadata
- object storage for point clouds
- project/client history
- QC reports and audit trail
- dashboard/viewer
- integration with Campo Digital's commercial workflow

The immediate engineering target is **Phase C: isolate the timber wall
reproducibly and begin measuring the visible log-end geometry**.

## Documentation and current technical findings

Start here for detailed engineering evidence:

- [Documentation index](docs/README.md)
- [Current cubicación accuracy findings](docs/findings/cubicacion_accuracy_problem.md)
- [Real dataset forensic baseline](docs/datasets/v01_MG_23jun2026.md)
- [Experiments](docs/experiments/)
- [Engineering decisions / ADRs](docs/decisions/)
- [Engineering journal](docs/journal/)
- [Spanish collaboration documentation](docs/es/README.md)
- [Estado técnico del proyecto](docs/es/estado-proyecto.md)
- [Preguntas abiertas para Campo Digital](docs/es/preguntas-campo-digital.md)

---

<a id="espanol"></a>

# Español

[↑ English](#english) · [Hoja de ruta](#roadmap-es) · [Índice de documentación](docs/README.md) · [Documentación en español](docs/es/README.md)

## Resumen

Este repositorio contiene el PoC de ingeniería para estudiar la medición y
cubicación de rumas de madera utilizando nubes de puntos LiDAR para Campo Digital.

El objetivo actual **no es entregar todavía un valor comercial de m³**.

Primero estamos determinando:

- qué información contiene realmente la nube;
- qué metadatos son confiables;
- qué geometría de la ruma es observable;
- qué partes requieren inferencia;
- cómo medir de forma reproducible;
- y contra qué medición de referencia debe validarse el resultado.

## Estado actual

Ya se puede procesar reproduciblemente el primer LAS real de Campo Digital,
con aproximadamente **9,7 millones de puntos**.

Entre los principales hallazgos:

- los límites almacenados en el encabezado LAS no coinciden con la geometría real;
- el archivo no declara CRS ni unidades lineales;
- la escala numérica del LAS no debe confundirse con precisión física;
- GPS Time mantiene un orden temporal coherente;
- existen 5.609.224 grupos exactos de timestamp;
- 4.109.685 de esos grupos contienen exactamente dos registros;
- todos los grupos de dos registros siguen el patrón `Return 1 -> Return 2`;
- todavía no está confirmada la interpretación física de esos retornos;
- la cara visible de la ruma de madera es el siguiente objetivo geométrico.

La explicación completa se encuentra en:

- [Estado técnico del proyecto](docs/es/estado-proyecto.md)
- [Hallazgos técnicos de cubicación](docs/findings/cubicacion_accuracy_problem.md)
- [Preguntas abiertas para Campo Digital](docs/es/preguntas-campo-digital.md)

<a id="roadmap-es"></a>

## Hoja de ruta

### Fase A — Forense y lectura correcta del LAS ✅

- lectura reproducible del dataset real;
- protección de datos privados;
- límites observados vs. límites del header;
- CRS/unidades no asumidos;
- herramientas PDAL, laspy y CloudCompare validadas.

### Fase B — Análisis de adquisición ✅

- GPS Time;
- estructura de retornos;
- grupos exactos de timestamp;
- pares R1/R2;
- documentación de limitaciones y hallazgos.

### Fase C — ROI reproducible de la ruma ← SIGUIENTE

- aislar la gran cara visible de madera;
- guardar la selección como configuración/código;
- generar un crop reproducible;
- verificar visualmente en CloudCompare.

### Fase D — Geometría de los extremos de rollizos

- orientar la cara de la ruma;
- detectar extremos circulares/elípticos;
- estimar diámetros;
- contar rollizos;
- identificar detecciones inciertas.

### Fase E — Cubicación y validación

- confirmar la definición de cubicación de Campo Digital;
- confirmar unidades;
- obtener ground truth de la misma ruma;
- incorporar largo/profundidad;
- calcular error y repetibilidad;
- comparar métodos.

### Fase F — Piloto y producto

Solo si el PoC geométrico funciona:

- aplicación de terreno;
- operación offline;
- API;
- base de datos;
- almacenamiento de nubes;
- dashboard;
- trazabilidad;
- integración con el flujo comercial de Campo Digital.

## Documentación en español

Para colaboradores de Campo Digital:

- [Índice en español](docs/es/README.md)
- [Estado técnico](docs/es/estado-proyecto.md)
- [Preguntas para Campo Digital](docs/es/preguntas-campo-digital.md)
- [Bitácora](docs/es/bitacora/)
- [Índice completo de documentación](docs/README.md)

## Limitaciones importantes

Todavía **no** se ha demostrado:

- sensor exacto del primer LAS;
- CRS;
- unidades físicas;
- precisión final en m³;
- detección automática completa de rollizos;
- largo/profundidad de cada rollizo;
- ground truth de la misma ruma;
- regla comercial definitiva de cubicación.

Por esa razón, cualquier cifra volumétrica actual debe considerarse experimental
hasta completar las fases de geometría y validación.

[↑ Volver al inicio](#campo-digital-lidar)
