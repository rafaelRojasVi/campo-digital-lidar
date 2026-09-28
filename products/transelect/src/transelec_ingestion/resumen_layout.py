"""Tolerant, evidence-recording layout resolution for the ``Resumen`` worksheet.

The V1 contract bound business fields to fixed positions A:AD and rejected
any change. The 09-Sept-2026 workbook inserted five columns at A:E (``AEF``,
``Quien solicita``, ``Fecha solicitud``, ``Fecha corta``, ``Fecha termino``),
shifting every V1 field right by five and moving the blank separator from AE
to AJ — a benign change the positional gate could only reject.

This module replaces position with *recognition*, without replacing review
with guessing:

- the header row is detected, not assumed to be row 1;
- a column is bound to a field only when its normalized header equals the
  field's canonical name or one of its documented aliases;
- the two columns both headed ``Carpeta`` are resolved explicitly from their
  recognized neighbours (beside ``PMF`` → source folder; beside
  ``Tramite``/``Sector`` → normalized folder) and are otherwise ambiguous;
- columns are split into blocks by fully blank columns, so the separator may
  move and worksheet-local summary/pivot material to its right is recorded
  as an ignored auxiliary region instead of being parsed;
- every decision is recorded in a :class:`LayoutReport` — which column was
  mapped to which field, what was ignored and why, and every issue with its
  worksheet row and column references.

Issues carry a severity. ``error`` blocks the import (nothing is persisted);
``warning`` imports but must be reviewed before an operator publishes;
``info`` is recorded evidence. No business value is ever inferred: a cell
that is not what its column promises is reported and left empty, never
reinterpreted, and nothing here fills values down or across rows. The one
reading of text is a date column holding a single date written out in Spanish
(``13 de noviembre de 2024``), which is unambiguous; the cell's raw text is
kept beside the parsed date, and every other text in a date column (several
dates, ``-``, numeric day/month forms) is kept as raw text with no date.

AEF tracking values are resolved per PMF (:func:`resolve_pmf_field`) from the
rows that carry them, naming those rows. Two different non-blank values for
one PMF are a conflict reported for review, never a choice.

Messages are Spanish and structural. They may name headers, column letters,
row numbers and counts; they never quote a business cell value.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
import xml.parsers.expat
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, Literal

PARSER_VERSION = "transelec_ingestion.resumen_layout@2"

RESUMEN_SHEET_NAME = "Resumen"

Severity = Literal["info", "warning", "error"]
Tier = Literal["identity", "required", "expected", "optional"]
FieldKind = Literal["text", "number", "date"]
ColumnStatus = Literal[
    "mapped",
    "duplicate_ignored",
    "unrecognized_ignored",
    "unlabeled_data_ignored",
    "separator",
]

# How many leading worksheet rows may hold titles/notes above the header.
HEADER_SCAN_ROWS = 15
# A header row must recognize at least this many distinct fields.
MIN_HEADER_MATCHES = 5
# Row lists inside one issue are capped; the full count is kept separately.
MAX_ROWS_PER_ISSUE = 50
# Headers are schema, not data, but still arbitrary workbook text: bound it.
MAX_HEADER_CHARS = 80

_EXCEL_ERROR_VALUES = frozenset(
    {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"}
)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One business field of the ``Resumen`` table.

    ``header`` is the canonical header text as it appears in the source.
    ``aliases`` are additional accepted headers; each is documented in
    ``products/transelect/docs/source-contract-v2.md``. ``tier`` decides what
    happens when no column carries the field.
    """

    name: str
    header: str
    tier: Tier
    kind: FieldKind
    aliases: tuple[str, ...] = ()


# Registry order is the 09-Sept-2026 source order. It is documentation of the
# observed layout; nothing below depends on position.
FIELD_SPECS: tuple[FieldSpec, ...] = (
    # AEF tracking block, new in the 09-Sept-2026 workbook (A:E). Optional so
    # a workbook in the earlier 30-column layout still imports.
    FieldSpec("aef", "AEF", "optional", "text", ("Estado AEF",)),
    FieldSpec(
        "quien_solicita",
        "Quien solicita",
        "optional",
        "text",
        ("Solicitante", "Solicitado por"),
    ),
    FieldSpec("fecha_solicitud", "Fecha solicitud", "optional", "date", ("Fecha de solicitud",)),
    FieldSpec("fecha_corta", "Fecha corta", "optional", "date", ("Fecha de corta",)),
    FieldSpec("fecha_termino", "Fecha termino", "optional", "date", ("Fecha de termino",)),
    # The V1 business table (formerly A:AD).
    FieldSpec("predio_ref", "Predio Ref", "expected", "text"),
    FieldSpec("rol_ref", "Rol Ref", "expected", "text"),
    FieldSpec("area_ref", "N° Area de Ref", "expected", "text"),
    FieldSpec("pmf", "PMF", "identity", "text"),
    FieldSpec("carpeta_source", "Carpeta", "expected", "text", ("Carpeta origen",)),
    FieldSpec("pas", "PAS", "expected", "text"),
    FieldSpec("estado", "Estado", "required", "text"),
    FieldSpec("estado_resumido", "Estado resumido", "required", "text"),
    FieldSpec("tipo_rechazo", "Tipo de rechazo", "expected", "text"),
    FieldSpec("reingreso_tec", "Reingreso_Tec", "expected", "text"),
    FieldSpec("reingreso_legal", "Reingreso_Legal", "expected", "text"),
    FieldSpec("reingreso_recrep", "Reingreso_RecRep", "expected", "text"),
    FieldSpec("tipo_propietario", "Tipo de propietario", "required", "text"),
    FieldSpec("id_transelec", "ID TRANSELEC", "expected", "text"),
    FieldSpec("rol", "Rol", "identity", "text"),
    FieldSpec("numero_predio", "N Predio", "identity", "text"),
    FieldSpec("numero_area_corta", "N Area de Corta", "expected", "text"),
    FieldSpec("superficie_corta", "Superficie de corta", "required", "number"),
    FieldSpec(
        "superficie_total_corta",
        "Superficie de total de corta",
        "expected",
        "number",
        ("Superficie total de corta",),
    ),
    FieldSpec("fecha_ingreso", "Fecha de ingreso", "expected", "date"),
    FieldSpec("numero_ingreso", "N Ingreso", "required", "text"),
    FieldSpec("fecha_90_dias", "90 dias", "expected", "date"),
    # "Hoy" is kept as raw text: the V1 audit found it type-inconsistent, and
    # it is never observation time.
    FieldSpec("hoy", "Hoy", "expected", "text"),
    FieldSpec("empresa", "Empresa", "required", "text"),
    FieldSpec("id_predio_unico_ii", "ID_Predio_UnicoII", "expected", "text"),
    FieldSpec("id_pmf", "ID_PMF", "expected", "text"),
    FieldSpec("id_predio_unico", "ID_Predo_Unico", "identity", "text", ("ID_Predio_Unico",)),
    FieldSpec("tramite", "Tramite", "expected", "text"),
    FieldSpec(
        "carpeta_normalizada",
        "Carpeta",
        "expected",
        "text",
        ("Carpeta normalizada",),
    ),
    FieldSpec("sector", "Sector", "expected", "text"),
)

