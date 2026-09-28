"""Transelec workbook inspection, reusing the xlsx source contract.

Intake inspection reports evidence; it does not gate upload on business
schema perfection. A contract mismatch is captured, never raised. The
authoritative review happens at validate-and-project, which returns the full
layout report; this only records counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from python_calamine import CalamineWorkbook

from transelec_ingestion.xlsx_contract import (
    TranselecWorkbookError,
    load_transelec_workbook,
)


@dataclass(frozen=True, slots=True)
class TranselecInspectionResult:
    """Safety-checked evidence about an uploaded Transelec workbook."""

    sheet_names: tuple[str, ...]
    resumen_row_count: int | None
    contract_error: str | None
    layout_warning_count: int | None = None


def inspect_transelec_workbook(path: Path) -> TranselecInspectionResult:
    """Report sheet names and existing-contract validation evidence."""

    with CalamineWorkbook.from_path(str(path)) as workbook:
        sheet_names = tuple(workbook.sheet_names)

    resumen_row_count: int | None = None
    contract_error: str | None = None
    layout_warning_count: int | None = None

    try:
        parsed = load_transelec_workbook(path)
    except TranselecWorkbookError as exc:
        contract_error = str(exc)
    else:
        resumen_row_count = len(parsed.resumen_rows)
        layout_warning_count = parsed.layout.count("warning")

    return TranselecInspectionResult(
        sheet_names=sheet_names,
        resumen_row_count=resumen_row_count,
        contract_error=contract_error,
        layout_warning_count=layout_warning_count,
    )
