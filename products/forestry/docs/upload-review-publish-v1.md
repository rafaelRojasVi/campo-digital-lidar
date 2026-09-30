# Rodales upload, review, publish and restore V1

## Status

Implemented 2026-09-30 on branch `feat/rodales-upload-review-publish` (from
`main` at `f1b3ebb`, which includes [Rodales hosted release V1](hosted-release-v1.md)).
**Not merged, not deployed, and no Rodales version was published on any
hosted system.** Migration `0010` is part of this change.

## What it does

An operator or admin of Rodales can, from the dashboard:

1. **Cargar versión**: upload one shapefile ZIP. It becomes a version
   *pending review*. Uploading never changes what the map shows.
2. **Revisión**: see where the version came from (file, uploader, date,
   size, layer, CRS, content fingerprint), its polygon count and areas, its
   invalid geometries and quality flags, and what changed from the published
   version. They can open it on the map as a private preview.
3. **Publicar**: after an explicit acknowledgement (when there are invalid
   geometries or uncertain matches) and a confirmation dialog, make it the
   version every Rodales user sees.
4. **Versiones**: see every version, its source and uploader, the audited
   trail of publications, and **Restaurar** any previously published
   version (the same review page and confirmation).

Viewers see the published map, the version list (published and previously
published versions only) and the trail. They cannot see pending uploads.

## Data model (migration `0010`, expand-only)

| Table | Purpose |
|---|---|
| `forestry.publication_state` | Singleton (`CHECK id = 1`): `published_snapshot_id`, the version the map serves. NULL means nothing is published. |
| `forestry.publication_event` | Append-only: one row per activation. `publish` (a never-published version), `restore` (a previously published one), `initial` (carried over by the migration or published by the controlled CLI import). `publish`/`restore` always have an actor; `initial` never does (a CHECK enforces both). Records `previous_snapshot_id`. |
| `forestry.snapshot_upload` | One row per accepted dashboard upload: uploader, original filename, byte size, SHA-256 of the ZIP, and the platform `source_snapshot` whose `object_storage_key` points at the stored ZIP. Uploading identical content twice records two uploads of one version. |

**Backfill (DECISION):** if any Forestry snapshot exists when `0010` runs, the
most recently ingested one becomes published with an `initial` event. That
is exactly what the previous release showed (it served the latest ingested
snapshot), so deploying changes nothing a viewer sees. Verified against a
database holding two snapshots: the newer one was published, one `initial`
event with no actor. On an empty database nothing is published.

A version's status is derived from the trail, never stored:
`published` (the current one), `previously_published` (in the trail but not
current) or `pending` (never published).

## Upload (`POST /api/forestry/uploads`)

Session + `forestry` grant with `Action.UPLOAD` (operator, admin) + CSRF
token + same-origin `Origin`, like every Transelec mutation.

Limits and archive rules (`forestry_ingestion.upload_archive`), calibrated on
the observed Degenfeld 2026 ZIP (2.6 MB zipped, 8 members, 5.9 MB
uncompressed, highest member compression ratio 12.5):

| Check | Rule |
|---|---|
| Body before reading | `RequestBodyLimitMiddleware`: anonymous or forged sessions get `401` before any body is read; a declared body over 50 MiB + 1 MiB framing gets `413`. |
| Upload size | 50 MiB, counted while streaming (`413`). |
| Filename | Must end in `.zip`; kept only as display data (last path part, printable, 200 chars). |
| Entries | At most 16. |
| Names | No absolute paths, drive letters, backslashes, `..`, `.`, empty parts, NUL, or more than one folder level. Symbolic links, encrypted members and compression other than stored/deflate are refused. |
| Members | Exactly one layer: `.shp .shx .dbf .prj .cpg` (required), `.sbn .sbx .shp.xml` (optional), same base name, all at the ZIP root or all in one folder. Anything else (a second layer, `__MACOSX/`, a `.txt`) refuses the upload instead of being skipped. |
| Expansion | Declared total ≤ 256 MiB; members of 1 MiB or more with ratio > 100 are refused before extraction; extraction counts real bytes and stops at the declared size. |
| Extraction | Member names are never used as paths: members are written as `family<suffix>` in a temporary directory. |

Then Source Contract V1 applies unchanged (UTF-8 `.cpg`, the exact
`WGS_1984_UTM_Zone_18S` `.prj`, the 14-column DBF schema, polygon shapes, no
null shapes, no soft-deleted records, aligned record counts). A refusal
answers `422` with a stable `reason` and a Spanish message built only from
structure (suffixes, record numbers, column names), never from a cell value.
Every refusal is audited as `forestry.snapshot.upload_rejected`.

Only after everything validates is the ZIP stored in the object store (the
existing Railway volume, `CAMPO_OBJECT_STORE_ROOT=/data/object-store`, which
production already requires to be a real mount), and the provenance,
snapshot, features and upload record written in one transaction, audited as
`forestry.snapshot.uploaded`. A refused upload leaves no row and no stored
object (tested).

