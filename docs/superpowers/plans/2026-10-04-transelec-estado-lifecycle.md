# Transelec «Estado» lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the «Pendientes» tab with «Estado». It shows each PMF's
lifecycle group and step (`lifecycle_pmf_v1`), the tipo de rechazo, the raw
reingreso flags, both ingresos, and a link to CONAF's Oficina Virtual. The
legacy pending rules stay reachable.

**Architecture:**
- **Classifier.** A pure module `transelec_ingestion/lifecycle_view.py`
  classifies each PMF from its first row. It mirrors `pending_view.py`: no
  database, adapters in the router.
- **Endpoint.** A new read route `GET /transelec/lifecycle` loads rows only
  through `_fetch_filtered_rows`, so the web-edits plan can swap the relation
  underneath, and hydrates each PMF's first row like `GET /pending` does.
- **Dashboard.** A new `EstadoPage` with a column-extensible `EstadoTable`;
  a redirect from `/transelec/pendientes`; a «Proceso CONAF» block in the row
  drawer; a Calidad block. The old pending zone moves, unchanged, into a
  closed «regla anterior» disclosure.

**Tech Stack:**
- Python 3.12, FastAPI, SQLAlchemy `text()` reads, Pydantic v2, pytest;
  real PostgreSQL for integration tests.
- React 19 + TypeScript, Vite, vitest + Testing Library, Playwright with
  stubbed API, oxlint.

**Spec:**
`/home/rafael/dev/freelance/campo-digital/worktrees/campo-digital-transelec-specs/docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md`.
It lives on branch `docs/transelec-estado-plazo-web-specs`, not on `main`;
read it from that absolute path. This plan sits next to it under
`docs/superpowers/plans/`.

## Global Constraints

**Rules from the spec:**
- **Matching.** Labels match exactly after
  `status_rollups.normalized_label` (case, accents and whitespace folded).
  The only exception is the whole word «aprobado» in the consistency check.
  Nothing is guessed: an unknown label or a contradiction goes to
  `sin_clasificar` with a reason.
- **Rejection.** «Rechazado» in *Estado resumido* or *Estado* is a step
  inside `en_tramite`, never terminal.
- **Closed groups.** «Descartado» and «Desistido» are separate groups,
  shown with the source word, and are never merged.
  `CLOSED_GROUPS = {"aprobado", "descartado", "desistido"}`.
- **Reingreso flags.** `Reingreso_Tec`, `Reingreso_Legal` and
  `Reingreso_RecRep` are shown raw and never interpreted.
- **Oficina Virtual.** The URL is exactly
  `https://oficinavirtual.conaf.cl/consultas/index.php`, opened with
  `target="_blank"` and `rel="noopener noreferrer"`. There is no deep link;
  a «Copiar N.º» button copies the number. The production CSP has
  `form-action 'self'`, so never post a form to CONAF.
- **Legacy reads stay.** `GET /pending`, `pending_priority_legacy` and
  `pending_stage_legacy` stay reachable and explained.
- **Copy.** All lifecycle copy is marked provisional.

**Interfaces other plans depend on:**
- **Row loading.** `/transelec/lifecycle` loads rows **only** through
  `_fetch_filtered_rows`. The web-edits plan changes the relation under it.
