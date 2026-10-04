"""Unit tests for ``lifecycle_pmf_v1`` — the «Estado» section's basis.

Synthetic PMF codes only. The labels are the vocabulary the 2026-10-04 Estado
spec records for the 30-Sept-2026 planilla, also spelled with the case,
accent and whitespace variants a workbook really carries.
"""

from __future__ import annotations

import pytest

from transelec_ingestion.lifecycle_view import (
    CLOSED_GROUPS,
    GROUP_ORDER,
    LIFECYCLE_BASIS,
    STEP_ORDER,
    LifecycleInputRow,
    build_lifecycle,
    classify_first_row,
)
from transelec_ingestion.status_rollups import RolledRow, first_row_wins


def _row(
    *,
    source_row_number: int = 2,
    pmf: str = "MP001",
    estado: str | None = "En evaluacion",
    estado_resumido: str | None = "En tramite",
    numero_ingreso: str | None = "ING-1",
    numero_ingreso_2: str | None = None,
) -> LifecycleInputRow:
    return LifecycleInputRow(
        source_row_number=source_row_number,
        pmf=pmf,
        estado=estado,
        estado_resumido=estado_resumido,
        numero_ingreso=numero_ingreso,
        numero_ingreso_2=numero_ingreso_2,
    )


@pytest.mark.parametrize(
    ("resumido", "estado", "expected"),
    [
        ("Aprobado", "Aprobado", ("aprobado", None, None)),
        ("Aprobado", "Recurso reposicion aprobado", ("aprobado", None, None)),
        ("Aprobado", "Recurso jerarquico aprobado", ("aprobado", None, None)),
        ("Descartado", "Descartado", ("descartado", None, None)),
        ("Desistido", "Desistido", ("desistido", None, None)),
        ("En tramite", "En Evaluacion", ("en_tramite", "en_evaluacion", None)),
        ("En tramite", "Rechazado", ("en_tramite", "rechazado_esperando_recurso", None)),
        (
            "En tramite",
            "Recurso jerarquico rechazado",
            ("en_tramite", "rechazado_esperando_recurso", None),
        ),
        ("En tramite", "Recurso reposicion", ("en_tramite", "en_recurso_reposicion", None)),
        ("Rechazado", "Recurso jerarquico", ("en_tramite", "en_recurso_jerarquico", None)),
    ],
)
def test_each_known_label_lands_in_its_group_and_step(
    resumido: str, estado: str, expected: tuple[str, str | None, str | None]
) -> None:
    assert classify_first_row(_row(estado_resumido=resumido, estado=estado)) == expected


def test_a_rejection_is_never_terminal() -> None:
    group, step, reason = classify_first_row(_row(estado_resumido="Rechazado", estado="Rechazado"))

    assert (group, step, reason) == ("en_tramite", "rechazado_esperando_recurso", None)
    assert group not in CLOSED_GROUPS


def test_case_accents_and_spaces_do_not_matter() -> None:
    assert classify_first_row(_row(estado_resumido="EN TRÁMITE", estado="  En   Evaluación ")) == (
        "en_tramite",
        "en_evaluacion",
        None,
    )
    assert classify_first_row(_row(estado_resumido="en trámite", estado="Recurso Jerárquico")) == (
        "en_tramite",
        "en_recurso_jerarquico",
        None,
    )


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_no_ingreso_at_all_is_sin_ingreso_whatever_estado_says(blank: str | None) -> None:
    row = _row(estado="En evaluacion", numero_ingreso=blank, numero_ingreso_2=blank)

    assert classify_first_row(row) == ("en_tramite", "sin_ingreso", None)


def test_a_second_ingreso_alone_is_not_sin_ingreso() -> None:
    row = _row(estado="Recurso reposicion", numero_ingreso=None, numero_ingreso_2="ING-1-R")

    assert classify_first_row(row) == ("en_tramite", "en_recurso_reposicion", None)


@pytest.mark.parametrize("resumido", ["Tachado", "Pendiente", None, ""])
def test_an_unknown_resumido_is_unclassified_not_guessed(resumido: str | None) -> None:
    assert classify_first_row(_row(estado_resumido=resumido)) == (
        "sin_clasificar",
        None,
        "resumido_desconocido",
    )


@pytest.mark.parametrize("estado", ["Rechazado por CONAF", "En preparacion", None])
def test_an_unknown_estado_inside_en_tramite_is_unclassified(estado: str | None) -> None:
    assert classify_first_row(_row(estado_resumido="En tramite", estado=estado)) == (
        "sin_clasificar",
        None,
        "estado_desconocido",
    )


