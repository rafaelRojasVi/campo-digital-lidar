"""Transelec web edits (field overrides) end to end against real PostgreSQL.

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md.
Synthetic workbooks only, built with the reads-router test's own builders;
no planilla value appears here.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from app.access import Role
from app.csrf import CSRF_HEADER_NAME
from app.deps import get_object_store
from app.main import app
from app.object_store import LocalObjectStore
from app.routers.transelec import _RESUMEN_ROW_COLUMNS
from app.transelec_overrides import (
    FieldNotInSourceError,
    NotInConflictError,
    ValueChangedError,
    VersionChangedError,
    discard_override,
    keep_override,
    list_overrides,
    save_override,
)
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from test_transelec_reads_router import (
    _SAME_ORIGIN,
    _ingestion_run_id,
    _login_with_grants,
    _source_row,
    _upload,
    _workbook_bytes,
)

from transelec_ingestion.field_overrides import EDITABLE_BY_NAME

ADMIN = (("transelect", Role.ADMIN),)
OPERATOR = (("transelect", Role.OPERATOR),)
VIEWER = (("transelect", Role.VIEWER),)

# MP002's Fecha de ingreso holds two dates as text: the importer keeps the raw
# text and stores no date. MP003's two rows share PMF + Rol + N Predio + N
# Area de Corta, so they are key_ordinal 1 and 2.
_BASE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "pmf": "MP001",
        "rol": "101",
        "numero_predio": "1",
        "numero_area_corta": "A1",
        "estado": "En evaluacion",
        "estado_resumido": "En tramite",
        "numero_ingreso": "ING-1",
        "tipo_propietario": "Empresa Forestal",
        "empresa": "Forestal Sur",
        "superficie_corta": 1.0,
    },
    {
        "pmf": "MP001",
        "rol": "101",
        "numero_predio": "1",
        "numero_area_corta": "A2",
        "estado": "En evaluacion",
        "estado_resumido": "En tramite",
        "numero_ingreso": "ING-1",
        "tipo_propietario": "Empresa Forestal",
        "empresa": "Forestal Sur",
        "superficie_corta": 2.0,
    },
    {
        "pmf": "MP002",
        "rol": "202",
        "numero_predio": "5",
        "numero_area_corta": "A1",
        "estado": "Rechazado",
        "estado_resumido": "En tramite",
        "numero_ingreso": "ING-2",
        "fecha_ingreso": "2 de enero de 2026 y 3 de febrero de 2026",
        "tipo_propietario": "Empresa Forestal",
        "empresa": "Forestal Norte",
        "superficie_corta": 3.0,
    },
    {
        "pmf": "MP003",
        "rol": "303",
        "numero_predio": "9",
        "numero_area_corta": "A1",
        "estado": "Aprobado",
        "estado_resumido": "Aprobado",
        "numero_ingreso": "ING-3",
        "tipo_propietario": "Persona Natural",
        "empresa": "Forestal Norte",
        "superficie_corta": 4.0,
    },
    {
        "pmf": "MP003",
        "rol": "303",
        "numero_predio": "9",
        "numero_area_corta": "A1",
        "estado": "Aprobado",
        "estado_resumido": "Aprobado",
        "numero_ingreso": "ING-3",
        "tipo_propietario": "Persona Natural",
        "empresa": "Forestal Norte",
        "superficie_corta": 5.0,
    },
)


@pytest.fixture
def client(integration_engine: Engine, tmp_path: Path) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_object_store] = lambda: LocalObjectStore(tmp_path / "object-store")

    with TestClient(app) as test_client:
        test_client.engine = integration_engine
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.begin() as conn:
        conn.execute(text("UPDATE platform.transelec_dashboard_state SET active_import_id = NULL"))
        for table in (
            "transelec_field_override",
            "transelec_publish_event",
            "transelec_resumen_row",
            "transelec_import",
            "generated_artifact",
            "processing_attempt",
            "processing_job",
            "ingestion_run",
            "source_observation",
            "source_snapshot",
            "source_asset",
            "source_system",
            "audit_event",
            "session",
            "product_grant",
            "app_user",
        ):
            conn.execute(text(f"DELETE FROM platform.{table}"))


def _workbook(tmp_path: Path, name: str, rows: list[dict[str, Any]] | None = None) -> bytes:
    source = [dict(row) for row in (rows if rows is not None else _BASE_ROWS)]
    return _workbook_bytes(tmp_path, name, [_source_row(**row) for row in source])


def _publish(client: TestClient, content: bytes, filename: str = "edits.xlsx") -> int:
    """Upload, validate and publish (acknowledging warnings); return import_id."""

    engine: Engine = client.engine
    upload = _upload(client, content, filename)
    assert upload.status_code == 200, upload.text
    run_id = _ingestion_run_id(engine, upload.json()["source_snapshot_id"])
    validated = client.post(
        f"/transelec/imports/{run_id}/validate-and-project", headers={"Origin": _SAME_ORIGIN}
    )
    assert validated.status_code == 200, validated.text
    import_id = validated.json()["import_id"]
    published = client.post(
        f"/transelec/imports/{import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )
    assert published.status_code == 200, published.text
    return import_id


def _rows(client: TestClient, pmf: str) -> list[dict[str, Any]]:
    response = client.get(f"/transelec/pmfs/{pmf}")
    assert response.status_code == 200, response.text
    return response.json()["rows"]


def _row(client: TestClient, pmf: str, index: int = 0) -> dict[str, Any]:
    return _rows(client, pmf)[index]


def _insert_override(
    engine: Engine,
    *,
    import_id: int,
    source_row_number: int,
    field: str,
    value: str,
    planilla_value_text: str | None = None,
) -> None:
    """A text edit written straight to the table (view tests only).

    By default the planilla value seen at edit time is the row's current cell,
    so the edit is ``aplicada``. Passing ``planilla_value_text`` that differs
    from the current cell (and from ``value``) makes it ``en_conflicto``.
    """

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO platform.transelec_field_override (
                    pmf, rol, numero_predio, numero_area_corta, key_ordinal, field,
                    value_text, planilla_value_text, base_import_id, created_by_app_user_id
                )
                SELECT pmf, rol, numero_predio, numero_area_corta, key_ordinal, :field,
                       :value, COALESCE(CAST(:seen AS text), {field}), import_id,
                       (SELECT min(id) FROM platform.app_user)
                FROM platform.transelec_keyed_row
                WHERE import_id = :import_id AND source_row_number = :row
                """
            ),
            {
                "field": field,
                "value": value,
                "seen": planilla_value_text,
                "import_id": import_id,
                "row": source_row_number,
            },
        )