- **API path (DECISION, deviates from the spec's `GET /api/transelec/estado`).**
  The read is `GET /transelec/lifecycle` (browsers call
  `/api/transelec/lifecycle`). Reason: `app.main` mounts the Transelec router
  at both `/transelec` and `/api/transelec`, and `transelec/estado` becomes a
  dashboard page path in `TRANSELEC_SPA_PAGE_PATHS`. Sharing that path would
  make a page reload answer JSON. This is the same reason the AEF page is
  `seguimiento-aef`. A guard test pins the rule (Task 2).
- **Dashboard route.** The page is `ROUTES.estado = '/transelec/estado'`.
  `ROUTES.pendientes` stays one release, as a redirect.
  `TRANSELEC_SPA_PAGE_PATHS` must equal the `ROUTES` values
  (`apps/api/tests/test_dashboard_static.py::test_spa_page_paths_match_every_dashboard_route`).

**Workbook and data rules:**
- Follow `.claude/skills/transelec-workbook/SKILL.md`. Use synthetic
  fixtures only. Never open, copy, import or publish a real planilla. No
  names, predios, roles or other business values in code, tests, commits or
  PRs.

**Style:**
- **Python:** ruff (line length 100, rules E F I UP B SIM), `ruff format`,
  mypy.
- **Dashboard:** oxlint (`react/only-export-components` warns on non-component
  exports from a component file, so keep constants and arrays in `src/lib/`),
  `tsc -b`.
- **Quotes:** match each file's existing style. Most dashboard files use
  single quotes and no semicolons; `src/components/RowDetailDrawer.test.tsx`
  uses double quotes and semicolons.

**Shared test resources:**
- **Database.** Integration tests use the disposable test database on
  `127.0.0.1:5433`, shared by every worktree. Never run `make
  persistence-check` or `make migration-check`; both reset the shared
  container. Never run integration tests from two worktrees at the same time.
- **Playwright.** It serves the app on port 5299. Never run `npm run
  test:e2e` from two worktrees at the same time.

**Commits:**
- End every commit message with the line
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Do not push or open a PR until Rafael asks (Task 8).

## Review Focus

1. **A reload of `/transelec/estado` in production gets the page, not
   JSON.** The read must never share a path with a dashboard page.
   - Task 2: guard test `test_no_transelec_api_path_is_also_a_dashboard_page_path`.
   - Task 6: adds the page path and re-runs it.
2. **Clicking or pressing Enter on «Abrir»/«Copiar N.º» inside an Estado
   table row acts on the link or button and does not open the drawer.**
   Today every row's `onKeyDown` calls `preventDefault()` on Enter, which
   would cancel the link.
   - Task 5: `EstadoTable.test.tsx` covers click and keydown.
   - Task 6: e2e copy test.
3. **Labels that differ only in case, accents or spacing classify like the
   canonical label.** For example «EN TRÁMITE» with «  En   Evaluación ».
   - Task 1: `test_case_accents_and_spaces_do_not_matter`.
4. **A blank `N Ingreso` with a filled `N Ingreso2` is not «sin ingreso».**
   - Task 1: `test_a_second_ingreso_alone_is_not_sin_ingreso`.
5. **An old bookmark `/transelec/pendientes?q=…` lands on Estado with the
   same filters, and Back does not bounce back to the retired address.**
   - Task 6: vitest `sends the old Pendientes address to Estado, keeping the
     filters`.
   - Task 6: e2e redirect test.

## File Structure

| Path | Responsibility |
|---|---|
| `products/transelect/src/transelec_ingestion/lifecycle_view.py` (create) | `lifecycle_pmf_v1`, pure |
| `products/transelect/tests/test_lifecycle_view.py` (create) | its unit tests |
| `apps/api/app/routers/transelec.py` (modify) | `GET /transelec/lifecycle`, `_closed_pmfs` |
| `apps/api/tests/test_transelec_lifecycle_routes.py` (create) | `_closed_pmfs` + path-collision guard (no DB) |
| `apps/api/integration_tests/test_transelec_reads_router.py` (modify) | lifecycle fixture + route tests |
| `apps/api/app/main.py` (modify) | `"transelec/estado"` page path |
| `products/transelect/dashboard/src/api.ts` (modify) | lifecycle types, `getLifecycle` |
| `.../src/lib/lifecycle.ts` (create) + `lifecycle.test.ts` | Spanish labels, bar segments, `needsReview` |
| `.../src/lib/rules.ts` (modify) | «Cómo se calcula» for `lifecycle_pmf_v1` |
| `.../src/lib/estadoColumns.tsx` (create) | `EstadoColumn`, `ESTADO_COLUMNS`, the extension point |
| `.../src/components/OficinaVirtualLink.tsx` (create) | link + copy |
| `.../src/components/EstadoTable.tsx` (create) + test | the table; takes `extraColumns` |
| `.../src/components/LegacyPendingSection.tsx` (create) | old pending zone, moved unchanged, closed |
| `.../src/components/LifecycleQualityPanel.tsx` (create) + test | Calidad block |
| `.../src/components/RowDetailDrawer.tsx` (modify) + test | «Proceso CONAF», Oficina Virtual |
| `.../src/pages/EstadoPage.tsx` (create) + test | the section |
| `.../src/pages/PendientesPage.tsx` (delete) | replaced |
| `.../src/router.tsx`, `src/components/AppHeader.tsx`, `src/App.tsx` (modify) | route, nav, redirect |
| `.../src/pages/ResumenPage.tsx`, `src/components/QualityPanel.tsx`, `src/pages/CalidadPage.tsx` (modify) | links, Calidad block |
| `.../src/test/factories.ts` (modify) | `makeLifecycleRow`, `makeLifecycle` |
| `.../src/styles/components.css` (modify) | `.oficina-virtual` |
| `.../tests/e2e/stubs.ts`, `dashboard.spec.ts`, `navigation.spec.ts`, `print-responsive.spec.ts` (modify) | e2e |
| `products/transelect/dashboard/README.md`, `products/transelect/docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md` (modify) | docs |

`...` = `products/transelect/dashboard`.

**Cross-plan interface: the names the 90-días plan will use.** That plan
branches from `feat/transelec-estado`.
- **Python, `transelec_ingestion.lifecycle_view`:**
  - constants `LIFECYCLE_BASIS = "lifecycle_pmf_v1"`, `GROUP_ORDER`,
    `STEP_ORDER`, and `CLOSED_GROUPS: frozenset[str]`;
  - types `LifecycleGroup`, `LifecycleStep`, `LifecycleReason` and
    `LifecycleFlag` (`Literal`s);
  - frozen dataclasses `LifecycleInputRow(source_row_number, pmf, estado,
    estado_resumido, numero_ingreso, numero_ingreso_2)`,
    `PmfLifecycle(pmf, source_row_number, group, step, reason, flags)` and
    `LifecycleSummary(basis, total_pmf_count, groups, steps, pmfs)`;
  - functions `classify_first_row(row) -> tuple[LifecycleGroup,
    LifecycleStep | None, LifecycleReason | None]` and
    `build_lifecycle(rows: Iterable[LifecycleInputRow]) -> LifecycleSummary`.
- **Router, `apps/api/app/routers/transelec.py`:**
  `_to_lifecycle_input_row(row) -> LifecycleInputRow`,
  `_lifecycle_of(rows: Sequence[Row[Any]]) -> LifecycleSummary`,
  `_closed_pmfs(rows: Sequence[Row[Any]]) -> frozenset[str]`, and the route
  `GET /transelec/lifecycle` → `TranselecLifecycleResponse`.
- **Dashboard:**
  - `ROUTES.estado`, `pages/EstadoPage.tsx`;
  - `getLifecycle(filters): Promise<ApiResult<TranselecLifecycle>>`;
  - types `TranselecLifecycle`, `LifecycleRow` (`ResumenRow` plus
    `lifecycle_group`, `lifecycle_step`, `lifecycle_reason`,
    `lifecycle_flags`), `LifecycleGroup` and `LifecycleStep`;
  - `components/EstadoTable.tsx` with props `{ rows, selectedRow, onOpen,
    extraColumns? }`, and `EstadoColumn = { key, header, render(row) }`
    from `lib/estadoColumns.tsx`.

  **To add «Plazo CONAF»,** EstadoPage passes
  `extraColumns={[{ key: 'plazo', header: 'Plazo CONAF', render: (row) => … }]}`.
  The new column is appended after `ESTADO_COLUMNS`, and the plazo data is
  joined by `row.pmf`.

---

### Task 0: Worktree and baseline

**Files:** none.

- [ ] **Step 1: Create the worktree.** Run from `/home/rafael/dev/freelance/campo-digital`:

```bash
git -C campo-digital-platform fetch origin
git -C campo-digital-platform worktree add ../worktrees/campo-digital-transelec-estado -b feat/transelec-estado origin/main
cd worktrees/campo-digital-transelec-estado
```

Every later path is relative to this worktree.

- [ ] **Step 2: Install dependencies**

```bash
make setup
cd products/transelect/dashboard && npm ci && cd -
```

- [ ] **Step 3: Baseline (all must pass before touching anything)**

```bash
uv run pytest products/transelect/tests apps/api/tests -q
cd products/transelect/dashboard && npm test && npx tsc -b && npm run lint && cd -
```

Expected: all green. If not, stop and report; do not fix unrelated failures.

- [ ] **Step 4: Prepare the test database**

Run this in the shell you will use for the integration tests:

```bash
make db-test-up
export APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test \
  POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api
uv run alembic upgrade head
```

Expected: `alembic upgrade head` ends at revision `0011`.

If it fails with "Can't locate revision", another worktree migrated the
shared container past `0011` (the web-edits plan adds `0012`). Run
`make db-test-reset` and then `uv run alembic upgrade head`, but only after
confirming that no other worktree is running integration tests. Otherwise,
wait.

---

### Task 1: `lifecycle_pmf_v1` pure classifier

**Files:**
- Create: `products/transelect/src/transelec_ingestion/lifecycle_view.py`
- Test: `products/transelect/tests/test_lifecycle_view.py`

**Interfaces:**
- Consumes: `transelec_ingestion.status_rollups.normalized_label(value: str | None) -> str | None`; `first_row_wins` and `RolledRow`, in a test only.
- Produces: every name in the cross-plan interface's Python section.

- [ ] **Step 1: Write the failing tests**

Create `products/transelect/tests/test_lifecycle_view.py`:

```python
"""Unit tests for ``lifecycle_pmf_v1`` — the «Estado» section's basis.

Synthetic PMF codes only. The labels are the vocabulary the 2026-10-04 Estado
spec records for the 30-Sept-2026 planilla, also spelled with the case,
accent and whitespace variants a workbook really carries.
"""

from __future__ import annotations

import pytest

from transelec_ingestion.lifecycle_view import (
    CLOSED_GROUPS,
    GROUP_ORDER,
    LIFECYCLE_BASIS,
    STEP_ORDER,
    LifecycleInputRow,
    build_lifecycle,
    classify_first_row,
)
from transelec_ingestion.status_rollups import RolledRow, first_row_wins


def _row(
    *,
    source_row_number: int = 2,
    pmf: str = "MP001",
    estado: str | None = "En evaluacion",
    estado_resumido: str | None = "En tramite",
    numero_ingreso: str | None = "ING-1",
    numero_ingreso_2: str | None = None,
) -> LifecycleInputRow:
    return LifecycleInputRow(
        source_row_number=source_row_number,
        pmf=pmf,
        estado=estado,
        estado_resumido=estado_resumido,
        numero_ingreso=numero_ingreso,
        numero_ingreso_2=numero_ingreso_2,
    )


@pytest.mark.parametrize(
    ("resumido", "estado", "expected"),
    [
        ("Aprobado", "Aprobado", ("aprobado", None, None)),
        ("Aprobado", "Recurso reposicion aprobado", ("aprobado", None, None)),
        ("Aprobado", "Recurso jerarquico aprobado", ("aprobado", None, None)),
        ("Descartado", "Descartado", ("descartado", None, None)),
        ("Desistido", "Desistido", ("desistido", None, None)),
        ("En tramite", "En Evaluacion", ("en_tramite", "en_evaluacion", None)),
        ("En tramite", "Rechazado", ("en_tramite", "rechazado_esperando_recurso", None)),
        (
            "En tramite",
            "Recurso jerarquico rechazado",
            ("en_tramite", "rechazado_esperando_recurso", None),
        ),
        ("En tramite", "Recurso reposicion", ("en_tramite", "en_recurso_reposicion", None)),
        ("Rechazado", "Recurso jerarquico", ("en_tramite", "en_recurso_jerarquico", None)),
    ],
)
def test_each_known_label_lands_in_its_group_and_step(
    resumido: str, estado: str, expected: tuple[str, str | None, str | None]
) -> None:
    assert classify_first_row(_row(estado_resumido=resumido, estado=estado)) == expected


def test_a_rejection_is_never_terminal() -> None:
    group, step, reason = classify_first_row(_row(estado_resumido="Rechazado", estado="Rechazado"))

    assert (group, step, reason) == ("en_tramite", "rechazado_esperando_recurso", None)
    assert group not in CLOSED_GROUPS


def test_case_accents_and_spaces_do_not_matter() -> None:
    assert classify_first_row(_row(estado_resumido="EN TRÁMITE", estado="  En   Evaluación ")) == (
        "en_tramite",
        "en_evaluacion",
        None,
    )
    assert classify_first_row(_row(estado_resumido="en trámite", estado="Recurso Jerárquico")) == (
        "en_tramite",
        "en_recurso_jerarquico",
        None,
    )


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_no_ingreso_at_all_is_sin_ingreso_whatever_estado_says(blank: str | None) -> None:
    row = _row(estado="En evaluacion", numero_ingreso=blank, numero_ingreso_2=blank)

    assert classify_first_row(row) == ("en_tramite", "sin_ingreso", None)


def test_a_second_ingreso_alone_is_not_sin_ingreso() -> None:
    row = _row(estado="Recurso reposicion", numero_ingreso=None, numero_ingreso_2="ING-1-R")

    assert classify_first_row(row) == ("en_tramite", "en_recurso_reposicion", None)


@pytest.mark.parametrize("resumido", ["Tachado", "Pendiente", None, ""])
def test_an_unknown_resumido_is_unclassified_not_guessed(resumido: str | None) -> None:
    assert classify_first_row(_row(estado_resumido=resumido)) == (
        "sin_clasificar",
        None,
        "resumido_desconocido",
    )


@pytest.mark.parametrize("estado", ["Rechazado por CONAF", "En preparacion", None])
def test_an_unknown_estado_inside_en_tramite_is_unclassified(estado: str | None) -> None:
    assert classify_first_row(_row(estado_resumido="En tramite", estado=estado)) == (
        "sin_clasificar",
        None,
        "estado_desconocido",
    )


@pytest.mark.parametrize(
    ("resumido", "estado"),
    [
        ("Aprobado", "Recurso reposicion"),  # approved summary, open recurso
        ("Aprobado", None),
        ("Aprobado", "Desaprobado"),  # «aprobado» is matched as a word only
        ("En tramite", "Recurso reposicion aprobado"),
        ("Rechazado", "Aprobado"),
        ("Descartado", "Rechazado"),
        ("Desistido", "Descartado"),  # never merged with each other
    ],
)
def test_a_contradiction_between_estado_and_resumido_is_unclassified(
    resumido: str, estado: str | None
) -> None:
    assert classify_first_row(_row(estado_resumido=resumido, estado=estado)) == (
        "sin_clasificar",
        None,
        "estado_y_resumido_no_coinciden",
    )


def test_the_representative_row_is_the_one_first_row_wins_picks() -> None:
    rows = [
        _row(source_row_number=9, estado="Aprobado", estado_resumido="Aprobado"),
        _row(source_row_number=4, estado="Rechazado", estado_resumido="En tramite"),
        _row(source_row_number=6, estado="En evaluacion", estado_resumido="En tramite"),
    ]
    rolled = [
        RolledRow(
            source_row_number=row.source_row_number,
            pmf=row.pmf,
            predio_group_key="key",
            estado=row.estado,
            estado_resumido=row.estado_resumido,
            numero_ingreso=row.numero_ingreso,
        )
        for row in rows
    ]

    (entry,) = build_lifecycle(rows).pmfs

    assert entry.source_row_number == first_row_wins(rolled, key="pmf")["MP001"].source_row_number
    assert entry.source_row_number == 4
    assert (entry.group, entry.step) == ("en_tramite", "rechazado_esperando_recurso")


def test_rows_that_disagree_keep_the_first_row_and_are_flagged() -> None:
    summary = build_lifecycle(
        [
            _row(source_row_number=2, estado="Aprobado", estado_resumido="Aprobado"),
            _row(
                source_row_number=3,
                estado="Recurso reposicion aprobado",
                estado_resumido="Aprobado",
            ),
            _row(source_row_number=5, pmf="MP002"),
        ]
    )

    by_pmf = {entry.pmf: entry for entry in summary.pmfs}
    assert by_pmf["MP001"].group == "aprobado"
    assert by_pmf["MP001"].flags == ("filas_no_coinciden",)
    assert by_pmf["MP002"].flags == ()


def test_rows_that_differ_only_in_spelling_are_not_flagged() -> None:
    summary = build_lifecycle(
        [
            _row(source_row_number=2, estado="En Evaluacion", estado_resumido="En tramite"),
            _row(source_row_number=3, estado="en evaluación", estado_resumido="EN TRÁMITE"),
        ]
    )

    assert summary.pmfs[0].flags == ()


def test_counts_cover_every_group_and_step_and_pmfs_follow_source_order() -> None:
    summary = build_lifecycle(
        [
            _row(
                source_row_number=7, pmf="MP003", estado="Descartado", estado_resumido="Descartado"
            ),
            _row(source_row_number=2, pmf="MP001", estado="Rechazado"),
            _row(source_row_number=4, pmf="MP002", estado="Aprobado", estado_resumido="Aprobado"),
        ]
    )

    assert summary.basis == LIFECYCLE_BASIS == "lifecycle_pmf_v1"
    assert summary.total_pmf_count == 3
    assert tuple(summary.groups) == GROUP_ORDER
    assert tuple(summary.steps) == STEP_ORDER
    assert summary.groups == {
        "aprobado": 1,
        "en_tramite": 1,
        "descartado": 1,
        "desistido": 0,
        "sin_clasificar": 0,
    }
    assert summary.steps["rechazado_esperando_recurso"] == 1
    assert sum(summary.steps.values()) == 1
    assert [entry.pmf for entry in summary.pmfs] == ["MP001", "MP002", "MP003"]


def test_no_rows_is_an_empty_summary_not_an_error() -> None:
    summary = build_lifecycle([])

    assert summary.total_pmf_count == 0
    assert summary.pmfs == ()
    assert set(summary.groups.values()) == {0}


def test_closed_groups_are_exactly_the_terminal_ones() -> None:
    assert frozenset({"aprobado", "descartado", "desistido"}) == CLOSED_GROUPS
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest products/transelect/tests/test_lifecycle_view.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'transelec_ingestion.lifecycle_view'`.

- [ ] **Step 3: Write the module**

Create `products/transelect/src/transelec_ingestion/lifecycle_view.py`:

```python
"""``lifecycle_pmf_v1`` — where each plan (PMF) stands in CONAF's process.

Design: docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md.

A rejection is a step, never an end (meeting of 2026-10-02): every rejection
ends approved or withdrawn. The group comes from the first row's
``Estado resumido``; inside «En trámite» the step comes from its ``Estado``.
Labels match exactly after ``normalized_label`` (case, accents and
whitespace folded). The only other test is the whole word «aprobado» in the
consistency check. Nothing is guessed: a label or a combination this basis
does not know lands in ``sin_clasificar`` with its reason, for a person to
read in the planilla.

A PMF's representative row is its first row — the same tie-break as
``status_rollups.first_row_wins`` (smallest ``source_row_number``). A PMF
whose rows disagree on ``Estado`` or ``Estado resumido`` keeps that result
and is flagged ``filas_no_coinciden``.

Pure and DB-agnostic, like ``pending_view``: the HTTP adapter projects rows
into ``LifecycleInputRow`` and hydrates each PMF's first row itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from transelec_ingestion.status_rollups import normalized_label

LIFECYCLE_BASIS = "lifecycle_pmf_v1"

LifecycleGroup = Literal["aprobado", "en_tramite", "descartado", "desistido", "sin_clasificar"]
LifecycleStep = Literal[
    "sin_ingreso",
    "en_evaluacion",
    "rechazado_esperando_recurso",
    "en_recurso_reposicion",
    "en_recurso_jerarquico",
]
LifecycleReason = Literal[
    "resumido_desconocido",
    "estado_desconocido",
    "estado_y_resumido_no_coinciden",
]
LifecycleFlag = Literal["filas_no_coinciden"]
Classification = tuple[LifecycleGroup, LifecycleStep | None, LifecycleReason | None]

GROUP_ORDER: tuple[LifecycleGroup, ...] = (
    "aprobado",
    "en_tramite",
    "descartado",
    "desistido",
    "sin_clasificar",
)
STEP_ORDER: tuple[LifecycleStep, ...] = (
    "sin_ingreso",
    "en_evaluacion",
    "rechazado_esperando_recurso",
    "en_recurso_reposicion",
    "en_recurso_jerarquico",
)

# The groups that end CONAF's process. The 90 días hábiles basis answers
# «no aplica» for them (through the router's ``_closed_pmfs``).
CLOSED_GROUPS: frozenset[str] = frozenset({"aprobado", "descartado", "desistido"})

_GROUP_BY_RESUMIDO: dict[str, LifecycleGroup] = {
    "aprobado": "aprobado",
    "en tramite": "en_tramite",
    # The source already summarizes a rejection as in progress; so does this.
    "rechazado": "en_tramite",
    "descartado": "descartado",
    "desistido": "desistido",
}

_APROBADO_WORD = re.compile(r"\baprobado\b")


@dataclass(frozen=True, slots=True)
class LifecycleInputRow:
    source_row_number: int
    pmf: str
    estado: str | None
    estado_resumido: str | None
    numero_ingreso: str | None
    numero_ingreso_2: str | None


@dataclass(frozen=True, slots=True)
class PmfLifecycle:
    pmf: str
    source_row_number: int
    group: LifecycleGroup
    step: LifecycleStep | None
    reason: LifecycleReason | None
    flags: tuple[LifecycleFlag, ...]


@dataclass(frozen=True, slots=True)
class LifecycleSummary:
    basis: str
    total_pmf_count: int
    groups: dict[LifecycleGroup, int]
    steps: dict[LifecycleStep, int]
    pmfs: tuple[PmfLifecycle, ...]


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _contradiction(group: LifecycleGroup, estado: str | None) -> bool:
    says_approved = estado is not None and _APROBADO_WORD.search(estado) is not None
    if group == "aprobado":
        return not says_approved
    if says_approved:
        return True
    if group in ("descartado", "desistido"):
        return estado != group
    return False


def _step(row: LifecycleInputRow, estado: str | None) -> LifecycleStep | None:
    if _blank(row.numero_ingreso) and _blank(row.numero_ingreso_2):
        return "sin_ingreso"
    if estado == "en evaluacion":
        return "en_evaluacion"
    if estado == "rechazado" or (
        estado is not None and estado.startswith("recurso") and estado.endswith("rechazado")
    ):
        return "rechazado_esperando_recurso"
    if estado == "recurso reposicion":
        return "en_recurso_reposicion"
    if estado == "recurso jerarquico":
        return "en_recurso_jerarquico"
    return None


def classify_first_row(row: LifecycleInputRow) -> Classification:
    """Group, step (only inside ``en_tramite``) and reason for one first row."""

    group = _GROUP_BY_RESUMIDO.get(normalized_label(row.estado_resumido) or "")
    if group is None:
        return "sin_clasificar", None, "resumido_desconocido"

    estado = normalized_label(row.estado)
    if _contradiction(group, estado):
        return "sin_clasificar", None, "estado_y_resumido_no_coinciden"
    if group != "en_tramite":
        return group, None, None

    step = _step(row, estado)
    if step is None:
        return "sin_clasificar", None, "estado_desconocido"
    return "en_tramite", step, None


def build_lifecycle(rows: Iterable[LifecycleInputRow]) -> LifecycleSummary:
    by_pmf: dict[str, list[LifecycleInputRow]] = {}
    for row in rows:
        by_pmf.setdefault(row.pmf, []).append(row)

    pmfs: list[PmfLifecycle] = []
    for pmf, pmf_rows in by_pmf.items():
        first = min(pmf_rows, key=lambda row: row.source_row_number)
        group, step, reason = classify_first_row(first)
        disagree = (
            len({normalized_label(row.estado) for row in pmf_rows}) > 1
            or len({normalized_label(row.estado_resumido) for row in pmf_rows}) > 1
        )
        flags: tuple[LifecycleFlag, ...] = ("filas_no_coinciden",) if disagree else ()
        pmfs.append(
            PmfLifecycle(
                pmf=pmf,
                source_row_number=first.source_row_number,
                group=group,
                step=step,
                reason=reason,
                flags=flags,
            )
        )

    pmfs.sort(key=lambda entry: entry.source_row_number)

    groups: dict[LifecycleGroup, int] = {group: 0 for group in GROUP_ORDER}
    steps: dict[LifecycleStep, int] = {step: 0 for step in STEP_ORDER}
    for entry in pmfs:
        groups[entry.group] += 1
        if entry.step is not None:
            steps[entry.step] += 1

    return LifecycleSummary(
        basis=LIFECYCLE_BASIS,
        total_pmf_count=len(pmfs),
        groups=groups,
        steps=steps,
        pmfs=tuple(pmfs),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest products/transelect/tests/test_lifecycle_view.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, format, type-check**

Run: `uv run ruff format products/transelect/src/transelec_ingestion/lifecycle_view.py products/transelect/tests/test_lifecycle_view.py && uv run ruff check products/transelect && uv run mypy products/transelect/src/transelec_ingestion/lifecycle_view.py && uv run pytest products/transelect/tests/test_lifecycle_view.py -q`
Expected: no findings, tests still PASS. Formatting runs first, so long
parametrize lines are wrapped before `E501` is checked.

- [ ] **Step 6: Commit**

```bash
git add products/transelect/src/transelec_ingestion/lifecycle_view.py products/transelect/tests/test_lifecycle_view.py
git commit -m "feat(transelec): lifecycle_pmf_v1, where each PMF stands in CONAF's process" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `GET /transelec/lifecycle` and `_closed_pmfs`

**Files:**
- Modify: `apps/api/app/routers/transelec.py`. Imports at lines 63-79; new section inserted just above the `# GET /owner-status — TR-FUNC-013` banner (around line 1501).
- Create: `apps/api/tests/test_transelec_lifecycle_routes.py`
- Modify: `apps/api/integration_tests/test_transelec_reads_router.py`. `READ_ROUTES` at 387-397; 404 list at 458-466; new fixture and tests after `test_pending_section_matches_the_hand_computed_fixture` (ends around line 654).

**Interfaces:**
- Consumes: from Task 1, `CLOSED_GROUPS`, `LifecycleFlag`, `LifecycleGroup`, `LifecycleInputRow`, `LifecycleReason`, `LifecycleStep`, `LifecycleSummary` and `build_lifecycle`. From the router: `_fetch_filtered_rows`, `_require_active_import_id`, `_resumen_row_view`, `ResumenRowView`, `TranselecFilters`, `_transelec_filters` and `require_transelec_grant`.
- Produces: `_to_lifecycle_input_row`, `_lifecycle_of`, `_closed_pmfs(rows: Sequence[Row[Any]]) -> frozenset[str]`, `TranselecLifecycleResponse` and `LifecyclePmfRowView`. JSON shape:

```json
{
  "basis": "lifecycle_pmf_v1",
  "total_pmf_count": 0,
  "groups": {"aprobado": 0, "en_tramite": 0, "descartado": 0, "desistido": 0, "sin_clasificar": 0},
  "steps": {"sin_ingreso": 0, "en_evaluacion": 0, "rechazado_esperando_recurso": 0,
            "en_recurso_reposicion": 0, "en_recurso_jerarquico": 0},
  "rows": [{"...every ResumenRowView field...": "...",
            "lifecycle_group": "en_tramite", "lifecycle_step": "en_evaluacion",
            "lifecycle_reason": null, "lifecycle_flags": []}]
}
```

- [ ] **Step 1: Write the failing unit tests (no database)**

Create `apps/api/tests/test_transelec_lifecycle_routes.py`:

```python
"""The «Estado» read without a database.

``_closed_pmfs`` is what the 90 días hábiles route reuses to answer «no
aplica». The path guard keeps API paths and dashboard page paths apart:
``app.main`` mounts the Transelec router at ``/transelec`` as well as
``/api/transelec``, so a dashboard page sharing an API path would answer a
reload with JSON. That is why the page is ``/transelec/estado`` and the read
is ``/transelec/lifecycle`` (as the AEF page is ``seguimiento-aef``).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.routers.transelec import _closed_pmfs
from fastapi.routing import APIRoute


def _row(source_row_number: int, pmf: str, estado_resumido: str, estado: str) -> Any:
    return SimpleNamespace(
        source_row_number=source_row_number,
        pmf=pmf,
        estado=estado,
        estado_resumido=estado_resumido,
        numero_ingreso="ING-1",
        numero_ingreso_2=None,
    )


def test_closed_pmfs_are_the_approved_descartado_and_desistido_ones() -> None:
    rows: list[Any] = [
        _row(1, "MP001", "Aprobado", "Aprobado"),
        _row(2, "MP002", "En tramite", "Rechazado"),
        _row(3, "MP003", "Descartado", "Descartado"),
        _row(4, "MP004", "Desistido", "Desistido"),
        _row(5, "MP005", "Tachado", "Tachado"),
        _row(6, "MP006", "Aprobado", "Recurso reposicion"),
    ]

    assert _closed_pmfs(rows) == frozenset({"MP001", "MP003", "MP004"})


def test_no_transelec_api_path_is_also_a_dashboard_page_path() -> None:
    from app.main import TRANSELEC_SPA_PAGE_PATHS, app

    api_paths = {route.path.lstrip("/") for route in app.routes if isinstance(route, APIRoute)}

    assert api_paths & TRANSELEC_SPA_PAGE_PATHS == set()
```

- [ ] **Step 2: Run them to verify the first fails**

Run: `uv run pytest apps/api/tests/test_transelec_lifecycle_routes.py -v`
Expected: collection error `ImportError: cannot import name '_closed_pmfs'`.
(The path guard passes once the import resolves. It is a guard that stops a
later `/estado` API route.)

- [ ] **Step 3: Add the imports to the router**

In `apps/api/app/routers/transelec.py`, insert after the
`from transelec_ingestion.import_projection import (...)` block and before
`from transelec_ingestion.owner_status_view import ...`:

```python
from transelec_ingestion.lifecycle_view import (
    CLOSED_GROUPS,
    LifecycleFlag,
    LifecycleGroup,
    LifecycleInputRow,
    LifecycleReason,
    LifecycleStep,
    LifecycleSummary,
    build_lifecycle,
)
```

- [ ] **Step 4: Add the route section**

Insert immediately above the banner block that reads
`# GET /owner-status — TR-FUNC-013` (keep the banner's own dashed lines
below the new code):

```python
# ---------------------------------------------------------------------------
# GET /lifecycle — lifecycle_pmf_v1, the «Estado» section
#
# Deliberately not "/estado": this router is also mounted without the /api
# prefix (app.main), and "transelec/estado" is a dashboard page path
# (TRANSELEC_SPA_PAGE_PATHS). A shared path would answer a page reload with
# JSON — the reason the AEF page is "seguimiento-aef", not "aef".
# ---------------------------------------------------------------------------


class LifecycleGroupCountsView(BaseModel):
    aprobado: int
    en_tramite: int
    descartado: int
    desistido: int
    sin_clasificar: int


class LifecycleStepCountsView(BaseModel):
    sin_ingreso: int
    en_evaluacion: int
    rechazado_esperando_recurso: int
    en_recurso_reposicion: int
    en_recurso_jerarquico: int


class LifecyclePmfRowView(ResumenRowView):
    """A PMF's first row — every contract field, for the table and the
    drawer — plus where the PMF stands under ``lifecycle_pmf_v1``."""

    lifecycle_group: LifecycleGroup
    lifecycle_step: LifecycleStep | None
    lifecycle_reason: LifecycleReason | None
    lifecycle_flags: list[LifecycleFlag]


class TranselecLifecycleResponse(BaseModel):
    basis: Literal["lifecycle_pmf_v1"]
    total_pmf_count: int
    groups: LifecycleGroupCountsView
    steps: LifecycleStepCountsView
    rows: list[LifecyclePmfRowView]


def _to_lifecycle_input_row(row: Row[Any]) -> LifecycleInputRow:
    return LifecycleInputRow(
        source_row_number=row.source_row_number,
        pmf=row.pmf,
        estado=row.estado,
        estado_resumido=row.estado_resumido,
        numero_ingreso=row.numero_ingreso,
        numero_ingreso_2=row.numero_ingreso_2,
    )


def _lifecycle_of(rows: Sequence[Row[Any]]) -> LifecycleSummary:
    return build_lifecycle(_to_lifecycle_input_row(row) for row in rows)


def _closed_pmfs(rows: Sequence[Row[Any]]) -> frozenset[str]:
    """PMFs whose ``lifecycle_pmf_v1`` group ends CONAF's process
    (``CLOSED_GROUPS``). ``GET /plazos`` answers «no aplica» for these; pass
    it the same rows ``_fetch_filtered_rows`` returned for the request."""

    return frozenset(
        entry.pmf for entry in _lifecycle_of(rows).pmfs if entry.group in CLOSED_GROUPS
    )


@router.get(
    "/lifecycle",
    response_model=TranselecLifecycleResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def get_lifecycle(
    connection: Annotated[Connection, Depends(get_db_connection)],
    filters: Annotated[TranselecFilters, Depends(_transelec_filters)],
) -> TranselecLifecycleResponse:
    """Each PMF of the filtered scope, once, with its lifecycle group and step.

    Rows come only from ``_fetch_filtered_rows`` so the shared filter
    contract — and whatever relation that function reads — applies here as
    it does to every other read.
    """

    import_id = _require_active_import_id(connection)
    rows = _fetch_filtered_rows(connection, import_id=import_id, filters=filters)
    rows_by_number = {row.source_row_number: row for row in rows}
    summary = _lifecycle_of(rows)

    return TranselecLifecycleResponse(
        basis=summary.basis,  # type: ignore[arg-type]
        total_pmf_count=summary.total_pmf_count,
        groups=LifecycleGroupCountsView(**summary.groups),
        steps=LifecycleStepCountsView(**summary.steps),
        rows=[
            LifecyclePmfRowView(
                **_resumen_row_view(rows_by_number[entry.source_row_number]).model_dump(),
                lifecycle_group=entry.group,
                lifecycle_step=entry.step,
                lifecycle_reason=entry.reason,
                lifecycle_flags=list(entry.flags),
            )
            for entry in summary.pmfs
        ],
    )
```

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_transelec_lifecycle_routes.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Write the failing integration tests**

In `apps/api/integration_tests/test_transelec_reads_router.py`:

(a) In `READ_ROUTES`, add `"/transelec/lifecycle",` after `"/transelec/pending",`.

(b) In `test_data_dependent_routes_404_with_a_clear_message_when_nothing_is_published`,
add `"/transelec/lifecycle",` after `"/transelec/pending",`.

(c) Insert after `test_pending_section_matches_the_hand_computed_fixture`:

```python
# ---------------------------------------------------------------------------
# GET /lifecycle — lifecycle_pmf_v1 («Estado»)
# ---------------------------------------------------------------------------

# 9 rows / 8 PMFs, one per lifecycle_pmf_v1 case. The status labels are the
# vocabulary recorded in the 2026-10-04 Estado spec; PMF codes, roles and
# numbers are synthetic.
#
#  LC001 Aprobado / Aprobado (first row) + Recurso reposicion aprobado
#        → aprobado, flagged filas_no_coinciden
#  LC002 En tramite / En Evaluacion           → en_tramite · en_evaluacion
#  LC003 En tramite / Rechazado, «Legal»      → en_tramite · rechazado_esperando_recurso
#  LC004 Rechazado / Recurso jerarquico       → en_tramite · en_recurso_jerarquico
#  LC005 Descartado / Descartado              → descartado
#  LC006 Aprobado / Recurso reposicion        → sin_clasificar · estado_y_resumido_no_coinciden
#  LC007 En tramite / Recurso reposicion, no N Ingreso → en_tramite · sin_ingreso
#  LC008 Tachado / Tachado                    → sin_clasificar · resumido_desconocido
def _lifecycle_fixture_workbook(tmp_path: Path) -> bytes:
    def row(index: int, pmf: str, estado_resumido: str, estado: str, **extra: Any) -> list[Any]:
        values: dict[str, Any] = {
            "pmf": pmf,
            "rol": f"9{index}",
            "numero_predio": str(index),
            "estado": estado,
            "estado_resumido": estado_resumido,
            "numero_ingreso": f"ING-L{index}",
            "tipo_propietario": "Empresa Forestal",
            "sector": "Sector Norte",
            "pas": "PAS-A",
            "empresa": "Forestal Sur",
            "superficie_corta": 1.0,
        }
        values.update(extra)
        return _source_row(**values)

    rows = [
        row(1, "LC001", "Aprobado", "Aprobado"),
        row(2, "LC001", "Aprobado", "Recurso reposicion aprobado"),
        row(3, "LC002", "En tramite", "En Evaluacion"),
        row(4, "LC003", "En tramite", "Rechazado", tipo_rechazo="Legal", reingreso_legal="1"),
        row(5, "LC004", "Rechazado", "Recurso jerarquico"),
        row(6, "LC005", "Descartado", "Descartado"),
        row(7, "LC006", "Aprobado", "Recurso reposicion"),
        row(8, "LC007", "En tramite", "Recurso reposicion", numero_ingreso=None),
        row(9, "LC008", "Tachado", "Tachado"),
    ]
    return _workbook_bytes(tmp_path, "lifecycle.xlsx", rows)


def test_lifecycle_places_each_pmf_by_its_first_row(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _lifecycle_fixture_workbook(tmp_path))

    body = client.get("/transelec/lifecycle").json()

    assert body["basis"] == "lifecycle_pmf_v1"
    assert body["total_pmf_count"] == 8
    assert body["groups"] == {
        "aprobado": 1,
        "en_tramite": 4,
        "descartado": 1,
        "desistido": 0,
        "sin_clasificar": 2,
    }
    assert body["steps"] == {
        "sin_ingreso": 1,
        "en_evaluacion": 1,
        "rechazado_esperando_recurso": 1,
        "en_recurso_reposicion": 0,
        "en_recurso_jerarquico": 1,
    }
    assert [row["pmf"] for row in body["rows"]] == [f"LC00{n}" for n in range(1, 9)]

    by_pmf = {row["pmf"]: row for row in body["rows"]}
    # The first row is the one hydrated, and the disagreeing second row flags it.
    assert by_pmf["LC001"]["estado"] == "Aprobado"
    assert by_pmf["LC001"]["lifecycle_group"] == "aprobado"
    assert by_pmf["LC001"]["lifecycle_flags"] == ["filas_no_coinciden"]
    # Rejection is a step, with its type and the raw reingreso flag.
    assert by_pmf["LC003"]["lifecycle_group"] == "en_tramite"
    assert by_pmf["LC003"]["lifecycle_step"] == "rechazado_esperando_recurso"
    assert by_pmf["LC003"]["tipo_rechazo"] == "Legal"
    assert by_pmf["LC003"]["reingreso_legal"] == "1"
    assert by_pmf["LC004"]["lifecycle_step"] == "en_recurso_jerarquico"
    assert by_pmf["LC005"]["lifecycle_group"] == "descartado"
    assert by_pmf["LC006"]["lifecycle_reason"] == "estado_y_resumido_no_coinciden"
    assert by_pmf["LC007"]["lifecycle_step"] == "sin_ingreso"
    assert by_pmf["LC008"]["lifecycle_reason"] == "resumido_desconocido"


def test_lifecycle_follows_the_shared_filter_contract(
    client: TestClient, integration_engine: Engine, tmp_path: Path
) -> None:
    _login(client, "dev-admin")
    _publish_fixture(client, integration_engine, _lifecycle_fixture_workbook(tmp_path))

    narrowed = client.get("/transelec/lifecycle", params={"estado_resumido": "En tramite"}).json()
    assert narrowed["total_pmf_count"] == 3
    assert {row["pmf"] for row in narrowed["rows"]} == {"LC002", "LC003", "LC007"}
    assert narrowed["groups"]["en_tramite"] == 3

    searched = client.get("/transelec/lifecycle", params={"q": "recurso jerarquico"}).json()
    assert [row["pmf"] for row in searched["rows"]] == ["LC004"]
```

- [ ] **Step 7: Run the integration tests**

In the shell where Task 0 Step 4 exported the test-DB variables:

Run: `uv run pytest -q apps/api/integration_tests/test_transelec_reads_router.py`
Expected: all PASS, including the parametrized RBAC, viewer and
no-CSRF cases for `/transelec/lifecycle`.

If the publish call in `_publish_fixture` fails with 409 (warnings not
acknowledged), print `validated.json()["report"]["issues"]` locally to see
which synthetic cell produced the warning. Fix the fixture value. Never
acknowledge warnings in the helper.

- [ ] **Step 8: Lint and type-check**

Run: `uv run ruff format apps/api/app/routers/transelec.py apps/api/tests/test_transelec_lifecycle_routes.py apps/api/integration_tests/test_transelec_reads_router.py && uv run ruff check apps/api && uv run mypy apps/api/app/routers/transelec.py apps/api/tests/test_transelec_lifecycle_routes.py`
Expected: no findings. `# type: ignore[arg-type]` on `basis=` mirrors
`get_pending`. If mypy reports it unused, remove it.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/routers/transelec.py apps/api/tests/test_transelec_lifecycle_routes.py apps/api/integration_tests/test_transelec_reads_router.py
git commit -m "feat(transelec): GET /transelec/lifecycle reads lifecycle_pmf_v1 through the shared filters" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Dashboard data layer (types, labels, rules, factories, e2e stub)

**Files:**
- Modify: `products/transelect/dashboard/src/api.ts`. Types go after `TranselecPending` (ends at line 255); the function goes after `getPending` (around line 873).
- Create: `products/transelect/dashboard/src/lib/lifecycle.ts`, `src/lib/lifecycle.test.ts`
- Modify: `products/transelect/dashboard/src/lib/rules.ts` (add a `RULES` entry)
- Modify: `products/transelect/dashboard/src/test/factories.ts`
- Modify: `products/transelect/dashboard/tests/e2e/stubs.ts`. `lifecycleBody` goes after `makeApiRow` (ends at line 200); the route goes after the `/pending*` route (around line 324).

**Interfaces:**
- Consumes: the JSON shape from Task 2.
- Produces: `LifecycleGroup`, `LifecycleStep`, `LifecycleReason`, `LifecycleFlag`, `LifecycleRow`, `TranselecLifecycle` and `getLifecycle` (api.ts). From `lib/lifecycle.ts`: `LIFECYCLE_GROUP_ORDER`, `LIFECYCLE_STEP_ORDER`, `LIFECYCLE_GROUP_LABELS`, `LIFECYCLE_STEP_LABELS`, `LIFECYCLE_REASON_LABELS`, `LIFECYCLE_FLAG_LABELS`, `LIFECYCLE_GROUP_PILL`, `lifecycleGroupSegments`, `lifecycleStepSegments`, `lifecycleStepText` and `needsReview`. Also `makeLifecycleRow`, `makeLifecycle` (factories) and `lifecycleBody` (stubs).

All commands in this task run from `products/transelect/dashboard`.

- [ ] **Step 1: Add the API types and read function**

In `src/api.ts`, after the `TranselecPending` interface, add:

```ts
/** `lifecycle_pmf_v1` — see transelec_ingestion/lifecycle_view.py. */
export type LifecycleGroup = 'aprobado' | 'en_tramite' | 'descartado' | 'desistido' | 'sin_clasificar'

export type LifecycleStep =
  | 'sin_ingreso'
  | 'en_evaluacion'
  | 'rechazado_esperando_recurso'
  | 'en_recurso_reposicion'
  | 'en_recurso_jerarquico'

export type LifecycleReason =
  | 'resumido_desconocido'
  | 'estado_desconocido'
  | 'estado_y_resumido_no_coinciden'

export type LifecycleFlag = 'filas_no_coinciden'

/** One PMF: its first row (every contract field), plus where it stands. */
export type LifecycleRow = ResumenRow & {
  lifecycle_group: LifecycleGroup
  lifecycle_step: LifecycleStep | null
  lifecycle_reason: LifecycleReason | null
  lifecycle_flags: LifecycleFlag[]
}

export interface TranselecLifecycle {
  basis: string
  total_pmf_count: number
  groups: Record<LifecycleGroup, number>
  steps: Record<LifecycleStep, number>
  rows: LifecycleRow[]
}
```

After `getPending`, add:

```ts
/**
 * `GET /transelec/lifecycle` — the «Estado» section's read. Not `/estado`:
 * that is the dashboard page's own address (see the router's comment).
 */
export function getLifecycle(filters: TranselecFilterState): Promise<ApiResult<TranselecLifecycle>> {
  return request<TranselecLifecycle>(withParams('/api/transelec/lifecycle', filterParams(filters)))
}
```

- [ ] **Step 2: Add the factories**

In `src/test/factories.ts`, extend the type import to include
`LifecycleRow` and `TranselecLifecycle`, then add after `makePending`:

```ts
export function makeLifecycleRow(overrides: Partial<LifecycleRow> = {}): LifecycleRow {
  return {
    ...makeRow(),
    lifecycle_group: 'en_tramite',
    lifecycle_step: 'en_evaluacion',
    lifecycle_reason: null,
    lifecycle_flags: [],
    ...overrides,
  }
}

export function makeLifecycle(overrides: Partial<TranselecLifecycle> = {}): TranselecLifecycle {
  return {
    basis: 'lifecycle_pmf_v1',
    total_pmf_count: 4,
    groups: { aprobado: 1, en_tramite: 2, descartado: 0, desistido: 0, sin_clasificar: 1 },
    steps: {
      sin_ingreso: 0,
      en_evaluacion: 1,
      rechazado_esperando_recurso: 1,
      en_recurso_reposicion: 0,
      en_recurso_jerarquico: 0,
    },
    rows: [
      makeLifecycleRow({
        source_row_number: 2,
        pmf: 'MP001',
        estado: 'Aprobado',
        estado_resumido: 'Aprobado',
        lifecycle_group: 'aprobado',
        lifecycle_step: null,
      }),
      makeLifecycleRow({
        source_row_number: 3,
        pmf: 'MP002',
        estado: 'Rechazado',
        tipo_rechazo: 'Legal',
        reingreso_legal: '1',
        lifecycle_step: 'rechazado_esperando_recurso',
      }),
      makeLifecycleRow({ source_row_number: 5, pmf: 'MP003' }),
      makeLifecycleRow({
        source_row_number: 7,
        pmf: 'MP004',
        estado: 'Recurso reposicion',
        estado_resumido: 'Aprobado',
        lifecycle_group: 'sin_clasificar',
        lifecycle_step: null,
        lifecycle_reason: 'estado_y_resumido_no_coinciden',
        lifecycle_flags: ['filas_no_coinciden'],
      }),
    ],
    ...overrides,
  }
}
```

- [ ] **Step 3: Write the failing label tests**

Create `src/lib/lifecycle.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import {
  LIFECYCLE_GROUP_LABELS,
  lifecycleGroupSegments,
  lifecycleStepSegments,
  lifecycleStepText,
  needsReview,
} from './lifecycle'
import { ruleFor } from './rules'
import { makeLifecycle, makeLifecycleRow } from '../test/factories'

describe('lifecycle_pmf_v1 labels and bars', () => {
  it('orders the groups approved first, each with its own tone', () => {
    const segments = lifecycleGroupSegments(makeLifecycle())
    expect(segments.map((segment) => segment.key)).toEqual([
      'aprobado',
      'en_tramite',
      'descartado',
      'desistido',
      'sin_clasificar',
    ])
    expect(segments.map((segment) => segment.tone)).toEqual([
      'approved',
      'progress',
      'struck',
      'struck',
      'none',
    ])
    expect(segments.map((segment) => segment.value)).toEqual([1, 2, 0, 0, 1])
  })

  it('reserves the attention tone for a rejection waiting for its recurso', () => {
    const late = lifecycleStepSegments(makeLifecycle()).filter((segment) => segment.tone === 'late')
    expect(late.map((segment) => segment.key)).toEqual(['rechazado_esperando_recurso'])
  })

  it('shows Descartado and Desistido with their own words, never merged', () => {
    expect(LIFECYCLE_GROUP_LABELS.descartado).toBe('Descartado')
    expect(LIFECYCLE_GROUP_LABELS.desistido).toBe('Desistido')
  })

  it('describes a PMF by its step, or by why it could not be placed', () => {
    expect(
      lifecycleStepText(makeLifecycleRow({ lifecycle_step: 'rechazado_esperando_recurso' })),
    ).toBe('Rechazado, esperando recurso')
    expect(
      lifecycleStepText(makeLifecycleRow({ lifecycle_group: 'aprobado', lifecycle_step: null })),
    ).toBe('—')
    expect(
      lifecycleStepText(
        makeLifecycleRow({
          lifecycle_group: 'sin_clasificar',
          lifecycle_step: null,
          lifecycle_reason: 'estado_desconocido',
        }),
      ),
    ).toBe('«Estado» con un valor que esta regla no reconoce')
  })

  it('marks for review an unclassified PMF and one whose rows disagree', () => {
    expect(needsReview(makeLifecycleRow())).toBe(false)
    expect(needsReview(makeLifecycleRow({ lifecycle_flags: ['filas_no_coinciden'] }))).toBe(true)
    expect(
      needsReview(
        makeLifecycleRow({
          lifecycle_group: 'sin_clasificar',
          lifecycle_step: null,
          lifecycle_reason: 'resumido_desconocido',
        }),
      ),
    ).toBe(true)
  })

  it('explains the rule in «Cómo se calcula», provisional', () => {
    const rule = ruleFor('lifecycle_pmf_v1')
    expect(rule?.sourceColumns).toEqual([
      'PMF',
      'Estado resumido',
      'Estado',
      'N Ingreso',
      'N Ingreso2',
      'Tipo de rechazo',
    ])
    expect(rule?.steps.join(' ')).toContain('provisional')
  })
})
```

- [ ] **Step 4: Run it to verify it fails**

Run: `npm test -- src/lib/lifecycle.test.ts`
Expected: FAIL. `Failed to resolve import "./lifecycle"`.

- [ ] **Step 5: Write `src/lib/lifecycle.ts`**

```ts
/**
 * `lifecycle_pmf_v1` in Spanish, for the «Estado» section.
 *
 * The classification is the server's (`transelec_ingestion/lifecycle_view.py`);
 * this module only names its keys and orders them. All of this wording is
 * provisional until Campo Digital confirms the vocabulary (spec 2026-10-04,
 * open questions). «Descartado» and «Desistido» keep the source's own words
 * and are never merged.
 */
import type {
  LifecycleFlag,
  LifecycleGroup,
  LifecycleReason,
  LifecycleRow,
  LifecycleStep,
  TranselecLifecycle,
} from '../api'
import type { CompositionSegment, SegmentTone } from '../ui/CompositionBar'

export const LIFECYCLE_GROUP_ORDER: LifecycleGroup[] = [
  'aprobado',
  'en_tramite',
  'descartado',
  'desistido',
  'sin_clasificar',
]

/** Attention first: a rejection waiting for its recurso is the work to do. */
export const LIFECYCLE_STEP_ORDER: LifecycleStep[] = [
  'rechazado_esperando_recurso',
  'en_recurso_reposicion',
  'en_recurso_jerarquico',
  'en_evaluacion',
  'sin_ingreso',
]

export const LIFECYCLE_GROUP_LABELS: Record<LifecycleGroup, string> = {
  aprobado: 'Aprobado',
  en_tramite: 'En trámite',
  descartado: 'Descartado',
  desistido: 'Desistido',
  sin_clasificar: 'Sin clasificar',
}

export const LIFECYCLE_STEP_LABELS: Record<LifecycleStep, string> = {
  sin_ingreso: 'Sin ingreso a CONAF',
  en_evaluacion: 'En evaluación',
  rechazado_esperando_recurso: 'Rechazado, esperando recurso',
  en_recurso_reposicion: 'En recurso de reposición',
  en_recurso_jerarquico: 'En recurso jerárquico',
}

export const LIFECYCLE_REASON_LABELS: Record<LifecycleReason, string> = {
  resumido_desconocido: '«Estado resumido» con un valor que esta regla no reconoce',
  estado_desconocido: '«Estado» con un valor que esta regla no reconoce',
  estado_y_resumido_no_coinciden: '«Estado» y «Estado resumido» no coinciden',
}

export const LIFECYCLE_FLAG_LABELS: Record<LifecycleFlag, string> = {
  filas_no_coinciden:
    'Sus filas no tienen el mismo «Estado» o «Estado resumido»; se usa la primera',
}

/** The existing `.pill-*` tones; closed-without-approval reads as struck. */
export const LIFECYCLE_GROUP_PILL: Record<LifecycleGroup, string> = {
  aprobado: 'pill-aprobado',
  en_tramite: 'pill-en-tramite',
  descartado: 'pill-tachado',
  desistido: 'pill-tachado',
  sin_clasificar: 'pill-otro',
}

const GROUP_TONES: Record<LifecycleGroup, SegmentTone> = {
  aprobado: 'approved',
  en_tramite: 'progress',
  descartado: 'struck',
  desistido: 'struck',
  sin_clasificar: 'none',
}

// Attention red is reserved for one step (spec 2026-10-04).
const STEP_TONES: Record<LifecycleStep, SegmentTone> = {
  rechazado_esperando_recurso: 'late',
  en_recurso_reposicion: 'progress',
  en_recurso_jerarquico: 'progress',
  en_evaluacion: 'progress',
  sin_ingreso: 'none',
}

export function lifecycleGroupSegments(data: TranselecLifecycle): CompositionSegment[] {
  return LIFECYCLE_GROUP_ORDER.map((group) => ({
    key: group,
    label: LIFECYCLE_GROUP_LABELS[group],
    value: data.groups[group],
    tone: GROUP_TONES[group],
  }))
}

export function lifecycleStepSegments(data: TranselecLifecycle): CompositionSegment[] {
  return LIFECYCLE_STEP_ORDER.map((step) => ({
    key: step,
    label: LIFECYCLE_STEP_LABELS[step],
    value: data.steps[step],
    tone: STEP_TONES[step],
  }))
}

/** The step inside «En trámite», why a PMF is unclassified, or a dash. */
export function lifecycleStepText(row: LifecycleRow): string {
  if (row.lifecycle_step) return LIFECYCLE_STEP_LABELS[row.lifecycle_step]
  if (row.lifecycle_reason) return LIFECYCLE_REASON_LABELS[row.lifecycle_reason]
  return '—'
}

/** Listed in Calidad: a PMF the rule could not place, or whose rows disagree. */
export function needsReview(row: LifecycleRow): boolean {
  return row.lifecycle_group === 'sin_clasificar' || row.lifecycle_flags.length > 0
}
```

- [ ] **Step 6: Add the rule explanation**

In `src/lib/rules.ts`, add this entry to `RULES` after `pending_stage_legacy`:

```ts
  lifecycle_pmf_v1: {
    name: 'Dónde está cada PMF en la tramitación CONAF',
    steps: [
      'Cada PMF se evalúa una sola vez, con su primera fila (la de número de fila más bajo).',
      'El grupo sale de «Estado resumido»: «Aprobado» → Aprobado; «En trámite» o «Rechazado» → En trámite; «Descartado» → Descartado; «Desistido» → Desistido.',
      'Dentro de «En trámite», el paso sale de «Estado»: sin «N Ingreso» ni «N Ingreso2» → Sin ingreso a CONAF; «En evaluación» → En evaluación; «Rechazado» o un recurso rechazado → Rechazado, esperando recurso; «Recurso reposición» → En recurso de reposición; «Recurso jerárquico» → En recurso jerárquico.',
      'Un rechazo no es un final: todo rechazo termina en Aprobado, Descartado o Desistido.',
      'No cuentan mayúsculas, tildes ni espacios; ninguna otra variación se adivina. Un valor que la regla no conoce, o un «Estado» que contradice al «Estado resumido», deja el PMF «Sin clasificar» con el motivo, y se lista en Calidad.',
      'Si las filas del PMF no tienen el mismo estado, se usa la primera y el PMF se marca para revisar.',
      'Categorías provisionales hasta que Campo Digital confirme el vocabulario.',
    ],
    sourceColumns: ['PMF', 'Estado resumido', 'Estado', 'N Ingreso', 'N Ingreso2', 'Tipo de rechazo'],
  },
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `npm test -- src/lib/lifecycle.test.ts`
Expected: PASS.

- [ ] **Step 8: Add the e2e stub**

In `tests/e2e/stubs.ts`, add after `makeApiRow`:

```ts
/**
 * `GET /transelec/lifecycle`: six synthetic PMFs, one per case the Estado
 * section draws. Counts agree with the rows.
 */
export function lifecycleBody() {
  const row = (
    index: number,
    lifecycle: Record<string, unknown>,
    overrides: Record<string, unknown> = {},
  ) => ({
    ...makeApiRow(index, overrides),
    lifecycle_step: null,
    lifecycle_reason: null,
    lifecycle_flags: [],
    ...lifecycle,
  })
  return {
    basis: 'lifecycle_pmf_v1',
    total_pmf_count: 6,
    groups: { aprobado: 1, en_tramite: 4, descartado: 0, desistido: 0, sin_clasificar: 1 },
    steps: {
      sin_ingreso: 1,
      en_evaluacion: 1,
      rechazado_esperando_recurso: 1,
      en_recurso_reposicion: 1,
      en_recurso_jerarquico: 0,
    },
    rows: [
      row(
        1,
        { lifecycle_group: 'en_tramite', lifecycle_step: 'rechazado_esperando_recurso' },
        { estado: 'Rechazado', tipo_rechazo: 'Legal', reingreso_legal: '1' },
      ),
      row(2, { lifecycle_group: 'en_tramite', lifecycle_step: 'en_evaluacion' }),
      row(
        3,
        { lifecycle_group: 'en_tramite', lifecycle_step: 'en_recurso_reposicion' },
        { estado: 'Recurso reposicion', numero_ingreso_2: 'ING-3-R' },
      ),
      row(4, { lifecycle_group: 'en_tramite', lifecycle_step: 'sin_ingreso' }, { numero_ingreso: null }),
      row(5, { lifecycle_group: 'aprobado' }, { estado: 'Aprobado', estado_resumido: 'Aprobado' }),
      row(
        6,
        {
          lifecycle_group: 'sin_clasificar',
          lifecycle_reason: 'estado_y_resumido_no_coinciden',
          lifecycle_flags: ['filas_no_coinciden'],
        },
        { estado: 'Recurso reposicion', estado_resumido: 'Aprobado' },
      ),
    ],
  }
}
```

In `stubPlatform`, after the `**/api/transelec/pending*` route, add:

```ts
  await page.route('**/api/transelec/lifecycle*', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, lifecycleBody())
  })
