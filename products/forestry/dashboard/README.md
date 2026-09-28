# Forestry Dashboard

Read-only, map-centric web application over the persisted Degenfeld snapshot,
served by the Forestry Read API (`/api/forestry`). Product/design record:
[`../docs/dashboard-v1.md`](../docs/dashboard-v1.md).

## One-command demo (recommended)

From the repository root:

```sh
make forestry-dev      # DB + migrations + idempotent ingestion + API + frontend
make forestry-status
make forestry-stop
```

## Manual development

Backend (repository root, requires the dev database and an ingested
snapshot):

```sh
uv run --extra api uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload
```

Frontend (this directory):

```sh
npm install
npm run dev          # proxies /api to 127.0.0.1:${FORESTRY_API_PORT:-8000}
```

## Checks

```sh
npm run lint         # oxlint
npm run build        # tsc -b && vite build
npm test             # vitest (jsdom; Leaflet map is exercised in browser QA)
```

Or from the repository root: `make forestry-frontend-check`.

## Layout of `src/`

- `api.ts`, `types.ts` — typed client for the read API.
- `lib/` — pure, unit-tested logic: EPSG:32718→WGS84 display reprojection
  (`proj.ts`, pyproj-derived fixtures), filters/search, aggregation, color
  encoding (validated categorical palette + fold rule), table sorting,
  comparison grouping, CSV export, es-CL formatting.
- `components/` — header/KPIs/filters/legend, Leaflet map (canvas renderer,
  centroid markers for sub-pixel polygons), synchronized table, 2024→2026
  comparison, quality-evidence panel, polygon inspector, status views.

The UI is Spanish (stakeholder-facing); code and docs are English. All
labels preserve the backend's evidence discipline: literal source values,
literal field comparisons, and quality evidence only.
