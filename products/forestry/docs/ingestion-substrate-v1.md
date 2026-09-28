# Forestry Ingestion Substrate V1

## Status

Implemented 2026-08-29 on top of [Source Contract V1](source-contract-v1.md).

This slice persists contract-valid Forestry shapefile snapshots immutably
into PostGIS and provides service-level read projections sufficient to prove
the persisted model. It is **not** the Forestry workflow application: no
editing, no management-plan requests, no business statuses, and no canonical
cross-snapshot polygon identity exist.

## Persistence model

Two product-specific tables in the new `forestry` schema (migration `0003`),
anchored to the platform provenance foundation:

```text
platform.source_system / source_asset / source_snapshot / source_observation
        ^ (unchanged shared foundation; the observed ZIP is recorded here)
        |
forestry.shapefile_snapshot   one row per immutable shapefile family
        |
forestry.source_feature       one row per source feature (1,568 in the
                              observed snapshot)
```

`forestry.shapefile_snapshot` preserves: the platform `source_snapshot`
reference of the observed archive, the deterministic family fingerprint
(unique), layer name, per-member SHA-256 digests (JSONB), the declared `.prj`
WKT, the storage SRID, encoding, shape type, header bounding box, and feature
count.

`forestry.source_feature` preserves, per feature: the owning snapshot, the
1-based `feature_ordinal`, the source `OBJECTID` (evidence only), the full
geometry (`geometry(MultiPolygon, 32718)`, GIST-indexed), OGC validity plus
invalidity reason, the geometry-derived area in source units², the complete
blank-normalized source attribute row (JSONB, all 14 fields), typed
projection columns (`nom_predio`, `cod_predial`, `n_rodal`, `cod_uso`,
`uso_2024`, `desc_uso`, `uso_2026`, `cod_uso_2026`, `sup_ha`, `shape_area`),
and machine-readable `quality_flags`.

**DECISION** — Raw JSONB attributes plus selected typed columns, no
normalization. The JSONB row makes the source projection reproducible even if
typed columns evolve; the typed columns serve the established read
projections. No canonical `predio`, `rodal`, or workflow tables exist because
the source evidence does not support them (JSONB key order is normalized by
PostgreSQL; field order remains defined by the contract).

## Identity and idempotency

**DECISION** — Feature identity is `(shapefile_snapshot_id, feature_ordinal)`
only, where the ordinal is the shared DBF/SHX/SHP record number. Source
Evidence V1 established that `OBJECTID` stability across exports is unproven
and `(predio, rodal)` is neither unique nor always present, so no
cross-snapshot identity is defined. `source_objectid` is stored as evidence:
it is not unique-constrained, and the same value may appear in many
snapshots.

**DECISION** — Snapshot identity is the contract's family fingerprint
(SHA-256 over sorted member digests), unique in
`forestry.shapefile_snapshot`. Ingestion behavior:

- contract validation, geometry decoding, and quality evidence all complete
  **before** the first database write;
- platform provenance (system/asset/snapshot/observation of the ZIP) is
  persisted in the same caller-owned transaction, following the established
  `app.source_provenance` pattern — a failure anywhere aborts everything, so
  a half-imported snapshot cannot exist;
- re-ingesting identical family content is idempotent: the existing Forestry
  snapshot is returned (`already_persisted=True`), no feature rows are
  written, and the repeated observation is appended as platform provenance
  history;
- a repackaged archive (different ZIP bytes, identical members) creates a new
  platform snapshot but resolves to the same Forestry snapshot, which keeps
  its original platform reference.

Implementation: `app.forestry_persistence.ingest_forestry_snapshot`
(app layer), using `forestry_ingestion.family_archive` (safe ZIP extraction:
traversal-safe member paths, exactly one `.shp` required, source untouched).

## Geometry and CRS

**DECISION** — The storage SRID is **EPSG:32718** ("WGS 84 / UTM zone 18S").
It is derived from the contract's pinned ESRI WKT declaration
(`WGS_1984_UTM_Zone_18S`) via pyproj's EPSG registry, never inferred from
coordinates, and guarded by a unit test
(`test_storage_srid_matches_authoritative_epsg_mapping_of_contract_wkt`).
The embedded ArcGIS metadata's EPSG 32718 declaration is consistent
supporting evidence.

**DECISION** — `forestry_ingestion.shapefile_geometry` decodes `.shp` polygon
records faithfully: coordinates are never reordered, repaired, or closed on
the reader's behalf (an unclosed or degenerate ring is a structured error,
not a repair). Clockwise rings are exteriors per the ESRI specification;
each counter-clockwise ring attaches to the smallest exterior that contains
the filled hole polygon; an orphan hole is preserved as its own part so no
source ring is ever dropped. Every record is stored as a MultiPolygon (the
standard PostGIS promotion for polygon shapefiles), which changes no
coordinates.

