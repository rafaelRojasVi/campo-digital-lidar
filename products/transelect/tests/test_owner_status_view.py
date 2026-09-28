"""Unit tests for TR-FUNC-013's owner-status table (predio-grain).

Ships Javier's existing ``ownerStage()`` legacy rule under the explicit
``owner_stage_legacy`` basis identifier — this does not resolve TR-OPEN-01.
"""

from __future__ import annotations

from transelec_ingestion.owner_status_view import OwnerStatusInputRow, build_owner_status


def _row(
    *,
    source_row_number: int,
    predio_group_key: str,
    tipo_propietario: str | None,
    estado: str | None = None,
    estado_resumido: str | None = None,
) -> OwnerStatusInputRow:
    return OwnerStatusInputRow(
        source_row_number=source_row_number,
        predio_group_key=predio_group_key,
        pmf="MP001",
        tipo_propietario=tipo_propietario,
        estado=estado,
        estado_resumido=estado_resumido,
        numero_ingreso="1",
    )


def test_groups_predio_grain_representative_rows_by_owner_type_and_stage() -> None:
    rows = [
        _row(
            source_row_number=1,
            predio_group_key="A",
            tipo_propietario="Empresa",
            estado_resumido="Aprobado",
        ),
        _row(
            source_row_number=1,
            predio_group_key="B",
            tipo_propietario="Empresa",
            estado_resumido="En tramite",
        ),
        _row(
            source_row_number=1,
            predio_group_key="C",
            tipo_propietario="Persona natural",
            estado_resumido="Aprobado",
        ),
    ]

    result = build_owner_status(rows)

    assert result.basis == "owner_stage_legacy"
    counts = {(row.tipo_propietario, row.owner_stage): row.predio_count for row in result.rows}
    assert counts[("Empresa", "Aprobado")] == 1
    assert counts[("Empresa", "En tramite")] == 1
    assert counts[("Persona natural", "Aprobado")] == 1
    assert result.total_predio_count == 3


def test_rechaz_override_applies_to_the_representative_row_only() -> None:
    """A predio's second row containing "rechaz" must NOT override the
    table when the first (winning) row does not."""

    rows = [
        _row(
            source_row_number=1,
            predio_group_key="A",
            tipo_propietario="Empresa",
            estado="Aprobado sin observaciones",
            estado_resumido="Aprobado",
        ),
        _row(
            source_row_number=2,
            predio_group_key="A",
            tipo_propietario="Empresa",
            estado="Rechazado",
            estado_resumido="Tachado",
        ),
    ]

    result = build_owner_status(rows)

    assert [(row.tipo_propietario, row.owner_stage, row.predio_count) for row in result.rows] == [
        ("Empresa", "Aprobado", 1)
    ]


def test_owner_stage_can_disagree_with_estado_resumido_for_the_same_predio() -> None:
    """The documented internal inconsistency: this table shows "Rechazado"
    for a predio whose Estado resumido says Aprobado, because the winning
    row's raw Estado contains "rechaz"."""

    rows = [
        _row(
            source_row_number=1,
            predio_group_key="A",
            tipo_propietario="Empresa",
            estado="Rechazado, recurso en tramite",
            estado_resumido="Aprobado",
        )
    ]

    result = build_owner_status(rows)

    assert result.rows[0].owner_stage == "Rechazado"


def test_empty_input_produces_no_rows() -> None:
    result = build_owner_status([])

    assert result.rows == []
    assert result.total_predio_count == 0
