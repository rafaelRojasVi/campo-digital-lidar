"""Print the structural layout report of a Transelec workbook, privately.

Usage (from the repository root):

    uv run python .claude/skills/transelec-workbook/inspect_workbook.py \
        <path/to/workbook.xlsx> --out <scratchpad>/layout-report.json

Runs the importer's own recognizer (`transelec_ingestion.resumen_layout`),
the same code the upload endpoint uses, without a database, an upload or a
publication. The terminal shows only structure: sheet names, header row,
column letters, field bindings, issue codes, row numbers and counts. The
full JSON report goes to --out, which must be outside the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from python_calamine import CalamineWorkbook

from transelec_ingestion.resumen_layout import (
    find_resumen_sheet,
    resolve_resumen_layout,
    scan_formula_cells,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workbook", type=Path)
    parser.add_argument(
        "--out", type=Path, required=True, help="JSON report path, outside the repo"
    )
    args = parser.parse_args()

    out = args.out.resolve()
    if out.is_relative_to(REPO_ROOT):
        print(f"refusing to write inside the repository: {out}", file=sys.stderr)
        return 2

    with CalamineWorkbook.from_path(str(args.workbook)) as workbook:
        sheet_names = tuple(workbook.sheet_names)
        sheet, issue = find_resumen_sheet(sheet_names)
        print(f"sheets: {len(sheet_names)}; Resumen sheet: {sheet!r}")
        if sheet is None:
            print(f"BLOCKED: {issue.code if issue else 'no Resumen sheet'}")
            return 1
        grid = workbook.get_sheet_by_name(sheet).to_python(skip_empty_area=False)

    resolution = resolve_resumen_layout(
        grid, formula_cells=scan_formula_cells(args.workbook, sheet)
    )
    report = resolution.report
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    header_row = None if report.header_row is None else report.header_row + 1
    print(f"parser: {report.parser_version}; header row (worksheet): {header_row}")
    distinct_pmf = len({row.values.get("pmf") for row in resolution.rows})
    print(f"business rows: {report.business_rows}; distinct PMF: {distinct_pmf}")
    print("field                    tier      column  filled rows")
    for field in report.fields:
        print(f"  {field.field:22s} {field.tier:9s} {field.column or '—':7s} {field.filled_rows}")
    statuses = Counter(decision.status for decision in report.columns)
    print(f"column decisions: {dict(statuses)}")
    for region in report.auxiliary_regions:
        print(
            f"auxiliary region {region.first_column}-{region.last_column} "
            f"({region.column_count} cols)"
        )
    print(
        f"issues: {report.count('error')} error, {report.count('warning')} warning, "
        f"{report.count('info')} info"
    )
    for issue in report.issues:
        rows = f" rows={issue.row_count}" if issue.row_count else ""
        cols = f" cols={','.join(issue.columns)}" if issue.columns else ""
        print(f"  [{issue.severity}] {issue.code}{cols}{rows}")
    print(f"full report: {out}")
    return 1 if report.has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
