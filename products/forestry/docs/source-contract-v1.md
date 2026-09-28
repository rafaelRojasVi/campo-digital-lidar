# Forestry Source Contract V1

## Status

Evidence-backed source contract, implemented in
`forestry_ingestion.shapefile_contract`.

The contract covers **structure only**: what a Forestry estate shapefile
snapshot must look like to be accepted for ingestion. It deliberately defines
no workflow states, no approval semantics, and no canonical business
entities. The evidence behind every rule is in
[source-evidence-v1.md](source-evidence-v1.md).

## Accepted source form

One ESRI shapefile family (the observed source arrives as a ZIP containing
one family; ZIP handling is a platform ingestion concern, the contract
validates the extracted family).

Required members: `.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`.

- `.prj` is required because CRS must be declared, never inferred from
  coordinates.
- `.cpg` is required because the DBF text encoding must be declared, never
  guessed. The observed source declares `UTF-8`; only UTF-8 is accepted in V1.

Optional members preserved and fingerprinted when present: `.sbn`, `.sbx`,
`.shp.xml` (the observed `.shp.xml` carries the 2012–2026 lineage and must
never be discarded).

## Declared CRS handling

The `.prj` content must equal (whitespace-trimmed) the established ESRI WKT
for `WGS_1984_UTM_Zone_18S` recorded in the code as `EXPECTED_PRJ_WKT`.

A different declaration is a **contract change requiring review**, not a data
change: silently accepting a CRS change would corrupt every derived area and
map. The contract does not attempt to interpret or convert coordinates.

## Schema expectations

The DBF schema must match the 14 established fields exactly — name, type,
width, and decimal count, in order (`EXPECTED_DBF_SCHEMA`). A renamed,
removed, reordered, or resized field fails validation for review.

Rationale: field width is part of the contract because width truncation has
already caused observable data loss in the source (`RaCoRo01Pi Rn` →
`RaCoRo01P*` in the 10-character `CodUso_202`).

Row projection restores lineage field names for the two truncated columns
(`cod_predial`, `cod_uso_2026`) and blank-normalizes values to `None`.

## Geometry expectations

- The `.shp` shape type must be Polygon (type 5).
- `.shp` and `.shx` headers must be internally consistent (magic, version,
  declared length vs actual size).
- The `.shx` record count must equal the DBF record count.
- The bounding box is read from the header and preserved as evidence.

V1 does **not** decode per-feature geometry. Known geometry issues in the
observed snapshot (7 ring self-intersections, 1 duplicate sliver pair) are
recorded as evidence; geometry-level validation policy belongs to the PostGIS
ingestion slice, where real geometry decoding and repair decisions can be
made deliberately.

## Identity

- `OBJECTID` must parse as an integer; it is unique within the observed
  snapshot but is treated as **per-snapshot ordering only**. No cross-snapshot
  stable feature identity is defined by this contract.
- `(Cod_Predial, N_Rodal)` is explicitly **not** an identity: the observed
  source contains blank and duplicated rodal numbers.
- No canonical predio or rodal primary key is defined until stakeholder
  confirmation.

## Provenance and fingerprinting

Every member file gets a SHA-256 digest. The family fingerprint is the
SHA-256 of the sorted `suffix:digest` lines — deterministic, order-independent,
and sensitive to any member change. This aligns with the platform's immutable
snapshot model (`docs/platform/source-ingestion.md`); the shared provenance
infrastructure owns observation timestamps and history.

## Rejection conditions

Validation fails (for review, never partial ingestion) when:

- the `.shp` path does not exist, or a required member is missing;
- the `.cpg` declaration is not UTF-8;
- the `.prj` text differs from the established declaration;
- a `.shp`/`.shx` header is malformed or its declared length disagrees with
  the file size;
- the shape type is not Polygon;
- the DBF schema differs from the established 14 fields;
- DBF and SHX record counts disagree;
- a DBF record is soft-deleted (deleted rows would silently vanish in GIS
  tools; they require review);
- a numeric field value does not parse;
- the family contains zero features.

## Not yet established

The following are outside this contract until stakeholder or stronger source
evidence exists:

- canonical predio identity and the two code/name anomaly rows;
- canonical rodal identity and the meaning of blank/duplicate rodal numbers;
- the use-code vocabulary (`BN`, `Prot`, `Rn`, `Rzg`, `??`, compound codes);
- `Editada` semantics;
- snapshot-supersession rules (which layer name/date is "current");
- any management-plan-request workflow;
- geometry validity/repair policy.
