"""Unit tests for the pure KPI/chart aggregation behind GET /transelec/summary.

Every numeric formula from TR-FUNC-001-016 is exercised here against a
hand-built synthetic fixture, independent of the database. Row/PMF/predio
counts deliberately differ from the reviewed 14-Aug snapshot's 729/159/272,
so nothing here could pass by accident if a code path assumed those numbers.
"""

from __future__ import annotations

from dataclasses import fields

from transelec_ingestion.summary_view import SummaryInputRow, build_summary


def _row(
    *,
    source_row_number: int,
    pmf: str,
    predio_group_key: str,
    estado: str | None = None,
    estado_resumido: str | None = None,
    numero_ingreso: str | None = "OK-1",
    tipo_propietario: str | None = None,
    predio_ref: str | None = None,
    id_predio_unico: str | None = "id",
    superficie_corta: float | None = 1.0,
    rol: str | None = "R1",
    empresa: str | None = None,
    rol_ref: str | None = None,
) -> SummaryInputRow:
    return SummaryInputRow(
        source_row_number=source_row_number,
        pmf=pmf,
        predio_group_key=predio_group_key,
        estado=estado,
        estado_resumido=estado_resumido,
        numero_ingreso=numero_ingreso,
        tipo_propietario=tipo_propietario,
        predio_ref=predio_ref,
        id_predio_unico=id_predio_unico,
        superficie_corta=superficie_corta,
        rol=rol,
        empresa=empresa,
        rol_ref=rol_ref,
    )


def test_pmf_predio_rol_counts_are_distinct_counts_over_the_filtered_view() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", rol="R1"),
        _row(source_row_number=2, pmf="MP001", predio_group_key="A", rol="R1"),
        _row(source_row_number=3, pmf="MP002", predio_group_key="B", rol="R2"),
    ]

    summary = build_summary(rows)

    assert summary.pmf_count == 2  # TR-FUNC-001
    assert summary.predio_count == 2  # TR-FUNC-002
    assert summary.rol_count == 2  # TR-FUNC-003
    assert summary.row_count == 3


def test_predio_count_uses_predio_group_key_which_already_implements_the_fallback() -> None:
    """TR-FUNC-002: dedup by ID_Predo_Unico, composite fallback if blank.
    predio_group_key already IS that fallback (computed at projection time),
    so predio_count is simply COUNT(DISTINCT predio_group_key)."""

    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="MP001-1-1", id_predio_unico=None),
        _row(source_row_number=2, pmf="MP001", predio_group_key="MP001-1-1", id_predio_unico=None),
        _row(
            source_row_number=3,
            pmf="MP002",
            predio_group_key="real-id",
            id_predio_unico="real-id",
        ),
    ]

    summary = build_summary(rows)

    assert summary.predio_count == 2


def test_surface_total_sums_superficie_corta_excluding_blanks() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", superficie_corta=1.5),
        _row(source_row_number=2, pmf="MP002", predio_group_key="B", superficie_corta=None),
        _row(source_row_number=3, pmf="MP003", predio_group_key="C", superficie_corta=2.25),
    ]

    summary = build_summary(rows)

    assert summary.surface_total == 3.75  # TR-FUNC-004


def test_aprobados_and_en_tramite_use_estado_resumido_first_row_pmf_grain() -> None:
    rows = [
        # MP001: first row (lowest source_row_number) is Aprobado.
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="Aprobado"),
        _row(source_row_number=2, pmf="MP001", predio_group_key="A", estado_resumido="Tachado"),
        # MP002: single row, En tramite.
        _row(source_row_number=1, pmf="MP002", predio_group_key="B", estado_resumido="En tramite"),
    ]

    summary = build_summary(rows)

    assert summary.aprobados_pmf_count == 1  # TR-FUNC-005
    assert summary.en_tramite_pmf_count == 1  # TR-FUNC-006
    assert summary.basis_estado_resumido == "estado_resumido_first_row"