Identical layer content (same family fingerprint) resolves to the existing
version (`status: already_uploaded`) and adds only an upload record. The
same content under a different layer name answers `409`.

## Comparison with the published version (DECISION)

`app.forestry_comparison`, computed on demand for the review and again at
publish time.

- **No source field is used as an identity.** OBJECTID is export-assigned;
  `(Cod_Predial, N_Rodal)` is blank 143 times and duplicated 32 times in the
  one observed snapshot (Source Evidence V1). They are shown next to each
  match as evidence only, and a renumbered OBJECTID is reported as a changed
  field.
- **Certain match:** a feature whose stored geometry is byte-identical to
  exactly one feature on the other side. Attribute differences are listed
  field by field (`same_geometry`).
- **Everything else is grouped by overlap.** A published and a pending
  feature are linked when their intersection is at least **5 %** of the
  smaller one's area (`LINK_OVERLAP_RATIO`; shared borders overlap by ~0).
  Connected groups become `geometry_changed` (1 published : 1 pending, a
  *probable* correspondence), `uncertain` (any other mix: a redraw, split,
  merge or neighbours; the code does not decide which), `added` or
  `removed`. The reviewer sees every overlap ratio.
- **Nothing is inferred as a cut.** No label, field or message says a rodal
  was cut, harvested or replaced; a test asserts the review payload contains
  neither "cut" nor "cort".
- Invalid geometries are compared through `ST_MakeValid` copies made in the
  query; stored geometry is never modified. If PostGIS still fails, the
  comparison is reported unavailable and publishing requires the
  acknowledgement.

**Publishing requires `acknowledge_review: true`** when the version has
invalid geometries, any `geometry_changed`/`uncertain` group, or no
comparison could be computed; otherwise `409`. The real Degenfeld layer has
7 invalid geometries, so publishing it always asks for the acknowledgement.

## Publish and restore (DECISION)

`POST /api/forestry/snapshots/{id}/publish` and `/restore`: `Action.PUBLISH`
(operator, admin, as in Transelec) + CSRF. One transaction locks the state
row, so concurrent activations serialize. The caller sends
`expected_published_snapshot_id`, the published version its review was
computed against; if it changed since, the activation is refused (`409`,
"La versión publicada cambió mientras usted revisaba"). `publish` accepts
only a never-published version, `restore` only a previously published one.
Audit events: `forestry.snapshot.published`, `forestry.snapshot.restored`,
and `forestry.snapshot.publish_refused` for every refusal.

## Read API changes

- `GET /snapshots/latest-ingested` is **removed**; `GET /snapshots/published`
  replaces it (`404` when nothing is published). The newest ingested
  snapshot is no longer "the" map.
- A pending version answers `404` to a viewer on every snapshot route, and
  is left out of `GET /snapshots` for viewers.
- New: `GET /versions` (any role; pending versions only for uploaders) and
  `GET /snapshots/{id}/review` (`Action.UPLOAD`).

## Dashboard

`/rodales/` (map, published version; `?version=N` shows a labelled private
preview), `/rodales/versiones`, `/rodales/importar`, `/rodales/revision?version=N`.
Every page path is in `RODALES_SPA_PAGE_PATHS`, pinned to the frontend
`ROUTES` by `test_dashboard_static.py`, so direct reloads and shared links
work. Uploader-only links are hidden from viewers; the API enforces it.

## Controlled CLI import

`scripts/forestry_snapshot_import.py` now publishes the imported snapshot as
`initial` **only when nothing is published** (same transaction; the dry run
reports it and rolls back). With something already published it publishes
nothing.

## Verification (RESULT, 2026-09-30, local only)

- Python: 934 unit/product tests, 395 integration tests against an isolated
  PostGIS 17-3.5 container, `migration_check.py` (upgrade, downgrade,
  upgrade), ruff, ruff format, mypy (263 files).
- Frontend: 109 vitest tests, tsc, oxlint, production build.
- `test_forestry_workflow.py` (synthetic PostGIS data, real sessions, CSRF,
  object store): upload → review → publish → upload → review (renumbered
  OBJECTID, changed attribute, redrawn invalid geometry, one square split in
  two, one removed, one added) → refused publish without acknowledgement →
  refused stale publish → publish → restore → re-upload recognised;
  viewers never see the pending version; viewer, Transelec-only and
  no-grant accounts get `403` on every mutation and on the review;
  anonymous `401`; missing CSRF token or foreign `Origin` `403`; seven
  malformed ZIPs (not a ZIP, truncated, `../` member, missing `.prj`,
  compression bomb, other CRS, null geometry) each `422` with no rows, no
  stored object and one rejection audit; oversize `413`.
- Browser (Chromium, the built dashboard served by the API with
  `APP_ENV=development` against the isolated database, synthetic ZIPs): the
  whole flow as a dev operator, direct reloads of Versiones and Revisión,
  the map preview banner, a Transelec-only account gets "Sin acceso a
  Rodales", 0 console errors, no horizontal scroll at 390 px.