FIELD_BY_NAME: dict[str, FieldSpec] = {spec.name: spec for spec in FIELD_SPECS}

AEF_TRACKING_FIELDS: tuple[str, ...] = (
    "aef",
    "quien_solicita",
    "fecha_solicitud",
    "fecha_corta",
    "fecha_termino",
)

# The shared bare header. Neither Carpeta field is recognized from it through
# the alias index; it is resolved only by _resolve_carpeta_columns.
_BARE_CARPETA = "carpeta"
_CARPETA_FIELDS = ("carpeta_source", "carpeta_normalizada")


def normalize_header(value: Any) -> str:
    """Fold a header cell to the form used for recognition.

    Case, accents, the degree/ordinal signs (``N°``/``Nº``), dots,
    underscores, hyphens, slashes and runs of whitespace are all
    insignificant. Nothing else is: a word that differs is a different
    header.
    """

    if value is None:
        return ""
    text = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    # Remove the ordinal/degree signs before NFKD, which would otherwise turn
    # "º" into a letter "o".
    text = re.sub(r"[°º]", "", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace(".", "")
    text = re.sub(r"[_\-/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for spec in FIELD_SPECS:
        names = (spec.header, *spec.aliases)
        for name in names:
            key = normalize_header(name)
            if key == _BARE_CARPETA:
                continue
            existing = index.get(key)
            if existing is not None and existing != spec.name:  # pragma: no cover
                raise RuntimeError(f"Header alias {name!r} maps to both {existing} and {spec.name}")
            index[key] = spec.name
    return index


ALIAS_INDEX: dict[str, str] = _build_alias_index()


def column_letter(index: int) -> str:
    """Zero-based column index to its spreadsheet letter (0 → A, 26 → AA)."""

    letters = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    """One finding, located by worksheet row numbers and column letters."""

    code: str
    severity: Severity
    message: str
    field: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[int, ...] = ()
    row_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
            "columns": list(self.columns),
            "rows": list(self.rows),
            "row_count": self.row_count,
        }


@dataclass(frozen=True, slots=True)
class ColumnDecision:
    """What the resolver decided about one worksheet column."""

    column: str
    header: str | None
    status: ColumnStatus
    field: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "header": self.header,
            "status": self.status,
            "field": self.field,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class FieldCoverage:
    field: str
    header: str
    tier: Tier
    column: str | None
    filled_rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "header": self.header,
            "tier": self.tier,
            "column": self.column,
            "filled_rows": self.filled_rows,
        }


@dataclass(frozen=True, slots=True)
class AuxiliaryRegion:
    first_column: str
    last_column: str
    column_count: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_column": self.first_column,
            "last_column": self.last_column,
            "column_count": self.column_count,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class LayoutReport:
    """Every mapping decision and issue for one ``Resumen`` worksheet."""

    parser_version: str
    sheet_name: str
    header_row: int | None
    business_rows: int
    columns: tuple[ColumnDecision, ...]
    fields: tuple[FieldCoverage, ...]
    auxiliary_regions: tuple[AuxiliaryRegion, ...]
    issues: tuple[LayoutIssue, ...]

    def count(self, severity: Severity) -> int:
        return sum(1 for issue in self.issues if issue.severity == severity)

    @property
    def has_errors(self) -> bool:
        return self.count("error") > 0

    @property
    def mapped_fields(self) -> tuple[str, ...]:
        return tuple(coverage.field for coverage in self.fields if coverage.column is not None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parser_version": self.parser_version,
            "sheet_name": self.sheet_name,
            "header_row": self.header_row,
            "business_rows": self.business_rows,
            "columns": [decision.to_dict() for decision in self.columns],
            "fields": [coverage.to_dict() for coverage in self.fields],
            "auxiliary_regions": [region.to_dict() for region in self.auxiliary_regions],
            "issues": [issue.to_dict() for issue in self.issues],
            "counts": {
                "error": self.count("error"),
                "warning": self.count("warning"),
                "info": self.count("info"),
            },
        }

    def first_error(self) -> LayoutIssue | None:
        return next((issue for issue in self.issues if issue.severity == "error"), None)


TextDateResolution = Literal["parsed_spanish_long", "multiple_dates", "placeholder", "unrecognized"]


@dataclass(frozen=True, slots=True)
class TextDateEvidence:
    """The raw text found in a date column, and what was (not) read from it.

    ``parsed`` is set only for ``parsed_spanish_long``. For every other
    resolution the cell has no date and ``raw`` is the only record of it.
    """

    raw: str
    resolution: TextDateResolution
    parsed: dt.date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "resolution": self.resolution,
            "parsed": self.parsed.isoformat() if self.parsed else None,
        }


@dataclass(frozen=True, slots=True)
class ResolvedRow:
    """One business row: its worksheet row number and raw values by field.

    Every field in :data:`FIELD_SPECS` is present as a key; a field no column
    carried is ``None``. Values are exactly what the worksheet cell held —
    coercion to persisted types happens in ``import_projection``.
    ``text_dates`` holds, per date field whose cell held text instead of an
    Excel date, that text and how it was classified.
    """

    source_row_number: int
    values: dict[str, Any]
    text_dates: dict[str, TextDateEvidence] = dataclass_field(default_factory=dict)

    def effective(self, name: str) -> Any:
        """The field's value for comparisons: a parsed text date when there
        is one, the raw text when a date column's text was not resolved,
        otherwise the cell value."""

        evidence = self.text_dates.get(name)
        if evidence is not None:
            return evidence.parsed if evidence.parsed is not None else evidence.raw
        return self.values.get(name)


@dataclass(frozen=True, slots=True)
class LayoutResolution:
    report: LayoutReport
    rows: tuple[ResolvedRow, ...]


