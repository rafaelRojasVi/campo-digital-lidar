from pathlib import Path
from typing import Any

import pytest
import xlsxwriter

from transelec_ingestion.xlsx_contract import (
    EXPECTED_RESUMEN_HEADERS,
    RESUMEN_COLUMNS,
    TranselecWorkbookError,
    load_transelec_workbook,
)


def _source_row(**overrides: Any) -> list[Any]:
    values: dict[str, Any] = {field_name: None for _, field_name in RESUMEN_COLUMNS}

    values.update(
        {
            "pmf": "MP001",
            "carpeta_source": "Expediente fuente",
            "estado": "En revisión",
            "estado_resumido": "En tramite",
            "id_predio_unico": "MP001-123-1",
            "carpeta_normalizada": "Maullin",
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
) -> None:
    workbook = xlsxwriter.Workbook(path)
    worksheet = workbook.add_worksheet(sheet_name)

    for column, header in enumerate(headers):
        worksheet.write(0, column, header)

    for row_index, row in enumerate(rows or [], start=1):
        for column, value in enumerate(row):
            if value is not None:
                worksheet.write(row_index, column, value)

    workbook.close()


def test_loads_business_rows_and_preserves_positional_duplicate_headers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transelec.xlsx"

    _write_workbook(
        path,
        rows=[
            _source_row(
                carpeta_source="Carpeta expediente A",
                carpeta_normalizada="Maullin",
            ),
            _source_row(pmf=None),
            _source_row(
                pmf="MP002",
                id_predio_unico="MP002-456-2",
                carpeta_source="Carpeta expediente B",
                carpeta_normalizada="Ancud",
            ),
        ],
    )

    workbook = load_transelec_workbook(path)

    assert len(workbook.resumen_rows) == 2

    first, second = workbook.resumen_rows

    assert first.source_row_number == 2
    assert second.source_row_number == 4

    assert first.pmf == "MP001"
    assert second.pmf == "MP002"

    assert first.provisional_predio_id == "MP001-123-1"
    assert second.provisional_predio_id == "MP002-456-2"

    assert first.values["carpeta_source"] == "Carpeta expediente A"
    assert first.values["carpeta_normalizada"] == "Maullin"


def test_rejects_workbook_without_resumen_sheet(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transelec.xlsx"

    _write_workbook(
        path,
        sheet_name="Otro",
    )

    with pytest.raises(
        TranselecWorkbookError,
        match="hoja_resumen_ausente",
    ):
        load_transelec_workbook(path)


def test_rejects_renamed_required_column(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transelec.xlsx"

    headers = list(EXPECTED_RESUMEN_HEADERS)
    headers[6] = "Estado nuevo"

    _write_workbook(
        path,
        headers=tuple(headers),
        rows=[_source_row()],
    )

    with pytest.raises(
        TranselecWorkbookError,
        match=r"columna_esencial_ausente field=estado($|;)",
    ):
        load_transelec_workbook(path)


def test_rejects_resumen_without_business_rows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transelec.xlsx"

    _write_workbook(
        path,
        rows=[_source_row(pmf=None)],
    )

    with pytest.raises(
        TranselecWorkbookError,
        match="sin_filas_con_pmf",
    ):
        load_transelec_workbook(path)


def test_rejects_missing_workbook(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        TranselecWorkbookError,
        match="Workbook does not exist",
    ):
        load_transelec_workbook(tmp_path / "missing.xlsx")


def test_warns_about_unlabeled_data_in_the_former_separator_column(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transelec.xlsx"

    row = _source_row()
    row.append("unexpected")

    _write_workbook(
        path,
        headers=EXPECTED_RESUMEN_HEADERS + ("",),
        rows=[row],
    )

    workbook = load_transelec_workbook(path)

    warnings = [issue for issue in workbook.layout.issues if issue.severity == "warning"]
    assert [(issue.code, issue.columns, issue.rows) for issue in warnings] == [
        ("columna_sin_encabezado", ("AE",), (2,))
    ]


def test_ignores_auxiliary_worksheet_content_after_separator(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transelec.xlsx"

    row = _source_row()
    row.extend([None, "helper value"])

    _write_workbook(
        path,
        headers=EXPECTED_RESUMEN_HEADERS + ("", "Auxiliary"),
        rows=[row],
    )

    workbook = load_transelec_workbook(path)

    assert len(workbook.resumen_rows) == 1
    assert workbook.resumen_rows[0].pmf == "MP001"
