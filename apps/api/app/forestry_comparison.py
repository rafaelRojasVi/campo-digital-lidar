"""Compare a pending Forestry snapshot with the published one, for review.

What this can and cannot say (DECISION, see
products/forestry/docs/upload-review-publish-v1.md):

- No source field is a proven cross-version identity. ``OBJECTID`` is an
  export-assigned number and ``(Cod_Predial, N_Rodal)`` is duplicated or
  blank inside the one observed snapshot. So matching never uses them; they
  are shown next to a match as evidence only.
- Matching is geometric. Two features whose stored geometry is byte-for-byte
  identical, one on each side, are ``same_geometry`` (attribute differences
  are then listed field by field). That is the only match treated as
  certain.
- Every other feature is grouped by area overlap. A pending feature and a
  published feature are *linked* when their overlap is at least
  ``LINK_OVERLAP_RATIO`` of the smaller of the two. Linked features form
  connected groups:

  - one published and one pending feature: ``geometry_changed``, a
    *probable* correspondence that needs review;
  - any other mix: ``uncertain`` (it could be a redraw, a split, a merge,
    or unrelated neighbours; this code does not decide which);
  - only pending: ``added``; only published: ``removed``.

- Nothing here says a rodal was cut, harvested, or replaced. A shape or
  attribute change is reported as a change, never as an operation.

Invalid source geometries are compared through ``ST_MakeValid`` copies made
on the fly; stored geometry is never modified.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

# Overlap, as a share of the smaller feature's area, needed to link two
# features. Shared borders overlap by ~0; a redrawn edge moves a few percent
# at most. Triage only: the reviewer sees every overlap ratio.
LINK_OVERLAP_RATIO = 0.05

ChangeKind = Literal["same_geometry", "geometry_changed", "uncertain", "added", "removed"]

# Kinds a reviewer has to acknowledge before publishing.
REVIEW_REQUIRED_KINDS: frozenset[str] = frozenset({"geometry_changed", "uncertain"})


@dataclass(frozen=True, slots=True)
class FeatureRef:
    """One feature as evidence: its snapshot-local ordinal plus source labels."""

    feature_ordinal: int
    source_objectid: int | None
    cod_predial: str | None
    nom_predio: str | None
    n_rodal: str | None
    sup_ha: float | None
    geometry_area_source_units: float


@dataclass(frozen=True, slots=True)
class OverlapEvidence:
    """Area overlap between one published and one pending feature."""

    published_ordinal: int
    pending_ordinal: int
    overlap_ratio_of_smaller: float


@dataclass(frozen=True, slots=True)
class ChangeItem:
    """One group of features and what can be said about it."""

    kind: ChangeKind
    published: tuple[FeatureRef, ...]
    pending: tuple[FeatureRef, ...]
    changed_fields: tuple[str, ...] = ()
    overlaps: tuple[OverlapEvidence, ...] = ()
    same_objectid: bool | None = None


@dataclass(frozen=True, slots=True)
class SnapshotComparison:
    """Everything a reviewer needs to judge a pending snapshot."""

    published_snapshot_id: int
    counts: dict[str, int]
    # same_geometry pairs with no attribute difference are counted, not listed.
    unchanged_count: int
    items: tuple[ChangeItem, ...]
    link_overlap_ratio: float = LINK_OVERLAP_RATIO
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def review_required_count(self) -> int:
        return sum(self.counts.get(kind, 0) for kind in REVIEW_REQUIRED_KINDS)


class ComparisonUnavailableError(RuntimeError):
    """PostGIS could not compute the overlaps (e.g. a geometry it cannot process)."""


_FEATURE_COLUMNS = """
    feature_ordinal, source_objectid, cod_predial, nom_predio, n_rodal, sup_ha,
    geometry_area_source_units, source_attributes, ST_AsBinary(geometry) AS wkb
