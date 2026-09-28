# ruff: noqa: E501 - hand-rolled OOXML fixture XML has long attribute lines
"""Transelec workbook inspector: reuses the existing xlsx source contract."""

from __future__ import annotations

import zipfile
from pathlib import Path

from app.inspection.transelec_inspector import inspect_transelec_workbook

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

_WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Resumen" sheetId="1" r:id="rId1"/>
    <sheet name="Pendientes" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>
"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>
"""

_SHEET1_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>not</t></is></c>
      <c r="B1" t="inlineStr"><is><t>the</t></is></c>
      <c r="C1" t="inlineStr"><is><t>real</t></is></c>
      <c r="D1" t="inlineStr"><is><t>contract</t></is></c>
      <c r="E1" t="inlineStr"><is><t>headers</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""

_SHEET2_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData/>
</worksheet>
"""


def _make_minimal_workbook(path: Path) -> Path:
    """Build a minimal, dependency-free OOXML workbook for tests.

    Deliberately hand-rolled instead of adding openpyxl as a dependency:
    the application only ever reads xlsx via python_calamine (already a
    dependency), and this fixture only needs to be readable, not
    round-trippable.
    """

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", _WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", _SHEET1_XML)
        archive.writestr("xl/worksheets/sheet2.xml", _SHEET2_XML)
    return path


def test_reports_sheet_names(tmp_path: Path) -> None:
    workbook_path = _make_minimal_workbook(tmp_path / "wb.xlsx")
    result = inspect_transelec_workbook(workbook_path)
    assert "Resumen" in result.sheet_names
    assert "Pendientes" in result.sheet_names


def test_contract_mismatch_is_reported_not_raised(tmp_path: Path) -> None:
    workbook_path = _make_minimal_workbook(tmp_path / "wb2.xlsx")
    result = inspect_transelec_workbook(workbook_path)
    assert result.contract_error is not None
    assert result.resumen_row_count is None
