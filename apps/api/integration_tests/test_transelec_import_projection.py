"""Step B against real PostgreSQL: commit, idempotency, rollback, no activation.

Every workbook here is synthetic and built by this module. None reproduces
the reviewed 14-Aug snapshot's 729/159/272 counts.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import xlsxwriter
from sqlalchemy import Engine, text

from transelec_ingestion import import_projection
from transelec_ingestion.import_projection import (
    ImportInvariantError,
    validate_and_project,
)
from transelec_ingestion.xlsx_contract import (
    EXPECTED_RESUMEN_HEADERS,
    RESUMEN_COLUMNS,
    TranselecWorkbookError,
)

TRANSELEC_PRODUCT_KEY = "transelect"


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


def _write_workbook(path: Path, rows: list[list[Any]]) -> Path:
    workbook = xlsxwriter.Workbook(path)
    worksheet = workbook.add_worksheet("Resumen")
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})

    for column, header in enumerate(EXPECTED_RESUMEN_HEADERS):
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
    return path


def _default_workbook(tmp_path: Path) -> Path:
    """Three business rows, two PMFs, two provisional predio ids."""

    return _write_workbook(
        tmp_path / "resumen.xlsx",
        [
            _source_row(fecha_ingreso=dt.date(2026, 5, 4), superficie_corta=1.5),
            _source_row(id_predio_unico=None, superficie_corta=0.5),
            _source_row(pmf="MP002", id_predio_unico="MP002-9-1", superficie_corta=2.0),
            _source_row(pmf=None),
        ],
    )


@pytest.fixture
def fixture_ids(integration_engine: Engine) -> Generator[dict[str, int], None, None]:
    """Create committed app_user / source_snapshot / ingestion_run rows."""

    sha = hashlib.sha256(b"transelec-import-projection-fixture").hexdigest()

    with integration_engine.begin() as connection:
        app_user_id = connection.execute(
            text(
                """
                INSERT INTO platform.app_user (identity_kind, identity_key, display_name)
                VALUES ('dev-local', 'projection-fixture-user', 'Projection Fixture')
                RETURNING id
                """
            )
        ).scalar_one()
        system_id = connection.execute(
            text(
                "INSERT INTO platform.source_system (system_key) "
                "VALUES ('projection_fixture') RETURNING id"
            )
        ).scalar_one()
        asset_id = connection.execute(
            text(
                """
                INSERT INTO platform.source_asset (source_system_id, identity_kind, identity_key)
                VALUES (:system_id, 'content_sha256', :sha)
                RETURNING id
                """
            ),
            {"system_id": system_id, "sha": sha},
        ).scalar_one()
        snapshot_id = connection.execute(
            text(
                """
                INSERT INTO platform.source_snapshot (source_asset_id, content_sha256, byte_size)
                VALUES (:asset_id, :sha, 1024)
                RETURNING id
                """
            ),
            {"asset_id": asset_id, "sha": sha},
        ).scalar_one()
        run_id = connection.execute(
            text(
                """
                INSERT INTO platform.ingestion_run
                    (source_snapshot_id, product_key, requested_by_app_user_id)
                VALUES (:snapshot_id, :product_key, :user_id)
                RETURNING id
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "product_key": TRANSELEC_PRODUCT_KEY,
                "user_id": app_user_id,
            },
        ).scalar_one()

    yield {
        "app_user_id": app_user_id,
        "source_snapshot_id": snapshot_id,
        "ingestion_run_id": run_id,
    }

    with integration_engine.begin() as connection:
        connection.execute(
            text("UPDATE platform.transelec_dashboard_state SET active_import_id = NULL")
        )
        for table in (
            "transelec_publish_event",
            "transelec_resumen_row",
            "transelec_import",
            "ingestion_run",
            "source_observation",
            "source_snapshot",
            "source_asset",
            "source_system",
            "audit_event",
            "product_grant",
            "app_user",
        ):
            connection.execute(text(f"DELETE FROM platform.{table}"))


def _project(engine: Engine, fixture_ids: dict[str, int], workbook_path: Path) -> Any:
    with engine.begin() as connection:
        return validate_and_project(
            connection,
            workbook_path=workbook_path,
            source_snapshot_id=fixture_ids["source_snapshot_id"],
            ingestion_run_id=fixture_ids["ingestion_run_id"],
            validated_by_app_user_id=fixture_ids["app_user_id"],
        )


def _counts(engine: Engine) -> tuple[int, int]:
    with engine.connect() as connection:
        imports = connection.execute(
            text("SELECT count(*) FROM platform.transelec_import")
        ).scalar_one()
        rows = connection.execute(
            text("SELECT count(*) FROM platform.transelec_resumen_row")
        ).scalar_one()
    return imports, rows


def _active_import_id(engine: Engine) -> int | None:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT active_import_id FROM platform.transelec_dashboard_state WHERE id = 1")
        ).scalar_one()


# ---------------------------------------------------------------------------
# Committing Step B
# ---------------------------------------------------------------------------


def test_validate_and_project_commits_an_import_and_its_rows(
    integration_engine: Engine, fixture_ids: dict[str, int], tmp_path: Path
) -> None:
    result = _project(integration_engine, fixture_ids, _default_workbook(tmp_path))

    assert result.already_existed is False
    assert result.business_rows == 3
    assert result.distinct_pmf == 2
    assert result.distinct_provisional_predio_ids == 2
    assert result.surface_total == pytest.approx(4.0)
    assert _counts(integration_engine) == (1, 3)