```

- [ ] **Step 9: Type-check, lint and run the whole unit suite**

Run: `npx tsc -b && npm run lint && npm test`
Expected: no type errors, no new lint warnings, all tests PASS.

- [ ] **Step 10: Commit**

```bash
git add src/api.ts src/lib/lifecycle.ts src/lib/lifecycle.test.ts src/lib/rules.ts src/test/factories.ts tests/e2e/stubs.ts
git commit -m "feat(transelec-dashboard): lifecycle types, labels and read for the Estado section" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Oficina Virtual link and the drawer's «Proceso CONAF» block

**Files:**
- Create: `products/transelect/dashboard/src/components/OficinaVirtualLink.tsx`
- Modify: `products/transelect/dashboard/src/components/RowDetailDrawer.tsx`. The import block is at lines 26-50; the props are at 230-238; the Tramitación section is at 318-359.
- Modify: `products/transelect/dashboard/src/components/RowDetailDrawer.test.tsx` (double quotes and semicolons)
- Modify: `products/transelect/dashboard/src/styles/components.css` (append)

**Interfaces:**
- Consumes: `LifecycleRow` (Task 3); `LIFECYCLE_GROUP_LABELS`, `LIFECYCLE_REASON_LABELS`, `LIFECYCLE_FLAG_LABELS` and `lifecycleStepText` (Task 3).
- Produces: `OficinaVirtualLink({ numero, compact?, testId? })` and `OFICINA_VIRTUAL_CONAF_URL`. The link carries test id `${testId}-link`; the copy button carries `${testId}-copy`. `RowDetailDrawer` gains the optional prop `lifecycle?: LifecycleRow | null`.

