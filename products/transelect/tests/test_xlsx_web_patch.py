"""The «web» planilla patcher (spec §5): only the touched parts change."""

from __future__ import annotations

import datetime as dt
import re
import zipfile
from pathlib import Path

import pytest
import xlsxwriter

from transelec_ingestion.resumen_layout import column_letter
from transelec_ingestion.xlsx_contract import EXPECTED_RESUMEN_HEADERS, load_transelec_workbook
from transelec_ingestion.xlsx_web_patch import (
    CellEdit,
    WorkbookPatchError,
    column_index,
    excel_serial,
    patch_workbook,
)

PIVOT = "xl/pivotCache/pivotCacheDefinition1.xml"


def _small_workbook(path: Path, *, with_note: bool) -> None:
    """Resumen: A=Estado (text), B=Reingreso (number), C=Fecha (date), D=formula.
    Row 3 has only A filled, so B..E are absent cells. A second sheet must
    come through untouched."""

    workbook = xlsxwriter.Workbook(path)
    sheet = workbook.add_worksheet("Resumen")
    other = workbook.add_worksheet("Otra")
    date_format = workbook.add_format({"num_format": "dd-mm-yyyy"})
    for column, header in enumerate(["Estado", "Reingreso", "Fecha", "ID", "N Ingreso"]):
        sheet.write(0, column, header)
    sheet.write_string(1, 0, "Rechazado")
    sheet.write_number(1, 1, 1)
    sheet.write_datetime(1, 2, dt.datetime(2026, 1, 5), date_format)
    sheet.write_formula(1, 3, '="X-"&A2', None, "X-Rechazado")
    sheet.write_string(2, 0, "En tramite")
    other.write(0, 0, "intacta")
    if with_note:
        sheet.write_comment(1, 0, "nota previa")
    workbook.close()


def _add_part(path: Path, name: str, data: bytes) -> None:
    rebuilt = path.with_suffix(".rebuilt")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info.filename))
        dst.writestr(name, data)
    rebuilt.replace(path)


def _strip_full_calc_on_load(path: Path) -> None:
    """xlsxwriter always writes ``fullCalcOnLoad="1"``; remove it so a test
    can prove the patcher is what sets it."""

    rebuilt = path.with_suffix(".rebuilt")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "xl/workbook.xml":
                data = data.replace(b' fullCalcOnLoad="1"', b"")
            dst.writestr(info, data)
    rebuilt.replace(path)


def _parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


EDITS = [
    CellEdit(2, "A", "text", "Aprobado", "web · Ana · 04-10-2026 · antes: Rechazado"),
    CellEdit(2, "B", "text", "2", "web · Ana · 04-10-2026 · antes: 1"),
    CellEdit(2, "C", "date", dt.date(2026, 2, 1), "web · Ana · 04-10-2026 · antes: 05-01-2026"),
    CellEdit(2, "D", "text", "Z", "web · Ana · 04-10-2026 · antes: X-Rechazado"),
    CellEdit(3, "E", "text", "ING <1> & 2", "web · Ana · 04-10-2026 · antes: (vacía)"),
    CellEdit(3, "C", "date", None, "web · Ana · 04-10-2026 · antes: (vacía)"),
]


