"""Write web edits into an uploaded planilla without rebuilding it.

The download promised to Campo Digital is "the same planilla, with the
edited cells marked «web» and everything else unchanged" (spec
docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md §5).
So this module never re-serializes a part with an XML library: doing so
renames the namespace prefixes that ``mc:Ignorable`` names, and Excel then
reports the file as damaged. Every change is a text-level edit of the few
parts listed below; every other ZIP entry is streamed through unchanged, in
its original order and with its original compression method.

Touched parts: the edited worksheet, ``xl/styles.xml``, ``xl/workbook.xml``
(recalculate on open), each ``xl/pivotCache/pivotCacheDefinitionN.xml``
(refresh on open), ``[Content_Types].xml`` and the sheet's relationships
(only when notes are added), plus a comments part and a VML drawing part
(created, or appended to when the sheet already has notes).

An unexpected XML shape makes the patcher refuse with
``WorkbookPatchError`` rather than write a file Excel would repair.
Standard library only.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from xml.parsers import expat
from xml.sax.saxutils import escape

CellKind = Literal["text", "date"]

WEB_FILL_RGB = "FFFFF2CC"
NOTE_AUTHOR = "web"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL_TYPE_COMMENTS = f"{_REL_NS}/comments"
_REL_TYPE_VML = f"{_REL_NS}/vmlDrawing"
_CT_COMMENTS = "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"
_CT_VML = "application/vnd.openxmlformats-officedocument.vmlDrawing"
_COPY_CHUNK = 1024 * 1024
# The edited worksheet is the one part read whole into memory (the real
# «Resumen» is about 1 MB); every other part streams in _COPY_CHUNK pieces.
MAX_EDITED_PART_BYTES = 64 * 1024 * 1024

# Built-in number formats Excel renders as dates or times (ECMA-376 §18.8.30).
_BUILTIN_DATE_FORMATS = frozenset({14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47})
_DATE_FORMAT_ID = 14

# Elements that may follow <legacyDrawing> in CT_Worksheet, in schema order.
_AFTER_LEGACY_DRAWING = (
    "legacyDrawingHF",
    "drawingHF",
    "picture",
    "oleObjects",
    "controls",
    "webPublishItems",
    "tableParts",
    "extLst",
)
# Elements that may follow <calcPr> in CT_Workbook, in schema order.
_AFTER_CALC_PR = (
    "oleSize",
    "customWorkbookViews",
    "pivotCaches",
    "smartTagPr",
    "smartTagTypes",
    "webPublishing",
    "fileRecoveryPr",
    "webPublishObjects",
    "extLst",
)

_PLAIN_NUMBER = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
_XML_FORBIDDEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PIVOT_CACHE_DEFINITION = re.compile(r"^xl/pivotCache/pivotCacheDefinition\d+\.xml$")
_CELL_REF = re.compile(r"^([A-Z]{1,3})([1-9]\d*)$")


class WorkbookPatchError(ValueError):
    """The workbook has a shape this patcher does not edit safely."""


@dataclass(frozen=True, slots=True)
class CellEdit:
    """One cell to rewrite. ``row`` is the Excel row number (1-based)."""

    row: int
    column: str
    kind: CellKind
    value: str | dt.date | None
    note: str

    @property
    def ref(self) -> str:
        return f"{self.column}{self.row}"


@dataclass(frozen=True, slots=True)
class SkippedEdit:
    row: int
    column: str
    reason: Literal["formula_cell"]


@dataclass(frozen=True, slots=True)
class PatchResult:
    written: tuple[CellEdit, ...]
    skipped: tuple[SkippedEdit, ...]
    touched_parts: tuple[str, ...]


def column_index(letters: str) -> int:
    """Spreadsheet column letters to a zero-based index (A → 0, AA → 26)."""

    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def excel_serial(value: dt.date, *, date1904: bool) -> int:
    epoch = dt.date(1904, 1, 1) if date1904 else dt.date(1899, 12, 30)
    return (value - epoch).days


# ---------------------------------------------------------------------------
# Small XML text helpers
# ---------------------------------------------------------------------------


def _assert_well_formed(name: str, data: bytes) -> None:
    parser = expat.ParserCreate()

    def refuse(*_: object) -> None:
        raise WorkbookPatchError(f"{name}: DOCTYPE/entity declarations are not accepted")

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise WorkbookPatchError(f"{name}: patched XML is not well formed ({exc})") from exc


def _clean_text(value: str) -> str:
    return _XML_FORBIDDEN.sub("", value)


def _unescape(value: str) -> str:
    return (
        value.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )


def _attr(tag: str, name: str) -> str | None:
    match = re.search(rf'\s{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else None


def _set_attr(tag: str, name: str, value: str) -> str:
    """Set ``name="value"`` on a start tag (``<x ...>`` or ``<x .../>``)."""

    pattern = re.compile(rf'(\s{re.escape(name)}=")[^"]*(")')
    if pattern.search(tag):
        return pattern.sub(rf"\g<1>{value}\g<2>", tag, count=1)
    if tag.endswith("/>"):
        return f'{tag[:-2].rstrip()} {name}="{value}"/>'
    return f'{tag[:-1]} {name}="{value}">'


def _remove_attr(tag: str, name: str) -> str:
    return re.sub(rf'\s{re.escape(name)}="[^"]*"', "", tag, count=1)


def _start_tag(xml: str, name: str) -> re.Match[str]:
    match = re.search(rf"<{name}(?=[\s>/])[^>]*>", xml)
    if match is None:
        raise WorkbookPatchError(f"<{name}> not found")
    return match


def _insert_before_first(xml: str, candidates: Sequence[str], closing: str, snippet: str) -> str:
    """Insert ``snippet`` before the first ``<candidate`` element present, or
    before ``closing`` when none is."""

    positions = [
        match.start()
        for name in candidates
        if (match := re.search(rf"<{name}[\s/>]", xml)) is not None
    ]
    position = min(positions) if positions else xml.rfind(closing)
    if position < 0:
        raise WorkbookPatchError(f"cannot place {snippet[:30]!r}: {closing} not found")
    return xml[:position] + snippet + xml[position:]


# ---------------------------------------------------------------------------
# Package navigation
# ---------------------------------------------------------------------------


def _resolve_target(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    parts = [part for part in base_dir.split("/") if part]
    for piece in target.split("/"):
        if piece == "..":
            if parts:
                parts.pop()
        elif piece and piece != ".":
            parts.append(piece)
    return "/".join(parts)


def _relative(from_dir: str, target: str) -> str:
    from_parts = from_dir.split("/")
    target_parts = target.split("/")
    common = 0
    while (
        common < min(len(from_parts), len(target_parts))
        and from_parts[common] == target_parts[common]
    ):
        common += 1
    return "/".join([".."] * (len(from_parts) - common) + target_parts[common:])


def _relationships(xml: str) -> list[dict[str, str]]:
    return [
        dict(re.findall(r'(\w+)="([^"]*)"', tag))
        for tag in re.findall(r"<Relationship\s[^>]*?/?>", xml)
    ]


def _sheet_part(workbook_xml: str, workbook_rels_xml: str, sheet_name: str) -> str:
    rels = _relationships(workbook_rels_xml)
    for tag in re.findall(r"<sheet\s[^>]*?/>", workbook_xml):
        name = _attr(tag, "name")
        if name is None or _unescape(name) != sheet_name:
            continue
        relationship_id = _attr(tag, "r:id")
        for rel in rels:
            if rel.get("Id") == relationship_id:
                return _resolve_target("xl", rel["Target"])
    raise WorkbookPatchError(f"worksheet {sheet_name!r} not found")


def _rels_path(part: str) -> str:
    directory, _, filename = part.rpartition("/")
    return f"{directory}/_rels/{filename}.rels"


def _next_free(names: set[str], pattern: str) -> str:
    number = 1
    while pattern.format(number) in names:
        number += 1
    return pattern.format(number)


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Styles:
    xml: str
    xfs: list[str]
    custom_formats: dict[int, str]
    fill_id: int | None = None
    clones: dict[tuple[int, bool], int] = field(default_factory=dict)

    @classmethod
    def parse(cls, xml: str) -> _Styles:
        block = re.search(r"<cellXfs\b[^>]*>(.*?)</cellXfs>", xml, re.S)
        if block is None:
            raise WorkbookPatchError("styles.xml has no <cellXfs>")
        xfs = re.findall(r"<xf\b[^>]*/>|<xf\b[^>]*>.*?</xf>", block.group(1), re.S)
        custom = {
            int(number): _unescape(code)
            for number, code in re.findall(
                r'<numFmt\b[^>]*numFmtId="(\d+)"[^>]*formatCode="([^"]*)"', xml
            )
        }
        return cls(xml=xml, xfs=xfs, custom_formats=custom)

    def is_date_format(self, number_format_id: int) -> bool:
        if number_format_id in _BUILTIN_DATE_FORMATS:
            return True
        code = self.custom_formats.get(number_format_id)
        if code is None:
            return False
        # Quoted literals, [locale/colour] sections and escapes are not tokens.
        stripped = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", code)
        return bool(re.search(r"[dmy]", stripped, re.I))

    def web_style(self, original: int, *, needs_date_format: bool) -> int:
        if original >= len(self.xfs):
            raise WorkbookPatchError(f"cell style {original} is not in <cellXfs>")
        base = self.xfs[original]
        number_format = int(_attr(base, "numFmtId") or "0")
        add_date = needs_date_format and not self.is_date_format(number_format)
        key = (original, add_date)
        if key in self.clones:
            return self.clones[key]
        if self.fill_id is None:
            self.fill_id = self._append_fill()
        open_tag = re.match(r"<xf\b[^>]*?/?>", base)
        if open_tag is None:
            raise WorkbookPatchError("unexpected <xf> shape")
        tag = _set_attr(open_tag.group(0), "fillId", str(self.fill_id))
        tag = _set_attr(tag, "applyFill", "1")
        if add_date:
            tag = _set_attr(tag, "numFmtId", str(_DATE_FORMAT_ID))
            tag = _set_attr(tag, "applyNumberFormat", "1")
        clone = tag + base[open_tag.end() :]
        self.xfs.append(clone)
        self.clones[key] = len(self.xfs) - 1
        self.xml = self._append_to_block("cellXfs", clone, len(self.xfs))
        return self.clones[key]

    def _append_fill(self) -> int:
        block = re.search(r"<fills\b[^>]*>(.*?)</fills>", self.xml, re.S)
        if block is None:
            raise WorkbookPatchError("styles.xml has no <fills>")
        existing = len(re.findall(r"<fill\b", block.group(1)))
        fill = (
            f'<fill><patternFill patternType="solid"><fgColor rgb="{WEB_FILL_RGB}"/>'
            '<bgColor indexed="64"/></patternFill></fill>'
        )
        self.xml = self._append_to_block("fills", fill, existing + 1)
        return existing

    def _append_to_block(self, name: str, element: str, new_count: int) -> str:
        start = _start_tag(self.xml, name)
        close = self.xml.index(f"</{name}>", start.end())
        opened = _set_attr(start.group(0), "count", str(new_count))
        return (
            self.xml[: start.start()]
            + opened
            + self.xml[start.end() : close]
            + element
            + self.xml[close:]
        )


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------


def _row_span(xml: str, row: int) -> tuple[int, int]:
    match = re.search(rf'<row\b[^>]*?\sr="{row}"[^>]*?(?:/>|>.*?</row>)', xml, re.S)
    if match is None:
        raise WorkbookPatchError(f"row {row} not found in the worksheet")
    return match.start(), match.end()


def _cell_xml(edit: CellEdit, style: int, *, numeric_ok: bool, date1904: bool) -> str:
    head = f'<c r="{edit.ref}" s="{style}"'
    if edit.value is None:
        return f"{head}/>"
    if edit.kind == "date":
        if not isinstance(edit.value, dt.date):
            raise WorkbookPatchError(f"{edit.ref}: a date edit needs a date value")
        return f"{head}><v>{excel_serial(edit.value, date1904=date1904)}</v></c>"
    text = _clean_text(str(edit.value))
    if numeric_ok and _PLAIN_NUMBER.match(text):
        return f"{head}><v>{text}</v></c>"
    return f'{head} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _patch_row(row_xml: str, edit: CellEdit, styles: _Styles, *, date1904: bool) -> str | None:
    """Return the row with ``edit`` applied, or None when the cell is a formula."""

    open_match = re.match(r"<row\b[^>]*?(/?)>", row_xml)
    if open_match is None:
        raise WorkbookPatchError("unexpected <row> shape")
    row_tag = open_match.group(0)
    if open_match.group(1) == "/":
        row_tag, body = row_tag[:-2].rstrip() + ">", ""
    else:
        body = row_xml[open_match.end() : -len("</row>")]

    target = column_index(edit.column)
    cells = list(re.finditer(r"<c\b[^>]*?(?:/>|>.*?</c>)", body, re.S))
    existing = next((c for c in cells if _attr(c.group(0), "r") == edit.ref), None)

    if existing is not None:
        cell = existing.group(0)
        if "<f" in cell:
            return None
        original_style = int(_attr(cell, "s") or "0")
        # A text value stays a number only where the planilla had a number
        # (keeps Reingreso_* and plain N Ingreso cells countable by pivots).
        numeric_ok = _attr(cell, "t") in (None, "n")
        new_style = styles.web_style(original_style, needs_date_format=edit.kind == "date")
        replacement = _cell_xml(edit, new_style, numeric_ok=numeric_ok, date1904=date1904)
        body = body[: existing.start()] + replacement + body[existing.end() :]
    else:
        # Excel omits blank, unstyled cells; a blank cell accepts a number.
        new_style = styles.web_style(0, needs_date_format=edit.kind == "date")
        replacement = _cell_xml(edit, new_style, numeric_ok=True, date1904=date1904)
        position = len(body)
        for candidate in cells:
            match = _CELL_REF.match(_attr(candidate.group(0), "r") or "")
            if match and column_index(match.group(1)) > target:
                position = candidate.start()
                break
        body = body[:position] + replacement + body[position:]
        spans = _attr(row_tag, "spans")
        if spans and ":" in spans:
            low, high = (int(part) for part in spans.split(":", 1))
            if not low <= target + 1 <= high:
                row_tag = _remove_attr(row_tag, "spans")

    return row_tag + body + "</row>"


def _patch_cells(
    sheet_xml: str, edits: Sequence[CellEdit], styles: _Styles, *, date1904: bool
) -> tuple[str, list[CellEdit], list[SkippedEdit]]:
    written: list[CellEdit] = []
    skipped: list[SkippedEdit] = []
    for edit in edits:
        if not _CELL_REF.match(edit.ref):
            raise WorkbookPatchError(f"invalid cell reference {edit.ref!r}")
        start, end = _row_span(sheet_xml, edit.row)
        patched = _patch_row(sheet_xml[start:end], edit, styles, date1904=date1904)
        if patched is None:
            skipped.append(SkippedEdit(edit.row, edit.column, "formula_cell"))
            continue
        sheet_xml = sheet_xml[:start] + patched + sheet_xml[end:]
        written.append(edit)
    return sheet_xml, written, skipped


# ---------------------------------------------------------------------------
# Notes (legacy comments + VML)
# ---------------------------------------------------------------------------


def _comment_xml(ref: str, author_id: int, note: str) -> str:
    return (
        f'<comment ref="{ref}" authorId="{author_id}"><text><r><t xml:space="preserve">'
        f"{escape(_clean_text(note))}</t></r></text></comment>"
    )


def _vml_shape(shape_id: int, row: int, column: int) -> str:
    return (
        f'<v:shape id="_x0000_s{shape_id}" type="#_x0000_t202" '
        'style="position:absolute;margin-left:59.25pt;margin-top:1.5pt;width:180pt;'
        'height:60pt;z-index:1;visibility:hidden" fillcolor="#ffffe1" o:insetmode="auto">'
        '<v:fill color2="#ffffe1"/><v:shadow on="t" color="black" obscured="t"/>'
        '<v:path o:connecttype="none"/><v:textbox style="mso-direction-alt:auto">'
        '<div style="text-align:left"></div></v:textbox><x:ClientData ObjectType="Note">'
        "<x:MoveWithCells/><x:SizeWithCells/>"
        f"<x:Anchor>{column + 1}, 15, {row}, 2, {column + 4}, 15, {row + 4}, 16</x:Anchor>"
        f"<x:AutoFill>False</x:AutoFill><x:Row>{row}</x:Row><x:Column>{column}</x:Column>"
        "</x:ClientData></v:shape>"
    )


_NEW_VML = (
    '<xml xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office" '
    'xmlns:x="urn:schemas-microsoft-com:office:excel"><o:shapelayout v:ext="edit">'
    '<o:idmap v:ext="edit" data="{idmap}"/></o:shapelayout><v:shapetype id="_x0000_t202" '
    'coordsize="21600,21600" o:spt="202" path="m,l,21600r21600,l21600,xe">'
    '<v:stroke joinstyle="miter"/><v:path gradientshapeok="t" o:connecttype="rect"/>'
    "</v:shapetype></xml>"
)

_EMPTY_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    "</Relationships>"
)


def _add_notes(
    parts: dict[str, bytes], names: set[str], sheet_part: str, edits: Sequence[CellEdit]
) -> list[str]:
    """Add one note per edit; return the part names touched or created."""

    touched: list[str] = []
    sheet_dir = sheet_part.rpartition("/")[0]
    rels_part = _rels_path(sheet_part)
    rels_xml = parts[rels_part].decode("utf-8") if rels_part in parts else _EMPTY_RELS
    rels = _relationships(rels_xml)
    comments_rel = next((r for r in rels if r.get("Type") == _REL_TYPE_COMMENTS), None)
    vml_rel = next((r for r in rels if r.get("Type") == _REL_TYPE_VML), None)
    if (comments_rel is None) != (vml_rel is None):
        raise WorkbookPatchError("worksheet has notes without their drawing (or the reverse)")

    if comments_rel is not None and vml_rel is not None:
        comments_part = _resolve_target(sheet_dir, comments_rel["Target"])
        vml_part = _resolve_target(sheet_dir, vml_rel["Target"])
        comments_xml = parts[comments_part].decode("utf-8")
        vml_xml = parts[vml_part].decode("utf-8")
    else:
        comments_part = _next_free(names, "xl/comments{}.xml")
        vml_part = _next_free(names, "xl/drawings/vmlDrawing{}.vml")
        used = {r["Id"] for r in rels}
        comments_id = _next_free(used, "rId{}")
        vml_id = _next_free(used | {comments_id}, "rId{}")
        rels_xml = rels_xml.replace(
            "</Relationships>",
            f'<Relationship Id="{comments_id}" Type="{_REL_TYPE_COMMENTS}" '
            f'Target="{_relative(sheet_dir, comments_part)}"/>'
            f'<Relationship Id="{vml_id}" Type="{_REL_TYPE_VML}" '
            f'Target="{_relative(sheet_dir, vml_part)}"/></Relationships>',
        )
        parts[rels_part] = rels_xml.encode("utf-8")
        touched.append(rels_part)

        sheet_xml = parts[sheet_part].decode("utf-8")
        root = _start_tag(sheet_xml, "worksheet")
        if 'xmlns:r="' not in root.group(0):
            sheet_xml = (
                sheet_xml[: root.start()]
                + _set_attr(root.group(0), "xmlns:r", _REL_NS)
                + sheet_xml[root.end() :]
            )
        sheet_xml = _insert_before_first(
            sheet_xml, _AFTER_LEGACY_DRAWING, "</worksheet>", f'<legacyDrawing r:id="{vml_id}"/>'
        )
        parts[sheet_part] = sheet_xml.encode("utf-8")

        comments_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<comments xmlns="{_MAIN_NS}"><authors><author>{NOTE_AUTHOR}</author></authors>'
            "<commentList></commentList></comments>"
        )
        drawings = [n for n in names if n.startswith("xl/drawings/vmlDrawing")]
        vml_xml = _NEW_VML.format(idmap=len(drawings) + 1)
        content_types = parts["[Content_Types].xml"].decode("utf-8")
        if 'Extension="vml"' not in content_types:
            content_types = content_types.replace(
                "<Override", f'<Default Extension="vml" ContentType="{_CT_VML}"/><Override', 1
            )
        content_types = content_types.replace(
            "</Types>",
            f'<Override PartName="/{comments_part}" ContentType="{_CT_COMMENTS}"/></Types>',
        )
        parts["[Content_Types].xml"] = content_types.encode("utf-8")
        touched.append("[Content_Types].xml")

    authors = re.findall(r"<author>(.*?)</author>|<author/>", comments_xml)
    if NOTE_AUTHOR in authors:
        author_id = authors.index(NOTE_AUTHOR)
    else:
        author_id = len(authors)
        if "<authors/>" in comments_xml:
            comments_xml = comments_xml.replace(
                "<authors/>", f"<authors><author>{NOTE_AUTHOR}</author></authors>"
            )
        else:
            comments_xml = comments_xml.replace(
                "</authors>", f"<author>{NOTE_AUTHOR}</author></authors>"
            )

    shape_ids = [int(n) for n in re.findall(r'id="_x0000_s(\d+)"', vml_xml)]
    next_shape = max(shape_ids, default=1024) + 1
    new_shapes: list[str] = []
    for edit in edits:
        existing = re.search(
            rf'<comment\b[^>]*\sref="{edit.ref}"[^>]*>.*?</comment>', comments_xml, re.S
        )
        if existing is not None:
            # Excel holds one note per cell: keep the existing note, add ours below.
            addition = (
                f'<r><t xml:space="preserve">{escape(chr(10) + _clean_text(edit.note))}</t></r>'
            )
            merged = existing.group(0).replace("</text>", addition + "</text>", 1)
            comments_xml = (
                comments_xml[: existing.start()] + merged + comments_xml[existing.end() :]
            )
            continue
        comment = _comment_xml(edit.ref, author_id, edit.note)
        if "<commentList/>" in comments_xml:
            comments_xml = comments_xml.replace(
                "<commentList/>", f"<commentList>{comment}</commentList>"
            )
        else:
            comments_xml = comments_xml.replace("</commentList>", comment + "</commentList>")
        new_shapes.append(_vml_shape(next_shape, edit.row - 1, column_index(edit.column)))
        next_shape += 1

    if new_shapes:
        if "</xml>" not in vml_xml:
            raise WorkbookPatchError(f"{vml_part}: unexpected VML shape")
        vml_xml = vml_xml.replace("</xml>", "".join(new_shapes) + "</xml>")

    parts[comments_part] = comments_xml.encode("utf-8")
    parts[vml_part] = vml_xml.encode("utf-8")
    touched += [comments_part, vml_part]
    return touched


# ---------------------------------------------------------------------------
# On-open flags
# ---------------------------------------------------------------------------


def _recalculate_on_open(workbook_xml: str) -> str:
    calc = re.search(r"<calcPr\b[^>]*?/?>", workbook_xml)
    if calc is not None:
        return (
            workbook_xml[: calc.start()]
            + _set_attr(calc.group(0), "fullCalcOnLoad", "1")
            + workbook_xml[calc.end() :]
        )
    return _insert_before_first(
        workbook_xml, _AFTER_CALC_PR, "</workbook>", '<calcPr fullCalcOnLoad="1"/>'
    )


def _refresh_pivot_on_open(definition_xml: str) -> str:
    root = _start_tag(definition_xml, "pivotCacheDefinition")
    return (
        definition_xml[: root.start()]
        + _set_attr(root.group(0), "refreshOnLoad", "1")
        + definition_xml[root.end() :]
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def patch_workbook(
    source: Path,
    destination: Path,
    *,
    sheet_name: str,
    edits: Sequence[CellEdit],
    max_edited_part_bytes: int = MAX_EDITED_PART_BYTES,
) -> PatchResult:
    """Write ``edits`` into a copy of ``source`` at ``destination``.

    Every ZIP entry not listed in ``PatchResult.touched_parts`` is copied
    byte-for-byte (after decompression), in its original order, streamed in
    chunks. Only the small parts the patch rewrites and the edited worksheet
    are read whole; a worksheet larger than ``max_edited_part_bytes``
    (uncompressed) is refused rather than loaded.
    """

    refs = [edit.ref for edit in edits]
    if len(set(refs)) != len(refs):
        raise WorkbookPatchError("two edits target the same cell")

    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        sheet = _sheet_part(
            workbook_xml, archive.read("xl/_rels/workbook.xml.rels").decode("utf-8"), sheet_name
        )
        if sheet not in names:
            raise WorkbookPatchError(f"worksheet part {sheet} is missing")
        sheet_size = archive.getinfo(sheet).file_size
        if sheet_size > max_edited_part_bytes:
            raise WorkbookPatchError(
                f"worksheet part {sheet} is {sheet_size} bytes, larger than the "
                f"{max_edited_part_bytes}-byte limit for an edited sheet"
            )

        wanted = {"[Content_Types].xml", "xl/styles.xml", sheet, _rels_path(sheet)}
        wanted |= {name for name in names if _PIVOT_CACHE_DEFINITION.match(name)}
        parts = {name: archive.read(name) for name in wanted if name in names}
        for rel in _relationships(parts.get(_rels_path(sheet), b"").decode("utf-8")):
            if rel.get("Type") in (_REL_TYPE_COMMENTS, _REL_TYPE_VML):
                target = _resolve_target(sheet.rpartition("/")[0], rel["Target"])
                parts[target] = archive.read(target)

        date1904 = bool(re.search(r'<workbookPr\b[^>]*\sdate1904="(?:1|true)"', workbook_xml))
        styles = _Styles.parse(parts["xl/styles.xml"].decode("utf-8"))
        sheet_xml, written, skipped = _patch_cells(
            parts[sheet].decode("utf-8"), edits, styles, date1904=date1904
        )

        touched: list[str] = []
        if written:
            parts[sheet] = sheet_xml.encode("utf-8")
            parts["xl/styles.xml"] = styles.xml.encode("utf-8")
            touched += [sheet, "xl/styles.xml"]
            touched += _add_notes(parts, names, sheet, written)
        parts["xl/workbook.xml"] = _recalculate_on_open(workbook_xml).encode("utf-8")
        touched.append("xl/workbook.xml")
        for name in sorted(names):
            if _PIVOT_CACHE_DEFINITION.match(name):
                parts[name] = _refresh_pivot_on_open(parts[name].decode("utf-8")).encode("utf-8")
                touched.append(name)

        touched_set = set(touched)
        for name in touched_set:
            _assert_well_formed(name, parts[name])

        with zipfile.ZipFile(destination, "w") as output:
            for info in archive.infolist():
                copy = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                copy.compress_type = info.compress_type
                copy.external_attr = info.external_attr
                if info.filename in touched_set:
                    output.writestr(copy, parts[info.filename])
                    continue
                copy.file_size = info.file_size  # lets zipfile pick ZIP64 only when needed
                with archive.open(info) as reader, output.open(copy, "w") as writer:
                    shutil.copyfileobj(reader, writer, _COPY_CHUNK)
            for name in sorted(touched_set - names):
                output.writestr(
                    zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)),
                    parts[name],
                    compress_type=zipfile.ZIP_DEFLATED,
                )

    return PatchResult(
        written=tuple(written), skipped=tuple(skipped), touched_parts=tuple(sorted(touched_set))
    )