# ---------------------------------------------------------------------------
# Formula evidence
# ---------------------------------------------------------------------------


class _UnsafeXmlError(ValueError):
    pass


def _sheet_xml_path(archive: zipfile.ZipFile, sheet_name: str) -> str | None:
    """Resolve a worksheet's XML part from workbook.xml and its relationships."""

    workbook_xml = archive.read("xl/workbook.xml")
    rels_xml = archive.read("xl/_rels/workbook.xml.rels")

    relationship_id: str | None = None
    targets: dict[str, str] = {}

    def on_workbook_start(name: str, attrs: dict[str, str]) -> None:
        nonlocal relationship_id
        if name.rsplit(":", 1)[-1] == "sheet" and attrs.get("name") == sheet_name:
            for key, value in attrs.items():
                if key.endswith(":id") or key == "id":
                    relationship_id = value

    def on_rels_start(name: str, attrs: dict[str, str]) -> None:
        if name.rsplit(":", 1)[-1] == "Relationship" and "Id" in attrs:
            targets[attrs["Id"]] = attrs.get("Target", "")

    _parse_xml_bytes(workbook_xml, on_workbook_start)
    _parse_xml_bytes(rels_xml, on_rels_start)

    if relationship_id is None or relationship_id not in targets:
        return None
    target = targets[relationship_id].lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _safe_parser() -> xml.parsers.expat.XMLParserType:
    parser = xml.parsers.expat.ParserCreate()

    def reject_doctype(*_: Any) -> None:
        raise _UnsafeXmlError("DOCTYPE declarations are not accepted in workbook XML")

    parser.StartDoctypeDeclHandler = reject_doctype
    parser.EntityDeclHandler = reject_doctype
    return parser


def _parse_xml_bytes(data: bytes, on_start: Any) -> None:
    parser = _safe_parser()
    parser.StartElementHandler = on_start
    parser.Parse(data, True)


_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _column_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


@dataclass(frozen=True, slots=True)
class CellEvidence:
    """What the sheet XML says about one cell that calamine cannot."""

    formula: bool
    cached: bool
    error: bool


def scan_formula_cells(path: Path, sheet_name: str) -> dict[tuple[int, int], CellEvidence]:
    """Return ``{(row0, col0): CellEvidence}`` for formula and error cells.

    calamine exposes a formula cell only through its cached result, so a
    formula saved without one (common for files written by scripts rather
    than by Excel) reads as blank — and it reads an Excel error value
    (``#N/A``, ``#REF!``…) as blank too. Neither is distinguishable from a
    truly blank cell unless the sheet XML is consulted, which is what this
    does — streaming, with DOCTYPE/entity declarations refused.

    Returns an empty mapping when the part cannot be located; this evidence
    is supplementary and must never block an import on its own.
    """

    try:
        with zipfile.ZipFile(path) as archive:
            part = _sheet_xml_path(archive, sheet_name)
            if part is None or part not in archive.namelist():
                return {}

            cells: dict[tuple[int, int], CellEvidence] = {}
            state: dict[str, Any] = {
                "ref": None,
                "formula": False,
                "value": False,
                "error": False,
                "in_v": False,
            }

            def on_start(name: str, attrs: dict[str, str]) -> None:
                local = name.rsplit(":", 1)[-1]
                if local == "c":
                    state.update(
                        ref=attrs.get("r"), formula=False, value=False, error=attrs.get("t") == "e"
                    )
                elif local == "f":
                    state["formula"] = True
                elif local == "v":
                    state["in_v"] = True

            def on_chars(data: str) -> None:
                if state["in_v"] and data.strip():
                    state["value"] = True

            def on_end(name: str) -> None:
                local = name.rsplit(":", 1)[-1]
                if local == "v":
                    state["in_v"] = False
                elif local == "c":
                    ref = state["ref"]
                    if (state["formula"] or state["error"]) and ref:
                        match = _CELL_REF.match(ref)
                        if match:
                            key = (int(match.group(2)) - 1, _column_index(match.group(1)))
                            cells[key] = CellEvidence(
                                formula=bool(state["formula"]),
                                cached=bool(state["value"]),
                                error=bool(state["error"]),
                            )
                    state["ref"] = None

            parser = _safe_parser()
            parser.StartElementHandler = on_start
            parser.EndElementHandler = on_end
            parser.CharacterDataHandler = on_chars
            with archive.open(part) as stream:
                while chunk := stream.read(1024 * 1024):
                    parser.Parse(chunk, False)
                parser.Parse(b"", True)
            return cells
    except (zipfile.BadZipFile, KeyError, xml.parsers.expat.ExpatError, _UnsafeXmlError):
        return {}


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _header_text(value: Any) -> str | None:
    if _is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()
    return text[:MAX_HEADER_CHARS]


def _cell(grid: Sequence[Sequence[Any]], row: int, column: int) -> Any:
    values = grid[row]
    return values[column] if column < len(values) else None


def _capped(
    rows: Iterable[int], limit: int | None = MAX_ROWS_PER_ISSUE
) -> tuple[tuple[int, ...], int]:
    ordered = sorted(set(rows))
    return tuple(ordered if limit is None else ordered[:limit]), len(ordered)


def _recognize(header: Any) -> str | None:
    """Field name, the bare-Carpeta marker, or None."""

    key = normalize_header(header)
    if not key:
        return None
    if key == _BARE_CARPETA:
        return _BARE_CARPETA
    return ALIAS_INDEX.get(key)


def _detect_header_row(
    grid: Sequence[Sequence[Any]],
) -> tuple[int | None, LayoutIssue | None]:
    scored: list[tuple[int, int]] = []

    for row in range(min(HEADER_SCAN_ROWS, len(grid))):
        recognized = {_recognize(value) for value in grid[row]} - {None}
        if "pmf" in recognized and len(recognized) >= MIN_HEADER_MATCHES:
            scored.append((len(recognized), row))

    if not scored:
        return None, LayoutIssue(
            code="encabezado_no_encontrado",
            severity="error",
            message=(
                f"No se encontró la fila de encabezados en las primeras {HEADER_SCAN_ROWS} filas "
                f"de «{RESUMEN_SHEET_NAME}»: ninguna fila contiene «PMF» y al menos "
                f"{MIN_HEADER_MATCHES} columnas reconocidas."
            ),
            field="pmf",
        )

    best = max(score for score, _ in scored)
    best_rows = [row for score, row in scored if score == best]
    if len(best_rows) > 1:
        return None, LayoutIssue(
            code="encabezado_ambiguo",
            severity="error",
            message=(
                "Hay más de una fila que parece ser la fila de encabezados; no se puede decidir "
                "cuál usar sin revisión."
            ),
            rows=tuple(row + 1 for row in best_rows),
            row_count=len(best_rows),
        )
    return best_rows[0], None


