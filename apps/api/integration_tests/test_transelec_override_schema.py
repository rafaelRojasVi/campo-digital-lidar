"""Migration 0012's text comparison rule and its override-table invariants.

``platform.transelec_norm_text`` (SQL) decides whether a planilla cell still
equals the value seen at edit time; ``transelec_ingestion.field_overrides.
normalize_text`` (Python) decides the same thing in the API. If the two ever
disagree, an edit flips between ``aplicada`` and ``en_conflicto`` depending
on which side looked. Both trim and collapse ASCII whitespace plus U+00A0
(NBSP), turn blank into NULL and keep case.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError
from test_transelec_import_constraints import insert_app_user, insert_import

from transelec_ingestion.field_overrides import normalize_text

NBSP = "\u00a0"

_VALUES: tuple[str | None, ...] = (
    None,
    "",
    "   ",
    "En tramite",
    "  En   tramite ",
    "En\ttramite\n",
    "aprobado",
    "Aprobado",
    f"En tramite{NBSP}",
    f"{NBSP}{NBSP}En tramite{NBSP}",
    f"En{NBSP}tramite",
    f"En{NBSP}{NBSP} \ttramite",
    NBSP,
    f" {NBSP}\t{NBSP} ",
    "\r\nEn\x0b\x0ctramite\r",
    f"\t En {NBSP}\r\n tramite {NBSP}\x0b",
    # Not whitespace for either side: kept as is.
    "En\u2007tramite",
    "En\u200btramite",
)


@pytest.mark.parametrize("value", _VALUES, ids=repr)
def test_sql_norm_text_equals_python_normalize_text(
    integration_engine: Engine, value: str | None
) -> None:
    with integration_engine.connect() as connection:
        sql = connection.execute(
            text("SELECT platform.transelec_norm_text(:value)"), {"value": value}
        ).scalar_one()

    assert sql == normalize_text(value)


def test_nbsp_padded_and_separated_values_normalize_to_the_plain_value(
    integration_engine: Engine,
) -> None:
    inputs = [f"{NBSP}En tramite{NBSP}", f"En{NBSP}tramite", f" En{NBSP}{NBSP}\ttramite "]
    with integration_engine.connect() as connection:
        results = [
            connection.execute(
                text("SELECT platform.transelec_norm_text(:value)"), {"value": value}
            ).scalar_one()
            for value in inputs
        ]

    assert results == ["En tramite"] * len(inputs)
    assert [normalize_text(value) for value in inputs] == results


def _insert_override(connection: Connection, **overrides: Any) -> None:
    connection.execute(
        text(
            """
            INSERT INTO platform.transelec_field_override (
                pmf, key_ordinal, field, value_text, base_import_id,
                created_by_app_user_id, ended_at, end_reason
            )
            VALUES (
                :pmf, 1, 'estado', 'Aprobado', :base_import_id,
                :created_by_app_user_id, :ended_at, :end_reason
            )
            """
        ),
        overrides,
    )


@pytest.mark.parametrize(
    ("ended", "end_reason", "accepted"),
    [
        (False, None, True),
        (True, "superseded", True),
        (True, None, False),
        (True, "other", False),
        (False, "kept", False),
    ],
)
def test_an_edit_ends_exactly_when_it_has_an_end_reason(
    integration_connection: Connection, ended: bool, end_reason: str | None, accepted: bool
) -> None:
    user_id = insert_app_user(integration_connection, identity_key="override-end-editor")
    import_id = insert_import(
        integration_connection, suffix="override-end", validated_by_app_user_id=user_id
    )
    values = {
        "pmf": "MP001",
        "base_import_id": import_id,
        "created_by_app_user_id": user_id,
        "ended_at": "2026-01-02T00:00:00+00:00" if ended else None,
        "end_reason": end_reason,
    }

    if accepted:
        _insert_override(integration_connection, **values)
    else:
        with pytest.raises(IntegrityError), integration_connection.begin_nested():
            _insert_override(integration_connection, **values)