# ---------------------------------------------------------------------------
# The effective-row view (Task 3)
# ---------------------------------------------------------------------------


def test_effective_view_exposes_every_column_the_router_selects(
    integration_engine: Engine,
) -> None:
    with integration_engine.connect() as conn:
        columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'platform' AND table_name = 'transelec_effective_row'"
                )
            ).scalars()
        )
    assert set(_RESUMEN_ROW_COLUMNS) <= columns
    assert {"import_id", "key_ordinal", "web_fields"} <= columns


def test_effective_view_equals_the_source_rows_without_edits(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-admin", ADMIN)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    shared = [column for column in _RESUMEN_ROW_COLUMNS if column != "web_fields"]
    with client.engine.connect() as conn:
        difference = conn.execute(
            text(
                f"""
                SELECT count(*) FROM (
                    SELECT source_row_number, {", ".join(shared)}
                    FROM platform.transelec_effective_row WHERE import_id = :i
                    EXCEPT
                    SELECT source_row_number, {", ".join(shared)}
                    FROM platform.transelec_resumen_row WHERE import_id = :i
                ) AS d
                """
            ),
            {"i": import_id},
        ).scalar_one()
        ordinals = (
            conn.execute(
                text(
                    "SELECT key_ordinal FROM platform.transelec_effective_row "
                    "WHERE import_id = :i AND pmf = 'MP003' ORDER BY source_row_number"
                ),
                {"i": import_id},
            )
            .scalars()
            .all()
        )
    assert difference == 0
    assert ordinals == [1, 2]
    assert all(row["web_fields"] == [] for row in _rows(client, "MP001"))


def test_every_read_sees_an_applied_edit(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-admin", ADMIN)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))

    before = client.get("/transelec/summary").json()
    target = _row(client, "MP001", 0)["source_row_number"]
    _insert_override(
        client.engine,
        import_id=import_id,
        source_row_number=target,
        field="estado_resumido",
        value="Aprobado",
    )

    detail = _row(client, "MP001", 0)
    assert detail["estado_resumido"] == "Aprobado"
    assert detail["web_fields"] == ["estado_resumido"]
    assert _row(client, "MP001", 1)["web_fields"] == []

    filtered = client.get("/transelec/pmfs", params={"estado_resumido": "Aprobado"}).json()
    assert target in {item["source_row_number"] for item in filtered["items"]}
    assert filtered["total_count"] == 3  # the edited row plus MP003's two rows

    searched = client.get("/transelec/pmfs", params={"q": "MP001", "estado_resumido": "Aprobado"})
    assert searched.json()["total_count"] == 1

    after = client.get("/transelec/summary").json()
    assert after["aprobados_pmf_count"] == before["aprobados_pmf_count"] + 1
    assert after["en_tramite_pmf_count"] == before["en_tramite_pmf_count"] - 1

    exported = _export_estado_resumido(client, "MP001")
    assert exported == {"A1": "Aprobado", "A2": "En tramite"}


def _export_estado_resumido(client: TestClient, pmf: str) -> dict[str, str]:
    """Estado resumido per N Area de Corta for one PMF, read from /export.csv."""

    body = client.get("/transelec/export.csv", params={"q": pmf}).content.decode("utf-8-sig")
    return {
        row["N Area de Corta"]: row["Estado resumido"]
        for row in csv.DictReader(io.StringIO(body), delimiter=";")
        if row["PMF"] == pmf
    }


def test_a_conflicting_edit_is_invisible_on_every_read(client: TestClient, tmp_path: Path) -> None:
    """en_conflicto: the cell differs from both the value seen at edit time
    and the web value, so the planilla value is shown and nothing is flagged."""

    _login_with_grants(client, "transelec-admin", ADMIN)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))

    summary_before = client.get("/transelec/summary").json()
    target = _row(client, "MP001", 0)["source_row_number"]
    _insert_override(
        client.engine,
        import_id=import_id,
        source_row_number=target,
        field="estado_resumido",
        value="Rechazado",
        planilla_value_text="Observado",  # neither the current cell nor the web value
    )
    with client.engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM platform.transelec_field_override")
            ).scalar_one()
            == 1
        )

    detail = _row(client, "MP001", 0)
    assert detail["estado_resumido"] == "En tramite"
    assert detail["web_fields"] == []

    by_web_value = client.get("/transelec/pmfs", params={"estado_resumido": "Rechazado"}).json()
    assert target not in {item["source_row_number"] for item in by_web_value["items"]}
    assert by_web_value["total_count"] == 0

    searched = client.get("/transelec/pmfs", params={"q": "Rechazado"}).json()
    assert target not in {item["source_row_number"] for item in searched["items"]}

    assert client.get("/transelec/summary").json() == summary_before

    assert _export_estado_resumido(client, "MP001") == {"A1": "En tramite", "A2": "En tramite"}


