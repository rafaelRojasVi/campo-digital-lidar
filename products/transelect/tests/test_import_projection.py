"""Step B pure logic: hard-gate contract validation and row projection.

Every fixture workbook here is synthetic, built by this test module for this
test suite. The real Transelec workbook is never read, committed, or
referenced — and, deliberately, no fixture reproduces the reviewed 14-Aug
snapshot's 729/159/272 counts, so a structural gate that silently assumed
them would fail these tests.

Database-backed behavior (transaction rollback, idempotency, invariant
verification against persisted rows) lives in
``apps/api/integration_tests/test_transelec_import_projection.py``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
import xlsxwriter

from transelec_ingestion.import_projection import (
    PARSER_VERSION,
    RESUMEN_ROW_PROJECTION,
    SCHEMA_CONTRACT_VERSION,
    read_validated_workbook,
    resolve_predio_group_key,
    validate_and_project,
)
from transelec_ingestion.xlsx_contract import (
    CURRENT_RESUMEN_COLUMNS,
    EXPECTED_RESUMEN_HEADERS,
    RESUMEN_COLUMNS,
    TranselecWorkbookError,
)


def _source_row(**overrides: Any) -> list[Any]:
    values: dict[str, Any] = {field_name: None for _, field_name in RESUMEN_COLUMNS}
    values.update(
        {
            "pmf": "MP001",
            "rol": "123-45",
            "numero_predio": "7",
            "estado": "En revision",
            "estado_resumido": "En tramite",
            "id_predio_unico": "MP001-123-45-7",
            "carpeta_source": "Carpeta fuente",
            "carpeta_normalizada": "Maullin",
            "superficie_corta": 1.25,
        }
    )
    values.update(overrides)
    return [values[field_name] for _, field_name in RESUMEN_COLUMNS]


def _write_workbook(
    path: Path,
    *,
    headers: tuple[str, ...] = EXPECTED_RESUMEN_HEADERS,
    rows: list[list[Any]] | None = None,
    sheet_name: str = "Resumen",
) -> Path:
    workbook = xlsxwriter.Workbook(path)
    worksheet = workbook.add_worksheet(sheet_name)
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})

    for column, header in enumerate(headers):
        worksheet.write(0, column, header)

    for row_index, row in enumerate(rows or [], start=1):
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


class _ForbiddenConnection:
    """A connection that fails the test if any statement is executed at all."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.statements.append(statement)
        raise AssertionError("Step B touched the database before the contract gate passed.")


# --------------------------------------------------------------------------
# Contract gate: a blocking issue raises and nothing is written
# --------------------------------------------------------------------------


def test_renamed_required_column_is_rejected(tmp_path: Path) -> None:
    headers = list(EXPECTED_RESUMEN_HEADERS)
    headers[7] = "Estado resumido nuevo"
    path = _write_workbook(tmp_path / "renamed.xlsx", headers=tuple(headers), rows=[_source_row()])

    with pytest.raises(
        TranselecWorkbookError, match="columna_esencial_ausente field=estado_resumido"
    ) as caught:
        read_validated_workbook(path)

    assert caught.value.report is not None
    assert any(
        issue.code == "columna_no_reconocida" and issue.columns == ("H",)
        for issue in caught.value.report.issues
    )


def test_reordered_columns_are_mapped_by_header(tmp_path: Path) -> None:
    """Contract V2 binds by recognized header, so swapping two columns moves
    the values with their headers instead of rejecting the workbook."""

    headers = list(EXPECTED_RESUMEN_HEADERS)
    headers[14], headers[15] = headers[15], headers[14]
    row = _source_row(rol="ROL-9", numero_predio="PRED-4")
    row[14], row[15] = row[15], row[14]
    path = _write_workbook(tmp_path / "reordered.xlsx", headers=tuple(headers), rows=[row])

    validated = read_validated_workbook(path)

    assert validated.rows[0].columns["rol"] == "ROL-9"
    assert validated.rows[0].columns["numero_predio"] == "PRED-4"


