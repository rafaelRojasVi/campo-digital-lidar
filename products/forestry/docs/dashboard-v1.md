# Forestry Dashboard V1

## Status

Implemented 2026-08-30 on top of [Read API V1](read-api-v1.md), following the
projection boundaries of [Product Projection V1](product-projection-v1.md).

This is the first visual Forestry application: a read-only, map-centric web
dashboard over the persisted Degenfeld snapshot, in Spanish, aimed at the
stakeholder (Javier / a forestry project manager). It preserves the evidence
discipline of the backend: every label is a source fact, a literal field
comparison, or quality evidence — never workflow status, progress, approval,
or canonical identity.

Code: `products/forestry/dashboard/` (Vite + React 19 + TypeScript, Leaflet
1.9, proj4). Launcher: `scripts/forestry_dev.py` via `make forestry-dev` /
`forestry-status` / `forestry-stop`.

## Information architecture

```text
Header      brand · "Patrimonio Degenfeld" · provenance (última ingesta,
            layer name, EPSG, family fingerprint) — labeled as ingestion
            order, never "vigente"
KPI strip   server-computed snapshot facts (feature count, Sup_ha total +
            geometry-derived total, predio code/name pairs, use classes,
            2024/2026 field differences, invalid geometries)
Sidebar     search · filters (predio, uso 2026, rodal; progressive
            disclosure: uso 2024, descripción, códigos, comparaciones,
            validez, evidencia de calidad) · color dimension + legend
Map         dominant surface (Leaflet, canvas renderer)
Bottom      tabs synchronized with the filtered set:
            Tabla (paginated) · 2024 → 2026 (literal comparison) ·
            Calidad de datos (evidence classes)
Inspector   right panel (desktop) / bottom sheet (mobile) per selected
            polygon; raw source attribute row behind a disclosure
```

**DECISION** — The full feature collection (~9.15 MB, 1,568 features) is
loaded once from `/api/forestry/.../feature-collection`; all filtering,
search, aggregation, and pagination run client-side over that set, so map,
table, legend, and export stay synchronized instantly without re-downloading
geometry. Server endpoints provide provenance-grade numbers (summary,
comparison, per-feature detail on selection). Measured behavior at pilot
scale justified the simple architecture (see Performance).

## Map stack and projection handling

**DECISION** — Leaflet 1.9 with the canvas renderer, chosen as the simplest
appropriate option for 1,568 polygons (the prior standalone dashboard was
also Leaflet). No vector tiles, tile server, or GIS frontend framework.

**DECISION** — Stored geometry is served in EPSG:32718 exactly as persisted;
the browser reprojects for display only via proj4
(`+proj=utm +zone=18 +south +datum=WGS84`). The transformation is explicit
(`src/lib/proj.ts`) and unit-tested against pyproj-derived fixtures over the
observed snapshot envelope (agreement within 1e-6°, ≈0.1 m). The persisted
source geometry object is never mutated (guarded by test).

- Basemap: OpenStreetMap raster tiles (key-free, attributed), toggleable;
  the application is fully functional without tiles — the forestry polygons
  remain the authoritative visual evidence.
- Fractional zoom (`zoomSnap 0.25`) so fitting the sparse estate envelope
  (≈45 × 70 km for 104 km² of polygons) does not snap a full zoom level out.
- Interactions: hover tooltip (predio, rodal, uso, ha), click to select,
  zoom-to-selection, "Ajustar a resultados", scale control.
- Cartographic readability rules established during browser QA:
  - the white boundary stroke appears from zoom 12 up, or whenever the
    filtered subset is ≤ 200 polygons (1,568 white strokes at estate scale
    washed the fills out);
  - **representative point markers**: in a filtered subset (≤ 200), any
    polygon smaller than ~8 px at the current resolution gets a centroid
    dot in its dimension color — the 72 changed polygons total ≈ 154 painted
    pixels at estate zoom and were effectively invisible without this.

## Visual encoding

Color dimensions (selector + legend): `Uso 2026` (default), `Uso 2024`,
`Predio`, `Comparación 2024 → 2026`, `Evidencia de calidad`.

**DECISION** — Categorical dimensions assign the 8 validated hues of the
dataviz reference palette in descending `Sup_ha` order; vocabularies beyond
8 values fold into a neutral "Otros" gray, blank source values into their own
gray. Colors are assigned over the full collection so they stay stable while
filters change. The palette order passes the CVD validator's adjacent-pair
gates (worst adjacent ΔE 9.1 protan; normal-vision floor 19.6); as documented
in the palette reference, no 8-hue set passes all-pairs, so identity is never
color-alone: hover tooltips, the legend (click-to-filter), and the table
carry it. The legend doubles as the factual area distribution (swatch, value,
Sup_ha sum, proportional bar, polygon count).

**DECISION** — No semantic color mapping (no green = forest, no red = bad):
hues follow area rank only, because land-class meanings are unconfirmed and
colors must not imply business semantics. The comparison dimension uses one
neutral blue for "campos distintos" vs light gray; quality evidence uses one
orange for "con evidencia" — explicitly labeled as literal field differences
and *evidencia de calidad de datos* respectively.

## 2024 → 2026 treatment

The comparison tab shows the API's literal source-field comparison:
`Uso2024 → Uso2026` (1 difference: OBJECTID 508, ENSAYO → PLANTACION) and
`Cod_Uso → CodUso_2026` (72 differences), each row joined client-side with
its predio/rodal context, plus the most frequent before→after value pairs
(e.g. `Pi01 → Pi25 ×8`). A single action filters the map to the differing
polygons. The panel states in the UI that these are literal field
differences within one snapshot, not workflow transitions or completed
management — mirroring the API's semantics string.