# ---------------------------------------------------------------------------
# Persistence (Task 4)
# ---------------------------------------------------------------------------


def _actor(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT min(id) FROM platform.app_user")).scalar_one()


def _save(
    engine: Engine,
    *,
    import_id: int,
    row: int,
    field: str,
    value: Any,
    expected: Any,
) -> Any:
    with engine.begin() as conn:
        return save_override(
            conn,
            import_id=import_id,
            source_row_number=row,
            field=EDITABLE_BY_NAME[field],
            value=value,
            expected=expected,
            actor_app_user_id=_actor(engine),
        )


def test_save_then_list_reports_an_applied_edit(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    outcome = _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="estado_resumido",
        value="Aprobado",
        expected="En tramite",
    )

    assert outcome.changed and outcome.override_id is not None
    with client.engine.connect() as conn:
        records = list_overrides(conn, import_id=import_id)
    assert [(r.field, r.status, r.source_row_number) for r in records] == [
        ("estado_resumido", "aplicada", row)
    ]
    assert records[0].web == ("Aprobado", None)
    assert records[0].planilla_at_edit == ("En tramite", None)
    assert records[0].created_by_display_name == "transelec-operator"


def test_save_refuses_a_stale_version_and_a_changed_value(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    with pytest.raises(VersionChangedError):
        _save(
            client.engine,
            import_id=import_id + 1000,
            row=row,
            field="estado",
            value="x",
            expected="En evaluacion",
        )
    with pytest.raises(ValueChangedError):
        _save(
            client.engine,
            import_id=import_id,
            row=row,
            field="estado",
            value="x",
            expected="Otro valor",
        )


def test_resave_supersedes_and_returning_to_the_planilla_discards(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="estado",
        value="A",
        expected="En evaluacion",
    )
    _save(client.engine, import_id=import_id, row=row, field="estado", value="B", expected="A")
    back = _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="estado",
        value="En evaluacion",
        expected="B",
    )
    same = _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="estado",
        value="En evaluacion",
        expected="En evaluacion",
    )

    assert back.override_id is None and back.changed
    assert not same.changed
    with client.engine.connect() as conn:
        history = conn.execute(
            text(
                "SELECT value_text, end_reason FROM platform.transelec_field_override "
                "WHERE field = 'estado' ORDER BY id"
            )
        ).all()
    assert [tuple(item) for item in history] == [("A", "superseded"), ("B", "discarded")]
    assert _row(client, "MP001", 0)["web_fields"] == []