def test_unlabeled_data_beside_the_table_is_ignored_with_a_warning(tmp_path: Path) -> None:
    row = _source_row()
    row.append("no deberia estar aqui")
    path = _write_workbook(
        tmp_path / "separator.xlsx",
        headers=EXPECTED_RESUMEN_HEADERS + ("",),
        rows=[row],
    )

    validated = read_validated_workbook(path)

    issues = [
        issue for issue in validated.mapping_report["issues"] if issue["severity"] == "warning"
    ]
    assert [(issue["code"], issue["columns"], issue["rows"]) for issue in issues] == [
        ("columna_sin_encabezado", ["AE"], [2])
    ]
    assert "no deberia estar aqui" not in validated.rows[0].columns.values()


def test_worksheet_without_any_pmf_row_is_rejected(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "no-business-rows.xlsx", rows=[_source_row(pmf=None)])

    with pytest.raises(TranselecWorkbookError, match="sin_filas_con_pmf"):
        read_validated_workbook(path)


def test_missing_resumen_worksheet_is_rejected(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "wrong-sheet.xlsx", sheet_name="Otro", rows=[_source_row()])

    with pytest.raises(TranselecWorkbookError, match="hoja_resumen_ausente"):
        read_validated_workbook(path)


def test_contract_violation_never_touches_the_database(tmp_path: Path) -> None:
    """The hard gate runs before any statement is issued, so a rejected
    workbook cannot leave a partial write behind even in principle."""

    headers = list(EXPECTED_RESUMEN_HEADERS)
    headers[3] = "PMF renombrado"
    path = _write_workbook(tmp_path / "gate.xlsx", headers=tuple(headers), rows=[_source_row()])
    connection = _ForbiddenConnection()

    with pytest.raises(TranselecWorkbookError):
        validate_and_project(
            connection,  # type: ignore[arg-type]
            workbook_path=path,
            source_snapshot_id=1,
            ingestion_run_id=1,
            validated_by_app_user_id=1,
        )

    assert connection.statements == []


# --------------------------------------------------------------------------
# Positional projection of all 30 A:AD fields
# --------------------------------------------------------------------------


def test_projection_covers_every_contract_field() -> None:
    """The 30 legacy fields plus the five AEF tracking fields, in the
    resolver's registry order."""

    assert len(RESUMEN_ROW_PROJECTION) == 35
    assert tuple(spec.contract_field for spec in RESUMEN_ROW_PROJECTION) == tuple(
        field_name for _, field_name in CURRENT_RESUMEN_COLUMNS
    )
    assert {field_name for _, field_name in RESUMEN_COLUMNS} <= {
        spec.contract_field for spec in RESUMEN_ROW_PROJECTION
    }