def test_persisted_rows_preserve_positional_identity_and_types(
    integration_engine: Engine, fixture_ids: dict[str, int], tmp_path: Path
) -> None:
    workbook = _write_workbook(
        tmp_path / "typed.xlsx",
        [_source_row(fecha_ingreso=dt.date(2026, 5, 4), hoy="texto libre", rol=123)],
    )
    result = _project(integration_engine, fixture_ids, workbook)

    with integration_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT source_row_number, carpeta_source, carpeta_normalizada, rol,
                       superficie_corta, fecha_ingreso, hoy_raw, predio_group_key
                FROM platform.transelec_resumen_row
                WHERE import_id = :import_id
                """
            ),
            {"import_id": result.import_id},
        ).one()

    assert row.source_row_number == 2
    # The two identically-named "Carpeta" columns stay distinct.
    assert row.carpeta_source == "COLUMNA-E"
    assert row.carpeta_normalizada == "COLUMNA-AC"
    assert row.rol == "123"
    assert row.superficie_corta == pytest.approx(1.25)
    assert row.fecha_ingreso == dt.date(2026, 5, 4)
    assert row.hoy_raw == "texto libre"
    assert row.predio_group_key == "MP001-123-45-7"


def test_every_persisted_row_has_a_non_blank_predio_group_key(
    integration_engine: Engine, fixture_ids: dict[str, int], tmp_path: Path
) -> None:
    result = _project(integration_engine, fixture_ids, _default_workbook(tmp_path))

    with integration_engine.connect() as connection:
        blank = connection.execute(
            text(
                """
                SELECT count(*)
                FROM platform.transelec_resumen_row
                WHERE import_id = :import_id
                  AND (predio_group_key IS NULL OR btrim(predio_group_key) = '')
                """
            ),
            {"import_id": result.import_id},
        ).scalar_one()
        fallback = connection.execute(
            text(
                """
                SELECT predio_group_key
                FROM platform.transelec_resumen_row
                WHERE import_id = :import_id AND id_predio_unico IS NULL
                """
            ),
            {"import_id": result.import_id},
        ).scalar_one()

    assert blank == 0
    assert fallback == "MP001-123-45-7"


def test_step_b_never_activates_the_import_it_commits(
    integration_engine: Engine, fixture_ids: dict[str, int], tmp_path: Path
) -> None:
    """A validated import is not what the dashboard serves until publish."""

    before = _active_import_id(integration_engine)

    _project(integration_engine, fixture_ids, _default_workbook(tmp_path))

    assert before is None
    assert _active_import_id(integration_engine) is None


def test_a_second_projection_of_the_same_snapshot_is_idempotent(
    integration_engine: Engine, fixture_ids: dict[str, int], tmp_path: Path
) -> None:
    workbook = _default_workbook(tmp_path)
    first = _project(integration_engine, fixture_ids, workbook)

    second = _project(integration_engine, fixture_ids, workbook)

    assert second.already_existed is True
    assert second.import_id == first.import_id
    assert _counts(integration_engine) == (1, 3)


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def test_invariant_mismatch_rolls_the_whole_step_b_transaction_back(
    integration_engine: Engine,
    fixture_ids: dict[str, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fault injection at the invariant check: the import row and every
    projected row must disappear, and the active version must be untouched."""

    real = import_projection.read_persisted_aggregates

    def _skewed(connection: Any, *, import_id: int) -> Any:
        aggregates = real(connection, import_id=import_id)
        return type(aggregates)(
            business_rows=aggregates.business_rows + 1,
            distinct_pmf=aggregates.distinct_pmf,
            distinct_provisional_predio_ids=aggregates.distinct_provisional_predio_ids,
            surface_total=aggregates.surface_total,
            blank_predio_group_keys=aggregates.blank_predio_group_keys,
            orphaned_rows=aggregates.orphaned_rows,
        )

    monkeypatch.setattr(import_projection, "read_persisted_aggregates", _skewed)

    active_before = _active_import_id(integration_engine)

    with pytest.raises(ImportInvariantError):
        _project(integration_engine, fixture_ids, _default_workbook(tmp_path))

    assert _counts(integration_engine) == (0, 0)
    assert _active_import_id(integration_engine) == active_before


def test_contract_violation_leaves_no_import_and_no_rows(
    integration_engine: Engine, fixture_ids: dict[str, int], tmp_path: Path
) -> None:
    path = tmp_path / "violating.xlsx"
    workbook = xlsxwriter.Workbook(path)
    worksheet = workbook.add_worksheet("Resumen")
    headers = list(EXPECTED_RESUMEN_HEADERS)
    headers[3] = "PMF renombrado"
    for column, header in enumerate(headers):
        worksheet.write(0, column, header)
    for column, value in enumerate(_source_row()):
        if value is not None:
            worksheet.write(1, column, value)
    workbook.close()

    active_before = _active_import_id(integration_engine)

    with pytest.raises(TranselecWorkbookError):
        _project(integration_engine, fixture_ids, path)

    assert _counts(integration_engine) == (0, 0)
    assert _active_import_id(integration_engine) == active_before
