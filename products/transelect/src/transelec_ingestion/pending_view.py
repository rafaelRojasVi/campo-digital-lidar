"""TR-FUNC-007/032/033's pending-priority section, PMF-grain.

``pending_priority_legacy`` (``isPendingPMF``) decides which PMFs are
pending-priority (TR-FUNC-007); ``pending_stage`` (``pendingStage()``'s
3-way substring heuristic) further subdivides those into stages
(TR-FUNC-032). Both are PMF-deduped via the shared first-row-wins mechanism
(``status_rollups.first_row_wins``) — the same tie-break TR-FUNC-001 uses.

Only identifying information is returned for the detail rows
(``source_row_number`` of the winning row): full row hydration for
TR-FUNC-033's detail table happens at the HTTP adapter, which already holds
the full fetched row set and can look the winning row up by
``source_row_number`` without this pure module needing to know about all 30
contract fields.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from transelec_ingestion.status_rollups import (
    RolledRow,
    first_row_wins,
    is_pending_row,
    pending_stage,
)

BASIS = "pending_priority_legacy"
STAGE_BASIS = "pending_stage_legacy"


@dataclass(frozen=True, slots=True)
class PendingInputRow:
    source_row_number: int
    pmf: str
    predio_group_key: str
    estado: str | None
    estado_resumido: str | None
    numero_ingreso: str | None

    def _as_rolled_row(self) -> RolledRow:
        return RolledRow(
            source_row_number=self.source_row_number,
            pmf=self.pmf,
            predio_group_key=self.predio_group_key,
            estado=self.estado,
            estado_resumido=self.estado_resumido,
            numero_ingreso=self.numero_ingreso,
        )


@dataclass(frozen=True, slots=True)
class PendingStageCounts:
    preparacion: int
    recurso_rechazo: int
    otros: int


@dataclass(frozen=True, slots=True)
class PendingPmfSummary:
    pmf: str
    source_row_number: int
    pending_stage: str


@dataclass(frozen=True, slots=True)
class PendingResult:
    basis: str
    pending_pmf_count: int
    total_pmf_count: int
    pending_pmf_percentage: float
    stage_basis: str
    stages: PendingStageCounts
    rows: list[PendingPmfSummary]


def build_pending(rows: Sequence[PendingInputRow]) -> PendingResult:
    rolled = [row._as_rolled_row() for row in rows]
    representative = first_row_wins(rolled, key="pmf")

    total_pmf_count = len(representative)
    pending_rows = {pmf: row for pmf, row in representative.items() if is_pending_row(row)}

    preparacion = recurso_rechazo = otros = 0
    detail_rows: list[PendingPmfSummary] = []
    for pmf, row in pending_rows.items():
        stage = pending_stage(row.estado)
        if stage == "preparacion":
            preparacion += 1
        elif stage == "recurso_rechazo":
            recurso_rechazo += 1
        else:
            otros += 1
        detail_rows.append(
            PendingPmfSummary(pmf=pmf, source_row_number=row.source_row_number, pending_stage=stage)
        )

    detail_rows.sort(key=lambda summary: summary.source_row_number)

    pending_pmf_count = len(pending_rows)
    percentage = (pending_pmf_count / total_pmf_count * 100) if total_pmf_count else 0.0

    return PendingResult(
        basis=BASIS,
        pending_pmf_count=pending_pmf_count,
        total_pmf_count=total_pmf_count,
        pending_pmf_percentage=percentage,
        stage_basis=STAGE_BASIS,
        stages=PendingStageCounts(
            preparacion=preparacion, recurso_rechazo=recurso_rechazo, otros=otros
        ),
        rows=detail_rows,
    )