def test_all_thirty_fields_are_projected_positionally(tmp_path: Path) -> None:
    """Values are read by position, never by header text — proven by giving
    the two identically-named ``Carpeta`` columns different values and
    asserting each lands in its own destination column."""

    row = _source_row(
        predio_ref="PR-1",
        rol_ref="RR-1",
        area_ref="AR-1",
        pmf="MP001",
        carpeta_source="COLUMNA-E",
        pas="PAS-1",
        estado="Estado detallado",
        estado_resumido="En tramite",
        tipo_rechazo="Tecnico",
        reingreso_tec="RT",
        reingreso_legal="RL",
        reingreso_recrep="RR",
        tipo_propietario="Privado",
        id_transelec="IDT-1",
        rol="123-45",
        numero_predio="7",
        numero_area_corta="AC-1",
        superficie_corta=1.5,
        superficie_total_corta=3.25,
        fecha_ingreso=dt.date(2026, 5, 4),
        numero_ingreso="NI-1",
        fecha_90_dias=dt.date(2026, 8, 2),
        hoy="texto libre",
        empresa="Empresa X",
        id_predio_unico_ii="IDPU2-1",
        id_pmf="IDPMF-1",
        id_predio_unico="MP001-123-45-7",
        tramite="Tramite-1",
        carpeta_normalizada="COLUMNA-AC",
        sector="Sector Sur",
    )
    path = _write_workbook(tmp_path / "positional.xlsx", rows=[row])

    projected = read_validated_workbook(path).rows[0].columns

    assert projected["predio_ref"] == "PR-1"
    assert projected["rol_ref"] == "RR-1"
    assert projected["area_ref"] == "AR-1"
    assert projected["pmf"] == "MP001"
    assert projected["carpeta_source"] == "COLUMNA-E"
    assert projected["carpeta_normalizada"] == "COLUMNA-AC"
    assert projected["pas"] == "PAS-1"
    assert projected["estado"] == "Estado detallado"
    assert projected["estado_resumido"] == "En tramite"
    assert projected["tipo_rechazo"] == "Tecnico"
    assert projected["reingreso_tec"] == "RT"
    assert projected["reingreso_legal"] == "RL"
    assert projected["reingreso_recrep"] == "RR"
    assert projected["tipo_propietario"] == "Privado"
    assert projected["id_transelec"] == "IDT-1"
    assert projected["rol"] == "123-45"
    assert projected["numero_predio"] == "7"
    assert projected["numero_area_corta"] == "AC-1"
    assert projected["superficie_corta"] == 1.5
    assert projected["superficie_total_corta"] == 3.25
    assert projected["fecha_ingreso"] == dt.date(2026, 5, 4)
    assert projected["numero_ingreso"] == "NI-1"
    assert projected["fecha_90_dias"] == dt.date(2026, 8, 2)
    assert projected["hoy_raw"] == "texto libre"
    assert projected["empresa"] == "Empresa X"
    assert projected["id_predio_unico_ii"] == "IDPU2-1"
    assert projected["id_pmf"] == "IDPMF-1"
    assert projected["id_predio_unico"] == "MP001-123-45-7"
    assert projected["tramite"] == "Tramite-1"
    assert projected["sector"] == "Sector Sur"


def test_source_row_number_is_the_real_worksheet_row(tmp_path: Path) -> None:
    path = _write_workbook(
        tmp_path / "rownumbers.xlsx",
        rows=[_source_row(), _source_row(pmf=None), _source_row(pmf="MP002")],
    )

    validated = read_validated_workbook(path)

    assert [row.source_row_number for row in validated.rows] == [2, 4]


def test_blank_cells_project_as_null_not_empty_string(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "blanks.xlsx", rows=[_source_row(sector="   ", empresa=None)])

    projected = read_validated_workbook(path).rows[0].columns

    assert projected["sector"] is None
    assert projected["empresa"] is None


def test_integral_numeric_cells_render_without_a_spurious_decimal(tmp_path: Path) -> None:
    """Excel stores every number as a double, so an integer identifier comes
    back as 123.0; projecting it as "123.0" would corrupt predio_group_key."""

    path = _write_workbook(
        tmp_path / "numeric-text.xlsx",
        rows=[_source_row(rol=123, numero_predio=7, id_predio_unico=None)],
    )

    projected = read_validated_workbook(path).rows[0].columns

    assert projected["rol"] == "123"
    assert projected["numero_predio"] == "7"
    assert projected["predio_group_key"] == "MP001-123-7"


def test_non_numeric_surface_projects_as_null_and_is_excluded_from_the_total(
    tmp_path: Path,
) -> None:
    path = _write_workbook(
        tmp_path / "surface.xlsx",
        rows=[_source_row(superficie_corta="sin dato"), _source_row(superficie_corta=2.5)],
    )

    validated = read_validated_workbook(path)

    assert validated.rows[0].columns["superficie_corta"] is None
    assert validated.surface_total == pytest.approx(2.5)