def _nearest_recognized(
    column: int,
    step: int,
    business_columns: Sequence[int],
    recognized: dict[int, str | None],
) -> str | None:
    """The field of the nearest business column in ``step`` direction whose
    header is recognized as a (non-Carpeta) field."""

    ordered = sorted(business_columns)
    position = ordered.index(column)
    index = position + step
    while 0 <= index < len(ordered):
        candidate = recognized.get(ordered[index])
        if candidate is not None and candidate != _BARE_CARPETA:
            return candidate
        index += step
    return None


def _resolve_carpeta_columns(
    candidates: Sequence[int],
    business_columns: Sequence[int],
    recognized: dict[int, str | None],
) -> tuple[dict[int, str], list[LayoutIssue], dict[int, str]]:
    """Assign each bare ``Carpeta`` column to a field from its neighbours.

    The workbook has two different columns both headed ``Carpeta``: one
    beside ``PMF`` (the PMF's own folder, e.g. a numbered tramo folder) and
    one between ``Tramite`` and ``Sector`` (a coarser locality grouping).
    Header text cannot tell them apart, so a bare ``Carpeta`` column is
    bound only when exactly one neighbour rule holds. Anything else — no
    rule, both rules, or two columns claiming the same field — is ambiguous
    and blocks the import.
    """

    assigned: dict[int, str] = {}
    notes: dict[int, str] = {}
    issues: list[LayoutIssue] = []

    for column in candidates:
        left = _nearest_recognized(column, -1, business_columns, recognized)
        right = _nearest_recognized(column, +1, business_columns, recognized)
        is_source = left == "pmf"
        is_normalized = left == "tramite" or right == "sector"

        if is_source == is_normalized:
            issues.append(
                LayoutIssue(
                    code="carpeta_ambigua",
                    severity="error",
                    message=(
                        f"La columna {column_letter(column)} se llama «Carpeta», pero su posición "
                        "no permite distinguir si es la carpeta del PMF (junto a «PMF») o la "
                        "carpeta normalizada (entre «Tramite» y «Sector»). Renómbrela "
                        "«Carpeta origen» o «Carpeta normalizada», o devuélvala junto a esas "
                        "columnas."
                    ),
                    columns=(column_letter(column),),
                )
            )
            continue

        field_name = "carpeta_source" if is_source else "carpeta_normalizada"
        assigned[column] = field_name
        notes[column] = (
            "«Carpeta» junto a «PMF»: carpeta del PMF."
            if is_source
            else "«Carpeta» junto a «Tramite»/«Sector»: carpeta normalizada."
        )

    by_field: dict[str, list[int]] = {}
    for column, field_name in assigned.items():
        by_field.setdefault(field_name, []).append(column)
    for field_name, columns in by_field.items():
        if len(columns) > 1:
            issues.append(
                LayoutIssue(
                    code="carpeta_ambigua",
                    severity="error",
                    message=(
                        "Varias columnas «Carpeta» se asignarían al mismo campo "
                        f"({FIELD_BY_NAME[field_name].header} → {field_name}); no se puede "
                        "decidir cuál usar sin revisión."
                    ),
                    field=field_name,
                    columns=tuple(column_letter(column) for column in sorted(columns)),
                )
            )
            for column in columns:
                assigned.pop(column, None)

    return assigned, issues, notes


def _comparable(value: Any) -> Any:
    if _is_blank(value):
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dt.datetime):
        return value.date() if value.time() == dt.time() else value
    return value