def test_field_without_a_source_column_is_refused(client: TestClient, tmp_path: Path) -> None:
    """The test builders write the earlier layout, which has no «…2» columns."""

    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    with pytest.raises(FieldNotInSourceError):
        _save(
            client.engine,
            import_id=import_id,
            row=row,
            field="numero_ingreso_2",
            value="ING-9",
            expected=None,
        )


def test_activation_retires_incorporated_edits_and_flags_conflicts(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    first = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    row_a = _row(client, "MP001", 0)["source_row_number"]
    row_b = _row(client, "MP001", 1)["source_row_number"]
    _save(
        client.engine,
        import_id=first,
        row=row_a,
        field="estado_resumido",
        value="Aprobado",
        expected="En tramite",
    )
    _save(
        client.engine,
        import_id=first,
        row=row_b,
        field="estado_resumido",
        value="Aprobado",
        expected="En tramite",
    )

    # v2: row A now says what the web said (incorporated); row B changed to
    # something else (conflict); MP002 is gone (orphan is covered in Task 5).
    rows = [dict(item) for item in _BASE_ROWS]
    rows[0]["estado_resumido"] = "Aprobado"
    rows[1]["estado_resumido"] = "Desistido"
    second = _publish(client, _workbook(tmp_path, "v2.xlsx", rows))

    with client.engine.connect() as conn:
        records = list_overrides(conn, import_id=second)
        ended = (
            conn.execute(
                text(
                    "SELECT end_reason FROM platform.transelec_field_override "
                    "WHERE ended_at IS NOT NULL"
                )
            )
            .scalars()
            .all()
        )
        audit = conn.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'import.published' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()
    assert ended == ["incorporated"]
    assert [(r.source_row_number, r.status) for r in records] == [(row_b, "en_conflicto")]
    assert records[0].planilla_now == ("Desistido", None)
    assert audit["incorporated_overrides"] == 1
    assert _row(client, "MP001", 1)["estado_resumido"] == "Desistido"  # the planilla wins

    with client.engine.begin() as conn:
        keep_override(conn, override_id=records[0].id, actor_app_user_id=_actor(client.engine))
    assert _row(client, "MP001", 1)["estado_resumido"] == "Aprobado"
    with client.engine.begin() as conn, pytest.raises(NotInConflictError):
        current = list_overrides(conn, import_id=second)[0]
        keep_override(conn, override_id=current.id, actor_app_user_id=_actor(client.engine))


def test_date_edit_over_raw_text_stores_only_the_text_side(
    client: TestClient, tmp_path: Path
) -> None:
    """MP002's date cell holds raw text; the edit sets a real date, and the
    planilla side records the text only, so a republish of the same text
    still matches (``aplicada``)."""

    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP002", 0)["source_row_number"]

    outcome = _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="fecha_ingreso",
        value=dt.date(2026, 2, 3),
        expected=None,
    )

    assert outcome.changed and outcome.override_id is not None
    with client.engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT value_text, value_date, planilla_value_text, planilla_value_date "
                "FROM platform.transelec_field_override WHERE id = :id"
            ),
            {"id": outcome.override_id},
        ).one()
        records = list_overrides(conn, import_id=import_id)
    assert tuple(stored) == (
        None,
        dt.date(2026, 2, 3),
        "2 de enero de 2026 y 3 de febrero de 2026",
        None,
    )
    assert [r.status for r in records] == ["aplicada"]


