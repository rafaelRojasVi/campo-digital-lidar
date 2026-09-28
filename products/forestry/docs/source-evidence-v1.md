# Forestry Source Evidence V1

## Status

Evidence record for the first real Forestry source snapshot, reviewed
2026-08-29. This document is the forensic basis for
[Source Contract V1](source-contract-v1.md).

All inspection was read-only. No external source file was modified, moved, or
committed. This record intentionally includes estate/predio names and
aggregate statistics because they are required to reason about identity and
data quality; it does not reproduce per-feature records or coordinate dumps.

## Method

- Recursive read-only inventory of
  `$CAMPO_DIGITAL_SOURCE_ROOT/01_Gestion_Predial_Forestal`.
- ZIP extracted to a session scratchpad outside the repository and outside the
  source root.
- Attribute/geometry profiling with `pyshp` 2.3.1 and `shapely` in an
  isolated interpreter (project dependencies untouched).
- Structural numbers independently reproduced by
  `forestry_ingestion.shapefile_contract` (pure stdlib) — both tools agree on
  every count reported here.
- The prior dashboard HTML was parsed and cross-checked against the shapefile.

## Source inventory

**FACT** — The Forestry source folder contains exactly three files (all other
subfolders — `01_Documentacion`, `03_Codigo_Fuente`, `04_Pruebas`,
`05_Resultados`, `06_Entregables`, `07_Respaldos` — are empty):

| Path (relative to `01_Gestion_Predial_Forestal/`) | Size | Modified |
|---|---|---|
| `02_Datos_Entrada/Idea.txt` | 818 B | 2026-08-26 |
| `02_Datos_Entrada/01_SAF_DEGENFELD/001_DEGENFELD_2026.zip` | 2,572,595 B | 2026-08-26 |
| `02_Datos_Entrada/01_SAF_DEGENFELD/dashboard_rodales_campodigital2.html` | 8,285,666 B | 2026-08-26 |

**FACT** — ZIP SHA-256:
`d6d390b8586aa8d198f6f14bed1e2e13a22ee5fcd749a7778baa50bbbad84385`.

**FACT** — Despite the source-catalog expectation of QGIS material, the
snapshot contains **no** `.qgz`/`.qgs` project, no GeoPackage, no raster, and
no Excel/CSV. The only spatial dataset is one ESRI shapefile family.

**FACT** — A name scan of the whole OneDrive hub found no other
Degenfeld/rodal/predial-named material outside this folder.

**OPEN QUESTION** — What the folder prefix `SAF` stands for.

### Stakeholder brief (`Idea.txt`)

**FACT** — `Idea.txt` is a written note from Javier describing intent:

- generate a shareable interactive HTML (single file or served) for the
  "base de datos del patrimonio Degenfeld";
- the owners are in Germany and should be able to view the geographic base;
- the important fields are: predio names, use descriptions, current use 2026
  and 2024 ("para saber que era antes"), area, and rodal code;
- users should be able to select and "edit" simply — **not overwrite**, but
  create *solicitudes de realización de planes de manejo* (management-plan
  requests);
- Excel export of the info plus a per-rodal graphic output at print scales
  (e.g. 1:10,000; formats A0/A1/A2/"circular").

This is direct stakeholder evidence of intended use, not yet a confirmed
workflow specification.

## Shapefile family `Gdb_Degenfeld2026_mv`

**FACT** — The ZIP contains exactly one complete shapefile family
(8 members, all dated 2026-08-26 12:17 inside the archive):

| Member | Size | SHA-256 |
|---|---|---|
| `.shp` | 5,275,172 B | `9e23c461ddc9993348efaa25f7c1ef4e604bf7fe281163681f91c3a44a4ffee7` |
| `.shx` | 12,644 B | `76b9a7cabcd6ac03bbce1d37f404392c95d09b527f5725a9844d72e3b7a1246a` |
| `.dbf` | 514,786 B | `64ab95116a38eb5f29adfdf5bfa76a25b936d65ab655baac2135a7aca7f107be` |
| `.prj` | 409 B | `5fe2418b950fed3d596d4092ed07b817045dfebd3c990a94cb555ebede91cd47` |
| `.cpg` | 5 B | `3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824` |
| `.sbn` | 14,972 B | `d61ffde0ef22e151b734526b8900d5202721310d2509c01472b6951fe8fb60f2` |
| `.sbx` | 428 B | `71bcb829707d709c247af90f0ffd6ac93a63adca61c8ad52b1f20bb319e8aed2` |
| `.shp.xml` | 83,967 B | `aee2ed46c3ededd67eeb63f66cd3607ce736b890ec7608e5078b65985265ea8d` |

