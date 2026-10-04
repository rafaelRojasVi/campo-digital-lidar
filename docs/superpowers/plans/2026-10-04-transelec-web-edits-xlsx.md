# Transelec web edits and «web» planilla download — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Operators and admins edit 11 status/ingreso fields of the published Transelec version in the dashboard. Every view shows the edited value with a «web» chip. They can download the uploaded planilla with only those cells changed, each highlighted and carrying a note.

**Architecture:** Migration `0012` adds:
- the `platform.transelec_field_override` table;
- one SQL comparison function;
- three views. `transelec_keyed_row` adds the row key ordinal. `transelec_override_state` gives each active edit's status against every import. `transelec_effective_row` gives the source rows with applied edits.

Every Transelec read selects from `transelec_effective_row` instead of `transelec_resumen_row`, so filters, search, paging, every product module and the CSV see edits unchanged. A new router `app/routers/transelec_edits.py` saves, discards, keeps and lists edits, and serves `GET /transelec/export.xlsx`. The download is built by the stdlib-only patcher `transelec_ingestion/xlsx_web_patch.py`, which streams every ZIP part through unchanged and rewrites only the edited cells, styles, notes and the "on open" flags. On the dashboard, the row drawer gets an editing section, Datos gets an «Ediciones web» pane and Calidad gets a conflicts block.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core (text SQL), Alembic, PostgreSQL/PostGIS 17, the Python standard library (`zipfile`, `re`, `xml.parsers.expat`), React 19 + TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md`. Sibling specs, merged first: `docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md` and `docs/superpowers/specs/2026-10-04-transelec-plazo-90-habiles-design.md`.

## Global Constraints

- Editable fields are exactly these 11:
  - text: `estado`, `estado_resumido`, `tipo_rechazo`, `reingreso_tec`, `reingreso_legal`, `reingreso_recrep`, `numero_ingreso`, `numero_ingreso_2`;
  - date: `fecha_ingreso`, `fecha_ingreso_2`, `fecha_90_dias`.
- Never editable: `pmf`, `rol`, `numero_predio`, `numero_area_corta`, `id_predio_unico`, `id_predio_unico_ii`, `id_pmf`, `hoy`.
- Who:
  - edit and download (`Action.EDIT`): OPERATOR and ADMIN;
  - list edits (`Action.VIEW`): VIEWER and above.
- Row key: `pmf` + `rol` + `numero_predio` + `numero_area_corta` + `key_ordinal`. `key_ordinal` is the row's 1-based position among rows of the same import sharing the four-part key, ordered by `source_row_number`.
- Text comparison: trim, collapse runs of ASCII whitespace `[ \t\r\n\f\v]` to one space, blank becomes NULL, case-sensitive. Dates compare as dates. A date cell that held unparsed text compares by that text.
- Status against the active version, in this order:
  1. `huerfana`: no matching row.
  2. `aplicada`: the cell equals the planilla value seen at edit time.
  3. `incorporada`: the cell equals the web value.
  4. `en_conflicto`: anything else. The planilla wins.
- Activation (publish or restore) ends every `incorporada` edit in the same transaction, with `end_reason = 'incorporated'`.
- 409 bodies are `{"detail": <Spanish>, "code": "version_changed" | "value_changed" | "not_in_conflict"}`.
- Download marking:
  - fill `FFFFF2CC`;
  - one Excel note per cell, author `web`, text `web · <display name> · <dd-mm-aaaa> · antes: <planilla value or (vacía)>`;
  - `fullCalcOnLoad="1"` on `calcPr` and `refreshOnLoad="1"` on every `xl/pivotCache/pivotCacheDefinitionN.xml`.
- Download filename: `<original stem>_web_<YYYY-MM-DD>.xlsx`, with the date in `America/Santiago` computed by PostgreSQL.
- The patcher uses the standard library only and makes text-level XML edits. It never re-serializes a part with an XML library.
- Migration revision `0012`, `down_revision = "0011"`. Only this PR adds a migration (ADR-003).
- Audit metadata carries field names, ids and counts. It never carries cell values (`app/audit.py` contract).
- Client-facing copy is Spanish. Engineering docs are English (`docs/DOCUMENTATION_POLICY.md`).
- Synthetic fixtures only. Never copy a planilla into the repository, and never put a planilla value in code, tests, commits or docs (`.claude/skills/transelec-workbook/SKILL.md`).
- Python checks, as CI runs them: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy .`, `uv run pytest`.
- Integration tests run against the disposable test DB (port 5433). Prefix every integration command with:
  `APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api`
- Dashboard checks (in `products/transelect/dashboard`): `npm test`, `npm run lint`, `npx tsc -b`, `npm run build`, `npm run test:e2e`.

## Review Focus

These five inputs are implied by the spec but easy to miss. Each one's test is pinned in the task named:

1. **Whitespace and case.** A planilla value «En tramite » next to a web value «En tramite» is the same value. «aprobado» against «Aprobado» is a different value. Python and SQL must agree on both, including NBSP, which is not trimmed by either. Tests: Task 1 (`test_normalize_text_*`) and Task 3 (`test_sql_and_python_text_rules_agree`).
2. **A date cell that held text («12 de marzo de 2026 y 4 de mayo de 2026»).** It is edited to a real date. If the next planilla still holds the same text, the edit stays `aplicada`, not `en_conflicto`. Test: Task 5 (`test_date_edit_over_raw_text_survives_an_unchanged_republish`).
3. **Rows sharing PMF + Rol + N Predio + N Área de Corta (2 groups in the real planilla).** An edit lands on exactly the chosen row. Test: Task 5 (`test_edit_hits_only_the_chosen_row_of_a_shared_key`).
4. **Editing a field the published planilla has no column for.** For example, the 09-Sept layout has no «…2» columns. The edit is refused with 422, because it could never be downloaded. Tests: Task 5 (`test_field_without_a_source_column_is_not_editable`) and Task 9 (drawer hides *Editar* for it).
5. **Downloading while some edits are in conflict or orphaned.** The download still succeeds and writes only `aplicada` edits. The pane says how many are not written. Tests: Task 7 (`test_export_writes_only_applied_edits`) and Task 10 (`EdicionesPage` note).

---

## File Structure

| Path | Responsibility |
|---|---|
| `products/transelect/src/transelec_ingestion/field_overrides.py` (create) | Editable-field registry, value parsing, the comparison rule (`normalize_text`, signatures), note text. Pure. |
| `products/transelect/src/transelec_ingestion/xlsx_web_patch.py` (create) | Writes cell edits plus «web» marks into a copy of an uploaded `.xlsx`. Standard library only. |
| `migrations/versions/0012_establish_transelec_field_overrides.py` (create) | Table, `transelec_norm_text`, the three views. |
| `apps/api/app/access.py` (modify) | `Action.EDIT` for OPERATOR and ADMIN. |
| `apps/api/app/transelec_overrides.py` (create) | Persistence: save, discard, keep, list, retire on activation. SQL only, inside the caller's transaction. |
| `apps/api/app/routers/transelec.py` (modify) | Reads from `transelec_effective_row`; `ResumenRowView.web_fields`; activation retires incorporated edits. |
| `apps/api/app/routers/transelec_edits.py` (create) | `PUT/DELETE/POST keep/GET /transelec/overrides`, `GET /transelec/export.xlsx`. |
| `apps/api/app/main.py` (modify) | Mount the new router at both prefixes; add the `transelec/ediciones` SPA path. |
| `apps/api/tests/test_access.py`, `apps/api/tests/test_transelec_override_migration.py` | RBAC matrix; migration field lists agree with the registry. |
| `products/transelect/tests/test_field_overrides.py`, `products/transelect/tests/test_xlsx_web_patch.py` | Pure unit tests. |
| `apps/api/integration_tests/test_transelec_overrides.py` (create) | View, routes, activation and export against real PostgreSQL. |
| `apps/api/integration_tests/test_transelec_reads_router.py`, `test_transelec_router.py` (modify) | Cleanup lists delete overrides first. |
| `products/transelect/dashboard/src/api.ts` (modify) | Types and client functions for edits and download; `canEdit`. |
| `products/transelect/dashboard/src/lib/webEdits.ts` (create) | Front-end field list, labels, tooltips, suggestions cache. |
| `products/transelect/dashboard/src/components/WebChip.tsx`, `EditableFieldsSection.tsx`, `WebEditConflicts.tsx` (create) | Chip, drawer editing block, Calidad block. |
| `products/transelect/dashboard/src/pages/EdicionesPage.tsx` (create) | Datos → «Ediciones web» pane plus the download. |
| `RowDetailDrawer.tsx`, `RowsTable.tsx`, `ExploradorPage.tsx`, `DatosPage.tsx`, `CalidadPage.tsx`, `App.tsx`, `router.tsx`, `styles/components.css` (modify) | Wiring. |
| `products/transelect/dashboard/tests/e2e/stubs.ts` (modify), `tests/e2e/web-edits.spec.ts` (create) | E2E. |
| `products/transelect/README.md` (modify) | Routes table. |

---

### Task 0: Worktree and green baseline

**Files:** none changed.

**Interfaces:**
- Consumes: nothing.
- Produces: worktree `worktrees/campo-digital-transelec-web-edits` on branch `feat/transelec-web-edits`.

- [ ] **Step 1: Create the worktree** (workspace `CLAUDE.md`)

```bash
cd /home/rafael/dev/freelance/campo-digital
git -C campo-digital-platform fetch origin
git -C campo-digital-platform worktree add ../worktrees/campo-digital-transelec-web-edits -b feat/transelec-web-edits origin/main
cd worktrees/campo-digital-transelec-web-edits
```

- [ ] **Step 2: Install and run the baseline**

```bash
uv sync --all-extras --dev
uv run pytest -q
(cd products/transelect/dashboard && npm ci && npm test && npm run lint)
```

Expected: everything passes. If not, stop and report: the baseline must be green before any change.

- [ ] **Step 3: Prepare the disposable test database**

```bash
docker ps --format '{{.Names}} {{.Ports}}' | grep 5433 || true
```

If a container that is not `*postgres-test*` holds port 5433 (on 2026-10-04 that was `heavy-ops-slice-14-v1-db-test-1`), **ask Rafael before stopping it**: it belongs to another project. Then run:

```bash
make migration-check
```

Expected: ends with the re-upgrade to head succeeding. It resets the test DB, never the dev DB.

---

### Task 1: Field registry and comparison rule

**Files:**
- Create: `products/transelect/src/transelec_ingestion/field_overrides.py`
- Test: `products/transelect/tests/test_field_overrides.py`

**Interfaces:**
- Consumes: `transelec_ingestion.resumen_layout.FIELD_BY_NAME` (name → `FieldSpec(name, header, tier, kind, aliases)`).
- Produces:
  - `EditableKind = Literal["text", "date"]`
  - `Signature = tuple[str | None, dt.date | None]`
  - `MAX_TEXT_LENGTH = 500`
  - `@dataclass(frozen=True, slots=True) class EditableField(name: str, kind: EditableKind, label: str)`
  - `EDITABLE_FIELDS: tuple[EditableField, ...]`, `EDITABLE_BY_NAME: dict[str, EditableField]`
  - `class OverrideValueError(ValueError)` (Spanish message)
  - `normalize_text(value: str | None) -> str | None`
  - `parse_value(field, raw: str | None) -> str | dt.date | None` (raises `OverrideValueError`)
  - `comparable(field, raw: str | None) -> str | dt.date | None` (what an editor saw; raises `OverrideValueError` on a malformed date)
  - `shown_value(field, value: Any) -> str | dt.date | None` (a DB value in comparable form)
  - `value_signature(field, value: str | dt.date | None) -> Signature`
  - `cell_signature(field, *, value: Any, text_dates: Mapping[str, Any] | None) -> Signature`
  - `display(signature: Signature) -> str | None` (ISO date or text)
  - `note_text(*, author: str, edited_on: dt.date, planilla: Signature) -> str`

- [ ] **Step 1: Write the failing tests**

```python
"""The web-edit field registry and its comparison rule (spec §2)."""

from __future__ import annotations

import datetime as dt

import pytest

from transelec_ingestion.field_overrides import (
    EDITABLE_BY_NAME,
    EDITABLE_FIELDS,
    MAX_TEXT_LENGTH,
    OverrideValueError,
    cell_signature,
    comparable,
    display,
    note_text,
    normalize_text,
    parse_value,
    shown_value,
    value_signature,
)
from transelec_ingestion.resumen_layout import FIELD_BY_NAME

TEXT = EDITABLE_BY_NAME["estado_resumido"]
DATE = EDITABLE_BY_NAME["fecha_ingreso"]


def test_registry_is_the_eleven_fields_of_the_spec() -> None:
    assert [field.name for field in EDITABLE_FIELDS] == [
        "estado",
        "estado_resumido",
        "tipo_rechazo",
        "reingreso_tec",
        "reingreso_legal",
        "reingreso_recrep",
        "fecha_ingreso",
        "numero_ingreso",
        "fecha_90_dias",
        "fecha_ingreso_2",
        "numero_ingreso_2",
    ]


def test_registry_kinds_and_labels_come_from_the_contract() -> None:
    for field in EDITABLE_FIELDS:
        assert field.kind == FIELD_BY_NAME[field.name].kind
        assert field.label == FIELD_BY_NAME[field.name].header


@pytest.mark.parametrize("name", ["pmf", "rol", "numero_predio", "numero_area_corta", "hoy"])
def test_identity_and_formula_fields_are_not_editable(name: str) -> None:
    assert name not in EDITABLE_BY_NAME


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("En tramite", "En tramite"),
        ("  En   tramite \t", "En tramite"),
        ("En\ntramite\r\n", "En tramite"),
        ("", None),
        (" \t\n ", None),
        (None, None),
    ],
)
def test_normalize_text_trims_and_collapses_ascii_whitespace(
    raw: str | None, expected: str | None
) -> None:
    assert normalize_text(raw) == expected


def test_normalize_text_keeps_case_and_non_ascii_spaces() -> None:
    assert normalize_text("aprobado") != normalize_text("Aprobado")
    assert normalize_text("En tramite") == "En tramite"


def test_parse_value_reads_dates_and_text() -> None:
    assert parse_value(DATE, "2026-03-12") == dt.date(2026, 3, 12)
    assert parse_value(DATE, "") is None
    assert parse_value(TEXT, "  Aprobado ") == "Aprobado"
    assert parse_value(TEXT, None) is None


@pytest.mark.parametrize("raw", ["12-03-2026", "2026-02-30", "mañana"])
def test_parse_value_rejects_malformed_dates(raw: str) -> None:
    with pytest.raises(OverrideValueError):
        parse_value(DATE, raw)


def test_parse_value_rejects_control_characters_and_long_text() -> None:
    with pytest.raises(OverrideValueError):
        parse_value(TEXT, "Apro\x00bado")
    with pytest.raises(OverrideValueError):
        parse_value(TEXT, "x" * (MAX_TEXT_LENGTH + 1))


def test_comparable_and_shown_value_meet_in_the_middle() -> None:
    assert comparable(DATE, "2026-03-12") == shown_value(DATE, dt.date(2026, 3, 12))
    assert comparable(DATE, None) == shown_value(DATE, None)
    assert comparable(TEXT, " En tramite ") == shown_value(TEXT, "En tramite")


def test_cell_signature_uses_raw_text_when_a_date_cell_held_text() -> None:
    evidence = {"fecha_ingreso": {"raw": " 12 de marzo y 4 de mayo ", "parsed": None}}
    assert cell_signature(DATE, value=None, text_dates=evidence) == ("12 de marzo y 4 de mayo", None)
    assert cell_signature(DATE, value=dt.date(2026, 3, 12), text_dates=evidence) == (
        None,
        dt.date(2026, 3, 12),
    )
    assert cell_signature(DATE, value=None, text_dates=None) == (None, None)
    assert cell_signature(TEXT, value=" Aprobado", text_dates=None) == ("Aprobado", None)


def test_value_signature_matches_cell_signature_of_the_same_value() -> None:
    assert value_signature(TEXT, "Aprobado") == cell_signature(TEXT, value="Aprobado", text_dates={})
    assert value_signature(DATE, dt.date(2026, 1, 2)) == (None, dt.date(2026, 1, 2))
    assert value_signature(DATE, None) == (None, None)


def test_display_and_note_text() -> None:
    assert display((None, dt.date(2026, 1, 2))) == "2026-01-02"
    assert display(("Aprobado", None)) == "Aprobado"
    assert display((None, None)) is None
    assert (
        note_text(author="Ana Pérez", edited_on=dt.date(2026, 10, 4), planilla=("Rechazado", None))
        == "web · Ana Pérez · 04-10-2026 · antes: Rechazado"
    )
    assert note_text(
        author="Ana", edited_on=dt.date(2026, 10, 4), planilla=(None, dt.date(2026, 1, 5))
    ).endswith("antes: 05-01-2026")
    assert note_text(author="Ana", edited_on=dt.date(2026, 10, 4), planilla=(None, None)).endswith(
        "antes: (vacía)"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest products/transelect/tests/test_field_overrides.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'transelec_ingestion.field_overrides'`

- [ ] **Step 3: Write the implementation**

