"""Unit tests for the three named, evidenced PMF/predio status-rollup bases.

TR-OPEN-01 is deliberately NOT resolved here: each basis below is Javier's
own current dashboard behavior, kept separate under its own identifier, per
the ratified functional parity matrix
(products/transelect/docs/audit/2026-09-02-functional-parity-matrix-v1.md,
rows TR-FUNC-005/006/007/011/013/032) and the source forensic audit. No test
in this file invents a canonical rollup rule.
"""

from __future__ import annotations

from transelec_ingestion.status_rollups import (
    STATUS_ROLLUP_BASES,
    RolledRow,
    bucket_3way,
    estado_resumido_first_row,
    first_row_wins,
    hero_state,
    is_pending_row,
    owner_stage_from_row,
    owner_stage_legacy,
    pending_priority_legacy,
    pending_stage,
)


def _row(
    *,
    source_row_number: int,
    pmf: str = "MP001",
    predio_group_key: str = "MP001-1-1",
    estado: str | None = None,
    estado_resumido: str | None = None,
    numero_ingreso: str | None = None,
    tipo_propietario: str | None = None,
) -> RolledRow:
    return RolledRow(
        source_row_number=source_row_number,
        pmf=pmf,
        predio_group_key=predio_group_key,
        estado=estado,
        estado_resumido=estado_resumido,
        numero_ingreso=numero_ingreso,
        tipo_propietario=tipo_propietario,
    )


# ---------------------------------------------------------------------------
# first_row_wins — the shared "Map-insertion-order first row wins" mechanism
# ---------------------------------------------------------------------------


def test_first_row_wins_keeps_the_lowest_source_row_number_per_key() -> None:
    rows = [
        _row(source_row_number=5, pmf="MP001", estado_resumido="Tachado"),
        _row(source_row_number=2, pmf="MP001", estado_resumido="Aprobado"),
        _row(source_row_number=9, pmf="MP001", estado_resumido="Pendiente"),
    ]

    winners = first_row_wins(rows, key="pmf")

    assert winners["MP001"].source_row_number == 2
    assert winners["MP001"].estado_resumido == "Aprobado"


def test_first_row_wins_is_independent_of_input_list_order() -> None:
    """Whichever row has the smallest source_row_number wins, regardless of
    the order rows are supplied in (not just insertion/list order)."""

    in_order = [_row(source_row_number=1, pmf="MP001"), _row(source_row_number=2, pmf="MP001")]
    reversed_order = list(reversed(in_order))

    assert first_row_wins(in_order, key="pmf")["MP001"].source_row_number == 1
    assert first_row_wins(reversed_order, key="pmf")["MP001"].source_row_number == 1


def test_first_row_wins_groups_independently_by_predio_group_key() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="Aprobado"),
        _row(source_row_number=2, pmf="MP001", predio_group_key="B", estado_resumido="Pendiente"),
    ]

    winners = first_row_wins(rows, key="predio_group_key")

    assert set(winners) == {"A", "B"}
    assert winners["A"].estado_resumido == "Aprobado"
    assert winners["B"].estado_resumido == "Pendiente"


# ---------------------------------------------------------------------------
# estado_resumido_first_row — TR-FUNC-005/006/011
# ---------------------------------------------------------------------------


def test_estado_resumido_first_row_reads_the_winning_rows_field() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", estado_resumido="Aprobado"),
        _row(source_row_number=2, pmf="MP001", estado_resumido="Tachado"),
        _row(source_row_number=1, pmf="MP002", estado_resumido="En tramite"),
    ]

    result = estado_resumido_first_row(rows, key="pmf")

    assert result == {"MP001": "Aprobado", "MP002": "En tramite"}


# ---------------------------------------------------------------------------
# pending_priority_legacy — TR-FUNC-007/032 (isPendingPMF)
# ---------------------------------------------------------------------------


def test_is_pending_row_true_when_numero_ingreso_is_blank() -> None:
    assert is_pending_row(_row(source_row_number=1, numero_ingreso=None)) is True
    assert is_pending_row(_row(source_row_number=1, numero_ingreso="   ")) is True


def test_is_pending_row_true_when_estado_contains_rechaz_case_insensitive() -> None:
    assert (
        is_pending_row(_row(source_row_number=1, numero_ingreso="123", estado="RECHAZADO")) is True
    )
    assert (
        is_pending_row(_row(source_row_number=1, numero_ingreso="123", estado="En rechazo parcial"))
        is True
    )


def test_is_pending_row_false_when_ingreso_present_and_not_rejected() -> None:
    assert (
        is_pending_row(_row(source_row_number=1, numero_ingreso="123", estado="Aprobado")) is False
    )


def test_pending_priority_legacy_dedups_pmf_grain_first_row_wins() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", numero_ingreso=None),  # pending
        _row(source_row_number=2, pmf="MP001", numero_ingreso="9"),  # would not be pending
    ]

    result = pending_priority_legacy(rows, key="pmf")

    assert result == {"MP001": True}


def test_pending_priority_legacy_diverges_from_estado_resumido_first_row_for_the_same_row() -> None:
    """Reproduces the forensic audit's live-confirmed divergence: a PMF whose
    first row is 'Estado resumido: En tramite' (not Aprobado) but whose
    detailed Estado contains 'rechaz' is pending under one rule and merely
    'en tramite' under the other, for the exact same underlying row."""

    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            estado="Rechazado por CONAF",
            estado_resumido="En tramite",
            numero_ingreso="778",
        )
    ]

    assert estado_resumido_first_row(rows, key="pmf") == {"MP001": "En tramite"}
    assert pending_priority_legacy(rows, key="pmf") == {"MP001": True}


