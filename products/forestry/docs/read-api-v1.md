# Forestry Read API V1

## Status

Implemented 2026-08-29 on top of
[Ingestion Substrate V1](ingestion-substrate-v1.md).

This is a **read-only factual projection** of the persisted Forestry source
substrate. Every endpoint reports stored source evidence or deterministic
arithmetic over it. There are no mutation endpoints and no authentication.
[Dashboard V1](dashboard-v1.md) consumes this API as its only data boundary.

## What this API does NOT establish

The API deliberately exposes *source* terminology (source predio, source
feature, snapshot-local feature, source fields, quality evidence) because the
underlying semantics are not confirmed. It does **not** establish:

- canonical predio or rodal identity (`Cod_Predial`/`nom_predio` pairs are
  source values; the two known anomaly pairs appear as their own rows);
- cross-snapshot feature identity (`OBJECTID` remains evidence only; features
  are addressed as `(shapefile_snapshot_id, feature_ordinal)`);
- workflow status, approval, progress, or management-plan request state;
- species or land-class meanings of use codes (values are served literally);
- geometry repair (invalid source geometry is served as stored, labeled);
- authoritative current forest state: `latest-ingested` is a fact about
  ingestion order only, not supersession semantics.

## Endpoints

All endpoints are `GET` under `/api/forestry`; the composition root is
`apps/api/app/main.py`, the router `apps/api/app/routers/forestry.py`, the
projections `apps/api/app/forestry_reads.py`.

| Endpoint | Returns |
|---|---|
| `/snapshots` | Persisted snapshots in ingestion order |
| `/snapshots/latest-ingested` | Most recently ingested snapshot (ingestion order only) |
| `/snapshots/{id}` | Per-snapshot summary: counts, areas, bbox, validity counts, quality-flag counts, dead-column count |
| `/snapshots/{id}/predio-distribution` | Source predio code/name pairs with feature counts and area sums |
| `/snapshots/{id}/use-distribution?field=uso_2024\|uso_2026` | Distribution of one year-stamped source use-class column |
| `/snapshots/{id}/source-field-comparison` | Literal `Uso2024 vs Uso2026` and `Cod_Uso vs CodUso_2026` differences |
| `/snapshots/{id}/features` | Paginated snapshot-local feature listing (no geometry payload) |
| `/snapshots/{id}/features/{ordinal}` | One feature: full source attribute row, validity evidence, GeoJSON-encoded geometry |
| `/snapshots/{id}/feature-collection` | GeoJSON-shaped collection of the filtered features with stored geometry |

Response contracts are explicit Pydantic models; they expose no filesystem
paths, connection information, SQL, or stack traces.

## Source-field comparison semantics

`/source-field-comparison` reports **source-field differences within one
snapshot**: rows where `Uso2024 IS DISTINCT FROM Uso2026`, and rows where
`Cod_Uso IS DISTINCT FROM CodUso_2026`. The payload carries a literal
`semantics` sentence restating this. These differences are **not** workflow
transitions, approvals, replant completions, or progress; individual code
semantics remain partially unconfirmed.

## Filtering

`/features` and `/feature-collection` accept the same deterministic,
source-justified filters (combined with AND):

- literal equality on `cod_predial`, `nom_predio`, `n_rodal`, `cod_uso`,
  `uso_2024`, `desc_uso`, `uso_2026`, `cod_uso_2026` (a NULL/blank stored
  value never matches an equality filter);
- `quality_flag` restricted to the established evidence vocabulary
  (`blank_rodal`, `duplicate_geometry`, `duplicate_predio_rodal_key`,
  `invalid_geometry`, `predio_code_name_anomaly`,
  `truncated_use_code_2026`); blank-rodal features are found via
  `quality_flag=blank_rodal`;
- `geometry_valid=true|false` on stored validity evidence;
- `uso_2024_vs_uso_2026=changed|unchanged` and
  `cod_uso_vs_cod_uso_2026=changed|unchanged` as literal
  `IS [NOT] DISTINCT FROM` conditions.