Commands run from `products/transelect/dashboard`.

- [ ] **Step 1: Write the failing drawer tests**

In `src/components/RowDetailDrawer.test.tsx`, change the factories import to
`import { makeLifecycleRow, makeRow } from "../test/factories";`. Then append:

```tsx
describe("RowDetailDrawer — Proceso CONAF (lifecycle_pmf_v1)", () => {
  beforeEach(() => {
    vi.mocked(getPmfDetail).mockReset();
    vi.mocked(getAef).mockReset();
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: { pmfs: [] } as unknown as TranselecAef,
    });
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: "MP002",
        row_count: 1,
        basis_estado_resumido: "estado_resumido_first_row",
        estado_resumido: "En tramite",
        rows: [makeRow({ source_row_number: 3, pmf: "MP002" })],
      },
    });
  });

  it("shows where the PMF stands when the Estado section opens it", () => {
    const lifecycle = makeLifecycleRow({
      source_row_number: 3,
      pmf: "MP002",
      lifecycle_step: "rechazado_esperando_recurso",
    });
    render(<RowDetailDrawer row={lifecycle} lifecycle={lifecycle} onClose={() => {}} />);

    const block = screen.getByTestId("drawer-lifecycle");
    expect(block).toHaveTextContent("En trámite");
    expect(block).toHaveTextContent("Rechazado, esperando recurso");
    expect(block).toHaveTextContent("primera fila del PMF (fila 3)");
  });

  it("says why a PMF is unclassified and that its rows disagree", () => {
    const lifecycle = makeLifecycleRow({
      source_row_number: 3,
      pmf: "MP002",
      lifecycle_group: "sin_clasificar",
      lifecycle_step: null,
      lifecycle_reason: "estado_y_resumido_no_coinciden",
      lifecycle_flags: ["filas_no_coinciden"],
    });
    render(<RowDetailDrawer row={lifecycle} lifecycle={lifecycle} onClose={() => {}} />);

    const block = screen.getByTestId("drawer-lifecycle");
    expect(block).toHaveTextContent("Sin clasificar");
    expect(block).toHaveTextContent("«Estado» y «Estado resumido» no coinciden");
    expect(block).toHaveTextContent("Sus filas no tienen el mismo");
  });

  it("has no Proceso CONAF block from elsewhere, but always links the Oficina Virtual", () => {
    render(
      <RowDetailDrawer
        row={makeRow({ source_row_number: 3, pmf: "MP002", numero_ingreso: "ING-7" })}
        onClose={() => {}}
      />,
    );

    expect(screen.queryByTestId("drawer-lifecycle")).toBeNull();
    const link = screen.getByTestId("drawer-ov-1-link");
    expect(link).toHaveAttribute("href", "https://oficinavirtual.conaf.cl/consultas/index.php");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByTestId("drawer-ov-1-copy")).toHaveAccessibleName("Copiar el N.º ING-7");
  });

  it("copies the N.º and says so", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    try {
      render(
        <RowDetailDrawer
          row={makeRow({ source_row_number: 3, pmf: "MP002", numero_ingreso: "ING-7" })}
          onClose={() => {}}
        />,
      );
      screen.getByTestId("drawer-ov-1-copy").click();

      await waitFor(() => expect(screen.getByText("N.º copiado.")).toBeInTheDocument());
      expect(writeText).toHaveBeenCalledWith("ING-7");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm test -- src/components/RowDetailDrawer.test.tsx`