"""


def _load_features(connection: Connection, snapshot_id: int) -> dict[int, Any]:
    rows = connection.execute(
        text(
            f"""
            SELECT {_FEATURE_COLUMNS}
            FROM forestry.source_feature
            WHERE shapefile_snapshot_id = :snapshot_id
            ORDER BY feature_ordinal
            """
        ),
        {"snapshot_id": snapshot_id},
    ).all()
    return {row.feature_ordinal: row for row in rows}


def _ref(row: Any) -> FeatureRef:
    return FeatureRef(
        feature_ordinal=row.feature_ordinal,
        source_objectid=row.source_objectid,
        cod_predial=row.cod_predial,
        nom_predio=row.nom_predio,
        n_rodal=row.n_rodal,
        sup_ha=row.sup_ha,
        geometry_area_source_units=row.geometry_area_source_units,
    )


def _digest(row: Any) -> str:
    return hashlib.sha256(bytes(row.wkb)).hexdigest()


def _changed_fields(published: Any, pending: Any) -> tuple[str, ...]:
    before: dict[str, Any] = published.source_attributes
    after: dict[str, Any] = pending.source_attributes
    return tuple(
        sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    )


def _overlaps(
    connection: Connection,
    *,
    published_id: int,
    pending_id: int,
    published_ordinals: list[int],
    pending_ordinals: list[int],
) -> list[OverlapEvidence]:
    if not published_ordinals or not pending_ordinals:
        return []

    # The bounding-box join uses the GIST index on the stored geometry; only
    # candidate pairs are made valid and intersected. A SAVEPOINT keeps a
    # GEOS failure from aborting the caller's transaction.
    try:
        with connection.begin_nested():
            rows = connection.execute(
                text(
                    """
                    WITH pairs AS (
                        SELECT
                            a.feature_ordinal AS published_ordinal,
                            b.feature_ordinal AS pending_ordinal,
                            CASE WHEN a.geometry_is_valid THEN a.geometry
                                 ELSE ST_MakeValid(a.geometry) END AS ga,
                            CASE WHEN b.geometry_is_valid THEN b.geometry
                                 ELSE ST_MakeValid(b.geometry) END AS gb
                        FROM forestry.source_feature AS a
                        JOIN forestry.source_feature AS b
                          ON a.geometry && b.geometry
                        WHERE a.shapefile_snapshot_id = :published_id
                          AND b.shapefile_snapshot_id = :pending_id
                          AND a.feature_ordinal = ANY(:published_ordinals)
                          AND b.feature_ordinal = ANY(:pending_ordinals)
                    )
                    SELECT
                        published_ordinal,
                        pending_ordinal,
                        ST_Area(ST_Intersection(ga, gb)) AS overlap_area,
                        LEAST(ST_Area(ga), ST_Area(gb)) AS smaller_area
                    FROM pairs
                    WHERE ST_Intersects(ga, gb)
                    """
                ),
                {
                    "published_id": published_id,
                    "pending_id": pending_id,
                    "published_ordinals": published_ordinals,
                    "pending_ordinals": pending_ordinals,
                },
            ).all()
    except DBAPIError as error:
        raise ComparisonUnavailableError("PostGIS could not intersect the geometries") from error

    evidence: list[OverlapEvidence] = []
    for row in rows:
        if row.smaller_area <= 0:
            continue
        ratio = float(row.overlap_area) / float(row.smaller_area)
        if ratio > 0:
            evidence.append(
                OverlapEvidence(
                    published_ordinal=row.published_ordinal,
                    pending_ordinal=row.pending_ordinal,
                    overlap_ratio_of_smaller=round(min(ratio, 1.0), 4),
                )
            )
    return evidence


def compare_snapshots(
    connection: Connection, *, published_id: int, pending_id: int
) -> SnapshotComparison:
    """Classify every feature of both snapshots; see the module docstring."""

    published = _load_features(connection, published_id)
    pending = _load_features(connection, pending_id)

    by_digest_published: dict[str, list[int]] = defaultdict(list)
    by_digest_pending: dict[str, list[int]] = defaultdict(list)
    for ordinal, row in published.items():
        by_digest_published[_digest(row)].append(ordinal)
    for ordinal, row in pending.items():
        by_digest_pending[_digest(row)].append(ordinal)

    items: list[ChangeItem] = []
    unchanged = 0
    matched_published: set[int] = set()
    matched_pending: set[int] = set()

    for digest, published_ordinals in by_digest_published.items():
        pending_ordinals = by_digest_pending.get(digest, [])
        # Only a unique geometry on each side is a certain pairing; duplicated
        # geometries fall through to the overlap grouping as uncertain.
        if len(published_ordinals) != 1 or len(pending_ordinals) != 1:
            continue
        before = published[published_ordinals[0]]
        after = pending[pending_ordinals[0]]
        matched_published.add(before.feature_ordinal)
        matched_pending.add(after.feature_ordinal)
        changed = _changed_fields(before, after)
        if not changed:
            unchanged += 1
            continue
        items.append(
            ChangeItem(
                kind="same_geometry",
                published=(_ref(before),),
                pending=(_ref(after),),
                changed_fields=changed,
                same_objectid=before.source_objectid == after.source_objectid,
            )
        )

    remaining_published = sorted(set(published) - matched_published)
    remaining_pending = sorted(set(pending) - matched_pending)
    overlaps = _overlaps(
        connection,
        published_id=published_id,
        pending_id=pending_id,
        published_ordinals=remaining_published,
        pending_ordinals=remaining_pending,
    )

    # Union-find over ("published", ordinal) / ("pending", ordinal) nodes.
    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(node: tuple[str, int]) -> tuple[str, int]:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for ordinal in remaining_published:
        find(("published", ordinal))
    for ordinal in remaining_pending:
        find(("pending", ordinal))

    links = [o for o in overlaps if o.overlap_ratio_of_smaller >= LINK_OVERLAP_RATIO]
    for link in links:
        a = find(("published", link.published_ordinal))
        b = find(("pending", link.pending_ordinal))
        if a != b:
            parent[a] = b

    groups: dict[tuple[str, int], list[tuple[str, int]]] = defaultdict(list)
    for node in list(parent):
        groups[find(node)].append(node)

    overlaps_by_group: dict[tuple[str, int], list[OverlapEvidence]] = defaultdict(list)
    for overlap in overlaps:
        root = find(("published", overlap.published_ordinal))
        if root == find(("pending", overlap.pending_ordinal)):
            overlaps_by_group[root].append(overlap)

    for root, nodes in groups.items():
        before_rows = [published[o] for side, o in sorted(nodes) if side == "published"]
        after_rows = [pending[o] for side, o in sorted(nodes) if side == "pending"]
        kind: ChangeKind
        if before_rows and after_rows:
            kind = (
                "geometry_changed"
                if len(before_rows) == 1 and len(after_rows) == 1
                else "uncertain"
            )
        elif after_rows:
            kind = "added"
        else:
            kind = "removed"

        pair = kind == "geometry_changed"
        items.append(
            ChangeItem(
                kind=kind,
                published=tuple(_ref(row) for row in before_rows),
                pending=tuple(_ref(row) for row in after_rows),
                changed_fields=_changed_fields(before_rows[0], after_rows[0]) if pair else (),
                overlaps=tuple(
                    sorted(
                        overlaps_by_group.get(root, []),
                        key=lambda o: (o.published_ordinal, o.pending_ordinal),
                    )
                ),
                same_objectid=(
                    before_rows[0].source_objectid == after_rows[0].source_objectid
                    if pair
                    else None
                ),
            )
        )

    order = {"uncertain": 0, "geometry_changed": 1, "removed": 2, "added": 3, "same_geometry": 4}
    items.sort(
        key=lambda item: (
            order[item.kind],
            min((ref.feature_ordinal for ref in item.pending), default=0),
            min((ref.feature_ordinal for ref in item.published), default=0),
        )
    )

    counts: dict[str, int] = {kind: 0 for kind in order}
    for item in items:
        counts[item.kind] += 1

    return SnapshotComparison(
        published_snapshot_id=published_id,
        counts=counts,
        unchanged_count=unchanged,
        items=tuple(items),
    )
