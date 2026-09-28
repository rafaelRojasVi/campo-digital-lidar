"""Transelec mutations end-to-end: lifecycle, RBAC, CSRF, audit, isolation.

Exercises the full four-step path against real PostgreSQL — upload →
validate-and-project → publish → restore — plus the separations the design
depends on: Step B commits without activating, publish is never automatic,
and a failed Step B rolls back completely while leaving the active version
byte-identical.

All fixture workbooks are synthetic and built here. None reproduces the
reviewed 14-Aug snapshot's 729/159/272 counts.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Generator
from datetime import timedelta
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
from sqlalchemy.exc import DataError

from transelec_ingestion import import_projection
from transelec_ingestion.xlsx_contract import (
    CURRENT_RESUMEN_COLUMNS,
    EXPECTED_RESUMEN_HEADERS,
    RESUMEN_COLUMNS,
)

_platform_sessions = PlatformSessionStore()

_SAME_ORIGIN = "http://testserver"
_ATTACKER_ORIGIN = "https://evil.example"

MUTATION_ROUTES = (
    ("/transelec/uploads", "upload"),
    ("/transelec/imports/1/validate-and-project", "plain"),
    ("/transelec/imports/1/publish", "plain"),
    ("/transelec/imports/1/restore", "plain"),
)


# ---------------------------------------------------------------------------
# Synthetic workbooks
# ---------------------------------------------------------------------------


def _source_row(**overrides: Any) -> list[Any]:
    values: dict[str, Any] = {field_name: None for _, field_name in RESUMEN_COLUMNS}
    values.update(
        {
            "pmf": "MP001",
            "rol": "123-45",
            "numero_predio": "7",
            "estado_resumido": "En tramite",
            "id_predio_unico": "MP001-123-45-7",
            "carpeta_source": "COLUMNA-E",
            "carpeta_normalizada": "COLUMNA-AC",
            "superficie_corta": 1.25,
        }
    )
    values.update(overrides)
    return [values[field_name] for _, field_name in RESUMEN_COLUMNS]


def _workbook_bytes(
    tmp_path: Path,
    name: str,
    rows: list[list[Any]],
    *,
    headers: tuple[str, ...] = EXPECTED_RESUMEN_HEADERS,
) -> bytes:
    path = tmp_path / name
    workbook = xlsxwriter.Workbook(path)
    # xlsxwriter stamps the file with the current second; pin it so a workbook
    # rebuilt for a re-upload has the same bytes, and so the same content hash.
    workbook.set_properties({"created": dt.datetime(2026, 1, 1)})
    worksheet = workbook.add_worksheet("Resumen")
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})

    for column, header in enumerate(headers):
        worksheet.write(0, column, header)

    for row_index, row in enumerate(rows, start=1):
        for column, value in enumerate(row):
            if value is None:
                continue
            if isinstance(value, dt.date):
                worksheet.write_datetime(
                    row_index,
                    column,
                    dt.datetime(value.year, value.month, value.day),
                    date_format,
                )
            else:
                worksheet.write(row_index, column, value)

    workbook.close()
    return path.read_bytes()


def _valid_workbook(tmp_path: Path, name: str = "resumen.xlsx", *, marker: str = "A") -> bytes:
    """Three business rows, two PMFs, two provisional predio ids.

    ``marker`` varies the content so two calls produce different SHA-256
    digests and therefore different source snapshots.
    """

    return _workbook_bytes(
        tmp_path,
        name,
        [
            _source_row(superficie_corta=1.5, numero_ingreso=marker),
            _source_row(id_predio_unico=None, superficie_corta=0.5),
            _source_row(pmf="MP002", id_predio_unico="MP002-9-1", superficie_corta=2.0),
            _source_row(pmf=None),
        ],
    )


def _contract_violating_workbook(tmp_path: Path) -> bytes:
    headers = list(EXPECTED_RESUMEN_HEADERS)
    headers[3] = "PMF renombrado"
    return _workbook_bytes(tmp_path, "violating.xlsx", [_source_row()], headers=tuple(headers))


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
    """Authenticate as a seeded dev identity and fetch a CSRF token."""

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
    """Authenticate a purpose-built identity with exactly ``grants``."""

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


def _upload(client: TestClient, content: bytes) -> Response:
    return client.post(
        "/transelec/uploads",
        files={
            "file": (
                "resumen.xlsx",
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


def _active_import_id(engine: Engine) -> int | None:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT active_import_id FROM platform.transelec_dashboard_state WHERE id = 1")
        ).scalar_one()


def _audit_event_types(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return [
            row.event_type
            for row in connection.execute(
                text("SELECT event_type FROM platform.audit_event ORDER BY id")
            ).all()
        ]


def _upload_and_validate(
    client: TestClient, engine: Engine, content: bytes
) -> tuple[int, Response]:
    """Run Step A then Step B; return the ingestion run id and Step B response."""

    upload = _upload(client, content)
    assert upload.status_code == 200, upload.text
    run_id = _ingestion_run_id(engine, upload.json()["source_snapshot_id"])

    response = client.post(
        f"/transelec/imports/{run_id}/validate-and-project",
        headers={"Origin": _SAME_ORIGIN},
    )
    return run_id, response


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


def test_full_lifecycle_upload_validate_publish_restore(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")

    _, first = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["status"] == "validated"
    assert first_body["business_rows"] == 3
    assert first_body["distinct_pmf"] == 2
    assert first_body["distinct_provisional_predio_ids"] == 2
    assert first_body["surface_total"] == pytest.approx(4.0)
    assert first_body["is_active"] is False
    first_import_id = first_body["import_id"]

    # Step B committed but activated nothing.
    assert _active_import_id(integration_engine) is None

    published = client.post(
        f"/transelec/imports/{first_import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["event_type"] == "publish"
    assert published.json()["previous_import_id"] is None
    assert published.json()["active_import_id"] == first_import_id
    assert _active_import_id(integration_engine) == first_import_id

    # A second, different workbook: validated and published, superseding the first.
    _, second = _upload_and_validate(
        client, integration_engine, _valid_workbook(tmp_path, "resumen2.xlsx", marker="B")
    )
    assert second.status_code == 200, second.text
    second_import_id = second.json()["import_id"]
    assert second_import_id != first_import_id
    assert second.json()["is_active"] is False
    assert _active_import_id(integration_engine) == first_import_id

    client.post(
        f"/transelec/imports/{second_import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )
    assert _active_import_id(integration_engine) == second_import_id

    restored = client.post(
        f"/transelec/imports/{first_import_id}/restore",
        headers={"Origin": _SAME_ORIGIN},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "restored"
    assert restored.json()["event_type"] == "restore"
    assert restored.json()["previous_import_id"] == second_import_id
    assert _active_import_id(integration_engine) == first_import_id

    with integration_engine.connect() as connection:
        events = connection.execute(
            text("SELECT import_id, event_type FROM platform.transelec_publish_event ORDER BY id")
        ).all()

    assert [(row.import_id, row.event_type) for row in events] == [
        (first_import_id, "publish"),
        (second_import_id, "publish"),
        (first_import_id, "restore"),
    ]

    event_types = _audit_event_types(integration_engine)
    assert event_types.count("import.validated") == 2
    assert event_types.count("import.published") == 2
    assert event_types.count("import.restored") == 1


def test_duplicate_upload_is_idempotent_and_never_double_imports(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    content = _valid_workbook(tmp_path)

    _, first = _upload_and_validate(client, integration_engine, content)
    first_import_id = first.json()["import_id"]

    _, second = _upload_and_validate(client, integration_engine, content)

    assert second.status_code == 200, second.text
    assert second.json()["status"] == "already_imported"
    assert second.json()["import_id"] == first_import_id
    assert second.json()["is_active"] is False

    with integration_engine.connect() as connection:
        imports = connection.execute(
            text("SELECT count(*) FROM platform.transelec_import")
        ).scalar_one()
        rows = connection.execute(
            text("SELECT count(*) FROM platform.transelec_resumen_row")
        ).scalar_one()

    assert (imports, rows) == (1, 3)


def test_reuploading_the_active_version_reports_already_current(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    content = _valid_workbook(tmp_path)

    _, first = _upload_and_validate(client, integration_engine, content)
    import_id = first.json()["import_id"]
    client.post(
        f"/transelec/imports/{import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )

    _, again = _upload_and_validate(client, integration_engine, content)

    assert again.json()["status"] == "already_current"
    assert again.json()["is_active"] is True
    assert _active_import_id(integration_engine) == import_id


# ---------------------------------------------------------------------------
# Transactional separation
# ---------------------------------------------------------------------------


def test_validated_import_does_not_become_active_until_publish_is_called(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")

    _, response = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))

    assert response.json()["status"] == "validated"
    assert response.json()["is_active"] is False
    assert _active_import_id(integration_engine) is None

    with integration_engine.connect() as connection:
        publish_events = connection.execute(
            text("SELECT count(*) FROM platform.transelec_publish_event")
        ).scalar_one()

    assert publish_events == 0
    assert "import.published" not in _audit_event_types(integration_engine)


def test_invariant_failure_mid_step_b_rolls_back_and_leaves_the_active_version_unchanged(
    client: TestClient,
    integration_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publish a first version, then force Step B to fail on a second upload:
    no import/row rows may persist and active_import_id must be identical
    before and after, because publish (Step C) was never invoked."""

    _login(client, "dev-admin")

    _, first = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))
    published_import_id = first.json()["import_id"]
    client.post(
        f"/transelec/imports/{published_import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )

    active_before = _active_import_id(integration_engine)
    with integration_engine.connect() as connection:
        imports_before = connection.execute(
            text("SELECT count(*) FROM platform.transelec_import")
        ).scalar_one()
        rows_before = connection.execute(
            text("SELECT count(*) FROM platform.transelec_resumen_row")
        ).scalar_one()

    real = import_projection.read_persisted_aggregates

    def _skewed(connection: Any, *, import_id: int) -> Any:
        aggregates = real(connection, import_id=import_id)
        return type(aggregates)(
            business_rows=aggregates.business_rows,
            distinct_pmf=aggregates.distinct_pmf + 1,
            distinct_provisional_predio_ids=aggregates.distinct_provisional_predio_ids,
            surface_total=aggregates.surface_total,
            blank_predio_group_keys=aggregates.blank_predio_group_keys,
            orphaned_rows=aggregates.orphaned_rows,
        )

    monkeypatch.setattr(import_projection, "read_persisted_aggregates", _skewed)

    _, failed = _upload_and_validate(
        client, integration_engine, _valid_workbook(tmp_path, "resumen2.xlsx", marker="B")
    )

    assert failed.status_code == 500
    assert (
        failed.json()["detail"]
        == "No se pudo verificar la importación. La versión activa no cambió."
    )

    with integration_engine.connect() as connection:
        imports_after = connection.execute(
            text("SELECT count(*) FROM platform.transelec_import")
        ).scalar_one()
        rows_after = connection.execute(
            text("SELECT count(*) FROM platform.transelec_resumen_row")
        ).scalar_one()

    assert (imports_after, rows_after) == (imports_before, rows_before)
    assert _active_import_id(integration_engine) == active_before
    assert "import.validation.failed" in _audit_event_types(integration_engine)


def test_contract_violation_is_rejected_and_leaves_the_active_version_unchanged(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")

    _, first = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))
    import_id = first.json()["import_id"]
    client.post(
        f"/transelec/imports/{import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )
    active_before = _active_import_id(integration_engine)

    _, rejected = _upload_and_validate(
        client, integration_engine, _contract_violating_workbook(tmp_path)
    )

    assert rejected.status_code == 422
    assert _active_import_id(integration_engine) == active_before

    with integration_engine.connect() as connection:
        imports = connection.execute(
            text("SELECT count(*) FROM platform.transelec_import")
        ).scalar_one()

    assert imports == 1


def test_client_facing_errors_never_leak_technical_detail(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")

    _, rejected = _upload_and_validate(
        client, integration_engine, _contract_violating_workbook(tmp_path)
    )
    body = rejected.json()
    detail = body["detail"]

    assert detail == (
        "La planilla necesita revisión antes de importarse. Revise las observaciones indicadas "
        "(filas y columnas). La versión activa no cambió."
    )
    # The structured review report is for the operator; it is structural and
    # must carry neither technical detail nor anything from the file system.
    assert [issue["code"] for issue in body["report"]["issues"]] == ["encabezado_no_encontrado"]
    for leak in ("Traceback", "/tmp", ".xlsx", "Resumen layout:"):
        assert leak not in rejected.text

    # The technical detail is preserved in the audit ledger instead.
    with integration_engine.connect() as connection:
        metadata = connection.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'import.validation.failed' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()

    assert metadata["reason"] == "contract_violation"
    assert "encabezado_no_encontrado" in metadata["detail"]
    assert metadata["parser_version"].startswith("transelec_ingestion.resumen_layout@")


def test_a_database_failure_never_writes_row_content_to_the_audit_ledger_or_the_log(
    client: TestClient,
    integration_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected database error must not smuggle source content out.

    SQLAlchemy's StatementError family appends the failing statement AND its
    bound parameters to str(exc) — for this projection, that is every column
    value of the failing rows. app.audit's contract forbids putting raw
    source content in metadata, and the process log is no better a place for
    it, so the router records only the sanitized form.
    """

    _login(client, "dev-admin")
    secret = "PMF-CONFIDENCIAL-001"
    content = _workbook_bytes(
        tmp_path,
        "confidencial.xlsx",
        [_source_row(pmf=secret, id_predio_unico=f"{secret}-9-9")],
    )
    leaking_parameters = [{"pmf": secret, "predio_group_key": f"{secret}-9-9"}]

    def _fail_with_bound_parameters(connection: Any, **kwargs: Any) -> None:
        raise DataError(
            "INSERT INTO platform.transelec_resumen_row (pmf, predio_group_key) VALUES (%s, %s)",
            leaking_parameters,
            Exception("value too long for type character varying"),
        )

    monkeypatch.setattr(import_projection, "_insert_rows", _fail_with_bound_parameters)

    with caplog.at_level(logging.WARNING, logger="app.routers.transelec"):
        _, failed = _upload_and_validate(client, integration_engine, content)

    assert failed.status_code == 500
    assert secret not in failed.text

    with integration_engine.connect() as connection:
        metadata = connection.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'import.validation.failed' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()

    assert metadata["reason"] == "projection_error"
    assert metadata["detail"] == "DataError"
    serialized_metadata = json.dumps(metadata)
    assert secret not in serialized_metadata
    assert "parameters" not in serialized_metadata
    assert "INSERT INTO" not in serialized_metadata

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "DataError" in logged
    assert secret not in logged
    assert "parameters" not in logged
    assert "INSERT INTO" not in logged


# ---------------------------------------------------------------------------
# Not-found and failure paths
# ---------------------------------------------------------------------------


def test_validate_and_project_on_an_unknown_run_is_not_found(client: TestClient) -> None:
    _login(client, "dev-admin")

    response = client.post(
        "/transelec/imports/999999/validate-and-project", headers={"Origin": _SAME_ORIGIN}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "No se encontró la carga solicitada."


def test_validate_and_project_on_another_products_run_is_not_found(
    client: TestClient, integration_engine: Engine
) -> None:
    """A Transelec-granted caller must not learn that a Forestry run exists."""

    _login(client, "dev-admin")
    with integration_engine.begin() as connection:
        snapshot_id = connection.execute(
            text(
                """
                WITH s AS (
                    INSERT INTO platform.source_system (system_key)
                    VALUES ('cross_product_probe') RETURNING id
                ), a AS (
                    INSERT INTO platform.source_asset
                        (source_system_id, identity_kind, identity_key)
                    SELECT id, 'content_sha256', repeat('a', 64) FROM s RETURNING id
                )
                INSERT INTO platform.source_snapshot
                    (source_asset_id, content_sha256, byte_size)
                SELECT id, repeat('a', 64), 10 FROM a RETURNING id
                """
            )
        ).scalar_one()
        run_id = connection.execute(
            text(
                "INSERT INTO platform.ingestion_run (source_snapshot_id, product_key) "
                "VALUES (:snapshot_id, 'forestry') RETURNING id"
            ),
            {"snapshot_id": snapshot_id},
        ).scalar_one()

    response = client.post(
        f"/transelec/imports/{run_id}/validate-and-project", headers={"Origin": _SAME_ORIGIN}
    )

    assert response.status_code == 404


def test_publishing_an_unknown_import_is_not_found_and_audited_as_failed(
    client: TestClient, integration_engine: Engine
) -> None:
    _login(client, "dev-admin")

    response = client.post("/transelec/imports/999999/publish", headers={"Origin": _SAME_ORIGIN})

    assert response.status_code == 404
    assert response.json()["detail"] == "No se encontró la versión solicitada."
    assert "import.publish.failed" in _audit_event_types(integration_engine)
    assert _active_import_id(integration_engine) is None


def test_restoring_an_unknown_import_is_not_found(
    client: TestClient, integration_engine: Engine
) -> None:
    _login(client, "dev-admin")

    response = client.post("/transelec/imports/999999/restore", headers={"Origin": _SAME_ORIGIN})

    assert response.status_code == 404
    assert "import.publish.failed" in _audit_event_types(integration_engine)


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "kind"), MUTATION_ROUTES)
def test_viewer_is_forbidden_on_every_mutation_route(
    client: TestClient, tmp_path: Path, path: str, kind: str
) -> None:
    _login(client, "dev-viewer")  # transelect VIEWER only

    response = _post_mutation(client, path, kind, tmp_path)

    assert response.status_code == 403, response.text


@pytest.mark.parametrize(("path", "kind"), MUTATION_ROUTES)
def test_a_forestry_only_operator_is_forbidden_on_every_transelec_mutation(
    client: TestClient, tmp_path: Path, path: str, kind: str
) -> None:
    """Cross-product isolation: OPERATOR (including PUBLISH) on Forestry
    grants nothing at all on Transelec."""

    _login_with_grants(client, "forestry-only-operator", (("forestry", Role.OPERATOR),))

    response = _post_mutation(client, path, kind, tmp_path)

    assert response.status_code == 403, response.text


def test_operator_with_a_transelec_grant_can_run_the_whole_lifecycle(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", (("transelect", Role.OPERATOR),))

    _, validated = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))
    assert validated.status_code == 200, validated.text
    import_id = validated.json()["import_id"]

    published = client.post(
        f"/transelec/imports/{import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )
    restored = client.post(
        f"/transelec/imports/{import_id}/restore", headers={"Origin": _SAME_ORIGIN}
    )

    assert published.status_code == 200, published.text
    assert restored.status_code == 200, restored.text


def test_admin_can_run_the_whole_lifecycle(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-admin", (("transelect", Role.ADMIN),))

    _, validated = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))
    assert validated.status_code == 200, validated.text

    published = client.post(
        f"/transelec/imports/{validated.json()['import_id']}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )

    assert published.status_code == 200, published.text


# ---------------------------------------------------------------------------
# CSRF on every Transelec mutation route
# ---------------------------------------------------------------------------


def _post_mutation(client: TestClient, path: str, kind: str, tmp_path: Path, **kwargs: Any) -> Any:
    if kind == "upload":
        return client.post(
            path,
            files={"file": ("resumen.xlsx", _valid_workbook(tmp_path), "application/octet-stream")},
            **kwargs,
        )
    return client.post(path, **kwargs)


@pytest.mark.parametrize(("path", "kind"), MUTATION_ROUTES)
def test_mutation_without_a_csrf_token_is_forbidden(
    client: TestClient, tmp_path: Path, path: str, kind: str
) -> None:
    _login(client, "dev-admin")
    del client.headers[CSRF_HEADER_NAME]

    response = _post_mutation(client, path, kind, tmp_path)

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF verification failed."


@pytest.mark.parametrize(("path", "kind"), MUTATION_ROUTES)
def test_mutation_with_a_mismatched_csrf_token_is_forbidden(
    client: TestClient, tmp_path: Path, path: str, kind: str
) -> None:
    _login(client, "dev-admin")
    valid = client.headers[CSRF_HEADER_NAME]
    client.headers[CSRF_HEADER_NAME] = valid[:-1] + ("A" if valid[-1] != "A" else "B")

    response = _post_mutation(client, path, kind, tmp_path)

    assert response.status_code == 403


@pytest.mark.parametrize(("path", "kind"), MUTATION_ROUTES)
def test_cross_origin_mutation_is_forbidden_even_with_a_valid_token(
    client: TestClient, tmp_path: Path, path: str, kind: str
) -> None:
    _login(client, "dev-admin")

    response = _post_mutation(client, path, kind, tmp_path, headers={"Origin": _ATTACKER_ORIGIN})

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF verification failed."


@pytest.mark.parametrize(("path", "kind"), MUTATION_ROUTES)
def test_mutation_with_a_valid_token_and_same_origin_passes_csrf(
    client: TestClient, tmp_path: Path, path: str, kind: str
) -> None:
    """Not 403: the request reaches the route's own logic (200 for the
    upload boundary, 404 for the fabricated import/run ids)."""

    _login(client, "dev-admin")

    response = _post_mutation(client, path, kind, tmp_path, headers={"Origin": _SAME_ORIGIN})

    assert response.status_code != 403, response.text
    assert response.status_code in (200, 404), response.text


@pytest.mark.parametrize(("path", "kind"), MUTATION_ROUTES)
def test_mutation_without_a_session_is_unauthenticated(
    client: TestClient, tmp_path: Path, path: str, kind: str
) -> None:
    response = _post_mutation(client, path, kind, tmp_path)

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Contract V2: recognized layout, AEF tracking block, review report
# ---------------------------------------------------------------------------

_CURRENT_HEADERS = tuple(header for header, _ in CURRENT_RESUMEN_COLUMNS)


def _current_row(**overrides: Any) -> list[Any]:
    values: dict[str, Any] = {field_name: None for _, field_name in CURRENT_RESUMEN_COLUMNS}
    values.update(
        {
            "pmf": "MP001",
            "rol": "123-45",
            "numero_predio": "7",
            "estado": "Aprobado",
            "estado_resumido": "Aprobado",
            "id_predio_unico": "MP001-123-45-7",
            "carpeta_source": "COLUMNA-J",
            "carpeta_normalizada": "COLUMNA-AH",
            "superficie_corta": 1.25,
        }
    )
    values.update(overrides)
    return [values[field_name] for _, field_name in CURRENT_RESUMEN_COLUMNS]


def _aef_workbook(tmp_path: Path) -> bytes:
    """09-Sept layout: each PMF's AEF data on one of its rows, other rows
    blank (as in the real workbook); MP002's dates are out of order."""

    return _workbook_bytes(
        tmp_path,
        "aef.xlsx",
        [
            _current_row(
                aef="Presentado",
                quien_solicita="Persona A",
                fecha_solicitud=dt.date(2026, 7, 3),
                fecha_corta=dt.date(2026, 7, 9),
                fecha_termino=dt.date(2026, 9, 1),
            ),
            _current_row(
                pmf="MP002",
                id_predio_unico="MP002-2",
                aef="Solicitado, se puede cortar",
                fecha_solicitud=dt.date(2026, 8, 20),
                fecha_corta=dt.date(2026, 8, 19),
                fecha_termino=dt.date(2026, 9, 1),
            ),
            _current_row(numero_predio="8", id_predio_unico="MP001-123-45-8"),
            _current_row(pmf="MP002", id_predio_unico="MP002-1"),
        ],
        headers=_CURRENT_HEADERS,
    )


def _aef_conflict_workbook(tmp_path: Path) -> bytes:
    """Synthetic: MP001 has two different non-blank AEF values; text dates."""

    return _workbook_bytes(
        tmp_path,
        "aef-conflict.xlsx",
        [
            _current_row(aef="Presentado", fecha_ingreso="13 de noviembre de 2024"),
            _current_row(numero_predio="8", id_predio_unico="MP001-123-45-8"),
            _current_row(
                numero_predio="9",
                id_predio_unico="MP001-123-45-9",
                aef="Solicitado, se puede cortar",
                fecha_ingreso="20-12-2024 09-06-26",
            ),
            _current_row(pmf="MP002", id_predio_unico="MP002-1", fecha_ingreso="-"),
        ],
        headers=_CURRENT_HEADERS,
    )


def test_v2_workbook_imports_with_its_review_report_and_is_not_published(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")

    _, response = _upload_and_validate(client, integration_engine, _aef_workbook(tmp_path))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "validated"
    assert body["is_active"] is False
    assert _active_import_id(integration_engine) is None
    assert body["schema_contract_version"] == "transelec-resumen-v2"
    assert body["warning_count"] == 1
    report = body["mapping_report"]
    assert report["header_row"] == 1
    warning = next(i for i in report["issues"] if i["severity"] == "warning")
    assert (warning["code"], warning["rows"], warning["columns"]) == (
        "cronologia_corta_antes_de_solicitud",
        [3],
        ["C", "D"],
    )
    mapped = {c["field"]: c["column"] for c in report["columns"] if c["status"] == "mapped"}
    assert (mapped["aef"], mapped["carpeta_source"], mapped["carpeta_normalizada"]) == (
        "A",
        "J",
        "AH",
    )

    with integration_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT source_row_number, aef, quien_solicita, fecha_corta, carpeta_source "
                "FROM platform.transelec_resumen_row WHERE import_id = :id "
                "ORDER BY source_row_number"
            ),
            {"id": body["import_id"]},
        ).all()
        stored = connection.execute(
            text("SELECT warning_count, mapping_report FROM platform.transelec_import")
        ).one()
        audit = connection.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'import.validated' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()

    assert [(r.source_row_number, r.aef, r.quien_solicita) for r in rows] == [
        (2, "Presentado", "Persona A"),
        (3, "Solicitado, se puede cortar", None),
        (4, None, None),
        (5, None, None),
    ]
    # The inverted date is stored as the source had it.
    assert rows[1].fecha_corta == dt.date(2026, 8, 19)
    assert rows[0].carpeta_source == "COLUMNA-J"
    assert stored.warning_count == 1
    assert stored.mapping_report["issues"] == report["issues"]
    assert audit["warning_codes"] == ["cronologia_corta_antes_de_solicitud"]

    # Re-validating identical content returns the persisted report unchanged.
    _, again = _upload_and_validate(client, integration_engine, _aef_workbook(tmp_path))
    assert again.json()["status"] == "already_imported"
    assert again.json()["mapping_report"] == report


def test_ambiguous_or_conflicting_layout_is_refused_with_references_and_no_values(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    secret = "VALOR-PRIVADO-9"
    headers = (*_CURRENT_HEADERS, "Estado resumido")
    content = _workbook_bytes(
        tmp_path,
        "conflict.xlsx",
        [
            [*_current_row(), "Aprobado"],
            [*_current_row(pmf="MP002", estado_resumido=secret), "En tramite"],
        ],
        headers=headers,
    )

    _, rejected = _upload_and_validate(client, integration_engine, content)

    assert rejected.status_code == 422
    issue = next(i for i in rejected.json()["report"]["issues"] if i["severity"] == "error")
    assert (issue["code"], issue["columns"], issue["rows"]) == (
        "encabezado_duplicado_conflictivo",
        ["M", "AJ"],
        [3],
    )
    assert secret not in rejected.text

    with integration_engine.connect() as connection:
        imports = connection.execute(
            text("SELECT count(*) FROM platform.transelec_import")
        ).scalar_one()
        metadata = connection.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'import.validation.failed' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()

    assert imports == 0
    assert "encabezado_duplicado_conflictivo" in metadata["detail"]
    assert secret not in str(metadata)


def test_import_report_requires_an_operator_grant(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _, response = _upload_and_validate(client, integration_engine, _aef_workbook(tmp_path))
    import_id = response.json()["import_id"]

    report = client.get(f"/transelec/imports/{import_id}/report")
    assert report.status_code == 200
    assert report.json()["warning_count"] == 1
    assert "aef" in report.json()["source_fields"]
    assert client.get("/transelec/imports/999999/report").status_code == 404

    _login(client, "dev-viewer")
    assert client.get(f"/transelec/imports/{import_id}/report").status_code == 403


def test_aef_reads_after_explicit_publish(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _, response = _upload_and_validate(client, integration_engine, _aef_workbook(tmp_path))
    import_id = response.json()["import_id"]
    assert client.get("/transelec/aef").status_code == 404  # nothing published yet
    client.post(
        f"/transelec/imports/{import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )

    aef = client.get("/transelec/aef").json()
    assert aef["source_fields"] == [
        "aef",
        "quien_solicita",
        "fecha_solicitud",
        "fecha_corta",
        "fecha_termino",
    ]
    assert aef["basis"] == "pmf_from_source_rows"
    # Row level: only the rows that carry values, nothing filled down.
    assert (aef["row_count"], aef["rows_with_aef"], aef["rows_with_quien_solicita"]) == (4, 2, 1)
    assert [row["source_row_number"] for row in aef["rows"]] == [2, 3]
    assert aef["rows"][1]["chronology_flags"] == ["cronologia_corta_antes_de_solicitud"]
    assert aef["rows_with_chronology_warning"] == 1
    # PMF level: each value names the row that supplied it.
    assert (aef["pmf_with_tracking"], aef["pmf_with_aef"], aef["pmf_with_conflict"]) == (2, 2, 0)
    by_pmf = {entry["pmf"]: entry for entry in aef["pmfs"]}
    mp001 = by_pmf["MP001"]
    assert (mp001["total_rows"], mp001["source_row_numbers"]) == (2, [2, 4])
    assert mp001["fields"]["aef"] == {
        "status": "value",
        "value": "Presentado",
        "value_kind": "text",
        "source_rows": [2],
        "variants": [{"value": "Presentado", "source_rows": [2]}],
    }
    assert mp001["fields"]["fecha_termino"]["value"] == "2026-09-01"
    assert mp001["fields"]["fecha_termino"]["value_kind"] == "date"
    assert by_pmf["MP002"]["chronology_flags"] == ["cronologia_corta_antes_de_solicitud"]
    assert by_pmf["MP002"]["fields"]["quien_solicita"]["status"] == "blank"
    assert aef["pmf_por_aef"] == [
        {"label": "Presentado", "count": 1},
        {"label": "Solicitado, se puede cortar", "count": 1},
    ]

    filtered = client.get("/transelec/pmfs", params={"aef": "Presentado"}).json()
    assert [row["source_row_number"] for row in filtered["items"]] == [2]
    assert filtered["items"][0]["fecha_termino"] == "2026-09-01"
    by_requester = client.get("/transelec/aef", params={"quien_solicita": "Persona A"}).json()
    assert by_requester["row_count"] == 1
    # A filter that keeps only MP001's blank row still shows MP001's values,
    # from all of its rows.
    blank_row = client.get("/transelec/aef", params={"q": "MP001-123-45-8"}).json()
    assert (blank_row["row_count"], blank_row["rows_with_aef"]) == (1, 0)
    assert [(p["pmf"], p["fields"]["aef"]["source_rows"]) for p in blank_row["pmfs"]] == [
        ("MP001", [2])
    ]

    active = client.get("/transelec/imports/active").json()
    assert active["warning_count"] == 1
    assert "fecha_termino" in active["source_fields"]


def test_pmf_conflicts_and_text_dates_are_reviewed_not_resolved(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _, response = _upload_and_validate(client, integration_engine, _aef_conflict_workbook(tmp_path))
    assert response.status_code == 200, response.text
    body = response.json()
    issues = {
        (issue["code"], issue["field"]): (issue["severity"], issue["rows"])
        for issue in body["mapping_report"]["issues"]
        if issue["code"] == "aef_conflicto_pmf" or issue["code"].startswith("fecha_")
    }
    assert issues == {
        ("aef_conflicto_pmf", "aef"): ("warning", [2, 4]),
        ("fecha_texto_interpretada", "fecha_ingreso"): ("info", [2]),
        ("fecha_texto_multiple", "fecha_ingreso"): ("warning", [4]),
        ("fecha_texto_guion", "fecha_ingreso"): ("warning", [5]),
    }
    assert body["warning_count"] == 3

    # Publishing still requires the explicit acknowledgement.
    refused = client.post(
        f"/transelec/imports/{body['import_id']}/publish", headers={"Origin": _SAME_ORIGIN}
    )
    assert refused.status_code == 409
    client.post(
        f"/transelec/imports/{body['import_id']}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )

    aef = client.get("/transelec/aef").json()
    (mp001,) = aef["pmfs"]
    assert mp001["has_conflict"] is True
    assert mp001["fields"]["aef"]["status"] == "conflict"
    assert mp001["fields"]["aef"]["value"] is None
    assert mp001["fields"]["aef"]["variants"] == [
        {"value": "Presentado", "source_rows": [2]},
        {"value": "Solicitado, se puede cortar", "source_rows": [4]},
    ]
    assert (aef["pmf_with_conflict"], aef["pmf_conflicts_by_field"]["aef"]) == (1, 1)
    # Each row keeps its own value.
    assert [(r["source_row_number"], r["aef"]) for r in aef["rows"]] == [
        (2, "Presentado"),
        (4, "Solicitado, se puede cortar"),
    ]

    rows = {row["source_row_number"]: row for row in client.get("/transelec/pmfs").json()["items"]}
    assert rows[2]["fecha_ingreso"] == "2024-11-13"
    assert rows[2]["source_text_dates"]["fecha_ingreso"] == {
        "raw": "13 de noviembre de 2024",
        "resolution": "parsed_spanish_long",
        "parsed": "2024-11-13",
    }
    assert rows[4]["fecha_ingreso"] is None
    assert rows[4]["source_text_dates"]["fecha_ingreso"]["raw"] == "20-12-2024 09-06-26"
    assert rows[5]["source_text_dates"]["fecha_ingreso"]["resolution"] == "placeholder"
    assert rows[3]["source_text_dates"] == {}


def test_legacy_layout_reports_the_aef_columns_as_absent(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _, response = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))
    client.post(
        f"/transelec/imports/{response.json()['import_id']}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )

    aef = client.get("/transelec/aef").json()
    assert aef["source_fields"] == []
    assert aef["rows_with_any_tracking"] == 0
    assert "aef" not in client.get("/transelec/imports/active").json()["source_fields"]


def test_an_import_made_under_contract_v1_reports_exactly_the_legacy_fields(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """Production already holds V1 imports, which kept no report. V1 accepted
    only the exact 30-column layout, so those fields — and no AEF field —
    were present."""

    _login(client, "dev-admin")
    _, response = _upload_and_validate(client, integration_engine, _valid_workbook(tmp_path))
    import_id = response.json()["import_id"]
    with integration_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE platform.transelec_import SET schema_contract_version = "
                "'transelec-resumen-v1', mapping_report = NULL, warning_count = 0"
            )
        )
    client.post(
        f"/transelec/imports/{import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )

    active = client.get("/transelec/imports/active").json()
    assert active["source_fields"] == [name for _, name in RESUMEN_COLUMNS]
    assert client.get("/transelec/aef").json()["source_fields"] == []
    assert client.get(f"/transelec/imports/{import_id}/report").json()["mapping_report"] is None


def test_publishing_an_import_with_warnings_requires_an_explicit_acknowledgement(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    """The dashboard's checkbox is a convenience; the API is the control."""

    _login(client, "dev-admin")
    _, response = _upload_and_validate(client, integration_engine, _aef_workbook(tmp_path))
    import_id = response.json()["import_id"]
    assert response.json()["warning_count"] == 1

    refused = client.post(
        f"/transelec/imports/{import_id}/publish", headers={"Origin": _SAME_ORIGIN}
    )
    assert refused.status_code == 409
    assert _active_import_id(integration_engine) is None

    accepted = client.post(
        f"/transelec/imports/{import_id}/publish",
        params={"acknowledge_warnings": "true"},
        headers={"Origin": _SAME_ORIGIN},
    )
    assert accepted.status_code == 200, accepted.text
    assert _active_import_id(integration_engine) == import_id

    with integration_engine.connect() as connection:
        metadata = connection.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'import.published' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()
    assert (metadata["warning_count"], metadata["warnings_acknowledged"]) == (1, True)