def test_pendientes_prioritarios_uses_pending_priority_legacy_and_can_diverge() -> None:
    """The audit's documented divergence: a PMF whose first row is
    'En tramite' under estado_resumido_first_row is nonetheless
    pending-priority because that same row's raw Estado contains 'rechaz'."""

    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            estado="Rechazado por CONAF",
            estado_resumido="En tramite",
            numero_ingreso="778",
        ),
        _row(
            source_row_number=1,
            pmf="MP002",
            predio_group_key="B",
            estado="Aprobado",
            estado_resumido="Aprobado",
            numero_ingreso="900",
        ),
    ]

    summary = build_summary(rows)

    assert summary.pendientes_prioritarios_pmf_count == 1  # TR-FUNC-007
    assert summary.aprobados_pmf_count == 1  # MP002 only
    assert summary.en_tramite_pmf_count == 1  # MP001, per estado_resumido_first_row
    assert summary.basis_pending_priority == "pending_priority_legacy"


def test_con_servidumbre_counts_distinct_predios_with_a_case_insensitive_match() -> None:
    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            tipo_propietario="Con SERVIDUMBRE firmada",
        ),
        _row(
            source_row_number=2,
            pmf="MP001",
            predio_group_key="A",  # same predio, second row: must not double count
            tipo_propietario="servidumbre",
        ),
        _row(
            source_row_number=1,
            pmf="MP002",
            predio_group_key="B",
            tipo_propietario="Propietario",
        ),
    ]

    summary = build_summary(rows)

    assert summary.con_servidumbre_predio_count == 1  # TR-FUNC-008


def test_charts_009_010_sum_to_the_matching_kpi_totals() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="Aprobado"),
        _row(source_row_number=1, pmf="MP002", predio_group_key="B", estado_resumido="En tramite"),
        _row(source_row_number=1, pmf="MP003", predio_group_key="C", estado_resumido="Pendiente"),
        _row(source_row_number=1, pmf="MP004", predio_group_key="D", estado_resumido="Tachado"),
    ]

    summary = build_summary(rows)

    by_predio = summary.avance_por_predio
    assert by_predio.aprobado + by_predio.en_tramite + by_predio.pendiente_o_tachado == (
        summary.predio_count
    )
    by_pmf = summary.avance_por_pmf
    assert by_pmf.aprobado + by_pmf.en_tramite + by_pmf.pendiente_o_tachado == summary.pmf_count
    assert by_predio.aprobado == 1
    assert by_predio.en_tramite == 1
    assert by_predio.pendiente_o_tachado == 2


def test_hero_011_four_state_predio_grain_sums_to_predio_count() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="Aprobado"),
        _row(source_row_number=1, pmf="MP002", predio_group_key="B", estado_resumido="En tramite"),
        _row(source_row_number=1, pmf="MP003", predio_group_key="C", estado_resumido="Pendiente"),
        _row(source_row_number=1, pmf="MP004", predio_group_key="D", estado_resumido="Tachado"),
        _row(source_row_number=1, pmf="MP005", predio_group_key="E", estado_resumido=None),
    ]

    summary = build_summary(rows)
    hero = summary.estado_resumido_hero_predio

    assert (
        hero.aprobado + hero.en_tramite + hero.pendiente + hero.tachado + hero.sin_estado
        == summary.predio_count
    )
    assert hero.sin_estado == 1


def test_predios_reforestacion_chips_are_distinct_non_blank_predio_ref_values() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", predio_ref="Fundo Norte"),
        _row(source_row_number=2, pmf="MP001", predio_group_key="A", predio_ref="Fundo Norte"),
        _row(source_row_number=3, pmf="MP002", predio_group_key="B", predio_ref=None),
        _row(source_row_number=4, pmf="MP003", predio_group_key="C", predio_ref="  "),
        _row(source_row_number=5, pmf="MP004", predio_group_key="D", predio_ref="Fundo Sur"),
    ]

    summary = build_summary(rows)

    assert sorted(summary.predios_reforestacion) == ["Fundo Norte", "Fundo Sur"]  # TR-FUNC-012


