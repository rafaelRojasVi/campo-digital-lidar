# Campo Digital LiDAR Viewer

Read-only engineering console for persisted timber-stack measurement runs.

The viewer is designed for inspection, quality control, provenance, and
reference validation. It does not mutate measurements or implement Campo
Digital's commercial cubicación rules.

## Development

Terminal 1 — API:

    uv run uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload

Terminal 2 — Viewer:

    cd apps/viewer
    npm run dev

Open the Vite URL printed in the terminal.

During development, Vite proxies `/api/*` to the local FastAPI server at
`127.0.0.1:8000`.

## Current UI

The console displays:

- persisted measurement runs
- measurement status and provenance
- structured blockers and warnings
- timber-stack selection metrics
- front cross-section geometry
- raw geometric volume results
- persisted reference comparisons
- registered JSON and PNG artifacts
- registered 3D timber-stack point-cloud previews

## 3D preview

Measurement runs may register a bounded browser-safe point-cloud preview:

    timber_stack_preview.ply
    timber_stack_preview.json

The preview:

- is derived only from the automatically selected timber-stack points
- uses deterministic sampling
- is capped at 120,000 points by default
- stores XYZ as binary float32 PLY
- rebases large source coordinates around a local origin for browser rendering
- preserves the source-coordinate origin and measurement frame in the manifest
- is served only through the API's registered-artifact allow-list
- is lazy-loaded in the browser using Three.js
- supports orbit, zoom, and pan
- is intended only for visual inspection and QC

The 3D preview is not a volume estimator and does not turn the observed
point-cloud surface into solid timber volume.

## Measurement interpretation

Raw geometric volume must not be interpreted automatically as commercial
timber cubicación.

In particular:

- the visible front envelope is directly observable
- an `A_front × depth` extrusion represents gross geometric stack-envelope
  volume when an explicit depth is supplied
- that extrusion may include voids between logs
- solid timber volume requires additional validated geometry and/or commercial
  rules
- unconfirmed coordinate units remain explicitly unconfirmed

## Current non-goals

- no measurement mutation
- no uploads
- no authentication
- no database-backed viewer state
- no inference of hidden pile depth
- no automatic conversion of stack-envelope volume to solid timber volume
- no commercial cubicación conversion rules
