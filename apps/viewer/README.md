# Campo Digital LiDAR Viewer

Read-only engineering console for persisted measurement runs.

This first viewer intentionally does not implement point-cloud rendering,
measurement mutation, authentication, uploads, or commercial cubicación rules.

## Development

Terminal 1 — API:

    uv run uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload

Terminal 2 — Viewer:

    cd apps/viewer
    npm run dev

Open the Vite URL printed in the terminal.

During development, Vite proxies /api/* to the local FastAPI server at
127.0.0.1:8000.

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

Raw geometric volume must not be interpreted as commercial timber cubicación.
Unconfirmed coordinate units remain explicitly unconfirmed.

## Current non-goals

- no point-cloud or 3D rendering
- no measurement mutation
- no uploads
- no authentication
- no database-backed viewer state
- no commercial cubicación conversion rules