def test_calidad_filas_sin_id_predial_unico_is_a_row_grain_count() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", id_predio_unico=None),
        _row(source_row_number=2, pmf="MP001", predio_group_key="A", id_predio_unico="   "),
        _row(source_row_number=3, pmf="MP002", predio_group_key="B", id_predio_unico="real"),
    ]

    summary = build_summary(rows)

    assert summary.calidad_filas_sin_id_predial_unico == 2  # TR-FUNC-014, row-grain not deduped


def test_calidad_pmf_sin_numero_ingreso_uses_the_same_pmf_dedup_tie_break() -> None:
    """TR-FUNC-015: PMF-deduped (first-row-wins) count of blank N Ingreso —
    inherits the exact same tie-break as TR-FUNC-001."""

    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", numero_ingreso=None),
        _row(source_row_number=2, pmf="MP001", predio_group_key="A", numero_ingreso="999"),
        _row(source_row_number=1, pmf="MP002", predio_group_key="B", numero_ingreso="1"),
    ]

    summary = build_summary(rows)

    assert summary.calidad_pmf_sin_numero_ingreso == 1  # MP001's first row has no N Ingreso


def test_calidad_numero_resolucion_is_a_static_literal() -> None:
    summary = build_summary([_row(source_row_number=1, pmf="MP001", predio_group_key="A")])

    assert summary.calidad_numero_resolucion == "No disponible"  # TR-FUNC-016


def test_empty_filtered_view_produces_all_zero_counts_not_an_error() -> None:
    summary = build_summary([])

    assert summary.pmf_count == 0
    assert summary.predio_count == 0
    assert summary.surface_total == 0.0
    assert summary.predios_reforestacion == []


# ---------------------------------------------------------------------------
# PMF-grain headline — "¿Cuál es el estado de los planes de manejo?"
#
# Marianne answers Javier's recurring question off the `Estado resumido`
# column, and the 29-Jul Power BI summary she produces from it reports
# 101 + 56 + 3 = 160 against a stated total of 159, because one PMF appears
# under two summarized states. These tests pin the invariant that makes that
# impossible here: the headline is PMF-grain, and its buckets sum to the PMF
# total exactly.
# ---------------------------------------------------------------------------


def test_headline_is_pmf_grain_not_row_grain() -> None:
    """729 detail rows in the reviewed snapshot describe 159 plans.

    Counting rows would report the workbook's row count as the number of
    management plans — roughly four and a half times the real figure. The
    shape is reproduced here in miniature: 5 rows, 2 plans.
    """

    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="Aprobado"),
        _row(source_row_number=2, pmf="MP001", predio_group_key="B", estado_resumido="Aprobado"),
        _row(source_row_number=3, pmf="MP001", predio_group_key="C", estado_resumido="Aprobado"),
        _row(source_row_number=4, pmf="MP002", predio_group_key="D", estado_resumido="En tramite"),
        _row(source_row_number=5, pmf="MP002", predio_group_key="E", estado_resumido="En tramite"),
    ]

    summary = build_summary(rows)

    assert summary.row_count == 5
    assert summary.pmf_count == 2
    assert summary.estado_resumido_pmf.aprobado == 1
    assert summary.estado_resumido_pmf.en_tramite == 1


def test_headline_buckets_sum_exactly_to_the_pmf_total() -> None:
    """The arithmetic the Power BI summary gets wrong, asserted directly."""

    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="Aprobado"),
        _row(source_row_number=2, pmf="MP002", predio_group_key="B", estado_resumido="En tramite"),
        _row(source_row_number=3, pmf="MP003", predio_group_key="C", estado_resumido="Tachado"),
        _row(source_row_number=4, pmf="MP004", predio_group_key="D", estado_resumido="Pendiente"),
        _row(source_row_number=5, pmf="MP005", predio_group_key="E", estado_resumido=None),
    ]

    summary = build_summary(rows)
    hero = summary.estado_resumido_pmf

    assert (
        hero.aprobado + hero.en_tramite + hero.pendiente + hero.tachado + hero.sin_estado
        == summary.pmf_count
        == 5
    )


