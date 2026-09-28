"""Unit tests for TR-FUNC-007/032/033's pending-priority section.

``pending_priority_legacy`` (isPendingPMF) and ``pending_stage``
(pendingStage()'s 3-way substring heuristic) are exercised together here.
"""

from __future__ import annotations

from transelec_ingestion.pending_view import PendingInputRow, build_pending


def _row(
    *,
    source_row_number: int,
    pmf: str,
    estado: str | None = None,
    numero_ingreso: str | None = "1",
) -> PendingInputRow:
    return PendingInputRow(
        source_row_number=source_row_number,
        pmf=pmf,
        predio_group_key=f"{pmf}-key",
        estado=estado,
        estado_resumido="En tramite",
        numero_ingreso=numero_ingreso,
    )


def test_pending_count_and_percentage_use_the_same_filtered_pmf_total() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", numero_ingreso=None),  # pending: blank ingreso
        _row(source_row_number=1, pmf="MP002", numero_ingreso="9"),  # not pending
        _row(source_row_number=1, pmf="MP003", estado="Rechazado", numero_ingreso="9"),  # pending
        _row(source_row_number=1, pmf="MP004", numero_ingreso="9"),  # not pending
    ]

    result = build_pending(rows)

    assert result.basis == "pending_priority_legacy"
    assert result.pending_pmf_count == 2  # TR-FUNC-007
    assert result.total_pmf_count == 4
    assert result.pending_pmf_percentage == 50.0  # TR-FUNC-032


def test_stage_breakdown_sums_to_pending_count() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", estado="En preparacion", numero_ingreso=None),
        _row(
            source_row_number=1,
            pmf="MP002",
            estado="Recurso por rechazo administrativo",
            numero_ingreso=None,
        ),
        _row(source_row_number=1, pmf="MP003", estado="En evaluacion legal", numero_ingreso=None),
        _row(source_row_number=1, pmf="MP004", numero_ingreso="9"),  # not pending, excluded
    ]

    result = build_pending(rows)

    assert result.pending_pmf_count == 3
    assert (
        result.stages.preparacion + result.stages.recurso_rechazo + result.stages.otros
        == result.pending_pmf_count
    )
    assert result.stages.preparacion == 1
    assert result.stages.recurso_rechazo == 1
    assert result.stages.otros == 1
    assert result.stage_basis == "pending_stage_legacy"


def test_detail_rows_are_pmf_deduped_first_row_wins_and_carry_pending_stage() -> None:
    rows = [
        _row(source_row_number=5, pmf="MP001", estado="Tachado", numero_ingreso=None),
        _row(source_row_number=2, pmf="MP001", estado="En preparacion", numero_ingreso=None),
        _row(source_row_number=1, pmf="MP002", numero_ingreso="9"),  # not pending
    ]

    result = build_pending(rows)

    assert len(result.rows) == 1
    detail = result.rows[0]
    assert detail.pmf == "MP001"
    assert detail.source_row_number == 2  # the first-encountered (winning) row
    assert detail.pending_stage == "preparacion"


def test_empty_input_returns_zero_counts_not_a_division_error() -> None:
    result = build_pending([])

    assert result.total_pmf_count == 0
    assert result.pending_pmf_count == 0
    assert result.pending_pmf_percentage == 0.0
    assert result.rows == []
