# Architecture

## Layout decision: single project, src-layout, NOT a true uv workspace

The spec allowed either a uv workspace of independently-publishable
packages, or a simpler single-project layout. This repo uses the latter:

- One root `pyproject.toml`, one `uv.lock`, one venv.
- Four import-only Python packages under `src/`: `lidar_core`, `lidar_io`,
  `lidar_volume`, `lidar_cli`, each a plain package directory (no nested
  `pyproject.toml`).
- `apps/api` is a separate FastAPI app that imports the `src/` packages
  from its own path insertion (see `tests/test_api.py`); it is not part
  of the installed package set.

**Why not a uv workspace:** none of these packages need independent
versioning, independent publishing, or independent dependency sets at this
stage -- they are tightly coupled layers of one PoC. A workspace would add
four `pyproject.toml` files and cross-package path dependencies for no
current benefit. If/when `lidar_core` needs to be published standalone
(e.g. as a library other Campo Digital tools consume), converting to a
workspace is a mechanical refactor, not a redesign.

## Package boundaries

```
lidar_core    domain models (pydantic), geometry primitives (numpy/sklearn/
              scipy, optional open3d), synthetic test-data generators.
              No I/O, no CLI, no PDAL.
lidar_io      LAS/LAZ inspection (laspy) and PDAL subprocess pipelines.
              Depends on lidar_core for models.
lidar_volume  Volume estimator interface + implementations. Depends on
              lidar_core for models/geometry.
lidar_cli     Typer CLI wiring the above together. Depends on all three.
```

## Future stack (NOT built in this bootstrap)

`apps/api` will eventually need: PostgreSQL + PostGIS for spatial storage
of ROIs/results, SQLAlchemy + Alembic for schema/migrations, object
storage (e.g. S3-compatible) for LAS/LAZ files themselves, a job queue
(e.g. Celery/RQ/arq) for long-running volume computations, and a real web
viewer (`apps/viewer`) built on a 3D web rendering stack. None of this
exists yet -- only `/health` is wired up in `apps/api`.

## Why PDAL is a subprocess dependency, not a Python binding

See `docs/tooling.md` -- summary: PDAL CLI was not installed on the
bootstrap host, python-pdal bindings can conflict with system packages,
and a subprocess wrapper degrades gracefully (clear error / pytest skip)
when PDAL is absent, which a hard import dependency would not.

<!-- DOC_NAV_START -->

---

### Documentation navigation

[Project README](../README.md) · [Docs index](README.md) · [Findings](findings/cubicacion_accuracy_problem.md) · [Experiments](experiments) · [Decisions](decisions) · [Spanish docs](es/README.md) · [Estado técnico](es/estado-proyecto.md) · [Preguntas Campo Digital](es/preguntas-campo-digital.md)

<!-- DOC_NAV_END -->