Family fingerprint (canonical suffix:sha256 lines, sorted, hashed):
`19beaed51b5c1bc144c8d34d500a21d1e3a31b7a1dbdc674b96ac69225060bd1`.

### Declared CRS and encoding

- **FACT** — `.cpg` declares `UTF-8`.
- **FACT** — `.prj` declares ESRI WKT `WGS_1984_UTM_Zone_18S`
  (Transverse Mercator, central meridian −75°, false northing 10,000,000,
  linear unit metre).
- **FACT** — The embedded ArcGIS metadata declares reference system
  EPSG `32718` — but that metadata block describes the 2024 **parent** layer
  (see below), so it is supporting rather than primary evidence for this file.
- **INFERENCE** — Interpreting the header bounding box in the declared CRS
  places the estate at roughly 40.1°–40.8° S, 73.1°–73.6° W (southern Chile,
  Los Ríos region scale). This is a consistency check of the declaration, not
  an independent CRS determination.

### Geometry evidence

- **FACT** — Shape type 5 (Polygon), 1,568 features, no empty geometries;
  1,401 single-ring/simple polygons and 167 multi-part polygons when decoded.
- **FACT** — Header bounding box (source units, declared metres):
  X 617,298.09 – 662,027.94; Y 5,484,858.70 – 5,555,261.33
  (≈ 44.7 km × 70.4 km envelope).
- **FACT** — 7 features fail OGC validity with ring self-intersections
  (OBJECTIDs 443, 757, 809, 823, 835, 860, 1011).
- **FACT** — Exactly one duplicate-geometry pair exists: OBJECTIDs 1547/1548
  (predio Purretrun) share identical geometry of ≈0.16 m² but carry different
  land-use attributes (`Ve PLT`/VEGA vs `BN`/BOSQUE NATIVO). This is
  consistent with a Union sliver artifact.
- **FACT** — Total geometric area equals 104,226,106.7 source-units² and the
  `Sup_ha` column sums to 10,422.61; for **every** feature
  `Shape_Area / Sup_ha = 10,000` exactly. `Sup_ha` is therefore derived from
  this exact geometry (hectares under the declared metre unit), not an
  independently surveyed area.

### DBF schema

**FACT** — 14 fields (DBF truncates names to 10 characters):

| DBF name | Type | Width.Dec | Lineage name | Notes |
|---|---|---|---|---|
| `OBJECTID` | N | 10 | — | unique in this snapshot (1..1568 range) |
| `Nom_Predio` | C | 50 | — | 13 distinct values, never blank |
| `N_Rodal` | C | 10 | — | 143 blank; numeric strings 0–1300 |
| `Sup_ha` | F | 19.11 | — | = Shape_Area / 10,000 exactly |
| `Cod_Uso` | C | 25 | — | 207 distinct; 2024-state use code |
| `Editada` | C | 2 | — | `mv` 715, `si` 408, `MV` 4, blank 441 |
| `Uso2024` | C | 50 | — | 28 distinct macro classes, never blank |
| `DescUso` | C | 50 | — | 42 distinct (case/typo variants), 56 blank |
| `Cod_Predia` | C | 10 | `Cod_Predial` | 13 distinct codes, never blank |
| `N_Rodal_te` | C | 3 | — | **entirely blank** (dead field) |
| `Uso2026` | C | 50 | — | 28 distinct macro classes, never blank |
| `CodUso_202` | C | 10 | `CodUso_2026` | 208 distinct; 2026-state use code |
| `Shape_Leng` | F | 19.11 | — | perimeter in source units |
| `Shape_Area` | F | 19.11 | — | area in source units² |

**STRONG INFERENCE** — `Cod_Predia` and `CodUso_202` are 10-character
truncations of `Cod_Predial` and `CodUso_2026`: the embedded lineage records
`CalculateField` operations on exactly those longer names for the same layer
chain.

**FACT** — Width truncation caused data loss: 8 features whose 25-char
`Cod_Uso` value is `RaCoRo01Pi Rn` carry `RaCoRo01P*` in the 10-char
`CodUso_202` field.

## Embedded lineage (`.shp.xml`)

**FACT** — The ArcGIS metadata (ArcGIS 10.0 → 10.8) contains 268 recorded
geoprocessing steps spanning 2012–2026: 261 `CalculateField`, 5
`FeatureClassToFeatureClass`, 2 `Union`. Campaign years: 2012 (14), 2017 (9),
2018 (75), 2019 (4), 2022 (12), 2023 (1), 2024 (140), 2026 (13).

**FACT** — Layer genealogy recorded in the lineage:

```text
BaseUsos2012.shp  (K:\Degenfeld\Actualizacion2012)
    -> GDB_degenfeld2012.gdb : Base2012Compilada / GDB_Degenfel2012_compilada
    -> GDB_Degenfeld2012_enActualizacion (2017)
    -> GDB_Degenfeld2017_23Nov17 / UsoSuelo2017 (2017-2018, edits to 2022)
    -> GDB_Degendeld2023.gdb\Patrimonio : USO_Predial2023 (2023)
    -> Union(UTILI_PURRETRUN, BASE_Uso_Predial_2023) -> BASE2024.shp
       (2024-04-02, in a folder named 0_DRONE_img)
    -> GDB_Degenfeld2024.gdb\USOS_SUELO : Gdb_Degenfeld2024
    -> Union(Gdb_Degenfeld2024, util) -> Gdb_Degenfeld2024_Intersect_
       (2024-04-05, in C:\Users\jguer\OneDrive\...\Default.gdb)
    -> Gdb_Degenfeld2024_vf (2024-04-08, edits through 2026-05-28)
    -> Gdb_Degenfeld2026_mv (2026-05-28)
```

**FACT** — The 2026 update steps (2026-05-28) were:
`Uso2026 = [Uso2024]` (copy), `CodUso_2026 = [Cod_Uso]` (copy), then selective
overwrites of `CodUso_2026` to `Pi25`/`Pi26`/`En26`/`Po25` with matching
`DescUso` updates, and `Editada = "mv"` on selected features.

**FACT** — The 2012 schema (OBJECTID, USO, NPOLGRAL, SECCION, SUP, RODAL,
DESCUSO, AÑOPLANT, ESQUEMAN, DENS_INICI, ESPECIE_NC, MIN_TIPO_F, MIN_SUBTIP,
EST_DESARR, CODIGO, COBERTURA, PREDIO) was much richer than the current
export; plantation year (`AÑOPLANT`), species, density, and management-scheme
fields no longer exist as dedicated columns.

**FACT** — In 2017 `N_Rodal` was calculated as `[NPOLGRAL]` — the rodal
number originates from a general-polygon numbering field.

**FACT** — The metadata identity block (`itemName`, attribute catalog,
EPSG 32718, sync date 2024-04-05) still describes
`Gdb_Degenfeld2024_Intersect_` from `GDB_Degenfeld2024.gdb`; it was not
re-synchronized for the 2026 layer. Metadata blocks in this source are
carried forward and can lag the actual data.

**HYPOTHESIS** — `_vf` = "versión final" and `_mv`/`Editada='mv'` are
editor initials or an edit-marker; `Editada='si'` marks features edited in an
earlier (2024) campaign. Unverified.

## Attribute evidence

### Predios

**FACT** — 13 predio codes and 13 predio names, in a 1:1 mapping except two
single-feature anomalies:

| Code | Name | Features | Sup_ha | Blank N_Rodal |
|---|---|---|---|---|
| HT | Hacienda Trinidad | 1,163 | 9,602.16 | 89 |
| SS | San Sebastian | 116 | 300.24 | 6 |
| VH | Vista Hermosa | 62 | 108.38 | 2 |
| MLL | Millantue | 27 | 80.38 | 0 |
| LUM | Lumaco | 36 | 68.89 | 0 |
| CB | Cumbres Borrascosas | 19 | 58.14 | 0 |
| FCL | Fundo Cancha Larga | 13 | 45.32 | 0 |
| PU1 | Purretrun | 34 | 42.92 | 18 |
| FLM | Fundo Las Malvinas | 34 | 36.29 | 1 |
| LP | Los Panchos | 16 | 30.06 | 0 |
| CL | Cancha Larga_HJ1_LT1 | 7 | 18.97 | 0 |
| BR | Buen Retiro | 4 | 17.00 | 0 |
| PU2 | Purretrun2 | 35 | 13.49 | 27 |

**FACT** — Anomalies: one feature named `Purretrun` carries code `PU2`
(0.34 ha), and one feature named `Cancha Larga_HJ1_LT1` carries code `FLM`
(0.03 ha). Either the code or the name is wrong on those rows.

**FACT** — The 2012 lineage used predio code `PUe` and a single `Purretrun`;
`PU1`/`PU2` appear from 2024. The estate total is 10,422.61 ha, dominated by
Hacienda Trinidad (92% of area).

### Rodal numbers

- **FACT** — `N_Rodal` is blank on 143 features (9%), concentrated in HT,
  PU1, PU2.
- **FACT** — `(Cod_Predial, N_Rodal)` is **not unique**: 13 duplicated keys,
  including `LUM/'0'` ×7 and `HT/'856'` ×3; 1,425 non-blank rows produce
  1,406 distinct keys.
- **LIMITATION** — No source field, alone or combined, is a proven stable
  feature identity. `OBJECTID` is unique in this snapshot but ArcGIS
  regenerates OBJECTIDs on export; cross-snapshot stability is unproven.

### Land-use fields

