# Forestry Product Projection V1 (proposal)

## Status

Proposal derived from [Source Evidence V1](source-evidence-v1.md) and
Javier's written brief. No dashboard is implemented yet; this document
separates what the evidence already supports from what needs stakeholder
confirmation before it is built.

## Primary object and navigation

The evidence supports a two-level read-only navigation:

```text
Patrimonio (estate, 13 predios, 10,422.61 ha)
    -> Predio (code + name)
        -> Land-use polygon (1,568 features; rodal number where present)
```

"Land-use polygon" is deliberately neutral: whether Javier's operational
unit is the polygon, the rodal number, or something coarser is unconfirmed.

## SAFE TO BUILD NOW (supported directly by source evidence)

- Read-only map of the current snapshot with polygons colored by `Uso2026`,
  `DescUso`, or predio — the prior dashboard already proves this projection.
- Filters: predio, Uso2026, DescUso, CodUso_2026, N_Rodal (exactly the five
  filter dimensions of the existing dashboard).
- Factual KPIs per selection/predio/estate: feature count, total `Sup_ha`,
  mean/median/max area, class breakdown — all derivable arithmetic.
- A 2024 → 2026 change view: the 72 use-code changes and 1 class change are
  fully computable from the snapshot's own year-stamped columns.
- Data-quality panel: 143 blank rodal numbers, 13 duplicate
  `(predio, rodal)` keys, 2 predio code/name anomalies, 8 truncated codes,
  7 invalid geometries, 1 duplicate sliver — all established facts a user
  can act on.
- Snapshot provenance display: family fingerprint, member hashes, observed
  date, source path (platform provenance foundation already persists these
  concepts).
- Excel export of the filtered attribute table (Javier explicitly asked for
  Excel output; column set = the source fields).

## REQUIRES JAVIER / DOMAIN CONFIRMATION (do not build yet)

- **Any editing**, including the *solicitudes de planes de manejo* request
  flow: Javier sketched the idea, but request content, states, approvers, and
  lifecycle are entirely undefined.
- Treating `N_Rodal` as an identifier or navigation key (blank on 9%,
  duplicated within predios).
- Any "current vs superseded snapshot" logic: only one snapshot has been
  supplied; supersession rules are unknown.
- Interpreting use codes as structured species/year data (strong inference,
  but the vocabulary must be confirmed before it drives filters or reports).
- Any harvest/operation semantics: per platform product boundaries, harvests
  must not be modeled as booleans on rodals — no operation geometry exists in
  this source at all.
- Per-rodal print/map generation at fixed scales (requested in the brief, but
  needs page-format, scale, and content decisions).
- German-language or owner-facing views (owners are in Germany; language and
  access expectations unconfirmed).
- Cross-year history beyond 2024/2026: earlier snapshots exist per the
  lineage but were not supplied.

## Recommended implementation order (after stakeholder answers)

1. Platform ingestion of the validated snapshot into PostGIS (declared CRS,
   geometry as-is plus validity flags).
2. Read-only API projection (estate → predio → polygon + KPIs + change view).
3. Dashboard replacing the standalone HTML, reusing its proven UX as the
   starting requirement.
4. Only then: the request-creation workflow, once semantics are confirmed.
