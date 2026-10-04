"""``lifecycle_pmf_v1`` — where each plan (PMF) stands in CONAF's process.

Design: docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md.

A rejection is a step, never an end (meeting of 2026-10-02): every rejection
ends approved or withdrawn. The group comes from the first row's
``Estado resumido``; inside «En trámite» the step comes from its ``Estado``.
Labels match exactly after ``normalized_label`` (case, accents and
whitespace folded). The only other test is the whole word «aprobado» in the
consistency check. Nothing is guessed: a label or a combination this basis
does not know lands in ``sin_clasificar`` with its reason, for a person to
read in the planilla.

A PMF's representative row is its first row — the same tie-break as
``status_rollups.first_row_wins`` (smallest ``source_row_number``). A PMF
whose rows disagree on ``Estado`` or ``Estado resumido`` keeps that result
and is flagged ``filas_no_coinciden``.

Pure and DB-agnostic, like ``pending_view``: the HTTP adapter projects rows
into ``LifecycleInputRow`` and hydrates each PMF's first row itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from transelec_ingestion.status_rollups import normalized_label

LIFECYCLE_BASIS = "lifecycle_pmf_v1"

LifecycleGroup = Literal["aprobado", "en_tramite", "descartado", "desistido", "sin_clasificar"]
LifecycleStep = Literal[
    "sin_ingreso",
    "en_evaluacion",
    "rechazado_esperando_recurso",
    "en_recurso_reposicion",
    "en_recurso_jerarquico",
]
LifecycleReason = Literal[
    "resumido_desconocido",
    "estado_desconocido",
    "estado_y_resumido_no_coinciden",
]
LifecycleFlag = Literal["filas_no_coinciden"]
Classification = tuple[LifecycleGroup, LifecycleStep | None, LifecycleReason | None]

GROUP_ORDER: tuple[LifecycleGroup, ...] = (
    "aprobado",
    "en_tramite",
    "descartado",
    "desistido",
    "sin_clasificar",
)
STEP_ORDER: tuple[LifecycleStep, ...] = (
    "sin_ingreso",
    "en_evaluacion",
    "rechazado_esperando_recurso",
    "en_recurso_reposicion",
    "en_recurso_jerarquico",
)

# The groups that end CONAF's process. The 90 días hábiles basis answers
# «no aplica» for them (through the router's ``_closed_pmfs``).
CLOSED_GROUPS: frozenset[str] = frozenset({"aprobado", "descartado", "desistido"})

_GROUP_BY_RESUMIDO: dict[str, LifecycleGroup] = {
    "aprobado": "aprobado",
    "en tramite": "en_tramite",
    # The source already summarizes a rejection as in progress; so does this.
    "rechazado": "en_tramite",
    "descartado": "descartado",
    "desistido": "desistido",
}

_APROBADO_WORD = re.compile(r"\baprobado\b")


@dataclass(frozen=True, slots=True)
class LifecycleInputRow:
    source_row_number: int
    pmf: str
    estado: str | None
    estado_resumido: str | None
    numero_ingreso: str | None
    numero_ingreso_2: str | None


@dataclass(frozen=True, slots=True)
class PmfLifecycle:
    pmf: str
    source_row_number: int
    group: LifecycleGroup
    step: LifecycleStep | None
    reason: LifecycleReason | None
    flags: tuple[LifecycleFlag, ...]


@dataclass(frozen=True, slots=True)
class LifecycleSummary:
    basis: str
    total_pmf_count: int
    groups: dict[LifecycleGroup, int]
    steps: dict[LifecycleStep, int]
    pmfs: tuple[PmfLifecycle, ...]


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _contradiction(group: LifecycleGroup, estado: str | None) -> bool:
    says_approved = estado is not None and _APROBADO_WORD.search(estado) is not None
    if group == "aprobado":
        return not says_approved
    if says_approved:
        return True
    if group in ("descartado", "desistido"):
        return estado != group
    return False


def _step(row: LifecycleInputRow, estado: str | None) -> LifecycleStep | None:
    if _blank(row.numero_ingreso) and _blank(row.numero_ingreso_2):
        return "sin_ingreso"
    if estado == "en evaluacion":
        return "en_evaluacion"
    if estado == "rechazado" or (
        estado is not None and estado.startswith("recurso") and estado.endswith("rechazado")
    ):
        return "rechazado_esperando_recurso"
    if estado == "recurso reposicion":
        return "en_recurso_reposicion"
    if estado == "recurso jerarquico":
        return "en_recurso_jerarquico"
    return None


def classify_first_row(row: LifecycleInputRow) -> Classification:
    """Group, step (only inside ``en_tramite``) and reason for one first row."""

    group = _GROUP_BY_RESUMIDO.get(normalized_label(row.estado_resumido) or "")
    if group is None:
        return "sin_clasificar", None, "resumido_desconocido"

    estado = normalized_label(row.estado)
    if _contradiction(group, estado):
        return "sin_clasificar", None, "estado_y_resumido_no_coinciden"
    if group != "en_tramite":
        return group, None, None

    step = _step(row, estado)
    if step is None:
        return "sin_clasificar", None, "estado_desconocido"
    return "en_tramite", step, None


def build_lifecycle(rows: Iterable[LifecycleInputRow]) -> LifecycleSummary:
    by_pmf: dict[str, list[LifecycleInputRow]] = {}
    for row in rows:
        by_pmf.setdefault(row.pmf, []).append(row)

    pmfs: list[PmfLifecycle] = []
    for pmf, pmf_rows in by_pmf.items():
        first = min(pmf_rows, key=lambda row: row.source_row_number)
        group, step, reason = classify_first_row(first)
        disagree = (
            len({normalized_label(row.estado) for row in pmf_rows}) > 1
            or len({normalized_label(row.estado_resumido) for row in pmf_rows}) > 1
        )
        flags: tuple[LifecycleFlag, ...] = ("filas_no_coinciden",) if disagree else ()
        pmfs.append(
            PmfLifecycle(
                pmf=pmf,
                source_row_number=first.source_row_number,
                group=group,
                step=step,
                reason=reason,
                flags=flags,
            )
        )

    pmfs.sort(key=lambda entry: entry.source_row_number)

    groups: dict[LifecycleGroup, int] = {group: 0 for group in GROUP_ORDER}
    steps: dict[LifecycleStep, int] = {step: 0 for step in STEP_ORDER}
    for entry in pmfs:
        groups[entry.group] += 1
        if entry.step is not None:
            steps[entry.step] += 1

    return LifecycleSummary(
        basis=LIFECYCLE_BASIS,
        total_pmf_count=len(pmfs),
        groups=groups,
        steps=steps,
        pmfs=tuple(pmfs),
    )
