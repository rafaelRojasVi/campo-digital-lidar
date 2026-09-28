"""The three named, evidenced PMF/predio status-rollup bases (TR-OPEN-01).

Javier's two HTML dashboards compute a PMF's or a predio's "status" three
different, genuinely disagreeing ways depending on which section of which
file you look at (source forensic audit, section 5, "Ambiguous conflicts
requiring a named decision"; functional parity matrix, TR-FUNC-005/006/007/
011/013/032). There is no canonical rule yet — TR-OPEN-01 is open, and this
module does not invent one. Instead it ships each of Javier's own current
rules, faithfully, under its own explicit basis identifier, so a future
canonical decision replaces exactly one of them, in one place, without
touching every call site that reads a status:

- ``estado_resumido_first_row`` — TR-FUNC-005/006/011. A `Map`-insertion-
  order "first row wins" dedup by PMF or by predio_group_key, reading the
  winning row's own ``Estado resumido``.
- ``pending_priority_legacy`` — TR-FUNC-007/032 (``isPendingPMF``). Same
  first-row-wins dedup mechanism, but the winning row is tested against a
  completely different predicate (blank ``N Ingreso`` or ``Estado``
  containing "rechaz"), which is *why* it can disagree with
  ``estado_resumido_first_row`` for the very same underlying row — confirmed
  live in the forensic audit (filtering to "rechaz" on the real dashboard
  produced PMFs whose Estado-resumido-based approval rate showed
  "0 Aprobados, 8 En trámite" while the same PMFs are "pending" here).
- ``owner_stage_legacy`` — TR-FUNC-013 (``ownerStage()``). Predio-grain,
  same dedup mechanism again; the winning row's raw ``Estado`` overrides
  ``Estado resumido`` with a synthesized "Rechazado" label when it contains
  "rechaz", otherwise the raw ``Estado resumido`` value passes through
  unchanged.

None of these three is "the" correct rollup. All three are shipped, all
three are named, and all three stay independently swappable behind the
``STATUS_ROLLUP_BASES`` lookup below.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

GroupKey = Literal["pmf", "predio_group_key"]

Bucket3Way = Literal["aprobado", "en_tramite", "pendiente_o_tachado"]
HeroState = Literal["aprobado", "en_tramite", "pendiente", "tachado", "sin_estado"]
PendingStage = Literal["preparacion", "recurso_rechazo", "otros"]


@dataclass(frozen=True, slots=True)
class RolledRow:
    """The minimal per-row shape every status-rollup basis needs.

    A thin, DB-agnostic view over one ``transelec_resumen_row`` — callers
    (the HTTP router) project a fetched database row into this shape;
    nothing here touches SQLAlchemy or the database, so every basis below is
    unit-testable with a hand-built list of these.
    """

    source_row_number: int
    pmf: str
    predio_group_key: str
    estado: str | None
    estado_resumido: str | None
    numero_ingreso: str | None
    tipo_propietario: str | None = None


_WHITESPACE = re.compile(r"\s+")


def normalized_label(value: str | None) -> str | None:
    """A casing/accent/whitespace-insensitive comparison key, or ``None``.

    The reviewed 14-Aug snapshot spells the same detailed ``Estado`` more
    than one way — ``En Evaluacion`` (129 rows) beside ``En evaluacion`` (2),
    ``Recurso reposicion`` (9) beside ``Recurso Reposicion`` (1) — which
    splits one business state into two rows of any breakdown built by naive
    string equality. Folding case, combining accents and runs of whitespace
    collapses the 13 raw spellings in that snapshot to 11 states.

    This is a *comparison* key only. Nothing in this module ever writes it
    back over a source value: every caller keeps the raw spelling it first
    encountered as the label it displays, so the fold can merge two rows
    without erasing what the workbook actually said.
    """

    if value is None:
        return None
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = _WHITESPACE.sub(" ", stripped).strip()
    return collapsed or None


def distinct_estado_resumido(
    rows: Iterable[RolledRow], *, key: GroupKey = "pmf"
) -> dict[str, tuple[str | None, ...]]:
    """Every distinct ``Estado resumido`` each key carries, in source order.

    Distinctness is decided on ``normalized_label``; the tuple holds the raw
    spellings, first-encountered first. A key whose rows all agree yields a
    1-tuple, so a caller can treat "length > 1" as the conflict predicate
    without a second pass.
    """

    seen: dict[str, dict[str | None, str | None]] = {}
    for row in sorted(rows, key=lambda row: row.source_row_number):
        group_value = getattr(row, key)
        bucket = seen.setdefault(group_value, {})
        bucket.setdefault(normalized_label(row.estado_resumido), row.estado_resumido)
    return {group_value: tuple(bucket.values()) for group_value, bucket in seen.items()}


def estado_resumido_conflicts(
    rows: Iterable[RolledRow], *, key: GroupKey = "pmf"
) -> dict[str, tuple[str | None, ...]]:
    """Only the keys carrying more than one distinct ``Estado resumido``.

    This is the evidence behind the headline's central invariant. A PMF
    belongs to exactly one headline bucket — decided by ``first_row_wins``,
    the contract this module has always used — but the rows a discarded
    value came from are real, and a reader who adds the source workbook's
    per-row values by hand will get a different, larger total. Javier's
    29-Jul Power BI summary does exactly that: its 101 + 56 + 3 buckets sum
    to 160 against a stated 159 PMF total, because one PMF is counted in two
    buckets.

    We do not reproduce that arithmetic, and we do not hide the row that
    causes it. The conflict is returned here, surfaced in the quality
    section, and left for the stakeholder to rule on.
    """

    return {
        group_value: values
        for group_value, values in distinct_estado_resumido(rows, key=key).items()
        if len(values) > 1
    }


def first_row_wins(rows: Iterable[RolledRow], *, key: GroupKey) -> dict[str, RolledRow]:
    """Return, for each distinct value of ``key``, its first-encountered row.

    "First" means the smallest ``source_row_number`` — the forensic audit's
    own characterization of the HTML's ``Map``-insertion-order dedup
    ("Dedup tie-break ... is first source row encountered"), not merely
    whichever row happens to appear first in the ``rows`` iterable. This is
    the single shared mechanism behind both ``estado_resumido_first_row``
    and ``pending_priority_legacy``, and (at predio grain) ``owner_stage_legacy``.
    """

    winners: dict[str, RolledRow] = {}
    for row in rows:
        group_value = getattr(row, key)
        current = winners.get(group_value)
        if current is None or row.source_row_number < current.source_row_number:
            winners[group_value] = row
    return winners


# ---------------------------------------------------------------------------
# Basis: estado_resumido_first_row — TR-FUNC-005/006/011
# ---------------------------------------------------------------------------


def estado_resumido_first_row(rows: Iterable[RolledRow], *, key: GroupKey) -> dict[str, str | None]:
    """Each key's ``Estado resumido``, read off its first-encountered row."""

    winners = first_row_wins(rows, key=key)
    return {group_key: row.estado_resumido for group_key, row in winners.items()}