No business filters exist. Unknown filter *values* on whitelisted enums are
rejected with 422; a filter that simply matches nothing returns a normal
empty result.

## Pagination

`/features` is paginated (`limit` 1–500, default 100; `offset` >= 0) with
`total_count` and a deterministic `feature_ordinal` order.
`/feature-collection` is deliberately not paginated: a map wants the full
filtered set in one response, and the collection is bounded by the snapshot
size (1,568 features in the observed snapshot).

## Geometry representation

**DECISION** — Geometry is served as GeoJSON-shaped `MultiPolygon` objects
whose coordinates are exactly the stored source geometry in the snapshot's
storage CRS (EPSG:32718), serialized by `ST_AsGeoJSON`. RFC 7946 assumes
WGS84 lon/lat; reprojection would alter coordinates, so the payload instead
declares `storage_srid` explicitly and clients must reproject client-side if
they need lon/lat. Invalid source geometries serialize as stored — never
repaired — and every feature carries `geometry_is_valid` (plus
`geometry_invalid_reason` in the detail projection) as validity evidence.

**DECISION** — No vector tiles, geometry simplification, caching layer, or
search service: at 1,568 polygons the full real feature collection is a
single 9.4 MB response (RESULT, 2026-08-29), acceptable for the intended
dashboard; summary/listing endpoints exclude geometry so tabular reads stay
small.

## Errors

- `404` — snapshot not persisted, no snapshot persisted at all
  (`latest-ingested`), or unknown feature ordinal; each with a distinct
  detail message.
- `422` — invalid parameters (non-positive ids/ordinals, unknown use field,
  unknown quality flag, non-literal change-filter values, pagination out of
  bounds).
- `503` — database unavailable (`{"detail": "database unavailable"}`,
  backend error never leaked).
- Normal empty results (no snapshots, no matching features) are `200`.

## Verification against the real source (RESULT)

On 2026-08-29 the real `001_DEGENFELD_2026.zip` was ingested read-only into
the disposable test database (transaction rolled back afterwards; source
untouched) and the HTTP API was exercised end-to-end: 39/39 checks agreed
with [Source Evidence V1](source-evidence-v1.md) and
[Ingestion Substrate V1](ingestion-substrate-v1.md), including 1,568
features, `Sup_ha` total 10,422.61, 15 predio source pairs (the two anomaly
pairs listed as their own rows), 28 distinct values per use column, exactly
1 `Uso2024→Uso2026` difference (OBJECTID 508, ENSAYO → PLANTACION) and 72
`Cod_Uso→CodUso_2026` differences, all quality-flag counts
(143/32/8/7/2/2), the seven invalid-geometry OBJECTIDs, and the full
feature collection (9.4 MB).

## Integration concerns

**OPEN QUESTION (integration)** — Alembic revision `0003` currently exists
on two independent, unmerged feature branches: this Forestry branch
(`0003_establish_forestry_source_substrate`) and the Transelec hosted-pilot
branch (its own `0003` revising `0002`). Whichever branch is integrated
second must be re-revisioned/rebased (or otherwise reconciled) so `main`
keeps exactly one valid Alembic head. This API slice adds no migration, so
it does not worsen the collision; do not resolve it by coupling Forestry to
the unmerged Transelec branch.

## Still requires Javier / domain confirmation

Unchanged from the substrate — see
[preguntas-campo-digital.md](es/preguntas-campo-digital.md). The dashboard,
any editing/workflow surface, and any canonical identity remain out of
scope until those answers arrive.

## Related documentation

[Forestry product](../README.md) ·
[Ingestion Substrate V1](ingestion-substrate-v1.md) ·
[Source Evidence V1](source-evidence-v1.md) ·
[Source Contract V1](source-contract-v1.md) ·
[Product projection V1](product-projection-v1.md)