@pytest.fixture(params=[False, True], ids=["no-notes", "existing-note"])
def source(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    path = tmp_path / "source.xlsx"
    _small_workbook(path, with_note=request.param)
    _add_part(
        path,
        PIVOT,
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        b'<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        b' recordCount="1"/>',
    )
    _strip_full_calc_on_load(path)
    return path


def test_untouched_parts_are_byte_identical_and_in_order(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    result = patch_workbook(source, out, sheet_name="Resumen", edits=EDITS)

    before, after = _parts(source), _parts(out)
    for name, data in before.items():
        if name not in result.touched_parts:
            assert after[name] == data, name
    assert [n for n in after if n in before] == list(before)
    assert "xl/worksheets/sheet2.xml" not in result.touched_parts


def test_formula_cells_are_skipped_and_reported(source: Path, tmp_path: Path) -> None:
    result = patch_workbook(source, tmp_path / "out.xlsx", sheet_name="Resumen", edits=EDITS)
    assert [(s.row, s.column, s.reason) for s in result.skipped] == [(2, "D", "formula_cell")]
    assert len(result.written) == 5


def test_cells_are_written_with_the_right_types(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    patch_workbook(source, out, sheet_name="Resumen", edits=EDITS)
    sheet = _parts(out)["xl/worksheets/sheet1.xml"].decode("utf-8")

    assert re.search(
        r'<c r="A2" s="\d+" t="inlineStr"><is><t xml:space="preserve">Aprobado</t>', sheet
    )
    assert re.search(r'<c r="B2" s="\d+"><v>2</v></c>', sheet)  # stays numeric
    assert re.search(
        rf'<c r="C2" s="\d+"><v>{excel_serial(dt.date(2026, 2, 1), date1904=False)}</v>', sheet
    )
    assert "ING &lt;1&gt; &amp; 2" in sheet  # escaped
    assert re.search(r'<c r="C3" s="\d+"/>', sheet)  # cleared, styled
    assert sheet.index('r="C3"') < sheet.index('r="E3"')  # inserted in column order
    assert '<f>"X-"&amp;A2</f>' in sheet  # formula untouched


def test_marks_fill_note_and_on_open_flags(source: Path, tmp_path: Path) -> None:
    assert "fullCalcOnLoad" not in _parts(source)["xl/workbook.xml"].decode("utf-8")
    assert "refreshOnLoad" not in _parts(source)[PIVOT].decode("utf-8")

    out = tmp_path / "out.xlsx"
    patch_workbook(source, out, sheet_name="Resumen", edits=EDITS)
    parts = _parts(out)

    assert 'rgb="FFFFF2CC"' in parts["xl/styles.xml"].decode("utf-8")
    comments = parts["xl/comments1.xml"].decode("utf-8")
    assert "<author>web</author>" in comments
    assert "web · Ana · 04-10-2026 · antes: Rechazado" in comments
    assert comments.count("<comment ") == 5
    assert 'fullCalcOnLoad="1"' in parts["xl/workbook.xml"].decode("utf-8")
    assert 'refreshOnLoad="1"' in parts[PIVOT].decode("utf-8")
    assert "<legacyDrawing" in parts["xl/worksheets/sheet1.xml"].decode("utf-8")
    assert 'Extension="vml"' in parts["[Content_Types].xml"].decode("utf-8")


def test_refuses_an_edited_worksheet_larger_than_the_limit(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    with pytest.raises(WorkbookPatchError, match="larger than"):
        patch_workbook(source, out, sheet_name="Resumen", edits=EDITS, max_edited_part_bytes=100)
    assert not out.exists()


def test_an_existing_note_is_kept_and_extended(tmp_path: Path) -> None:
    path = tmp_path / "note.xlsx"
    _small_workbook(path, with_note=True)
    out = tmp_path / "out.xlsx"
    patch_workbook(path, out, sheet_name="Resumen", edits=EDITS[:1])
    comments = _parts(out)["xl/comments1.xml"].decode("utf-8")
    note = re.search(r'<comment ref="A2".*?</comment>', comments, re.S)
    assert note is not None
    assert "nota previa" in note.group(0) and "web · Ana" in note.group(0)


def test_the_importer_reads_the_web_values_back(tmp_path: Path) -> None:
    path = tmp_path / "planilla.xlsx"
    workbook = xlsxwriter.Workbook(path)
    sheet = workbook.add_worksheet("Resumen")
    for column, header in enumerate(EXPECTED_RESUMEN_HEADERS):
        sheet.write(0, column, header)
    values = {
        "PMF": "MP001",
        "Rol": "101",
        "N Predio": "1",
        "Estado": "En evaluacion",
        "Estado resumido": "En tramite",
        "N Ingreso": "ING-1",
        "Tipo de propietario": "Empresa Forestal",
        "Empresa": "Forestal Sur",
        "Superficie de corta": 1.0,
    }
    for column, header in enumerate(EXPECTED_RESUMEN_HEADERS):
        if header in values:
            sheet.write(1, column, values[header])
    workbook.close()
    letter = {header: index for index, header in enumerate(EXPECTED_RESUMEN_HEADERS)}

    def col(header: str) -> str:
        return column_letter(letter[header])

    out = tmp_path / "web.xlsx"
    patch_workbook(
        path,
        out,
        sheet_name="Resumen",
        edits=[
            CellEdit(2, col("Estado resumido"), "text", "Aprobado", "web"),
            CellEdit(2, col("Fecha de ingreso"), "date", dt.date(2026, 3, 12), "web"),
            CellEdit(2, col("Tipo de rechazo"), "text", "Legal", "web"),
        ],
    )
    row = load_transelec_workbook(out).resumen_rows[0]
    assert row.values["estado_resumido"] == "Aprobado"
    assert row.values["tipo_rechazo"] == "Legal"
    assert row.values["fecha_ingreso"] == dt.date(2026, 3, 12)


def test_refuses_unknown_sheet_missing_row_and_duplicate_cells(
    source: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.xlsx"
    with pytest.raises(WorkbookPatchError):
        patch_workbook(source, out, sheet_name="Nope", edits=EDITS)
    with pytest.raises(WorkbookPatchError):
        patch_workbook(
            source, out, sheet_name="Resumen", edits=[CellEdit(99, "A", "text", "x", "n")]
        )
    with pytest.raises(WorkbookPatchError):
        patch_workbook(source, out, sheet_name="Resumen", edits=[EDITS[0], EDITS[0]])


def test_helpers() -> None:
    assert column_index("A") == 0 and column_index("AB") == 27
    assert excel_serial(dt.date(2026, 1, 5), date1904=False) == 46027
    assert excel_serial(dt.date(1904, 1, 2), date1904=True) == 1