# ---------------------------------------------------------------------------
# Basis: pending_priority_legacy — TR-FUNC-007/032 (isPendingPMF)
# ---------------------------------------------------------------------------


def is_pending_row(row: RolledRow) -> bool:
    """``isPendingPMF``: blank ``N Ingreso`` OR ``Estado`` contains "rechaz".

    Case-insensitive substring match on ``Estado``, per the ratified matrix.
    """

    blank_ingreso = row.numero_ingreso is None or not row.numero_ingreso.strip()
    rejected = row.estado is not None and "rechaz" in row.estado.lower()
    return blank_ingreso or rejected


def pending_priority_legacy(rows: Iterable[RolledRow], *, key: GroupKey = "pmf") -> dict[str, bool]:
    """Each key's pending-priority flag, evaluated on its first-encountered row.

    Uses the same first-row-wins dedup as ``estado_resumido_first_row``, but
    applies a different predicate to the winning row — which is exactly why
    the two bases can (and, per the forensic audit, do) disagree for the
    same underlying row.
    """

    return {
        group_key: is_pending_row(row) for group_key, row in first_row_wins(rows, key=key).items()
    }


# ---------------------------------------------------------------------------
# Basis: owner_stage_legacy — TR-FUNC-013 (ownerStage())
# ---------------------------------------------------------------------------


