"""The web-edit field registry and its comparison rule (spec §2)."""

from __future__ import annotations

import datetime as dt

import pytest

from transelec_ingestion.field_overrides import (
    EDITABLE_BY_NAME,
    EDITABLE_FIELDS,
    MAX_TEXT_LENGTH,
    OverrideValueError,
    cell_signature,
    comparable,
    display,
    normalize_text,
    note_text,
    parse_value,
    shown_value,
    value_signature,
)
from transelec_ingestion.resumen_layout import FIELD_BY_NAME

TEXT = EDITABLE_BY_NAME["estado_resumido"]
DATE = EDITABLE_BY_NAME["fecha_ingreso"]


def test_registry_is_the_eleven_fields_of_the_spec() -> None:
    assert [field.name for field in EDITABLE_FIELDS] == [
        "estado",
        "estado_resumido",
        "tipo_rechazo",
        "reingreso_tec",
        "reingreso_legal",
        "reingreso_recrep",
        "fecha_ingreso",
        "numero_ingreso",
        "fecha_90_dias",
        "fecha_ingreso_2",
        "numero_ingreso_2",
    ]


def test_registry_kinds_and_labels_come_from_the_contract() -> None:
    for field in EDITABLE_FIELDS:
        assert field.kind == FIELD_BY_NAME[field.name].kind
        assert field.label == FIELD_BY_NAME[field.name].header


@pytest.mark.parametrize("name", ["pmf", "rol", "numero_predio", "numero_area_corta", "hoy"])
def test_identity_and_formula_fields_are_not_editable(name: str) -> None:
    assert name not in EDITABLE_BY_NAME


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("En tramite", "En tramite"),
        ("  En   tramite \t", "En tramite"),
        ("En\ntramite\r\n", "En tramite"),
        ("", None),
        (" \t\n ", None),
        (None, None),
    ],
)
def test_normalize_text_trims_and_collapses_ascii_whitespace(
    raw: str | None, expected: str | None
) -> None:
    assert normalize_text(raw) == expected


def test_normalize_text_keeps_case() -> None:
    assert normalize_text("aprobado") != normalize_text("Aprobado")
    assert normalize_text("En tramite") == "En tramite"


def test_parse_value_reads_dates_and_text() -> None:
    assert parse_value(DATE, "2026-03-12") == dt.date(2026, 3, 12)
    assert parse_value(DATE, "") is None
    assert parse_value(TEXT, "  Aprobado ") == "Aprobado"
    assert parse_value(TEXT, None) is None


@pytest.mark.parametrize("raw", ["12-03-2026", "2026-02-30", "mañana"])
def test_parse_value_rejects_malformed_dates(raw: str) -> None:
    with pytest.raises(OverrideValueError):
        parse_value(DATE, raw)


def test_parse_value_rejects_control_characters_and_long_text() -> None:
    with pytest.raises(OverrideValueError):
        parse_value(TEXT, "Apro\x00bado")
    with pytest.raises(OverrideValueError):
        parse_value(TEXT, "x" * (MAX_TEXT_LENGTH + 1))


def test_comparable_and_shown_value_meet_in_the_middle() -> None:
    assert comparable(DATE, "2026-03-12") == shown_value(DATE, dt.date(2026, 3, 12))
    assert comparable(DATE, None) == shown_value(DATE, None)
    assert comparable(TEXT, " En tramite ") == shown_value(TEXT, "En tramite")


def test_cell_signature_uses_raw_text_when_a_date_cell_held_text() -> None:
    evidence = {"fecha_ingreso": {"raw": " 12 de marzo y 4 de mayo ", "parsed": None}}
    assert cell_signature(DATE, value=None, text_dates=evidence) == (
        "12 de marzo y 4 de mayo",
        None,
    )
    assert cell_signature(DATE, value=dt.date(2026, 3, 12), text_dates=evidence) == (
        None,
        dt.date(2026, 3, 12),
    )
    assert cell_signature(DATE, value=None, text_dates=None) == (None, None)
    assert cell_signature(TEXT, value=" Aprobado", text_dates=None) == ("Aprobado", None)


def test_value_signature_matches_cell_signature_of_the_same_value() -> None:
    assert value_signature(TEXT, "Aprobado") == cell_signature(
        TEXT, value="Aprobado", text_dates={}
    )
    assert value_signature(DATE, dt.date(2026, 1, 2)) == (None, dt.date(2026, 1, 2))
    assert value_signature(DATE, None) == (None, None)


def test_display_and_note_text() -> None:
    assert display((None, dt.date(2026, 1, 2))) == "2026-01-02"
    assert display(("Aprobado", None)) == "Aprobado"
    assert display((None, None)) is None
    assert (
        note_text(author="Ana Pérez", edited_on=dt.date(2026, 10, 4), planilla=("Rechazado", None))
        == "web · Ana Pérez · 04-10-2026 · antes: Rechazado"
    )
    assert note_text(
        author="Ana", edited_on=dt.date(2026, 10, 4), planilla=(None, dt.date(2026, 1, 5))
    ).endswith("antes: 05-01-2026")
    assert note_text(author="Ana", edited_on=dt.date(2026, 10, 4), planilla=(None, None)).endswith(
        "antes: (vacía)"
    )


def test_normalize_text_treats_non_breaking_space_as_whitespace() -> None:
    assert normalize_text("\u00a0En\u00a0\u00a0tramite\u00a0") == "En tramite"
    assert normalize_text("\u00a0En \u00a0 tramite ") == normalize_text("En tramite")
    assert normalize_text("\u00a0 \u00a0") is None
    assert parse_value(TEXT, "\u00a0Aprobado\u00a0") == "Aprobado"
    assert parse_value(DATE, "\u00a0") is None
    assert parse_value(DATE, "\u00a02026-03-12\u00a0") == dt.date(2026, 3, 12)
    assert comparable(TEXT, "\u00a0En\u00a0tramite") == shown_value(TEXT, "En tramite")
    assert comparable(DATE, "\u00a0") is None