@pytest.mark.parametrize(
    ("resumido", "estado"),
    [
        ("Aprobado", "Recurso reposicion"),  # approved summary, open recurso
        ("Aprobado", None),
        ("Aprobado", "Desaprobado"),  # «aprobado» is matched as a word only
        ("En tramite", "Recurso reposicion aprobado"),
        ("Rechazado", "Aprobado"),
        ("Descartado", "Rechazado"),
        ("Desistido", "Descartado"),  # never merged with each other
    ],
)
def test_a_contradiction_between_estado_and_resumido_is_unclassified(
    resumido: str, estado: str | None
) -> None:
    assert classify_first_row(_row(estado_resumido=resumido, estado=estado)) == (
        "sin_clasificar",
        None,
        "estado_y_resumido_no_coinciden",
    )


def test_the_representative_row_is_the_one_first_row_wins_picks() -> None:
    rows = [
        _row(source_row_number=9, estado="Aprobado", estado_resumido="Aprobado"),
        _row(source_row_number=4, estado="Rechazado", estado_resumido="En tramite"),
        _row(source_row_number=6, estado="En evaluacion", estado_resumido="En tramite"),
    ]
    rolled = [
        RolledRow(
            source_row_number=row.source_row_number,
            pmf=row.pmf,
            predio_group_key="key",
            estado=row.estado,
            estado_resumido=row.estado_resumido,
            numero_ingreso=row.numero_ingreso,
        )
        for row in rows
    ]

    (entry,) = build_lifecycle(rows).pmfs

    assert entry.source_row_number == first_row_wins(rolled, key="pmf")["MP001"].source_row_number
    assert entry.source_row_number == 4
    assert (entry.group, entry.step) == ("en_tramite", "rechazado_esperando_recurso")


def test_rows_that_disagree_keep_the_first_row_and_are_flagged() -> None:
    summary = build_lifecycle(
        [
            _row(source_row_number=2, estado="Aprobado", estado_resumido="Aprobado"),
            _row(
                source_row_number=3,
                estado="Recurso reposicion aprobado",
                estado_resumido="Aprobado",
            ),
            _row(source_row_number=5, pmf="MP002"),
        ]
    )

    by_pmf = {entry.pmf: entry for entry in summary.pmfs}
    assert by_pmf["MP001"].group == "aprobado"
    assert by_pmf["MP001"].flags == ("filas_no_coinciden",)
    assert by_pmf["MP002"].flags == ()


def test_rows_that_differ_only_in_spelling_are_not_flagged() -> None:
    summary = build_lifecycle(
        [
            _row(source_row_number=2, estado="En Evaluacion", estado_resumido="En tramite"),
            _row(source_row_number=3, estado="en evaluación", estado_resumido="EN TRÁMITE"),
        ]
    )

    assert summary.pmfs[0].flags == ()


def test_counts_cover_every_group_and_step_and_pmfs_follow_source_order() -> None:
    summary = build_lifecycle(
        [
            _row(
                source_row_number=7, pmf="MP003", estado="Descartado", estado_resumido="Descartado"
            ),
            _row(source_row_number=2, pmf="MP001", estado="Rechazado"),
            _row(source_row_number=4, pmf="MP002", estado="Aprobado", estado_resumido="Aprobado"),
        ]
    )

    assert summary.basis == LIFECYCLE_BASIS == "lifecycle_pmf_v1"
    assert summary.total_pmf_count == 3
    assert tuple(summary.groups) == GROUP_ORDER
    assert tuple(summary.steps) == STEP_ORDER
    assert summary.groups == {
        "aprobado": 1,
        "en_tramite": 1,
        "descartado": 1,
        "desistido": 0,
        "sin_clasificar": 0,
    }
    assert summary.steps["rechazado_esperando_recurso"] == 1
    assert sum(summary.steps.values()) == 1
    assert [entry.pmf for entry in summary.pmfs] == ["MP001", "MP002", "MP003"]


def test_no_rows_is_an_empty_summary_not_an_error() -> None:
    summary = build_lifecycle([])

    assert summary.total_pmf_count == 0
    assert summary.pmfs == ()
    assert set(summary.groups.values()) == {0}


def test_closed_groups_are_exactly_the_terminal_ones() -> None:
    assert frozenset({"aprobado", "descartado", "desistido"}) == CLOSED_GROUPS
