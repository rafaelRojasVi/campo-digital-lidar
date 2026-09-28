"""TR-FUNC-013's owner-status table: predio-grain, grouped by owner type.

Ships Javier's existing ``ownerStage()`` legacy rule under the explicit
``owner_stage_legacy`` basis identifier (see ``status_rollups``). This does
NOT resolve TR-OPEN-01 — the ambiguity against ``estado_resumido_first_row``
and ``pending_priority_legacy`` for the same underlying rows is left
visible, not silently reconciled.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from transelec_ingestion.status_rollups import RolledRow, first_row_wins, owner_stage_from_row

BASIS = "owner_stage_legacy"


@dataclass(frozen=True, slots=True)
class OwnerStatusInputRow:
    source_row_number: int
    predio_group_key: str
    pmf: str
    tipo_propietario: str | None
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
            tipo_propietario=self.tipo_propietario,
        )


@dataclass(frozen=True, slots=True)
class OwnerStatusRow:
    tipo_propietario: str | None
    owner_stage: str | None
    predio_count: int


@dataclass(frozen=True, slots=True)
class OwnerStatusResult:
    basis: str
    rows: list[OwnerStatusRow]
    total_predio_count: int


def build_owner_status(rows: Sequence[OwnerStatusInputRow]) -> OwnerStatusResult:
    """Dedup predio-grain (first-row-wins), apply ``ownerStage()``, group by
    (``Tipo de propietario``, owner stage) and count distinct predios."""

    rolled = [row._as_rolled_row() for row in rows]
    representative = first_row_wins(rolled, key="predio_group_key")

    counts: Counter[tuple[str | None, str | None]] = Counter()
    for row in representative.values():
        counts[(row.tipo_propietario, owner_stage_from_row(row))] += 1

    result_rows = [
        OwnerStatusRow(
            tipo_propietario=tipo_propietario, owner_stage=owner_stage, predio_count=count
        )
        for (tipo_propietario, owner_stage), count in sorted(
            counts.items(), key=lambda item: (item[0][0] or "", item[0][1] or "")
        )
    ]

    return OwnerStatusResult(
        basis=BASIS,
        rows=result_rows,
        total_predio_count=len(representative),
    )