- **Degenfeld source, privately:** the pinned ZIP (SHA-256 `d6d390b8…`,
  read-only from `CAMPO_DIGITAL_SOURCE_ROOT`, never committed) uploaded
  through `POST /api/forestry/uploads` into the isolated local database was
  accepted: 1,568 polygons, 10,422.61 ha, EPSG:32718, 7 invalid geometries,
  quality flags 143/32/8/7/2/2 (the documented numbers), status pending,
  nothing published. Upload 0.6 s; review 0.02 s. Compared with itself:
  1,566 unchanged and 1 uncertain group (the known duplicate-geometry pair,
  correctly not paired with certainty) in 0.14 s. The rows and the stored
  copy were deleted afterwards.

## LIMITATIONS

- Worst case: when **every** geometry differs from the published version
  (e.g. a re-export that moves every vertex), the overlap step intersects
  every candidate pair. Measured on the Degenfeld layer against itself with
  every feature forced into it: 9.7 s locally, and it runs again at publish.
- The 5 % link threshold is triage, not a rule: a small redrawn edge that
  overlaps a neighbour by more than 5 % of the smaller polygon joins them
  into one uncertain group (see the browser test, where a shifted rodal and
  a split one form one group). Nothing is hidden; the group is larger.
- The contract is still the Degenfeld 2026 contract: a layer with another
  CRS, other columns, or null/deleted records is refused with the reason,
  not adapted.
- The original ZIP is kept on the volume, but there is no download button
  yet. No backups exist on the current Railway plan (accepted 2026-09-28):
  losing the volume loses stored ZIPs; losing the database loses versions,
  trail and audit.
- Pending versions are never deleted; a discard action does not exist yet.
- Response compression is still absent (the feature collection is ~9 MB).

## Deployment (Rafael, manual; do not merge or deploy without deciding to)

1. Review and merge the PR into `main`. Railway deploys `main` manually.
2. The Railway **pre-deploy command** (`alembic upgrade head`, configured
   in the Railway UI, not in `railway.json`) runs `0010`. Confirm it is still
   set before deploying.
3. Confirm `CAMPO_OBJECT_STORE_ROOT=/data/object-store` on the app service
   (it is already required for Transelec uploads; `/ready` fails without a
   writable mounted store).
4. Deploy. Then check from outside:

   ```sh
   BASE=https://campo-digital-platform-production.up.railway.app
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/api/forestry/snapshots/published  # 401
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/api/forestry/versions             # 401
   curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/api/forestry/uploads      # 401
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/rodales/versiones                 # 200
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/transelec/                        # 200
   curl -s -o /dev/null -w '%{http_code}\n' $BASE/ready                             # 200
   ```

5. Signed in as the Rodales admin, open `/rodales/versiones`:
   - if the Degenfeld snapshot had been imported before the deploy, it shows
     as version N.º 1 (or its id), **Publicada**, with a "Versión inicial"
     event, and the map is unchanged;
   - if it had not (this repository cannot tell; confirm in the database or
     the UI), the map says "Sin versión publicada". Then either upload the
     ZIP from **Cargar versión**, review it and **Publicar** (Rafael approved
     uploading the Degenfeld data to Railway on 2026-09-28), or run the CLI
     import from the hosted release runbook, which now publishes it as the
     initial version.
6. Transelec is untouched by this change; spot-check `/transelec/` and its
   sign-in.

### Rollback

- **Code:** redeploy `f1b3ebb`. It ignores the new tables, but it shows the
  *latest ingested* snapshot: if a version was uploaded after this deploy,
  that newest upload becomes visible even if it was never published. Before
  rolling back after an upload, decide whether that is acceptable.
- **Schema:** `alembic downgrade 0009` drops the three new tables (the
  trail and upload records are lost; snapshots, features, stored ZIPs and
  audit events stay).

## OPEN QUESTIONS

Operational cuts (cortes) are deliberately **not** implemented here, and no
cut is ever inferred from a change between versions. Before designing them
we need, from Javier (Spanish version in
[Preguntas para Javier](es/preguntas-campo-digital.md), section 6):

- Full versus partial cuts: is a cut always a whole rodal, or a part of one
  (and then, drawn how)?
- Dates: which dates matter (planned, started, finished, reported) and
  which one is authoritative?
- Evidence: what proves a cut happened (a field report, a photo, a new
  shapefile, an invoice) and does the platform have to keep it?
- Approval: who records a cut and who approves it, if anyone?
- Linking across source versions: when a new shapefile arrives, how is a
  recorded cut attached to the right rodal, given that OBJECTID and the
  rodal code are not stable? Should the person publishing confirm the
  links?

Also still open from the hosted release: the first Rodales admin, and Esri
World Imagery terms.

## Related documentation

[Forestry product](../README.md) ·
[Rodales hosted release V1](hosted-release-v1.md) ·
[Read API V1](read-api-v1.md) ·
[Source Contract V1](source-contract-v1.md) ·
[Resumen en español](es/carga-y-publicacion.md)