```python
"""Which ``Resumen`` fields a dashboard user may edit, and the one rule for
comparing an edited value with the planilla's cell.

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
("Editable fields", §2). ``platform.transelec_norm_text`` (migration 0012)
is ``normalize_text`` in SQL; the two must stay identical, and
``apps/api/integration_tests/test_transelec_overrides.py`` checks they agree.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from transelec_ingestion.resumen_layout import FIELD_BY_NAME

EditableKind = Literal["text", "date"]

# A planilla cell as the comparison sees it: (text, date). A filled cell sets
# exactly one side; a blank cell sets neither. A date cell that held text the
# importer could not read as one date compares by that text.
Signature = tuple[str | None, dt.date | None]

MAX_TEXT_LENGTH = 500

_ASCII_SPACE = " \t\r\n\f\v"
_SPACE_RUN = re.compile(r"[ \t\r\n\f\v]+")
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Spec order of the 30-Sept-2026 layout. Identity fields (PMF, Rol, N Predio,
# ID_Predo_Unico) and the formula column "Hoy" are never editable.
_EDITABLE_NAMES: tuple[str, ...] = (
    "estado",
    "estado_resumido",
    "tipo_rechazo",
    "reingreso_tec",
    "reingreso_legal",
    "reingreso_recrep",
    "fecha_ingreso",
    "numero_ingreso",
    "fecha_90_dias",
    "fecha_ingreso_2",
    "numero_ingreso_2",
)


@dataclass(frozen=True, slots=True)
class EditableField:
    """One editable field: its contract name, its kind and its source header."""

    name: str
    kind: EditableKind
    label: str


def _editable(name: str) -> EditableField:
    spec = FIELD_BY_NAME[name]
    if spec.kind not in ("text", "date"):  # pragma: no cover - a contract change must break loudly
        raise RuntimeError(f"{name} is a {spec.kind} field; web edits support text and date only")
    return EditableField(name=name, kind=cast(EditableKind, spec.kind), label=spec.header)


EDITABLE_FIELDS: tuple[EditableField, ...] = tuple(_editable(name) for name in _EDITABLE_NAMES)
EDITABLE_BY_NAME: dict[str, EditableField] = {field.name: field for field in EDITABLE_FIELDS}


class OverrideValueError(ValueError):
    """A submitted value cannot be stored. The message is shown to the user."""


def normalize_text(value: str | None) -> str | None:
    """Trim and collapse ASCII whitespace; blank is None. Case is kept."""

    if value is None:
        return None
    collapsed = _SPACE_RUN.sub(" ", value.strip(_ASCII_SPACE))
    return collapsed or None


def _parse_date(raw: str) -> dt.date:
    text = raw.strip(_ASCII_SPACE)
    if not _ISO_DATE.match(text):
        raise OverrideValueError("La fecha debe tener el formato AAAA-MM-DD.")
    try:
        return dt.date.fromisoformat(text)
    except ValueError as exc:
        raise OverrideValueError("La fecha no existe en el calendario.") from exc


def parse_value(field: EditableField, raw: str | None) -> str | dt.date | None:
    """A submitted value as it will be stored. Blank means "clear the cell"."""

    if raw is None or not raw.strip(_ASCII_SPACE):
        return None
    if field.kind == "date":
        return _parse_date(raw)
    if _CONTROL.search(raw):
        raise OverrideValueError("El texto contiene caracteres no permitidos.")
    text = normalize_text(raw)
    if text is not None and len(text) > MAX_TEXT_LENGTH:
        raise OverrideValueError(f"El texto no puede superar {MAX_TEXT_LENGTH} caracteres.")
    return text


def comparable(field: EditableField, raw: str | None) -> str | dt.date | None:
    """What an editor saw (``expected_value``), ready to compare with ``shown_value``."""

    if raw is None or not raw.strip(_ASCII_SPACE):
        return None
    if field.kind == "date":
        return _parse_date(raw)
    return normalize_text(raw)


def shown_value(field: EditableField, value: Any) -> str | dt.date | None:
    """A value read from ``transelec_effective_row``, in ``comparable`` form."""

    if value is None:
        return None
    if field.kind == "date":
        return cast(dt.date, value)
    return normalize_text(str(value))


def value_signature(field: EditableField, value: str | dt.date | None) -> Signature:
    if field.kind == "date":
        return (None, cast("dt.date | None", value))
    return (normalize_text(cast("str | None", value)), None)


def cell_signature(
    field: EditableField, *, value: Any, text_dates: Mapping[str, Any] | None
) -> Signature:
    """A stored cell (value plus ``source_text_dates``) as a ``Signature``."""

    if field.kind == "date":
        if value is not None:
            return (None, cast(dt.date, value))
        evidence = (text_dates or {}).get(field.name) or {}
        return (normalize_text(evidence.get("raw")), None)
    return (normalize_text(None if value is None else str(value)), None)


def display(signature: Signature) -> str | None:
    """A signature as the API shows it: an ISO date, the text, or None."""

    text, date = signature
    return date.isoformat() if date is not None else text


def note_text(*, author: str, edited_on: dt.date, planilla: Signature) -> str:
    """The Excel note written next to an edited cell (spec §5)."""

    text, date = planilla
    before = date.strftime("%d-%m-%Y") if date is not None else (text or "(vacía)")
    return f"web · {author} · {edited_on:%d-%m-%Y} · antes: {before}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest products/transelect/tests/test_field_overrides.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Lint, type-check and commit**

```bash
uv run ruff check --fix products/transelect && uv run ruff format products/transelect && uv run mypy products/transelect
git add products/transelect/src/transelec_ingestion/field_overrides.py products/transelect/tests/test_field_overrides.py
git commit -m "feat(transelec): registry and comparison rule for web edits"
```

---

### Task 2: Migration 0012 — override table, comparison function, three views

**Files:**
- Create: `migrations/versions/0012_establish_transelec_field_overrides.py`
- Create: `apps/api/tests/test_transelec_override_migration.py`

**Interfaces:**
- Consumes: `EDITABLE_FIELDS` (Task 1); `platform.transelec_resumen_row` columns at `0011`.
- Produces (SQL):
  - table `platform.transelec_field_override(id, pmf, rol, numero_predio, numero_area_corta, key_ordinal, field, value_text, value_date, planilla_value_text, planilla_value_date, base_import_id, created_by_app_user_id, created_at, ended_at, ended_by_app_user_id, end_reason)`;
  - function `platform.transelec_norm_text(text) -> text`;
  - view `platform.transelec_keyed_row` (every `transelec_resumen_row` column plus `key_ordinal`);
  - view `platform.transelec_override_state(import_id, override_id, field, source_row_number, source_text, source_date, status)`;
  - view `platform.transelec_effective_row(import_id, source_row_number, key_ordinal, <every contract column>, predio_group_key, source_text_dates, web_fields text[])`.

The SQL below was run against the real local PostGIS 17 database on 2026-10-04 inside a rolled-back transaction. With no edits, the view equalled the source rows exactly. An applied edit was visible to an `= ANY()` filter. The conflict, orphan and raw-text-date cases behaved as specified.

- [ ] **Step 1: Write the failing test** (`apps/api/tests/test_transelec_override_migration.py`)

```python
"""Migration 0012 freezes the editable field lists; they must equal the registry."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from transelec_ingestion.field_overrides import EDITABLE_FIELDS
from transelec_ingestion.import_projection import RESUMEN_ROW_PROJECTION

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "versions"
    / "0012_establish_transelec_field_overrides.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MIGRATION.stem, _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_field_lists_equal_the_registry() -> None:
    migration = _load()
    assert set(migration.TEXT_FIELDS) == {f.name for f in EDITABLE_FIELDS if f.kind == "text"}
    assert set(migration.DATE_FIELDS) == {f.name for f in EDITABLE_FIELDS if f.kind == "date"}


def test_migration_row_columns_equal_the_projection() -> None:
    migration = _load()
    assert migration.ROW_COLUMNS == tuple(spec.column for spec in RESUMEN_ROW_PROJECTION)


def test_migration_follows_0011() -> None:
    migration = _load()
    assert (migration.revision, migration.down_revision) == ("0012", "0011")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest apps/api/tests/test_transelec_override_migration.py -v`
Expected: FAIL. `spec_from_file_location` gets a missing file, so loading the module raises `FileNotFoundError`.

- [ ] **Step 3: Write the migration** (`migrations/versions/0012_establish_transelec_field_overrides.py`)

```python
"""Establish Transelec field overrides (web edits) and the effective-row view.

Revision ID: 0012
Revises: 0011

Expand-only. Spec:
docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md.

- ``platform.transelec_field_override``: one row per web edit of one cell
  of one source row, keyed by the row's business key (PMF, Rol, N Predio,
  N Area de Corta) plus ``key_ordinal`` — the row's 1-based position among
  rows of the same import sharing that key, by ``source_row_number``.
  Rows are never deleted; an edit ends (``ended_at``/``end_reason``) and
  history stays. At most one active edit per cell (partial unique index).
- ``platform.transelec_norm_text(text)``: the one text comparison rule
  (trim, collapse ASCII whitespace, blank → NULL). Mirrored exactly by
  ``transelec_ingestion.field_overrides.normalize_text``.
- ``platform.transelec_keyed_row``: every source row with its ``key_ordinal``.
- ``platform.transelec_override_state``: every active edit against every
  import — ``aplicada``, ``incorporada``, ``en_conflicto`` or ``huerfana``.
- ``platform.transelec_effective_row``: every source row with its applied
  edits — the relation every Transelec read selects from. Same column names
  as ``transelec_resumen_row`` plus ``key_ordinal`` and ``web_fields``.

The field lists below are frozen at this revision on purpose: a migration
must not import application code. ``apps/api/tests/
test_transelec_override_migration.py`` asserts they still equal the
registry and the projection. A later contract column must be added to
``transelec_effective_row`` by a new migration that recreates the views
(``test_transelec_overrides.py`` checks the view exposes every column the
router selects).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEXT_FIELDS: tuple[str, ...] = (
    "estado",
    "estado_resumido",
    "tipo_rechazo",
    "reingreso_tec",
    "reingreso_legal",
    "reingreso_recrep",
    "numero_ingreso",
    "numero_ingreso_2",
)
DATE_FIELDS: tuple[str, ...] = ("fecha_ingreso", "fecha_ingreso_2", "fecha_90_dias")
EDITABLE: tuple[str, ...] = TEXT_FIELDS + DATE_FIELDS

# transelec_resumen_row's contract columns at revision 0011, in contract order.
ROW_COLUMNS: tuple[str, ...] = (
    "aef",
    "quien_solicita",
    "fecha_solicitud",
    "fecha_corta",
    "fecha_termino",
    "predio_ref",
    "rol_ref",
    "area_ref",
    "pmf",
    "carpeta_source",
    "pas",
    "estado",
    "estado_resumido",
    "tipo_rechazo",
    "reingreso_tec",
    "reingreso_legal",
    "reingreso_recrep",
    "tipo_propietario",
    "id_transelec",
    "rol",
    "numero_predio",
    "numero_area_corta",
    "superficie_corta",
    "superficie_total_corta",
    "fecha_ingreso",
    "numero_ingreso",
    "fecha_90_dias",
    "hoy_raw",
    "fecha_ingreso_2",
    "numero_ingreso_2",
    "empresa",
    "id_predio_unico_ii",
    "id_pmf",
    "id_predio_unico",
    "tramite",
    "carpeta_normalizada",
    "sector",
)


def _quoted(names: Sequence[str]) -> str:
    return ", ".join(f"'{name}'" for name in names)


# E'\x0B' is vertical tab: PostgreSQL E-strings have no \v escape.
_NORM_TEXT = r"""
CREATE FUNCTION platform.transelec_norm_text(value text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT NULLIF(
        regexp_replace(btrim(value, E' \t\r\n\f\x0B'), E'[ \t\r\n\f\x0B]+', ' ', 'g'),
        ''
    )
$$
"""

_KEYED_ROW = """
CREATE VIEW platform.transelec_keyed_row AS
SELECT
    r.*,
    row_number() OVER (
        PARTITION BY r.import_id, r.pmf, r.rol, r.numero_predio, r.numero_area_corta
        ORDER BY r.source_row_number
    ) AS key_ordinal
FROM platform.transelec_resumen_row AS r
"""


def _override_state_sql() -> str:
    text_cases = "\n".join(f"                WHEN '{name}' THEN k.{name}" for name in TEXT_FIELDS)
    date_cases = "\n".join(f"            WHEN '{name}' THEN k.{name}" for name in DATE_FIELDS)
    return f"""
CREATE VIEW platform.transelec_override_state AS
SELECT
    i.id AS import_id,
    o.id AS override_id,
    o.field,
    k.source_row_number,
    s.source_text,
    s.source_date,
    CASE
        WHEN k.source_row_number IS NULL THEN 'huerfana'
        WHEN (s.source_text, s.source_date) IS NOT DISTINCT FROM
             (platform.transelec_norm_text(o.planilla_value_text), o.planilla_value_date)
            THEN 'aplicada'
        WHEN (s.source_text, s.source_date) IS NOT DISTINCT FROM
             (platform.transelec_norm_text(o.value_text), o.value_date)
            THEN 'incorporada'
        ELSE 'en_conflicto'
    END AS status
FROM platform.transelec_field_override AS o
CROSS JOIN platform.transelec_import AS i
LEFT JOIN platform.transelec_keyed_row AS k
    ON k.import_id = i.id
    AND k.pmf = o.pmf
    AND k.rol IS NOT DISTINCT FROM o.rol
    AND k.numero_predio IS NOT DISTINCT FROM o.numero_predio
    AND k.numero_area_corta IS NOT DISTINCT FROM o.numero_area_corta
    AND k.key_ordinal = o.key_ordinal
LEFT JOIN LATERAL (
    SELECT
        CASE
            WHEN o.field IN ({_quoted(DATE_FIELDS)}) THEN
                CASE WHEN d.value IS NULL
                    THEN platform.transelec_norm_text(k.source_text_dates -> o.field ->> 'raw')
                END
            ELSE platform.transelec_norm_text(CASE o.field
{text_cases}
            END)
        END AS source_text,
        d.value AS source_date
    FROM (
        SELECT CASE o.field
{date_cases}
        END AS value
    ) AS d
) AS s ON true
WHERE o.ended_at IS NULL
"""


def _effective_row_sql() -> str:
    aggregates = [
        "array_agg(s.field ORDER BY s.field) AS web_fields",
        "array_agg(s.field ORDER BY s.field) FILTER "
        f"(WHERE s.field IN ({_quoted(DATE_FIELDS)})) AS web_date_fields",
    ]
    for name in TEXT_FIELDS:
        aggregates.append(f"bool_or(s.field = '{name}') AS has_{name}")
        aggregates.append(f"max(o.value_text) FILTER (WHERE s.field = '{name}') AS web_{name}")
    for name in DATE_FIELDS:
        aggregates.append(f"bool_or(s.field = '{name}') AS has_{name}")
        aggregates.append(f"max(o.value_date) FILTER (WHERE s.field = '{name}') AS web_{name}")

    columns = [
        f"CASE WHEN a.has_{name} THEN a.web_{name} ELSE k.{name} END AS {name}"
        if name in EDITABLE
        else f"k.{name}"
        for name in ROW_COLUMNS
    ]
    aggregate_sql = ",\n        ".join(aggregates)
    column_sql = ",\n    ".join(columns)
    return f"""
CREATE VIEW platform.transelec_effective_row AS
SELECT
    k.import_id,
    k.source_row_number,
    k.key_ordinal,
    {column_sql},
    k.predio_group_key,
    CASE
        WHEN a.web_date_fields IS NULL THEN k.source_text_dates
        ELSE NULLIF(k.source_text_dates - a.web_date_fields, '{{}}'::jsonb)
    END AS source_text_dates,
    COALESCE(a.web_fields, ARRAY[]::text[]) AS web_fields
FROM platform.transelec_keyed_row AS k
LEFT JOIN (
    SELECT
        s.import_id,
        s.source_row_number,
        {aggregate_sql}
    FROM platform.transelec_override_state AS s
    JOIN platform.transelec_field_override AS o ON o.id = s.override_id
    WHERE s.status = 'aplicada'
    GROUP BY s.import_id, s.source_row_number
) AS a
    ON a.import_id = k.import_id AND a.source_row_number = k.source_row_number
"""


def upgrade() -> None:
    """Create the override table, the comparison function and the three views."""

    op.create_table(
        "transelec_field_override",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("pmf", sa.Text(), nullable=False),
        sa.Column("rol", sa.Text(), nullable=True),
        sa.Column("numero_predio", sa.Text(), nullable=True),
        sa.Column("numero_area_corta", sa.Text(), nullable=True),
        sa.Column("key_ordinal", sa.Integer(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("planilla_value_text", sa.Text(), nullable=True),
        sa.Column("planilla_value_date", sa.Date(), nullable=True),
        sa.Column("base_import_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_app_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by_app_user_id", sa.BigInteger(), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_transelec_field_override"),
        sa.ForeignKeyConstraint(
            ["base_import_id"],
            ["platform.transelec_import.id"],
            name="fk_transelec_field_override_base_import",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_transelec_field_override_created_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_app_user_id"],
            ["platform.app_user.id"],
            name="fk_transelec_field_override_ended_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"field IN ({_quoted(EDITABLE)})", name="ck_transelec_field_override_field"
        ),
        sa.CheckConstraint(
            f"(field IN ({_quoted(DATE_FIELDS)}) AND value_text IS NULL) "
            f"OR (field NOT IN ({_quoted(DATE_FIELDS)}) AND value_date IS NULL "
            "AND planilla_value_date IS NULL)",
            name="ck_transelec_field_override_value_kind",
        ),
        sa.CheckConstraint("key_ordinal >= 1", name="ck_transelec_field_override_key_ordinal"),
        sa.CheckConstraint(
            "(ended_at IS NULL AND end_reason IS NULL) "
            "OR (ended_at IS NOT NULL AND end_reason IN "
            "('superseded', 'discarded', 'kept', 'incorporated'))",
            name="ck_transelec_field_override_end",
        ),
        schema="platform",
    )
    op.create_index(
        "uq_transelec_field_override_active_cell",
        "transelec_field_override",
        [
            "pmf",
            sa.text("coalesce(rol, '')"),
            sa.text("coalesce(numero_predio, '')"),
            sa.text("coalesce(numero_area_corta, '')"),
            "key_ordinal",
            "field",
        ],
        unique=True,
        schema="platform",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.execute(_NORM_TEXT)
    op.execute(_KEYED_ROW)
    op.execute(_override_state_sql())
    op.execute(_effective_row_sql())


def downgrade() -> None:
    """Drop the views, the function and the table; source rows are untouched."""

    op.execute("DROP VIEW platform.transelec_effective_row")
    op.execute("DROP VIEW platform.transelec_override_state")
    op.execute("DROP VIEW platform.transelec_keyed_row")
    op.execute("DROP FUNCTION platform.transelec_norm_text(text)")
    op.drop_index(
        "uq_transelec_field_override_active_cell",
        table_name="transelec_field_override",
        schema="platform",
    )
    op.drop_table("transelec_field_override", schema="platform")
```

- [ ] **Step 4: Run the unit tests, the migration graph and the migration lifecycle**

```bash
uv run pytest apps/api/tests/test_transelec_override_migration.py apps/api/tests/test_migration_graph.py -v
make migration-check
```

Expected:
- the unit tests PASS;
- `migration-check` prints the downgrade of the latest migration (`0012`) and the re-upgrade to head with no error.

- [ ] **Step 5: Commit**

```bash
uv run ruff check --fix migrations apps/api/tests && uv run ruff format migrations apps/api/tests
git add migrations/versions/0012_establish_transelec_field_overrides.py apps/api/tests/test_transelec_override_migration.py
git commit -m "feat(transelec): migration 0012 — field overrides and the effective-row view"
```

---

### Task 3: Every read goes through `transelec_effective_row`

**Files:**
- Modify: `apps/api/app/routers/transelec.py`:
  - `_RESUMEN_ROW_COLUMNS` (lines ~621-626);
  - the read-section comment (~605-613);
  - `_fetch_filtered_rows` FROM (~778);
  - `/pmfs` count and rows FROM (~1160, ~1176);
  - `/pmfs/{pmf}` FROM (~1221);
  - `ResumenRowView` (~824-882);
  - `_resumen_row_view` (~902-944).
- Modify: `apps/api/integration_tests/test_transelec_reads_router.py` cleanup tuple (~279) and `apps/api/integration_tests/test_transelec_router.py` cleanup tuple (~167).
- Create: `apps/api/integration_tests/test_transelec_overrides.py`

**Interfaces:**
- Consumes: the views from Task 2; `normalize_text` (Task 1).
- Produces:
  - `_RESUMEN_ROW_COLUMNS` now ends with `"web_fields"`;
  - `ResumenRowView.web_fields: list[str]` (default `[]`);
  - every row-returning route reads `platform.transelec_effective_row`;
  - test helpers in `test_transelec_overrides.py`: `client`, `_BASE_ROWS`, `_workbook`, `_publish`, `_rows`, `_row`, `_insert_override`. Later tasks extend this file.

- [ ] **Step 1: Write the failing integration tests** (`apps/api/integration_tests/test_transelec_overrides.py`)

```python
"""Transelec web edits (field overrides) end to end against real PostgreSQL.

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md.
Synthetic workbooks only, built with the reads-router test's own builders;
no planilla value appears here.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from app.access import Role
from app.deps import get_object_store
from app.main import app
from app.object_store import LocalObjectStore
from app.routers.transelec import _RESUMEN_ROW_COLUMNS
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_transelec_reads_router import (
    _SAME_ORIGIN,
    _ingestion_run_id,
    _login_with_grants,
    _source_row,
    _upload,
    _workbook_bytes,
)

from transelec_ingestion.field_overrides import normalize_text

ADMIN = (("transelect", Role.ADMIN),)
OPERATOR = (("transelect", Role.OPERATOR),)
VIEWER = (("transelect", Role.VIEWER),)

# MP002's Fecha de ingreso holds two dates as text: the importer keeps the raw
# text and stores no date. MP003's two rows share PMF + Rol + N Predio + N
# Area de Corta, so they are key_ordinal 1 and 2.
_BASE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "pmf": "MP001",
        "rol": "101",
        "numero_predio": "1",
        "numero_area_corta": "A1",
        "estado": "En evaluacion",
        "estado_resumido": "En tramite",
        "numero_ingreso": "ING-1",
        "tipo_propietario": "Empresa Forestal",
        "empresa": "Forestal Sur",
        "superficie_corta": 1.0,
    },
    {
        "pmf": "MP001",
        "rol": "101",
        "numero_predio": "1",
        "numero_area_corta": "A2",
        "estado": "En evaluacion",
        "estado_resumido": "En tramite",
        "numero_ingreso": "ING-1",
        "tipo_propietario": "Empresa Forestal",
        "empresa": "Forestal Sur",
        "superficie_corta": 2.0,
    },
    {
        "pmf": "MP002",
        "rol": "202",
        "numero_predio": "5",
        "numero_area_corta": "A1",
        "estado": "Rechazado",
        "estado_resumido": "En tramite",
        "numero_ingreso": "ING-2",
        "fecha_ingreso": "12 de marzo de 2026 y 4 de mayo de 2026",
        "tipo_propietario": "Empresa Forestal",
        "empresa": "Forestal Norte",
        "superficie_corta": 3.0,
    },
    {
        "pmf": "MP003",
        "rol": "303",
        "numero_predio": "9",
        "numero_area_corta": "A1",
        "estado": "Aprobado",
        "estado_resumido": "Aprobado",
        "numero_ingreso": "ING-3",
        "tipo_propietario": "Persona Natural",
        "empresa": "Forestal Norte",
        "superficie_corta": 4.0,
    },
    {
        "pmf": "MP003",
        "rol": "303",
        "numero_predio": "9",
        "numero_area_corta": "A1",
        "estado": "Aprobado",
        "estado_resumido": "Aprobado",
        "numero_ingreso": "ING-3",
        "tipo_propietario": "Persona Natural",
        "empresa": "Forestal Norte",
        "superficie_corta": 5.0,
    },
)


@pytest.fixture
def client(integration_engine: Engine, tmp_path: Path) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_object_store] = lambda: LocalObjectStore(tmp_path / "object-store")

    with TestClient(app) as test_client:
        test_client.engine = integration_engine
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _isolated_platform_tables(integration_engine: Engine) -> Generator[None, None, None]:
    yield
    with integration_engine.begin() as conn:
        conn.execute(text("UPDATE platform.transelec_dashboard_state SET active_import_id = NULL"))
        for table in (
            "transelec_field_override",
            "transelec_publish_event",
            "transelec_resumen_row",
            "transelec_import",
            "generated_artifact",
            "processing_attempt",
            "processing_job",
            "ingestion_run",
            "source_observation",
            "source_snapshot",
            "source_asset",
            "source_system",
            "audit_event",
            "session",
            "product_grant",
            "app_user",
        ):
            conn.execute(text(f"DELETE FROM platform.{table}"))


def _workbook(tmp_path: Path, name: str, rows: list[dict[str, Any]] | None = None) -> bytes:
    source = [dict(row) for row in (rows if rows is not None else _BASE_ROWS)]
    return _workbook_bytes(tmp_path, name, [_source_row(**row) for row in source])


def _publish(client: TestClient, content: bytes, filename: str = "edits.xlsx") -> int:
    """Upload, validate and publish (acknowledging warnings); return import_id."""

    engine: Engine = client.engine
    upload = _upload(client, content, filename)
    assert upload.status_code == 200, upload.text
    run_id = _ingestion_run_id(engine, upload.json()["source_snapshot_id"])
    validated = client.post(
        f"/transelec/imports/{run_id}/validate-and-project", headers={"Origin": _SAME_ORIGIN}
    )
    assert validated.status_code == 200, validated.text
    import_id = validated.json()["import_id"]
    published = client.post(
        f"/transelec/imports/{import_id}/publish?acknowledge_warnings=true",
        headers={"Origin": _SAME_ORIGIN},
    )
    assert published.status_code == 200, published.text
    return import_id


def _rows(client: TestClient, pmf: str) -> list[dict[str, Any]]:
    response = client.get(f"/transelec/pmfs/{pmf}")
    assert response.status_code == 200, response.text
    return response.json()["rows"]


def _row(client: TestClient, pmf: str, index: int = 0) -> dict[str, Any]:
    return _rows(client, pmf)[index]


def _insert_override(
    engine: Engine, *, import_id: int, source_row_number: int, field: str, value: str
) -> None:
    """An applied text edit written straight to the table (view tests only)."""

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO platform.transelec_field_override (
                    pmf, rol, numero_predio, numero_area_corta, key_ordinal, field,
                    value_text, planilla_value_text, base_import_id, created_by_app_user_id
                )
                SELECT pmf, rol, numero_predio, numero_area_corta, key_ordinal, :field,
                       :value, {field}, import_id, (SELECT min(id) FROM platform.app_user)
                FROM platform.transelec_keyed_row
                WHERE import_id = :import_id AND source_row_number = :row
                """
            ),
            {"field": field, "value": value, "import_id": import_id, "row": source_row_number},
        )


# ---------------------------------------------------------------------------
# The effective-row view (Task 3)
# ---------------------------------------------------------------------------


def test_effective_view_exposes_every_column_the_router_selects(
    integration_engine: Engine,
) -> None:
    with integration_engine.connect() as conn:
        columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'platform' AND table_name = 'transelec_effective_row'"
                )
            ).scalars()
        )
    assert set(_RESUMEN_ROW_COLUMNS) <= columns
    assert {"import_id", "key_ordinal", "web_fields"} <= columns