def test_hoy_is_preserved_as_raw_text_when_the_source_holds_a_date(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "hoy.xlsx", rows=[_source_row(hoy=dt.date(2026, 5, 4))])

    assert read_validated_workbook(path).rows[0].columns["hoy_raw"] == "2026-05-04"


# --------------------------------------------------------------------------
# predio_group_key
# --------------------------------------------------------------------------


def test_predio_group_key_uses_id_predio_unico_when_present() -> None:
    assert (
        resolve_predio_group_key(
            id_predio_unico="MP001-123-45-7",
            pmf="MP001",
            rol="999",
            numero_predio="1",
        )
        == "MP001-123-45-7"
    )


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_predio_group_key_falls_back_to_the_composite_when_blank(blank: str | None) -> None:
    assert (
        resolve_predio_group_key(
            id_predio_unico=blank,
            pmf="MP001",
            rol="123-45",
            numero_predio="7",
        )
        == "MP001-123-45-7"
    )


def test_predio_group_key_is_never_blank_even_without_rol_or_numero_predio() -> None:
    """PMF is guaranteed non-blank by the contract, so the fallback always
    yields a non-empty key — the column is NOT NULL with no default."""

    key = resolve_predio_group_key(
        id_predio_unico=None,
        pmf="MP001",
        rol=None,
        numero_predio=None,
    )

    assert key.strip() != ""
    assert key == "MP001--"


def test_every_projected_row_has_a_non_blank_predio_group_key(tmp_path: Path) -> None:
    path = _write_workbook(
        tmp_path / "keys.xlsx",
        rows=[
            _source_row(id_predio_unico=None, rol=None, numero_predio=None),
            _source_row(id_predio_unico="   ", pmf="MP002", rol="9", numero_predio="1"),
            _source_row(id_predio_unico="MP003-1-1", pmf="MP003"),
        ],
    )

    validated = read_validated_workbook(path)

    keys = [row.columns["predio_group_key"] for row in validated.rows]
    assert all(isinstance(key, str) and key.strip() for key in keys)
    assert keys == ["MP001--", "MP002-9-1", "MP003-1-1"]


def test_predio_group_key_never_overwrites_the_raw_id_predio_unico(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "raw-id.xlsx", rows=[_source_row(id_predio_unico=None)])

    projected = read_validated_workbook(path).rows[0].columns

    assert projected["id_predio_unico"] is None
    assert projected["predio_group_key"] == "MP001-123-45-7"


# --------------------------------------------------------------------------
# Structural aggregates: computed from the rows, never assumed
# --------------------------------------------------------------------------


def test_aggregates_are_derived_from_the_projected_rows(tmp_path: Path) -> None:
    """A workbook with counts nothing like the reviewed 729/159/272 snapshot
    must validate and report its own numbers."""

    path = _write_workbook(
        tmp_path / "aggregates.xlsx",
        rows=[
            _source_row(pmf="MP001", id_predio_unico="A", superficie_corta=1.0),
            _source_row(pmf="MP001", id_predio_unico="A", superficie_corta=2.0),
            _source_row(pmf="MP002", id_predio_unico="B", superficie_corta=0.5),
            _source_row(pmf="MP003", id_predio_unico=None, superficie_corta=None),
            _source_row(pmf=None),
        ],
    )

    validated = read_validated_workbook(path)

    assert validated.business_rows == 4
    assert validated.distinct_pmf == 3
    assert validated.distinct_provisional_predio_ids == 2
    assert validated.surface_total == pytest.approx(3.5)


def test_a_single_row_workbook_is_structurally_valid(tmp_path: Path) -> None:
    path = _write_workbook(tmp_path / "single.xlsx", rows=[_source_row()])

    validated = read_validated_workbook(path)

    assert validated.business_rows == 1
    assert validated.distinct_pmf == 1


def test_contract_and_parser_versions_are_stable_identifiers() -> None:
    assert SCHEMA_CONTRACT_VERSION == "transelec-resumen-v2"
    assert PARSER_VERSION.startswith("transelec_ingestion.resumen_layout@")