**DECISION** — Invalid source geometries are stored as-is with
`geometry_is_valid = false` and the GEOS invalidity reason. The seven known
self-intersecting features ingest faithfully; no derived repaired geometry
exists in this slice.

`geometry_area_source_units` is computed at ingestion (GEOS area, identical
formula to PostGIS `ST_Area`; verified equal on the real snapshot). Areas are
in source units² — the declared linear unit is metres, but m³/m² accuracy
claims remain governed by the documentation policy.

## Data-quality evidence

Per-feature `quality_flags` reproduce only anomaly classes established by
[Source Evidence V1](source-evidence-v1.md); they are evidence, not workflow
status:

| Flag | Rule (snapshot-local) | Observed count |
|---|---|---|
| `invalid_geometry` | fails OGC validity | 7 |
| `duplicate_geometry` | byte-identical WKB shared with another feature | 2 |
| `blank_rodal` | `N_Rodal` blank | 143 |
| `duplicate_predio_rodal_key` | non-blank `(Cod_Predial, N_Rodal)` shared | 32 |
| `predio_code_name_anomaly` | minority pair vs majority code↔name mapping | 2 |
| `truncated_use_code_2026` | `CodUso_2026` ends in the observed `*` artifact | 8 |

The dead source column `N_Rodal_te` is exposed at snapshot level as
`n_rodal_te_non_blank_count` (0 in the observed snapshot) rather than as a
per-feature flag.

## Read projections

`app.forestry_reads` (service level; exposed over HTTP by
[Read API V1](read-api-v1.md) and visually by [Dashboard V1](dashboard-v1.md)):

- `list_shapefile_snapshots` — persisted snapshots in ingestion order;
- `snapshot_summary` — feature count, total geometry-derived area, total
  `Sup_ha`, validity counts, quality-flag counts, dead-column count, bbox;
- `predio_distribution` — source predio code/name pairs with counts and area
  sums (pairs, not canonical predios: the two anomaly rows appear as their
  own pairs);
- `use_distribution` — distribution of `uso_2024` or `uso_2026`;
- `use_field_comparison` — literal snapshot-internal differences
  `Uso2024 vs Uso2026` and `Cod_Uso vs CodUso_2026`.

**LIMITATION** — The comparison reports source-field differences only. The
observed snapshot yields exactly 1 class change and 72 detailed-code changes;
these are **not** labeled progress, approved changes, replant completions, or
any workflow transition, because individual code semantics remain partially
unconfirmed.

## Verification against the real source (RESULT)

On 2026-08-29 the real `001_DEGENFELD_2026.zip` was ingested read-only into
the disposable test database (transaction rolled back afterwards; source
untouched). Every check agreed with Source Evidence V1:

- 1,568 features; family fingerprint `19beaed5…60bd1`; ZIP SHA-256
  `d6d390b8…4385`; layer `Gdb_Degenfeld2026_mv`; SRID 32718;
- total geometry area 104,226,106.7 source units²; `Sup_ha` total 10,422.61;
  header bbox exact;
- 7 invalid geometries (OBJECTIDs 443, 757, 809, 823, 835, 860, 1011), with
  PostGIS `ST_IsValid` agreeing with the stored evidence on every feature and
  `ST_Area` equal to the stored area (max difference 0.0);
- duplicate pair OBJECTIDs 1547/1548; predio anomalies `PU2/Purretrun` and
  `FLM/Cancha Larga_HJ1_LT1`; 143 blank rodales; 32 duplicate-key holders;
  8 truncated codes;
- exactly 1 `Uso2024→Uso2026` change (OBJECTID 508, ENSAYO → PLANTACION) and
  72 `Cod_Uso→CodUso_2026` changes;
- re-ingestion idempotent.

## Still requires Javier / domain confirmation

Unchanged from the contract — see
[preguntas-campo-digital.md](es/preguntas-campo-digital.md): canonical
predio/rodal identity, the anomaly rows, use-code vocabulary, `Editada`
semantics, snapshot supersession, the management-plan-request workflow, and
geometry repair policy. None of these is modeled.

## Related documentation

[Forestry product](../README.md) ·
[Source Evidence V1](source-evidence-v1.md) ·
[Source Contract V1](source-contract-v1.md) ·
[Read API V1](read-api-v1.md) ·
[Product projection V1](product-projection-v1.md) ·
[Platform source ingestion](../../../docs/platform/source-ingestion.md)
