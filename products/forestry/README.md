# Gestión Predial Forestal

Gestión Predial Forestal is a Campo Digital bounded product context covering
the Degenfeld estate ("patrimonio Degenfeld") land-use base.

## Current status

Forestry has an evidence-backed source contract, an immutable PostGIS
ingestion/read substrate, a read-only API, and a read-only visual dashboard;
business workflow and canonical cross-snapshot feature identity remain
unresolved.

Source Evidence V1 and Source Contract V1 are established from the first real
source snapshot supplied by the stakeholder (reviewed 2026-08-29). Ingestion
Substrate V1 (2026-08-29) persists contract-valid snapshots into PostGIS and
was verified read-only against the real snapshot. Read API V1 (2026-08-29)
exposes the persisted evidence as a read-only factual HTTP projection under
`/api/forestry`, also verified read-only against the real snapshot.
Dashboard V1 (2026-08-30) is a map-centric read-only web application over
that API, verified in the browser against the real snapshot and launched
locally with `make forestry-dev`.

No canonical entities, workflow states, or editing have been implemented;
those wait for stakeholder confirmation of the open questions.

## Source boundary

Expected external source location:

`01_Gestion_Predial_Forestal/02_Datos_Entrada/`

Source files remain outside Git. The observed snapshot is a ZIP containing a
single ESRI shapefile family (`Gdb_Degenfeld2026_mv`: 1,568 land-use
polygons, 13 predios), plus a previously generated standalone dashboard HTML
and a written stakeholder brief.

## Current implementation

`forestry_ingestion.shapefile_contract`:

- resolves and validates the shapefile family (`.shp/.shx/.dbf/.prj/.cpg`
  required; sidecars preserved);
- requires the declared UTF-8 encoding and the established CRS declaration
  (WGS_1984_UTM_Zone_18S) — a change fails validation for review;
- validates the 14-field DBF schema by name, type, width, and decimals;
- checks `.shp`/`.shx` header integrity, polygon shape type, and
  attribute/geometry record-count agreement;
- rejects soft-deleted records, unparseable numerics, and empty families;
- projects blank-normalized attribute rows with per-snapshot record numbers;
- fingerprints every member and derives a deterministic family fingerprint
  (SHA-256), aligned with the platform provenance model.

`forestry_ingestion.shapefile_geometry`, `family_archive`, and
`snapshot_evidence`:

- decode `.shp` polygon records faithfully (no repair, no reordering; a
  record that cannot be represented faithfully is a structured error);
- extract the source ZIP safely (read-only source, traversal-safe, exactly
  one family);
- compute snapshot-local quality flags for the anomaly classes established
  by Source Evidence V1.

`app.forestry_persistence` / `app.forestry_reads` (platform app layer):

- transactional, idempotent ingestion into the `forestry` PostGIS schema
  (migration `0003`), reusing the shared platform provenance foundation;
- snapshot-scoped read projections (summary, predio and use distributions,
  literal `Uso2024 vs Uso2026` / `Cod_Uso vs CodUso_2026` comparison,
  paginated/filterable feature listing, feature detail, GeoJSON-encoded
  geometry).

`app.routers.forestry` (platform app layer):

- read-only HTTP projection of those reads under `/api/forestry`
  ([Read API V1](docs/read-api-v1.md)); no mutation endpoints.

`products/forestry/dashboard/` (frontend):

- read-only map-centric dashboard over the read API
  ([Dashboard V1](docs/dashboard-v1.md)): estate map with factual color
  dimensions and legend, search/filters, synchronized paginated table,
  literal 2024→2026 comparison, quality-evidence panel, polygon inspector,
  filtered CSV export; launched via `make forestry-dev`.

All workflow semantics remain future slices.

## Documentation

- [Source Evidence V1](docs/source-evidence-v1.md) — forensic record of the
  observed snapshot (inventory, lineage, schema, profiling, dashboard).
- [Source Contract V1](docs/source-contract-v1.md) — the implemented
  structural contract.
- [Ingestion Substrate V1](docs/ingestion-substrate-v1.md) — the implemented
  PostGIS persistence, identity/idempotency, geometry/CRS decisions, and
  read projections.
- [Read API V1](docs/read-api-v1.md) — the read-only factual HTTP
  projection: endpoint contract, filters/pagination, geometry
  representation, and what it does not establish.
- [Product Projection V1](docs/product-projection-v1.md) — what a first
  read-only dashboard could safely show vs what needs confirmation.
- [Dashboard V1](docs/dashboard-v1.md) — the implemented read-only visual
  application: information architecture, map stack/projection, visual
  encoding, launcher, QA and performance results.
- [Resumen del visor para Campo Digital](docs/es/dashboard-v1.md) — Spanish
  stakeholder summary of the dashboard.
- [Preguntas para Javier](docs/es/preguntas-campo-digital.md) — Spanish
  stakeholder questionnaire.