# ---------------------------------------------------------------------------
# owner_stage_legacy — TR-FUNC-013 (ownerStage())
# ---------------------------------------------------------------------------


def test_owner_stage_from_row_overrides_to_rechazado_when_estado_contains_rechaz() -> None:
    row = _row(source_row_number=1, estado="Recurso de Rechazo", estado_resumido="Aprobado")

    assert owner_stage_from_row(row) == "Rechazado"


def test_owner_stage_from_row_passes_through_estado_resumido_otherwise() -> None:
    row = _row(source_row_number=1, estado="En evaluacion", estado_resumido="En tramite")

    assert owner_stage_from_row(row) == "En tramite"


def test_owner_stage_legacy_dedups_predio_grain_first_row_wins() -> None:
    rows = [
        _row(
            source_row_number=1,
            predio_group_key="P1",
            estado="Aprobado sin observaciones",
            estado_resumido="Aprobado",
        ),
        _row(
            source_row_number=2,
            predio_group_key="P1",
            estado="Rechazado",
            estado_resumido="Tachado",
        ),
    ]

    result = owner_stage_legacy(rows, key="predio_group_key")

    # The first row (source_row_number=1) wins the dedup; its own estado does
    # not contain "rechaz", so no override applies.
    assert result == {"P1": "Aprobado"}


def test_owner_stage_legacy_can_disagree_with_estado_resumido_first_row() -> None:
    """The audit's documented internal inconsistency: the same predio is
    'Aprobado' under estado_resumido_first_row but 'Rechazado' under
    owner_stage_legacy, because the winning row's raw Estado contains
    "rechaz" even though its Estado resumido says Aprobado."""

    rows = [
        _row(
            source_row_number=1,
            predio_group_key="P1",
            estado="Rechazado, recurso en tramite",
            estado_resumido="Aprobado",
        )
    ]

    assert estado_resumido_first_row(rows, key="predio_group_key") == {"P1": "Aprobado"}
    assert owner_stage_legacy(rows, key="predio_group_key") == {"P1": "Rechazado"}


# ---------------------------------------------------------------------------
# pending_stage — TR-FUNC-032's 3-way heuristic (INFERENCE-quality, not one
# of the three named bases, but named and disclosed the same way)
# ---------------------------------------------------------------------------


def test_pending_stage_prepar_substring() -> None:
    assert pending_stage("En preparacion de antecedentes") == "preparacion"
    assert pending_stage("PREPARANDO RECURSO") == "preparacion"  # prepar wins even with recurso


def test_pending_stage_requires_both_recurso_and_rechaz() -> None:
    assert pending_stage("Recurso de reposicion por rechazo") == "recurso_rechazo"
    assert pending_stage("Recurso administrativo en curso") == "otros"  # no "rechaz"
    assert pending_stage("Solicitud denegada") == "otros"  # no "recurso", no "rechaz" substring


def test_pending_stage_default_bucket() -> None:
    assert pending_stage(None) == "otros"
    assert pending_stage("") == "otros"
    assert pending_stage("En evaluacion") == "otros"


# ---------------------------------------------------------------------------
# Chart bucketing helpers — TR-FUNC-009/010 (3-way) and TR-FUNC-011 (4-state)
# ---------------------------------------------------------------------------


def test_bucket_3way_maps_aprobado_and_en_tramite_and_merges_the_rest() -> None:
    assert bucket_3way("Aprobado") == "aprobado"
    assert bucket_3way("aprobado") == "aprobado"  # case-insensitive
    assert bucket_3way("En tramite") == "en_tramite"
    assert bucket_3way("En trámite") == "en_tramite"  # accented variant
    assert bucket_3way("Pendiente") == "pendiente_o_tachado"
    assert bucket_3way("Tachado") == "pendiente_o_tachado"
    assert bucket_3way(None) == "pendiente_o_tachado"
    assert bucket_3way("") == "pendiente_o_tachado"


def test_hero_state_maps_the_four_known_states_and_a_safety_net_bucket() -> None:
    assert hero_state("Aprobado") == "aprobado"
    assert hero_state("En tramite") == "en_tramite"
    assert hero_state("Pendiente") == "pendiente"
    assert hero_state("Tachado") == "tachado"
    assert hero_state(None) == "sin_estado"
    assert hero_state("algo-inesperado") == "sin_estado"


# ---------------------------------------------------------------------------
# Common interface — one lookup keyed by basis identifier
# ---------------------------------------------------------------------------


def test_status_rollup_bases_registry_exposes_exactly_the_three_named_bases() -> None:
    assert set(STATUS_ROLLUP_BASES) == {
        "estado_resumido_first_row",
        "pending_priority_legacy",
        "owner_stage_legacy",
    }
    assert STATUS_ROLLUP_BASES["estado_resumido_first_row"] is estado_resumido_first_row
    assert STATUS_ROLLUP_BASES["pending_priority_legacy"] is pending_priority_legacy
    assert STATUS_ROLLUP_BASES["owner_stage_legacy"] is owner_stage_legacy