def resolve_resumen_layout(
    grid: Sequence[Sequence[Any]],
    *,
    formula_cells: dict[tuple[int, int], CellEvidence] | None = None,
) -> LayoutResolution:
    """Resolve an absolute ``Resumen`` grid (row 0 = worksheet row 1) into
    business rows plus a complete report of every decision.

    Never raises for a layout problem: problems become issues. The caller
    decides what an ``error`` issue means (the import gate refuses).
    """

    formula_cells = formula_cells or {}
    issues: list[LayoutIssue] = []

    header_row, header_issue = _detect_header_row(grid)
    if header_row is None:
        assert header_issue is not None
        return LayoutResolution(
            report=LayoutReport(
                parser_version=PARSER_VERSION,
                sheet_name=RESUMEN_SHEET_NAME,
                header_row=None,
                business_rows=0,
                columns=(),
                fields=tuple(
                    FieldCoverage(spec.name, spec.header, spec.tier, None, 0)
                    for spec in FIELD_SPECS
                ),
                auxiliary_regions=(),
                issues=(header_issue,),
            ),
            rows=(),
        )

    data_rows = range(header_row + 1, len(grid))
    width = max((len(values) for values in grid), default=0)

    recognized: dict[int, str | None] = {}
    has_data: dict[int, bool] = {}
    for column in range(width):
        recognized[column] = _recognize(_cell(grid, header_row, column))
        has_data[column] = any(not _is_blank(_cell(grid, row, column)) for row in data_rows)

    def is_blank_column(column: int) -> bool:
        return _header_text(_cell(grid, header_row, column)) is None and not has_data[column]

    # --- Blocks separated by fully blank columns ---------------------------
    blocks: list[list[int]] = []
    current: list[int] = []
    for column in range(width):
        if is_blank_column(column):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(column)
    if current:
        blocks.append(current)

    def block_fields(block: Sequence[int]) -> set[str]:
        return {
            name
            for column in block
            if (name := recognized[column]) is not None and name != _BARE_CARPETA
        }

    main_index = next(
        (index for index, block in enumerate(blocks) if "pmf" in block_fields(block)),
        None,
    )
    assert main_index is not None, "header detection guarantees a PMF column"

    business_columns: list[int] = list(blocks[main_index])
    main_fields = block_fields(blocks[main_index])
    auxiliary_regions: list[AuxiliaryRegion] = []
    joined_blocks: list[list[int]] = []

    for index, block in enumerate(blocks):
        if index == main_index:
            continue
        new_fields = block_fields(block) - main_fields
        if new_fields:
            business_columns.extend(block)
            main_fields |= new_fields
            joined_blocks.append(block)
        else:
            auxiliary_regions.append(
                AuxiliaryRegion(
                    first_column=column_letter(block[0]),
                    last_column=column_letter(block[-1]),
                    column_count=len(block),
                    reason=(
                        "Región separada de la tabla por una columna vacía y sin columnas de "
                        "negocio nuevas (tablas resumen o dinámicas de la hoja): no se lee."
                    ),
                )
            )

    business_columns.sort()
    business_set = set(business_columns)

    if joined_blocks:
        issues.append(
            LayoutIssue(
                code="columna_vacia_intermedia",
                severity="warning",
                message=(
                    "La tabla contiene columnas completamente vacías entre columnas reconocidas; "
                    "se leyó como una sola tabla. Verifique que no falte información."
                ),
                columns=tuple(
                    column_letter(column)
                    for column in range(min(business_columns), max(business_columns) + 1)
                    if column not in business_set and is_blank_column(column)
                ),
            )
        )

    if auxiliary_regions:
        issues.append(
            LayoutIssue(
                code="region_auxiliar_ignorada",
                severity="info",
                message=(
                    "Se ignoraron regiones fuera de la tabla principal: "
                    + ", ".join(
                        f"{region.first_column}–{region.last_column}"
                        if region.first_column != region.last_column
                        else region.first_column
                        for region in auxiliary_regions
                    )
                    + "."
                ),
                columns=tuple(region.first_column for region in auxiliary_regions),
            )
        )

    # --- Column decisions ----------------------------------------------------
    decisions: dict[int, ColumnDecision] = {}
    groups: dict[str, list[int]] = {}
    carpeta_candidates: list[int] = []
    unrecognized: list[int] = []
    unlabeled: list[int] = []

    for column in business_columns:
        name = recognized[column]
        header = _header_text(_cell(grid, header_row, column))
        if name == _BARE_CARPETA:
            carpeta_candidates.append(column)
        elif name is not None:
            groups.setdefault(name, []).append(column)
        elif header is None:
            unlabeled.append(column)
            decisions[column] = ColumnDecision(
                column_letter(column),
                None,
                "unlabeled_data_ignored",
                note="Columna sin encabezado con datos: no se lee.",
            )
        else:
            unrecognized.append(column)
            decisions[column] = ColumnDecision(
                column_letter(column),
                header,
                "unrecognized_ignored",
                note="Encabezado no reconocido: no se lee.",
            )

    carpeta_assigned, carpeta_issues, carpeta_notes = _resolve_carpeta_columns(
        carpeta_candidates, business_columns, recognized
    )
    issues.extend(carpeta_issues)
    for column, field_name in carpeta_assigned.items():
        groups.setdefault(field_name, []).append(column)
    for column in carpeta_candidates:
        if column not in carpeta_assigned:
            decisions[column] = ColumnDecision(
                column_letter(column),
                _header_text(_cell(grid, header_row, column)),
                "unrecognized_ignored",
                note="«Carpeta» ambigua: requiere revisión.",
            )

    if unrecognized:
        issues.append(
            LayoutIssue(
                code="columna_no_reconocida",
                severity="info",
                message=(
                    "Columnas con encabezado no reconocido; no se leen: "
                    + ", ".join(
                        f"{column_letter(c)} «{_header_text(_cell(grid, header_row, c))}»"
                        for c in unrecognized
                    )
                    + "."
                ),
                columns=tuple(column_letter(column) for column in unrecognized),
            )
        )
    if unlabeled:
        rows_with_data = [
            row + 1
            for row in data_rows
            if any(not _is_blank(_cell(grid, row, column)) for column in unlabeled)
        ]
        capped, total = _capped(rows_with_data)
        issues.append(
            LayoutIssue(
                code="columna_sin_encabezado",
                severity="warning",
                message=(
                    "Columnas sin encabezado contienen datos dentro de la tabla; no se leen. "
                    "Si son información de negocio, agregue un encabezado reconocido."
                ),
                columns=tuple(column_letter(column) for column in unlabeled),
                rows=capped,
                row_count=total,
            )
        )

    # --- Duplicate recognized headers -----------------------------------------
    field_column: dict[str, int] = {}
    for field_name, columns in groups.items():
        columns.sort()
        primary = columns[0]
        if len(columns) > 1:
            conflicting_rows = [
                row + 1
                for row in data_rows
                if len({_comparable(_cell(grid, row, column)) for column in columns}) > 1
            ]
            letters = tuple(column_letter(column) for column in columns)
            if conflicting_rows:
                capped, total = _capped(conflicting_rows)
                issues.append(
                    LayoutIssue(
                        code="encabezado_duplicado_conflictivo",
                        severity="error",
                        message=(
                            f"El campo «{FIELD_BY_NAME[field_name].header}» aparece en varias "
                            f"columnas ({', '.join(letters)}) con valores distintos en "
                            f"{total} filas; no se puede elegir una sin revisión."
                        ),
                        field=field_name,
                        columns=letters,
                        rows=capped,
                        row_count=total,
                    )
                )
                for column in columns:
                    decisions[column] = ColumnDecision(
                        column_letter(column),
                        _header_text(_cell(grid, header_row, column)),
                        "duplicate_ignored",
                        field=field_name,
                        note="Duplicado con valores distintos: requiere revisión.",
                    )
                continue
            issues.append(
                LayoutIssue(
                    code="encabezado_duplicado_identico",
                    severity="warning",
                    message=(
                        f"El campo «{FIELD_BY_NAME[field_name].header}» aparece en varias "
                        f"columnas ({', '.join(letters)}) con valores idénticos; se usa "
                        f"{letters[0]} y se ignoran las demás."
                    ),
                    field=field_name,
                    columns=letters,
                )
            )
            for column in columns[1:]:
                decisions[column] = ColumnDecision(
                    column_letter(column),
                    _header_text(_cell(grid, header_row, column)),
                    "duplicate_ignored",
                    field=field_name,
                    note=f"Duplicado idéntico de {column_letter(primary)}.",
                )

        field_column[field_name] = primary
        header = _header_text(_cell(grid, header_row, primary))
        canonical = FIELD_BY_NAME[field_name].header
        note = carpeta_notes.get(primary)
        if note is None and normalize_header(header) != normalize_header(canonical):
            note = f"Alias documentado de «{canonical}»."
        decisions[primary] = ColumnDecision(
            column_letter(primary), header, "mapped", field=field_name, note=note
        )

    # Separators inside the business span are worth showing in the preview.
    if business_columns:
        for column in range(min(business_columns), max(business_columns) + 2):
            if column < width and column not in business_set and is_blank_column(column):
                decisions[column] = ColumnDecision(
                    column_letter(column), None, "separator", note="Columna vacía."
                )

    # --- Missing fields -------------------------------------------------------
    for spec in FIELD_SPECS:
        if spec.name in field_column:
            continue
        if any(issue.field == spec.name and issue.severity == "error" for issue in issues):
            continue
        if spec.name in _CARPETA_FIELDS and any(i.code == "carpeta_ambigua" for i in issues):
            continue
        if spec.tier in ("identity", "required"):
            issues.append(
                LayoutIssue(
                    code="columna_esencial_ausente",
                    severity="error",
                    message=(
                        f"No se encontró la columna esencial «{spec.header}» "
                        f"({'identidad' if spec.tier == 'identity' else 'requerida'}). "
                        "Sin ella la importación no es confiable."
                    ),
                    field=spec.name,
                )
            )
        elif spec.tier == "expected":
            issues.append(
                LayoutIssue(
                    code="columna_esperada_ausente",
                    severity="warning",
                    message=(
                        f"No se encontró la columna «{spec.header}». El campo quedará vacío "
                        "en esta versión."
                    ),
                    field=spec.name,
                )
            )
        else:
            issues.append(
                LayoutIssue(
                    code="columna_opcional_ausente",
                    severity="info",
                    message=(
                        f"La planilla no incluye la columna «{spec.header}»; el campo queda "
                        "sin datos en esta versión."
                    ),
                    field=spec.name,
                )
            )

    column_decisions = tuple(decisions[column] for column in sorted(decisions))

    if any(issue.severity == "error" for issue in issues):
        return LayoutResolution(
            report=LayoutReport(
                parser_version=PARSER_VERSION,
                sheet_name=RESUMEN_SHEET_NAME,
                header_row=header_row + 1,
                business_rows=0,
                columns=column_decisions,
                fields=tuple(
                    FieldCoverage(
                        spec.name,
                        spec.header,
                        spec.tier,
                        column_letter(field_column[spec.name])
                        if spec.name in field_column
                        else None,
                        0,
                    )
                    for spec in FIELD_SPECS
                ),
                auxiliary_regions=tuple(auxiliary_regions),
                issues=tuple(issues),
            ),
            rows=(),
        )

    # --- Rows ----------------------------------------------------------------
    pmf_column = field_column["pmf"]
    rows: list[ResolvedRow] = []
    rows_without_pmf: list[int] = []
    filled: dict[str, int] = {name: 0 for name in field_column}
    bad_dates: dict[str, list[int]] = {}
    text_dates_by_resolution: dict[tuple[str, TextDateResolution], list[int]] = {}
    bad_numbers: dict[str, list[int]] = {}
    excel_errors: dict[str, list[int]] = {}
    uncached_formulas: dict[str, list[int]] = {}
    cached_formulas: dict[str, int] = {}

    for row in data_rows:
        mapped = {name: _cell(grid, row, column) for name, column in field_column.items()}
        text_dates: dict[str, TextDateEvidence] = {}
        if all(_is_blank(value) for value in mapped.values()):
            continue
        if _is_blank(_cell(grid, row, pmf_column)):
            rows_without_pmf.append(row + 1)
            continue

        for name, column in field_column.items():
            value = mapped[name]
            evidence = formula_cells.get((row, column))
            if evidence is not None:
                if evidence.error:
                    excel_errors.setdefault(name, []).append(row + 1)
                    mapped[name] = None
                    continue
                if evidence.formula and evidence.cached:
                    cached_formulas[name] = cached_formulas.get(name, 0) + 1
                elif evidence.formula:
                    uncached_formulas.setdefault(name, []).append(row + 1)
            if _is_blank(value):
                mapped[name] = None
                continue
            filled[name] += 1
            if isinstance(value, str) and value.strip() in _EXCEL_ERROR_VALUES:
                excel_errors.setdefault(name, []).append(row + 1)
                mapped[name] = None
                filled[name] -= 1
                continue
            kind = FIELD_BY_NAME[name].kind
            if kind == "date" and not isinstance(value, dt.date):
                if isinstance(value, str):
                    text_date = classify_text_date(value)
                    text_dates[name] = text_date
                    text_dates_by_resolution.setdefault((name, text_date.resolution), []).append(
                        row + 1
                    )
                else:
                    # A bare time-of-day, which is what a zero or fractional
                    # value in a date-formatted cell reads as, or a number.
                    bad_dates.setdefault(name, []).append(row + 1)
            elif kind == "number" and not _is_number_like(value):
                bad_numbers.setdefault(name, []).append(row + 1)

        values = {spec.name: mapped.get(spec.name) for spec in FIELD_SPECS}
        resolved = ResolvedRow(source_row_number=row + 1, values=values, text_dates=text_dates)
        rows.append(resolved)

        issues.extend(
            _chronology_issues(
                row + 1,
                {name: resolved.effective(name) for name in AEF_TRACKING_FIELDS},
                field_column,
            )
        )

    if rows_without_pmf:
        capped, total = _capped(rows_without_pmf)
        issues.append(
            LayoutIssue(
                code="fila_sin_pmf",
                severity="warning",
                message=(
                    f"{total} filas tienen datos en columnas reconocidas pero no tienen PMF; "
                    "no se importan. Revise si deben tener PMF."
                ),
                field="pmf",
                columns=(column_letter(pmf_column),),
                rows=capped,
                row_count=total,
            )
        )

    for (name, resolution), affected in text_dates_by_resolution.items():
        # Every affected row is listed: the operator reviews these cell by
        # cell, and the raw text of each is kept on its row.
        listed, total = _capped(affected, limit=None)
        code, severity, message = _TEXT_DATE_ISSUES[resolution]
        issues.append(
            LayoutIssue(
                code=code,
                severity=severity,
                message=f"«{FIELD_BY_NAME[name].header}» tiene {total} {message}",
                field=name,
                columns=(column_letter(field_column[name]),),
                rows=listed,
                row_count=total,
            )
        )
    for name, bad in bad_dates.items():
        capped, total = _capped(bad)
        issues.append(
            LayoutIssue(
                code="fecha_no_reconocida",
                severity="warning",
                message=(
                    f"«{FIELD_BY_NAME[name].header}» tiene {total} celdas que no son fechas de "
                    "Excel (un número o una hora); quedan vacías en esta versión."
                ),
                field=name,
                columns=(column_letter(field_column[name]),),
                rows=capped,
                row_count=total,
            )
        )
    for name, bad in bad_numbers.items():
        capped, total = _capped(bad)
        issues.append(
            LayoutIssue(
                code="numero_no_reconocido",
                severity="warning",
                message=(
                    f"«{FIELD_BY_NAME[name].header}» tiene {total} celdas no numéricas; quedan "
                    "vacías en esta versión y no suman en los totales."
                ),
                field=name,
                columns=(column_letter(field_column[name]),),
                rows=capped,
                row_count=total,
            )
        )
    for name, bad in excel_errors.items():
        capped, total = _capped(bad)
        issues.append(
            LayoutIssue(
                code="error_de_formula",
                severity="warning",
                message=(
                    f"«{FIELD_BY_NAME[name].header}» tiene {total} celdas con un error de Excel "
                    "(p. ej. #N/A o #REF!); quedan vacías en esta versión."
                ),
                field=name,
                columns=(column_letter(field_column[name]),),
                rows=capped,
                row_count=total,
            )
        )
    for name, bad in uncached_formulas.items():
        capped, total = _capped(bad)
        issues.append(
            LayoutIssue(
                code="formula_sin_valor",
                severity="warning",
                message=(
                    f"«{FIELD_BY_NAME[name].header}» tiene {total} fórmulas sin valor calculado "
                    "guardado; se leen como vacías. Abra y guarde la planilla en Excel para "
                    "que se calculen."
                ),
                field=name,
                columns=(column_letter(field_column[name]),),
                rows=capped,
                row_count=total,
            )
        )
    for name, count in cached_formulas.items():
        issues.append(
            LayoutIssue(
                code="columna_con_formulas",
                severity="info",
                message=(
                    f"«{FIELD_BY_NAME[name].header}» contiene {count} fórmulas; se usa el valor "
                    "calculado guardado en la planilla."
                ),
                field=name,
                columns=(column_letter(field_column[name]),),
                row_count=count,
            )
        )

    issues.extend(_pmf_conflict_issues(rows, field_column))

    if not rows:
        issues.append(
            LayoutIssue(
                code="sin_filas_con_pmf",
                severity="error",
                message=f"La hoja «{RESUMEN_SHEET_NAME}» no contiene filas de negocio con PMF.",
                field="pmf",
                columns=(column_letter(pmf_column),),
            )
        )

    report = LayoutReport(
        parser_version=PARSER_VERSION,
        sheet_name=RESUMEN_SHEET_NAME,
        header_row=header_row + 1,
        business_rows=len(rows),
        columns=column_decisions,
        fields=tuple(
            FieldCoverage(
                spec.name,
                spec.header,
                spec.tier,
                column_letter(field_column[spec.name]) if spec.name in field_column else None,
                filled.get(spec.name, 0),
            )
            for spec in FIELD_SPECS
        ),
        auxiliary_regions=tuple(auxiliary_regions),
        issues=tuple(issues),
    )
    return LayoutResolution(report=report, rows=tuple(rows) if not report.has_errors else ())


