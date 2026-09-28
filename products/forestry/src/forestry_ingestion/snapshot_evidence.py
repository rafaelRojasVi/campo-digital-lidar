"""Snapshot-local data-quality evidence established by Source Evidence V1.

Every flag reproduces an anomaly class already observed and documented in the
first real source snapshot. Flags are machine-readable evidence about the
source data — they are deliberately not workflow states or business statuses,
and none of them implies that a feature should be repaired or excluded.

All rules are snapshot-local: they compare features only within the snapshot
being ingested, because no cross-snapshot identity has been established.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from forestry_ingestion.shapefile_contract import ForestryShapefileError, SourceFeatureRow
from forestry_ingestion.shapefile_geometry import SourceFeatureGeometry

# Feature fails OGC validity (evidence: 7 ring self-intersections observed).
FLAG_INVALID_GEOMETRY = "invalid_geometry"

# Byte-identical geometry shared with another feature in the same snapshot
# (evidence: one duplicate sliver pair observed).
FLAG_DUPLICATE_GEOMETRY = "duplicate_geometry"

# N_Rodal is blank (evidence: 143 blank values observed).
FLAG_BLANK_RODAL = "blank_rodal"

# Non-blank (Cod_Predial, N_Rodal) shared by several features
# (evidence: 13 duplicated keys observed).
FLAG_DUPLICATE_PREDIO_RODAL_KEY = "duplicate_predio_rodal_key"

# (Cod_Predial, Nom_Predio) pair is a minority against the snapshot's majority
# code<->name mapping (evidence: two single-feature anomalies observed).
FLAG_PREDIO_CODE_NAME_ANOMALY = "predio_code_name_anomaly"

# CodUso_2026 carries the observed DBF width-truncation artifact, a value
# ending in '*' (evidence: 8 truncated codes observed).
FLAG_TRUNCATED_USE_CODE_2026 = "truncated_use_code_2026"


def compute_quality_flags(
    rows: Sequence[SourceFeatureRow],
    geometries: Sequence[SourceFeatureGeometry],
) -> dict[int, tuple[str, ...]]:
    """Return sorted quality flags per record number for one snapshot."""

    if [row.record_number for row in rows] != [geometry.record_number for geometry in geometries]:
        raise ForestryShapefileError(
            "Attribute rows and geometries do not describe the same records"
        )

    geometry_counts = Counter(geometry.wkb for geometry in geometries)

    predio_rodal_counts = Counter(
        (row.cod_predial, row.n_rodal)
        for row in rows
        if row.cod_predial is not None and row.n_rodal is not None
    )

    pair_counts = Counter(
        (row.cod_predial, row.nom_predio)
        for row in rows
        if row.cod_predial is not None and row.nom_predio is not None
    )
    max_count_by_code: Counter[str] = Counter()
    max_count_by_name: Counter[str] = Counter()

    for (code, name), count in pair_counts.items():
        max_count_by_code[code] = max(max_count_by_code[code], count)
        max_count_by_name[name] = max(max_count_by_name[name], count)

    flags: dict[int, tuple[str, ...]] = {}

    for row, geometry in zip(rows, geometries, strict=True):
        feature_flags: list[str] = []

        if not geometry.is_valid:
            feature_flags.append(FLAG_INVALID_GEOMETRY)

        if geometry_counts[geometry.wkb] > 1:
            feature_flags.append(FLAG_DUPLICATE_GEOMETRY)

        if row.n_rodal is None:
            feature_flags.append(FLAG_BLANK_RODAL)
        elif (
            row.cod_predial is not None and predio_rodal_counts[(row.cod_predial, row.n_rodal)] > 1
        ):
            feature_flags.append(FLAG_DUPLICATE_PREDIO_RODAL_KEY)

        if row.cod_predial is not None and row.nom_predio is not None:
            count = pair_counts[(row.cod_predial, row.nom_predio)]

            if (
                count < max_count_by_code[row.cod_predial]
                or count < max_count_by_name[row.nom_predio]
            ):
                feature_flags.append(FLAG_PREDIO_CODE_NAME_ANOMALY)

        cod_uso_2026 = row.values["cod_uso_2026"]

        if isinstance(cod_uso_2026, str) and cod_uso_2026.endswith("*"):
            feature_flags.append(FLAG_TRUNCATED_USE_CODE_2026)

        flags[row.record_number] = tuple(sorted(feature_flags))

    return flags