def test_a_pmf_with_two_summarized_states_is_counted_once_not_twice() -> None:
    """The MP015/MP022 case: conflicting evidence, one headline bucket.

    The reviewed 14-Aug snapshot's conflicting PMF is MP022 (`En tramite`
    on rows 293-306 and 308-314, `Tachado` on row 307, detailed `Estado`
    `Rechazado` throughout); the 29-Jul summary's is MP015. Same shape, so
    the rule is pinned rather than either identifier.
    """

    rows = [
        _row(
            source_row_number=1,
            pmf="MP015",
            predio_group_key="A",
            estado="Rechazado",
            estado_resumido="En tramite",
        ),
        _row(
            source_row_number=2,
            pmf="MP015",
            predio_group_key="B",
            estado="Rechazado",
            estado_resumido="Aprobado",
        ),
        _row(source_row_number=3, pmf="MP016", predio_group_key="C", estado_resumido="Aprobado"),
    ]

    summary = build_summary(rows)
    hero = summary.estado_resumido_pmf

    assert summary.pmf_count == 2
    # Not 1 approved + 1 in process + 1 approved = 3 across 2 plans.
    assert (hero.aprobado, hero.en_tramite) == (1, 1)
    assert hero.aprobado + hero.en_tramite + hero.pendiente + hero.tachado + hero.sin_estado == 2


def test_the_conflict_is_reported_rather_than_silently_resolved() -> None:
    rows = [
        _row(
            source_row_number=7,
            pmf="MP015",
            predio_group_key="A",
            estado="Rechazado",
            estado_resumido="En tramite",
        ),
        _row(
            source_row_number=8,
            pmf="MP015",
            predio_group_key="B",
            estado="Rechazado",
            estado_resumido="Aprobado",
        ),
        _row(source_row_number=9, pmf="MP016", predio_group_key="C", estado_resumido="Aprobado"),
    ]

    conflicts = build_summary(rows).calidad_pmf_estado_resumido_conflictivo

    assert [conflict.pmf for conflict in conflicts] == ["MP015"]
    conflict = conflicts[0]
    assert conflict.valores == ["En tramite", "Aprobado"]
    assert conflict.canonico == "En tramite"  # first source row wins, the repository's contract
    assert conflict.estado_detalle == "Rechazado"
    assert conflict.source_row_number == 7


def test_a_consistent_pmf_is_not_reported_as_a_conflict() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="Aprobado"),
        _row(source_row_number=2, pmf="MP001", predio_group_key="B", estado_resumido="Aprobado"),
    ]

    assert build_summary(rows).calidad_pmf_estado_resumido_conflictivo == []


def test_casing_variants_of_one_state_are_not_two_conflicting_states() -> None:
    """`En Evaluacion` and `En evaluacion` are one state, not two.

    Normalisation reconciles the spelling; the raw value still reaches the
    caller as the label.
    """

    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            estado="En Evaluacion",
            estado_resumido="En tramite",
        ),
        _row(
            source_row_number=2,
            pmf="MP001",
            predio_group_key="B",
            estado="En evaluacion",
            estado_resumido="En Tramite",
        ),
    ]

    summary = build_summary(rows)

    assert summary.calidad_pmf_estado_resumido_conflictivo == []
    assert [(item.label, item.count) for item in summary.estado_detalle_pmf] == [
        ("En Evaluacion", 1)
    ]


def test_estado_detalle_breakdown_is_pmf_grain_and_sums_to_the_pmf_total() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado="Aprobado"),
        _row(source_row_number=2, pmf="MP001", predio_group_key="B", estado="Aprobado"),
        _row(source_row_number=3, pmf="MP002", predio_group_key="C", estado="Recurso jerarquico"),
        _row(source_row_number=4, pmf="MP003", predio_group_key="D", estado="Aprobado"),
    ]

    summary = build_summary(rows)

    assert sum(item.count for item in summary.estado_detalle_pmf) == summary.pmf_count == 3
    assert [(item.label, item.count) for item in summary.estado_detalle_pmf] == [
        ("Aprobado", 2),
        ("Recurso jerarquico", 1),
    ]