Expected: FAIL. Type error or "Unable to find an element by: [data-testid="drawer-lifecycle"]".

- [ ] **Step 3: Create `src/components/OficinaVirtualLink.tsx`**

```tsx
/**
 * «Abrir Oficina Virtual CONAF» and «Copiar N.º», beside an N.º de ingreso.
 *
 * CONAF's consulta page is a form that POSTs `nsolicitud` to `action.php`
 * (read 2026-10-04): no address opens one expediente, and the production CSP
 * (`form-action 'self'`) forbids posting a form to another site anyway. So
 * this opens the page in a new tab and copies the number for the reader to
 * paste. Whether CONAF's «N.º de solicitud» is the planilla's `N Ingreso` is
 * still an open question, so the copy says «N.º».
 *
 * Used inside clickable table rows: a click or a key press here belongs to
 * the link or the button, never to the row behind it.
 */
import { useEffect, useRef, useState } from 'react'

export const OFICINA_VIRTUAL_CONAF_URL = 'https://oficinavirtual.conaf.cl/consultas/index.php'

export function OficinaVirtualLink({
  numero,
  compact = false,
  testId = 'oficina-virtual',
}: {
  numero: string | null
  /** «Abrir» instead of the full label, for a table cell. */
  compact?: boolean
  testId?: string
}) {
  const [copied, setCopied] = useState<'ok' | 'err' | null>(null)
  const timeoutRef = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timeoutRef.current), [])

  const value = numero?.trim() ?? ''

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied('ok')
    } catch {
      setCopied('err')
    }
    window.clearTimeout(timeoutRef.current)
    timeoutRef.current = window.setTimeout(() => setCopied(null), 4000)
  }

  return (
    <span
      className="oficina-virtual no-print"
      data-testid={testId}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <a
        href={OFICINA_VIRTUAL_CONAF_URL}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={compact ? 'Abrir Oficina Virtual CONAF' : undefined}
        data-testid={`${testId}-link`}
      >
        {compact ? 'Abrir' : 'Abrir Oficina Virtual CONAF'}
      </a>
      {value !== '' && (
        <button
          type="button"
          className="btn-link"
          onClick={() => void copy()}
          aria-label={`Copiar el N.º ${value}`}
          data-testid={`${testId}-copy`}
        >
          Copiar N.º
        </button>
      )}
      <span role="status" aria-live="polite" className="hint">
        {copied === 'ok' ? 'N.º copiado.' : copied === 'err' ? 'El navegador no permitió copiar.' : ''}
      </span>
    </span>
  )
}
```

- [ ] **Step 4: Wire the drawer**

In `src/components/RowDetailDrawer.tsx`:

(a) Add `type LifecycleRow,` to the `from '../api'` import list. Add these imports:

```tsx
import {
  LIFECYCLE_FLAG_LABELS,
  LIFECYCLE_GROUP_LABELS,
  LIFECYCLE_REASON_LABELS,
  lifecycleStepText,
} from '../lib/lifecycle'
import { OficinaVirtualLink } from './OficinaVirtualLink'
```

(b) Change the component signature to:

```tsx
export function RowDetailDrawer({
  row,
  onClose,
  sourceFields,
  lifecycle = null,
}: {
  row: ResumenRow
  onClose: () => void
  /** The published version's source fields; null/undefined while unknown. */
  sourceFields?: readonly string[] | null
  /** Where the PMF stands (`lifecycle_pmf_v1`), when the Estado section opens it. */
  lifecycle?: LifecycleRow | null
}) {
```

(c) Directly above `<section className="drawer-section" aria-labelledby="drawer-tramitacion">`, insert:

```tsx
        {lifecycle && (
          <section
            className="drawer-section"
            aria-labelledby="drawer-proceso"
            data-testid="drawer-lifecycle"
          >
            <h3 id="drawer-proceso">Proceso CONAF</h3>
            <dl className="facts">
              <Fact label="Grupo">{LIFECYCLE_GROUP_LABELS[lifecycle.lifecycle_group]}</Fact>
              <Fact label="Paso">{lifecycleStepText(lifecycle)}</Fact>
            </dl>
            {lifecycle.lifecycle_flags.map((flag) => (
              <p className="hint" key={flag}>
                {LIFECYCLE_FLAG_LABELS[flag]}.
              </p>
            ))}
            {lifecycle.lifecycle_reason && lifecycle.lifecycle_step === null && (
              <p className="hint">
                Para revisar en la planilla: {LIFECYCLE_REASON_LABELS[lifecycle.lifecycle_reason]}.
              </p>
            )}
            <p className="hint">
              Según la primera fila del PMF (fila {formatInteger(lifecycle.source_row_number)}).
              Categorías provisionales hasta que Campo Digital las confirme.
            </p>
          </section>
        )}
```

(d) Replace the N.º ingreso fact:

```tsx
            <Fact label="N.º ingreso">{cell(current.numero_ingreso, 'Sin ingreso')}</Fact>
```

with:

```tsx
            <Fact label="N.º ingreso">
              {cell(current.numero_ingreso, 'Sin ingreso')}
              <OficinaVirtualLink numero={current.numero_ingreso} testId="drawer-ov-1" />
            </Fact>
```

(e) In the `N.º ingreso 2` fact, after the closing `</span>` of
`data-testid="drawer-numero-ingreso-2"` and still inside the `Fact`, add:

```tsx
                  {current.numero_ingreso_2 && (
                    <OficinaVirtualLink numero={current.numero_ingreso_2} testId="drawer-ov-2" />
                  )}
```

- [ ] **Step 5: Add the style**

Append to `src/styles/components.css`:

```css
/* «Abrir Oficina Virtual CONAF» + «Copiar N.º», beside an N.º de ingreso. */
.oficina-virtual {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-3);
  margin-left: var(--s-3);
  font-size: var(--t-micro);
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm test -- src/components/RowDetailDrawer.test.tsx`
Expected: PASS, including the three existing second-ingreso tests. They use
substring matches on their own test ids, which the link sits outside.

- [ ] **Step 7: Type-check and lint**

Run: `npx tsc -b && npm run lint`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/components/OficinaVirtualLink.tsx src/components/RowDetailDrawer.tsx src/components/RowDetailDrawer.test.tsx src/styles/components.css
git commit -m "feat(transelec-dashboard): Oficina Virtual link and «Proceso CONAF» in the PMF drawer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Estado table, legacy pending section and `EstadoPage`

**Files:**
- Create: `products/transelect/dashboard/src/lib/estadoColumns.tsx`
- Create: `products/transelect/dashboard/src/components/EstadoTable.tsx` + `EstadoTable.test.tsx`
- Create: `products/transelect/dashboard/src/components/LegacyPendingSection.tsx`
- Create: `products/transelect/dashboard/src/pages/EstadoPage.tsx` + `EstadoPage.test.tsx`

**Interfaces:**
- Consumes: from Task 3, `getLifecycle`, `LifecycleRow`, `TranselecLifecycle`, the label helpers and `makeLifecycle`. From Task 4, `OficinaVirtualLink` and `RowDetailDrawer`'s `lifecycle` prop. Existing: `getPending`, `observedServerNow`, `OverduePanel`, `collectAllRows`, `selectOverdueRows`, `CompositionBar`, `HowCalculated` and `useReads`.
- Produces: `EstadoColumn`, `ESTADO_COLUMNS`; `EstadoTable({ rows, selectedRow, onOpen, extraColumns? })`; `LegacyPendingSection({ filters, selectedRow, onOpenRow })`; and `EstadoPage({ filterController, sourceFields })`.
- Test ids: `estado-zone`, `estado-group-<group>`, `estado-step-<step>`, `estado-how`, `estado-table`, `estado-row-<source_row_number>`, `estado-ov-<source_row_number>-link|-copy`, `clear-estado-filters`, `legacy-pending`. These are kept from the old page: `pending-zone`, `pending-count`, `pending-stage-*`, `pending-row-*`, `overdue-*`.

`PendientesPage.tsx` is left in place until Task 6 rewires the router.

- [ ] **Step 1: Write the failing table tests**

Create `src/components/EstadoTable.test.tsx`:

```tsx
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EstadoTable } from './EstadoTable'
import type { EstadoColumn } from '../lib/estadoColumns'
import { makeLifecycle } from '../test/factories'

const rows = makeLifecycle().rows

describe('EstadoTable', () => {
  it('shows each PMF with its group, step, rejection type, ingresos and raw reingreso flags', () => {
    render(<EstadoTable rows={rows} selectedRow={null} onOpen={() => {}} />)
    const row = screen.getByTestId('estado-row-3')
    expect(row).toHaveTextContent('MP002')
    expect(row).toHaveTextContent('En trámite')
    expect(row).toHaveTextContent('Rechazado, esperando recurso')
    expect(row).toHaveTextContent('Legal')
    expect(row).toHaveTextContent('ING-900 / —')
    expect(row).toHaveTextContent('— / 1 / —')
  })

  it('appends extra columns after its own, so a later basis adds one column', () => {
    const plazo: EstadoColumn = {
      key: 'plazo',
      header: 'Plazo CONAF',
      render: (row) => `plazo de ${row.pmf}`,
    }
    render(<EstadoTable rows={rows} selectedRow={null} onOpen={() => {}} extraColumns={[plazo]} />)
    const headers = screen.getAllByRole('columnheader').map((header) => header.textContent)
    expect(headers[headers.length - 1]).toBe('Plazo CONAF')
    expect(screen.getByTestId('estado-row-2')).toHaveTextContent('plazo de MP001')
  })

  it('opens a PMF by click and by Enter', async () => {
    const onOpen = vi.fn()
    render(<EstadoTable rows={rows} selectedRow={null} onOpen={onOpen} />)
    await userEvent.click(screen.getByTestId('estado-row-2'))
    expect(onOpen).toHaveBeenLastCalledWith(rows[0])
    fireEvent.keyDown(screen.getByTestId('estado-row-5'), { key: 'Enter' })
    expect(onOpen).toHaveBeenLastCalledWith(rows[2])
  })

  it('leaves a click or Enter on the Oficina Virtual controls to them, not to the row', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    const onOpen = vi.fn()
    try {
      render(<EstadoTable rows={rows} selectedRow={null} onOpen={onOpen} />)
      const row = screen.getByTestId('estado-row-3')
      await userEvent.click(within(row).getByRole('button', { name: 'Copiar el N.º ING-900' }))
      fireEvent.keyDown(within(row).getByRole('link', { name: 'Abrir Oficina Virtual CONAF' }), {
        key: 'Enter',
      })
      expect(writeText).toHaveBeenCalledWith('ING-900')
      expect(onOpen).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('says so when the scope has no PMF', () => {
    render(<EstadoTable rows={[]} selectedRow={null} onOpen={() => {}} />)
    expect(screen.getByText('No hay PMF en el alcance seleccionado.')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm test -- src/components/EstadoTable.test.tsx`
Expected: FAIL. `Failed to resolve import "./EstadoTable"`.

- [ ] **Step 3: Create `src/lib/estadoColumns.tsx`**

