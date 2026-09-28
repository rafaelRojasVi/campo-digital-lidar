import datetime as dt

from transelec_ingestion.aef_view import AefInputRow, LabelCount, build_aef_summary


def _row(number: int, pmf: str, **values: object) -> AefInputRow:
    fields: dict[str, object] = {
        "aef": None,
        "quien_solicita": None,
        "fecha_solicitud": None,
        "fecha_corta": None,
        "fecha_termino": None,
    }
    fields.update(values)
    return AefInputRow(source_row_number=number, pmf=pmf, **fields)  # type: ignore[arg-type]


def test_pmf_value_comes_from_its_source_row_and_rows_are_not_filled() -> None:
    rows = [
        _row(2, "BN001", aef="Presentado", fecha_corta=dt.date(2025, 12, 1)),
        _row(3, "BN001"),
        _row(4, "BN001"),
        _row(5, "MP020", aef="Presentado", quien_solicita="Persona A"),
        _row(6, "PL001"),
    ]

    summary = build_aef_summary(rows)

    # Row-level counts are unchanged: blank rows stay blank.
    assert (summary.row_count, summary.rows_with_aef, summary.rows_with_quien_solicita) == (5, 2, 1)
    assert summary.tracked_row_numbers == (2, 5)
    # PMF level: BN001's AEF is the value on row 2, stated with that row.
    assert (summary.pmf_count, summary.pmf_with_tracking, summary.pmf_with_aef) == (3, 2, 2)
    bn001 = next(record for record in summary.pmfs if record.pmf == "BN001")
    assert (bn001.total_rows, bn001.rows_with_aef, bn001.source_row_numbers) == (3, 1, (2, 3, 4))
    assert (bn001.fields["aef"].status, bn001.fields["aef"].value) == ("value", "Presentado")
    assert bn001.fields["aef"].source_rows == (2,)
    assert bn001.fields["fecha_corta"].value == dt.date(2025, 12, 1)
    assert bn001.fields["quien_solicita"].status == "blank"
    assert not bn001.has_conflict
    # PL001 has no tracking at all: not listed.
    assert [record.pmf for record in summary.pmfs] == ["BN001", "MP020"]


def test_conflicting_values_within_a_pmf_are_reported_not_chosen() -> None:
    rows = [
        _row(2, "A", aef="Presentado", quien_solicita="Persona A"),
        _row(3, "A", aef="Solicitado, se puede cortar"),
        _row(4, "B", aef="Presentado"),
    ]

    summary = build_aef_summary(rows)

    record = summary.pmfs[0]
    assert record.has_conflict
    assert (record.fields["aef"].status, record.fields["aef"].value) == ("conflict", None)
    assert [(v.value, v.source_rows) for v in record.fields["aef"].variants] == [
        ("Presentado", (2,)),
        ("Solicitado, se puede cortar", (3,)),
    ]
    # The requester has one value; the AEF conflict does not affect it.
    assert record.fields["quien_solicita"].value == "Persona A"
    assert summary.pmf_with_conflict == 1
    assert summary.pmf_conflicts_by_field["aef"] == 1
    # A conflicting PMF is not counted under either value.
    assert summary.pmf_por_aef == (LabelCount("Presentado", 1),)
    # Row-level counts still see both rows.
    assert summary.por_aef == (
        LabelCount("Presentado", 2),
        LabelCount("Solicitado, se puede cortar", 1),
    )


def test_unresolved_text_in_a_date_field_is_kept_and_never_matches_a_date() -> None:
    rows = [
        _row(2, "A", fecha_termino=dt.date(2026, 9, 1)),
        _row(
            3,
            "A",
            text_dates={"fecha_termino": {"raw": "-", "resolution": "placeholder", "parsed": None}},
        ),
        _row(
            4,
            "B",
            text_dates={
                "fecha_corta": {
                    "raw": "01-08-2026 02-08-2026",
                    "resolution": "multiple_dates",
                    "parsed": None,
                }
            },
        ),
    ]

    summary = build_aef_summary(rows)

    a, b = summary.pmfs
    assert a.fields["fecha_termino"].status == "conflict"
    assert (b.fields["fecha_corta"].status, b.fields["fecha_corta"].value) == (
        "value",
        "01-08-2026 02-08-2026",
    )
    assert summary.rows_with_fecha_corta == 1


def test_filtered_scope_uses_all_rows_of_the_pmf_for_its_values() -> None:
    all_rows = [
        _row(2, "A", aef="Presentado"),
        _row(3, "A"),
        _row(4, "B"),
    ]

    summary = build_aef_summary([all_rows[1]], pmf_rows=all_rows)

    # Only row 3 is in scope and it is blank, but PMF A's AEF is on row 2.
    assert summary.rows_with_aef == 0
    assert summary.rows_with_any_tracking == 0
    assert [(r.pmf, r.fields["aef"].value, r.fields["aef"].source_rows) for r in summary.pmfs] == [
        ("A", "Presentado", (2,))
    ]


def test_blank_requester_is_counted_as_blank_not_dropped() -> None:
    rows = [
        _row(2, "A", aef="Presentado", quien_solicita="Persona A"),
        _row(3, "B", aef="Presentado"),
        _row(4, "C", aef="Solicitado, se puede cortar", quien_solicita="Persona A"),
    ]

    summary = build_aef_summary(rows)

    assert summary.por_aef == (
        LabelCount("Presentado", 2),
        LabelCount("Solicitado, se puede cortar", 1),
    )
    assert summary.por_solicitante == (LabelCount("Persona A", 2), LabelCount(None, 1))
    assert summary.pmf_por_solicitante == (LabelCount("Persona A", 2), LabelCount(None, 1))


def test_a_row_with_only_dates_is_tracked_and_chronology_is_counted() -> None:
    rows = [
        _row(
            2,
            "A",
            fecha_solicitud=dt.date(2026, 8, 20),
            fecha_corta=dt.date(2026, 8, 19),
        ),
        _row(3, "B", aef="   "),
    ]

    summary = build_aef_summary(rows)

    assert summary.rows_with_any_tracking == 1
    assert summary.rows_with_aef == 0
    assert summary.rows_with_chronology_warning == 1
    assert summary.pmf_with_chronology_warning == 1
    assert summary.pmfs[0].chronology_flags == ("cronologia_corta_antes_de_solicitud",)
    assert summary.por_aef == (LabelCount(None, 1),)


def test_pmf_chronology_combines_dates_from_different_rows() -> None:
    rows = [
        _row(2, "A", fecha_solicitud=dt.date(2026, 8, 20)),
        _row(3, "A", fecha_corta=dt.date(2026, 8, 19)),
    ]

    summary = build_aef_summary(rows)

    # No single row is out of order, but the PMF's dates are.
    assert summary.rows_with_chronology_warning == 0
    assert summary.pmfs[0].chronology_flags == ("cronologia_corta_antes_de_solicitud",)