def test_a_missing_detailed_state_keeps_its_own_bucket_rather_than_vanishing() -> None:
    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado=None),
        _row(source_row_number=2, pmf="MP002", predio_group_key="B", estado="Aprobado"),
    ]

    summary = build_summary(rows)

    assert sum(item.count for item in summary.estado_detalle_pmf) == summary.pmf_count == 2
    assert any(item.label is None for item in summary.estado_detalle_pmf)


def test_company_subtotals_reconcile_to_the_overall_total() -> None:
    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            empresa="Campo digital",
            estado_resumido="Aprobado",
        ),
        _row(
            source_row_number=2,
            pmf="MP002",
            predio_group_key="B",
            empresa="Campo digital",
            estado_resumido="En tramite",
        ),
        _row(
            source_row_number=3,
            pmf="MP003",
            predio_group_key="C",
            empresa="Ecores",
            estado_resumido="Aprobado",
        ),
        _row(
            source_row_number=4,
            pmf="MP004",
            predio_group_key="D",
            empresa="Ecores",
            estado_resumido="Tachado",
        ),
    ]

    summary = build_summary(rows)

    assert sum(item.pmf_count for item in summary.por_empresa) == summary.pmf_count == 4
    for attribute in ("aprobado", "en_tramite", "pendiente", "tachado", "sin_estado"):
        assert sum(
            getattr(item.estado_resumido, attribute) for item in summary.por_empresa
        ) == getattr(summary.estado_resumido_pmf, attribute)


def test_company_is_attributed_per_pmf_not_per_row() -> None:
    """A PMF whose rows straddle two companies still lands in exactly one.

    The reviewed snapshot has no such PMF, which is precisely why the
    invariant needs a test rather than the data's goodwill.
    """

    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            empresa="Campo digital",
            estado_resumido="Aprobado",
        ),
        _row(
            source_row_number=2,
            pmf="MP001",
            predio_group_key="B",
            empresa="Ecores",
            estado_resumido="Aprobado",
        ),
    ]

    summary = build_summary(rows)

    assert sum(item.pmf_count for item in summary.por_empresa) == summary.pmf_count == 1
    assert [(item.empresa, item.pmf_count) for item in summary.por_empresa] == [
        ("Campo digital", 1)
    ]


def test_a_blank_company_keeps_its_own_bucket_rather_than_being_dropped() -> None:
    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            empresa=None,
            estado_resumido="Aprobado",
        ),
        _row(
            source_row_number=2,
            pmf="MP002",
            predio_group_key="B",
            empresa="Ecores",
            estado_resumido="Aprobado",
        ),
    ]

    summary = build_summary(rows)

    assert sum(item.pmf_count for item in summary.por_empresa) == 2
    assert None in [item.empresa for item in summary.por_empresa]


# ---------------------------------------------------------------------------
# Reforestación — what the source can and cannot answer
# ---------------------------------------------------------------------------


def test_reforestation_count_excludes_the_sin_reforestacion_sentinel() -> None:
    """`Sin reforestacion` is the absence of a property, not a property."""

    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", predio_ref="Ref001_Rubi"),
        _row(
            source_row_number=2, pmf="MP002", predio_group_key="B", predio_ref="Sin reforestacion"
        ),
        _row(
            source_row_number=3, pmf="MP003", predio_group_key="C", predio_ref="Ref005_ Kompatzki"
        ),
        _row(source_row_number=4, pmf="MP004", predio_group_key="D", predio_ref=None),
    ]

    summary = build_summary(rows)

    assert summary.reforestacion.predio_ref_count == 2
    assert summary.reforestacion.predio_ref_labels == ["Ref001_Rubi", "Ref005_ Kompatzki"]
    assert summary.reforestacion.sentinel_row_count == 1
    assert summary.predios_reforestacion == summary.reforestacion.predio_ref_labels


def test_reforestation_metric_states_the_field_it_counts() -> None:
    summary = build_summary(
        [_row(source_row_number=1, pmf="MP001", predio_group_key="A", predio_ref="Ref001_Rubi")]
    )

    assert "Predio Ref" in summary.reforestacion.definicion
    assert "Sin reforestacion" in summary.reforestacion.definicion