```tsx
/**
 * The «Estado» table's columns, and the one extension point it has.
 *
 * Kept in `lib/` rather than beside the component so the component module
 * exports only components (oxlint `react/only-export-components`). A later
 * basis — the 90 días hábiles «Plazo CONAF» — adds a column by passing
 * `extraColumns` to `EstadoTable`; it never edits this list.
 */
import type { ReactNode } from 'react'
import type { LifecycleRow } from '../api'
import { OficinaVirtualLink } from '../components/OficinaVirtualLink'
import { cell } from '../format'
import { LIFECYCLE_GROUP_LABELS, LIFECYCLE_GROUP_PILL, lifecycleStepText } from './lifecycle'

export interface EstadoColumn {
  key: string
  header: string
  render: (row: LifecycleRow) => ReactNode
}

export const ESTADO_COLUMNS: readonly EstadoColumn[] = [
  { key: 'pmf', header: 'PMF', render: (row) => <b>{row.pmf}</b> },
  {
    key: 'grupo',
    header: 'Grupo',
    render: (row) => (
      <span className={`pill ${LIFECYCLE_GROUP_PILL[row.lifecycle_group]}`}>
        {LIFECYCLE_GROUP_LABELS[row.lifecycle_group]}
      </span>
    ),
  },
  { key: 'paso', header: 'Paso', render: (row) => lifecycleStepText(row) },
  { key: 'tipo_rechazo', header: 'Tipo de rechazo', render: (row) => cell(row.tipo_rechazo, '—') },
  {
    key: 'ingresos',
    header: 'N.º ingreso (1 / 2)',
    render: (row) => `${cell(row.numero_ingreso, 'Sin ingreso')} / ${cell(row.numero_ingreso_2, '—')}`,
  },
  {
    key: 'reingresos',
    header: 'Reingreso Tec / Legal / RecRep',
    // Raw, as the planilla has them: their meaning is an open question.
    render: (row) =>
      [row.reingreso_tec, row.reingreso_legal, row.reingreso_recrep]
        .map((value) => cell(value, '—'))
        .join(' / '),
  },
  {
    key: 'oficina',
    header: 'Oficina Virtual',
    // The most recent ingreso, as the 90-day clock counts from it.
    render: (row) => (
      <OficinaVirtualLink
        numero={row.numero_ingreso_2 ?? row.numero_ingreso}
        compact
        testId={`estado-ov-${row.source_row_number}`}
      />
    ),
  },
]
```

- [ ] **Step 4: Create `src/components/EstadoTable.tsx`**

```tsx
/**
 * One row per PMF, under `lifecycle_pmf_v1`. A row opens the PMF drawer by
 * click, Enter or Space, like every other queue in the dashboard.
 */
import type { LifecycleRow } from '../api'
import { ESTADO_COLUMNS, type EstadoColumn } from '../lib/estadoColumns'

export function EstadoTable({
  rows,
  selectedRow,
  onOpen,
  extraColumns = [],
}: {
  rows: readonly LifecycleRow[]
  /** `source_row_number` of the row whose drawer is open. */
  selectedRow: number | null
  onOpen: (row: LifecycleRow) => void
  /** Appended after the lifecycle columns (e.g. «Plazo CONAF»). */
  extraColumns?: readonly EstadoColumn[]
}) {
  const columns = [...ESTADO_COLUMNS, ...extraColumns]

  return (
    <div className="tablewrap" data-testid="estado-table">
      <table className="queue-table rows-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th scope="col" key={column.key}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.source_row_number}
              tabIndex={0}
              aria-selected={selectedRow === row.source_row_number}
              aria-haspopup="dialog"
              data-testid={`estado-row-${row.source_row_number}`}
              onClick={() => onOpen(row)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onOpen(row)
                }
              }}
            >
              {columns.map((column) => (
                <td key={column.key}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="empty">
                No hay PMF en el alcance seleccionado.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 5: Run the table tests to verify they pass**

Run: `npm test -- src/components/EstadoTable.test.tsx`
Expected: PASS.

- [ ] **Step 6: Create `src/components/LegacyPendingSection.tsx`**

The body is the former `PendientesPage` pending zone, moved without changing
any rule, count or test id. Only these are removed: the page header, the
filter chips, the clear button and the overdue toggle. Those now live on
`EstadoPage`.

```tsx
/**
 * The «Pendientes prioritarios» rule the «Estado» section replaced
 * (`pending_priority_legacy`, `pending_stage_legacy`).
 *
 * Kept reachable and closed by default: the functional parity matrix
 * (TR-FUNC-007/032/033) requires the source dashboards' own rules to stay
 * available beside a new basis, and the Resumen still counts with this one.
 * Moved here unchanged from the former `PendientesPage`; its stage bar keeps
 * its old tones inside this closed disclosure.
 */
import { useCallback } from 'react'
import { type ResumenRow, type TranselecFilterState, type TranselecPending, getPending } from '../api'
import { cell, formatInteger, formatNumber } from '../format'
import { PENDING_STAGE_LABELS, PENDING_STAGE_ORDER } from '../lib/pendingStage'
import { useReads } from '../lib/useFilters'
import { CompositionBar, type CompositionSegment } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Figure, SectionHeader } from '../ui/Primitives'
import { AlertBanner, LoadingBlock } from './StateViews'
import { StatusPill } from './StatusPill'

function stageSegments(pending: TranselecPending): CompositionSegment[] {
  const tones = ['late', 'progress', 'struck'] as const
  return PENDING_STAGE_ORDER.map((stage, index) => ({
    key: stage,
    label: PENDING_STAGE_LABELS[stage],
    value: pending.stages[stage],
    tone: tones[index],
  }))
}

export function LegacyPendingSection({
  filters,
  selectedRow,
  onOpenRow,
}: {
  filters: TranselecFilterState
  selectedRow: number | null
  onOpenRow: (row: ResumenRow) => void
}) {
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<TranselecPending>(
    useCallback(
      () => getPending(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )

  return (
    <details className="how" data-testid="legacy-pending">
      <summary>Pendientes prioritarios (regla anterior)</summary>
      <div className="how-body">
        {failure && <AlertBanner title={failure.title}>{failure.message}</AlertBanner>}
        {!data && loading && <LoadingBlock label="Cargando los PMF pendientes…" shape="bar" />}
        {data && (
          <section id="pendingzone" data-testid="pending-zone">
            <div className="pending-lead">
              <Figure
                lead
                testId="pending-count"
                value={`${formatInteger(data.pending_pmf_count)} de ${formatInteger(
                  data.total_pmf_count,
                )}`}
                label="PMF pendientes prioritarios"
                note={`${formatNumber(data.pending_pmf_percentage)}% de los PMF del alcance seleccionado`}
              />
              <CompositionBar
                title="Etapa, según el texto de «Estado»"
                noun="PMF pendientes"
                testId="pending-stage"
                lead={false}
                segments={stageSegments(data)}
              />
            </div>

            <p className="hint">
              Regla anterior a «Estado», que el Resumen todavía usa: un PMF es pendiente
              prioritario si le falta el N.º de ingreso o si su «Estado» menciona un rechazo. No se
              basa en el «Estado resumido». La etapa se deduce del texto de «Estado»; no es una
              clasificación confirmada por CONAF.
            </p>
            <HowCalculated bases={[data.basis, data.stage_basis]} testId="pending-how" />

            <SectionHeader
              id="pending-rows-title"
              title="Cola de PMF pendientes"
              meta={`${formatInteger(data.rows.length)} filas de origen · seleccione una para ver el detalle del PMF`}
            />
            <div className="tablewrap">
              <table className="queue-table rows-table">
                <thead>
                  <tr>
                    <th scope="col">PMF</th>
                    <th scope="col">Predio de reforestación</th>
                    <th scope="col">Carpeta PMF</th>
                    <th scope="col">Carpeta normalizada</th>
                    <th scope="col">Predio</th>
                    <th scope="col">Rol</th>
                    <th scope="col">Estado resumido</th>
                    <th scope="col">Motivo</th>
                    <th scope="col">N.º ingreso</th>
                    <th scope="col">Empresa</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr
                      key={row.source_row_number}
                      tabIndex={0}
                      aria-selected={selectedRow === row.source_row_number}
                      aria-haspopup="dialog"
                      data-testid={`pending-row-${row.source_row_number}`}
                      onClick={() => onOpenRow(row)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          onOpenRow(row)
                        }
                      }}
                    >
                      <td>
                        <b>{row.pmf}</b>
                      </td>
                      <td>{cell(row.predio_ref, 'Sin información')}</td>
                      <td>{cell(row.carpeta_source)}</td>
                      <td>{cell(row.carpeta_normalizada)}</td>
                      <td>{cell(row.numero_predio)}</td>
                      <td>{cell(row.rol)}</td>
                      <td>
                        <StatusPill value={row.estado_resumido} />
                      </td>
                      <td>{cell(row.tipo_rechazo, '—')}</td>
                      <td>{cell(row.numero_ingreso, 'Sin ingreso')}</td>
                      <td>{cell(row.empresa)}</td>
                    </tr>
                  ))}
                  {data.rows.length === 0 && (
                    <tr>
                      <td colSpan={10} className="empty">
                        No hay PMF pendientes prioritarios para el alcance seleccionado.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </details>
  )
}
```

- [ ] **Step 7: Write the failing page tests**

Create `src/pages/EstadoPage.test.tsx`:

```tsx
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EstadoPage } from './EstadoPage'
import { EMPTY_FILTERS, type TranselecAef } from '../api'
import type { FilterController } from '../lib/useFilters'
import { RouterProvider } from '../router'
import { makeLifecycle, makePending } from '../test/factories'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    getLifecycle: vi.fn(),
    getPending: vi.fn(),
    getPmfDetail: vi.fn(),
    getAef: vi.fn(),
  }
})

const { getLifecycle, getPending, getPmfDetail, getAef } = await import('../api')

const controller: FilterController = {
  filters: EMPTY_FILTERS,
  draftQuery: '',
  setQuery: () => {},
  setField: () => {},
  replaceFilters: () => {},
  reset: () => {},
}

function renderPage() {
  render(
    <RouterProvider initialPath="/transelec/estado">
      <EstadoPage filterController={controller} sourceFields={null} />
    </RouterProvider>,
  )
}