# (issue code, severity, message tail after "«header» tiene N") per resolution.
_TEXT_DATE_ISSUES: dict[TextDateResolution, tuple[str, Severity, str]] = {
    "parsed_spanish_long": (
        "fecha_texto_interpretada",
        "info",
        "celdas con una sola fecha escrita en texto (día, mes en palabras y año); se leen "
        "como esa fecha y se conserva el texto original.",
    ),
    "multiple_dates": (
        "fecha_texto_multiple",
        "warning",
        "celdas con más de una fecha en el mismo texto; no se elige ninguna. La fila queda "
        "sin fecha y conserva el texto original.",
    ),
    "placeholder": (
        "fecha_texto_guion",
        "warning",
        "celdas con «-» en lugar de una fecha; la fila queda sin fecha y conserva el texto.",
    ),
    "unrecognized": (
        "fecha_no_reconocida",
        "warning",
        "celdas con texto que no es una fecha inequívoca (p. ej. día y mes solo en números); "
        "la fila queda sin fecha y conserva el texto original.",
    ),
}

_SPANISH_MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_SPANISH_LONG_DATE = re.compile(r"(\d{1,2}) de ([a-z]+) de (\d{4})")
_NUMERIC_DATE = re.compile(r"(?<!\d)\d{1,2}[-/.]\d{1,2}[-/.](?:\d{4}|\d{2})(?!\d)")
_PLACEHOLDER = re.compile(r"[-\u2010-\u2015]+")