def test_labels_naming_more_than_one_property_are_flagged_not_counted_as_one() -> None:
    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            predio_ref="Ref036_ Reyes y Ref037_ Reyes",
        ),
        _row(source_row_number=2, pmf="MP002", predio_group_key="B", predio_ref="Rubi + Marin"),
        _row(source_row_number=3, pmf="MP003", predio_group_key="C", predio_ref="Ref001_Rubi"),
    ]

    summary = build_summary(rows)

    assert summary.reforestacion.etiquetas_compuestas == [
        "Ref036_ Reyes y Ref037_ Reyes",
        "Rubi + Marin",
    ]


def test_no_owner_count_is_derived_from_tipo_de_propietario_or_from_surnames() -> None:
    """`Tipo de propietario` is tenure, and `Predio Ref` surnames are text.

    Neither identifies an owner, so the owner figure is a literal saying so
    — never a number, and never zero, which would read as "there are none".
    """

    rows = [
        _row(
            source_row_number=1,
            pmf="MP001",
            predio_group_key="A",
            tipo_propietario="Servidumbre firmada",
            predio_ref="Ref025_ Contreras",
        ),
        _row(
            source_row_number=2,
            pmf="MP002",
            predio_group_key="B",
            tipo_propietario="Poseedor",
            predio_ref="Ref026_ Contreras",
        ),
        _row(
            source_row_number=3,
            pmf="MP003",
            predio_group_key="C",
            tipo_propietario="BNUP",
            predio_ref="Ref_ Hermanos Held",
        ),
    ]

    summary = build_summary(rows)

    assert summary.reforestacion.propietarios == "No disponible en el origen"

    # No numeric owner figure exists anywhere in the result — not here, and
    # not under some other name elsewhere in the summary.
    numeric_owner_fields = [
        field.name
        for field in fields(summary)
        if ("propietario" in field.name or "owner" in field.name)
        and isinstance(getattr(summary, field.name), int)
    ]
    assert numeric_owner_fields == []


def test_empty_filtered_scope_yields_a_populated_shape_not_none() -> None:
    summary = build_summary([])

    hero = summary.estado_resumido_pmf
    assert hero.aprobado + hero.en_tramite + hero.pendiente + hero.tachado + hero.sin_estado == 0
    assert summary.estado_detalle_pmf == []
    assert summary.por_empresa == []
    assert summary.calidad_pmf_estado_resumido_conflictivo == []
    assert summary.reforestacion.predio_ref_count == 0
    assert summary.reforestacion.propietarios == "No disponible en el origen"


def test_sparse_id_pmf_is_not_the_identity_used_for_pmf_grain() -> None:
    """`ID_PMF` is populated on 159 of 729 rows in the reviewed snapshot.

    Grouping on it would drop every plan whose first row leaves it blank.
    `SummaryInputRow` does not carry it at all: identity is `PMF`, which the
    source contract guarantees non-blank on every business row.
    """

    assert "id_pmf" not in SummaryInputRow.__annotations__


def test_status_buckets_carry_the_raw_spellings_that_reproduce_them() -> None:
    """A status card links to the filter that reproduces its own count.

    The bucket is a normalized state; the Explorador filters on the literal
    source value, so both spellings of one state have to travel with it.
    """

    rows = [
        _row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido="En tramite"),
        _row(source_row_number=2, pmf="MP002", predio_group_key="B", estado_resumido="En trámite"),
        _row(source_row_number=3, pmf="MP003", predio_group_key="C", estado_resumido="Aprobado"),
    ]

    valores = build_summary(rows).estado_resumido_valores

    assert valores["en_tramite"] == ["En tramite", "En trámite"]
    assert valores["aprobado"] == ["Aprobado"]


def test_a_blank_summarized_state_contributes_no_filter_value() -> None:
    """`sin_estado` cannot be reproduced by an equality filter, so it offers
    none — rather than a filter that would silently match nothing."""

    rows = [_row(source_row_number=1, pmf="MP001", predio_group_key="A", estado_resumido=None)]

    summary = build_summary(rows)

    assert summary.estado_resumido_pmf.sin_estado == 1
    assert summary.estado_resumido_valores == {}
