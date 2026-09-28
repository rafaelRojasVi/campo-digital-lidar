"""Transelec read routes end-to-end: RBAC, filter-consistency, pagination,
each named status-rollup basis, CSV injection hardening, and version
metadata — against real PostgreSQL.

All fixture workbooks are synthetic and built here. None reproduces the
reviewed 14-Aug snapshot's 729/159/272 counts — the main fixture below is
7 rows / 6 PMFs / 6 predios, deliberately different, to prove no code path
assumes those specific numbers.
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import xlsxwriter
from app.access import Role
from app.access_repository import (
    grant_product_role,
    list_grants_for_user,
    resolve_or_create_app_user,
)
from app.csrf import CSRF_HEADER_NAME
from app.deps import SESSION_COOKIE_NAME, get_object_store
from app.dev_auth import DEFAULT_SEED_GRANTS, DEV_IDENTITY_KIND, SEEDED_DEV_IDENTITIES
from app.main import app
from app.object_store import LocalObjectStore
from app.session_store import PlatformSessionStore
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, text

from transelec_ingestion.xlsx_contract import EXPECTED_RESUMEN_HEADERS, RESUMEN_COLUMNS

_platform_sessions = PlatformSessionStore()
_SAME_ORIGIN = "http://testserver"


# ---------------------------------------------------------------------------
# Synthetic workbooks
# ---------------------------------------------------------------------------


def _source_row(**overrides: Any) -> list[Any]:
    values: dict[str, Any] = {field_name: None for _, field_name in RESUMEN_COLUMNS}
    values.update(overrides)
    return [values[field_name] for _, field_name in RESUMEN_COLUMNS]


def _workbook_bytes(
    tmp_path: Path,
    name: str,
    rows: list[list[Any]],
) -> bytes:
    path = tmp_path / name
    workbook = xlsxwriter.Workbook(path)
    worksheet = workbook.add_worksheet("Resumen")

    for column, header in enumerate(EXPECTED_RESUMEN_HEADERS):
        worksheet.write(0, column, header)

    for row_index, row in enumerate(rows, start=1):
        for column, value in enumerate(row):
            if value is None:
                continue
            if isinstance(value, str):
                # write_string(), not the generic write() dispatcher: a
                # source cell whose TEXT happens to start with "=" (the CSV
                # injection test relies on this) is real fixture data, not
                # an Excel formula, and write() would otherwise silently
                # reinterpret it as one.
                worksheet.write_string(row_index, column, value)
            else:
                worksheet.write(row_index, column, value)

    workbook.close()
    return path.read_bytes()


# The rich fixture: 7 rows / 6 PMFs / 6 predios (never 729/159/272), hand-
# designed so every KPI, chart, hero, quality indicator, and each of the
# three named status-rollup bases has a known, independently verifiable
# value. See the task report for the full worked-out expected-value table.
#
# Row map (source_row_number is 1-indexed from the header, i.e. row index+1):
#  1 MP001 "MP001-101-1" Aprobado / En evaluacion    / ING-1   (wins the dedup)
#  2 MP001 "MP001-101-1" Tachado  / Rechazado        / ING-2   (loses to row 1)
#  3 MP002 "MP002-202-5" En tramite / Rechazado x CONAF / ING-9  (pending+override)
#  4 MP003 "REAL-ID-001" Aprobado / Aprobado         / ING-77  (non-blank id)
#  5 MP004 "MP004-404-12" Pendiente / En preparacion / (blank) (pending: preparacion)
#  6 MP005 "MP005-505-20" Tachado / Recurso x rechazo / (blank) (pending: recurso_rechazo, override)
#  7 MP006 "MP006-606-30" Aprobado / En evaluacion   / ING-100 (con servidumbre)
def _rich_fixture_workbook(tmp_path: Path) -> bytes:
    rows = [
        _source_row(
            pmf="MP001",
            rol="101",
            numero_predio="1",
            estado="En evaluacion",
            estado_resumido="Aprobado",
            numero_ingreso="ING-1",
            tipo_propietario="Empresa Forestal",
            sector="Sector Norte",
            pas="PAS-A",
            empresa="Forestal Sur",
            superficie_corta=10.0,
            predio_ref="Fundo Uno",
        ),
        _source_row(
            pmf="MP001",
            rol="101",
            numero_predio="1",
            estado="Rechazado",
            estado_resumido="Tachado",
            numero_ingreso="ING-2",
            tipo_propietario="Empresa Forestal",
            sector="Sector Norte",
            pas="PAS-A",
            empresa="Forestal Sur",
            superficie_corta=4.0,
        ),
        _source_row(
            pmf="MP002",
            rol="202",
            numero_predio="5",
            estado="Rechazado por CONAF",
            estado_resumido="En tramite",
            numero_ingreso="ING-9",
            tipo_propietario="Empresa Forestal",
            sector="Sector Sur",
            pas="PAS-B",
            empresa="Forestal Norte",
            superficie_corta=6.0,
        ),
        _source_row(
            pmf="MP003",
            rol="303",
            numero_predio="9",
            id_predio_unico="REAL-ID-001",
            estado="Aprobado",
            estado_resumido="Aprobado",
            numero_ingreso="ING-77",
            tipo_propietario="Persona Natural",
            sector="Sector Sur",
            pas="PAS-B",
            empresa="Forestal Norte",
            superficie_corta=5.5,
        ),
        _source_row(
            pmf="MP004",
            rol="404",
            numero_predio="12",
            estado="En preparacion de antecedentes",
            estado_resumido="Pendiente",
            numero_ingreso=None,
            tipo_propietario="Empresa Forestal",
            sector="Sector Norte",
            pas="PAS-A",
            empresa="Forestal Sur",
            superficie_corta=2.25,
            predio_ref="Fundo Dos",
        ),
        _source_row(
            pmf="MP005",
            rol="505",
            numero_predio="20",
            estado="Recurso por rechazo administrativo",
            estado_resumido="Tachado",
            numero_ingreso=None,
            tipo_propietario="Empresa Forestal",
            sector="Sector Este",
            pas="PAS-C",
            empresa="Forestal Sur",
            superficie_corta=1.0,
        ),
        _source_row(
            pmf="MP006",
            rol="606",
            numero_predio="30",
            estado="En evaluacion",
            estado_resumido="Aprobado",
            numero_ingreso="ING-100",
            tipo_propietario="Persona Natural con Servidumbre firmada",
            sector="Sector Norte",
            pas="PAS-A",
            empresa="Forestal Sur",
            superficie_corta=3.75,
            predio_ref="Fundo Uno",
        ),
    ]
    return _workbook_bytes(tmp_path, "rich.xlsx", rows)


def _many_rows_workbook(tmp_path: Path, count: int) -> bytes:
    rows = [
        _source_row(
            pmf=f"MP-MANY-{index:04d}",
            rol=str(index),
            numero_predio=str(index),
            estado="En evaluacion",
            estado_resumido="Aprobado",
            numero_ingreso=f"ING-{index}",
        )
        for index in range(count)
    ]
    return _workbook_bytes(tmp_path, "many.xlsx", rows)


def _injection_workbook(tmp_path: Path) -> bytes:
    rows = [
        _source_row(
            pmf="MP-INJ",
            rol="1",
            numero_predio="1",
            estado_resumido="=SUM(1+1)",
            pas="+1+1",
            empresa="-2+3",
            sector="@cmd|'/c calc'!A1",
            carpeta_normalizada="Carpeta normal",
        )
    ]
    return _workbook_bytes(tmp_path, "injection.xlsx", rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _login(client: TestClient, identity_key: str) -> None:
    engine: Engine = client.engine
    display_name = next(
        (
            identity.display_name
            for identity in SEEDED_DEV_IDENTITIES
            if identity.identity_key == identity_key
        ),
        identity_key,
    )
    with engine.connect() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind=DEV_IDENTITY_KIND,
            identity_key=identity_key,
            display_name=display_name,
        )
        if not list_grants_for_user(connection, app_user_id=user.id):
            for product_key, role in DEFAULT_SEED_GRANTS.get(identity_key, ()):
                grant_product_role(
                    connection, app_user_id=user.id, product_key=product_key, role=role
                )
        raw_secret = _platform_sessions.create_session(
            connection, app_user_id=user.id, ttl=timedelta(hours=8)
        )
        connection.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)
    _refresh_csrf(client)


def _login_with_grants(
    client: TestClient, identity_key: str, grants: tuple[tuple[str, Role], ...]
) -> None:
    engine: Engine = client.engine
    with engine.connect() as connection:
        user = resolve_or_create_app_user(
            connection,
            identity_kind=DEV_IDENTITY_KIND,
            identity_key=identity_key,
            display_name=identity_key,
        )
        for product_key, role in grants:
            grant_product_role(connection, app_user_id=user.id, product_key=product_key, role=role)
        raw_secret = _platform_sessions.create_session(
            connection, app_user_id=user.id, ttl=timedelta(hours=8)
        )
        connection.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_secret)
    _refresh_csrf(client)


def _refresh_csrf(client: TestClient) -> None:
    response = client.get("/auth/csrf")
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER_NAME] = response.json()["csrf_token"]


def _upload(client: TestClient, content: bytes, filename: str = "resumen.xlsx") -> Response:
    return client.post(
        "/transelec/uploads",
        files={
            "file": (
                filename,
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers={"Origin": _SAME_ORIGIN},
    )


def _ingestion_run_id(engine: Engine, source_snapshot_id: int) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT id FROM platform.ingestion_run "
                "WHERE source_snapshot_id = :id ORDER BY id DESC LIMIT 1"
            ),
            {"id": source_snapshot_id},
        ).scalar_one()


def _publish_fixture(
    client: TestClient, engine: Engine, content: bytes, *, filename: str = "resumen.xlsx"
) -> int:
    """Upload, validate-and-project, and publish one workbook; return import_id."""

    upload = _upload(client, content, filename)
    assert upload.status_code == 200, upload.text
    run_id = _ingestion_run_id(engine, upload.json()["source_snapshot_id"])

    validated = client.post(
        f"/transelec/imports/{run_id}/validate-and-project", headers={"Origin": _SAME_ORIGIN}
    )
    assert validated.status_code == 200, validated.text
    import_id = validated.json()["import_id"]

    published = client.post(
        f"/transelec/imports/{import_id}/publish", headers={"Origin": _SAME_ORIGIN}
    )
    assert published.status_code == 200, published.text

    return import_id


# ---------------------------------------------------------------------------
# RBAC — every read route requires VIEW, none unauthenticated
# ---------------------------------------------------------------------------

# /transelec/pmfs/{pmf} is deliberately not in this list (it needs a path
# parameter); its own RBAC/CSRF coverage lives next to its other tests below.
READ_ROUTES = (
    "/transelec/summary",
    "/transelec/pmfs",
    "/transelec/pending",
    "/transelec/owner-status",
    "/transelec/report",
    "/transelec/export.csv",
    "/transelec/imports",
    "/transelec/imports/active",
    "/transelec/uploads/recent",
)


@pytest.mark.parametrize("path", READ_ROUTES)
def test_every_read_route_requires_authentication(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize("path", READ_ROUTES)
def test_every_read_route_is_reachable_by_the_viewer_role(client: TestClient, path: str) -> None:
    """VIEW is granted to VIEWER/OPERATOR/ADMIN alike (app.access._ALLOWED);
    a plain VIEWER must be able to reach every read route."""

    _login_with_grants(client, "transelec-viewer", (("transelect", Role.VIEWER),))

    response = client.get(path)

    # A VIEWER with no published import yet gets 404 ("no active version"),
    # not 403 — proving RBAC passed and the failure is business-logic, not
    # authorization. /imports and /uploads/recent return 200 with []
    # regardless of whether anything is published.
    assert response.status_code != 403, response.text
    assert response.status_code != 401, response.text


@pytest.mark.parametrize("path", READ_ROUTES)
def test_a_forestry_only_operator_is_forbidden_on_every_transelec_read_route(
    client: TestClient, path: str
) -> None:
    _login_with_grants(client, "forestry-only-operator-reads", (("forestry", Role.OPERATOR),))

    response = client.get(path)

    assert response.status_code == 403


@pytest.mark.parametrize("path", READ_ROUTES)
def test_no_read_route_carries_require_csrf(client: TestClient, path: str) -> None:
    """A GET must never be rejected for a missing CSRF token — require_csrf
    must only ever gate mutations."""

    _login(client, "dev-admin")
    del client.headers[CSRF_HEADER_NAME]

    response = client.get(path)

    assert (
        response.status_code != 403 or response.json().get("detail") != "CSRF verification failed."
    )


# ---------------------------------------------------------------------------
# Empty state — no active import yet
# ---------------------------------------------------------------------------


def test_data_dependent_routes_404_with_a_clear_message_when_nothing_is_published(
    client: TestClient,
) -> None:
    _login(client, "dev-admin")

    for path in (
        "/transelec/summary",
        "/transelec/pmfs",
        "/transelec/pending",
        "/transelec/owner-status",
        "/transelec/report",
        "/transelec/export.csv",
        "/transelec/imports/active",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json()["detail"] == "No hay una versión publicada de Transelec."


def test_imports_and_recent_uploads_return_empty_lists_not_errors(client: TestClient) -> None:
    _login(client, "dev-admin")

    assert client.get("/transelec/imports").json() == []
    assert client.get("/transelec/uploads/recent").json() == []


# ---------------------------------------------------------------------------
# KPIs, charts, hero, quality — TR-FUNC-001-016, against the rich fixture
# ---------------------------------------------------------------------------


def test_summary_kpis_charts_hero_and_quality_match_the_hand_computed_fixture(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/summary").json()

    assert body["row_count"] == 7
    assert body["pmf_count"] == 6  # TR-FUNC-001
    assert body["predio_count"] == 6  # TR-FUNC-002
    assert body["rol_count"] == 6  # TR-FUNC-003
    assert body["surface_total"] == pytest.approx(32.5)  # TR-FUNC-004
    assert body["basis_estado_resumido"] == "estado_resumido_first_row"
    assert body["aprobados_pmf_count"] == 3  # TR-FUNC-005: MP001, MP003, MP006
    assert body["en_tramite_pmf_count"] == 1  # TR-FUNC-006: MP002
    assert body["basis_pending_priority"] == "pending_priority_legacy"
    assert body["pendientes_prioritarios_pmf_count"] == 3  # TR-FUNC-007: MP002, MP004, MP005
    assert body["con_servidumbre_predio_count"] == 1  # TR-FUNC-008: MP006's predio

    by_predio = body["avance_por_predio"]
    assert (by_predio["aprobado"], by_predio["en_tramite"], by_predio["pendiente_o_tachado"]) == (
        3,
        1,
        2,
    )
    by_pmf = body["avance_por_pmf"]
    assert (by_pmf["aprobado"], by_pmf["en_tramite"], by_pmf["pendiente_o_tachado"]) == (3, 1, 2)

    hero = body["estado_resumido_hero_predio"]
    assert (hero["aprobado"], hero["en_tramite"], hero["pendiente"], hero["tachado"]) == (
        3,
        1,
        1,
        1,
    )
    assert hero["sin_estado"] == 0

    assert sorted(body["predios_reforestacion"]) == ["Fundo Dos", "Fundo Uno"]  # TR-FUNC-012
    assert body["calidad_filas_sin_id_predial_unico"] == 6  # TR-FUNC-014
    assert body["calidad_pmf_sin_numero_ingreso"] == 2  # TR-FUNC-015: MP004, MP005
    assert body["calidad_numero_resolucion"] == "No disponible"  # TR-FUNC-016


def test_summary_headline_is_pmf_grain_and_its_buckets_sum_to_the_pmf_total(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """Javier's recurring question, answered at the grain he asks it in.

    The fixture's 7 detail rows describe 6 plans, and MP001 carries two
    different `Estado resumido` values (`Aprobado` on its first row,
    `Tachado` on its second) — the same shape as MP015 in the 29-Jul Power
    BI summary and MP022 in the 14-Aug workbook. The buckets must still sum
    to 6, not 7.
    """

    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/summary").json()
    hero = body["estado_resumido_pmf"]

    assert body["row_count"] == 7
    assert body["pmf_count"] == 6
    assert (hero["aprobado"], hero["en_tramite"], hero["pendiente"], hero["tachado"]) == (
        3,
        1,
        1,
        1,
    )
    assert sum(hero.values()) == body["pmf_count"]

    detalle = body["estado_detalle_pmf"]
    assert sum(item["count"] for item in detalle) == body["pmf_count"]


def test_summary_reports_the_conflicting_pmf_rather_than_double_counting_it(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/summary").json()
    conflicts = body["calidad_pmf_estado_resumido_conflictivo"]

    assert [conflict["pmf"] for conflict in conflicts] == ["MP001"]
    assert conflicts[0]["valores"] == ["Aprobado", "Tachado"]
    assert conflicts[0]["canonico"] == "Aprobado"
    assert conflicts[0]["estado_detalle"] == "En evaluacion"


def test_summary_company_subtotals_reconcile_to_the_overall_pmf_total(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/summary").json()
    por_empresa = body["por_empresa"]

    assert {item["empresa"]: item["pmf_count"] for item in por_empresa} == {
        "Forestal Sur": 4,
        "Forestal Norte": 2,
    }
    assert sum(item["pmf_count"] for item in por_empresa) == body["pmf_count"]
    for state in ("aprobado", "en_tramite", "pendiente", "tachado", "sin_estado"):
        assert (
            sum(item["estado_resumido"][state] for item in por_empresa)
            == (body["estado_resumido_pmf"][state])
        )


def test_summary_reforestation_states_its_definition_and_offers_no_owner_count(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    reforestacion = client.get("/transelec/summary").json()["reforestacion"]

    assert reforestacion["predio_ref_count"] == 2
    assert reforestacion["predio_ref_labels"] == ["Fundo Dos", "Fundo Uno"]
    assert "Predio Ref" in reforestacion["definicion"]
    assert reforestacion["propietarios"] == "No disponible en el origen"


def test_summary_headline_is_computed_over_the_whole_filtered_population(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """Not over a page: the buckets still sum to the filtered PMF total.

    `/summary` reads every matching row for the filter state, while
    `/pmfs` pages. A headline built from a page would disagree with the
    total the same response reports.
    """

    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    params = {"sector": "Sector Norte"}
    body = client.get("/transelec/summary", params=params).json()
    first_page = client.get("/transelec/pmfs", params={**params, "limit": 1}).json()

    assert len(first_page["items"]) == 1
    assert first_page["total_count"] == body["row_count"] > 1
    assert sum(body["estado_resumido_pmf"].values()) == body["pmf_count"]


def test_pending_section_matches_the_hand_computed_fixture(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/pending").json()

    assert body["basis"] == "pending_priority_legacy"
    assert body["pending_pmf_count"] == 3
    assert body["total_pmf_count"] == 6
    assert body["pending_pmf_percentage"] == pytest.approx(50.0)
    assert body["stage_basis"] == "pending_stage_legacy"
    assert body["stages"] == {"preparacion": 1, "recurso_rechazo": 1, "otros": 1}

    pmfs_in_detail = {row["pmf"] for row in body["rows"]}
    assert pmfs_in_detail == {"MP002", "MP004", "MP005"}
    stage_by_pmf = {row["pmf"]: row["pending_stage"] for row in body["rows"]}
    assert stage_by_pmf == {
        "MP002": "otros",
        "MP004": "preparacion",
        "MP005": "recurso_rechazo",
    }


def test_owner_status_shows_the_documented_internal_inconsistency(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """TR-FUNC-013: the same predio (MP002's) is 'En tramite' under
    estado_resumido_first_row (see the summary test above) but 'Rechazado'
    here, under owner_stage_legacy — the documented divergence, made
    visible rather than silently reconciled."""

    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/owner-status").json()

    assert body["basis"] == "owner_stage_legacy"
    assert body["total_predio_count"] == 6

    by_key = {
        (row["tipo_propietario"], row["owner_stage"]): row["predio_count"] for row in body["rows"]
    }
    assert by_key[("Empresa Forestal", "Aprobado")] == 1
    assert by_key[("Empresa Forestal", "Rechazado")] == 2  # MP002's and MP005's predios
    assert by_key[("Empresa Forestal", "Pendiente")] == 1
    assert by_key[("Persona Natural", "Aprobado")] == 1
    assert by_key[("Persona Natural con Servidumbre firmada", "Aprobado")] == 1
    assert sum(by_key.values()) == 6


def test_pmf_detail_drawer_reports_the_estado_resumido_first_row_status(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/pmfs/MP001").json()

    assert body["pmf"] == "MP001"
    assert body["row_count"] == 2
    assert body["basis_estado_resumido"] == "estado_resumido_first_row"
    assert body["estado_resumido"] == "Aprobado"  # row 1 wins the dedup, not row 2's Tachado
    assert [row["estado_resumido"] for row in body["rows"]] == ["Aprobado", "Tachado"]


def test_pmf_detail_drawer_404s_for_an_unknown_pmf(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    response = client.get("/transelec/pmfs/DOES-NOT-EXIST")

    assert response.status_code == 404


def test_pmf_detail_drawer_requires_authentication(client: TestClient) -> None:
    """Not in READ_ROUTES above (it has a path parameter) — covered on its
    own so every route, not just the static-path ones, is proven to reject
    an unauthenticated caller."""

    response = client.get("/transelec/pmfs/MP001")

    assert response.status_code == 401


def test_pmf_detail_drawer_is_forbidden_for_a_forestry_only_operator(client: TestClient) -> None:
    _login_with_grants(client, "forestry-only-operator-pmf", (("forestry", Role.OPERATOR),))

    response = client.get("/transelec/pmfs/MP001")

    assert response.status_code == 403


def test_pmf_detail_drawer_never_needs_a_csrf_token(client: TestClient) -> None:
    _login(client, "dev-admin")
    del client.headers[CSRF_HEADER_NAME]

    response = client.get("/transelec/pmfs/MP001")

    assert response.status_code != 403 or response.json().get("detail") != (
        "CSRF verification failed."
    )


# ---------------------------------------------------------------------------
# Report — TR-FUNC-034, the real renderReport() template (Actualizable's
# wording), with the hardcoded 14-08-2026 replaced by the active import's
# own publish date.
# ---------------------------------------------------------------------------


def test_report_text_matches_hand_computed_values_from_the_fixture(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    active = client.get("/transelec/imports/active").json()
    published_at = datetime.fromisoformat(active["published_at"])
    expected_corte = published_at.strftime("%d-%m-%Y")

    body = client.get("/transelec/report").json()

    assert body["basis_estado_resumido"] == "estado_resumido_first_row"
    assert body["basis_pending_priority"] == "pending_priority_legacy"

    # Hand-computed from the rich fixture (see the summary test above):
    # pmf_count=6, predio_count=6, rol_count=6, surface_total=32.5,
    # aprobados=3, en_tramite=1, avance_por_pmf.pendiente_o_tachado=2
    # (3+1+2=6), rate=3/6*100=50.0, con_servidumbre_predio_count=1.
    expected_text = (
        "REPORTE EJECUTIVO · SEGUIMIENTO CONAF\n"
        f"Corte de información: {expected_corte}\n"
        "\n"
        "El alcance seleccionado comprende 6 PMF, 6 predios identificados y 6 roles, "
        "con 32,50 ha de superficie de corta.\n"
        "\n"
        "Estado resumido: 3 PMF aprobados (50,00%), 1 en trámite y 2 PMF con registros "
        "Pendiente o Tachado. Se identifican 1 predios con servidumbre firmada.\n"
        "\n"
        "Criterio: los PMF y predios se cuentan sin duplicados; la superficie "
        "corresponde a la suma de las áreas de corta filtradas. El N.º de ingreso se "
        "vincula al PMF correspondiente. Las resoluciones no pueden verificarse porque "
        "la fuente no incluye un campo específico para ellas."
    )
    assert body["text"] == expected_text


def test_report_reflects_the_active_imports_publish_date_not_request_time(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """The literal source template hardcodes a snapshot date; this must
    never be replaced with request-time `now()` either — two calls a
    moment apart must return the identical date/`generated_at`, and that
    date must match the fixture's own publish timestamp, not whenever the
    test happened to call the endpoint."""

    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    active = client.get("/transelec/imports/active").json()

    first = client.get("/transelec/report").json()
    time.sleep(0.05)
    second = client.get("/transelec/report").json()

    assert first["generated_at"] == second["generated_at"]
    assert first["generated_at"] == active["published_at"]

    expected_corte = datetime.fromisoformat(active["published_at"]).strftime("%d-%m-%Y")
    assert f"Corte de información: {expected_corte}" in first["text"]
    assert "Corte de información: 14-08-2026" not in first["text"]


# ---------------------------------------------------------------------------
# Filter-consistency — TR-FUNC-017's acceptance test, automated
# ---------------------------------------------------------------------------


def test_filter_consistency_summary_and_pmfs_agree_on_the_same_filter_state(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    unfiltered_summary = client.get("/transelec/summary").json()
    unfiltered_pmfs = client.get("/transelec/pmfs", params={"limit": 50}).json()
    assert unfiltered_pmfs["total_count"] == 7
    assert unfiltered_summary["row_count"] == 7

    filtered_summary = client.get("/transelec/summary", params={"sector": "Sector Norte"}).json()
    filtered_pmfs = client.get(
        "/transelec/pmfs", params={"sector": "Sector Norte", "limit": 50}
    ).json()
    filtered_pending = client.get("/transelec/pending", params={"sector": "Sector Norte"}).json()

    # Rows 1, 2, 5, 7 are "Sector Norte" -> PMFs {MP001, MP004, MP006} (3 distinct).
    assert filtered_summary["pmf_count"] == 3
    assert filtered_summary["predio_count"] == 3
    assert filtered_pmfs["total_count"] == 4  # row-grain: MP001 contributes 2 rows
    assert {item["pmf"] for item in filtered_pmfs["items"]} == {"MP001", "MP004", "MP006"}
    # The pending section's own PMF total, under the SAME filter, must agree
    # with the summary's pmf_count for that filter state.
    assert filtered_pending["total_pmf_count"] == filtered_summary["pmf_count"]


def test_multiselect_filters_are_ored_within_and_anded_across(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    # OR within sector: Norte + Sur covers everything except MP005 (Este).
    or_within = client.get(
        "/transelec/pmfs",
        params={"sector": ["Sector Norte", "Sector Sur"], "limit": 50},
    ).json()
    assert or_within["total_count"] == 6  # all rows except MP005's single row

    # AND across fields: sector=Norte AND pas=PAS-A AND empresa=Forestal Sur
    # matches rows 1, 2, 5, 7; adding a pas that excludes them empties the set.
    and_across_match = client.get(
        "/transelec/pmfs",
        params={"sector": "Sector Norte", "pas": "PAS-A", "empresa": "Forestal Sur", "limit": 50},
    ).json()
    assert and_across_match["total_count"] == 4

    and_across_empty = client.get(
        "/transelec/pmfs",
        params={"sector": "Sector Norte", "pas": "PAS-B", "limit": 50},
    ).json()
    assert and_across_empty["total_count"] == 0


def test_free_text_search_matches_across_fields_case_insensitively(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    body = client.get("/transelec/pmfs", params={"q": "RECHAZ", "limit": 50}).json()

    # Row 2 ("Rechazado"), row 3 ("Rechazado por CONAF"), and row 6
    # ("Recurso por rechazo administrativo") all contain the substring,
    # case-insensitively, in their Estado field.
    assert body["total_count"] == 3
    assert {item["pmf"] for item in body["items"]} == {"MP001", "MP002", "MP005"}


# ---------------------------------------------------------------------------
# Pagination correctness — no hidden row cap
# ---------------------------------------------------------------------------


def test_pmfs_pagination_has_no_hidden_cap_and_pages_through_every_row(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    total_rows = 123  # deliberately not a round number, and well above any typical page size
    _publish_fixture(client, integration_engine, _many_rows_workbook(tmp_path, total_rows))

    seen_pmfs: list[str] = []
    cursor: str | None = None
    page_count = 0

    while True:
        params: dict[str, Any] = {"limit": 20}
        if cursor is not None:
            params["cursor"] = cursor
        page = client.get("/transelec/pmfs", params=params).json()
        page_count += 1

        assert page["total_count"] == total_rows
        assert len(page["items"]) <= 20
        seen_pmfs.extend(item["pmf"] for item in page["items"])

        if not page["has_more"]:
            assert page["next_cursor"] is None
            break

        cursor = page["next_cursor"]
        assert cursor is not None
        assert page_count < 20  # sanity bound against an infinite loop

    assert len(seen_pmfs) == total_rows
    assert len(set(seen_pmfs)) == total_rows  # no duplicate, no skipped row
    assert page_count == 7  # ceil(123 / 20)


def test_pmfs_page_size_is_configurable_and_bounded(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _many_rows_workbook(tmp_path, 10))

    small_page = client.get("/transelec/pmfs", params={"limit": 3}).json()
    assert len(small_page["items"]) == 3
    assert small_page["has_more"] is True

    too_large = client.get("/transelec/pmfs", params={"limit": 99999})
    assert too_large.status_code == 422  # exceeds the declared le=200 bound


def test_invalid_cursor_is_a_client_error_not_a_server_error(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    response = client.get("/transelec/pmfs", params={"cursor": "not-a-valid-cursor!!"})

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# CSV export — TR-FUNC-037, mandatory formula-injection hardening
# ---------------------------------------------------------------------------


def test_export_csv_field_set_and_bom_and_delimiter(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _rich_fixture_workbook(tmp_path))

    response = client.get("/transelec/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text_body = response.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text_body), delimiter=";")
    header = next(reader)
    # 17 Actualizable fields, Carpeta split into 2 positional columns: 18.
    assert len(header) == 18
    assert "PMF" in header
    assert "Predio Ref" in header  # Actualizable's addition
    assert "Estado" not in header  # raw Estado excluded, per Actualizable
    assert "Carpeta PMF" in header
    assert "Carpeta normalizada" in header
    assert "Observación auxiliar" in header
    data_rows = list(reader)
    assert len(data_rows) == 7
    # Observación auxiliar is always empty (Pendientes-sheet field, out of
    # scope for V1's auto-merge non-goals) — never populated for any row.
    auxiliar_index = header.index("Observación auxiliar")
    assert all(row[auxiliar_index] == "" for row in data_rows)


def test_export_csv_neutralizes_a_real_exported_row_with_dangerous_values(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """The exact mandatory requirement: a real exported row whose cell
    values begin with =, +, -, or @ must never reach Excel as live formulas."""

    _login(client, "dev-admin")
    _publish_fixture(
        client, integration_engine, _injection_workbook(tmp_path), filename="injection.xlsx"
    )

    response = client.get("/transelec/export.csv")
    assert response.status_code == 200

    text_body = response.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text_body), delimiter=";")
    header = next(reader)
    row = next(reader)
    record = dict(zip(header, row, strict=True))

    assert record["PAS"] == "'+1+1"
    assert record["Empresa"] == "'-2+3"
    assert record["Sector"] == "'@cmd|'/c calc'!A1"
    assert record["Estado resumido"] == "'=SUM(1+1)"
    for value in record.values():
        assert not value.startswith(("=", "+", "-", "@"))


# ---------------------------------------------------------------------------
# Version metadata — /imports and /imports/active read from
# transelec_publish_event, not transelec_import
# ---------------------------------------------------------------------------


def test_active_import_reads_publish_actor_and_timestamp_from_the_publish_event(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """The validating user (dev-admin) and the publishing user (a distinct
    transelec-operator) are different — proving published_by_* comes from
    transelec_publish_event, not from transelec_import.validated_by."""

    _login(client, "dev-admin")
    upload = _upload(client, _rich_fixture_workbook(tmp_path))
    run_id = _ingestion_run_id(integration_engine, upload.json()["source_snapshot_id"])
    validated = client.post(
        f"/transelec/imports/{run_id}/validate-and-project", headers={"Origin": _SAME_ORIGIN}
    )
    import_id = validated.json()["import_id"]

    _login_with_grants(client, "transelec-publisher", (("transelect", Role.OPERATOR),))
    published = client.post(
        f"/transelec/imports/{import_id}/publish", headers={"Origin": _SAME_ORIGIN}
    )
    assert published.status_code == 200, published.text

    body = client.get("/transelec/imports/active").json()

    assert body["import_id"] == import_id
    assert body["published_by_display_name"] == "transelec-publisher"
    assert body["published_event_type"] == "publish"
    # Sanity: the response never silently substitutes validated_at for
    # published_at even if a caller (or a future refactor) confused them.
    assert body["published_at"] == published.json()["occurred_at"]


def test_active_import_reflects_the_most_recent_activation_after_a_restore(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    first_import_id = _publish_fixture(
        client, integration_engine, _rich_fixture_workbook(tmp_path), filename="a.xlsx"
    )
    second_import_id = _publish_fixture(
        client, integration_engine, _many_rows_workbook(tmp_path, 3), filename="b.xlsx"
    )
    assert second_import_id != first_import_id

    restored = client.post(
        f"/transelec/imports/{first_import_id}/restore", headers={"Origin": _SAME_ORIGIN}
    )
    assert restored.status_code == 200, restored.text

    body = client.get("/transelec/imports/active").json()

    assert body["import_id"] == first_import_id
    assert body["published_event_type"] == "restore"
    assert body["published_at"] == restored.json()["occurred_at"]


def test_imports_history_lists_every_activation_newest_first(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    first_import_id = _publish_fixture(
        client, integration_engine, _rich_fixture_workbook(tmp_path), filename="a.xlsx"
    )
    second_import_id = _publish_fixture(
        client, integration_engine, _many_rows_workbook(tmp_path, 3), filename="b.xlsx"
    )
    client.post(f"/transelec/imports/{first_import_id}/restore", headers={"Origin": _SAME_ORIGIN})

    body = client.get("/transelec/imports").json()

    assert [row["event_type"] for row in body] == ["restore", "publish", "publish"]
    assert body[0]["import_id"] == first_import_id
    assert body[0]["is_active"] is True
    assert body[1]["import_id"] == second_import_id
    assert body[1]["is_active"] is False


# ---------------------------------------------------------------------------
# Run/import lookup — the ingestion_run_id resolution Task 3 flagged
# ---------------------------------------------------------------------------


def test_recent_uploads_resolves_ingestion_run_id_by_source_snapshot_id(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    upload = _upload(client, _rich_fixture_workbook(tmp_path))
    source_snapshot_id = upload.json()["source_snapshot_id"]

    body = client.get("/transelec/uploads/recent").json()

    matching = [row for row in body if row["source_snapshot_id"] == source_snapshot_id]
    assert len(matching) == 1
    assert matching[0]["import_id"] is None  # not validated-and-projected yet
    assert matching[0]["is_active"] is False
    assert isinstance(matching[0]["ingestion_run_id"], int)


def test_recent_uploads_reflects_active_status_after_publish(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    upload = _upload(client, _rich_fixture_workbook(tmp_path))
    source_snapshot_id = upload.json()["source_snapshot_id"]
    run_id = _ingestion_run_id(integration_engine, source_snapshot_id)
    validated = client.post(
        f"/transelec/imports/{run_id}/validate-and-project", headers={"Origin": _SAME_ORIGIN}
    )
    import_id = validated.json()["import_id"]
    client.post(f"/transelec/imports/{import_id}/publish", headers={"Origin": _SAME_ORIGIN})

    body = client.get("/transelec/uploads/recent").json()
    matching = next(row for row in body if row["source_snapshot_id"] == source_snapshot_id)

    assert matching["import_id"] == import_id
    assert matching["is_active"] is True