def test_effective_view_equals_the_source_rows_without_edits(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-admin", ADMIN)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    shared = [column for column in _RESUMEN_ROW_COLUMNS if column != "web_fields"]
    with client.engine.connect() as conn:
        difference = conn.execute(
            text(
                f"""
                SELECT count(*) FROM (
                    SELECT source_row_number, {", ".join(shared)}
                    FROM platform.transelec_effective_row WHERE import_id = :i
                    EXCEPT
                    SELECT source_row_number, {", ".join(shared)}
                    FROM platform.transelec_resumen_row WHERE import_id = :i
                ) AS d
                """
            ),
            {"i": import_id},
        ).scalar_one()
        ordinals = conn.execute(
            text(
                "SELECT key_ordinal FROM platform.transelec_effective_row "
                "WHERE import_id = :i AND pmf = 'MP003' ORDER BY source_row_number"
            ),
            {"i": import_id},
        ).scalars().all()
    assert difference == 0
    assert ordinals == [1, 2]
    assert all(row["web_fields"] == [] for row in _rows(client, "MP001"))


def test_every_read_sees_an_applied_edit(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-admin", ADMIN)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    target = _row(client, "MP001", 0)["source_row_number"]
    _insert_override(
        client.engine,
        import_id=import_id,
        source_row_number=target,
        field="estado_resumido",
        value="Aprobado",
    )

    detail = _row(client, "MP001", 0)
    assert detail["estado_resumido"] == "Aprobado"
    assert detail["web_fields"] == ["estado_resumido"]

    filtered = client.get("/transelec/pmfs", params={"estado_resumido": "Aprobado"}).json()
    assert target in {item["source_row_number"] for item in filtered["items"]}
    assert filtered["total_count"] == 3  # the edited row plus MP003's two rows

    searched = client.get("/transelec/pmfs", params={"q": "MP001", "estado_resumido": "Aprobado"})
    assert searched.json()["total_count"] == 1

    csv_text = client.get("/transelec/export.csv", params={"q": "MP001"}).content.decode("utf-8-sig")
    assert "Aprobado" in csv_text


@pytest.mark.parametrize(
    "value",
    ["  En   tramite ", "En\ttramite\n", "aprobado", "Aprobado", "En tramite", "", "   "],
)
def test_sql_and_python_text_rules_agree(integration_engine: Engine, value: str) -> None:
    with integration_engine.connect() as conn:
        sql = conn.execute(
            text("SELECT platform.transelec_norm_text(:v)"), {"v": value}
        ).scalar_one()
    assert sql == normalize_text(value)
```

- [ ] **Step 2: Run them to verify they fail**

```bash
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py
```

Expected:
- FAIL: `test_effective_view_exposes_every_column_the_router_selects`, because `web_fields` is not yet in `_RESUMEN_ROW_COLUMNS`.
- FAIL: `test_every_read_sees_an_applied_edit`, because the routes still read `transelec_resumen_row`.
- FAIL: `test_effective_view_equals_the_source_rows_without_edits`, with KeyError `web_fields`.
- PASS: the SQL/Python parity tests.

- [ ] **Step 3: Point every read at the view** (`apps/api/app/routers/transelec.py`)

Replace the column tuple:

```python
# Every column this router selects for a "full row" read (list/detail/
# pending/export), from platform.transelec_effective_row: the source row with
# its applied web edits (migration 0012). Order matches the contract.
_RESUMEN_ROW_COLUMNS: tuple[str, ...] = (
    "source_row_number",
    *_CONTRACT_FIELDS,
    "predio_group_key",
    "source_text_dates",
    "web_fields",
)
```

In the "Reads" section comment, replace the sentence "All read the active import's transelec_resumen_row projection;" with:

```python
# All read the active import's rows through platform.transelec_effective_row
# — the transelec_resumen_row projection with its applied web edits
# (migration 0012), so a filter, a search and every status basis see an
# edited value exactly as the dashboard shows it;
```

Change the four `FROM` clauses. Leave `WHERE import_id = :import_id` and everything else unchanged:

- `_fetch_filtered_rows`: `FROM platform.transelec_resumen_row` → `FROM platform.transelec_effective_row`
- `list_pmf_rows` count: `f"SELECT count(*) FROM platform.transelec_resumen_row "` → `f"SELECT count(*) FROM platform.transelec_effective_row "`
- `list_pmf_rows` rows: `FROM platform.transelec_resumen_row` → `FROM platform.transelec_effective_row`
- `get_pmf_detail`: `FROM platform.transelec_resumen_row` → `FROM platform.transelec_effective_row`

Add to `ResumenRowView`, after `source_text_dates`:

```python
    # The editable fields whose shown value came from a web edit (spec §3).
    # Empty for a row nobody edited.
    web_fields: list[str] = Field(default_factory=list)
```

Add to `_resumen_row_view`, after `source_text_dates=...`:

```python
        web_fields=list(row.web_fields or []),
```

Check that no other read still selects the base table. Expected: only `import_projection.py` (the write path) and docstrings mention it.

```bash
grep -n "FROM platform.transelec_resumen_row" apps/api/app/routers/transelec.py   # expected: no output
```

- [ ] **Step 4: Make the other Transelec integration modules delete overrides first**

In both `apps/api/integration_tests/test_transelec_reads_router.py` (`_isolated_platform_tables`) and `apps/api/integration_tests/test_transelec_router.py` (its cleanup tuple), insert `"transelec_field_override",` as the first entry of the table tuple, before `"transelec_publish_event",`.

- [ ] **Step 5: Run the new and existing Transelec integration tests**

```bash
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py apps/api/integration_tests/test_transelec_reads_router.py apps/api/integration_tests/test_transelec_router.py
```

Expected: PASS. Every existing reads test passes unchanged: that is the proof the view is a drop-in for the base table.

- [ ] **Step 6: Commit**

```bash
uv run ruff check --fix apps && uv run ruff format apps && uv run mypy apps
git add apps/api/app/routers/transelec.py apps/api/integration_tests/test_transelec_overrides.py apps/api/integration_tests/test_transelec_reads_router.py apps/api/integration_tests/test_transelec_router.py
git commit -m "feat(transelec): every read goes through the effective-row view"
```

---

### Task 4: `Action.EDIT`, override persistence, and retirement on activation

**Files:**
- Modify: `apps/api/app/access.py` (`Action`, `_ALLOWED`)
- Modify: `apps/api/tests/test_access.py` (`MATRIX`)
- Create: `apps/api/app/transelec_overrides.py`
- Modify: `apps/api/app/routers/transelec.py` (`_activate`, ~464-526)
- Test: `apps/api/integration_tests/test_transelec_overrides.py` (append)

**Interfaces:**
- Consumes: Task 1 helpers; the Task 2 views.
- Produces:
  - `Action.EDIT = "edit"`.
  - In `app.transelec_overrides`:
    - `OverrideStatus = Literal["aplicada","incorporada","en_conflicto","huerfana"]`;
    - errors `OverrideError`, `NoActiveVersionError`, `VersionChangedError`, `RowNotFoundError`, `FieldNotInSourceError`, `ValueChangedError`, `OverrideNotFoundError`, `NotInConflictError`;
    - `SaveOutcome(override_id: int | None, ended_override_id: int | None, changed: bool)`;
    - `OverrideRecord(id, field, status, pmf, rol, numero_predio, numero_area_corta, key_ordinal, source_row_number, web: Signature, planilla_at_edit: Signature, planilla_now: Signature, created_by_display_name: str, created_at: dt.datetime, created_on_chile: dt.date)`.
  - Functions:
    - `save_override(connection, *, import_id, source_row_number, field, value, expected, actor_app_user_id) -> SaveOutcome`
    - `discard_override(connection, *, override_id, actor_app_user_id) -> None`
    - `keep_override(connection, *, override_id, actor_app_user_id) -> int`
    - `list_overrides(connection, *, import_id, status=None, pmf=None) -> list[OverrideRecord]`
    - `retire_incorporated_overrides(connection, *, import_id, actor_app_user_id) -> int`
  - Router: `_activate` writes `incorporated_overrides` into its audit metadata.

- [ ] **Step 1: Write the failing tests**

In `apps/api/tests/test_access.py` add to `MATRIX`:

```python
    (Role.ADMIN, Action.EDIT): True,
    (Role.OPERATOR, Action.EDIT): True,
    (Role.VIEWER, Action.EDIT): False,
```

Append to `apps/api/integration_tests/test_transelec_overrides.py` (the imports go at the top of the module):

```python
import datetime as dt

from app.transelec_overrides import (
    FieldNotInSourceError,
    NotInConflictError,
    ValueChangedError,
    VersionChangedError,
    keep_override,
    list_overrides,
    save_override,
)

from transelec_ingestion.field_overrides import EDITABLE_BY_NAME

# ---------------------------------------------------------------------------
# Persistence (Task 4)
# ---------------------------------------------------------------------------


def _actor(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT min(id) FROM platform.app_user")).scalar_one()


def _save(
    engine: Engine,
    *,
    import_id: int,
    row: int,
    field: str,
    value: Any,
    expected: Any,
) -> Any:
    with engine.begin() as conn:
        return save_override(
            conn,
            import_id=import_id,
            source_row_number=row,
            field=EDITABLE_BY_NAME[field],
            value=value,
            expected=expected,
            actor_app_user_id=_actor(engine),
        )


def test_save_then_list_reports_an_applied_edit(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    outcome = _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="estado_resumido",
        value="Aprobado",
        expected="En tramite",
    )

    assert outcome.changed and outcome.override_id is not None
    with client.engine.connect() as conn:
        records = list_overrides(conn, import_id=import_id)
    assert [(r.field, r.status, r.source_row_number) for r in records] == [
        ("estado_resumido", "aplicada", row)
    ]
    assert records[0].web == ("Aprobado", None)
    assert records[0].planilla_at_edit == ("En tramite", None)
    assert records[0].created_by_display_name == "transelec-operator"


def test_save_refuses_a_stale_version_and_a_changed_value(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    with pytest.raises(VersionChangedError):
        _save(
            client.engine,
            import_id=import_id + 1000,
            row=row,
            field="estado",
            value="x",
            expected="En evaluacion",
        )
    with pytest.raises(ValueChangedError):
        _save(
            client.engine,
            import_id=import_id,
            row=row,
            field="estado",
            value="x",
            expected="Otro valor",
        )


def test_resave_supersedes_and_returning_to_the_planilla_discards(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    _save(client.engine, import_id=import_id, row=row, field="estado", value="A", expected="En evaluacion")
    _save(client.engine, import_id=import_id, row=row, field="estado", value="B", expected="A")
    back = _save(
        client.engine, import_id=import_id, row=row, field="estado", value="En evaluacion", expected="B"
    )
    same = _save(
        client.engine,
        import_id=import_id,
        row=row,
        field="estado",
        value="En evaluacion",
        expected="En evaluacion",
    )

    assert back.override_id is None and back.changed
    assert not same.changed
    with client.engine.connect() as conn:
        history = conn.execute(
            text(
                "SELECT value_text, end_reason FROM platform.transelec_field_override "
                "WHERE field = 'estado' ORDER BY id"
            )
        ).all()
    assert [tuple(item) for item in history] == [("A", "superseded"), ("B", "discarded")]
    assert _row(client, "MP001", 0)["web_fields"] == []


def test_field_without_a_source_column_is_refused(client: TestClient, tmp_path: Path) -> None:
    """The test builders write the earlier layout, which has no «…2» columns."""

    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    with pytest.raises(FieldNotInSourceError):
        _save(
            client.engine,
            import_id=import_id,
            row=row,
            field="numero_ingreso_2",
            value="ING-9",
            expected=None,
        )


def test_activation_retires_incorporated_edits_and_flags_conflicts(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    first = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    row_a = _row(client, "MP001", 0)["source_row_number"]
    row_b = _row(client, "MP001", 1)["source_row_number"]
    _save(client.engine, import_id=first, row=row_a, field="estado_resumido", value="Aprobado", expected="En tramite")
    _save(client.engine, import_id=first, row=row_b, field="estado_resumido", value="Aprobado", expected="En tramite")

    # v2: row A now says what the web said (incorporated); row B changed to
    # something else (conflict); MP002 is gone (orphan is covered in Task 5).
    rows = [dict(item) for item in _BASE_ROWS]
    rows[0]["estado_resumido"] = "Aprobado"
    rows[1]["estado_resumido"] = "Desistido"
    second = _publish(client, _workbook(tmp_path, "v2.xlsx", rows))

    with client.engine.connect() as conn:
        records = list_overrides(conn, import_id=second)
        ended = conn.execute(
            text(
                "SELECT end_reason FROM platform.transelec_field_override "
                "WHERE ended_at IS NOT NULL"
            )
        ).scalars().all()
        audit = conn.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'import.published' ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()
    assert ended == ["incorporated"]
    assert [(r.source_row_number, r.status) for r in records] == [(row_b, "en_conflicto")]
    assert records[0].planilla_now == ("Desistido", None)
    assert audit["incorporated_overrides"] == 1
    assert _row(client, "MP001", 1)["estado_resumido"] == "Desistido"  # the planilla wins

    with client.engine.begin() as conn:
        keep_override(conn, override_id=records[0].id, actor_app_user_id=_actor(client.engine))
    assert _row(client, "MP001", 1)["estado_resumido"] == "Aprobado"
    with client.engine.begin() as conn, pytest.raises(NotInConflictError):
        current = list_overrides(conn, import_id=second)[0]
        keep_override(conn, override_id=current.id, actor_app_user_id=_actor(client.engine))
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest apps/api/tests/test_access.py -q
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py
```

Expected:
- `test_access.py` FAILS with `AttributeError: EDIT`.
- The integration module fails at import with `ModuleNotFoundError: No module named 'app.transelec_overrides'`.

- [ ] **Step 3: Add `Action.EDIT`** (`apps/api/app/access.py`)

In `Action`, after `PUBLISH`:

```python
    # Changing a field of the published version through the dashboard (a web
    # edit) and downloading the planilla with those edits. Distinct from
    # PUBLISH: it changes values, not which version every viewer is served.
    EDIT = "edit"
```

In `_ALLOWED` add `(Role.ADMIN, Action.EDIT),` and `(Role.OPERATOR, Action.EDIT),`.

- [ ] **Step 4: Write `apps/api/app/transelec_overrides.py`**

```python
"""Persistence for Transelec web edits (field overrides).

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
§1-§4. The table and the three views come from migration 0012. An edit's
status is computed only by ``platform.transelec_override_state``; this
module never re-derives it, so the dashboard, the download and activation
always agree on which edits apply.

Every function runs inside the caller's transaction; the caller commits.
Field names interpolated into SQL come only from ``EDITABLE_BY_NAME``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Connection, text

from transelec_ingestion.field_overrides import (
    EditableField,
    Signature,
    cell_signature,
    shown_value,
    value_signature,
)

OverrideStatus = Literal["aplicada", "incorporada", "en_conflicto", "huerfana"]


class OverrideError(RuntimeError):
    """Base error for a web-edit operation."""


class NoActiveVersionError(OverrideError):
    """Nothing is published, so there is nothing to edit."""


class VersionChangedError(OverrideError):
    """The edit was made against a version that is no longer the active one."""


class RowNotFoundError(OverrideError):
    """The source row does not exist in the active version."""


class FieldNotInSourceError(OverrideError):
    """The published planilla has no column for this field."""


class ValueChangedError(OverrideError):
    """The value changed since the editor loaded it."""


class OverrideNotFoundError(OverrideError):
    """No active edit with that id."""


class NotInConflictError(OverrideError):
    """Only an edit in conflict with the planilla can be kept."""


@dataclass(frozen=True, slots=True)
class SaveOutcome:
    """``override_id`` is None when the cell went back to the planilla value."""

    override_id: int | None
    ended_override_id: int | None
    changed: bool


@dataclass(frozen=True, slots=True)
class OverrideRecord:
    id: int
    field: str
    status: OverrideStatus
    pmf: str
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    key_ordinal: int
    source_row_number: int | None
    web: Signature
    planilla_at_edit: Signature
    planilla_now: Signature
    created_by_display_name: str
    created_at: dt.datetime
    created_on_chile: dt.date


_KEY_MATCH = """
    pmf = :pmf
    AND rol IS NOT DISTINCT FROM :rol
    AND numero_predio IS NOT DISTINCT FROM :numero_predio
    AND numero_area_corta IS NOT DISTINCT FROM :numero_area_corta
    AND key_ordinal = :key_ordinal
"""

_INSERT = """
    INSERT INTO platform.transelec_field_override (
        pmf, rol, numero_predio, numero_area_corta, key_ordinal, field,
        value_text, value_date, planilla_value_text, planilla_value_date,
        base_import_id, created_by_app_user_id
    )
    VALUES (
        :pmf, :rol, :numero_predio, :numero_area_corta, :key_ordinal, :field,
        :value_text, :value_date, :planilla_value_text, :planilla_value_date,
        :base_import_id, :actor
    )
    RETURNING id
"""


def _locked_active_import(connection: Connection) -> int:
    """The active import, share-locked so no activation interleaves with an edit.

    ``activate_import`` takes ``FOR UPDATE`` on the same singleton row, so an
    edit and a publish/restore serialize instead of racing.
    """

    active = connection.execute(
        text(
            "SELECT active_import_id FROM platform.transelec_dashboard_state "
            "WHERE id = 1 FOR SHARE"
        )
    ).scalar_one()
    if active is None:
        raise NoActiveVersionError()
    return int(active)


def _source_fields(connection: Connection, *, import_id: int) -> set[str] | None:
    """Fields the import's planilla has a column for; None when unknown (V1 import)."""

    report = connection.execute(
        text("SELECT mapping_report FROM platform.transelec_import WHERE id = :id"),
        {"id": import_id},
    ).scalar_one()
    if report is None:
        return None
    return {entry["field"] for entry in report.get("fields", []) if entry.get("column")}


def _end(connection: Connection, *, override_id: int, reason: str, actor: int) -> None:
    connection.execute(
        text(
            """
            UPDATE platform.transelec_field_override
            SET ended_at = now(), ended_by_app_user_id = :actor, end_reason = :reason
            WHERE id = :id AND ended_at IS NULL
            """
        ),
        {"id": override_id, "reason": reason, "actor": actor},
    )


def save_override(
    connection: Connection,
    *,
    import_id: int,
    source_row_number: int,
    field: EditableField,
    value: str | dt.date | None,
    expected: str | dt.date | None,
    actor_app_user_id: int,
) -> SaveOutcome:
    """Save one cell. ``expected`` is what the editor saw (``comparable`` form)."""

    if import_id != _locked_active_import(connection):
        raise VersionChangedError()

    source_fields = _source_fields(connection, import_id=import_id)
    if source_fields is not None and field.name not in source_fields:
        raise FieldNotInSourceError()

    source = connection.execute(
        text(
            "SELECT * FROM platform.transelec_keyed_row "
            "WHERE import_id = :import_id AND source_row_number = :row"
        ),
        {"import_id": import_id, "row": source_row_number},
    ).one_or_none()
    if source is None:
        raise RowNotFoundError()

    effective = connection.execute(
        text(
            f"SELECT {field.name} AS value, source_text_dates "
            "FROM platform.transelec_effective_row "
            "WHERE import_id = :import_id AND source_row_number = :row"
        ),
        {"import_id": import_id, "row": source_row_number},
    ).one()
    if shown_value(field, effective.value) != expected:
        raise ValueChangedError()

    key = {
        "pmf": source.pmf,
        "rol": source.rol,
        "numero_predio": source.numero_predio,
        "numero_area_corta": source.numero_area_corta,
        "key_ordinal": source.key_ordinal,
        "field": field.name,
    }
    active_id = connection.execute(
        text(
            "SELECT id FROM platform.transelec_field_override "
            f"WHERE ended_at IS NULL AND field = :field AND {_KEY_MATCH} FOR UPDATE"
        ),
        key,
    ).scalar_one_or_none()

    web = value_signature(field, value)
    if web == cell_signature(field, value=effective.value, text_dates=effective.source_text_dates):
        return SaveOutcome(override_id=active_id, ended_override_id=None, changed=False)

    planilla = cell_signature(
        field, value=getattr(source, field.name), text_dates=source.source_text_dates
    )
    if web == planilla:
        if active_id is not None:
            _end(connection, override_id=active_id, reason="discarded", actor=actor_app_user_id)
        return SaveOutcome(override_id=None, ended_override_id=active_id, changed=True)

    if active_id is not None:
        _end(connection, override_id=active_id, reason="superseded", actor=actor_app_user_id)
    new_id = connection.execute(
        text(_INSERT),
        {
            **key,
            "value_text": web[0],
            "value_date": web[1],
            "planilla_value_text": planilla[0],
            "planilla_value_date": planilla[1],
            "base_import_id": import_id,
            "actor": actor_app_user_id,
        },
    ).scalar_one()
    return SaveOutcome(override_id=int(new_id), ended_override_id=active_id, changed=True)


def discard_override(connection: Connection, *, override_id: int, actor_app_user_id: int) -> None:
    """Return the cell to the planilla value."""

    ended = connection.execute(
        text(
            """
            UPDATE platform.transelec_field_override
            SET ended_at = now(), ended_by_app_user_id = :actor, end_reason = 'discarded'
            WHERE id = :id AND ended_at IS NULL
            RETURNING id
            """
        ),
        {"id": override_id, "actor": actor_app_user_id},
    ).scalar_one_or_none()
    if ended is None:
        raise OverrideNotFoundError()


def keep_override(connection: Connection, *, override_id: int, actor_app_user_id: int) -> int:
    """Keep a conflicting web value: re-anchor it to the current planilla value."""

    import_id = _locked_active_import(connection)
    current = connection.execute(
        text(
            "SELECT * FROM platform.transelec_field_override "
            "WHERE id = :id AND ended_at IS NULL FOR UPDATE"
        ),
        {"id": override_id},
    ).one_or_none()
    if current is None:
        raise OverrideNotFoundError()
    state = connection.execute(
        text(
            "SELECT status, source_text, source_date FROM platform.transelec_override_state "
            "WHERE override_id = :id AND import_id = :import_id"
        ),
        {"id": override_id, "import_id": import_id},
    ).one()
    if state.status != "en_conflicto":
        raise NotInConflictError()

    _end(connection, override_id=override_id, reason="kept", actor=actor_app_user_id)
    new_id = connection.execute(
        text(_INSERT),
        {
            "pmf": current.pmf,
            "rol": current.rol,
            "numero_predio": current.numero_predio,
            "numero_area_corta": current.numero_area_corta,
            "key_ordinal": current.key_ordinal,
            "field": current.field,
            "value_text": current.value_text,
            "value_date": current.value_date,
            "planilla_value_text": state.source_text,
            "planilla_value_date": state.source_date,
            "base_import_id": import_id,
            "actor": actor_app_user_id,
        },
    ).scalar_one()
    return int(new_id)


def list_overrides(
    connection: Connection,
    *,
    import_id: int,
    status: OverrideStatus | None = None,
    pmf: str | None = None,
) -> list[OverrideRecord]:
    """Active edits against ``import_id``: conflicts first, then orphans, then the rest."""

    clauses = ""
    params: dict[str, Any] = {"import_id": import_id}
    if status is not None:
        clauses += " AND s.status = :status"
        params["status"] = status
    if pmf is not None:
        clauses += " AND o.pmf = :pmf"
        params["pmf"] = pmf

    rows = connection.execute(
        text(
            f"""
            SELECT o.id, o.field, s.status, o.pmf, o.rol, o.numero_predio,
                   o.numero_area_corta, o.key_ordinal, s.source_row_number,
                   o.value_text, o.value_date, o.planilla_value_text, o.planilla_value_date,
                   s.source_text, s.source_date, u.display_name, o.created_at,
                   (o.created_at AT TIME ZONE 'America/Santiago')::date AS created_on_chile
            FROM platform.transelec_override_state AS s
            JOIN platform.transelec_field_override AS o ON o.id = s.override_id
            JOIN platform.app_user AS u ON u.id = o.created_by_app_user_id
            WHERE s.import_id = :import_id{clauses}
            ORDER BY
                CASE s.status
                    WHEN 'en_conflicto' THEN 0
                    WHEN 'huerfana' THEN 1
                    WHEN 'aplicada' THEN 2
                    ELSE 3
                END,
                o.pmf, s.source_row_number NULLS LAST, o.field, o.id
            """
        ),
        params,
    ).all()
    return [
        OverrideRecord(
            id=row.id,
            field=row.field,
            status=row.status,
            pmf=row.pmf,
            rol=row.rol,
            numero_predio=row.numero_predio,
            numero_area_corta=row.numero_area_corta,
            key_ordinal=row.key_ordinal,
            source_row_number=row.source_row_number,
            web=(row.value_text, row.value_date),
            planilla_at_edit=(row.planilla_value_text, row.planilla_value_date),
            planilla_now=(row.source_text, row.source_date),
            created_by_display_name=row.display_name,
            created_at=row.created_at,
            created_on_chile=row.created_on_chile,
        )
        for row in rows
    ]


def retire_incorporated_overrides(
    connection: Connection, *, import_id: int, actor_app_user_id: int
) -> int:
    """End every edit the newly active planilla already carries; return how many."""

    retired = connection.execute(
        text(
            """
            UPDATE platform.transelec_field_override AS o
            SET ended_at = now(), ended_by_app_user_id = :actor, end_reason = 'incorporated'
            FROM platform.transelec_override_state AS s
            WHERE s.override_id = o.id
              AND s.import_id = :import_id
              AND s.status = 'incorporada'
              AND o.ended_at IS NULL
            RETURNING o.id
            """
        ),
        {"import_id": import_id, "actor": actor_app_user_id},
    ).all()
    return len(retired)
```

- [ ] **Step 5: Retire incorporated edits inside the activation transaction** (`apps/api/app/routers/transelec.py`)

Import at the top with the other `app.` imports:

```python
from app.transelec_overrides import retire_incorporated_overrides
```

In `_activate`, change the transaction body to:

```python
        with engine.begin() as activation:
            result = activate_import(
                activation,
                import_id=import_id,
                actor_user_id=user.id,
                event_type=event_type,
            )
            # Edits the newly active planilla already carries retire in the
            # same transaction; otherwise a later change in the planilla would
            # read as a conflict (spec §2).
            incorporated = retire_incorporated_overrides(
                activation, import_id=import_id, actor_app_user_id=user.id
            )
            record_audit_event(
                activation,
                actor_app_user_id=user.id,
                event_type=audit_event_type,
                product_key=TRANSELEC_PRODUCT_KEY,
                subject_kind="transelec_import",
                subject_id=str(import_id),
                metadata={
                    "event_type": event_type,
                    "previous_import_id": result.previous_import_id,
                    "publish_event_id": result.publish_event_id,
                    "incorporated_overrides": incorporated,
                    **(extra_audit_metadata or {}),
                },
            )
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
uv run pytest apps/api/tests/test_access.py -q
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py apps/api/integration_tests/test_transelec_router.py
```

Expected: PASS. If `test_transelec_router.py` asserts the exact audit metadata keys of `import.published`, add `"incorporated_overrides": 0` to its expected dict. That is a behaviour addition, not a regression.

- [ ] **Step 7: Commit**

```bash
uv run ruff check --fix apps && uv run ruff format apps && uv run mypy apps
git add apps/api/app/access.py apps/api/tests/test_access.py apps/api/app/transelec_overrides.py apps/api/app/routers/transelec.py apps/api/integration_tests/test_transelec_overrides.py
git commit -m "feat(transelec): web-edit persistence and retirement on activation"
```

---

### Task 5: The override routes

**Files:**
- Create: `apps/api/app/routers/transelec_edits.py`
- Modify: `apps/api/app/main.py` (import + `app.include_router(transelec_edits_router)` after `transelec_router` at ~209, and `app.include_router(transelec_edits_router, prefix="/api")` after `transelec_router` at ~273)
- Test: `apps/api/integration_tests/test_transelec_overrides.py` (append)

**Interfaces:**
- Consumes: Task 4 persistence; `require_transelec_grant`, `_require_active_import_id`, `_resumen_row_view`, `_RESUMEN_ROW_COLUMNS`, `ResumenRowView` from `app.routers.transelec`.
- Produces:
  - `PUT /transelec/overrides` → `OverrideSaveResponse{override_id: int|None, changed: bool, row: ResumenRowView}`
  - `DELETE /transelec/overrides/{override_id}` → 204
  - `POST /transelec/overrides/{override_id}/keep` → `{override_id: int}`
  - `GET /transelec/overrides?status=&pmf=` → `list[OverrideView]` with fields `id, field, field_label, status, pmf, rol, numero_predio, numero_area_corta, source_row_number, web_value, planilla_value_at_edit, planilla_value_now, created_by_display_name, created_at`
  - Every route is also mounted under `/api`.

- [ ] **Step 1: Write the failing tests** (append)

```python
# ---------------------------------------------------------------------------
# Routes (Task 5)
# ---------------------------------------------------------------------------


def _put(
    client: TestClient,
    import_id: int,
    row: int,
    field: str,
    value: str | None,
    *,
    expected: str | None,
    csrf: bool = True,
) -> Any:
    headers = {"Origin": _SAME_ORIGIN}
    if not csrf:
        headers[CSRF_HEADER_NAME] = ""  # from app.csrf; add it to the module imports
    return client.put(
        "/transelec/overrides",
        json={
            "import_id": import_id,
            "source_row_number": row,
            "field": field,
            "value": value,
            "expected_value": expected,
        },
        headers=headers,
    )


def test_unauthenticated_and_viewer_cannot_edit(client: TestClient, tmp_path: Path) -> None:
    assert client.put("/transelec/overrides", json={}).status_code in (401, 403)
    _login_with_grants(client, "transelec-admin", ADMIN)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    client.cookies.clear()

    _login_with_grants(client, "transelec-viewer", VIEWER)
    response = _put(client, import_id, row, "estado", "x", expected="En evaluacion")
    assert response.status_code == 403
    assert client.get("/transelec/overrides").status_code == 200  # viewers read the list


def test_edit_requires_csrf(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    response = _put(client, import_id, row, "estado", "x", expected="En evaluacion", csrf=False)
    assert response.status_code == 403


def test_operator_saves_and_gets_the_effective_row(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    response = _put(client, import_id, row, "estado_resumido", "Aprobado", expected="En tramite")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True and body["override_id"] is not None
    assert body["row"]["estado_resumido"] == "Aprobado"
    assert body["row"]["web_fields"] == ["estado_resumido"]
    listed = client.get("/transelec/overrides", params={"pmf": "MP001"}).json()
    assert listed[0]["status"] == "aplicada"
    assert listed[0]["field_label"] == "Estado resumido"
    assert listed[0]["web_value"] == "Aprobado"
    assert listed[0]["planilla_value_at_edit"] == "En tramite"
    assert listed[0]["created_by_display_name"] == "transelec-operator"
    assert client.get("/api/transelec/overrides").status_code == 200  # /api alias mounted


def test_conflicts_return_codes_and_spanish_messages(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]

    stale = _put(client, import_id + 1000, row, "estado", "x", expected="En evaluacion")
    changed = _put(client, import_id, row, "estado", "x", expected="Otro")

    assert stale.status_code == 409 and stale.json()["code"] == "version_changed"
    assert changed.status_code == 409 and changed.json()["code"] == "value_changed"
    assert "Recargue" in changed.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("empresa", "x", 422),
        ("fecha_ingreso", "12-03-2026", 422),
        ("estado", "x" * 501, 422),
    ],
)
def test_invalid_edits_are_422(
    client: TestClient, tmp_path: Path, field: str, value: str, status: int
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    assert _put(client, import_id, row, field, value, expected=None).status_code == status


def test_field_without_a_source_column_is_not_editable(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    response = _put(client, import_id, row, "fecha_ingreso_2", "2026-01-02", expected=None)
    assert response.status_code == 422
    assert "columna" in response.json()["detail"]


def test_edit_hits_only_the_chosen_row_of_a_shared_key(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    second = _row(client, "MP003", 1)["source_row_number"]

    assert _put(client, import_id, second, "estado", "Desistido", expected="Aprobado").status_code == 200

    rows = _rows(client, "MP003")
    assert [r["estado"] for r in rows] == ["Aprobado", "Desistido"]


def test_date_edit_over_raw_text_survives_an_unchanged_republish(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    row = _row(client, "MP002")
    assert row["fecha_ingreso"] is None and "fecha_ingreso" in row["source_text_dates"]

    saved = _put(client, import_id, row["source_row_number"], "fecha_ingreso", "2026-03-12", expected=None)
    assert saved.status_code == 200, saved.text
    assert saved.json()["row"]["fecha_ingreso"] == "2026-03-12"
    assert "fecha_ingreso" not in saved.json()["row"]["source_text_dates"]

    # A new upload whose MP002 cell still holds the same text: the edit applies.
    rows = [dict(item) for item in _BASE_ROWS]
    rows[0]["empresa"] = "Forestal Este"  # a different file, same MP002 cell
    _publish(client, _workbook(tmp_path, "v2.xlsx", rows), filename="v2.xlsx")
    assert _row(client, "MP002")["fecha_ingreso"] == "2026-03-12"
    assert client.get("/transelec/overrides").json()[0]["status"] == "aplicada"


def test_orphans_are_listed_and_discard_returns_to_the_planilla(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    mp002 = _row(client, "MP002")["source_row_number"]
    mp001 = _row(client, "MP001", 0)["source_row_number"]
    _put(client, import_id, mp002, "estado", "Reingresado", expected="Rechazado")
    saved = _put(client, import_id, mp001, "estado", "Aprobado", expected="En evaluacion")

    rows = [dict(item) for item in _BASE_ROWS if item["pmf"] != "MP002"]
    _publish(client, _workbook(tmp_path, "v2.xlsx", rows), filename="v2.xlsx")
    listed = client.get("/transelec/overrides").json()
    assert [item["status"] for item in listed] == ["huerfana", "aplicada"]
    assert listed[0]["source_row_number"] is None

    gone = client.delete(
        f"/transelec/overrides/{saved.json()['override_id']}", headers={"Origin": _SAME_ORIGIN}
    )
    assert gone.status_code == 204
    assert _row(client, "MP001", 0)["estado"] == "En evaluacion"
    again = client.delete(
        f"/transelec/overrides/{saved.json()['override_id']}", headers={"Origin": _SAME_ORIGIN}
    )
    assert again.status_code == 404


def test_keep_route_requires_a_conflict(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    saved = _put(client, import_id, row, "estado", "Aprobado", expected="En evaluacion").json()
    response = client.post(
        f"/transelec/overrides/{saved['override_id']}/keep", headers={"Origin": _SAME_ORIGIN}
    )
    assert response.status_code == 409 and response.json()["code"] == "not_in_conflict"


def test_audit_rows_carry_no_cell_values(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    row = _row(client, "MP001", 0)["source_row_number"]
    _put(client, import_id, row, "estado_resumido", "Valor-Unico-Web", expected="En tramite")

    with client.engine.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT subject_kind, metadata::text FROM platform.audit_event "
                "WHERE event_type = 'transelec.override.saved'"
            )
        ).one()
    assert audit.subject_kind == "transelec_override"
    assert "Valor-Unico-Web" not in audit.metadata and "En tramite" not in audit.metadata
```

- [ ] **Step 2: Run them to verify they fail**

```bash
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py -k "route or edit or conflict or invalid or orphan or keep or audit or viewer or csrf or column"
```

Expected: FAIL with 404/405 on `/transelec/overrides`.

- [ ] **Step 3: Write `apps/api/app/routers/transelec_edits.py`**

```python
"""Transelec web edits: field overrides and the planilla download marked «web».

Spec: docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
§4-§5. Mounted beside ``app.routers.transelec`` with the same ``/transelec``
prefix (and its ``/api`` alias in ``app.main``). Mutations are
CSRF-protected and need ``Action.EDIT`` (OPERATOR/ADMIN). The list needs
only ``Action.VIEW``: every viewer sees the «web» chips and who made them.

Client-facing failures are Spanish and never quote a cell value; audit
metadata carries field names, ids and counts only (``app.audit``).
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from app.access import Action
from app.access_repository import AppUser
from app.audit import record_audit_event
from app.csrf import require_csrf
from app.database import get_database_engine
from app.deps import get_current_app_user, get_db_connection
from app.routers.transelec import (
    _RESUMEN_ROW_COLUMNS,
    ResumenRowView,
    _require_active_import_id,
    _resumen_row_view,
    require_transelec_grant,
)
from app.transelec_overrides import (
    FieldNotInSourceError,
    NoActiveVersionError,
    NotInConflictError,
    OverrideNotFoundError,
    OverrideRecord,
    OverrideStatus,
    RowNotFoundError,
    ValueChangedError,
    VersionChangedError,
    discard_override,
    keep_override,
    list_overrides,
    save_override,
)
from app.transelec_publication import TRANSELEC_PRODUCT_KEY
from transelec_ingestion.field_overrides import (
    EDITABLE_BY_NAME,
    OverrideValueError,
    comparable,
    display,
    parse_value,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transelec", tags=["transelec"])

_FIELD_NOT_EDITABLE = "Este campo no se puede editar en el panel."
_FIELD_NOT_IN_SOURCE = (
    "La planilla publicada no tiene una columna para este campo; no se puede editar."
)
_ROW_NOT_FOUND = "No se encontró la fila en la versión activa."
_NO_ACTIVE_IMPORT = "No hay una versión publicada de Transelec."
_VERSION_CHANGED = (
    "Se publicó otra versión de la planilla mientras editaba. Recargue la página para ver la "
    "versión activa."
)
_VALUE_CHANGED = (
    "Otra persona cambió este valor mientras lo editaba. Recargue para ver el valor actual."
)
_OVERRIDE_NOT_FOUND = "No se encontró la edición solicitada."
_NOT_IN_CONFLICT = "Sólo se puede mantener una edición que está en conflicto con la planilla."


def _conflict(code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": detail, "code": code})


class OverrideSaveRequest(BaseModel):
    import_id: int
    source_row_number: int
    field: str
    value: str | None = Field(default=None, max_length=4000)
    expected_value: str | None = Field(default=None, max_length=4000)


class OverrideSaveResponse(BaseModel):
    override_id: int | None
    changed: bool
    row: ResumenRowView


class OverrideKeepResponse(BaseModel):
    override_id: int


class OverrideView(BaseModel):
    id: int
    field: str
    field_label: str
    status: Literal["aplicada", "incorporada", "en_conflicto", "huerfana"]
    pmf: str
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    source_row_number: int | None
    web_value: str | None
    planilla_value_at_edit: str | None
    planilla_value_now: str | None
    created_by_display_name: str
    created_at: str


def _override_view(record: OverrideRecord) -> OverrideView:
    return OverrideView(
        id=record.id,
        field=record.field,
        field_label=EDITABLE_BY_NAME[record.field].label,
        status=record.status,
        pmf=record.pmf,
        rol=record.rol,
        numero_predio=record.numero_predio,
        numero_area_corta=record.numero_area_corta,
        source_row_number=record.source_row_number,
        web_value=display(record.web),
        planilla_value_at_edit=display(record.planilla_at_edit),
        planilla_value_now=display(record.planilla_now),
        created_by_display_name=record.created_by_display_name,
        created_at=record.created_at.isoformat(),
    )


@router.put(
    "/overrides",
    response_model=OverrideSaveResponse,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.EDIT))],
)
def save_field_override(
    payload: OverrideSaveRequest,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> OverrideSaveResponse | JSONResponse:
    """Save one cell of the active version (spec §4)."""

    field = EDITABLE_BY_NAME.get(payload.field)
    if field is None:
        raise HTTPException(status_code=422, detail=_FIELD_NOT_EDITABLE)
    try:
        value = parse_value(field, payload.value)
        expected = comparable(field, payload.expected_value)
    except OverrideValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        with engine.begin() as tx:
            outcome = save_override(
                tx,
                import_id=payload.import_id,
                source_row_number=payload.source_row_number,
                field=field,
                value=value,
                expected=expected,
                actor_app_user_id=user.id,
            )
            if outcome.changed:
                record_audit_event(
                    tx,
                    actor_app_user_id=user.id,
                    event_type="transelec.override.saved",
                    product_key=TRANSELEC_PRODUCT_KEY,
                    subject_kind="transelec_override",
                    subject_id=str(outcome.override_id or outcome.ended_override_id),
                    metadata={
                        "field": field.name,
                        "import_id": payload.import_id,
                        "source_row_number": payload.source_row_number,
                        "ended_override_id": outcome.ended_override_id,
                        "returned_to_planilla": outcome.override_id is None,
                    },
                )
            row = tx.execute(
                text(
                    f"SELECT {', '.join(_RESUMEN_ROW_COLUMNS)} "
                    "FROM platform.transelec_effective_row "
                    "WHERE import_id = :import_id AND source_row_number = :row"
                ),
                {"import_id": payload.import_id, "row": payload.source_row_number},
            ).one()
    except VersionChangedError:
        return _conflict("version_changed", _VERSION_CHANGED)
    except (ValueChangedError, IntegrityError):
        # IntegrityError: a concurrent save won the partial unique index.
        return _conflict("value_changed", _VALUE_CHANGED)
    except NoActiveVersionError as exc:
        raise HTTPException(status_code=404, detail=_NO_ACTIVE_IMPORT) from exc
    except RowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_ROW_NOT_FOUND) from exc
    except FieldNotInSourceError as exc:
        raise HTTPException(status_code=422, detail=_FIELD_NOT_IN_SOURCE) from exc

    return OverrideSaveResponse(
        override_id=outcome.override_id, changed=outcome.changed, row=_resumen_row_view(row)
    )


@router.delete(
    "/overrides/{override_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.EDIT))],
)
def discard_field_override(
    override_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> Response:
    """Return the cell to the planilla value."""

    try:
        with engine.begin() as tx:
            discard_override(tx, override_id=override_id, actor_app_user_id=user.id)
            record_audit_event(
                tx,
                actor_app_user_id=user.id,
                event_type="transelec.override.discarded",
                product_key=TRANSELEC_PRODUCT_KEY,
                subject_kind="transelec_override",
                subject_id=str(override_id),
            )
    except OverrideNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_OVERRIDE_NOT_FOUND) from exc
    return Response(status_code=204)


@router.post(
    "/overrides/{override_id}/keep",
    response_model=OverrideKeepResponse,
    dependencies=[Depends(require_csrf), Depends(require_transelec_grant(Action.EDIT))],
)
def keep_field_override(
    override_id: int,
    user: Annotated[AppUser, Depends(get_current_app_user)],
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> OverrideKeepResponse | JSONResponse:
    """Keep a web value the newer planilla contradicts (spec §4)."""

    try:
        with engine.begin() as tx:
            new_id = keep_override(tx, override_id=override_id, actor_app_user_id=user.id)
            record_audit_event(
                tx,
                actor_app_user_id=user.id,
                event_type="transelec.override.kept",
                product_key=TRANSELEC_PRODUCT_KEY,
                subject_kind="transelec_override",
                subject_id=str(new_id),
                metadata={"kept_override_id": override_id},
            )
    except NotInConflictError:
        return _conflict("not_in_conflict", _NOT_IN_CONFLICT)
    except OverrideNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_OVERRIDE_NOT_FOUND) from exc
    except NoActiveVersionError as exc:
        raise HTTPException(status_code=404, detail=_NO_ACTIVE_IMPORT) from exc
    return OverrideKeepResponse(override_id=new_id)


@router.get(
    "/overrides",
    response_model=list[OverrideView],
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def list_field_overrides(
    connection: Annotated[Connection, Depends(get_db_connection)],
    status: Annotated[OverrideStatus | None, Query()] = None,
    pmf: Annotated[str | None, Query()] = None,
) -> list[OverrideView]:
    """Active edits against the published version, conflicts and orphans first."""

    import_id = _require_active_import_id(connection)
    return [
        _override_view(record)
        for record in list_overrides(connection, import_id=import_id, status=status, pmf=pmf)
    ]
```

In `apps/api/app/main.py`, next to the existing transelec import add:

```python
from app.routers.transelec_edits import router as transelec_edits_router
```

Mount it after `app.include_router(transelec_router)`:

```python
app.include_router(transelec_edits_router)
```

Mount it again after `app.include_router(transelec_router, prefix="/api")`:

```python
app.include_router(transelec_edits_router, prefix="/api")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py
uv run pytest -q apps/api/tests
```

Expected: PASS. If `apps/api/tests/test_main_api_prefix_alias.py` enumerates every Transelec path, add `/transelec/overrides` to its expectation.

- [ ] **Step 5: Commit**

```bash
uv run ruff check --fix apps && uv run ruff format apps && uv run mypy apps
git add apps/api/app/routers/transelec_edits.py apps/api/app/main.py apps/api/integration_tests/test_transelec_overrides.py
git commit -m "feat(transelec): override routes — save, discard, keep and list web edits"
```

---

### Task 6: The `.xlsx` patcher

**Files:**
- Create: `products/transelect/src/transelec_ingestion/xlsx_web_patch.py`
- Test: `products/transelect/tests/test_xlsx_web_patch.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (standard library only).
- Produces:
  - `CellKind = Literal["text", "date"]`
  - `WEB_FILL_RGB = "FFFFF2CC"`, `NOTE_AUTHOR = "web"`
  - `class WorkbookPatchError(ValueError)`
  - `@dataclass CellEdit(row: int, column: str, kind: CellKind, value: str | dt.date | None, note: str)` with property `ref`
  - `SkippedEdit(row, column, reason: Literal["formula_cell"])`
  - `PatchResult(written: tuple[CellEdit, ...], skipped: tuple[SkippedEdit, ...], touched_parts: tuple[str, ...])`
  - `patch_workbook(source: Path, destination: Path, *, sheet_name: str, edits: Sequence[CellEdit]) -> PatchResult`
  - `column_index(letters) -> int`, `excel_serial(date, *, date1904) -> int`

This code was prototyped on 2026-10-04. It was run against synthetic xlsxwriter workbooks, with and without an existing note. It was also run, outside the repository, against the real 30-Sept planilla with 6 edits: absent cells, existing dates, a numeric blank and a formula cell. Results:
- 1.9 s;
- every untouched part byte-identical after decompression, in the original entry order;
- the importer read back every web value with 0 errors and the same warnings.

- [ ] **Step 1: Write the failing tests** (`products/transelect/tests/test_xlsx_web_patch.py`)

```python
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

    assert re.search(r'<c r="A2" s="\d+" t="inlineStr"><is><t xml:space="preserve">Aprobado</t>', sheet)
    assert re.search(r'<c r="B2" s="\d+"><v>2</v></c>', sheet)  # stays numeric
    assert re.search(rf'<c r="C2" s="\d+"><v>{excel_serial(dt.date(2026, 2, 1), date1904=False)}</v>', sheet)
    assert "ING &lt;1&gt; &amp; 2" in sheet  # escaped
    assert re.search(r'<c r="C3" s="\d+"/>', sheet)  # cleared, styled
    assert sheet.index('r="C3"') < sheet.index('r="E3"')  # inserted in column order
    assert '<f>"X-"&amp;A2</f>' in sheet  # formula untouched


def test_marks_fill_note_and_on_open_flags(source: Path, tmp_path: Path) -> None:
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


def test_refuses_unknown_sheet_missing_row_and_duplicate_cells(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    with pytest.raises(WorkbookPatchError):
        patch_workbook(source, out, sheet_name="Nope", edits=EDITS)
    with pytest.raises(WorkbookPatchError):
        patch_workbook(source, out, sheet_name="Resumen", edits=[CellEdit(99, "A", "text", "x", "n")])
    with pytest.raises(WorkbookPatchError):
        patch_workbook(source, out, sheet_name="Resumen", edits=[EDITS[0], EDITS[0]])


def test_helpers() -> None:
    assert column_index("A") == 0 and column_index("AB") == 27
    assert excel_serial(dt.date(2026, 1, 5), date1904=False) == 46027
    assert excel_serial(dt.date(1904, 1, 2), date1904=True) == 1
```

If `fecha_ingreso` comes back as a `datetime` from calamine in `test_the_importer_reads_the_web_values_back`, compare `.date()`. Check what `load_transelec_workbook` returns for an Excel date in `products/transelect/tests/test_xlsx_contract.py` and match it.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest products/transelect/tests/test_xlsx_web_patch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'transelec_ingestion.xlsx_web_patch'`

- [ ] **Step 3: Write the implementation** (`products/transelect/src/transelec_ingestion/xlsx_web_patch.py`)

```python
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


def _add_notes(parts: dict[str, bytes], names: set[str], sheet_part: str,
               edits: Sequence[CellEdit]) -> list[str]:
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
                '<r><t xml:space="preserve">'
                f"{escape(chr(10) + _clean_text(edit.note))}</t></r>"
            )
            merged = existing.group(0).replace("</text>", addition + "</text>", 1)
            comments_xml = comments_xml[: existing.start()] + merged + comments_xml[existing.end() :]
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
    source: Path, destination: Path, *, sheet_name: str, edits: Sequence[CellEdit]
) -> PatchResult:
    """Write ``edits`` into a copy of ``source`` at ``destination``.

    Every ZIP entry not listed in ``PatchResult.touched_parts`` is copied
    byte-for-byte (after decompression), in its original order.
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest products/transelect/tests/test_xlsx_web_patch.py -v`
Expected: PASS (both parametrizations of the fixture-based tests).

- [ ] **Step 5: Commit**

```bash
uv run ruff check --fix products/transelect && uv run ruff format products/transelect && uv run mypy products/transelect
git add products/transelect/src/transelec_ingestion/xlsx_web_patch.py products/transelect/tests/test_xlsx_web_patch.py
git commit -m "feat(transelec): patch the uploaded planilla with «web» cells, notes and on-open flags"
```

---

### Task 7: `GET /transelec/export.xlsx`

**Files:**
- Modify: `apps/api/app/routers/transelec_edits.py` (append the route)
- Test: `apps/api/integration_tests/test_transelec_overrides.py` (append)

**Interfaces:**
- Consumes:
  - `list_overrides(..., status="aplicada")` (Task 4);
  - `patch_workbook`, `CellEdit`, `WorkbookPatchError` (Task 6);
  - `note_text` (Task 1);
  - `ObjectStore.open(key)`;
  - `transelec_import.mapping_report` (`sheet_name`, `fields[].field/column`).
- Produces: `GET /transelec/export.xlsx`. It needs `Action.EDIT` and returns `FileResponse` attachment `<stem>_web_<YYYY-MM-DD>.xlsx`. On failure:
  - 409 when the import has no mapping report or the stored file is unavailable;
  - 422 when the patcher refuses the workbook shape.

- [ ] **Step 1: Write the failing tests** (append; add `import io`, `import zipfile` and `from transelec_ingestion.xlsx_contract import load_transelec_workbook` to the module imports)

```python
# ---------------------------------------------------------------------------
# Download (Task 7)
# ---------------------------------------------------------------------------


def _download(client: TestClient) -> Any:
    return client.get("/transelec/export.xlsx")


def test_viewer_cannot_download(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-admin", ADMIN)
    _publish(client, _workbook(tmp_path, "base.xlsx"))
    client.cookies.clear()
    _login_with_grants(client, "transelec-viewer", VIEWER)
    assert _download(client).status_code == 403


def test_export_writes_only_applied_edits(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    original = _workbook(tmp_path, "PlanillaSintetica.xlsx")
    import_id = _publish(client, original, filename="PlanillaSintetica.xlsx")
    mp001 = _row(client, "MP001", 0)["source_row_number"]
    mp002 = _row(client, "MP002")["source_row_number"]
    _put(client, import_id, mp001, "estado_resumido", "Aprobado", expected="En tramite")
    _put(client, import_id, mp002, "estado", "Reingresado", expected="Rechazado")
    # v2 drops MP002 (its edit becomes an orphan) but keeps MP001's cell.
    rows = [dict(item) for item in _BASE_ROWS if item["pmf"] != "MP002"]
    second = _workbook(tmp_path, "PlanillaSintetica2.xlsx", rows)
    _publish(client, second, filename="PlanillaSintetica2.xlsx")

    response = _download(client)

    assert response.status_code == 200, response.text
    disposition = response.headers["content-disposition"]
    assert "PlanillaSintetica2_web_" in disposition and disposition.endswith('.xlsx"')
    downloaded = tmp_path / "downloaded.xlsx"
    downloaded.write_bytes(response.content)
    # MP001's rows come first in both versions, so its row number did not move.
    edited = next(
        r for r in load_transelec_workbook(downloaded).resumen_rows if r.source_row_number == mp001
    )
    assert edited.values["estado_resumido"] == "Aprobado"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        comments = archive.read("xl/comments1.xml").decode("utf-8")
        assert comments.count("<comment ") == 1  # the orphan is not written
        assert "web · transelec-operator · " in comments and "antes: En tramite" in comments
        after = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(io.BytesIO(second)) as archive:
        before = {name: archive.read(name) for name in archive.namelist()}
    changed = {name for name, data in before.items() if after.get(name) != data}
    assert changed <= {
        "xl/worksheets/sheet1.xml",
        "xl/styles.xml",
        "xl/workbook.xml",
        "[Content_Types].xml",
        "xl/worksheets/_rels/sheet1.xml.rels",
    }
    with client.engine.connect() as conn:
        metadata = conn.execute(
            text(
                "SELECT metadata FROM platform.audit_event "
                "WHERE event_type = 'transelec.export.xlsx_downloaded'"
            )
        ).scalar_one()
    assert metadata == {"written": 1, "skipped_formula": 0, "unmapped": 0}


def test_export_needs_the_mapping_report(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    with client.engine.begin() as conn:
        conn.execute(
            text("UPDATE platform.transelec_import SET mapping_report = NULL WHERE id = :i"),
            {"i": import_id},
        )
    response = _download(client)
    assert response.status_code == 409
    assert "vuelva a importar" in response.json()["detail"]
```

- [ ] **Step 2: Run them to verify they fail**

```bash
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py -k "download or export"
```

Expected: FAIL with 404 on `/transelec/export.xlsx`.

- [ ] **Step 3: Append the route to `apps/api/app/routers/transelec_edits.py`**

Add these imports at the top:

```python
import shutil
import tempfile
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.deps import get_object_store
from app.object_store import ObjectStore, ObjectStoreError
from app.routers.transelec import _DOWNLOAD_CHUNK_BYTES, _SOURCE_UNAVAILABLE
from transelec_ingestion.field_overrides import note_text
from transelec_ingestion.xlsx_web_patch import CellEdit, WorkbookPatchError, patch_workbook
```

Then add the copy and the route:

```python
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXPORT_NEEDS_MAPPING = (
    "Esta versión se importó sin el mapa de columnas; vuelva a importar la planilla para "
    "descargarla con ediciones."
)
_EXPORT_FAILED = (
    "No se pudo preparar la planilla con ediciones: su estructura no es la esperada. "
    "Contacte a soporte."
)


@router.get(
    "/export.xlsx",
    dependencies=[Depends(require_transelec_grant(Action.EDIT))],
)
def export_planilla_with_edits(
    user: Annotated[AppUser, Depends(get_current_app_user)],
    connection: Annotated[Connection, Depends(get_db_connection)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> FileResponse:
    """The active version's uploaded planilla with its applied edits marked «web» (spec §5)."""

    import_id = _require_active_import_id(connection)
    source = connection.execute(
        text(
            """
            SELECT i.mapping_report, s.object_storage_key,
                   (SELECT o.filename FROM platform.source_observation AS o
                    WHERE o.source_snapshot_id = s.id
                    ORDER BY o.observed_at DESC LIMIT 1) AS filename,
                   (now() AT TIME ZONE 'America/Santiago')::date AS today_chile
            FROM platform.transelec_import AS i
            JOIN platform.source_snapshot AS s ON s.id = i.source_snapshot_id
            WHERE i.id = :import_id
            """
        ),
        {"import_id": import_id},
    ).one()
    if source.mapping_report is None:
        raise HTTPException(status_code=409, detail=_EXPORT_NEEDS_MAPPING)
    if source.object_storage_key is None:
        raise HTTPException(status_code=409, detail=_SOURCE_UNAVAILABLE)

    columns = {
        entry["field"]: entry["column"]
        for entry in source.mapping_report.get("fields", [])
        if entry.get("column")
    }
    edits: list[CellEdit] = []
    unmapped = 0
    for record in list_overrides(connection, import_id=import_id, status="aplicada"):
        column = columns.get(record.field)
        if column is None or record.source_row_number is None:
            unmapped += 1
            continue
        field = EDITABLE_BY_NAME[record.field]
        text_value, date_value = record.web
        edits.append(
            CellEdit(
                row=record.source_row_number,
                column=column,
                kind=field.kind,
                value=date_value if field.kind == "date" else text_value,
                note=note_text(
                    author=record.created_by_display_name,
                    edited_on=record.created_on_chile,
                    planilla=record.planilla_at_edit,
                ),
            )
        )

    workdir = Path(tempfile.mkdtemp(prefix="campo-transelec-export-"))
    source_path = workdir / "source.xlsx"
    output_path = workdir / "planilla-web.xlsx"
    try:
        with store.open(source.object_storage_key) as reader, source_path.open("wb") as sink:
            while chunk := reader.read(_DOWNLOAD_CHUNK_BYTES):
                sink.write(chunk)
        result = patch_workbook(
            source_path,
            output_path,
            sheet_name=source.mapping_report["sheet_name"],
            edits=edits,
        )
    except ObjectStoreError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        logger.warning("Transelec export: source object unavailable for import_id=%s", import_id)
        raise HTTPException(status_code=409, detail=_SOURCE_UNAVAILABLE) from exc
    except WorkbookPatchError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        logger.warning("Transelec export refused for import_id=%s: %s", import_id, exc)
        raise HTTPException(status_code=422, detail=_EXPORT_FAILED) from exc
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    record_audit_event(
        connection,
        actor_app_user_id=user.id,
        event_type="transelec.export.xlsx_downloaded",
        product_key=TRANSELEC_PRODUCT_KEY,
        subject_kind="transelec_import",
        subject_id=str(import_id),
        metadata={
            "written": len(result.written),
            "skipped_formula": len(result.skipped),
            "unmapped": unmapped,
        },
    )
    stem = Path(source.filename or "planilla").stem
    return FileResponse(
        output_path,
        media_type=_XLSX_MIME,
        filename=f"{stem}_web_{source.today_chile.isoformat()}.xlsx",
        background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
    )
```

Here `connection` is the request-scoped connection from `get_db_connection`, which commits on success. `_require_active_import_id` already uses it, so the audit row is committed with the request.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py
```

Expected: PASS. If the audit row is not visible in `test_export_writes_only_applied_edits`, the request-scoped commit ran after the test read. Wrap the audit write in `with engine.begin() as tx:` (inject `engine: Annotated[Engine, Depends(get_database_engine)]`), as the PUT route does.

- [ ] **Step 5: Commit**

```bash
uv run ruff check --fix apps && uv run ruff format apps && uv run mypy apps
git add apps/api/app/routers/transelec_edits.py apps/api/integration_tests/test_transelec_overrides.py
git commit -m "feat(transelec): download the planilla with web edits marked"
```

---

### Task 8: Dashboard API client and web-edit helpers

**Files:**
- Modify: `products/transelect/dashboard/src/api.ts`:
  - `ResumenRow` (~176-220);
  - new section after "Access administration" (end of file).
- Create: `products/transelect/dashboard/src/lib/webEdits.ts`, `products/transelect/dashboard/src/lib/webEdits.test.ts`
- Create: `products/transelect/dashboard/src/components/WebChip.tsx`

**Interfaces:**
- Consumes:
  - `request`, `withParams`, `transelecRole` (private and public functions in `api.ts`);
  - `collectAllRows` (`lib/rowCollection.ts`);
  - `formatDate` (`format.ts`).
- Produces:
  - in `api.ts`: `ResumenRow.web_fields?: string[]`, `EditableFieldName`, `OverrideStatus`, `TranselecOverride`, `OverrideSaveInput`, `OverrideSaveResult`, `OverrideConflictCode`, `overrideConflictCode(payload)`, `listOverrides(options)`, `saveOverride(input)`, `discardOverride(id)`, `keepOverride(id)`, `exportXlsxUrl()`, `canEdit(me)`;
  - in `lib/webEdits.ts`: `EditableFieldSpec`, `EDITABLE_FIELDS`, `STATUS_LABELS`, `isWebField(row, field)`, `displayValue(spec, value)`, `webTooltip(override, spec)`, `overrideFor(overrides, row, field)`, `suggestionsFrom(rows, field)`, `loadSuggestions(importId)`, `resetSuggestionCache()`, `specFor(field)`;
  - `components/WebChip.tsx`: `WebChip({ title })`.

- [ ] **Step 1: Write the failing test** (`src/lib/webEdits.test.ts`)

```ts
import { describe, expect, it } from 'vitest'
import type { TranselecOverride } from '../api'
import { canEdit, overrideConflictCode } from '../api'
import { makeRow } from '../test/factories'
import {
  EDITABLE_FIELDS,
  displayValue,
  isWebField,
  overrideFor,
  specFor,
  suggestionsFrom,
  webTooltip,
} from './webEdits'

const override: TranselecOverride = {
  id: 31,
  field: 'estado_resumido',
  field_label: 'Estado resumido',
  status: 'aplicada',
  pmf: 'MP001',
  rol: '101',
  numero_predio: '1',
  numero_area_corta: 'A1',
  source_row_number: 2,
  web_value: 'Aprobado',
  planilla_value_at_edit: 'En tramite',
  planilla_value_now: 'En tramite',
  created_by_display_name: 'Ana Pérez',
  created_at: '2026-10-04T15:00:00+00:00',
}

describe('web edit helpers', () => {
  it('lists the eleven editable fields', () => {
    expect(EDITABLE_FIELDS.map((spec) => spec.name).sort()).toEqual(
      [
        'estado',
        'estado_resumido',
        'fecha_90_dias',
        'fecha_ingreso',
        'fecha_ingreso_2',
        'numero_ingreso',
        'numero_ingreso_2',
        'reingreso_legal',
        'reingreso_recrep',
        'reingreso_tec',
        'tipo_rechazo',
      ].sort(),
    )
  })

  it('knows which fields of a row came from the web', () => {
    expect(isWebField(makeRow({ web_fields: ['estado'] }), 'estado')).toBe(true)
    expect(isWebField(makeRow(), 'estado')).toBe(false)
  })

  it('formats dates and builds the tooltip', () => {
    expect(displayValue(specFor('fecha_ingreso'), '2026-03-12')).toBe('12-03-2026')
    expect(displayValue(specFor('estado'), null)).toBe('')
    expect(webTooltip(override, specFor('estado_resumido'))).toBe(
      'Editado en la web por Ana Pérez · 04-10-2026 · en la planilla: En tramite',
    )
  })

  it('finds the applied override of a row and field', () => {
    const row = makeRow({ source_row_number: 2 })
    expect(overrideFor([override], row, 'estado_resumido')?.id).toBe(31)
    expect(overrideFor([override], row, 'estado')).toBeUndefined()
  })

  it('collects distinct suggestions, sorted', () => {
    const rows = [
      makeRow({ estado_resumido: 'En tramite' }),
      makeRow({ estado_resumido: 'Aprobado' }),
      makeRow({ estado_resumido: 'Aprobado' }),
      makeRow({ estado_resumido: null }),
    ]
    expect(suggestionsFrom(rows, 'estado_resumido')).toEqual(['Aprobado', 'En tramite'])
  })

  it('reads the conflict code and the edit permission', () => {
    expect(overrideConflictCode({ detail: 'x', code: 'value_changed' })).toBe('value_changed')
    expect(overrideConflictCode({ detail: 'x' })).toBeNull()
    const grant = (role: 'admin' | 'operator' | 'viewer') => ({
      identity_key: 'k',
      display_name: 'K',
      product_grants: [{ product_key: 'transelect', role }],
    })
    expect(canEdit(grant('operator'))).toBe(true)
    expect(canEdit(grant('viewer'))).toBe(false)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd products/transelect/dashboard && npx vitest run src/lib/webEdits.test.ts`
Expected: FAIL with `Failed to resolve import "./webEdits"`.

- [ ] **Step 3: Extend `api.ts`**

In `ResumenRow`, after `source_text_dates?`:

```ts
  /** Editable fields whose shown value came from a web edit; absent or `[]` when none. */
  web_fields?: string[]
```

Append at the end of the file:

```ts
// ---------------------------------------------------------------------------
// Web edits (field overrides)
//
// docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md §4.
// The server gates PUT/DELETE/keep and the download on Action.EDIT
// (operator/admin) and re-checks every value; this client only shapes calls.
// ---------------------------------------------------------------------------

export type EditableFieldName =
  | 'estado'
  | 'estado_resumido'
  | 'tipo_rechazo'
  | 'reingreso_tec'
  | 'reingreso_legal'
  | 'reingreso_recrep'
  | 'numero_ingreso'
  | 'numero_ingreso_2'
  | 'fecha_ingreso'
  | 'fecha_ingreso_2'
  | 'fecha_90_dias'

export type OverrideStatus = 'aplicada' | 'incorporada' | 'en_conflicto' | 'huerfana'

export interface TranselecOverride {
  id: number
  field: EditableFieldName
  field_label: string
  status: OverrideStatus
  pmf: string
  rol: string | null
  numero_predio: string | null
  numero_area_corta: string | null
  source_row_number: number | null
  web_value: string | null
  planilla_value_at_edit: string | null
  planilla_value_now: string | null
  created_by_display_name: string
  created_at: string
}

export interface OverrideSaveInput {
  importId: number
  sourceRowNumber: number
  field: EditableFieldName
  value: string | null
  expectedValue: string | null
}

export interface OverrideSaveResult {
  override_id: number | null
  changed: boolean
  row: ResumenRow
}

export type OverrideConflictCode = 'version_changed' | 'value_changed' | 'not_in_conflict'

/** The `code` of a 409 from the override routes, or null for any other failure. */
export function overrideConflictCode(payload: unknown): OverrideConflictCode | null {
  if (payload && typeof payload === 'object' && 'code' in payload) {
    const code = (payload as { code?: unknown }).code
    if (code === 'version_changed' || code === 'value_changed' || code === 'not_in_conflict') {
      return code
    }
  }
  return null
}

/** OPERATOR/ADMIN gate for editing and the «web» download (server re-enforces). */
export function canEdit(me: Me | null): boolean {
  const role = transelecRole(me)
  return role === 'admin' || role === 'operator'
}

export function listOverrides(
  options: { status?: OverrideStatus; pmf?: string } = {},
): Promise<ApiResult<TranselecOverride[]>> {
  const params = new URLSearchParams()
  if (options.status) params.set('status', options.status)
  if (options.pmf) params.set('pmf', options.pmf)
  return request<TranselecOverride[]>(withParams('/api/transelec/overrides', params))
}

export function saveOverride(input: OverrideSaveInput): Promise<ApiResult<OverrideSaveResult>> {
  return request<OverrideSaveResult>('/api/transelec/overrides', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      import_id: input.importId,
      source_row_number: input.sourceRowNumber,
      field: input.field,
      value: input.value,
      expected_value: input.expectedValue,
    }),
  })
}

export function discardOverride(id: number): Promise<ApiResult<void>> {
  return request<void>(`/api/transelec/overrides/${id}`, { method: 'DELETE' })
}

export function keepOverride(id: number): Promise<ApiResult<{ override_id: number }>> {
  return request<{ override_id: number }>(`/api/transelec/overrides/${id}/keep`, {
    method: 'POST',
  })
}

/** The planilla with the applied edits marked «web»; the browser downloads it. */
export function exportXlsxUrl(): string {
  return '/api/transelec/export.xlsx'
}
```

- [ ] **Step 4: Write `src/lib/webEdits.ts` and `src/components/WebChip.tsx`**

```ts
/**
 * Web edits, front-end side: the editable fields in the drawer's reading
 * order, labels, tooltips and the datalist suggestions.
 *
 * Mirrors `transelec_ingestion.field_overrides.EDITABLE_FIELDS`; the server
 * is the authority and re-checks every save.
 */
import {
  EMPTY_FILTERS,
  type EditableFieldName,
  type OverrideStatus,
  type ResumenRow,
  type TranselecOverride,
} from '../api'
import { formatDate } from '../format'
import { collectAllRows } from './rowCollection'

export interface EditableFieldSpec {
  name: EditableFieldName
  label: string
  kind: 'text' | 'date'
  /** Offer the values present in the published version as suggestions. */
  suggest: boolean
}

export const EDITABLE_FIELDS: readonly EditableFieldSpec[] = [
  { name: 'estado_resumido', label: 'Estado resumido', kind: 'text', suggest: true },
  { name: 'estado', label: 'Estado', kind: 'text', suggest: true },
  { name: 'tipo_rechazo', label: 'Tipo de rechazo', kind: 'text', suggest: true },
  { name: 'reingreso_tec', label: 'Reingreso técnico', kind: 'text', suggest: false },
  { name: 'reingreso_legal', label: 'Reingreso legal', kind: 'text', suggest: false },
  { name: 'reingreso_recrep', label: 'Reingreso rec. reposición', kind: 'text', suggest: false },
  { name: 'numero_ingreso', label: 'N.º ingreso', kind: 'text', suggest: false },
  { name: 'fecha_ingreso', label: 'Fecha ingreso', kind: 'date', suggest: false },
  { name: 'numero_ingreso_2', label: 'N.º ingreso 2', kind: 'text', suggest: false },
  { name: 'fecha_ingreso_2', label: 'Fecha ingreso 2', kind: 'date', suggest: false },
  { name: 'fecha_90_dias', label: '90 días', kind: 'date', suggest: false },
]

export const STATUS_LABELS: Record<OverrideStatus, string> = {
  aplicada: 'Aplicada',
  incorporada: 'Ya está en la planilla',
  en_conflicto: 'En conflicto con la planilla',
  huerfana: 'Sin fila en la versión publicada',
}

export function specFor(field: EditableFieldName): EditableFieldSpec {
  const spec = EDITABLE_FIELDS.find((entry) => entry.name === field)
  if (!spec) throw new Error(`unknown editable field ${field}`)
  return spec
}

export function isWebField(row: Pick<ResumenRow, 'web_fields'>, field: EditableFieldName): boolean {
  return (row.web_fields ?? []).includes(field)
}

export function displayValue(spec: EditableFieldSpec, value: string | null): string {
  if (value === null || value.trim() === '') return ''
  return spec.kind === 'date' ? formatDate(value) : value
}

export function webTooltip(override: TranselecOverride | undefined, spec: EditableFieldSpec): string {
  if (!override) return 'Editado en la web'
  const before = displayValue(spec, override.planilla_value_at_edit) || '(vacía)'
  return `Editado en la web por ${override.created_by_display_name} · ${formatDate(override.created_at)} · en la planilla: ${before}`
}

export function overrideFor(
  overrides: readonly TranselecOverride[],
  row: Pick<ResumenRow, 'source_row_number'>,
  field: EditableFieldName,
): TranselecOverride | undefined {
  return overrides.find(
    (entry) =>
      entry.field === field &&
      entry.source_row_number === row.source_row_number &&
      entry.status === 'aplicada',
  )
}

export function suggestionsFrom(rows: readonly ResumenRow[], field: EditableFieldName): string[] {
  const values = new Set<string>()
  for (const row of rows) {
    const value = row[field]
    if (value && value.trim()) values.add(value.trim())
  }
  return [...values].sort((a, b) => a.localeCompare(b, 'es'))
}

let suggestionCache: { importId: number; values: Partial<Record<EditableFieldName, string[]>> } | null =
  null

/** Distinct values per suggestible field of the published version, cached per version. */
export async function loadSuggestions(
  importId: number,
): Promise<Partial<Record<EditableFieldName, string[]>>> {
  if (suggestionCache?.importId === importId) return suggestionCache.values
  const result = await collectAllRows(EMPTY_FILTERS)
  if (!result.ok) return {}
  const values: Partial<Record<EditableFieldName, string[]>> = {}
  for (const spec of EDITABLE_FIELDS) {
    if (spec.suggest) values[spec.name] = suggestionsFrom(result.rows, spec.name)
  }
  suggestionCache = { importId, values }
  return values
}

/** Test seam. */
export function resetSuggestionCache(): void {
  suggestionCache = null
}
```

```tsx
/** The «web» mark next to a value that came from a dashboard edit. */
export function WebChip({ title }: { title?: string }) {
  return (
    <span className="web-chip" title={title} data-testid="web-chip">
      web
    </span>
  )
}
```

- [ ] **Step 5: Run the test and the type check**

Run: `cd products/transelect/dashboard && npx vitest run src/lib/webEdits.test.ts && npx tsc -b`
Expected: PASS; no type errors.

- [ ] **Step 6: Commit**

```bash
cd products/transelect/dashboard && npm run lint && cd -
git add products/transelect/dashboard/src/api.ts products/transelect/dashboard/src/lib/webEdits.ts products/transelect/dashboard/src/lib/webEdits.test.ts products/transelect/dashboard/src/components/WebChip.tsx
git commit -m "feat(transelec-dashboard): client and helpers for web edits"
```

---

### Task 9: Editing in the drawer, chips in Explorador

**Files:**
- Create: `products/transelect/dashboard/src/components/EditableFieldsSection.tsx`, `EditableFieldsSection.test.tsx`
- Modify:
  - `src/components/RowDetailDrawer.tsx` (props ~206-214, the detail effect ~233-251, render after the Tramitación section ~359);
  - `src/components/RowsTable.tsx` (Estado resumido and N.º ingreso cells ~89-108);
  - `src/pages/ExploradorPage.tsx` (props ~51-61, drawer ~331-337);
  - `src/App.tsx` (`ExploradorPage` case ~190-196);
  - `src/styles/components.css` (append next to `.flag`, ~1612).

**Interfaces:**
- Consumes: Task 8.
- Produces:
  - `EditableFieldsSection({ row, activeImportId, canEdit, sourceFields, overrides, suggestions, onSaved, onReload })`;
  - `RowDetailDrawer` gains optional `canEdit?: boolean`, `activeImportId?: number | null`, `onRowEdited?: (row: ResumenRow) => void`;
  - `ExploradorPage` gains `canEdit?: boolean`.

- [ ] **Step 1: Write the failing component test** (`src/components/EditableFieldsSection.test.tsx`)

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EditableFieldsSection } from './EditableFieldsSection'
import { makeRow } from '../test/factories'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, saveOverride: vi.fn(), discardOverride: vi.fn() }
})

const { saveOverride } = await import('../api')

const base = {
  activeImportId: 7,
  sourceFields: null,
  overrides: [],
  suggestions: { estado_resumido: ['Aprobado', 'En tramite'] },
  onReload: vi.fn(),
}

describe('EditableFieldsSection', () => {
  beforeEach(() => vi.mocked(saveOverride).mockReset())

  it('saves a new value with the value the editor saw', async () => {
    const onSaved = vi.fn()
    const row = makeRow({ source_row_number: 2, estado_resumido: 'En tramite' })
    vi.mocked(saveOverride).mockResolvedValue({
      ok: true,
      data: {
        override_id: 31,
        changed: true,
        row: { ...row, estado_resumido: 'Aprobado', web_fields: ['estado_resumido'] },
      },
    })
    render(<EditableFieldsSection {...base} row={row} canEdit onSaved={onSaved} />)

    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado resumido' }))
    const input = screen.getByLabelText('Nuevo valor de Estado resumido')
    await userEvent.clear(input)
    await userEvent.type(input, 'Aprobado')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(saveOverride).toHaveBeenCalledWith({
      importId: 7,
      sourceRowNumber: 2,
      field: 'estado_resumido',
      value: 'Aprobado',
      expectedValue: 'En tramite',
    })
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ estado_resumido: 'Aprobado' }))
  })

  it('explains a concurrent change and offers a reload', async () => {
    vi.mocked(saveOverride).mockResolvedValue({
      ok: false,
      status: 409,
      error: 'x',
      payload: { detail: 'x', code: 'value_changed' },
    })
    render(<EditableFieldsSection {...base} row={makeRow()} canEdit onSaved={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado' }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Otra persona cambió este valor')
    expect(screen.getByRole('button', { name: 'Recargar' })).toBeInTheDocument()
  })

  it('shows chips but no edit controls to a viewer', () => {
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ web_fields: ['estado'] })}
        canEdit={false}
        onSaved={vi.fn()}
      />,
    )
    expect(screen.getAllByTestId('web-chip')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
  })

  it('hides Editar for a field the published planilla has no column for', () => {
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow()}
        canEdit
        sourceFields={['estado', 'estado_resumido']}
        onSaved={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Editar Estado' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Editar N.º ingreso 2' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd products/transelect/dashboard && npx vitest run src/components/EditableFieldsSection.test.tsx`
Expected: FAIL with `Failed to resolve import "./EditableFieldsSection"`.

- [ ] **Step 3: Write `src/components/EditableFieldsSection.tsx`**

```tsx
/**
 * The drawer's «Campos editables» block (web edits, spec §6).
 *
 * Operators and administrators change one cell at a time. Every save sends
 * the value the editor saw, so a concurrent change or a newly published
 * version is refused (409) instead of overwritten. Viewers see which values
 * came from the web and who changed them, and nothing else. A field the
 * published planilla has no column for is not offered: it could never be
 * written back into the download.
 */
import { useState } from 'react'
import {
  type EditableFieldName,
  type ResumenRow,
  type TranselecOverride,
  discardOverride,
  overrideConflictCode,
  saveOverride,
} from '../api'
import {
  EDITABLE_FIELDS,
  type EditableFieldSpec,
  displayValue,
  isWebField,
  overrideFor,
  webTooltip,
} from '../lib/webEdits'
import { AlertBanner } from './StateViews'
import { WebChip } from './WebChip'

const RELOAD_COPY = {
  version_changed:
    'Se publicó otra versión de la planilla mientras editaba. Recargue para ver la versión activa.',
  value_changed:
    'Otra persona cambió este valor mientras lo editaba. Recargue para ver el valor actual.',
} as const

export function EditableFieldsSection({
  row,
  activeImportId,
  canEdit,
  sourceFields,
  overrides,
  suggestions,
  onSaved,
  onReload,
}: {
  row: ResumenRow
  activeImportId: number | null
  canEdit: boolean
  /** The published version's source fields; null while unknown. */
  sourceFields: readonly string[] | null
  overrides: readonly TranselecOverride[]
  suggestions: Partial<Record<EditableFieldName, string[]>>
  onSaved: (row: ResumenRow) => void
  onReload: () => void
}) {
  const [editing, setEditing] = useState<EditableFieldName | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ message: string; reload: boolean } | null>(null)

  const editable = (spec: EditableFieldSpec) =>
    canEdit && activeImportId !== null && (sourceFields === null || sourceFields.includes(spec.name))

  const start = (spec: EditableFieldSpec) => {
    setEditing(spec.name)
    setDraft(row[spec.name] ?? '')
    setError(null)
  }

  const submit = async (spec: EditableFieldSpec) => {
    if (activeImportId === null) return
    setBusy(true)
    setError(null)
    const result = await saveOverride({
      importId: activeImportId,
      sourceRowNumber: row.source_row_number,
      field: spec.name,
      value: draft.trim() === '' ? null : draft,
      expectedValue: row[spec.name],
    })
    setBusy(false)
    if (!result.ok) {
      const code = overrideConflictCode(result.payload)
      if (code === 'version_changed' || code === 'value_changed') {
        setError({ message: RELOAD_COPY[code], reload: true })
      } else {
        setError({ message: result.error, reload: false })
      }
      return
    }
    setEditing(null)
    onSaved(result.data.row)
  }

  const revert = async (override: TranselecOverride) => {
    setBusy(true)
    setError(null)
    const result = await discardOverride(override.id)
    setBusy(false)
    if (!result.ok) {
      setError({ message: result.error, reload: false })
      return
    }
    onReload()
  }

  return (
    <section
      className="drawer-section"
      aria-labelledby="drawer-editables"
      data-testid="drawer-editables"
    >
      <h3 id="drawer-editables">Campos editables</h3>
      <p className="hint">
        Los valores marcados «web» se cambiaron en el panel; la planilla publicada no se modifica.
        {!canEdit && ' Sólo operadores y administradores pueden editarlos.'}
      </p>
      {error && (
        <AlertBanner title="No se guardó el cambio">
          {error.message}{' '}
          {error.reload && (
            <button type="button" className="btn-link" onClick={onReload}>
              Recargar
            </button>
          )}
        </AlertBanner>
      )}
      <dl className="facts">
        {EDITABLE_FIELDS.map((spec) => {
          const web = isWebField(row, spec.name)
          const override = web ? overrideFor(overrides, row, spec.name) : undefined
          const shown = displayValue(spec, row[spec.name])
          return (
            <div className="fact editable-fact" key={spec.name} data-testid={`editable-${spec.name}`}>
              <dt>{spec.label}</dt>
              <dd>
                {editing === spec.name ? (
                  <form
                    className="field-editor"
                    onSubmit={(event) => {
                      event.preventDefault()
                      void submit(spec)
                    }}
                  >
                    <input
                      type={spec.kind === 'date' ? 'date' : 'text'}
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      list={spec.suggest ? `suggest-${spec.name}` : undefined}
                      aria-label={`Nuevo valor de ${spec.label}`}
                      maxLength={500}
                      autoFocus
                    />
                    {spec.suggest && (
                      <datalist id={`suggest-${spec.name}`}>
                        {(suggestions[spec.name] ?? []).map((value) => (
                          <option key={value} value={value} />
                        ))}
                      </datalist>
                    )}
                    <button type="submit" className="btn small" disabled={busy}>
                      Guardar
                    </button>
                    <button
                      type="button"
                      className="btn alt small"
                      disabled={busy}
                      onClick={() => {
                        setEditing(null)
                        setError(null)
                      }}
                    >
                      Cancelar
                    </button>
                  </form>
                ) : (
                  <>
                    <span>{shown || <span className="hint">Sin dato</span>}</span>
                    {web && (
                      <>
                        {' '}
                        <WebChip title={webTooltip(override, spec)} />
                      </>
                    )}
                    {editable(spec) && (
                      <>
                        {' '}
                        <button
                          type="button"
                          className="btn-link"
                          aria-label={`Editar ${spec.label}`}
                          onClick={() => start(spec)}
                        >
                          Editar
                        </button>
                      </>
                    )}
                    {canEdit && override && (
                      <>
                        {' '}
                        <button
                          type="button"
                          className="btn-link"
                          disabled={busy}
                          onClick={() => void revert(override)}
                        >
                          Volver al valor de la planilla
                        </button>
                      </>
                    )}
                  </>
                )}
              </dd>
            </div>
          )
        })}
      </dl>
    </section>
  )
}
```

- [ ] **Step 4: Wire the drawer** (`src/components/RowDetailDrawer.tsx`)

Add imports:

```tsx
import { type TranselecOverride, listOverrides } from '../api'
import { type EditableFieldName } from '../api'
import { loadSuggestions } from '../lib/webEdits'
import { EditableFieldsSection } from './EditableFieldsSection'
```

Merge them into the existing `'../api'` import, which already imports from that module.

Extend the props:

```tsx
export function RowDetailDrawer({
  row,
  onClose,
  sourceFields,
  canEdit = false,
  activeImportId = null,
  onRowEdited,
}: {
  row: ResumenRow
  onClose: () => void
  /** The published version's source fields; null/undefined while unknown. */
  sourceFields?: readonly string[] | null
  /** Operator/admin: offer web edits (the server re-enforces Action.EDIT). */
  canEdit?: boolean
  activeImportId?: number | null
  onRowEdited?: (row: ResumenRow) => void
}) {
```

Add state next to the others:

```tsx
  const [reloadToken, setReloadToken] = useState(0)
  const [overrides, setOverrides] = useState<TranselecOverride[]>([])
  const [suggestions, setSuggestions] = useState<Partial<Record<EditableFieldName, string[]>>>({})
```

Change the detail effect so it re-runs on `reloadToken` and, on a reload only, re-targets the shown row to its fresh copy:

```tsx
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setDetail(null)
    setFailure(null)

    void getPmfDetail(row.pmf).then((result) => {
      if (cancelled) return
      if (result.ok) {
        setDetail(result.data)
        // After a save or a reload, show the fresh copy of the row being read.
        if (reloadToken > 0) {
          setCurrent(
            (previous) =>
              result.data.rows.find(
                (entry) => entry.source_row_number === previous.source_row_number,
              ) ?? previous,
          )
        }
      } else setFailure(classifyFailure({ status: result.status, error: result.error }))
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [row.pmf, reloadToken])

  useEffect(() => {
    let cancelled = false
    void listOverrides({ pmf: row.pmf }).then((result) => {
      if (!cancelled) setOverrides(result.ok ? result.data : [])
    })
    return () => {
      cancelled = true
    }
  }, [row.pmf, reloadToken])

  useEffect(() => {
    if (!canEdit || activeImportId === null) return
    let cancelled = false
    void loadSuggestions(activeImportId).then((values) => {
      if (!cancelled) setSuggestions(values)
    })
    return () => {
      cancelled = true
    }
  }, [canEdit, activeImportId])
```

Render the section right after the closing `</section>` of «Tramitación»:

```tsx
        {(canEdit || (current.web_fields ?? []).length > 0) && (
          <EditableFieldsSection
            row={current}
            activeImportId={activeImportId}
            canEdit={canEdit}
            sourceFields={sourceFields ?? null}
            overrides={overrides}
            suggestions={suggestions}
            onSaved={(updated) => {
              setCurrent(updated)
              setReloadToken((value) => value + 1)
              onRowEdited?.(updated)
            }}
            onReload={() => setReloadToken((value) => value + 1)}
          />
        )}
```

- [ ] **Step 5: Chips in the table, wiring in Explorador and App, CSS**

`src/components/RowsTable.tsx`: import `WebChip` and `isWebField`. Replace the Estado resumido cell and the N.º ingreso cell with:

```tsx
              <td>
                <StatusPill value={row.estado_resumido} />
                {isWebField(row, 'estado_resumido') && (
                  <>
                    {' '}
                    <WebChip title="Editado en la web" />
                  </>
                )}
              </td>
```

```tsx
              <td>
                {cell(row.numero_ingreso)}
                {isWebField(row, 'numero_ingreso') && (
                  <>
                    {' '}
                    <WebChip title="Editado en la web" />
                  </>
                )}
              </td>
```

`src/pages/ExploradorPage.tsx`: add `canEdit = false` to the destructured props and `canEdit?: boolean` to the prop type, with the doc comment `/** Operator/admin: the drawer offers web edits. */`. Pass these to the drawer:

```tsx
        <RowDetailDrawer
          row={openRow}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
          canEdit={canEdit}
          activeImportId={activeImportId}
          onRowEdited={(updated) =>
            setRows(
              (current) =>
                current?.map((entry) =>
                  entry.source_row_number === updated.source_row_number ? updated : entry,
                ) ?? current,
            )
          }
        />
```

`src/App.tsx`: in `case ROUTES.explorador`, add `canEdit={publisher}` to `<ExploradorPage …/>`. `publisher` is `canPublishFor(me)`, the same operator/admin rule as `canEdit`.

`src/styles/components.css`, appended after the `.flag` rule:

```css
/* The «web» mark: a value that came from a dashboard edit (web edits spec §6).
   Same yellow as the fill written into the downloaded planilla. */
.web-chip {
  display: inline-block;
  padding: 0 var(--s-2);
  border: 1px solid #e6c35c;
  border-radius: var(--r-pill);
  background: #fff2cc;
  color: #6b5200;
  font-size: var(--t-micro);
  font-weight: 650;
  letter-spacing: 0.02em;
  vertical-align: middle;
}

.field-editor {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  align-items: center;
}

.field-editor input {
  min-width: 12ch;
}
```

If `--s-2` is not defined in `src/styles/*.css`, use `--s-3`. Check with `grep -n -- '--s-2:' src/styles/*.css`.

- [ ] **Step 6: Run the tests, the type check and lint**

Run: `cd products/transelect/dashboard && npm test && npx tsc -b && npm run lint`
Expected: PASS. The existing `RowDetailDrawer.test.tsx` mocks only `getPmfDetail` and `getAef`, so `listOverrides` now runs unmocked and may fail the test environment's fetch. If it does, add `listOverrides: vi.fn().mockResolvedValue({ ok: true, data: [] })` to that file's `vi.mock('../api', …)` factory.

- [ ] **Step 7: Commit**

```bash
git add products/transelect/dashboard/src
git commit -m "feat(transelec-dashboard): edit fields from the drawer, «web» chips in Explorador"
```

---

### Task 10: Datos → «Ediciones web», Calidad block

**Files:**
- Create: `src/pages/EdicionesPage.tsx`, `src/pages/EdicionesPage.test.tsx`, `src/components/WebEditConflicts.tsx`
- Modify:
  - `src/router.tsx` (`ROUTES`, `ADMIN_ROUTES`, ~20-40);
  - `src/pages/DatosPage.tsx`;
  - `src/pages/CalidadPage.tsx` (props and a block after the header);
  - `src/App.tsx` (Datos cases ~214-226, Calidad case ~212);
  - `apps/api/app/main.py` (`TRANSELEC_SPA_PAGE_PATHS`).

**Interfaces:**
- Consumes: Task 8.
- Produces:
  - `ROUTES.ediciones = '/transelec/ediciones'` (admin route);
  - `EdicionesPage()`;
  - `WebEditConflicts({ canEdit })`;
  - `CalidadPage({ filterController, canEdit })`.

- [ ] **Step 1: Write the failing test** (`src/pages/EdicionesPage.test.tsx`)

```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TranselecOverride } from '../api'
import { RouterProvider } from '../router'
import { EdicionesPage } from './EdicionesPage'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, listOverrides: vi.fn(), keepOverride: vi.fn(), discardOverride: vi.fn() }
})

const { listOverrides, keepOverride } = await import('../api')

const make = (id: number, status: TranselecOverride['status']): TranselecOverride => ({
  id,
  field: 'estado_resumido',
  field_label: 'Estado resumido',
  status,
  pmf: `MP00${id}`,
  rol: '1',
  numero_predio: '1',
  numero_area_corta: 'A1',
  source_row_number: status === 'huerfana' ? null : id + 1,
  web_value: 'Aprobado',
  planilla_value_at_edit: 'En tramite',
  planilla_value_now: status === 'en_conflicto' ? 'Desistido' : 'En tramite',
  created_by_display_name: 'Ana Pérez',
  created_at: '2026-10-04T15:00:00+00:00',
})

describe('EdicionesPage', () => {
  beforeEach(() => {
    vi.mocked(listOverrides).mockReset()
    vi.mocked(keepOverride).mockReset()
  })

  it('lists edits, says what the download writes, and keeps a conflict', async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, 'en_conflicto'), make(2, 'huerfana'), make(3, 'aplicada')],
    })
    vi.mocked(keepOverride).mockResolvedValue({ ok: true, data: { override_id: 9 } })
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    )

    expect(await screen.findByTestId('download-xlsx')).toHaveAttribute(
      'href',
      '/api/transelec/export.xlsx',
    )
    expect(screen.getByTestId('download-note')).toHaveTextContent('1 celda editada marcada')
    expect(screen.getByTestId('download-note')).toHaveTextContent('2 ediciones no se escriben')
    const conflict = screen.getByTestId('override-1')
    expect(conflict).toHaveTextContent('Desistido')
    await userEvent.click(within(conflict).getByRole('button', { name: 'Mantener valor web' }))
    expect(keepOverride).toHaveBeenCalledWith(1)
  })

  it('says so when nobody edited anything', async () => {
    vi.mocked(listOverrides).mockResolvedValue({ ok: true, data: [] })
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    )
    expect(await screen.findByTestId('overrides-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd products/transelect/dashboard && npx vitest run src/pages/EdicionesPage.test.tsx`
Expected: FAIL with `Failed to resolve import "./EdicionesPage"`.

- [ ] **Step 3: Write `src/pages/EdicionesPage.tsx`**

```tsx
/**
 * The Datos section's «Ediciones web» pane (web edits spec §6).
 *
 * Every active edit against the published version, with conflicts and
 * orphans first because those are the ones that need a decision: the
 * planilla wins until someone keeps or discards the web value. The download
 * writes only applied edits into the uploaded file; the note above the table
 * says how many and why the rest are left out.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  type TranselecOverride,
  discardOverride,
  exportXlsxUrl,
  keepOverride,
  listOverrides,
} from '../api'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { formatDate, formatInteger } from '../format'
import { classifyFailure, type FailureView } from '../lib/apiState'
import { STATUS_LABELS, displayValue, specFor } from '../lib/webEdits'
import { Link, ROUTES } from '../router'
import { SectionHeader } from '../ui/Primitives'

export function EdicionesPage() {
  const [overrides, setOverrides] = useState<TranselecOverride[] | null>(null)
  const [failure, setFailure] = useState<FailureView | null>(null)
  const [actionError, setActionError] = useState<FailureView | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let cancelled = false
    void listOverrides().then((result) => {
      if (cancelled) return
      if (result.ok) {
        setOverrides(result.data)
        setFailure(null)
      } else setFailure(classifyFailure(result))
    })
    return () => {
      cancelled = true
    }
  }, [reloadToken])

  const act = useCallback(async (override: TranselecOverride, action: 'keep' | 'discard') => {
    setBusyId(override.id)
    setActionError(null)
    const result =
      action === 'keep' ? await keepOverride(override.id) : await discardOverride(override.id)
    setBusyId(null)
    if (!result.ok) {
      setActionError(classifyFailure(result))
      return
    }
    setReloadToken((value) => value + 1)
  }, [])

  if (failure) return <StateBlock view={failure} />
  if (!overrides) return <LoadingBlock label="Cargando las ediciones web…" lines={3} />

  const applied = overrides.filter((entry) => entry.status === 'aplicada').length
  const notWritten = overrides.filter(
    (entry) => entry.status === 'en_conflicto' || entry.status === 'huerfana',
  ).length

  return (
    <div className="stack datos-pane">
      <section>
        <SectionHeader
          title="Ediciones web"
          meta="Valores cambiados en el panel sobre la versión publicada. La planilla publicada no se modifica."
        />
        <div className="btns no-print">
          <a className="btn" href={exportXlsxUrl()} download data-testid="download-xlsx">
            Descargar planilla con ediciones (.xlsx)
          </a>
        </div>
        <p className="hint" data-testid="download-note">
          Es la misma planilla que se publicó, con {formatInteger(applied)}{' '}
          {applied === 1 ? 'celda editada marcada' : 'celdas editadas marcadas'} «web» (color y
          nota de Excel).
          {notWritten > 0 &&
            ` ${formatInteger(notWritten)} ${notWritten === 1 ? 'edición no se escribe' : 'ediciones no se escriben'} porque la planilla cambió o la fila ya no existe; revíselas abajo.`}
        </p>
        {actionError && <AlertBanner title={actionError.title}>{actionError.message}</AlertBanner>}

        {overrides.length === 0 ? (
          <div className="empty" data-testid="overrides-empty">
            Nadie ha editado valores en el panel para la versión publicada.
          </div>
        ) : (
          <div className="tablewrap">
            <table className="rows-table" data-testid="overrides-table">
              <thead>
                <tr>
                  <th scope="col">Estado</th>
                  <th scope="col">PMF</th>
                  <th scope="col" className="numeric">
                    Fila
                  </th>
                  <th scope="col">Campo</th>
                  <th scope="col">En la planilla</th>
                  <th scope="col">Valor web</th>
                  <th scope="col">Editado por</th>
                  <th scope="col">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {overrides.map((entry) => {
                  const spec = specFor(entry.field)
                  const planilla =
                    entry.status === 'en_conflicto'
                      ? entry.planilla_value_now
                      : entry.planilla_value_at_edit
                  return (
                    <tr key={entry.id} data-testid={`override-${entry.id}`} data-status={entry.status}>
                      <td>{STATUS_LABELS[entry.status]}</td>
                      <td>
                        <b>{entry.pmf}</b>
                      </td>
                      <td className="numeric">{entry.source_row_number ?? '—'}</td>
                      <td>{entry.field_label}</td>
                      <td>{displayValue(spec, planilla) || '(vacía)'}</td>
                      <td>{displayValue(spec, entry.web_value) || '(vacía)'}</td>
                      <td>
                        {entry.created_by_display_name} · {formatDate(entry.created_at)}
                      </td>
                      <td>
                        {entry.status === 'en_conflicto' && (
                          <button
                            type="button"
                            className="btn alt small"
                            disabled={busyId === entry.id}
                            onClick={() => void act(entry, 'keep')}
                          >
                            Mantener valor web
                          </button>
                        )}{' '}
                        <button
                          type="button"
                          className="btn-link"
                          disabled={busyId === entry.id}
                          onClick={() => void act(entry, 'discard')}
                        >
                          Descartar
                        </button>{' '}
                        {entry.source_row_number !== null && (
                          <Link to={`${ROUTES.explorador}?q=${encodeURIComponent(entry.pmf)}`}>
                            Ver fila
                          </Link>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Route, Datos tab, SPA path, Calidad block**

`src/router.tsx`: add `ediciones: '/transelec/ediciones',` to `ROUTES` after `accesos`, and `ROUTES.ediciones` to `ADMIN_ROUTES`.

`apps/api/app/main.py`: add `"transelec/ediciones",` to `TRANSELEC_SPA_PAGE_PATHS`. `apps/api/tests/test_dashboard_static.py::test_spa_page_paths_match_every_dashboard_route` enforces the match.

`src/pages/DatosPage.tsx`:

```tsx
import { EdicionesPage } from './EdicionesPage'
```

```tsx
  const pane =
    route === ROUTES.versiones
      ? 'versiones'
      : route === ROUTES.accesos
        ? 'accesos'
        : route === ROUTES.ediciones
          ? 'ediciones'
          : 'importar'
```

In `content()`, before the Accesos branch:

```tsx
    if (pane === 'ediciones') {
      return <EdicionesPage />
    }
```

In the tab `nav`, after the Versiones link:

```tsx
        <Link to={ROUTES.ediciones} current={pane === 'ediciones'}>
          Ediciones web
        </Link>
```

`src/components/WebEditConflicts.tsx`:

```tsx
/**
 * Calidad: how many web edits the published planilla now contradicts or no
 * longer has a row for. Hidden when there are none (web edits spec §6).
 */
import { useEffect, useState } from 'react'
import { listOverrides } from '../api'
import { formatInteger } from '../format'
import { Link, ROUTES } from '../router'
import { SectionHeader } from '../ui/Primitives'

export function WebEditConflicts({ canEdit }: { canEdit: boolean }) {
  const [counts, setCounts] = useState<{ conflicts: number; orphans: number } | null>(null)

  useEffect(() => {
    let cancelled = false
    void listOverrides().then((result) => {
      if (cancelled || !result.ok) return
      setCounts({
        conflicts: result.data.filter((entry) => entry.status === 'en_conflicto').length,
        orphans: result.data.filter((entry) => entry.status === 'huerfana').length,
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (!counts || counts.conflicts + counts.orphans === 0) return null

  return (
    <section className="ruled" aria-labelledby="web-conflicts-title" data-testid="web-edit-conflicts">
      <SectionHeader
        id="web-conflicts-title"
        title="Ediciones web en conflicto"
        meta="La planilla publicada manda: el panel muestra su valor hasta que alguien decida."
      />
      <p className="prose">
        {formatInteger(counts.conflicts)}{' '}
        {counts.conflicts === 1 ? 'edición difiere' : 'ediciones difieren'} de la planilla
        publicada y {formatInteger(counts.orphans)}{' '}
        {counts.orphans === 1 ? 'ya no tiene fila' : 'ya no tienen fila'} en ella.{' '}
        {canEdit && <Link to={ROUTES.ediciones}>Revisarlas en Datos → Ediciones web</Link>}
      </p>
    </section>
  )
}
```

If `SectionHeader` does not accept `id`, check `src/ui/Primitives.tsx:20`. CalidadPage already passes `id=`, so it does.

`src/pages/CalidadPage.tsx`:
- add `canEdit = false` to the props (`{ filterController, canEdit = false }: { filterController: FilterController; canEdit?: boolean }`);
- import `WebEditConflicts`;
- render `<WebEditConflicts canEdit={canEdit} />` as the first child of `<div className="stack">`.

`src/App.tsx`:
- `case ROUTES.calidad: return <CalidadPage filterController={filterController} canEdit={publisher} />`;
- add `case ROUTES.ediciones:` to the Datos case group.

- [ ] **Step 5: Run every dashboard check plus the SPA-path test**

```bash
cd products/transelect/dashboard && npm test && npx tsc -b && npm run lint && cd -
uv run pytest apps/api/tests/test_dashboard_static.py -q
```

Expected: PASS. If the `navigation.spec.ts` e2e or a vitest snapshot counts the Datos tabs, update the expected count. It is one new tab, by design.

- [ ] **Step 6: Commit**

```bash
git add products/transelect/dashboard/src apps/api/app/main.py
git commit -m "feat(transelec-dashboard): «Ediciones web» pane with the download, Calidad conflicts block"
```

---

### Task 11: End-to-end tests

**Files:**
- Modify: `products/transelect/dashboard/tests/e2e/stubs.ts`:
  - `StubOptions` gains `rowOverrides?: (index: number) => Record<string, unknown>`;
  - a default `/overrides*` route goes before `options.extra`;
  - the `/pmfs?*` handler uses `rowOverrides`.
- Create: `products/transelect/dashboard/tests/e2e/web-edits.spec.ts`

**Interfaces:**
- Consumes: Tasks 8-10.
- Produces: a Playwright spec covering:
  - edit and save;
  - a 409;
  - a viewer with no controls but a chip;
  - the Datos pane with keep and the download link;
  - the Calidad block.

- [ ] **Step 1: Extend the stubs**

In `StubOptions`:

```ts
  /** Extra fields merged into every list row (`/pmfs?`), by 1-based row index. */
  rowOverrides?: (index: number) => Record<string, unknown>
```

Right after the `**/api/transelec/pmfs/*` default route, before `if (options.extra)`:

```ts
  // Web edits: none by default. Registered before `options.extra` so a test's
  // own handler wins (Playwright matches the most recently added route first).
  await page.route('**/api/transelec/overrides*', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, [])
  })
```

In the `**/api/transelec/pmfs?*` handler:

```ts
      items: Array.from({ length: size }, (_, offset) =>
        makeApiRow(cursor + offset + 1, options.rowOverrides?.(cursor + offset + 1) ?? {}),
      ),
```

- [ ] **Step 2: Write `tests/e2e/web-edits.spec.ts`**

```ts
/**
 * Web edits (docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md §6):
 * edit from the drawer, the 409 path, what a viewer sees, the Datos pane and
 * the Calidad block. The API is stubbed; the server-side rules have their own
 * integration tests.
 */
import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { makeApiRow, stubPlatform } from './stubs'

const OVERRIDE = {
  id: 31,
  field: 'estado_resumido',
  field_label: 'Estado resumido',
  status: 'aplicada',
  pmf: 'PMF-001',
  rol: '101-1',
  numero_predio: '10',
  numero_area_corta: 'A1',
  source_row_number: 1,
  web_value: 'Aprobado',
  planilla_value_at_edit: 'En tramite',
  planilla_value_now: 'En tramite',
  created_by_display_name: 'Dev Admin',
  created_at: '2026-10-04T15:00:00+00:00',
}

const VIEWER = {
  identity_key: 'dev-viewer',
  display_name: 'Dev Viewer',
  product_grants: [{ product_key: 'transelect', role: 'viewer' }],
}

function fulfill(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function openFirstRow(page: Page) {
  await page.goto('/transelec/explorador')
  await page.getByTestId('row-1').click()
  return page.getByTestId('row-drawer')
}

test('an operator edits Estado resumido from the drawer and sees the «web» chip', async ({
  page,
}) => {
  let sent: unknown = null
  await stubPlatform(page, {
    extra: async (p) => {
      await p.route('**/api/transelec/overrides', async (route) => {
        if (route.request().method() !== 'PUT') return route.fallback()
        sent = route.request().postDataJSON()
        await fulfill(route, {
          override_id: 31,
          changed: true,
          row: makeApiRow(1, { estado_resumido: 'Aprobado', web_fields: ['estado_resumido'] }),
        })
      })
    },
  })

  const drawer = await openFirstRow(page)
  await drawer.getByRole('button', { name: 'Editar Estado resumido' }).click()
  await drawer.getByLabel('Nuevo valor de Estado resumido').fill('Aprobado')
  await drawer.getByRole('button', { name: 'Guardar' }).click()

  await expect(drawer.getByTestId('editable-estado_resumido').getByTestId('web-chip')).toBeVisible()
  expect(sent).toEqual({
    import_id: 7,
    source_row_number: 1,
    field: 'estado_resumido',
    value: 'Aprobado',
    expected_value: 'En tramite',
  })
})

test('a concurrent change is explained and nothing is overwritten', async ({ page }) => {
  await stubPlatform(page, {
    extra: async (p) => {
      await p.route('**/api/transelec/overrides', async (route) => {
        if (route.request().method() !== 'PUT') return route.fallback()
        await fulfill(route, { detail: 'x', code: 'value_changed' }, 409)
      })
    },
  })

  // The stubbed active version's source_fields list Estado resumido but not
  // Estado, so only Estado resumido is offered for editing here.
  const drawer = await openFirstRow(page)
  await drawer.getByRole('button', { name: 'Editar Estado resumido' }).click()
  await drawer.getByLabel('Nuevo valor de Estado resumido').fill('Aprobado')
  await drawer.getByRole('button', { name: 'Guardar' }).click()

  await expect(drawer.getByRole('alert')).toContainText('Otra persona cambió este valor')
  await expect(drawer.getByRole('button', { name: 'Recargar' })).toBeVisible()
})

test('a viewer sees the chip and who edited, but no edit controls', async ({ page }) => {
  await stubPlatform(page, {
    me: VIEWER,
    rowOverrides: (index) =>
      index === 1 ? { estado_resumido: 'Aprobado', web_fields: ['estado_resumido'] } : {},
    extra: async (p) => {
      await p.route('**/api/transelec/overrides*', (route) => fulfill(route, [OVERRIDE]))
    },
  })

  await page.goto('/transelec/explorador')
  await expect(page.getByTestId('row-1').getByTestId('web-chip')).toBeVisible()
  await page.getByTestId('row-1').click()
  const drawer = page.getByTestId('row-drawer')
  const chip = drawer.getByTestId('editable-estado_resumido').getByTestId('web-chip')
  await expect(chip).toHaveAttribute('title', /Editado en la web por Dev Admin · 04-10-2026/)
  await expect(drawer.getByRole('button', { name: /^Editar/ })).toHaveCount(0)
})

test('Datos → Ediciones web lists conflicts first, keeps one, and offers the download', async ({
  page,
}) => {
  let kept = false
  await stubPlatform(page, {
    extra: async (p) => {
      await p.route('**/api/transelec/overrides*', async (route) => {
        if (route.request().method() === 'POST' && route.request().url().endsWith('/31/keep')) {
          kept = true
          return fulfill(route, { override_id: 32 })
        }
        return fulfill(route, [
          { ...OVERRIDE, status: 'en_conflicto', planilla_value_now: 'Desistido' },
        ])
      })
    },
  })

  await page.goto('/transelec/ediciones')
  await expect(page.getByTestId('download-xlsx')).toHaveAttribute('href', '/api/transelec/export.xlsx')
  const conflict = page.getByTestId('override-31')
  await expect(conflict).toContainText('En conflicto con la planilla')
  await expect(conflict).toContainText('Desistido')
  await conflict.getByRole('button', { name: 'Mantener valor web' }).click()
  await expect.poll(() => kept).toBe(true)
})

test('Calidad shows the conflicts block only when there are conflicts', async ({ page }) => {
  await stubPlatform(page, {
    extra: async (p) => {
      await p.route('**/api/transelec/overrides*', (route) =>
        fulfill(route, [{ ...OVERRIDE, status: 'en_conflicto' }]),
      )
    },
  })
  await page.goto('/transelec/calidad')
  await expect(page.getByTestId('web-edit-conflicts')).toContainText('1 edición difiere')
})
```

- [ ] **Step 3: Run the full e2e suite**

Run: `cd products/transelect/dashboard && npm run test:e2e`
Expected: PASS. That includes the existing specs: the default `/overrides*` stub returns `[]`, so the drawer and Calidad behave as before for them.

- [ ] **Step 4: Commit**

```bash
git add products/transelect/dashboard/tests/e2e
git commit -m "test(transelec-dashboard): e2e for web edits, the Datos pane and Calidad"
```

---

### Task 12: Docs and full verification

**Files:**
- Modify: `products/transelect/README.md` (Dashboard section)
- Modify: `products/transelect/dashboard/README.md` (Routes table)
- Modify: `docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md` (Status line only)

**Interfaces:**
- Consumes: everything above.
- Produces: documentation that matches the code.

- [ ] **Step 1: Update the docs**

`products/transelect/dashboard/README.md` Routes table. Add:

```markdown
| `/transelec/ediciones` | operator/admin | Web edits against the published version and the planilla download marked «web» |
```

Extend the `/transelec/datos` row's purpose with "and web edits".

`products/transelect/README.md`, Dashboard section. Add this paragraph:

```markdown
Operators and administrators can correct eleven status and ingreso fields
from the row drawer; every view shows the edited value with a «web» mark,
and Datos → Ediciones web downloads the uploaded planilla with only those
cells changed, highlighted and annotated. See
[the web-edits design][web-edits-spec].

[web-edits-spec]: ../../docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
```

Spec status line: replace "this file awaits his review before a plan is written" with "implemented on `feat/transelec-web-edits` ([plan](../plans/2026-10-04-transelec-web-edits-xlsx.md))".

- [ ] **Step 2: Run every check**

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy . && uv run pytest
uv run python scripts/check_architecture_boundaries.py
make migration-check
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests
(cd products/transelect/dashboard && npm test && npm run lint && npm run build && npm run test:e2e)
uv run python scripts/update_doc_nav.py && uv run python scripts/check_doc_links.py
```

Expected: all PASS; "Documentation links OK".

- [ ] **Step 3: Commit**

```bash
git add products/transelect/README.md products/transelect/dashboard/README.md docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md
git commit -m "docs(transelec): web edits in the product and dashboard READMEs"
```

---

### Task 13: Manual check against the real planilla (not in CI)

**Files:** none in the repository. Everything stays in a scratchpad outside the repo and is deleted afterwards (`.claude/skills/transelec-workbook/SKILL.md`).

**Interfaces:**
- Consumes: `patch_workbook` (Task 6), `load_transelec_workbook`.
- Produces: a go/no-go from Rafael after opening the result in Excel.

- [ ] **Step 1: Patch a copy outside the repo and verify**

`PlanillaMaestra-CD_30sep2026.xlsx` stays in `/mnt/c/Users/Rafael/Downloads/` and is only read. Print counts and booleans only, never cell values.

```bash
OUT=$(mktemp -d)
uv run python - "$OUT" <<'EOF'
import datetime as dt, sys, time, zipfile
from pathlib import Path
from transelec_ingestion.xlsx_contract import load_transelec_workbook
from transelec_ingestion.xlsx_web_patch import CellEdit, patch_workbook

src = Path("/mnt/c/Users/Rafael/Downloads/PlanillaMaestra-CD_30sep2026.xlsx")
out = Path(sys.argv[1]) / "planilla_web_check.xlsx"
wb = load_transelec_workbook(src)
cols = {f.field: f.column for f in wb.layout.fields}
row = wb.resumen_rows[3].source_row_number
edits = [
    CellEdit(row, cols["estado_resumido"], "text", "WEB-PRUEBA", "web · prueba · 04-10-2026 · antes: x"),
    CellEdit(row, cols["tipo_rechazo"], "text", "WEB-PRUEBA", "web · prueba"),
    CellEdit(row, cols["fecha_ingreso_2"], "date", dt.date(2026, 9, 1), "web · prueba"),
]
start = time.time()
result = patch_workbook(src, out, sheet_name=wb.layout.sheet_name, edits=edits)
print("seconds", round(time.time() - start, 1), "written", len(result.written), "skipped", len(result.skipped))
a, b = zipfile.ZipFile(src), zipfile.ZipFile(out)
print("untouched parts differing:", [n for n in a.namelist() if n not in result.touched_parts and a.read(n) != b.read(n)])
back = load_transelec_workbook(out)
print("rows", len(back.resumen_rows), "errors", back.layout.count("error"))
print("file for Excel:", out)
EOF
```

Expected:
- `written 3 skipped 0`;
- `untouched parts differing: []`;
- `rows 729 errors 0`;
- under ~5 s.

- [ ] **Step 2: Rafael opens the file in Excel**

Ask Rafael to copy the printed path to Windows and open it in Excel. He confirms:
1. no "We found a problem with some content" prompt;
2. the three cells are light yellow and each has a note;
3. the pivots on «Resumen» refreshed;
4. the other six sheets look unchanged.

Record his answer in the PR description, without values.

- [ ] **Step 3: Delete the scratch output**

```bash
rm -rf "$OUT"
```

---

### Task 14: Rebase after the sibling PRs and prove `/lifecycle` and `/plazos` see web edits

Run this task only after the Estado and 90-días PRs are merged into `main`.

**Files:**
- Test: `apps/api/integration_tests/test_transelec_overrides.py` (append)
- Modify: the dashboard page the Estado PR created (`src/pages/EstadoPage.tsx`) and `src/App.tsx`, so its drawer can edit.

**Interfaces:**
- Consumes:
  - `GET /transelec/lifecycle` (Estado plan, Task 2; not `/estado`, which is the dashboard page path): `TranselecLifecycleResponse.rows[]`, each a `LifecyclePmfRowView` with `pmf` and `lifecycle_group`;
  - `GET /transelec/plazos` (plazo plan, Task 3): `TranselecPlazosResponse.pmfs[]`, each a `PlazoPmfView` with `pmf`, `base_field` and `estado` (the plazo status).
  - Both read through `_fetch_filtered_rows`, so they read the effective view.
- Produces: proof that both bases see web edits, and the Estado page's drawer offering edits.

- [ ] **Step 1: Check the sibling routes exist on main, then rebase**

```bash
git fetch origin
git grep -n '"/lifecycle"\|"/plazos"' origin/main -- apps/api/app/routers/transelec.py
```

Expected: both routes found. If either is missing, stop: the sibling PRs are not merged yet.

```bash
git rebase origin/main
```

Resolve conflicts. The expected ones are `ROUTES` / `TRANSELEC_SPA_PAGE_PATHS` (keep both `estado` and `ediciones`), `App.tsx`, `stubs.ts` and `api.ts` (keep both sides). Re-run Task 12 Step 2.

- [ ] **Step 2: Write the integration test** (append)

The Estado spec's rule says *Estado resumido* «Aprobado» together with *Estado* «Aprobado» is group `aprobado`, and *Estado resumido* «En tramite» with *Estado* «Aprobado» is `sin_clasificar`. So editing *Estado resumido* must move the PMF. MP002's raw-text *Fecha de ingreso* gives `sin_fecha_texto` until a web date replaces it.

```python
# ---------------------------------------------------------------------------
# Sibling bases read web edits (Task 14)
# ---------------------------------------------------------------------------


def _pmf_entry(client: TestClient, path: str, list_key: str, pmf: str) -> dict[str, Any]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return next(entry for entry in response.json()[list_key] if entry["pmf"] == pmf)


def test_estado_and_plazos_read_web_edits(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    rows = [dict(item) for item in _BASE_ROWS]
    rows[0]["estado"] = "Aprobado"  # contradicts its Estado resumido «En tramite»
    import_id = _publish(client, _workbook(tmp_path, "siblings.xlsx", rows))

    assert _pmf_entry(client, "/transelec/lifecycle", "rows", "MP001")["lifecycle_group"] != "aprobado"
    first = _row(client, "MP001", 0)["source_row_number"]
    saved = _put(client, import_id, first, "estado_resumido", "Aprobado", expected="En tramite")
    assert saved.status_code == 200, saved.text
    assert _pmf_entry(client, "/transelec/lifecycle", "rows", "MP001")["lifecycle_group"] == "aprobado"

    assert _pmf_entry(client, "/transelec/plazos", "pmfs", "MP002")["estado"] == "sin_fecha_texto"
    mp002 = _row(client, "MP002")["source_row_number"]
    saved = _put(client, import_id, mp002, "fecha_ingreso", "2026-06-01", expected=None)
    assert saved.status_code == 200, saved.text
    plazo = _pmf_entry(client, "/transelec/plazos", "pmfs", "MP002")
    assert plazo["base_field"] == "fecha_ingreso"
    assert plazo["estado"] != "sin_fecha_texto"
```

The key names above come from the sibling plans (`TranselecLifecycleResponse`, `PlazoPmfView`). If review changed them before merge, align `_pmf_entry`'s callers with `grep -n "class TranselecLifecycleResponse\|class LifecyclePmfRowView\|class PlazoPmfView" apps/api/app/routers/transelec.py`, keeping the assertions' meaning.

- [ ] **Step 3: Run it**

```bash
APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api uv run pytest -q apps/api/integration_tests/test_transelec_overrides.py -k siblings
```

Expected: PASS with no production-code change. Both sibling routes read `_fetch_filtered_rows`. If one fails because it issues its own SQL against `transelec_resumen_row`, change that `FROM` to `platform.transelec_effective_row` (as in Task 3) and re-run.

- [ ] **Step 4: Let the Estado page's drawer edit**

Add `canEdit?: boolean` and `activeImportId: number | null` to `EstadoPage`'s props, and pass them into its `RowDetailDrawer` exactly as `ExploradorPage` does (Task 9 Step 5). In `App.tsx`'s `case ROUTES.estado`, pass `canEdit={publisher}` and `activeImportId={activeImport?.import_id ?? null}`.

Extend `tests/e2e/web-edits.spec.ts` with one test. Open `/transelec/estado`, click the first queue row (its test id is defined by the Estado PR; find it with `grep -n "data-testid" src/pages/EstadoPage.tsx`), and assert `getByRole('button', { name: 'Editar Estado resumido' })` is visible in the drawer.

- [ ] **Step 5: Full verification and commit**

Re-run Task 12 Step 2 in full.

```bash
git add apps/api/integration_tests/test_transelec_overrides.py products/transelect/dashboard
git commit -m "test(transelec): Estado and 90 días read web edits; edit from the Estado drawer"
```

---

## Self-review (done while writing; kept for the reviewer)

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 storage | 2 |
| §2 status and comparison | 1, 2 |
| §2 retirement on activation | 4 |
| §3 one read layer, `web_fields` | 3 |
| §4 routes, `Action.EDIT`, 409 codes, 422s, audit | 4, 5 |
| §5 download | 6, 7 |
| §6 drawer, chip, Explorador | 9 |
| §6 Datos pane | 10 |
| §6 Calidad | 10 |
| §6 api.ts and `canEdit` | 8 |
| Testing: product | 1, 6 |
| Testing: integration | 3-5, 7 |
| Testing: migration | 2 |
| Testing: vitest and e2e | 8-11 |
| Testing: manual Excel | 13 |
| Risks: download time | measured in 13; 1.9 s in the prototype |
| Risks: restore limitation | documented in the spec; behaviour follows from 4 |
| Risks: text-level XML | refusal paths tested in 6 |

**Where the plan refines the spec** (call these out in the PR):
1. A text value is written as a number when the original cell was numeric **or absent**. The spec says only "when the original cell was numeric". The real planilla omits blank cells entirely (seen for `Tipo de rechazo` / `Reingreso_*` / `…2` cells), so an absent cell must accept a number.
2. An edit of a field the published planilla has no column for is refused (422). The spec is silent; without this it could never be downloaded.
3. Retirement of incorporated edits runs in `_activate` (router), inside the same activation transaction. `transelec_publication.activate_import` stays free of edit knowledge.
4. The note date and the filename date use PostgreSQL's `America/Santiago`, avoiding a Python `tzdata` dependency.
5. The new Datos pane needs `transelec/ediciones` in `TRANSELEC_SPA_PAGE_PATHS` (enforced by `test_dashboard_static.py`).
6. The view's column list is frozen in migration 0012. A future contract column needs a view-recreating migration, and `test_effective_view_exposes_every_column_the_router_selects` fails loudly if it is forgotten.

**Type consistency** was checked across tasks:
- `save_override(..., field: EditableField, value, expected)` in Tasks 4 and 5;
- `OverrideRecord.web`, `planilla_at_edit` and `planilla_now` as `Signature` in Tasks 4, 5 and 7;
- `CellEdit(row, column, kind, value, note)` in Tasks 6 and 7;
- `EditableFieldName` and `TranselecOverride` in Tasks 8-11;
- `RowDetailDrawer` props in Tasks 9 and 14.