def test_a_v1_import_has_no_second_ingreso_columns() -> None:
    """V1 (no mapping report) carried the 30 legacy columns: refuse the «…2» pair."""

    from app.transelec_overrides import source_fields

    present = set(source_fields("transelec-resumen-v1", None))
    assert {"numero_ingreso", "fecha_ingreso"} <= present
    assert not {"numero_ingreso_2", "fecha_ingreso_2"} & present


def _race_setup(client: TestClient, tmp_path: Path) -> tuple[int, int, int]:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    outcome = _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="estado",
        value="Web",
        expected="En evaluacion",
    )
    assert outcome.override_id is not None
    return import_id, row, outcome.override_id


@pytest.mark.parametrize("stale_value", ["Otro", "En evaluacion"])
def test_a_save_racing_a_discard_is_refused_not_silently_applied(
    client: TestClient, tmp_path: Path, stale_value: str
) -> None:
    """A discards the active edit and holds its transaction open; B, who still
    saw the web value, must wait for A and then fail ``value_changed``."""

    import threading

    import_id, row, override_id = _race_setup(client, tmp_path)
    actor = _actor(client.engine)
    outcome: dict[str, Any] = {}
    started = threading.Event()

    def attempt() -> None:
        try:
            with client.engine.begin() as conn:
                started.set()
                outcome["result"] = save_override(
                    conn,
                    import_id=import_id,
                    source_row_number=row,
                    field=EDITABLE_BY_NAME["estado"],
                    value=stale_value,
                    expected="Web",
                    actor_app_user_id=actor,
                )
        except Exception as exc:  # noqa: BLE001 - asserted below
            outcome["error"] = exc

    with client.engine.connect() as conn_a:
        with conn_a.begin():
            discard_override(conn_a, override_id=override_id, actor_app_user_id=actor)
            worker = threading.Thread(target=attempt)
            worker.start()
            assert started.wait(5)
            worker.join(0.5)
            assert worker.is_alive(), "B must block on A's cell lock"
        worker.join(10)

    assert not worker.is_alive()
    assert isinstance(outcome.get("error"), ValueChangedError), outcome
    with client.engine.connect() as conn:
        active = conn.execute(
            text("SELECT count(*) FROM platform.transelec_field_override WHERE ended_at IS NULL")
        ).scalar_one()
    assert active == 0


# ---------------------------------------------------------------------------
# Routes (Task 5)
# ---------------------------------------------------------------------------


def _put(
    client: TestClient,
    import_id: int,
    row: int,
    field: str,
    value: str | None,
    *,
    expected: str | None,
    csrf: bool = True,
) -> Any:
    headers = {"Origin": _SAME_ORIGIN}
    if not csrf:
        headers[CSRF_HEADER_NAME] = ""
    return client.put(
        "/transelec/overrides",
        json={
            "import_id": import_id,
            "source_row_number": row,
            "field": field,
            "value": value,
            "expected_value": expected,
        },
        headers=headers,
    )