- **FACT** — `Uso2024` and `Uso2026` share the same 28-value macro
  vocabulary (PLANTACION 833, BOSQUE NATIVO 336, VEGETACION NATIVA 94,
  AREA NO PRODUCTIVA 80, PLANTACION NATIVA 75, VEGA 34, FAJA DE CAMINO 29,
  …), and differ on exactly **one** feature: OBJECTID 508 (HT, rodal 606)
  changed ENSAYO → PLANTACION.
- **FACT** — `Cod_Uso` (2024 state) and `CodUso_2026` differ on **72**
  features; 858 of 1,568 `Cod_Uso` values match the pattern
  `<letters><2-digit year>` (e.g. `Pi06`, `En11`, `Eg03`, `Po99`).
- **STRONG INFERENCE** — In that pattern the letter prefix encodes the
  planted species and the digits the plantation year: `Pi` co-occurs with
  DescUso "Plantacion de P. radiata" on 385/388 rows, `Po` with P. oregon on
  104/104, `En` with E. nitens, `Eg` with E. globulus; year suffixes span
  73–99 and 00–26. The 72 changed codes read as replant events
  (e.g. `En11` → `Pi26`: an E. nitens 2011 stand replanted with P. radiata
  2026), and the mismatched DescUso rows are exactly those replants.
- **HYPOTHESIS** — Non-pattern codes are land-class abbreviations
  (`BN` bosque nativo, `VN` vegetación nativa, `Prot` protección, `FJC` faja
  de camino, `Ve` vega, `Mat` matorral, `PLT` plantable, `ANP` área no
  productiva, `Adm` administración, `ZHU` zona húmeda, `FE` faja eléctrica,
  `CCV` cortina cortaviento, …) and suffixes `Rn`/`Rzg`/`??` mean
  regeneración natural / rezago / unknown year. Plausible from co-occurrence
  but unconfirmed vocabulary.
- **FACT** — `DescUso` contains manual-maintenance variants
  (`Boque nativo`, `Varias especies` vs `Varias Especies`, `AROMO`), and 56
  blanks.
- **FACT** — `Editada` does not reliably flag the 2026 changes: of the 72
  features whose use code or class changed, 58 are `mv`, 5 `si`, 9 blank —
  while 661 `mv` features show no attribute change (geometry edits cannot be
  ruled out from attributes alone).

## Prior dashboard evidence

**FACT** — `dashboard_rodales_campodigital2.html` is a self-contained
Spanish-language Leaflet page titled "Gestión Forestal | Campo Digital" /
"Gestión territorial de rodales". It embeds
`const DATA = {"type":"FeatureCollection","name":"Gdb_Degenfeld2026_mv",…}`
with exactly 1,568 features whose properties are
`predio, nrodal, tipo (=Uso2026), descripcion (=DescUso),
codigo (=CodUso_2026), area_ha (=Sup_ha)` plus generated `_key`/`_order`;
predio censuses and the 10,422.61 ha total match the shapefile exactly, and
the 8 truncated `*` codes are present. Coordinates are reprojected to
lon/lat.

**FACT** — Its UI provides: filters for predio, uso 2026, descripción,
código 2026, and rodal; selection with count/area/mean/median/max statistics;
charts by dimension; a table (Predio, Rodal, Uso 2026, Código, ha); metric and
imperial units; Excel export; shapefile-ZIP export; and a print/graphic view.

**STRONG INFERENCE** — The dashboard is a derived projection of this exact
snapshot (same layer name, count, totals, truncation artifacts). The `2` in
`campodigital2` suggests at least one earlier generation, which is not present
in the source folder.

## What was NOT established

- Stable cross-snapshot feature identity (see LIMITATION above).
- Semantics of `Editada` values and of the `_mv`/`_vf` layer suffixes.
- The authoritative meaning of rodal: `N_Rodal` descends from a
  general-polygon number (`NPOLGRAL`), is blank on 9% of features, and is not
  unique — whether Javier treats "rodal" as these polygons, as the number, or
  as something coarser is unknown.
- The full use-code vocabulary and the meaning of `??`, `Rn`, `Rzg`,
  compound codes (`Po99Eg97`), and `ES`.
- Whether geometry was edited in the 2026 campaign.
- Where the historical snapshots (2012–2024 layers named in the lineage)
  live and whether they will be supplied.
- Any workflow/approval semantics for the *solicitudes de planes de manejo*
  Javier described.

Questions for Javier are maintained in
[preguntas-campo-digital.md](es/preguntas-campo-digital.md).

## Related documentation

[Forestry product](../README.md) ·
[Source Contract V1](source-contract-v1.md) ·
[Product projection V1](product-projection-v1.md) ·
[Platform source ingestion](../../../docs/platform/source-ingestion.md)
