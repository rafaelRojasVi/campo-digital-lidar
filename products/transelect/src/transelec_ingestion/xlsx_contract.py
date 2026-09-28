"""Load the ``Resumen`` worksheet of a Transelec workbook.

Since contract V2 the layout is *recognized* rather than fixed: see
``transelec_ingestion.resumen_layout`` for header detection, alias mapping,
the explicit two-``Carpeta`` rule and the report of every decision. This
module keeps the loading entry point and its error type, and raises when the
resolution contains a blocking (``error``) issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from python_calamine import CalamineWorkbook

from transelec_ingestion.resumen_layout import (
    AEF_TRACKING_FIELDS,
    FIELD_SPECS,
    LayoutIssue,
    LayoutReport,
    TextDateEvidence,
    find_resumen_sheet,
    resolve_resumen_layout,
    scan_formula_cells,
)


class TranselecWorkbookError(ValueError):
    """Raised when a workbook cannot be imported without review.

    ``report`` carries the full layout report when one could be produced, so
    a caller can show the operator every row/column reference rather than
    only the first problem. Its ``str()`` is structural only: issue codes,
    field names, column letters and row numbers, never a business cell value.
    """

    def __init__(self, message: str, *, report: LayoutReport | None = None) -> None:
        super().__init__(message)
        self.report = report


# The 30-column business table as it stood in the 14-Aug-2026 workbook (then
# at A:AD). Kept as the documented legacy layout; tests use it to prove that
# layout still imports. Header text, not position, binds a column now.
RESUMEN_COLUMNS: tuple[tuple[str, str], ...] = tuple(
    (spec.header, spec.name) for spec in FIELD_SPECS if spec.name not in AEF_TRACKING_FIELDS
)

EXPECTED_RESUMEN_HEADERS = tuple(header for header, _ in RESUMEN_COLUMNS)

# The 09-Sept-2026 layout: the AEF tracking block at A:E, then the 30 fields.
CURRENT_RESUMEN_COLUMNS: tuple[tuple[str, str], ...] = tuple(
    (spec.header, spec.name) for spec in FIELD_SPECS
)


@dataclass(frozen=True, slots=True)
class ResumenSourceRow:
    source_row_number: int
    values: dict[str, Any]
    # Raw text found in date columns and how it was classified; see
    # resumen_layout.classify_text_date.
    text_dates: dict[str, TextDateEvidence] = field(default_factory=dict)

    @property
    def pmf(self) -> str:
        value = self.values["pmf"]
        return str(value).strip()

    @property
    def provisional_predio_id(self) -> str | None:
        value = self.values["id_predio_unico"]
        if value is None:
            return None

        normalized = str(value).strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class TranselecWorkbook:
    source_path: Path
    sheet_names: tuple[str, ...]
    resumen_rows: tuple[ResumenSourceRow, ...]
    layout: LayoutReport


def _describe(issue: LayoutIssue) -> str:
    parts = [issue.code]
    if issue.field:
        parts.append(f"field={issue.field}")
    if issue.columns:
        parts.append(f"columns={','.join(issue.columns)}")
    if issue.rows:
        parts.append(f"rows={','.join(str(row) for row in issue.rows[:10])}")
    return " ".join(parts)


def load_transelec_workbook(path: str | Path) -> TranselecWorkbook:
    """Read and resolve ``Resumen``; raise on any blocking issue."""

    source_path = Path(path)

    if not source_path.is_file():
        raise TranselecWorkbookError(f"Workbook does not exist: {source_path}")

    with CalamineWorkbook.from_path(str(source_path)) as workbook:
        sheet_names = tuple(workbook.sheet_names)
        sheet_name, sheet_issue = find_resumen_sheet(sheet_names)
        if sheet_name is None:
            assert sheet_issue is not None
            raise TranselecWorkbookError(f"Resumen layout: {_describe(sheet_issue)}")
        # skip_empty_area=False keeps the grid absolute: row 0 is worksheet
        # row 1 and column 0 is column A even when leading rows are blank.
        grid = workbook.get_sheet_by_name(sheet_name).to_python(skip_empty_area=False)

    if not grid:
        raise TranselecWorkbookError('Worksheet "Resumen" is empty')

    resolution = resolve_resumen_layout(
        grid, formula_cells=scan_formula_cells(source_path, sheet_name)
    )
    report = resolution.report

    if report.has_errors:
        errors = [issue for issue in report.issues if issue.severity == "error"]
        raise TranselecWorkbookError(
            "Resumen layout: " + "; ".join(_describe(issue) for issue in errors[:5]),
            report=report,
        )

    return TranselecWorkbook(
        source_path=source_path,
        sheet_names=sheet_names,
        resumen_rows=tuple(
            ResumenSourceRow(
                source_row_number=row.source_row_number,
                values=row.values,
                text_dates=row.text_dates,
            )
            for row in resolution.rows
        ),
        layout=report,
    )