def _fold_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).casefold()
    return re.sub(r"\s+", " ", folded).strip()


def classify_text_date(value: str) -> TextDateEvidence:
    """Classify the text of a date-column cell; parse only what is unambiguous.

    Only one form is read as a date: the whole cell is a single day, a month
    written as a Spanish word and a four-digit year (``13 de noviembre de
    2024``, any case or accents), naming a real calendar day. The month word
    removes the day/month-order ambiguity of numeric forms, which are never
    parsed. Several dates in one cell are not resolved — which one the column
    means is not established — and a dash is a placeholder, not a date.
    """

    raw = value.strip()
    folded = _fold_text(raw)
    if _PLACEHOLDER.fullmatch(folded):
        return TextDateEvidence(raw=raw, resolution="placeholder")
    date_tokens = len(_SPANISH_LONG_DATE.findall(folded)) + len(_NUMERIC_DATE.findall(folded))
    if date_tokens >= 2:
        return TextDateEvidence(raw=raw, resolution="multiple_dates")
    match = _SPANISH_LONG_DATE.fullmatch(folded)
    if match is not None and match.group(2) in _SPANISH_MONTHS:
        try:
            parsed = dt.date(
                int(match.group(3)), _SPANISH_MONTHS[match.group(2)], int(match.group(1))
            )
        except ValueError:
            parsed = None
        if parsed is not None:
            return TextDateEvidence(raw=raw, resolution="parsed_spanish_long", parsed=parsed)
    return TextDateEvidence(raw=raw, resolution="unrecognized")


# ---------------------------------------------------------------------------
# PMF-level AEF tracking values
# ---------------------------------------------------------------------------

PmfValueStatus = Literal["value", "blank", "conflict"]


@dataclass(frozen=True, slots=True)
class PmfValueVariant:
    """One distinct non-blank value of a field within a PMF, and its rows."""

    value: Any
    source_rows: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PmfFieldValue:
    """A tracking field resolved for one PMF from the rows that carry it.

    - ``value``: every non-blank row agrees; ``value`` is that value and
      ``source_rows`` are the rows that supplied it.
    - ``blank``: no row of the PMF has a value.
    - ``conflict``: rows disagree; ``value`` is None and ``variants`` lists
      each distinct value with its rows. Nothing is chosen.

    Blank rows never count as disagreement and never receive the value.
    """

    status: PmfValueStatus
    value: Any
    source_rows: tuple[int, ...]
    variants: tuple[PmfValueVariant, ...]