## Data-quality treatment

The quality tab lists the six established evidence classes with
server-computed counts (7 invalid geometries, 2 duplicate geometries, 143
blank rodales, 32 repeated predio/rodal keys, 2 code/name anomalies, 8
truncated codes), each with a Spanish description and a "Ver en el mapa"
filter action. Framing in the UI: observed evidence recorded at ingestion,
not errors the system corrects nor prioritized tasks. Invalid geometries are
drawn exactly as stored; the inspector shows the GEOS invalidity reason.

## Polygon detail (inspector)

Selected via map click, centroid marker, table row, or comparison row (rows
also zoom). Sections: land use (both year-stamped classes and codes, with a
"difieren" note when literal fields differ), surface (`Sup_ha` vs
geometry-derived hectares), geometry validity (+ reason), quality-evidence
chips, source evidence (OBJECTID labeled as source evidence, shapefile
record number, snapshot id), and the full 14-field raw attribute row behind
a disclosure. Detail data comes from the per-feature endpoint with its own
loading/error states.

## Table, export, states

- 25 rows per page; sortable by predio, rodal (numeric-aware), uso, código,
  `Sup_ha`; row click selects + zooms; external selections jump to the
  containing page and scroll into view; pagination resets on filter change.
- CSV export of the filtered, sorted set (client-side, UTF-8 BOM for Excel;
  column set = source projection fields + validity/quality evidence).
  Exports are browser downloads only and are never committed.
- Handled states: initial loading, no persisted snapshot (points to
  `make forestry-dev`), API unavailable (retry), empty filter results (map
  overlay + table message), detail-fetch failure. No stack traces or
  internal paths are exposed.

## Responsive behavior

Desktop-first (QA at 1440×900 and 1920×1080). At ≤720 px (QA at 390×844):
map-first, sidebar becomes a slide-in drawer, inspector becomes a bottom
sheet, KPI strip scrolls horizontally, wide tables scroll inside their own
container. Reduced motion is respected for the spinner and drawer
transition.

## Local launcher

`make forestry-dev` (`scripts/forestry_dev.py up`):

1. creates `.env` from `.env.example` with a generated password if missing;
2. refuses to run unless `APP_ENV=development` and the DB host is local;
3. validates the external source ZIP read-only (via `app.source_discovery`,
   which rejects symlinks/traversal and never writes);
4. `docker compose up -d --wait postgres` (the shared dev service);
5. `alembic upgrade head`;
6. ingests `001_DEGENFELD_2026.zip` idempotently (family-fingerprint
   identity; re-runs log `already persisted`);
7. starts uvicorn and the Vite dev server on free ports (preferred 8000 /
   5173; falls back to OS-assigned — verified when 8000 was occupied),
   wiring the frontend proxy via `FORESTRY_API_PORT`;
8. prints URLs and opens a browser best-effort (wslview/xdg-open/powershell).

`make forestry-status` reports recorded PIDs, ports, and HTTP health;
`make forestry-stop` terminates only the recorded processes after
re-verifying their `/proc` cmdline against the recorded marker, and
deliberately leaves the shared dev database running. State lives in
`.forestry-dev/` (gitignored).

## Verification against the real source (RESULT)

Browser QA on 2026-08-30 ran against the real snapshot ingested by the
launcher (1,568 features, fingerprint `19beaed5…60bd1`, id 1):

- KPI/legend/comparison/quality numbers matched Source Evidence V1 exactly
  (10,422.61 ha; 15 code/name pairs over 13 names and 13 codes; 28 classes;
  1 class change = OBJECTID 508 ENSAYO → PLANTACION; 72 code changes;
  7/2/143/32/2/8 evidence counts);
- filter/fit/hover/select/inspector flows verified at 1440×900, 1920×1080,
  390×844, including an invalid geometry (HT rodal 677, ring
  self-intersection reason shown) and keyboard row activation;
- CSV export produced 1,568 rows with faithful source values.

## Performance (RESULT)

Measured in Chromium at 1440×900 against the real snapshot, dev server:

- feature collection: 9.15 MB decoded, fetched in ≈0.4 s locally;
- initial layer build (reprojection + 1,568 canvas polygons) leaves a JS
  heap of ≈128 MB; steady-state frame time ≈16.3 ms (60 fps);
- filter changes restyle/re-add layers without visible lag.

**DECISION** — No vector tiles, server clustering, or caching infrastructure
at this scale; revisit only with measured evidence of degradation.

## Limitations and open items

- **LIMITATION** — The client-side search/filters operate on the loaded
  snapshot only; they are not a general query interface.
- **LIMITATION** — Raster basemap at fractional zoom can show transient
  tile-sharpness seams while tiles load.
- **LIMITATION** — At estate zoom, sub-pixel polygons are clickable only via
  their centroid markers (small subsets) or after zooming; hit-testing tiny
  canvas polygons is inherently imprecise.
- Read-only by design: no editing, uploads, management-plan requests, print
  layouts, Excel (XLSX) export, or German-language views — pending the
  stakeholder answers in
  [preguntas-campo-digital.md](es/preguntas-campo-digital.md).

## Related documentation

[Forestry product](../README.md) ·
[Read API V1](read-api-v1.md) ·
[Ingestion Substrate V1](ingestion-substrate-v1.md) ·
[Source Evidence V1](source-evidence-v1.md) ·
[Product projection V1](product-projection-v1.md) ·
[Resumen para Campo Digital](es/dashboard-v1.md)