def owner_stage_from_row(row: RolledRow) -> str | None:
    """``ownerStage()``: "Rechazado" override when raw Estado contains
    "rechaz", else the raw ``Estado resumido`` value, unchanged."""

    if row.estado is not None and "rechaz" in row.estado.lower():
        return "Rechazado"
    return row.estado_resumido


def owner_stage_legacy(
    rows: Iterable[RolledRow], *, key: GroupKey = "predio_group_key"
) -> dict[str, str | None]:
    """Each key's owner-stage label, evaluated on its first-encountered row."""

    return {
        group_key: owner_stage_from_row(row)
        for group_key, row in first_row_wins(rows, key=key).items()
    }


STATUS_ROLLUP_BASES: Mapping[str, Callable[..., Mapping[str, object]]] = {
    "estado_resumido_first_row": estado_resumido_first_row,
    "pending_priority_legacy": pending_priority_legacy,
    "owner_stage_legacy": owner_stage_legacy,
}


# ---------------------------------------------------------------------------
# pending_stage — TR-FUNC-032's 3-way substring heuristic over raw Estado.
#
# NOT one of the three basis identifiers above (it further subdivides an
# already-pending row, it does not decide whether a row is pending), but
# named and disclosed the same way: the parity matrix flags it explicitly as
# "INFERENCE-quality (not a confirmed CONAF taxonomy)", and this
# implementation makes no attempt to upgrade that confidence level.
# ---------------------------------------------------------------------------


def pending_stage(estado: str | None) -> PendingStage:
    """3-way heuristic: 'prepar' / ('recurso' AND 'rechaz') / else.

    Case-insensitive substring checks, per the ratified matrix's own
    characterization of ``pendingStage()``. "prepar" is checked first, so a
    string containing both "prepar" and "recurso"/"rechaz" is classified as
    "preparacion" — the matrix does not evidence a tie-break, so this
    mirrors the natural reading order of a 3-way if/else-if chain.
    """

    normalized = (estado or "").lower()
    if "prepar" in normalized:
        return "preparacion"
    if "recurso" in normalized and "rechaz" in normalized:
        return "recurso_rechazo"
    return "otros"


# ---------------------------------------------------------------------------
# Chart/hero bucketing — TR-FUNC-009/010 (3-way) and TR-FUNC-011 (4-state).
#
# Both read the same estado_resumido_first_row-deduped representative row;
# these two functions only decide how to *bucket* that row's Estado
# resumido value for display. Not a new rollup basis: same input, same
# dedup, just a different presentation grouping.
# ---------------------------------------------------------------------------

_APROBADO = "aprobado"
_EN_TRAMITE = {"en tramite", "en trámite"}


def bucket_3way(estado_resumido: str | None) -> Bucket3Way:
    """Aprobado / En trámite / Pendiente-o-Tachado (TR-FUNC-009/010).

    Anything that is not recognizably "Aprobado" or "En tramite" — including
    a blank/unexpected value — merges into the third bucket, matching the
    matrix's own "Pendiente-o-Tachado" catch-all framing.
    """

    normalized = (estado_resumido or "").strip().lower()
    if normalized == _APROBADO:
        return "aprobado"
    if normalized in _EN_TRAMITE:
        return "en_tramite"
    return "pendiente_o_tachado"


_HERO_STATES: dict[str, HeroState] = {
    "aprobado": "aprobado",
    "en tramite": "en_tramite",
    "en trámite": "en_tramite",
    "pendiente": "pendiente",
    "tachado": "tachado",
}


def hero_state(estado_resumido: str | None) -> HeroState:
    """One of the 4 known ``Estado resumido`` values (TR-FUNC-011), or the
    defensive ``"sin_estado"`` bucket for a blank/unrecognized value.

    ``sin_estado`` is a technical safety net, not a 5th business category:
    the reviewed workbook has exactly 4 distinct values here, but nothing
    guarantees a future import does, and TR-FUNC-011's acceptance test
    requires hero counts to sum exactly to the predio total.
    """

    normalized = (estado_resumido or "").strip().lower()
    return _HERO_STATES.get(normalized, "sin_estado")