def test_unauthenticated_and_viewer_cannot_edit(client: TestClient, tmp_path: Path) -> None:
    assert client.put("/transelec/overrides", json={}).status_code in (401, 403)
    _login_with_grants(client, "transelec-admin", ADMIN)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    client.cookies.clear()

    _login_with_grants(client, "transelec-viewer", VIEWER)
    response = _put(client, import_id, row, "estado", "x", expected="En evaluacion")
    assert response.status_code == 403
    assert client.get("/transelec/overrides").status_code == 200  # viewers read the list


def test_edit_requires_csrf(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    response = _put(client, import_id, row, "estado", "x", expected="En evaluacion", csrf=False)
    assert response.status_code == 403


def test_operator_saves_and_gets_the_effective_row(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    response = _put(client, import_id, row, "estado_resumido", "Aprobado", expected="En tramite")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True and body["override_id"] is not None
    assert body["row"]["estado_resumido"] == "Aprobado"
    assert body["row"]["web_fields"] == ["estado_resumido"]
    listed = client.get("/transelec/overrides", params={"pmf": "MP001"}).json()
    assert listed[0]["status"] == "aplicada"
    assert listed[0]["field_label"] == "Estado resumido"
    assert listed[0]["web_value"] == "Aprobado"
    assert listed[0]["planilla_value_at_edit"] == "En tramite"
    assert listed[0]["created_by_display_name"] == "transelec-operator"
    assert client.get("/api/transelec/overrides").status_code == 200  # /api alias mounted


def test_conflicts_return_codes_and_spanish_messages(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    stale = _put(client, import_id + 1000, row, "estado", "x", expected="En evaluacion")
    changed = _put(client, import_id, row, "estado", "x", expected="Otro")

    assert stale.status_code == 409 and stale.json()["code"] == "version_changed"
    assert changed.status_code == 409 and changed.json()["code"] == "value_changed"
    assert "Recargue" in changed.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("empresa", "x", 422),
        ("fecha_ingreso", "12-03-2026", 422),
        ("estado", "x" * 501, 422),
    ],
)
def test_invalid_edits_are_422(
    client: TestClient, tmp_path: Path, field: str, value: str, status: int
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    assert _put(client, import_id, row, field, value, expected=None).status_code == status


def test_field_without_a_source_column_is_not_editable(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    response = _put(client, import_id, row, "fecha_ingreso_2", "2026-01-02", expected=None)
    assert response.status_code == 422
    assert "columna" in response.json()["detail"]


def test_edit_hits_only_the_chosen_row_of_a_shared_key(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    second = _row(client, "MP003", 1)["source_row_number"]

    assert (
        _put(client, import_id, second, "estado", "Desistido", expected="Aprobado").status_code
        == 200
    )

    rows = _rows(client, "MP003")
    assert [r["estado"] for r in rows] == ["Aprobado", "Desistido"]


def test_date_edit_over_raw_text_survives_an_unchanged_republish(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    row = _row(client, "MP002")
    assert row["fecha_ingreso"] is None and "fecha_ingreso" in row["source_text_dates"]

    saved = _put(
        client, import_id, row["source_row_number"], "fecha_ingreso", "2026-03-12", expected=None
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["row"]["fecha_ingreso"] == "2026-03-12"
    assert "fecha_ingreso" not in saved.json()["row"]["source_text_dates"]

    # A new upload whose MP002 cell still holds the same text: the edit applies.
    rows = [dict(item) for item in _BASE_ROWS]
    rows[0]["empresa"] = "Forestal Este"  # a different file, same MP002 cell
    _publish(client, _workbook(tmp_path, "v2.xlsx", rows), filename="v2.xlsx")
    assert _row(client, "MP002")["fecha_ingreso"] == "2026-03-12"
    assert client.get("/transelec/overrides").json()[0]["status"] == "aplicada"


def test_orphans_are_listed_and_discard_returns_to_the_planilla(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    mp002 = _row(client, "MP002")["source_row_number"]
    mp001 = _row(client, "MP001", 0)["source_row_number"]
    _put(client, import_id, mp002, "estado", "Reingresado", expected="Rechazado")
    saved = _put(client, import_id, mp001, "estado", "Aprobado", expected="En evaluacion")

    rows = [dict(item) for item in _BASE_ROWS if item["pmf"] != "MP002"]
    _publish(client, _workbook(tmp_path, "v2.xlsx", rows), filename="v2.xlsx")
    listed = client.get("/transelec/overrides").json()
    assert [item["status"] for item in listed] == ["huerfana", "aplicada"]
    assert listed[0]["source_row_number"] is None

    gone = client.delete(
        f"/transelec/overrides/{saved.json()['override_id']}", headers={"Origin": _SAME_ORIGIN}
    )
    assert gone.status_code == 204
    assert _row(client, "MP001", 0)["estado"] == "En evaluacion"
    again = client.delete(
        f"/transelec/overrides/{saved.json()['override_id']}", headers={"Origin": _SAME_ORIGIN}
    )
    assert again.status_code == 404


def test_keep_route_requires_a_conflict(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    saved = _put(client, import_id, row, "estado", "Aprobado", expected="En evaluacion").json()
    response = client.post(
        f"/transelec/overrides/{saved['override_id']}/keep", headers={"Origin": _SAME_ORIGIN}
    )
    assert response.status_code == 409 and response.json()["code"] == "not_in_conflict"


def test_audit_rows_carry_no_cell_values(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    _put(client, import_id, row, "estado_resumido", "Valor-Unico-Web", expected="En tramite")

    with client.engine.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT subject_kind, metadata::text FROM platform.audit_event "
                "WHERE event_type = 'transelec.override.saved'"
            )
        ).one()
    assert audit.subject_kind == "transelec_override"
    assert "Valor-Unico-Web" not in audit.metadata and "En tramite" not in audit.metadata


def _insert_cell_edit(conn: Any, *, key_ordinal: int = 1) -> None:
    conn.execute(
        text(
            """
            INSERT INTO platform.transelec_field_override (
                pmf, rol, numero_predio, numero_area_corta, key_ordinal, field,
                value_text, planilla_value_text, base_import_id, created_by_app_user_id
            )
            SELECT pmf, rol, numero_predio, numero_area_corta, :ordinal, 'estado',
                   'dup', 'x', import_id, (SELECT min(id) FROM platform.app_user)
            FROM platform.transelec_keyed_row
            ORDER BY source_row_number
            LIMIT 1
            """
        ),
        {"ordinal": key_ordinal},
    )


def test_duplicate_active_edit_maps_to_value_changed(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    def racing_save(conn: Any, **_: Any) -> Any:
        # Two active edits of one cell: the partial unique index refuses the second.
        _insert_cell_edit(conn)
        _insert_cell_edit(conn)

    monkeypatch.setattr("app.routers.transelec_edits.save_override", racing_save)
    response = _put(client, import_id, row, "estado", "x", expected="En evaluacion")
    assert response.status_code == 409 and response.json()["code"] == "value_changed"


def test_other_integrity_errors_are_not_value_changed(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    def broken_save(conn: Any, **_: Any) -> Any:
        _insert_cell_edit(conn, key_ordinal=0)  # violates ck_..._key_ordinal

    monkeypatch.setattr("app.routers.transelec_edits.save_override", broken_save)
    with pytest.raises(IntegrityError):
        _put(client, import_id, row, "estado", "x", expected="En evaluacion")


def test_noop_save_writes_no_audit_event(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    response = _put(client, import_id, row, "estado", "En evaluacion", expected="En evaluacion")
    assert response.status_code == 200 and response.json()["changed"] is False
    with client.engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM platform.audit_event "
                "WHERE event_type LIKE 'transelec.override.%'"
            )
        ).scalar_one()
        none_ids = conn.execute(
            text("SELECT count(*) FROM platform.audit_event WHERE subject_id = 'None'")
        ).scalar_one()
    assert count == 0 and none_ids == 0
