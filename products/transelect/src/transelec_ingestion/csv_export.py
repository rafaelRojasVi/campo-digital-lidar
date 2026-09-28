"""TR-FUNC-037's CSV export: field set (TR-OPEN-04) and formula-injection hardening.

**Corrected from an earlier draft of this module.** TR-OPEN-04's field set
was originally a best-effort guess because neither ratified document
enumerated the literal field names. The source forensic audit now records
the exact, ordered field list confirmed by direct read of `exportCSV()` in
both source HTML files (see that document's "Exact field list, confirmed by
direct read" notes under the v0 and Actualizable sections). Actualizable's
order (the more recent, more-used file, and the one whose KPI set this
task already implements) is:

``PMF, Predio Ref, Carpeta, PAS, Estado resumido, Tipo de rechazo, Tipo de
propietario, Rol, N Predio, N Area de Corta, Superficie de corta, Fecha de
ingreso, N Ingreso, Empresa, ID_Predo_Unico, Sector, Observación auxiliar``

``EXPORT_FIELDS_V1`` below reproduces that order with two settled
adjustments (not re-derived here — the corrected audit doc already decided
both):

1. **``Carpeta`` is split into its two distinct source fields**,
   ``carpeta_source`` (the ``Carpeta`` beside ``PMF``) and
   ``carpeta_normalizada`` (the ``Carpeta`` beside ``Tramite``/``Sector``),
   each its own labeled column — Actualizable's single ``Carpeta`` export
   value has *ambiguous* provenance (a JS object-key collision silently
   picks one of the two source columns, and which one was never
   independently confirmed), so exporting both is more faithful than
   guessing which one Javier's export happens to keep. The headers name
   what each field is (``Carpeta PMF`` / ``Carpeta normalizada``, as the
   dashboard labels them), not a column letter: the letters were E/AC in
   the 14-Aug-2026 layout and J/AH in the 09-Sept-2026 one, and contract V2
   binds these fields by header and neighbour, not by position.
2. **``Observación auxiliar`` ships as an always-empty reserved column.**
   The audit confirms this field is sourced from the ``Pendientes`` sheet
   (per the source HTML's own footer text), not from any ``Resumen`` A:AD
   field — populating it would require exactly the auxiliary-sheet
   auto-merge this design's non-goals rule out for V1
   (`docs/superpowers/specs/2026-09-02-transelec-hosted-pilot-v2-design.md`,
   "No automatic merge of historical `Resumen` sheets, `Pendientes`,
   `Reingresos`, or `Urgentes 07May` into current state"). The column is
   kept for structural familiarity with what Javier is used to opening,
   deliberately unmapped to any `transelec_resumen_row` column so it
   always renders blank.

Net result: **18 columns, not a literal 17** — the corrected matrix's
TR-FUNC-037 row documents why. This is still a single named constant, so a
future correction (e.g. Javier confirming a preference between the two
``Carpeta`` columns) is a one-place change.

A date column (``Fecha de ingreso``) exports the date when there is one.
When the source cell held text that was not resolved to a date (several
dates, ``-``, a numeric day/month form), the export writes that raw text
instead of leaving the cell blank, so the export never loses what the
workbook said. The raw text is kept on the row (``source_text_dates``).

CSV formula-injection hardening is a **separate, mandatory, security**
requirement, independent of the field-set question above: any cell value
beginning with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return (the
full OWASP set: a leading tab or CR is stripped by some spreadsheet
importers, exposing a formula behind it) is prefixed with a single quote
before being written, so it can never be interpreted as a live formula by
Excel/LibreOffice/Google Sheets on open ("CSV injection" / "formula
injection"). This is a deliberate, security-motivated divergence from
Javier's raw CSV export (neither HTML file does this), applied uniformly to
every cell regardless of source type — including a legitimate negative
number, which is the accepted, documented trade-off of this class of
mitigation (see OWASP's CSV Injection guidance): a stray ``'`` prefix on a
negative surface value is a much smaller cost than a live formula executing
in a stakeholder's spreadsheet.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Mapping, Sequence
from typing import Any

# Never a real transelec_resumen_row column — .get() always returns None
# for it, so this column always renders blank. See the module docstring's
# "Observación auxiliar" note: it is sourced from the Pendientes sheet,
# which this design's non-goals exclude from any V1 auto-merge.
_OBSERVACION_AUXILIAR_RESERVED_COLUMN = "_observacion_auxiliar_reserved_v1"

# (destination column name, Spanish CSV header) — see the module docstring
# for the rationale behind each inclusion/exclusion/split. Order here is the
# order columns are written in the exported file, matching Actualizable's
# own export order with Carpeta split into its two distinct source fields.
EXPORT_FIELDS_V1: tuple[tuple[str, str], ...] = (
    ("pmf", "PMF"),
    ("predio_ref", "Predio Ref"),
    ("carpeta_source", "Carpeta PMF"),
    ("carpeta_normalizada", "Carpeta normalizada"),
    ("pas", "PAS"),
    ("estado_resumido", "Estado resumido"),
    ("tipo_rechazo", "Tipo de rechazo"),
    ("tipo_propietario", "Tipo de propietario"),
    ("rol", "Rol"),
    ("numero_predio", "N Predio"),
    ("numero_area_corta", "N Area de Corta"),
    ("superficie_corta", "Superficie de corta"),
    ("fecha_ingreso", "Fecha de ingreso"),
    ("numero_ingreso", "N Ingreso"),
    ("empresa", "Empresa"),
    ("id_predio_unico", "ID_Predo_Unico"),
    ("sector", "Sector"),
    (_OBSERVACION_AUXILIAR_RESERVED_COLUMN, "Observación auxiliar"),
)

assert len(EXPORT_FIELDS_V1) == 18  # 17 Actualizable fields, Carpeta split into 2, net +1

_DANGEROUS_LEADING_CHARACTERS = ("=", "+", "-", "@", "\t", "\r")

_CSV_DELIMITER = ";"
_CSV_LINE_TERMINATOR = "\r\n"


def neutralize_formula_injection(value: str) -> str:
    """Prefix ``value`` with ``'`` if it begins with =, +, -, @, tab or CR.

    A leading apostrophe forces spreadsheet software to treat the cell as
    text rather than evaluating it as a formula, without changing the
    visible/copyable content for a human reader inspecting the file in a
    text editor.
    """

    if value and value[0] in _DANGEROUS_LEADING_CHARACTERS:
        return f"'{value}"
    return value


def _render_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        rendered = str(value)
    elif isinstance(value, float):
        rendered = str(int(value)) if value.is_integer() else str(value)
    elif isinstance(value, dt.date | dt.datetime):
        rendered = value.isoformat()
    else:
        rendered = str(value)
    return neutralize_formula_injection(rendered)


def _render_row_cell(row: Mapping[str, Any], column: str) -> str:
    if column == _OBSERVACION_AUXILIAR_RESERVED_COLUMN:
        # Always blank, unconditionally -- never read from `row`, even if a
        # caller's dict happens to carry this exact key. The guarantee is
        # "this column is never populated," not merely "no real
        # transelec_resumen_row column happens to be named this."
        return ""
    value = row.get(column)
    if value is None:
        evidence = (row.get("source_text_dates") or {}).get(column)
        if evidence and evidence.get("parsed") is None:
            return neutralize_formula_injection(str(evidence.get("raw") or ""))
    return _render_cell(value)


def render_transelec_export_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """Render ``rows`` (dicts keyed by destination column name) as export CSV bytes.

    UTF-8 with a BOM and ``;`` delimiter, matching both source HTML files'
    export mechanism, per the source forensic audit. Every cell passes
    through ``neutralize_formula_injection`` — this is the one place the
    hardening is applied, so every caller gets it for free.
    """

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=_CSV_DELIMITER, lineterminator=_CSV_LINE_TERMINATOR)
    writer.writerow(header for _, header in EXPORT_FIELDS_V1)

    for row in rows:
        writer.writerow(_render_row_cell(row, column) for column, _ in EXPORT_FIELDS_V1)

    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
