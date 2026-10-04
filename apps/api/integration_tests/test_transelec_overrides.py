"""Transelec web edits (field overrides) end to end against real PostgreSQL.

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md.
Synthetic workbooks only, built with the reads-router test's own builders;
no planilla value appears here.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from app.access import Role
from app.deps import get_object_store
from app.main import app
from app.object_store import LocalObjectStore
from app.routers.transelec import _RESUMEN_ROW_COLUMNS
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_transelec_reads_router import (
    _SAME_ORIGIN,
    _ingestion_run_id,
    _login_with_grants,
    _source_row,
    _upload,
    _workbook_bytes,
)

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
    engine: Engine, *, import_id: int, source_row_number: int, field: str, value: str
) -> None:
    """An applied text edit written straight to the table (view tests only)."""

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO platform.transelec_field_override (
                    pmf, rol, numero_predio, numero_area_corta, key_ordinal, field,
                    value_text, planilla_value_text, base_import_id, created_by_app_user_id
                )
                SELECT pmf, rol, numero_predio, numero_area_corta, key_ordinal, :field,
                       :value, {field}, import_id, (SELECT min(id) FROM platform.app_user)
                FROM platform.transelec_keyed_row
                WHERE import_id = :import_id AND source_row_number = :row
                """
            ),
            {"field": field, "value": value, "import_id": import_id, "row": source_row_number},
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

    csv_text = client.get("/transelec/export.csv", params={"q": "MP001"}).content.decode(
        "utf-8-sig"
    )
    assert "Aprobado" in csv_text