def resolve_pmf_field(entries: Iterable[tuple[int, Any]]) -> PmfFieldValue:
    """Resolve one field for one PMF from ``(source_row_number, value)``.

    Values compare after trimming text and folding a midnight datetime to its
    date; nothing else is normalized, so ``"Juan"`` and ``"juan"`` differ. A
    raw text left unresolved in a date column is compared as that text, so it
    conflicts with a real date rather than being assumed equal to it.
    """

    by_value: dict[Any, list[int]] = {}
    originals: dict[Any, Any] = {}
    for row_number, value in entries:
        key = _comparable(value)
        if key is None:
            continue
        # A date and a same-looking string must never compare equal.
        tagged = (type(key).__name__, key)
        by_value.setdefault(tagged, []).append(row_number)
        originals.setdefault(tagged, key)
    variants = tuple(
        PmfValueVariant(value=originals[tagged], source_rows=tuple(sorted(rows)))
        for tagged, rows in sorted(by_value.items(), key=lambda item: min(item[1]))
    )
    if not variants:
        return PmfFieldValue(status="blank", value=None, source_rows=(), variants=())
    if len(variants) == 1:
        only = variants[0]
        return PmfFieldValue(
            status="value", value=only.value, source_rows=only.source_rows, variants=variants
        )
    return PmfFieldValue(
        status="conflict",
        value=None,
        source_rows=tuple(sorted(row for variant in variants for row in variant.source_rows)),
        variants=variants,
    )


def _pmf_conflict_issues(
    rows: Sequence[ResolvedRow], field_column: dict[str, int]
) -> list[LayoutIssue]:
    by_pmf: dict[Any, list[ResolvedRow]] = {}
    for resolved in rows:
        by_pmf.setdefault(_comparable(resolved.values["pmf"]), []).append(resolved)

    issues: list[LayoutIssue] = []
    for name in AEF_TRACKING_FIELDS:
        if name not in field_column:
            continue
        conflicting_pmfs = 0
        affected: list[int] = []
        for pmf_rows in by_pmf.values():
            resolved_field = resolve_pmf_field(
                (resolved.source_row_number, resolved.effective(name)) for resolved in pmf_rows
            )
            if resolved_field.status == "conflict":
                conflicting_pmfs += 1
                affected.extend(resolved_field.source_rows)
        if not conflicting_pmfs:
            continue
        listed, total = _capped(affected, limit=None)
        issues.append(
            LayoutIssue(
                code="aef_conflicto_pmf",
                severity="warning",
                message=(
                    f"«{FIELD_BY_NAME[name].header}»: {conflicting_pmfs} PMF tienen valores "
                    "distintos en sus filas. No se elige ninguno para el PMF; cada fila "
                    "conserva su valor. Revise las filas indicadas."
                ),
                field=name,
                columns=(column_letter(field_column[name]),),
                rows=listed,
                row_count=total,
            )
        )
    return issues


def _is_number_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    try:
        float(str(value).strip())
    except ValueError:
        return False
    return True


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


# Pairs checked for chronological order: (earlier, later, issue code).
CHRONOLOGY_RULES: tuple[tuple[str, str, str], ...] = (
    ("fecha_solicitud", "fecha_corta", "cronologia_corta_antes_de_solicitud"),
    ("fecha_corta", "fecha_termino", "cronologia_termino_antes_de_corta"),
    ("fecha_solicitud", "fecha_termino", "cronologia_termino_antes_de_solicitud"),
)


def chronology_flags(values: dict[str, Any]) -> tuple[str, ...]:
    """Codes of every chronology rule this row's AEF dates break.

    Only inconsistencies between dates that are present are reported; a
    missing (or unreadable) date is not an inconsistency. Every violated pair
    is reported on its own: no rule is suppressed as "implied" by another,
    because an operator must see each ordering that is actually wrong.
    """

    flags: list[str] = []
    for earlier, later, code in CHRONOLOGY_RULES:
        first, second = _as_date(values.get(earlier)), _as_date(values.get(later))
        if first is None or second is None or second >= first:
            continue
        flags.append(code)
    return tuple(flags)


_CHRONOLOGY_MESSAGES = {
    "cronologia_corta_antes_de_solicitud": "«Fecha corta» es anterior a «Fecha solicitud»",
    "cronologia_termino_antes_de_corta": "«Fecha termino» es anterior a «Fecha corta»",
    "cronologia_termino_antes_de_solicitud": "«Fecha termino» es anterior a «Fecha solicitud»",
}


def _chronology_issues(
    row_number: int, values: dict[str, Any], field_column: dict[str, int]
) -> list[LayoutIssue]:
    issues: list[LayoutIssue] = []
    flags = chronology_flags(values)
    for earlier, later, code in CHRONOLOGY_RULES:
        if code not in flags:
            continue
        issues.append(
            LayoutIssue(
                code=code,
                severity="warning",
                message=(
                    f"Fila {row_number}: {_CHRONOLOGY_MESSAGES[code]}. Se conservan las fechas "
                    "tal como vienen; revise la planilla."
                ),
                field=later,
                columns=tuple(
                    column_letter(field_column[name])
                    for name in (earlier, later)
                    if name in field_column
                ),
                rows=(row_number,),
                row_count=1,
            )
        )
    return issues


def find_resumen_sheet(sheet_names: Sequence[str]) -> tuple[str | None, LayoutIssue | None]:
    """The worksheet to read: exactly ``Resumen``, tolerating case/spacing.

    Historical snapshots (``Resumen 16Feb26``) are distinct names and never
    match. Two sheets that both normalize to ``resumen`` are ambiguous.
    """

    matches = [name for name in sheet_names if normalize_header(name) == "resumen"]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, LayoutIssue(
            code="hoja_resumen_ausente",
            severity="error",
            message=f"La planilla no tiene la hoja «{RESUMEN_SHEET_NAME}».",
        )
    return None, LayoutIssue(
        code="hoja_resumen_ambigua",
        severity="error",
        message=(
            f"La planilla tiene varias hojas que se llaman «{RESUMEN_SHEET_NAME}» "
            f"({', '.join(matches)}); no se puede elegir una sin revisión."
        ),
    )