describe('EstadoPage', () => {
  beforeEach(() => {
    vi.mocked(getLifecycle).mockReset()
    vi.mocked(getLifecycle).mockResolvedValue({ ok: true, data: makeLifecycle() })
    vi.mocked(getPending).mockReset()
    vi.mocked(getPending).mockResolvedValue({ ok: true, data: makePending() })
    vi.mocked(getPmfDetail).mockReset()
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: false,
      status: 404,
      error: 'No se encontró el PMF solicitado en la versión activa.',
    })
    vi.mocked(getAef).mockReset()
    vi.mocked(getAef).mockResolvedValue({ ok: true, data: { pmfs: [] } as unknown as TranselecAef })
  })

  it('leads with the groups and the steps inside «En trámite»', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('estado-zone')).toBeInTheDocument())
    expect(screen.getByTestId('estado-group-aprobado')).toHaveTextContent('1')
    expect(screen.getByTestId('estado-group-en_tramite')).toHaveTextContent('2')
    expect(screen.getByTestId('estado-group-sin_clasificar')).toHaveTextContent('1')
    expect(screen.getByTestId('estado-step-rechazado_esperando_recurso')).toHaveTextContent('1')
    expect(screen.getByTestId('estado-how')).toHaveTextContent('lifecycle_pmf_v1')
  })

  it('opens the PMF drawer with its «Proceso CONAF» block', async () => {
    renderPage()
    await userEvent.click(await screen.findByTestId('estado-row-3'))
    const block = await screen.findByTestId('drawer-lifecycle')
    expect(block).toHaveTextContent('En trámite')
    expect(block).toHaveTextContent('Rechazado, esperando recurso')
  })

  it('keeps the old pending rule, closed, below the table', async () => {
    renderPage()
    const legacy = await screen.findByTestId('legacy-pending')
    expect(legacy.tagName).toBe('DETAILS')
    expect(legacy).not.toHaveAttribute('open')
    await waitFor(() =>
      expect(within(legacy).getByTestId('pending-count')).toHaveTextContent('2 de 6'),
    )
  })

  it('offers no clear button when nothing is filtered', async () => {
    renderPage()
    await screen.findByTestId('estado-zone')
    expect(screen.queryByTestId('clear-estado-filters')).toBeNull()
  })
})
```

- [ ] **Step 8: Run them to verify they fail**

Run: `npm test -- src/pages/EstadoPage.test.tsx`
Expected: FAIL. `Failed to resolve import "./EstadoPage"`.

- [ ] **Step 9: Create `src/pages/EstadoPage.tsx`**

```tsx
/**
 * `/transelec/estado` — where each plan (PMF) stands in CONAF's process.
 *
 * Replaces «Pendientes» (meeting of 2026-10-02; spec
 * docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md).
 * Everything is computed by `GET /transelec/lifecycle` under the current
 * filter state with `lifecycle_pmf_v1`: the group from the first row's
 * «Estado resumido», the step inside «En trámite» from its «Estado». A
 * rejection is a step, never an end. Whatever the rule does not recognize is
 * «Sin clasificar», with its reason, and is listed in Calidad.
 *
 * Kept from the former page: the filter chips with one «Quitar filtros»
 * button, the 90-day consultation toggle (TR-FUNC-031), and — closed by
 * default — the old «Pendientes prioritarios» rule (`LegacyPendingSection`).
 *
 * `EstadoTable` takes `extraColumns`, so the 90 días hábiles work adds
 * «Plazo CONAF» without touching this page's rule.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type LifecycleRow,
  type ResumenRow,
  type TranselecLifecycle,
  getLifecycle,
  observedServerNow,
} from '../api'
import { EstadoTable } from '../components/EstadoTable'
import { LegacyPendingSection } from '../components/LegacyPendingSection'
import { OverduePanel } from '../components/OverduePanel'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { formatInteger } from '../format'
import { classifyFailure } from '../lib/apiState'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { lifecycleGroupSegments, lifecycleStepSegments } from '../lib/lifecycle'
import { selectOverdueRows } from '../lib/overdue'
import { collectAllRows } from '../lib/rowCollection'
import { useReads, type FilterController } from '../lib/useFilters'
import { CompositionBar } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Chip, SectionHeader } from '../ui/Primitives'

export function EstadoPage({
  filterController,
  sourceFields = null,
}: {
  filterController: FilterController
  /** Contract fields the published workbook had, for the detail drawer. */
  sourceFields?: readonly string[] | null
}) {
  const { filters, replaceFilters, reset } = filterController
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<TranselecLifecycle>(
    useCallback(
      () => getLifecycle(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )

  const [openRow, setOpenRow] = useState<ResumenRow | null>(null)
  const [overdueOpen, setOverdueOpen] = useState(false)
  const [overdueRows, setOverdueRows] = useState<ResumenRow[]>([])
  const [overdueLoading, setOverdueLoading] = useState(false)
  const [overdueError, setOverdueError] = useState<string | null>(null)
  const [overdueReference, setOverdueReference] = useState<Date | null>(null)
  const overdueRequestId = useRef(0)

  // The 90-day consultation, moved unchanged from the former Pendientes
  // page: it follows the filter state like every other read, so it never
  // shows rows computed under a scope the page has left.
  useEffect(() => {
    if (!overdueOpen) return

    const id = ++overdueRequestId.current
    let cancelled = false
    setOverdueLoading(true)
    setOverdueError(null)
    setOverdueRows([])

    const reference = observedServerNow() ?? new Date()
    setOverdueReference(reference)

    void collectAllRows(filters).then((result) => {
      if (cancelled || id !== overdueRequestId.current) return
      setOverdueLoading(false)
      if (!result.ok) {
        setOverdueError(classifyFailure(result).message)
        return
      }
      setOverdueRows(selectOverdueRows(result.rows, reference))
    })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overdueOpen, key])

  const chips = activeFilterChips(filters)
  const openLifecycle: LifecycleRow | null =
    openRow && data ? (data.rows.find((entry) => entry.pmf === openRow.pmf) ?? null) : null

  if (failure && !data) {
    return (
      <div className="page">
        <StateBlock view={failure} />
      </div>
    )
  }

  return (
    <div className="page enter">
      <SectionHeader
        title="Estado"
        meta="Dónde está cada PMF en la tramitación CONAF. Un rechazo es un paso, no un final."
      />

      {chips.length > 0 && (
        <div className="active-filters no-print" style={{ paddingBottom: 'var(--s-5)' }}>
          <span className="eyebrow">Alcance filtrado</span>
          {chips.map((chip) => (
            <Chip
              key={chip.key}
              onRemove={() => replaceFilters(withoutChip(filters, chip))}
              removeLabel={`Quitar el filtro ${chip.label}: ${chip.value}`}
            >
              {chip.label}: {chip.value}
            </Chip>
          ))}
        </div>
      )}

      {failure && data && <AlertBanner title={failure.title}>{failure.message}</AlertBanner>}

      {!data && loading && <LoadingBlock label="Cargando el estado de los PMF…" shape="bar" />}

      {data && (
        <section id="estadozone" data-testid="estado-zone">
          <div className="pending-lead">
            <CompositionBar
              title="PMF por grupo"
              noun="PMF"
              testId="estado-group"
              segments={lifecycleGroupSegments(data)}
            />
            <CompositionBar
              title="En trámite, por paso"
              noun="PMF en trámite"
              testId="estado-step"
              lead={false}
              segments={lifecycleStepSegments(data)}
            />
          </div>

          <p className="hint">
            El grupo sale del «Estado resumido» de la primera fila de cada PMF; el paso, de su
            «Estado». «Rechazado» es un paso dentro de «En trámite»: todo rechazo termina en
            «Aprobado», «Descartado» o «Desistido». Lo que esta regla no reconoce queda «Sin
            clasificar» y se lista en Calidad. Categorías provisionales hasta que Campo Digital las
            confirme.
          </p>
          <HowCalculated bases={[data.basis]} testId="estado-how" />

          <div className="btns no-print" style={{ margin: 'var(--s-5) 0' }}>
            {chips.length > 0 && (
              <button
                type="button"
                className="btn alt"
                onClick={reset}
                data-testid="clear-estado-filters"
              >
                Quitar filtros y ver todos los PMF
              </button>
            )}
            <button
              type="button"
              className={overdueOpen ? 'btn' : 'btn alt'}
              aria-pressed={overdueOpen}
              onClick={() => setOverdueOpen((value) => !value)}
              data-quick="overdue"
            >
              {overdueOpen ? 'Ocultar los ingresos sobre 90 días' : '¿Qué ingresos superaron 90 días?'}
            </button>
          </div>

          {overdueOpen && (
            <OverduePanel
              rows={overdueRows}
              reference={overdueReference}
              loading={overdueLoading}
              error={overdueError}
              onClose={() => setOverdueOpen(false)}
            />
          )}

          <section className="ruled" aria-labelledby="estado-rows-title">
            <SectionHeader
              id="estado-rows-title"
              title="PMF del alcance"
              meta={`${formatInteger(data.rows.length)} PMF · seleccione uno para ver su detalle`}
            />
            <EstadoTable
              rows={data.rows}
              selectedRow={openRow?.source_row_number ?? null}
              onOpen={setOpenRow}
            />
          </section>

          <section className="ruled">
            <LegacyPendingSection
              filters={filters}
              selectedRow={openRow?.source_row_number ?? null}
              onOpenRow={setOpenRow}
            />
          </section>
        </section>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          lifecycle={openLifecycle}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 10: Run the page and table tests**

Run: `npm test -- src/pages/EstadoPage.test.tsx src/components/EstadoTable.test.tsx`
Expected: PASS.

- [ ] **Step 11: Type-check, lint, full unit suite**

Run: `npx tsc -b && npm run lint && npm test`
Expected: clean and all PASS.

- [ ] **Step 12: Commit**

```bash
git add src/lib/estadoColumns.tsx src/components/EstadoTable.tsx src/components/EstadoTable.test.tsx src/components/LegacyPendingSection.tsx src/pages/EstadoPage.tsx src/pages/EstadoPage.test.tsx
git commit -m "feat(transelec-dashboard): Estado page with lifecycle groups, steps and an extensible table" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Route, navigation, redirect, page path and e2e

**Files:**
- Modify: `products/transelect/dashboard/src/router.tsx` (lines 20-30)
- Modify: `products/transelect/dashboard/src/components/AppHeader.tsx` (line 58)
- Modify: `products/transelect/dashboard/src/App.tsx`. Imports are at lines 1-25, `Shell` starts at line 27, the switch is at 196-201.
- Delete: `products/transelect/dashboard/src/pages/PendientesPage.tsx`
- Modify: `products/transelect/dashboard/src/pages/ResumenPage.tsx` (lines 183, 305-306)
- Modify: `products/transelect/dashboard/src/components/QualityPanel.tsx` (lines 64-65)
- Modify: `products/transelect/dashboard/src/App.test.tsx`, `src/components/Chrome.test.tsx`
- Modify: `apps/api/app/main.py` (`TRANSELEC_SPA_PAGE_PATHS`, lines 280-292)
- Modify: `products/transelect/dashboard/tests/e2e/dashboard.spec.ts`, `navigation.spec.ts`, `print-responsive.spec.ts`

**Interfaces:**
- Consumes: `EstadoPage` (Task 5) and the `lifecycleBody` stub (Task 3).
- Produces: `ROUTES.estado = '/transelec/estado'`; `ROUTES.pendientes` is kept for one release as a redirect; the page path `"transelec/estado"`.

- [ ] **Step 1: Write the failing vitest for the redirect and nav**

In `src/App.test.tsx`:

(a) In the `vi.mock('./api', …)` factory, add `getLifecycle: vi.fn(),` after `getPending: vi.fn(),`.

(b) In `stubDashboardReads`, change the array to
`[api.getSummary, api.getPending, api.getLifecycle, api.getOwnerStatus, api.getReport, api.listRows]`.

(c) In the `beforeEach` reset list, add `api.getLifecycle,` after `api.getPending,`.

(d) Change `render(<App initialPath={ROUTES.pendientes} />)` in "sends a signed-out visitor to the front door…" to `render(<App initialPath={ROUTES.estado} />)`.

(e) In "gives the viewer the panel without any administrative navigation", change `{ name: 'Pendientes' }` to `{ name: 'Estado' }`.

(f) Append inside `describe('App session lifecycle', …)`:

```tsx
  it('sends the old Pendientes address to Estado, keeping the filters', async () => {
    window.history.replaceState({}, '', '/transelec/pendientes?q=legal')
    vi.mocked(api.getMe).mockResolvedValue({ ok: true, data: ADMIN })
    try {
      render(<App initialPath="/transelec/pendientes?q=legal" />)

      await waitFor(() => expect(window.location.pathname).toBe('/transelec/estado'))
      expect(window.location.search).toBe('?q=legal')
      expect(nav().getByRole('link', { name: 'Estado' })).toHaveAttribute('aria-current', 'page')
    } finally {
      window.history.replaceState({}, '', '/')
    }
  })
```

In `src/components/Chrome.test.tsx`, change
`for (const label of ['Resumen', 'Explorador', 'Pendientes', 'Calidad'])` to
`for (const label of ['Resumen', 'Explorador', 'Estado', 'Calidad'])`.

- [ ] **Step 2: Run them to verify they fail**

Run: `npm test -- src/App.test.tsx src/components/Chrome.test.tsx`
Expected: FAIL. TS error `Property 'estado' does not exist`, or no link named 'Estado'.

- [ ] **Step 3: Router**

In `src/router.tsx`, change the `ROUTES` object to:

```tsx
export const ROUTES = {
  resumen: '/transelec',
  explorador: '/transelec/explorador',
  estado: '/transelec/estado',
  // Retired 2026-10-04 in favour of «Estado»; kept one release so old links
  // and bookmarks land on it (App.tsx replaces the address).
  pendientes: '/transelec/pendientes',
  aef: '/transelec/seguimiento-aef',
  calidad: '/transelec/calidad',
  datos: '/transelec/datos',
  importar: '/transelec/importar',
  versiones: '/transelec/versiones',
  accesos: '/transelec/accesos',
} as const
```

- [ ] **Step 4: Navigation**

In `src/components/AppHeader.tsx`, replace
`{ to: ROUTES.pendientes, label: 'Pendientes', filtered: true },` with:

```tsx
  { to: ROUTES.estado, label: 'Estado', filtered: true, also: [ROUTES.pendientes] },
```

- [ ] **Step 5: App switch and redirect**

In `src/App.tsx`:

(a) Replace `import { PendientesPage } from './pages/PendientesPage'` with
`import { EstadoPage } from './pages/EstadoPage'`. Keep the import list sorted
as it is: place the line after `import { DatosPage } from './pages/DatosPage'`.

(b) In `Shell`, replace `const { pathname } = useRouter()` with
`const { pathname, search, navigate } = useRouter()`. Directly after
`const filterController = useFilters()` and its comment, add:

```tsx
  // «Pendientes» became «Estado» on 2026-10-04. Old links and bookmarks keep
  // working for one release: the address is replaced, filters and all, so
  // Back never returns to the retired one.
  useEffect(() => {
    if (route === ROUTES.pendientes) navigate(`${ROUTES.estado}${search}`, { replace: true })
  }, [route, search, navigate])
```

(c) Replace the `case ROUTES.pendientes:` block with:

```tsx
      case ROUTES.estado:
      case ROUTES.pendientes:
        return (
          <EstadoPage
            filterController={filterController}
            sourceFields={activeImport?.source_fields ?? null}
          />
        )
```

(d) Delete `src/pages/PendientesPage.tsx`:

```bash
git rm src/pages/PendientesPage.tsx
```

- [ ] **Step 6: Point the Resumen and Calidad links at Estado**

In `src/pages/ResumenPage.tsx`:
- Change `pendientes: ROUTES.pendientes,` to `pendientes: ROUTES.estado,`.
- Change the `<Link to={ROUTES.pendientes} className="btn">` block to:

```tsx
              <Link to={ROUTES.estado} className="btn">
                Ver el estado de los PMF
              </Link>
```

In `src/components/QualityPanel.tsx`, change:

```tsx
              <Link to={`${ROUTES.pendientes}${search}`} className="quality-go">
                Ver en Pendientes →
              </Link>
```

to:

```tsx
              <Link to={`${ROUTES.estado}${search}`} className="quality-go">
                Ver en Estado →
              </Link>
```

- [ ] **Step 7: Add the page path on the server**

In `apps/api/app/main.py`, in `TRANSELEC_SPA_PAGE_PATHS`, add
`"transelec/estado",` after `"transelec/explorador",`. Change the
`"transelec/pendientes",` line to:

```python
("transelec/estado",)
# Redirects to transelec/estado in the browser (one release, 2026-10-04).
("transelec/pendientes",)
```

- [ ] **Step 8: Run unit tests (dashboard and server)**

Run (dashboard dir): `npm test && npx tsc -b && npm run lint`
Expected: all PASS, clean.

Run (repo root): `uv run pytest apps/api/tests/test_dashboard_static.py apps/api/tests/test_transelec_lifecycle_routes.py -v`
Expected: PASS. `test_spa_page_paths_match_every_dashboard_route` sees
`transelec/estado` on both sides. The path guard still finds no overlap,
because the API read is `transelec/lifecycle`.

- [ ] **Step 9: Update the e2e specs**

In `tests/e2e/dashboard.spec.ts`:

(a) Replace the `openPendientes` helper with:

```ts
async function openEstado(page: Page) {
  await page.goto('/transelec/estado')
  await expect(page.getByTestId('estado-zone')).toBeVisible()
}

/** The old «Pendientes prioritarios» rule, closed by default inside Estado. */
async function openLegacyPending(page: Page) {
  await openEstado(page)
  await page.getByText('Pendientes prioritarios (regla anterior)').click()
  await expect(page.getByTestId('pending-zone')).toBeVisible()
}
```

(b) Replace the three tests "TR-FUNC-024/032: the Resumen attention card and
the Pendientes section agree", "Pendientes: a narrowed scope offers one
button that clears it" and "Pendientes: every queue row opens the PMF
detail, by mouse and by keyboard" with:

```ts
test('TR-FUNC-024/032: the Resumen attention card and the old pending rule agree', async ({
  page,
}) => {
  await openResumen(page)
  await expect(page.getByTestId('kpi-pendientes')).toHaveText('5')

  await page.getByRole('link', { name: /Ver la cola de trabajo/ }).click()
  await expect(page).toHaveURL(/\/transelec\/estado$/)
  await expect(page.getByTestId('estado-zone')).toBeVisible()
  await page.getByText('Pendientes prioritarios (regla anterior)').click()
  await expect(page.getByTestId('pending-count')).toHaveText('5 de 12')

  // Unfiltered, there is nothing to clear, so no button pretends to act.
  await expect(page.getByTestId('clear-estado-filters')).toHaveCount(0)
})

test('Estado: a narrowed scope offers one button that clears it', async ({ page }) => {
  await page.goto('/transelec/estado?q=legal')
  await expect(page.getByTestId('estado-zone')).toBeVisible()
  await page.getByTestId('clear-estado-filters').click()
  await expect(page).toHaveURL(/\/transelec\/estado$/)
  await expect(page.getByTestId('clear-estado-filters')).toHaveCount(0)
})

test('Estado: every PMF row opens the PMF detail, by mouse and by keyboard', async ({ page }) => {
  await openEstado(page)
  const row = page.getByTestId('estado-row-2')
  // The first cell, not the row's centre: the last column holds the
  // Oficina Virtual link, which deliberately does not open the drawer.
  await row.locator('td').first().click()
  const drawer = page.getByTestId('row-drawer')
  await expect(drawer).toBeVisible()
  await expect(drawer).toContainText('PMF-002')
  await expect(page.getByTestId('drawer-provenance')).toHaveText(
    'Fila de origen 2 de la hoja «Resumen»',
  )
  await expect(page.getByTestId('drawer-lifecycle')).toContainText('En evaluación')
  await expect(row).toHaveAttribute('aria-selected', 'true')
  await page.getByTestId('row-drawer-close').click()
  await expect(drawer).toBeHidden()
  await expect(row).toBeFocused()

  await page.getByTestId('estado-row-3').focus()
  await page.keyboard.press('Enter')
  await expect(drawer).toContainText('PMF-003')
})

test('Estado: groups, steps and the table come from lifecycle_pmf_v1', async ({ page }) => {
  await openEstado(page)
  await expect(page.getByTestId('estado-group-aprobado')).toHaveText('1')
  await expect(page.getByTestId('estado-group-en_tramite')).toHaveText('4')
  await expect(page.getByTestId('estado-group-sin_clasificar')).toHaveText('1')
  await expect(page.getByTestId('estado-step-rechazado_esperando_recurso')).toHaveText('1')
  await expect(page.getByTestId('estado-table').locator('tbody tr')).toHaveCount(6)
  await expect(page.getByTestId('estado-row-1')).toContainText('Rechazado, esperando recurso')
  await expect(page.getByTestId('estado-row-1')).toContainText('Legal')
  await expect(page.getByTestId('estado-row-6')).toContainText('Sin clasificar')
  await expect(page.getByTestId('estado-how')).toContainText('lifecycle_pmf_v1')
})

test('Estado: the old Pendientes address lands on Estado with its filters', async ({ page }) => {
  await page.goto('/transelec/pendientes?q=legal')
  await expect(page).toHaveURL(/\/transelec\/estado\?q=legal$/)
  await expect(page.getByTestId('estado-zone')).toBeVisible()
  await expect(
    page
      .getByRole('navigation', { name: 'Secciones de Transelec' })
      .getByRole('link', { name: 'Estado' }),
  ).toHaveAttribute('aria-current', 'page')
})

test('Estado: the Oficina Virtual opens CONAF in a new tab and the N.º can be copied', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await openEstado(page)
  const link = page.getByTestId('estado-ov-3-link')
  await expect(link).toHaveAttribute('href', 'https://oficinavirtual.conaf.cl/consultas/index.php')
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer')

  await page.getByTestId('estado-ov-3-copy').click()
  // Copying inside a row must not open the drawer behind it.
  await expect(page.getByTestId('row-drawer')).toHaveCount(0)
  // The most recent ingreso is the one copied.
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('ING-3-R')
})
```

(c) In "no section shows a raw rule identifier in its reading text":
- change `'/transelec/pendientes',` to `'/transelec/estado',`;
- change the regex to
  `/_legacy|_first_row|pmf_from_source_rows|lifecycle_pmf|canónic|deduplica/`.

(d) In "TR-FUNC-031: the overdue consultation uses a computed reference
date…", replace `await openPendientes(page)` with `await openEstado(page)`.

(e) In "TR-FUNC-017/031: the overdue panel follows a filter change…":
- replace `page.goto('/transelec/pendientes')` with `page.goto('/transelec/estado')`;
- replace `page.goto('/transelec/pendientes?q=rechaz')` with `page.goto('/transelec/estado?q=rechaz')`;
- replace both `page.getByTestId('pending-zone')` visibility waits with `page.getByTestId('estado-zone')`.

(f) In "TR-FUNC-032/033: Pendientes shows the count, the stages once, and the
detail table":
- rename the test to `'TR-FUNC-032/033: the old pending rule keeps its count, its stages once, and its detail table'`;
- replace `await openPendientes(page)` with `await openLegacyPending(page)`.

In `tests/e2e/navigation.spec.ts`:
- replace `['Pendientes', '/transelec/pendientes', 'pending-zone'],` with
  `['Estado', '/transelec/estado', 'estado-zone'],`;
- in the viewer test, change
  `['Resumen', 'Explorador', 'Pendientes', 'AEF', 'Calidad']` to
  `['Resumen', 'Explorador', 'Estado', 'AEF', 'Calidad']`.

In `tests/e2e/print-responsive.spec.ts`, replace
`['pendientes', '/transelec/pendientes', 'pending-zone'],` with
`['estado', '/transelec/estado', 'estado-zone'],`.

- [ ] **Step 10: Run the e2e suite**

Make sure no other worktree is running Playwright (port 5299). Then:

Run: `npm run test:e2e`
Expected: all PASS. If a test fails on visibility of `pending-zone`, it is
reading the legacy section without opening it; use `openLegacyPending`.

- [ ] **Step 11: Commit**

```bash
git add -A src tests ../../../apps/api/app/main.py
git commit -m "feat(transelec-dashboard): «Estado» replaces «Pendientes»; the old address redirects" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(The `git add` runs from `products/transelect/dashboard`. Check
`git status` afterwards: `apps/api/app/main.py` and the deletion of
`PendientesPage.tsx` must be staged.)

---

### Task 7: Calidad lists the PMFs to review

**Files:**
- Create: `products/transelect/dashboard/src/components/LifecycleQualityPanel.tsx` + `LifecycleQualityPanel.test.tsx`
- Modify: `products/transelect/dashboard/src/pages/CalidadPage.tsx` (imports 24-41, data 43-67, sections ~117-129)
- Modify: `products/transelect/dashboard/tests/e2e/dashboard.spec.ts` (append one test)

**Interfaces:**
- Consumes: `getLifecycle`, `TranselecLifecycle`, `needsReview`, the label maps and `makeLifecycle` (Task 3); `ROUTES.estado` (Task 6).
- Produces: `LifecycleQualityPanel({ lifecycle, filters? })`, with test ids `lifecycle-quality`, `lifecycle-review-count`, `lifecycle-review-list`, `lifecycle-review-<source_row_number>` and `how-lifecycle-review`.

- [ ] **Step 1: Write the failing test**

Create `src/components/LifecycleQualityPanel.test.tsx`:

```tsx
import { render as renderInDom, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { LifecycleQualityPanel } from './LifecycleQualityPanel'
import { ROUTES, RouterProvider } from '../router'
import { makeLifecycle } from '../test/factories'

function render(node: ReactNode) {
  return renderInDom(<RouterProvider initialPath={ROUTES.calidad}>{node}</RouterProvider>)
}

describe('LifecycleQualityPanel', () => {
  it('lists each PMF to review with its row and its reason', () => {
    render(<LifecycleQualityPanel lifecycle={makeLifecycle()} />)

    expect(screen.getByTestId('lifecycle-review-count')).toHaveTextContent('1')
    const item = screen.getByTestId('lifecycle-review-7')
    expect(item).toHaveTextContent('MP004')
    expect(item).toHaveTextContent('fila 7')
    expect(item).toHaveTextContent('«Estado» y «Estado resumido» no coinciden')
    expect(item).toHaveTextContent('Sus filas no tienen el mismo')
    expect(screen.getByRole('link', { name: 'Ver en Estado →' })).toHaveAttribute(
      'href',
      '/transelec/estado',
    )
  })

  it('reads calm when every PMF is placed', () => {
    render(<LifecycleQualityPanel lifecycle={makeLifecycle({ rows: [] })} />)

    expect(screen.getByTestId('lifecycle-review-count')).toHaveTextContent('0')
    expect(screen.queryByTestId('lifecycle-review-list')).toBeNull()
  })

  it('keeps the rule one «Cómo se calcula» away', () => {
    render(<LifecycleQualityPanel lifecycle={makeLifecycle()} />)

    const how = screen.getByTestId('how-lifecycle-review')
    expect(how.tagName).toBe('DETAILS')
    expect(how).toHaveTextContent('lifecycle_pmf_v1')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test -- src/components/LifecycleQualityPanel.test.tsx`
Expected: FAIL. `Failed to resolve import "./LifecycleQualityPanel"`.

- [ ] **Step 3: Create `src/components/LifecycleQualityPanel.tsx`**

```tsx
/**
 * Calidad: the PMFs `lifecycle_pmf_v1` could not place, and those whose rows
 * disagree on their status (spec 2026-10-04). Listed with their row and
 * reason so a person reads the planilla; nothing here is resolved.
 */
import type { TranselecFilterState, TranselecLifecycle } from '../api'
import { formatInteger } from '../format'
import { searchFromFilters } from '../lib/filterUrl'
import { LIFECYCLE_FLAG_LABELS, LIFECYCLE_REASON_LABELS, needsReview } from '../lib/lifecycle'
import { Link, ROUTES } from '../router'
import { HowCalculated } from '../ui/HowCalculated'

export function LifecycleQualityPanel({
  lifecycle,
  filters,
}: {
  lifecycle: TranselecLifecycle
  /** Carried into the link, so the finding opens under the same scope. */
  filters?: TranselecFilterState
}) {
  const review = lifecycle.rows.filter(needsReview)
  const search = filters ? searchFromFilters(filters) : ''

  return (
    <div data-testid="lifecycle-quality">
      <ul className="quality" aria-label="PMF que la regla de «Estado» no pudo clasificar">
        <li className="quality-item" data-tone={review.length > 0 ? 'warn' : 'calm'}>
          <p className="quality-headline">
            <b data-testid="lifecycle-review-count">{formatInteger(review.length)}</b>
            <span>PMF para revisar en «Estado»</span>
          </p>
          {review.length === 0 ? (
            <p className="quality-what">
              Todos los PMF del alcance tienen un grupo y un paso reconocidos.
            </p>
          ) : (
            <>
              <ul className="variant-list" data-testid="lifecycle-review-list">
                {review.map((row) => (
                  <li
                    key={row.source_row_number}
                    data-testid={`lifecycle-review-${row.source_row_number}`}
                  >
                    <b>{row.pmf}</b> · fila {formatInteger(row.source_row_number)} ·{' '}
                    {[
                      row.lifecycle_reason ? LIFECYCLE_REASON_LABELS[row.lifecycle_reason] : null,
                      ...row.lifecycle_flags.map((flag) => LIFECYCLE_FLAG_LABELS[flag]),
                    ]
                      .filter(Boolean)
                      .join('; ')}
                  </li>
                ))}
              </ul>
              <p className="quality-todo">
                <b>Qué revisar:</b> los valores de «Estado» y «Estado resumido» de esas filas en la
                planilla.
              </p>
              <Link to={`${ROUTES.estado}${search}`} className="quality-go">
                Ver en Estado →
              </Link>
            </>
          )}
          <HowCalculated bases={[lifecycle.basis]} testId="how-lifecycle-review" />
        </li>
      </ul>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- src/components/LifecycleQualityPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Add the block to `CalidadPage`**

In `src/pages/CalidadPage.tsx`:

(a) Add `type TranselecLifecycle,` and `getLifecycle,` to the `from '../api'`
import. Add `import { LifecycleQualityPanel } from '../components/LifecycleQualityPanel'`
after the `ConflictPanel` import.

(b) Add `lifecycle: TranselecLifecycle` to `interface CalidadData`.

(c) Replace the `useReads` body with:

```tsx
    useCallback(async () => {
      const [summary, ownerStatus, report, lifecycle] = await Promise.all([
        getSummary(filters),
        getOwnerStatus(filters),
        getReport(filters),
        getLifecycle(filters),
      ])
      if (!summary.ok) return summary
      if (!ownerStatus.ok) return ownerStatus
      if (!report.ok) return report
      if (!lifecycle.ok) return lifecycle
      return {
        ok: true,
        data: {
          summary: summary.data,
          ownerStatus: ownerStatus.data,
          report: report.data,
          lifecycle: lifecycle.data,
        },
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]),
```

(d) Directly after the `conflict-title` section (the one rendering
`<ConflictPanel …/>`), add:

```tsx
          <section className="ruled" aria-labelledby="lifecycle-review-title">
            <SectionHeader
              id="lifecycle-review-title"
              title="PMF que la regla de «Estado» no pudo clasificar"
              meta="Valores que la regla no reconoce, estados que se contradicen y filas que no coinciden."
            />
            <LifecycleQualityPanel lifecycle={data.lifecycle} filters={filters} />
          </section>
```

- [ ] **Step 6: Add the e2e test**

Append to `tests/e2e/dashboard.spec.ts`:

```ts
test('Calidad: the PMFs the Estado rule could not place are listed with their reason', async ({
  page,
}) => {
  await openCalidad(page)
  await expect(page.getByTestId('lifecycle-review-count')).toHaveText('1')
  await expect(page.getByTestId('lifecycle-review-6')).toContainText(
    '«Estado» y «Estado resumido» no coinciden',
  )
})
```

- [ ] **Step 7: Run everything for the dashboard**

Run: `npx tsc -b && npm run lint && npm test && npm run test:e2e`
Expected: all PASS. Run e2e only when no other worktree is using port 5299.

- [ ] **Step 8: Commit**

```bash
git add src/components/LifecycleQualityPanel.tsx src/components/LifecycleQualityPanel.test.tsx src/pages/CalidadPage.tsx tests/e2e/dashboard.spec.ts
git commit -m "feat(transelec-dashboard): Calidad lists the PMFs the Estado rule could not place" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation, full verification, hand-off

**Files:**
- Modify: `products/transelect/dashboard/README.md` (routes table, lines 9-17)
- Modify: `products/transelect/docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md` (§4.3, around line 194)

- [ ] **Step 1: Dashboard README routes**

Replace the row
`| `/transelec/pendientes` | viewer+ | Priority queue and 90-day consultation |` with:

```markdown
| `/transelec/estado` | viewer+ | Where each PMF stands (`lifecycle_pmf_v1`), the 90-day consultation, and the former pending rule (closed) |
| `/transelec/pendientes` | viewer+ | Redirects to `/transelec/estado` (kept one release from 2026-10-04) |
```

- [ ] **Step 2: UX document note**

At the end of §4.3 in
`products/transelect/docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md`
(before `### 4.4`), add:

```markdown
**Superseded 2026-10-04 (DECISION).** «Pendientes» became «Estado»
(`/transelec/estado`), per the
[Estado lifecycle design][estado-spec].
The page leads with each PMF's lifecycle group and step (`lifecycle_pmf_v1`).
The pending-priority zone described above is kept unchanged inside a closed
«Pendientes prioritarios (regla anterior)» disclosure. The 90-day toggle
stays on the page. The old address redirects for one release.

[estado-spec]: ../../../../docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md
```

The spec link resolves once `docs/transelec-estado-plazo-web-specs` is
merged. If it is not merged when this PR opens, cite the spec by path in
backticks instead of linking it, so `docs-check` passes.

- [ ] **Step 3: Full verification (repo root)**

```bash
make format-check lint typecheck architecture-check docs-check
uv run pytest products/transelect/tests apps/api/tests -q
uv run pytest -q apps/api/integration_tests/test_transelec_reads_router.py apps/api/integration_tests/test_transelec_router.py
cd products/transelect/dashboard && npx tsc -b && npm run lint && npm test && npm run build && npm run test:e2e && cd -
```

Run the integration line in the shell with the Task 0 Step 4 exports. Run
it only when no other worktree is using the test DB.

Expected: every command exits 0. Record the pass counts for the PR body.

- [ ] **Step 4: Manual check in the browser (local only)**

Run `make transelec-dev` and open `http://127.0.0.1:5200/transelec/estado`.
Sign in with the demo admin identity. Check:
- the group and step bars;
- the table;
- a row opens the drawer with «Proceso CONAF»;
- «Abrir» opens CONAF in a new tab, and «Copiar N.º» copies;
- `/transelec/pendientes` redirects;
- the Calidad block.

Use only the already-published local version. Do not upload or publish
any workbook.

- [ ] **Step 5: Commit the docs**

```bash
git add products/transelect/dashboard/README.md products/transelect/docs/design/2026-09-13-frontend-ux-rearchitecture-v1.md
git commit -m "docs(transelec): Estado replaces Pendientes in the routes and the UX record" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Hand-off (push and PR only when Rafael asks)**

Report the branch `feat/transelec-estado`, the commit list and the
verification counts. When Rafael says to publish it:

```bash
git push -u origin feat/transelec-estado
gh pr create --base main --head feat/transelec-estado \
  --title "feat(transelec): «Estado» replaces «Pendientes» with the PMF lifecycle" \
  --body "$(cat <<'EOF'
Implements docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md.

- lifecycle_pmf_v1 (transelec_ingestion/lifecycle_view.py): group from the first row's Estado resumido, step inside En trámite from Estado; rejection is a step, never an end; Descartado/Desistido kept apart; unknown labels and contradictions go to «Sin clasificar» with a reason.
- GET /api/transelec/lifecycle (not /estado: that is the dashboard page path, and the router is also mounted without /api). Reads only through _fetch_filtered_rows. `_closed_pmfs` is ready for the 90 días hábiles route.
- Dashboard: «Estado» tab with an extensible table (extraColumns), Oficina Virtual link + copy, «Proceso CONAF» in the drawer, Calidad block; the former pending rule kept closed; /transelec/pendientes redirects for one release.

Verification: <paste the pass counts from Task 8 Step 3>.

Synthetic fixtures only; no workbook was opened, imported or published.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Fill in the verification line with the real counts before running
`gh pr create`.

---

## Self-review notes (resolved inline)

- **Spec coverage:**
  - groups, steps, consistency reasons and the `filas_no_coinciden` flag →
    Task 1;
  - API with filters and viewer access → Task 2;
  - route, redirect and nav → Task 6;
  - EstadoPage bar, step breakdown with red reserved, table columns and
    drawer → Tasks 3-5;
  - Oficina Virtual link and copy → Task 4;
  - «Cómo se calcula» with the legacy bases kept → Tasks 3 and 5;
  - Calidad block → Task 7;
  - provisional copy → Tasks 3 and 5;
  - Playwright for nav, redirect, columns, link attributes, copy and
    Calidad → Tasks 6 and 7.
- **Deviation recorded:** the API path is `/transelec/lifecycle`, not
  `/estado` (see Global Constraints), and is pinned by a guard test.
- **Deviation recorded:** `LifecycleInputRow` carries only the classification
  inputs. The spec's display outputs (Tipo de rechazo, Reingreso_*, both
  ingreso pairs) come from hydrating the first row into `ResumenRowView`, as
  `/pending` does.
- **Type consistency:**
  - Python `PmfLifecycle.group/step/reason/flags` maps to JSON
    `lifecycle_group/lifecycle_step/lifecycle_reason/lifecycle_flags`, which
    maps to TS `LifecycleRow`.
  - `EstadoColumn.render(row: LifecycleRow)` is the same in
    `estadoColumns.tsx`, `EstadoTable` and its test.
