# Transelec web edits indicator, log and history — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anyone signed in sees that values were edited on the web (a header pill), opens a log of who changed what and when (including replaced and reverted edits), and can tell which Estado values and Resumen totals come from edits; the drawer's edit flow gets three fixes.

**Architecture:** The API gains one read, `GET /transelec/overrides/history`, built from `platform.transelec_field_override` with the active import's `transelec_override_state` joined in, and one summary number, `web_edited_pmf_count`. No migration. On the dashboard a `WebEditsProvider` in the shell owns the history; the header pill and its native-popover log, the Resumen hint and Ediciones web read it, and every save/revert/discard/keep refreshes it. The Explorador learns `?fila=<n>` so a log entry opens its row's drawer. Estado renders «web» chips from the `web_fields` it already receives.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core (text SQL), PostgreSQL/PostGIS 17, React 19 + TypeScript 6, Vitest + Testing Library (jsdom), Playwright (Chromium).

**Spec:** `docs/superpowers/specs/2026-10-05-transelec-web-edits-indicator-design.md` (revision `b047863`). Builds on `docs/superpowers/plans/2026-10-04-transelec-web-edits-xlsx.md` (PR #83).

## Global Constraints

- History route: `GET /api/transelec/overrides/history?limit=50` (also `/transelec/...`), `Action.VIEW`, 404 when nothing is published, `limit` 1–200, default 50.
- Entries: latest `limit` override rows, active or ended, `created_at DESC, id DESC`, no per-version cutoff.
- `state`: active edits → status against the active import (`aplicada`, `en_conflicto`, `huerfana`, `incorporada`); ended edits → `end_reason` (`superseded`, `discarded`, `kept`, `incorporated`).
- `source_row_number`: active edits → the active import's row (null for `huerfana`); ended edits → always null.
- `ended_by_display_name` is null exactly when `ended_at` is null.
- Counts over all active edits, independent of `limit`: `in_force_count` = `aplicada`; `needs_review_count` = `en_conflicto` + `huerfana`; active `incorporada` counts in neither.
- `web_edited_pmf_count`: PMFs whose first row (`first_row_wins`, within the request's filters) has `estado_resumido` or `estado` in `web_fields`.
- No audit row for reads; audit rows never carry values. No migration in this PR.
- Copy is Spanish and exactly as the spec writes it: «5 ediciones web» / «1 edición web», «· 2 por revisar», «5 en vigor», «(vacío)», «hoy 09:41» / «ayer 17:02» / «03-10-2026» (America/Santiago), state labels «en conflicto: la planilla cambió», «sin fila en la versión activa», «ya está en la planilla», «reemplazada por una edición posterior», «revertida al valor de la planilla · <quien>», «conservada al resolver un conflicto · <quien>», «y N más», «Ver todas en Ediciones web →», «Descargar planilla con ediciones (.xlsx)», «No se encontró esta fila en la versión activa.», «Los valores marcados «web» se editaron en el panel; la planilla publicada no cambió.», «Incluye 1 PMF con estado editado en la web.», «Ver ediciones», «¿Descartar el cambio sin guardar?», «Historial», «Últimas 50 ediciones».
- The popover is `<div id="edit-log" popover="auto" role="dialog" aria-labelledby="edit-log-heading">`; the pill has `popovertarget`, `aria-haspopup="dialog"`, `aria-controls`, `aria-expanded` synced from the `toggle` event; no Unicode pencil (SVG, `aria-hidden`).
- Pill hidden until the first successful load, on error, with nothing published, and when both counts are 0. Footer (Ediciones link, download) operator/admin only.
- jsdom has no Popover API (checked: `showPopover` is undefined); code guards for it and Playwright covers opening/closing.
- Synthetic fixtures only; never a planilla value in code, tests, commits or docs.
- Python checks as CI runs them: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy .`, `uv run pytest`.
- Integration tests need the disposable DB (`docker compose up -d --wait postgres-test`, port 5433) and this prefix:
  `APP_ENV=test POSTGRES_DB=campo_digital_test POSTGRES_USER=campo_digital_test POSTGRES_PASSWORD=campo_digital_test POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 PYTHONPATH=apps/api`
- Dashboard checks in `products/transelect/dashboard`: `npm test`, `npm run lint`, `npx tsc -b`, `npm run build`, `npm run test:e2e`.

## Review Focus

1. **A history row whose author or ender is the same person, and an ended edit that never had a state row.** The two `app_user` joins must not multiply rows, and an ended edit must come back with `state = end_reason` and no row number even though the state subquery has nothing for it. Test: Task 1 (`test_history_lists_every_ending_newest_first`).
2. **The bar at 1280 px with the pill and «por revisar».** The pill must not push the section links under the shell side. Test: Task 12 (`navigation.spec.ts`, pill variant of «nothing overlaps»); if it fails, the compact breakpoint moves up (recorded as a deviation).
3. **A log link whose row is not on the Explorador's first page.** `?q=<pmf>` is a substring search across every field, so other PMFs can push the row past page 1; the drawer must still open. Test: Task 6 (`falls back to the PMF detail when the row is not on the first page`).
4. **A save still in flight when the reader switches rows.** The response must not yank the drawer back to the old row. Test: Task 10 (`a save that lands after a row switch does not switch back`).
5. **Two near-identical suggestions with equal counts.** Ties resolve to the first spelling in `es` order, deterministically. Test: Task 11 (`ties go to the first spelling in Spanish order`).

---

## File Structure

| Path | Responsibility |
|---|---|
| `apps/api/app/transelec_overrides.py` (modify) | `HistoryState`, `HistoryRecord`, `HistoryPage`, `list_override_history`. |
| `apps/api/app/routers/transelec_edits.py` (modify) | `GET /overrides/history` and its response models. |
| `apps/api/app/routers/transelec.py` (modify) | `web_edited_pmf_count` on `TranselecSummaryResponse`. |
| `apps/api/integration_tests/test_transelec_overrides.py` (modify) | History and summary-count tests (this module already owns the override fixtures). |
| `products/transelect/dashboard/src/api.ts` (modify) | `TranselecHistoryEntry`, `TranselecEditHistory`, `getOverrideHistory`, `web_edited_pmf_count`. |
| `src/lib/editLog.ts` (create) | Pure log wording: pill text, state labels, Chile-time dates, entry links. |
| `src/lib/webEditsState.ts` (create) | The shared context, `useWebEdits`, `openEditLog`. |
| `src/components/WebEditsProvider.tsx` (create) | Loads/refreshes the history (§3). |
| `src/components/EditLog.tsx` (create) | The entry list (popover and Ediciones) and the popover body. |
| `src/components/WebEditsPill.tsx` (create) | The header pill and the popover element. |
| `src/lib/xlsxDownload.ts` (create) | The «web» download as a hook, shared by Ediciones and the popover footer. |
| `src/components/DrawerConfirm.tsx` (create) | A `ConfirmDialog` over the drawer that keeps Escape and Tab to itself. |
| `src/App.tsx`, `src/components/AppHeader.tsx` (modify) | Provider in the shell; pill after the version chip. |
| `src/pages/ExploradorPage.tsx` (modify) | `?fila=<n>` opens a row's drawer. |
| `src/pages/EdicionesPage.tsx` (modify) | «Historial»; refresh after keep/discard; download via the hook. |
| `src/components/EstadoTable.tsx`, `src/lib/estadoColumns.tsx`, `src/lib/plazoColumn.tsx` (modify) | «web» chips and the note. |
| `src/components/StatusHeadline.tsx` (modify) | The Resumen hint. |
| `src/components/RowDetailDrawer.tsx`, `src/components/EditableFieldsSection.tsx` (modify) | Drawer order, Tramitación by role, remount, unsaved-change confirmation, refresh. |
| `src/lib/webEdits.ts` (modify) | Grouped suggestions; `webFieldsDescription`, `editedAmong`. |
| `src/styles/components.css` (modify) | Pill, popover, log, Estado note. |
| `src/test/factories.ts` (modify) | `web_edited_pmf_count`, history factories. |
| `tests/e2e/stubs.ts`, `tests/e2e/web-edits.spec.ts`, `tests/e2e/navigation.spec.ts` (modify) | History stub; pill/log/Explorador flows; bar fit with the pill. |

---

### Task 1: API — the history list

**Files:**
- Modify: `apps/api/app/transelec_overrides.py` (after `list_overrides`)
- Modify: `apps/api/app/routers/transelec_edits.py` (after `list_field_overrides`)
- Test: `apps/api/integration_tests/test_transelec_overrides.py` (new section at the end)

**Interfaces:**
- Produces: `GET /transelec/overrides/history?limit=` → `{in_force_count: int, needs_review_count: int, entries: [{id, field, field_label, pmf, rol, numero_predio, numero_area_corta, source_row_number, web_value, planilla_value_at_edit, created_by_display_name, created_at, state, ended_at, ended_by_display_name}]}`; Python `list_override_history(connection, *, import_id: int, limit: int) -> HistoryPage`.

- [ ] **Step 1: Write the failing tests** (append to `test_transelec_overrides.py`)

```python
# ---------------------------------------------------------------------------
# The history list (indicator spec §1)
# ---------------------------------------------------------------------------


def _history(client: TestClient, limit: int | None = None) -> dict[str, Any]:
    query = "" if limit is None else f"?limit={limit}"
    response = client.get(f"/transelec/overrides/history{query}")
    assert response.status_code == 200, response.text
    return response.json()


def test_history_lists_every_ending_newest_first(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    mp001 = _row(client, "MP001", 0)["source_row_number"]
    mp003 = _row(client, "MP003", 0)["source_row_number"]

    _put(client, import_id, mp001, "estado", "A", expected="En evaluacion")
    _put(client, import_id, mp001, "estado", "B", expected="A")  # A superseded
    _put(client, import_id, mp001, "estado", "En evaluacion", expected="B")  # B discarded by a save
    reverted = _put(client, import_id, mp003, "tipo_rechazo", "Legal", expected=None).json()
    gone = client.delete(
        f"/transelec/overrides/{reverted['override_id']}", headers={"Origin": _SAME_ORIGIN}
    )
    assert gone.status_code == 204  # discarded with DELETE
    _put(client, import_id, mp003, "estado_resumido", "Desistido", expected="Aprobado")

    body = _history(client)

    assert [(e["field"], e["web_value"], e["state"]) for e in body["entries"]] == [
        ("estado_resumido", "Desistido", "aplicada"),
        ("tipo_rechazo", "Legal", "discarded"),
        ("estado", "B", "discarded"),
        ("estado", "A", "superseded"),
    ]
    in_force, *ended = body["entries"]
    assert in_force["source_row_number"] == mp003
    assert in_force["ended_at"] is None and in_force["ended_by_display_name"] is None
    assert in_force["planilla_value_at_edit"] == "Aprobado"
    assert in_force["field_label"] == EDITABLE_BY_NAME["estado_resumido"].label
    for entry in ended:
        assert entry["source_row_number"] is None
        assert entry["ended_at"] is not None
        assert entry["ended_by_display_name"] == "transelec-operator"
        assert entry["created_by_display_name"] == "transelec-operator"
    assert ended[-1]["planilla_value_at_edit"] == "En evaluacion"
    assert (body["in_force_count"], body["needs_review_count"]) == (1, 0)


def test_history_shows_kept_and_incorporated_edits_and_survives_a_restore(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-admin", ADMIN)
    first = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    row_a = _row(client, "MP001", 0)["source_row_number"]
    row_b = _row(client, "MP001", 1)["source_row_number"]
    _put(client, first, row_a, "estado_resumido", "Aprobado", expected="En tramite")
    _put(client, first, row_b, "estado_resumido", "Aprobado", expected="En tramite")

    rows = [dict(item) for item in _BASE_ROWS]
    rows[0]["estado_resumido"] = "Aprobado"  # incorporates row A's edit
    rows[1]["estado_resumido"] = "Desistido"  # contradicts row B's edit
    _publish(client, _workbook(tmp_path, "v2.xlsx", rows), filename="v2.xlsx")

    conflict = _history(client)["entries"][0]
    assert (conflict["state"], conflict["source_row_number"]) == ("en_conflicto", row_b)
    assert _history(client)["needs_review_count"] == 1
    kept = client.post(
        f"/transelec/overrides/{conflict['id']}/keep", headers={"Origin": _SAME_ORIGIN}
    )
    assert kept.status_code == 200, kept.text

    body = _history(client)
    assert [e["state"] for e in body["entries"]] == ["aplicada", "kept", "incorporated"]
    assert body["entries"][1]["ended_by_display_name"] == "transelec-admin"
    assert body["entries"][2]["ended_by_display_name"] == "transelec-admin"

    restored = client.post(f"/transelec/imports/{first}/restore", headers={"Origin": _SAME_ORIGIN})
    assert restored.status_code == 200, restored.text
    after = _history(client)
    assert [e["id"] for e in after["entries"]] == [e["id"] for e in body["entries"]]
    assert after["entries"][0]["state"] == "en_conflicto"  # v1 still says «En tramite»


def test_history_rows_and_counts_ignore_the_limit(client: TestClient, tmp_path: Path) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "v1.xlsx"))
    mp002 = _row(client, "MP002")["source_row_number"]
    mp001 = _row(client, "MP001", 0)["source_row_number"]
    _put(client, import_id, mp002, "estado", "Reingresado", expected="Rechazado")
    _put(client, import_id, mp001, "estado", "Aprobado", expected="En evaluacion")
    _put(client, import_id, mp001, "tipo_rechazo", "Legal", expected=None)

    rows = [dict(item) for item in _BASE_ROWS if item["pmf"] != "MP002"]
    _publish(client, _workbook(tmp_path, "v2.xlsx", rows), filename="v2.xlsx")

    limited = _history(client, limit=1)
    assert len(limited["entries"]) == 1
    assert (limited["in_force_count"], limited["needs_review_count"]) == (2, 1)
    by_key = {(e["pmf"], e["field"]): e for e in _history(client)["entries"]}
    assert by_key[("MP002", "estado")]["state"] == "huerfana"
    assert by_key[("MP002", "estado")]["source_row_number"] is None
    assert (
        by_key[("MP001", "estado")]["source_row_number"]
        == _row(client, "MP001", 0)["source_row_number"]
    )


def test_an_active_incorporada_edit_is_listed_but_counted_in_neither(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    first = _publish(client, _new_layout_workbook(tmp_path, "v1.xlsx", "X"))
    row = _row(client, "MP001", 0)["source_row_number"]
    _put(client, first, row, "numero_ingreso_2", None, expected="X")
    _publish(client, _workbook(tmp_path, "v2.xlsx"))  # older layout: no «…2» column

    body = _history(client)
    assert [e["state"] for e in body["entries"]] == ["incorporada"]
    assert (body["in_force_count"], body["needs_review_count"]) == (0, 0)


def test_history_needs_a_version_validates_the_limit_and_is_open_to_viewers(
    client: TestClient, tmp_path: Path
) -> None:
    assert client.get("/transelec/overrides/history").status_code == 401
    _login_with_grants(client, "transelec-admin", ADMIN)
    assert client.get("/transelec/overrides/history").status_code == 404
    _publish(client, _workbook(tmp_path, "base.xlsx"))
    assert client.get("/transelec/overrides/history?limit=0").status_code == 422
    assert client.get("/transelec/overrides/history?limit=201").status_code == 422
    assert client.get("/api/transelec/overrides/history").status_code == 200
    client.cookies.clear()

    _login_with_grants(client, "transelec-viewer", VIEWER)
    assert _history(client) == {"in_force_count": 0, "needs_review_count": 0, "entries": []}
```

- [ ] **Step 2: Run them to see them fail**

Run: `<integration prefix> uv run pytest apps/api/integration_tests/test_transelec_overrides.py -k history -q`
Expected: FAIL — `404 Not Found` (no route; the DELETE route matches the path only).

- [ ] **Step 3: Implement the persistence read** (in `transelec_overrides.py`, after `list_overrides`)

```python
HistoryState = Literal[
    "aplicada",
    "incorporada",
    "en_conflicto",
    "huerfana",
    "superseded",
    "discarded",
    "kept",
    "incorporated",
]


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    """One edit, active or ended, as the edits log shows it."""

    id: int
    field: str
    state: HistoryState
    pmf: str
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    source_row_number: int | None
    web: Signature
    planilla_at_edit: Signature
    created_by_display_name: str
    created_at: dt.datetime
    ended_at: dt.datetime | None
    ended_by_display_name: str | None


@dataclass(frozen=True, slots=True)
class HistoryPage:
    in_force_count: int
    needs_review_count: int
    entries: list[HistoryRecord]


def list_override_history(connection: Connection, *, import_id: int, limit: int) -> HistoryPage:
    """The latest ``limit`` edits, active or ended, newest first, plus counts.

    Spec: docs/superpowers/specs/2026-10-05-transelec-web-edits-indicator-design.md §1.
    An active edit's state is its status against ``import_id``; an ended
    edit's is its ``end_reason``, and it carries no row: it acts on none, and
    its ``key_ordinal`` may point at another row in this version. The state
    view is filtered to one import inside the joined subquery, so PostgreSQL
    pushes the filter below the view's cross join over every import. The
    counts cover every active edit, whatever ``limit`` is.
    """

    rows = connection.execute(
        text(
            """
            SELECT o.id, o.field, o.pmf, o.rol, o.numero_predio, o.numero_area_corta,
                   o.value_text, o.value_date, o.planilla_value_text, o.planilla_value_date,
                   o.created_at, o.ended_at, o.end_reason,
                   author.display_name AS created_by_display_name,
                   ender.display_name AS ended_by_display_name,
                   s.status, s.source_row_number
            FROM platform.transelec_field_override AS o
            JOIN platform.app_user AS author ON author.id = o.created_by_app_user_id
            LEFT JOIN platform.app_user AS ender ON ender.id = o.ended_by_app_user_id
            LEFT JOIN (
                SELECT override_id, status, source_row_number
                FROM platform.transelec_override_state
                WHERE import_id = :import_id
            ) AS s ON s.override_id = o.id
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit
            """
        ),
        {"import_id": import_id, "limit": limit},
    ).all()
    counts = connection.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE status = 'aplicada') AS in_force,
                   count(*) FILTER (WHERE status IN ('en_conflicto', 'huerfana')) AS needs_review
            FROM platform.transelec_override_state
            WHERE import_id = :import_id
            """
        ),
        {"import_id": import_id},
    ).one()
    return HistoryPage(
        in_force_count=counts.in_force,
        needs_review_count=counts.needs_review,
        entries=[
            HistoryRecord(
                id=row.id,
                field=row.field,
                state=row.status if row.ended_at is None else row.end_reason,
                pmf=row.pmf,
                rol=row.rol,
                numero_predio=row.numero_predio,
                numero_area_corta=row.numero_area_corta,
                source_row_number=row.source_row_number if row.ended_at is None else None,
                web=(row.value_text, row.value_date),
                planilla_at_edit=(row.planilla_value_text, row.planilla_value_date),
                created_by_display_name=row.created_by_display_name,
                created_at=row.created_at,
                ended_at=row.ended_at,
                ended_by_display_name=row.ended_by_display_name,
            )
            for row in rows
        ],
    )
```

- [ ] **Step 4: Implement the route** (in `transelec_edits.py`; import `HistoryRecord`, `HistoryState`, `list_override_history`)

```python
class OverrideHistoryEntryView(BaseModel):
    id: int
    field: str
    field_label: str
    pmf: str
    rol: str | None
    numero_predio: str | None
    numero_area_corta: str | None
    source_row_number: int | None
    web_value: str | None
    planilla_value_at_edit: str | None
    created_by_display_name: str
    created_at: str
    state: HistoryState
    ended_at: str | None
    ended_by_display_name: str | None


class OverrideHistoryResponse(BaseModel):
    in_force_count: int
    needs_review_count: int
    entries: list[OverrideHistoryEntryView]


def _history_entry_view(record: HistoryRecord) -> OverrideHistoryEntryView:
    return OverrideHistoryEntryView(
        id=record.id,
        field=record.field,
        field_label=EDITABLE_BY_NAME[record.field].label,
        pmf=record.pmf,
        rol=record.rol,
        numero_predio=record.numero_predio,
        numero_area_corta=record.numero_area_corta,
        source_row_number=record.source_row_number,
        web_value=display(record.web),
        planilla_value_at_edit=display(record.planilla_at_edit),
        created_by_display_name=record.created_by_display_name,
        created_at=record.created_at.isoformat(),
        state=record.state,
        ended_at=None if record.ended_at is None else record.ended_at.isoformat(),
        ended_by_display_name=record.ended_by_display_name,
    )


@router.get(
    "/overrides/history",
    response_model=OverrideHistoryResponse,
    dependencies=[Depends(require_transelec_grant(Action.VIEW))],
)
def list_field_override_history(
    connection: Annotated[Connection, Depends(get_db_connection)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OverrideHistoryResponse:
    """The latest edits, active or ended, for the header's edits log.

    Spec: docs/superpowers/specs/2026-10-05-transelec-web-edits-indicator-design.md §1.
    A read: no audit row.
    """

    import_id = _require_active_import_id(connection)
    page = list_override_history(connection, import_id=import_id, limit=limit)
    return OverrideHistoryResponse(
        in_force_count=page.in_force_count,
        needs_review_count=page.needs_review_count,
        entries=[_history_entry_view(record) for record in page.entries],
    )
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `<integration prefix> uv run pytest apps/api/integration_tests/test_transelec_overrides.py -q`
Expected: PASS (all, old and new).

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff format apps/api && uv run ruff check apps/api && uv run mypy apps/api
git add apps/api/app/transelec_overrides.py apps/api/app/routers/transelec_edits.py apps/api/integration_tests/test_transelec_overrides.py
git commit -m "feat(transelec): list web edits with their history"
```

### Task 2: API — `web_edited_pmf_count`

**Files:**
- Modify: `apps/api/app/routers/transelec.py` (`TranselecSummaryResponse`, `get_summary`, import `first_row_wins`)
- Test: `apps/api/integration_tests/test_transelec_overrides.py`

**Interfaces:**
- Produces: `GET /transelec/summary` → `web_edited_pmf_count: int`.

- [ ] **Step 1: Write the failing test**

```python
# ---------------------------------------------------------------------------
# The summary says how many PMFs show an edited state (indicator spec §2)
# ---------------------------------------------------------------------------


def _web_edited(client: TestClient, query: str = "") -> int:
    response = client.get(f"/transelec/summary{query}")
    assert response.status_code == 200, response.text
    return response.json()["web_edited_pmf_count"]


def test_summary_counts_pmfs_whose_counted_row_has_an_edited_state(
    client: TestClient, tmp_path: Path
) -> None:
    _login_with_grants(client, "transelec-operator", OPERATOR)
    import_id = _publish(client, _workbook(tmp_path, "base.xlsx"))
    assert _web_edited(client) == 0

    mp001_second = _row(client, "MP001", 1)["source_row_number"]
    mp002 = _row(client, "MP002")["source_row_number"]
    mp003_first = _row(client, "MP003", 0)["source_row_number"]
    # Not counted: a PMF's second row, and a field the headline does not read.
    _put(client, import_id, mp001_second, "estado_resumido", "Aprobado", expected="En tramite")
    _put(client, import_id, mp002, "numero_ingreso", "ING-20", expected="ING-2")
    assert _web_edited(client) == 0

    # Counted: «Estado» on MP003's first row.
    _put(client, import_id, mp003_first, "estado", "Desistido", expected="Aprobado")
    assert _web_edited(client) == 1

    # The filters decide the first row, as for every other summary number.
    assert _web_edited(client, "?q=A2") == 1  # only MP001's second row is in scope
    assert _web_edited(client, "?empresa=Forestal%20Sur") == 0
    assert _web_edited(client, "?empresa=Forestal%20Norte") == 1
```

- [ ] **Step 2: Run it** — Expected: FAIL with `KeyError: 'web_edited_pmf_count'`.

- [ ] **Step 3: Implement** (in `routers/transelec.py`)

Add `first_row_wins` to the `status_rollups` import. Above `TranselecSummaryResponse`:

```python
# The headline counts each PMF under its first row's «Estado resumido» (and
# «Estado detallado» under its «Estado»), so only those two fields on that row
# move a headline number. Indicator spec §2.
_HEADLINE_STATE_FIELDS = frozenset({"estado_resumido", "estado"})


def _web_edited_pmf_count(rows: Sequence[Row[Any]]) -> int:
    """PMFs whose first row in ``rows`` shows an edited state; ``rows`` are
    the request's filtered rows, so this follows the filters like every other
    summary number."""

    by_number = {row.source_row_number: row for row in rows}
    winners = first_row_wins((_to_rolled_row(row) for row in rows), key="pmf")
    return sum(
        1
        for winner in winners.values()
        if _HEADLINE_STATE_FIELDS.intersection(by_number[winner.source_row_number].web_fields or ())
    )
```

Add `web_edited_pmf_count: int` as the last field of `TranselecSummaryResponse`, and `web_edited_pmf_count=_web_edited_pmf_count(rows),` as the last argument in `get_summary`.

- [ ] **Step 4: Run** `<integration prefix> uv run pytest apps/api/integration_tests/test_transelec_overrides.py apps/api/integration_tests/test_transelec_reads_router.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(transelec): the summary counts PMFs shown with an edited state"`

### Task 3: Dashboard — API client and the log's wording

**Files:**
- Modify: `products/transelect/dashboard/src/api.ts`, `src/test/factories.ts`
- Create: `src/lib/editLog.ts`, `src/lib/editLog.test.ts`

**Interfaces:**
- Produces (api.ts): `type EditHistoryState`, `interface TranselecHistoryEntry`, `interface TranselecEditHistory`, `EDIT_HISTORY_LIMIT = 50`, `getOverrideHistory(limit?: number): Promise<ApiResult<TranselecEditHistory>>`, `TranselecSummary.web_edited_pmf_count: number`.
- Produces (editLog.ts): `EDIT_LOG_ID = 'edit-log'`, `LOG_PREVIEW_COUNT = 8`, `editsWord(count): string`, `pillLabel(history): string`, `pillVisible(history | null): history is TranselecEditHistory`, `isMuted(state): boolean`, `stateLabel(entry): string | null`, `formatEditWhen(iso, now?): string`, `logValue(field, value): string`, `entryHref(entry): string | null`.
- Produces (factories.ts): `makeHistoryEntry(overrides)`, `makeHistory(overrides)`.

- [ ] **Step 1: API types and client** (append to the web-edits block of `api.ts`; add `web_edited_pmf_count: number` to `TranselecSummary` with a doc comment)

```ts
/** Where an edit stands: its status against the active version while in force, or how it ended. */
export type EditHistoryState =
  | OverrideStatus
  | 'superseded'
  | 'discarded'
  | 'kept'
  | 'incorporated'

export interface TranselecHistoryEntry {
  id: number
  field: EditableFieldName
  field_label: string
  pmf: string
  rol: string | null
  numero_predio: string | null
  numero_area_corta: string | null
  /** The active version's row while the edit is in force; null when it has none or ended. */
  source_row_number: number | null
  web_value: string | null
  planilla_value_at_edit: string | null
  created_by_display_name: string
  created_at: string
  state: EditHistoryState
  ended_at: string | null
  ended_by_display_name: string | null
}

export interface TranselecEditHistory {
  /** Active edits the dashboard shows. */
  in_force_count: number
  /** Active edits in conflict with the planilla or without a row. */
  needs_review_count: number
  /** The latest edits, active or ended, newest first. */
  entries: TranselecHistoryEntry[]
}

export const EDIT_HISTORY_LIMIT = 50

export function getOverrideHistory(
  limit: number = EDIT_HISTORY_LIMIT,
): Promise<ApiResult<TranselecEditHistory>> {
  return request<TranselecEditHistory>(`/api/transelec/overrides/history?limit=${limit}`)
}
```

`factories.ts`: add `web_edited_pmf_count: 0` to `makeSummary`, and

```ts
export function makeHistoryEntry(
  overrides: Partial<TranselecHistoryEntry> = {},
): TranselecHistoryEntry {
  return {
    id: 41,
    field: 'estado_resumido',
    field_label: 'Estado resumido',
    pmf: 'MP001',
    rol: '101',
    numero_predio: '1',
    numero_area_corta: 'A1',
    source_row_number: 7,
    web_value: 'Aprobado',
    planilla_value_at_edit: 'En tramite',
    created_by_display_name: 'Dev Admin',
    created_at: '2026-10-05T12:41:00+00:00',
    state: 'aplicada',
    ended_at: null,
    ended_by_display_name: null,
    ...overrides,
  }
}

export function makeHistory(overrides: Partial<TranselecEditHistory> = {}): TranselecEditHistory {
  return { in_force_count: 1, needs_review_count: 0, entries: [makeHistoryEntry()], ...overrides }
}
```

- [ ] **Step 2: Write the failing tests** (`src/lib/editLog.test.ts`)

```ts
import { describe, expect, it } from 'vitest'
import { makeHistory, makeHistoryEntry } from '../test/factories'
import {
  entryHref,
  formatEditWhen,
  isMuted,
  logValue,
  pillLabel,
  pillVisible,
  stateLabel,
} from './editLog'

// 12:00 in Santiago (UTC-3 in October 2026).
const NOW = new Date('2026-10-05T15:00:00Z')

describe('the pill', () => {
  it('counts edits in force, singular and plural, and adds what needs review', () => {
    expect(pillLabel({ in_force_count: 1, needs_review_count: 0 })).toBe('1 edición web')
    expect(pillLabel({ in_force_count: 5, needs_review_count: 0 })).toBe('5 ediciones web')
    expect(pillLabel({ in_force_count: 5, needs_review_count: 2 })).toBe(
      '5 ediciones web · 2 por revisar',
    )
  })

  it('exists only after a load with something in force or to review', () => {
    expect(pillVisible(null)).toBe(false)
    expect(pillVisible(makeHistory({ in_force_count: 0, needs_review_count: 0 }))).toBe(false)
    expect(pillVisible(makeHistory({ in_force_count: 0, needs_review_count: 1 }))).toBe(true)
    expect(pillVisible(makeHistory({ in_force_count: 3 }))).toBe(true)
  })
})

describe('state labels', () => {
  it.each([
    ['aplicada', null, null, false],
    ['en_conflicto', null, 'en conflicto: la planilla cambió', false],
    ['huerfana', null, 'sin fila en la versión activa', false],
    ['incorporada', null, 'ya está en la planilla', true],
    ['incorporated', 'Ana', 'ya está en la planilla', true],
    ['superseded', 'Ana', 'reemplazada por una edición posterior', true],
    ['discarded', 'Ana', 'revertida al valor de la planilla · Ana', true],
    ['kept', 'Luis', 'conservada al resolver un conflicto · Luis', true],
  ] as const)('%s', (state, who, label, muted) => {
    expect(stateLabel(makeHistoryEntry({ state, ended_by_display_name: who }))).toBe(label)
    expect(isMuted(state)).toBe(muted)
  })
})

describe('dates in Chile time', () => {
  it('reads «hoy», «ayer» or the date', () => {
    expect(formatEditWhen('2026-10-05T12:41:00Z', NOW)).toBe('hoy 09:41')
    expect(formatEditWhen('2026-10-04T20:02:00Z', NOW)).toBe('ayer 17:02')
    expect(formatEditWhen('2026-10-03T15:00:00Z', NOW)).toBe('03-10-2026')
  })

  it('uses the Santiago day, not the UTC day', () => {
    // 02:30 UTC on the 5th is 23:30 on the 4th in Santiago.
    expect(formatEditWhen('2026-10-05T02:30:00Z', NOW)).toBe('ayer 23:30')
  })
})

describe('values and links', () => {
  it('writes an empty value as «(vacío)» and dates as dd-mm-aaaa', () => {
    expect(logValue('estado', null)).toBe('(vacío)')
    expect(logValue('estado', '  ')).toBe('(vacío)')
    expect(logValue('fecha_ingreso', '2026-03-12')).toBe('12-03-2026')
    expect(logValue('estado', 'Aprobado')).toBe('Aprobado')
  })

  it('links an entry with a row to the Explorador, filtered to its PMF with the row open', () => {
    expect(entryHref(makeHistoryEntry({ pmf: 'MP 001', source_row_number: 7 }))).toBe(
      '/transelec/explorador?q=MP+001&fila=7',
    )
    expect(entryHref(makeHistoryEntry({ source_row_number: null }))).toBeNull()
  })
})
```

- [ ] **Step 3: Run** `cd products/transelect/dashboard && npx vitest run src/lib/editLog.test.ts` — Expected: FAIL (module not found).

- [ ] **Step 4: Implement** `src/lib/editLog.ts`

```ts
/**
 * The edits log's wording (indicator spec §4-§6): the pill's text, each
 * entry's state label, its date in Chile time and where it links. Pure, so
 * the header popover and the «Historial» in Ediciones web read the same.
 */
import {
  EMPTY_FILTERS,
  type EditHistoryState,
  type EditableFieldName,
  type TranselecEditHistory,
  type TranselecHistoryEntry,
} from '../api'
import { ROUTES } from '../router'
import { searchFromFilters } from './filterUrl'
import { displayValue, formatEditDate, specFor } from './webEdits'

/** The popover's id: the pill's `popovertarget` and `openEditLog` find it by this. */
export const EDIT_LOG_ID = 'edit-log'

/** How many entries the popover shows; Ediciones web shows every loaded one. */
export const LOG_PREVIEW_COUNT = 8

export function editsWord(count: number): string {
  return count === 1 ? 'edición web' : 'ediciones web'
}

/** The pill's full text, which is also its accessible name at every width. */
export function pillLabel(
  history: Pick<TranselecEditHistory, 'in_force_count' | 'needs_review_count'>,
): string {
  const base = `${history.in_force_count} ${editsWord(history.in_force_count)}`
  return history.needs_review_count > 0
    ? `${base} · ${history.needs_review_count} por revisar`
    : base
}

/** The pill exists only after a successful load with something in force or to review. */
export function pillVisible(history: TranselecEditHistory | null): history is TranselecEditHistory {
  return history !== null && history.in_force_count + history.needs_review_count > 0
}

const MUTED: ReadonlySet<EditHistoryState> = new Set([
  'incorporada',
  'incorporated',
  'superseded',
  'discarded',
  'kept',
])

/** Greyed entries: the edit no longer changes what the dashboard shows. */
export function isMuted(state: EditHistoryState): boolean {
  return MUTED.has(state)
}

function byWhom(label: string, who: string | null): string {
  return who ? `${label} · ${who}` : label
}

/** What happened to an edit; null for one in force, which needs no label. */
export function stateLabel(
  entry: Pick<TranselecHistoryEntry, 'state' | 'ended_by_display_name'>,
): string | null {
  switch (entry.state) {
    case 'aplicada':
      return null
    case 'en_conflicto':
      return 'en conflicto: la planilla cambió'
    case 'huerfana':
      return 'sin fila en la versión activa'
    case 'incorporada':
    case 'incorporated':
      return 'ya está en la planilla'
    case 'superseded':
      return 'reemplazada por una edición posterior'
    case 'discarded':
      return byWhom('revertida al valor de la planilla', entry.ended_by_display_name)
    case 'kept':
      return byWhom('conservada al resolver un conflicto', entry.ended_by_display_name)
  }
}

const SANTIAGO = new Intl.DateTimeFormat('es-CL', {
  timeZone: 'America/Santiago',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function santiago(date: Date): { day: string; time: string } {
  const parts = SANTIAGO.formatToParts(date)
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? ''
  return {
    day: `${part('year')}-${part('month')}-${part('day')}`,
    time: `${part('hour')}:${part('minute')}`,
  }
}

/** «hoy 09:41», «ayer 17:02» or «03-10-2026», in America/Santiago. */
export function formatEditWhen(iso: string, now: Date = new Date()): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return formatEditDate(iso)
  const when = santiago(at)
  const today = santiago(now).day
  if (when.day === today) return `hoy ${when.time}`
  // The calendar day before today's Santiago date (noon UTC avoids any edge).
  const [year, month, day] = today.split('-').map(Number)
  const yesterday = new Date(Date.UTC(year, month - 1, day - 1, 12)).toISOString().slice(0, 10)
  if (when.day === yesterday) return `ayer ${when.time}`
  return formatEditDate(iso)
}

/** A value as the log shows it: dates dd-mm-aaaa, an empty one «(vacío)». */
export function logValue(field: EditableFieldName, value: string | null): string {
  return displayValue(specFor(field), value) || '(vacío)'
}

/** The Explorador filtered to the entry's PMF with its row's drawer open; null without a row. */
export function entryHref(
  entry: Pick<TranselecHistoryEntry, 'pmf' | 'source_row_number'>,
): string | null {
  if (entry.source_row_number === null) return null
  return `${ROUTES.explorador}${searchFromFilters(
    { ...EMPTY_FILTERS, q: entry.pmf },
    { fila: String(entry.source_row_number) },
  )}`
}
```

- [ ] **Step 5: Run** the test, `npx tsc -b` — Expected: PASS (fix any `makeSummary` users the new field breaks).
- [ ] **Step 6: Commit** — `git commit -m "feat(transelec): history client and the edits log's wording"`

### Task 4: Dashboard — shared web-edits state

**Files:**
- Create: `src/lib/webEditsState.ts`, `src/components/WebEditsProvider.tsx`, `src/components/WebEditsProvider.test.tsx`
- Modify: `src/App.tsx`, `src/components/EditableFieldsSection.tsx`, `src/pages/EdicionesPage.tsx`

**Interfaces:**
- Consumes: `getOverrideHistory`, `EDIT_LOG_ID`.
- Produces: `WebEditsContext`, `useWebEdits(): {history, status, refresh, openLog}`, `openEditLog()`, `REFOCUS_REFRESH_MS = 60_000`, `<WebEditsProvider activeImport={…}>`.

- [ ] **Step 1: Write the failing tests** (`WebEditsProvider.test.tsx`)

```tsx
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiResult, TranselecEditHistory } from '../api'
import { useWebEdits } from '../lib/webEditsState'
import { makeActiveImport, makeHistory } from '../test/factories'
import { WebEditsProvider } from './WebEditsProvider'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, getOverrideHistory: vi.fn() }
})
const { getOverrideHistory } = await import('../api')

function Probe() {
  const { history, status, refresh } = useWebEdits()
  return (
    <>
      <span data-testid="status">{status}</span>
      <span data-testid="count">{history ? history.in_force_count : 'none'}</span>
      <button type="button" onClick={refresh}>
        refresh
      </button>
    </>
  )
}

function deferred() {
  let resolve!: (value: ApiResult<TranselecEditHistory>) => void
  const promise = new Promise<ApiResult<TranselecEditHistory>>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

const ok = (in_force_count: number): ApiResult<TranselecEditHistory> => ({
  ok: true,
  data: makeHistory({ in_force_count }),
})

describe('WebEditsProvider', () => {
  beforeEach(() => vi.mocked(getOverrideHistory).mockReset())
  afterEach(() => vi.restoreAllMocks())

  it('loads once a version is active and clears when none is', async () => {
    vi.mocked(getOverrideHistory).mockResolvedValue(ok(3))
    const { rerender } = render(
      <WebEditsProvider activeImport={null}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(getOverrideHistory).not.toHaveBeenCalled()
    expect(screen.getByTestId('status')).toHaveTextContent('idle')

    rerender(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByTestId('status')).toHaveTextContent('ready')

    rerender(
      <WebEditsProvider activeImport={null}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(screen.getByTestId('count')).toHaveTextContent('none')
  })

  it('reloads when the active version is read again (publish or restore)', async () => {
    vi.mocked(getOverrideHistory).mockResolvedValue(ok(1))
    const { rerender } = render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('1')
    rerender(
      <WebEditsProvider activeImport={makeActiveImport({ import_id: 13 })}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(getOverrideHistory).toHaveBeenCalledTimes(2)
  })

  it('keeps the previous history while a refresh runs and drops an out-of-order answer', async () => {
    const first = deferred()
    const second = deferred()
    vi.mocked(getOverrideHistory)
      .mockResolvedValueOnce(ok(1))
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('1')

    await userEvent.click(screen.getByRole('button', { name: 'refresh' }))
    await userEvent.click(screen.getByRole('button', { name: 'refresh' }))
    expect(screen.getByTestId('count')).toHaveTextContent('1') // no flicker
    expect(screen.getByTestId('status')).toHaveTextContent('ready')

    await act(async () => second.resolve(ok(5)))
    await act(async () => first.resolve(ok(2))) // older request: ignored
    expect(screen.getByTestId('count')).toHaveTextContent('5')
  })

  it('clears on a failed load', async () => {
    vi.mocked(getOverrideHistory)
      .mockResolvedValueOnce(ok(4))
      .mockResolvedValueOnce({ ok: false, status: 401, error: 'Not authenticated.' })
    render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('4')
    await userEvent.click(screen.getByRole('button', { name: 'refresh' }))
    expect(await screen.findByText('none')).toBeInTheDocument()
    expect(screen.getByTestId('status')).toHaveTextContent('error')
  })

  it('refreshes when the tab is visible again, at most once a minute', async () => {
    vi.mocked(getOverrideHistory).mockResolvedValue(ok(1))
    const now = vi.spyOn(Date, 'now').mockReturnValue(1_000_000)
    render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('1')
    const visible = () => act(() => document.dispatchEvent(new Event('visibilitychange')))

    now.mockReturnValue(1_000_000 + 59_000)
    visible()
    expect(getOverrideHistory).toHaveBeenCalledTimes(1)

    now.mockReturnValue(1_000_000 + 61_000)
    visible()
    expect(getOverrideHistory).toHaveBeenCalledTimes(2)
  })
})
```

- [ ] **Step 2: Run** — Expected: FAIL (modules missing).

- [ ] **Step 3: Implement** `src/lib/webEditsState.ts`

```ts
/**
 * The shell's shared web-edits state (indicator spec §3): the edit history
 * the header pill, its log, the Resumen hint and Ediciones web all read.
 *
 * The context lives apart from its provider so component modules export only
 * components (oxlint `react/only-export-components`). Outside a provider, as
 * in most component tests, it is inert: no history, and `refresh` and
 * `openLog` do nothing.
 */
import { createContext, useContext } from 'react'
import type { TranselecEditHistory } from '../api'
import { EDIT_LOG_ID } from './editLog'

export type WebEditsStatus = 'idle' | 'loading' | 'ready' | 'error'

/** A tab that becomes visible again re-reads the history at most this often. */
export const REFOCUS_REFRESH_MS = 60_000

export interface WebEditsValue {
  /** The last successful load. Kept while a refresh runs; cleared by a failed one. */
  history: TranselecEditHistory | null
  status: WebEditsStatus
  /** Re-read the history. Call after every save, revert, discard or keep. */
  refresh: () => void
  /** Open the header's edits log, if it is on the page. */
  openLog: () => void
}

export const WebEditsContext = createContext<WebEditsValue>({
  history: null,
  status: 'idle',
  refresh: () => {},
  openLog: () => {},
})

export function useWebEdits(): WebEditsValue {
  return useContext(WebEditsContext)
}

/** Show the log popover; nothing where it is absent, already open, or the Popover API is missing. */
export function openEditLog(): void {
  const log = document.getElementById(EDIT_LOG_ID)
  if (!log || typeof log.showPopover !== 'function' || log.matches(':popover-open')) return
  log.showPopover()
}
```

`src/components/WebEditsProvider.tsx`

```tsx
/**
 * Owns the shared web-edits history (indicator spec §3).
 *
 * Loads once a version is active, and again whenever the shell re-reads the
 * active version (after a publish or restore in this session). Without one —
 * signed out, or nothing published — it holds nothing. A failed load,
 * including a 401, clears it, so the pill never shows another session's or a
 * stale version's numbers. When the tab becomes visible again it refreshes,
 * at most once a minute, so another tab's or person's edits show up. A
 * refresh keeps the previous history on screen until the answer arrives, and
 * an answer older than the latest request is dropped.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { type TranselecActiveImport, type TranselecEditHistory, getOverrideHistory } from '../api'
import {
  REFOCUS_REFRESH_MS,
  WebEditsContext,
  type WebEditsStatus,
  openEditLog,
} from '../lib/webEditsState'

export function WebEditsProvider({
  activeImport,
  children,
}: {
  /** The shell's active-version read; a new object after every publish or restore. */
  activeImport: TranselecActiveImport | null
  children: ReactNode
}) {
  const [history, setHistory] = useState<TranselecEditHistory | null>(null)
  const [status, setStatus] = useState<WebEditsStatus>('idle')
  const latestRequest = useRef(0)
  const lastStarted = useRef(0)
  const enabled = activeImport !== null

  const load = useCallback(() => {
    const id = ++latestRequest.current
    lastStarted.current = Date.now()
    setStatus((current) => (current === 'ready' ? current : 'loading'))
    void getOverrideHistory().then((result) => {
      if (id !== latestRequest.current) return
      setHistory(result.ok ? result.data : null)
      setStatus(result.ok ? 'ready' : 'error')
    })
  }, [])

  useEffect(() => {
    if (activeImport === null) {
      latestRequest.current += 1 // an answer still in flight belongs to the old session
      setHistory(null)
      setStatus('idle')
      return
    }
    load()
  }, [activeImport, load])

  useEffect(() => {
    if (!enabled) return undefined
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastStarted.current < REFOCUS_REFRESH_MS) return
      load()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [enabled, load])

  const refresh = useCallback(() => {
    if (enabled) load()
  }, [enabled, load])

  const value = useMemo(
    () => ({ history, status, refresh, openLog: openEditLog }),
    [history, status, refresh],
  )
  return <WebEditsContext.Provider value={value}>{children}</WebEditsContext.Provider>
}
```

- [ ] **Step 4: Wire it in.**
  - `App.tsx`: wrap the returned fragment's content (skip link, `AppHeader`, `<main>`) in `<WebEditsProvider activeImport={activeImport}>…</WebEditsProvider>`.
  - `EditableFieldsSection.tsx`: `const { refresh: refreshEdits } = useWebEdits()`; call `refreshEdits()` after a successful save whose `result.data.changed` is true, after a successful revert, and in `reloadAfterConflict` (another change landed).
  - `EdicionesPage.tsx`: `const { refresh: refreshEdits } = useWebEdits()`; in `act`, call `refreshEdits()` next to each `reload()`.

- [ ] **Step 5: Add refresh assertions to the existing suites.** In `EditableFieldsSection.test.tsx` and `EdicionesPage.test.tsx`, render inside `<WebEditsContext.Provider value={{ history: null, status: 'ready', refresh, openLog: vi.fn() }}>` with `const refresh = vi.fn()` and assert `expect(refresh).toHaveBeenCalledTimes(1)` after a save, a revert, a keep and a discard; and `not.toHaveBeenCalled()` after a no-change save.

- [ ] **Step 6: Run** `npx vitest run && npx tsc -b` — Expected: PASS.
- [ ] **Step 7: Commit** — `git commit -m "feat(transelec): shared web-edits state in the shell"`

### Task 5: Dashboard — the header pill and its log

**Files:**
- Create: `src/lib/xlsxDownload.ts`, `src/components/EditLog.tsx`, `src/components/WebEditsPill.tsx`, `src/components/WebEditsPill.test.tsx`
- Modify: `src/components/AppHeader.tsx`, `src/pages/EdicionesPage.tsx` (download via the hook), `src/styles/components.css`, `src/components/Chrome.test.tsx`

**Interfaces:**
- Consumes: `useWebEdits`, `pillLabel`, `pillVisible`, `stateLabel`, `isMuted`, `formatEditWhen`, `logValue`, `entryHref`, `EDIT_LOG_ID`, `LOG_PREVIEW_COUNT`.
- Produces: `useXlsxDownload(): {downloading: boolean, error: string | null, download: () => Promise<void>}`, `DOWNLOAD_BUSY`, `DOWNLOAD_LABEL`; `<EditLogList entries onNavigate?>`, `<EditLogBody history canEdit headingRef onNavigate>`; `<WebEditsPill canEdit>`.

- [ ] **Step 1: Extract the download** — `src/lib/xlsxDownload.ts` takes `downloadErrorCopy`, `DOWNLOAD_BUSY`, `DOWNLOAD_SERVER_ERROR` and the body of `EdicionesPage.download` unchanged:

```ts
/**
 * «Descargar planilla con ediciones (.xlsx)», shared by Ediciones web and the
 * header log's footer. The file is fetched first, so a failure can be shown
 * instead of a dead download.
 */
import { useCallback, useState } from 'react'
import { downloadOverridesXlsx } from '../api'
import { classifyFailure } from './apiState'

export const DOWNLOAD_LABEL = 'Descargar planilla con ediciones (.xlsx)'
export const DOWNLOAD_BUSY = 'Preparando la planilla…'
const DOWNLOAD_SERVER_ERROR =
  'La plataforma no pudo preparar la planilla. Intente de nuevo; si se repite, contacte a soporte.'

/** 403 and a bare 5xx get fixed Spanish copy; 404/409/422 keep the server's own detail. */
function downloadErrorCopy(result: { status: number; error: string; payload?: unknown }): string {
  if (result.status === 403) return classifyFailure(result).message
  if (result.status >= 500 && result.payload === undefined) return DOWNLOAD_SERVER_ERROR
  return result.error
}

export function useXlsxDownload() {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const download = useCallback(async () => {
    // Callers use aria-disabled, not disabled, so the button keeps focus while busy.
    if (downloading) return
    setDownloading(true)
    setError(null)
    const result = await downloadOverridesXlsx()
    setDownloading(false)
    if (!result.ok) {
      setError(downloadErrorCopy(result))
      return
    }
    const url = URL.createObjectURL(result.data.blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = result.data.filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    // Safari can abort the save if the URL is revoked in the same tick.
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }, [downloading])

  return { downloading, error, download }
}
```

`EdicionesPage` then uses `const { downloading, error: downloadError, download } = useXlsxDownload()`; its live region reads `{downloading ? DOWNLOAD_BUSY : status}` and its button label `{downloading ? DOWNLOAD_BUSY : DOWNLOAD_LABEL}`. Its existing download tests must pass unchanged.

- [ ] **Step 2: Write the failing tests** — `src/components/WebEditsPill.test.tsx`

```tsx
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { TranselecEditHistory } from '../api'
import { WebEditsContext } from '../lib/webEditsState'
import { ROUTES, RouterProvider } from '../router'
import { makeHistory, makeHistoryEntry } from '../test/factories'
import { WebEditsPill } from './WebEditsPill'

function renderPill(history: TranselecEditHistory | null, canEdit = true) {
  return render(
    <RouterProvider initialPath={ROUTES.resumen}>
      <WebEditsContext.Provider
        value={{ history, status: history ? 'ready' : 'error', refresh: vi.fn(), openLog: vi.fn() }}
      >
        <WebEditsPill canEdit={canEdit} />
      </WebEditsContext.Provider>
    </RouterProvider>,
  )
}

describe('the «ediciones web» pill', () => {
  it('names the full count at every width and points at the log', () => {
    renderPill(makeHistory({ in_force_count: 5, needs_review_count: 2 }))
    const pill = screen.getByRole('button', { name: '5 ediciones web · 2 por revisar' })
    expect(pill).toHaveAttribute('popovertarget', 'edit-log')
    expect(pill).toHaveAttribute('aria-haspopup', 'dialog')
    expect(pill).toHaveAttribute('aria-controls', 'edit-log')
    expect(pill).toHaveAttribute('aria-expanded', 'false')
    expect(pill.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(pill).not.toHaveTextContent('✎')
  })

  it('is singular for one edit and has no review part when nothing needs review', () => {
    renderPill(makeHistory({ in_force_count: 1 }))
    expect(screen.getByRole('button', { name: '1 edición web' })).toBeInTheDocument()
    expect(screen.queryByText(/por revisar/)).not.toBeInTheDocument()
  })

  it.each([
    ['before a successful load or after an error', null],
    ['with nothing in force or to review', makeHistory({ in_force_count: 0, needs_review_count: 0 })],
  ])('is absent %s', (_, history) => {
    renderPill(history)
    expect(screen.queryByTestId('edits-pill')).not.toBeInTheDocument()
    expect(screen.queryByTestId('edit-log')).not.toBeInTheDocument()
  })
})

describe('the edits log', () => {
  const entries = [
    makeHistoryEntry({ id: 9, state: 'aplicada', source_row_number: 7, pmf: 'MP009' }),
    makeHistoryEntry({ id: 8, state: 'en_conflicto', source_row_number: 3 }),
    makeHistoryEntry({ id: 7, state: 'huerfana', source_row_number: null }),
    makeHistoryEntry({ id: 6, state: 'incorporada' }),
    makeHistoryEntry({ id: 5, state: 'superseded', source_row_number: null, ended_by_display_name: 'Ana' }),
    makeHistoryEntry({ id: 4, state: 'discarded', source_row_number: null, ended_by_display_name: 'Ana' }),
    makeHistoryEntry({ id: 3, state: 'kept', source_row_number: null, ended_by_display_name: 'Luis' }),
    makeHistoryEntry({ id: 2, state: 'incorporated', source_row_number: null, planilla_value_at_edit: null }),
    makeHistoryEntry({ id: 1 }),
    makeHistoryEntry({ id: 0 }),
  ]

  it('is a named dialog popover with the counts beside its heading', () => {
    renderPill(makeHistory({ in_force_count: 5, needs_review_count: 2, entries }))
    const log = screen.getByTestId('edit-log')
    expect(log).toHaveAttribute('popover', 'auto')
    expect(log).toHaveAttribute('role', 'dialog')
    expect(log).toHaveAttribute('aria-labelledby', 'edit-log-heading')
    expect(within(log).getByRole('heading', { name: 'Ediciones web' })).toHaveAttribute('tabindex', '-1')
    expect(log).toHaveTextContent('5 en vigor')
    expect(log).toHaveTextContent('2 por revisar')
  })

  it('shows the latest 8 with their labels, greys what no longer applies, and says how many more', () => {
    renderPill(makeHistory({ entries }))
    const log = screen.getByTestId('edit-log')
    expect(within(log).getAllByRole('listitem')).toHaveLength(8)
    expect(log).toHaveTextContent('y 2 más')
    expect(screen.getByTestId('edit-log-9')).not.toHaveAttribute('data-muted')
    expect(screen.getByTestId('edit-log-8')).toHaveTextContent('en conflicto: la planilla cambió')
    expect(screen.getByTestId('edit-log-8')).not.toHaveAttribute('data-muted')
    expect(screen.getByTestId('edit-log-7')).toHaveTextContent('sin fila en la versión activa')
    expect(screen.getByTestId('edit-log-6')).toHaveTextContent('ya está en la planilla')
    expect(screen.getByTestId('edit-log-5')).toHaveTextContent('reemplazada por una edición posterior')
    expect(screen.getByTestId('edit-log-4')).toHaveTextContent('revertida al valor de la planilla · Ana')
    expect(screen.getByTestId('edit-log-3')).toHaveTextContent('conservada al resolver un conflicto · Luis')
    expect(screen.getByTestId('edit-log-2')).toHaveTextContent('(vacío)')
    expect(screen.getByTestId('edit-log-4')).toHaveAttribute('data-muted', 'true')
  })

  it('links only entries with a row, to the Explorador with that row open', () => {
    renderPill(makeHistory({ entries }))
    expect(within(screen.getByTestId('edit-log-9')).getByRole('link')).toHaveAttribute(
      'href',
      '/transelec/explorador?q=MP009&fila=7',
    )
    expect(within(screen.getByTestId('edit-log-4')).queryByRole('link')).not.toBeInTheDocument()
    expect(within(screen.getByTestId('edit-log-7')).queryByRole('link')).not.toBeInTheDocument()
  })

  it('keeps each full value for screen readers and on hover', () => {
    const long = 'Un valor largo '.repeat(20).trim()
    renderPill(makeHistory({ entries: [makeHistoryEntry({ web_value: long })] }))
    const value = screen.getByTitle(long)
    expect(value).toHaveTextContent(long)
  })

  it('offers Ediciones web and the download to operators and administrators only', () => {
    const { unmount } = renderPill(makeHistory(), true)
    expect(screen.getByRole('link', { name: 'Ver todas en Ediciones web →' })).toHaveAttribute(
      'href',
      '/transelec/ediciones',
    )
    expect(screen.getByRole('button', { name: 'Descargar planilla con ediciones (.xlsx)' })).toBeInTheDocument()
    unmount()

    renderPill(makeHistory(), false)
    expect(screen.queryByRole('link', { name: /Ediciones web/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Descargar/ })).not.toBeInTheDocument()
  })
})
```

`Chrome.test.tsx` gains one test: `AppHeader` inside a `WebEditsContext.Provider` with `makeHistory({ in_force_count: 3 })` shows `getByRole('button', { name: '3 ediciones web' })` right after the version chip (`.version-chip` + `.edits-pill` sibling order), and no pill when `activeImport` is null.

- [ ] **Step 3: Run** — Expected: FAIL (modules missing).

- [ ] **Step 4: Implement** `src/components/EditLog.tsx`

```tsx
/**
 * The edits log's entries (indicator spec §5-§6), shared by the header
 * popover and the «Historial» in Ediciones web, and the popover's body.
 *
 * An entry still acting on a row (in force or in conflict) links to the
 * Explorador with that row's drawer open; the rest are plain text, greyed
 * when the edit no longer changes what the dashboard shows. Each value is
 * clamped to two lines on screen; the full text stays in the DOM for screen
 * readers and in `title` on hover.
 */
import type { Ref } from 'react'
import type { TranselecEditHistory, TranselecHistoryEntry } from '../api'
import {
  LOG_PREVIEW_COUNT,
  entryHref,
  formatEditWhen,
  isMuted,
  logValue,
  stateLabel,
} from '../lib/editLog'
import { specFor } from '../lib/webEdits'
import { DOWNLOAD_BUSY, DOWNLOAD_LABEL, useXlsxDownload } from '../lib/xlsxDownload'
import { Link, ROUTES } from '../router'

function EditLogItem({
  entry,
  onNavigate,
}: {
  entry: TranselecHistoryEntry
  onNavigate?: () => void
}) {
  const label = stateLabel(entry)
  const before = logValue(entry.field, entry.planilla_value_at_edit)
  const after = logValue(entry.field, entry.web_value)
  const href = entryHref(entry)
  const body = (
    <>
      <span className="edit-log-what">
        <b>{entry.pmf}</b> · {specFor(entry.field).label}
      </span>
      <span className="edit-log-change">
        <span className="sr-only">de </span>
        <span className="edit-log-value" title={before}>
          {before}
        </span>
        <span aria-hidden="true"> → </span>
        <span className="sr-only"> a </span>
        <span className="edit-log-value" title={after}>
          {after}
        </span>
      </span>
      <span className="edit-log-who">
        {entry.created_by_display_name} ·{' '}
        <time dateTime={entry.created_at}>{formatEditWhen(entry.created_at)}</time>
      </span>
      {label && (
        <span className="edit-log-state" data-state={entry.state}>
          {label}
        </span>
      )}
    </>
  )
  return (
    <li
      className="edit-log-entry"
      data-state={entry.state}
      data-muted={isMuted(entry.state) ? 'true' : undefined}
      data-testid={`edit-log-${entry.id}`}
    >
      {href ? (
        <Link to={href} className="edit-log-target" onNavigate={onNavigate}>
          {body}
        </Link>
      ) : (
        <div className="edit-log-target">{body}</div>
      )}
    </li>
  )
}

export function EditLogList({
  entries,
  onNavigate,
}: {
  entries: readonly TranselecHistoryEntry[]
  onNavigate?: () => void
}) {
  return (
    <ol className="edit-log-list">
      {entries.map((entry) => (
        <EditLogItem key={entry.id} entry={entry} onNavigate={onNavigate} />
      ))}
    </ol>
  )
}

function DownloadLink() {
  const { downloading, error, download } = useXlsxDownload()
  return (
    <>
      <button
        type="button"
        className="btn-link"
        aria-disabled={downloading}
        onClick={() => void download()}
      >
        {downloading ? DOWNLOAD_BUSY : DOWNLOAD_LABEL}
      </button>
      {error && (
        <p className="hint" role="alert">
          No se pudo descargar la planilla. {error}
        </p>
      )}
    </>
  )
}

export function EditLogBody({
  history,
  canEdit,
  headingRef,
  onNavigate,
}: {
  history: TranselecEditHistory
  canEdit: boolean
  headingRef: Ref<HTMLHeadingElement>
  onNavigate: () => void
}) {
  const shown = history.entries.slice(0, LOG_PREVIEW_COUNT)
  const more = history.entries.length - shown.length
  return (
    <>
      <div className="edit-log-head">
        <h2 id="edit-log-heading" ref={headingRef} tabIndex={-1}>
          Ediciones web
        </h2>
        <span className="edit-log-counts">
          {history.in_force_count} en vigor
          {history.needs_review_count > 0 && (
            <>
              {' · '}
              <span className="edit-log-review">{history.needs_review_count} por revisar</span>
            </>
          )}
        </span>
      </div>
      {shown.length === 0 ? (
        <p className="hint">Todavía no hay ediciones web.</p>
      ) : (
        <EditLogList entries={shown} onNavigate={onNavigate} />
      )}
      {more > 0 && <p className="hint edit-log-more">y {more} más</p>}
      {canEdit && (
        <div className="edit-log-foot">
          <Link to={ROUTES.ediciones} onNavigate={onNavigate}>
            Ver todas en Ediciones web →
          </Link>
          <DownloadLink />
        </div>
      )}
    </>
  )
}
```

`src/components/WebEditsPill.tsx`

```tsx
/**
 * The header's «N ediciones web» pill and its log (indicator spec §4-§5).
 *
 * The log is a native popover: the platform gives it Esc, light dismiss and
 * the top layer, so nothing here handles an outside click or a z-index. The
 * `toggle` event keeps `aria-expanded` true to the popover, moves focus to
 * the heading on open and back to the pill on close. CSS anchor positioning
 * puts it under the pill (components.css), with a fixed place under the bar
 * where that is unsupported. The pill is not a live region: its numbers
 * change only after the reader's own edits or a tab refocus.
 */
import { useEffect, useRef, useState } from 'react'
import { EDIT_LOG_ID, editsWord, pillLabel, pillVisible } from '../lib/editLog'
import { useWebEdits } from '../lib/webEditsState'
import { EditLogBody } from './EditLog'

function PencilIcon() {
  return (
    <svg
      className="edits-pill-icon"
      width="12"
      height="12"
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M11.2 1.8a1.6 1.6 0 0 1 2.3 0l.7.7a1.6 1.6 0 0 1 0 2.3L5 14l-3.5.9.9-3.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function WebEditsPill({ canEdit }: { canEdit: boolean }) {
  const { history } = useWebEdits()
  const visible = pillVisible(history)
  const pillRef = useRef<HTMLButtonElement>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const log = logRef.current
    if (!log) return undefined
    const onToggle = (event: Event) => {
      const opened = (event as ToggleEvent).newState === 'open'
      setOpen(opened)
      if (opened) {
        headingRef.current?.focus()
        return
      }
      const focused = document.activeElement
      if (!focused || focused === document.body || log.contains(focused)) pillRef.current?.focus()
    }
    log.addEventListener('toggle', onToggle)
    return () => log.removeEventListener('toggle', onToggle)
  }, [visible])

  if (!visible) return null

  const close = () => {
    const log = logRef.current
    if (log && typeof log.hidePopover === 'function' && log.matches(':popover-open')) {
      log.hidePopover()
    }
  }

  return (
    <>
      <button
        ref={pillRef}
        type="button"
        className="edits-pill"
        popoverTarget={EDIT_LOG_ID}
        aria-haspopup="dialog"
        aria-controls={EDIT_LOG_ID}
        aria-expanded={open}
        aria-label={pillLabel(history)}
        data-testid="edits-pill"
      >
        <PencilIcon />
        <span>{history.in_force_count}</span>
        <span className="edits-pill-words">{editsWord(history.in_force_count)}</span>
        {history.needs_review_count > 0 && (
          <span className="edits-pill-review">
            · {history.needs_review_count}
            <span className="edits-pill-words"> por revisar</span>
          </span>
        )}
      </button>
      <div
        ref={logRef}
        id={EDIT_LOG_ID}
        popover="auto"
        role="dialog"
        aria-labelledby="edit-log-heading"
        className="edit-log no-print"
        data-testid="edit-log"
      >
        <EditLogBody history={history} canEdit={canEdit} headingRef={headingRef} onNavigate={close} />
      </div>
    </>
  )
}
```

`AppHeader.tsx`: render `<WebEditsPill canEdit={canPublish} />` immediately after the `.version-chip` span, inside the same `signedIn && activeImport` branch.

`components.css` (after the `.version-chip.none` rule):

```css
/* ------------------------------------------------- web edits: pill and log */

/* The header's «N ediciones web» pill (indicator spec §4). The «web» chip's
   yellow: 6.65:1 text on its fill, and the fill stands well clear of the
   green bar. The words carry the meaning; colour repeats them. */
.edits-pill {
  anchor-name: --edit-log;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--s-2);
  min-height: 28px;
  padding: var(--s-1) var(--s-4);
  border: 1px solid var(--web-chip-line);
  border-radius: var(--r-pill);
  background: var(--web-chip-bg);
  color: var(--web-chip-ink);
  font: inherit;
  font-size: var(--t-micro);
  font-weight: 650;
  line-height: 1.35;
  white-space: nowrap;
  cursor: pointer;
}

.edits-pill:hover {
  border-color: var(--web-chip-ink);
}

.edits-pill:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

.edits-pill-icon {
  flex-shrink: 0;
}

/* «· 2 por revisar»: the conflict colour, 6.97:1. */
.edits-pill-review {
  margin-left: var(--s-1);
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--st-late-tint);
  color: var(--st-late-ink);
}

/* The log (spec §5): a native popover under the pill, right edges aligned. */
.edit-log {
  inset: auto;
  margin: 0;
  position-anchor: --edit-log;
  top: anchor(bottom);
  right: anchor(right);
  margin-top: var(--s-3);
  position-try-fallbacks: flip-inline, flip-block;
  width: min(26rem, calc(100vw - 2 * var(--s-4)));
  max-height: min(70vh, 36rem);
  overflow: auto;
  padding: var(--s-5);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-surface);
  background: var(--surface);
  box-shadow: var(--shadow-overlay);
  color: var(--ink);
  font-size: var(--t-small);
}

/* Before anchor positioning (pre-2026 browsers): under the bar, at the
   right gutter, which is where the pill sits anyway. */
@supports not (anchor-name: --edit-log) {
  .edit-log {
    top: calc(var(--shell-h) + var(--s-2));
    right: var(--s-6);
  }
}

.edit-log-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-2) var(--s-4);
  margin-bottom: var(--s-4);
}

.edit-log-head h2 {
  margin: 0;
  font-size: var(--t-section);
}

.edit-log-head h2:focus {
  outline: none;
}

.edit-log-counts {
  color: var(--ink-2);
  font-size: var(--t-micro);
}

.edit-log-review {
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--st-late-tint);
  color: var(--st-late-ink);
}

.edit-log-list {
  display: grid;
  gap: var(--s-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.edit-log-target {
  display: grid;
  gap: var(--s-1);
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-control);
  color: inherit;
  text-decoration: none;
}

a.edit-log-target:hover {
  background: var(--sunken);
}

.edit-log-what b {
  font-weight: 650;
}

.edit-log-value {
  display: -webkit-inline-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow-wrap: anywhere;
}

.edit-log-who {
  color: var(--ink-3);
  font-size: var(--t-micro);
}

.edit-log-state {
  justify-self: start;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  font-size: var(--t-micro);
  font-weight: 650;
}

.edit-log-state[data-state='en_conflicto'],
.edit-log-state[data-state='huerfana'] {
  border-color: var(--st-late);
  background: var(--st-late-tint);
  color: var(--st-late-ink);
}

.edit-log-entry[data-muted='true'] .edit-log-target {
  color: var(--ink-3);
}

.edit-log-more {
  margin: var(--s-3) 0 0;
}

.edit-log-foot {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3) var(--s-5);
  margin-top: var(--s-4);
  padding-top: var(--s-4);
  border-top: 1px solid var(--line);
}
```

In the `@media (max-width: 1023px)` block add `.edits-pill-words { display: none; }`. In the `@media (max-width: 767px)` block add:

```css
  /* A full-width panel under the wrapped bar, scrolling inside. */
  .edit-log {
    left: 0;
    right: 0;
    width: auto;
    max-height: 70vh;
    border-radius: 0;
  }
```

- [ ] **Step 5: Run** `npx vitest run && npx tsc -b && npm run lint` — Expected: PASS, no new lint warnings.
- [ ] **Step 6: Commit** — `git commit -m "feat(transelec): header pill with a log of web edits"`

### Task 6: Explorador — `?fila=<n>` opens a row

**Files:**
- Modify: `src/pages/ExploradorPage.tsx`
- Create: `src/pages/ExploradorPage.test.tsx`

**Interfaces:**
- Consumes: `entryHref` URLs (`?q=<pmf>&fila=<n>`), `getPmfDetail`.

- [ ] **Step 1: Write the failing tests** (`ExploradorPage.test.tsx`; mocks `getSummary`, `listRows`, `getPmfDetail`, and `RowDetailDrawer` as a stub with a «Cerrar» button calling `onClose`)

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../router'
import { useFilters } from '../lib/useFilters'
import { makeRow, makeSummary } from '../test/factories'
import { ExploradorPage } from './ExploradorPage'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, getSummary: vi.fn(), listRows: vi.fn(), getPmfDetail: vi.fn() }
})
vi.mock('../components/RowDetailDrawer', () => ({
  RowDetailDrawer: ({ row, onClose }: { row: { source_row_number: number }; onClose: () => void }) => (
    <div data-testid="drawer">
      fila {row.source_row_number}
      <button type="button" onClick={onClose}>
        Cerrar
      </button>
    </div>
  ),
}))
const { getSummary, listRows, getPmfDetail } = await import('../api')

function Page() {
  return <ExploradorPage filterController={useFilters()} activeImportId={12} />
}

function renderAt(path: string) {
  window.history.replaceState({}, '', path)
  return render(
    <RouterProvider initialPath={path}>
      <Page />
    </RouterProvider>,
  )
}

const page = (rows: number[]) => ({
  ok: true as const,
  data: {
    items: rows.map((n) => makeRow({ source_row_number: n, pmf: 'MP001' })),
    next_cursor: null,
    has_more: false,
    total_count: rows.length,
  },
})

describe('Explorador ?fila=', () => {
  beforeEach(() => {
    vi.mocked(getSummary).mockResolvedValue({ ok: true, data: makeSummary() })
    vi.mocked(listRows).mockResolvedValue(page([3, 7]))
    vi.mocked(getPmfDetail).mockReset()
  })

  it('opens the row once the rows load, and closing drops fila from the address', async () => {
    renderAt('/transelec/explorador?q=MP001&fila=7')
    expect(await screen.findByTestId('drawer')).toHaveTextContent('fila 7')
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByTestId('drawer')).not.toBeInTheDocument()
    expect(window.location.search).toBe('?q=MP001')
  })

  it('falls back to the PMF detail when the row is not on the first page', async () => {
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: 'MP001',
        row_count: 1,
        basis_estado_resumido: 'estado_resumido_first_row',
        estado_resumido: null,
        rows: [makeRow({ source_row_number: 90, pmf: 'MP001' })],
      },
    })
    renderAt('/transelec/explorador?q=MP001&fila=90')
    expect(await screen.findByTestId('drawer')).toHaveTextContent('fila 90')
    expect(getPmfDetail).toHaveBeenCalledWith('MP001')
  })

  it('says so when the row is not in the active version, and drops fila', async () => {
    vi.mocked(getPmfDetail).mockResolvedValue({ ok: false, status: 404, error: 'No encontrado' })
    renderAt('/transelec/explorador?q=MP001&fila=999')
    expect(
      await screen.findByText('No se encontró esta fila en la versión activa.'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('drawer')).not.toBeInTheDocument()
    expect(window.location.search).toBe('?q=MP001')
  })
})
```

(`collectAllRows` calls `listRows` too; the mocked page answers it.)

- [ ] **Step 2: Run** — Expected: FAIL (no drawer opens).

- [ ] **Step 3: Implement** in `ExploradorPage.tsx` (import `getPmfDetail`, `useRouter`, `ROUTES`):

```tsx
  const { search, navigate } = useRouter()
  const fila = new URLSearchParams(search).get('fila')
  const [filaMissing, setFilaMissing] = useState(false)
  const handledFila = useRef<string | null>(null)

  /** The address without `fila`, every filter kept. */
  const dropFila = useCallback(() => {
    const params = new URLSearchParams(search)
    if (!params.has('fila')) return
    params.delete('fila')
    const rest = params.toString()
    navigate(`${ROUTES.explorador}${rest ? `?${rest}` : ''}`, { replace: true })
  }, [search, navigate])

  // A log entry links here with `?q=<pmf>&fila=<n>` (indicator spec §5): open
  // that row's drawer once the filtered rows are in. A search for the PMF can
  // match other PMFs too, so a row past the first page is found through the
  // PMF's own detail instead.
  useEffect(() => {
    if (fila === null) {
      handledFila.current = null
      return
    }
    if (loading || !data || handledFila.current === fila) return
    handledFila.current = fila
    setFilaMissing(false)
    const target = /^\d+$/.test(fila) ? Number(fila) : null
    const onPage = data.page.items.find((entry) => entry.source_row_number === target)
    if (onPage) {
      setOpenRow(onPage)
      return
    }
    void (async () => {
      const detail = target !== null && filters.q ? await getPmfDetail(filters.q) : null
      if (handledFila.current !== fila) return
      const row = detail?.ok
        ? detail.data.rows.find((entry) => entry.source_row_number === target)
        : undefined
      if (row) {
        setOpenRow(row)
      } else {
        setFilaMissing(true)
        dropFila()
      }
    })()
  }, [fila, data, loading, filters.q, dropFila])

  useEffect(() => setFilaMissing(false), [key])
```

Render, above the `pageFailure` banner: `{filaMissing && <AlertBanner tone="warn" title="Fila no encontrada">No se encontró esta fila en la versión activa.</AlertBanner>}` — change the test's `findByText` to match the banner body (`/No se encontró esta fila en la versión activa\./`) if the title splits the text node. The drawer's `onClose` becomes `() => { setOpenRow(null); dropFila() }`.

- [ ] **Step 4: Run** `npx vitest run src/pages/ExploradorPage.test.tsx && npx tsc -b` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(transelec): Explorador opens the row a log entry links to"`

### Task 7: Ediciones web — «Historial»

**Files:**
- Modify: `src/pages/EdicionesPage.tsx`, `src/pages/EdicionesPage.test.tsx`

- [ ] **Step 1: Failing test** — rendered inside a `WebEditsContext.Provider` with `makeHistory({ entries: [makeHistoryEntry({ id: 3, state: 'discarded', source_row_number: null, ended_by_display_name: 'Ana' }), makeHistoryEntry({ id: 2 })] })`:

```tsx
it('lists the latest edits under «Historial», in the log’s format', async () => {
  vi.mocked(listOverrides).mockResolvedValue({ ok: true, data: [] })
  renderWithEdits(history)
  const section = await screen.findByTestId('edits-history')
  expect(within(section).getByRole('heading', { name: 'Historial' })).toBeInTheDocument()
  expect(section).toHaveTextContent('Últimas 50 ediciones')
  expect(within(section).getByTestId('edit-log-3')).toHaveTextContent(
    'revertida al valor de la planilla · Ana',
  )
  expect(within(section).getByTestId('edit-log-2')).toBeInTheDocument()
})

it('says when the history could not be loaded', async () => {
  vi.mocked(listOverrides).mockResolvedValue({ ok: true, data: [] })
  renderWithEdits(null, 'error')
  expect(await screen.findByText('No se pudo cargar el historial de ediciones.')).toBeInTheDocument()
})
```

- [ ] **Step 2: Implement** — after the active-edits `<section>`:

```tsx
      <section aria-labelledby="historial-title" data-testid="edits-history">
        <SectionHeader
          id="historial-title"
          title="Historial"
          meta={`Últimas ${EDIT_HISTORY_LIMIT} ediciones, de la más reciente a la más antigua, incluidas las reemplazadas y las revertidas.`}
        />
        {editsHistory ? (
          editsHistory.entries.length === 0 ? (
            <div className="empty">Todavía no hay ediciones web.</div>
          ) : (
            <EditLogList entries={editsHistory.entries} />
          )
        ) : editsStatus === 'error' ? (
          <p className="hint">No se pudo cargar el historial de ediciones.</p>
        ) : (
          <LoadingBlock label="Cargando el historial…" lines={2} />
        )}
      </section>
```

with `const { history: editsHistory, status: editsStatus, refresh: refreshEdits } = useWebEdits()`. (Check `SectionHeader` accepts `id`, as the existing «Ediciones web» header does.)

- [ ] **Step 3: Run** `npx vitest run src/pages/EdicionesPage.test.tsx` — PASS. **Commit** — `git commit -m "feat(transelec): Ediciones web shows the edit history"`

### Task 8: Estado — «web» chips and the note

**Files:**
- Modify: `src/lib/webEdits.ts` (+test), `src/lib/estadoColumns.tsx`, `src/lib/plazoColumn.tsx`, `src/components/EstadoTable.tsx`, `src/components/EstadoTable.test.tsx`, `src/styles/components.css`

**Interfaces:**
- Produces: `EstadoColumn.webFields?: readonly EditableFieldName[]`; `webFieldsDescription(fields): string`; `editedAmong(row, fields): EditableFieldName[]`.

- [ ] **Step 1: Failing tests**

`webEdits.test.ts`:

```ts
it('describes edited fields by name, joined with «y»', () => {
  expect(webFieldsDescription(['numero_ingreso_2'])).toBe('N.º ingreso 2 editado en la web')
  expect(webFieldsDescription(['reingreso_tec', 'reingreso_legal'])).toBe(
    'Reingreso técnico y Reingreso legal editados en la web',
  )
  expect(webFieldsDescription(['fecha_ingreso', 'fecha_ingreso_2', 'fecha_90_dias'])).toBe(
    'Fecha ingreso, Fecha ingreso 2 y 90 días editados en la web',
  )
})
```

`EstadoTable.test.tsx`:

```tsx
it('marks each cell whose value was edited, naming the fields for screen readers', () => {
  const rows = [
    makeLifecycleRow({ source_row_number: 1, pmf: 'MP001', web_fields: ['numero_ingreso_2'] }),
    makeLifecycleRow({ source_row_number: 2, pmf: 'MP002', web_fields: ['estado_resumido'] }),
    makeLifecycleRow({ source_row_number: 3, pmf: 'MP003', web_fields: [] }),
  ]
  render(<EstadoTable rows={rows} selectedRow={null} onOpen={() => {}} />)
  const first = screen.getByTestId('estado-row-1')
  const ingresos = first.querySelector('td[data-col="ingresos"]') as HTMLElement
  expect(within(ingresos).getByTestId('web-chip')).toHaveTextContent(
    'web, N.º ingreso 2 editado en la web',
  )
  expect(within(first).getAllByTestId('web-chip')).toHaveLength(1)
  const second = screen.getByTestId('estado-row-2')
  for (const col of ['grupo', 'paso']) {
    const cellEl = second.querySelector(`td[data-col="${col}"]`) as HTMLElement
    expect(within(cellEl).getByTestId('web-chip')).toHaveTextContent('Estado resumido editado en la web')
  }
  expect(within(screen.getByTestId('estado-row-3')).queryByTestId('web-chip')).not.toBeInTheDocument()
  expect(screen.getByTestId('estado-web-note')).toHaveTextContent(
    'Los valores marcados «web» se editaron en el panel; la planilla publicada no cambió.',
  )
})

it('marks the plazo column for an edited date, and shows no note without edits', () => {
  const rows = [makeLifecycleRow({ source_row_number: 1, web_fields: ['fecha_90_dias'] })]
  const { unmount } = render(
    <EstadoTable
      rows={rows}
      selectedRow={null}
      onOpen={() => {}}
      extraColumns={[plazoColumn(new Map(), false)]}
    />,
  )
  const plazo = screen.getByTestId('estado-row-1').querySelector('td[data-col="plazo"]') as HTMLElement
  expect(within(plazo).getByTestId('web-chip')).toHaveTextContent('90 días editado en la web')
  unmount()

  render(<EstadoTable rows={[makeLifecycleRow({ web_fields: [] })]} selectedRow={null} onOpen={() => {}} />)
  expect(screen.queryByTestId('estado-web-note')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Implement.** `webEdits.ts`:

```ts
const FIELD_LIST = new Intl.ListFormat('es', { type: 'conjunction' })

/** «N.º ingreso 2 editado en la web»; several fields joined with «y». */
export function webFieldsDescription(fields: readonly EditableFieldName[]): string {
  const labels = fields.map((field) => specFor(field).label)
  return `${FIELD_LIST.format(labels)} ${labels.length === 1 ? 'editado' : 'editados'} en la web`
}

/** The fields among `fields` this row shows as edited on the web, in that order. */
export function editedAmong(
  row: Pick<ResumenRow, 'web_fields'>,
  fields: readonly EditableFieldName[],
): EditableFieldName[] {
  return fields.filter((field) => isWebField(row, field))
}
```

`estadoColumns.tsx`: add to `EstadoColumn` the documented field `webFields?: readonly EditableFieldName[]` («The fields this column shows; an edit to any of them marks the cell «web».»), and set it: `grupo` and `paso` → `['estado_resumido', 'estado']`; `tipo_rechazo` → `['tipo_rechazo']`; `ingresos` → `['numero_ingreso', 'numero_ingreso_2']`; `reingresos` → `['reingreso_tec', 'reingreso_legal', 'reingreso_recrep']`. `plazoColumn` → `webFields: ['fecha_ingreso', 'fecha_ingreso_2', 'fecha_90_dias']`.

`EstadoTable.tsx`:

```tsx
  const columns = withExtraColumns(extraColumns)
  const edited = (row: LifecycleRow, column: EstadoColumn) =>
    column.webFields ? editedAmong(row, column.webFields) : []
  const anyEdited = rows.some((row) => columns.some((column) => edited(row, column).length > 0))

  return (
    <>
      {anyEdited && (
        <p className="hint estado-web-note" data-testid="estado-web-note">
          Los valores marcados «web» se editaron en el panel; la planilla publicada no cambió.
        </p>
      )}
      <div className="tablewrap" data-testid="estado-table">
        …
                {columns.map((column) => {
                  const fields = edited(row, column)
                  return (
                    <td key={column.key} data-col={column.key}>
                      {column.render(row)}
                      {fields.length > 0 && <WebChip description={webFieldsDescription(fields)} />}
                    </td>
                  )
                })}
        …
      </div>
    </>
  )
```

CSS: `.estado-web-note { margin: 0 0 var(--s-3); }`.

- [ ] **Step 3: Run** `npx vitest run src/components/EstadoTable.test.tsx src/lib/webEdits.test.ts src/pages/EstadoPage.test.tsx` — PASS. **Commit** — `git commit -m "feat(transelec): Estado marks values edited on the web"`

### Task 9: Resumen — the edited-totals hint

**Files:** Modify `src/components/StatusHeadline.tsx`, `src/components/StatusHeadline.test.tsx`

- [ ] **Step 1: Failing tests**

```tsx
it('says how many PMF are counted under an edited state, and opens the log', async () => {
  const openLog = vi.fn()
  render(
    <RouterProvider initialPath={ROUTES.resumen}>
      <WebEditsContext.Provider value={{ history: makeHistory(), status: 'ready', refresh: vi.fn(), openLog }}>
        <StatusHeadline summary={makeSummary({ web_edited_pmf_count: 2 })} filters={EMPTY_FILTERS} />
      </WebEditsContext.Provider>
    </RouterProvider>,
  )
  expect(screen.getByTestId('status-web-note')).toHaveTextContent(
    'Incluye 2 PMF con estado editado en la web.',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Ver ediciones' }))
  expect(openLog).toHaveBeenCalledTimes(1)
})

it('is singular-safe and absent without edited states', () => {
  … makeSummary({ web_edited_pmf_count: 1 }) → 'Incluye 1 PMF con estado editado en la web.'
  … makeSummary({ web_edited_pmf_count: 0 }) → queryByTestId('status-web-note') is null
})
```

- [ ] **Step 2: Implement** — in `StatusHeadline`, `const { history, openLog } = useWebEdits()`, and after the conflicts note:

```tsx
        {summary.web_edited_pmf_count > 0 && (
          <p className="hint" data-testid="status-web-note">
            Incluye {formatInteger(summary.web_edited_pmf_count)} PMF con estado editado en la
            web.{' '}
            {pillVisible(history) && (
              <button type="button" className="btn-link" onClick={openLog}>
                Ver ediciones
              </button>
            )}
          </p>
        )}
```

The top bar is sticky, so the log opens in view; the popover's `toggle` handler moves focus into it.

- [ ] **Step 3: Run, commit** — `git commit -m "feat(transelec): the Resumen says when totals include web edits"`

### Task 10: Drawer fixes

**Files:**
- Create: `src/components/DrawerConfirm.tsx`
- Modify: `src/components/RowDetailDrawer.tsx`, `src/components/EditableFieldsSection.tsx`, `src/components/RowDetailDrawer.test.tsx`, `src/components/EditableFieldsSection.test.tsx`

**Interfaces:**
- Produces: `<DrawerConfirm {...ConfirmDialogProps}>`; `EditableFieldsSection` prop `onDirtyChange?: (dirty: boolean) => void`.

- [ ] **Step 1: Failing tests** (`RowDetailDrawer.test.tsx`, a new `describe('RowDetailDrawer — editing')`, with `getPmfDetail` answering two rows 2 and 3 of `BN001`, `listOverrides` `[]`, `saveOverride` mocked)

```tsx
it('puts «Campos editables» first for editors and leaves Tramitación only what is not editable', async () => {
  render(<RowDetailDrawer row={tracked} onClose={() => {}} canEdit activeImportId={12} sourceFields={null} />)
  const sections = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
  expect(sections[0]).toBe('Campos editables')
  const tramitacion = screen.getByRole('heading', { name: 'Tramitación' }).closest('section') as HTMLElement
  expect(within(tramitacion).queryByText('Estado vigente')).not.toBeInTheDocument()
  expect(within(tramitacion).queryByText('N.º ingreso')).not.toBeInTheDocument()
  expect(within(tramitacion).getByText('PAS')).toBeInTheDocument()
  // The CONAF links moved with the N.º de ingreso.
  expect(within(screen.getByTestId('drawer-editables')).getByTestId('drawer-ov-1')).toBeInTheDocument()
})

it('changes nothing for viewers', async () => {
  render(<RowDetailDrawer row={tracked} onClose={() => {}} canEdit={false} sourceFields={null} />)
  const tramitacion = screen.getByRole('heading', { name: 'Tramitación' }).closest('section') as HTMLElement
  expect(within(tramitacion).getByText('Estado vigente')).toBeInTheDocument()
  expect(within(tramitacion).getByTestId('drawer-ov-1')).toBeInTheDocument()
})

it('starts the editable fields fresh on another row', async () => {
  vi.mocked(saveOverride).mockResolvedValue({ ok: true, data: { override_id: 5, changed: true, row: { ...tracked, estado: 'X' } } })
  render(<RowDetailDrawer row={tracked} onClose={() => {}} canEdit activeImportId={12} sourceFields={null} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Editar Estado vigente' }))
  await userEvent.clear(screen.getByLabelText('Nuevo valor de Estado vigente'))
  await userEvent.type(screen.getByLabelText('Nuevo valor de Estado vigente'), 'X')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(await screen.findByText('Se guardó el cambio en Estado vigente.')).toBeInTheDocument()
  await userEvent.click(await screen.findByRole('button', { name: 'Ver la fila 3' }))
  expect(screen.getByTestId('editables-status')).toBeEmptyDOMElement()
})

it('asks before discarding an unsaved change when another row is chosen', async () => {
  render(<RowDetailDrawer row={tracked} onClose={() => {}} canEdit activeImportId={12} sourceFields={null} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Editar Estado vigente' }))
  await userEvent.type(screen.getByLabelText('Nuevo valor de Estado vigente'), ' nuevo')
  await userEvent.click(await screen.findByRole('button', { name: 'Ver la fila 3' }))
  const dialog = screen.getByRole('dialog', { name: '¿Descartar el cambio sin guardar?' })
  await userEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
  expect(screen.getByLabelText('Nuevo valor de Estado vigente')).toHaveValue(`${tracked.estado ?? ''} nuevo`)
  expect(screen.getByTestId('drawer-provenance')).toHaveTextContent('Fila de origen 2')

  await userEvent.click(screen.getByRole('button', { name: 'Ver la fila 3' }))
  await userEvent.click(screen.getByRole('button', { name: 'Descartar el cambio' }))
  expect(screen.getByTestId('drawer-provenance')).toHaveTextContent('Fila de origen 3')
  expect(screen.queryByLabelText('Nuevo valor de Estado vigente')).not.toBeInTheDocument()
})

it('switches rows without asking when the open editor has no change', async () => {
  … open the editor, click «Ver la fila 3» → no dialog, provenance «Fila de origen 3»
})

it('a save that lands after a row switch does not switch back', async () => {
  let finish!: (value: unknown) => void
  vi.mocked(saveOverride).mockReturnValue(new Promise((done) => { finish = done }) as never)
  … edit row 2, click Guardar (pending), click «Ver la fila 3», confirm «Descartar el cambio»
  await act(async () => finish({ ok: true, data: { override_id: 5, changed: true, row: { ...tracked, estado: 'X' } } }))
  expect(screen.getByTestId('drawer-provenance')).toHaveTextContent('Fila de origen 3')
})
```

`EditableFieldsSection.test.tsx`: `onDirtyChange` reports `true` after typing a different value and `false` after Cancelar.

- [ ] **Step 2: Implement `DrawerConfirm.tsx`** — moves `EditableFieldsSection`'s portal and `onDialogKeyDown` here:

```tsx
/**
 * A confirmation opened over the row drawer.
 *
 * The drawer listens for Escape and Tab on the document, so a dialog on top
 * of it keeps both to itself: Escape cancels only the dialog, and Tab cycles
 * only its buttons. Rendered into document.body, like the drawer.
 */
import type { ComponentProps, KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { ConfirmDialog } from './ConfirmDialog'

const FOCUSABLE = 'button:not([disabled])'

export function DrawerConfirm(props: ComponentProps<typeof ConfirmDialog>) {
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      event.preventDefault()
      props.onCancel()
    } else if (event.key === 'Tab') {
      const buttons = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (buttons.length === 0) return
      event.stopPropagation()
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
  }
  return createPortal(<div onKeyDown={onKeyDown}><ConfirmDialog {...props} /></div>, document.body)
}
```

`EditableFieldsSection` renders the revert confirmation as `<DrawerConfirm … onCancel={() => { setReverting(null); setFocusTarget(`revert-${reverting.spec.name}`) }}>` and drops `onDialogKeyDown`, `FOCUSABLE` and `createPortal`.

- [ ] **Step 3: Implement the section changes** (`EditableFieldsSection.tsx`):
  - prop `onDirtyChange?: (dirty: boolean) => void`; `const dirty = editing !== null && draft !== (seenValue ?? '')`; `useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange])`.
  - for editors (`canEdit`), in the read view of `numero_ingreso` (always) and `numero_ingreso_2` (when it has a value), after the value: `<OficinaVirtualLink key={row[spec.name] ?? ''} numero={row[spec.name]} testId={spec.name === 'numero_ingreso' ? 'drawer-ov-1' : 'drawer-ov-2'} />`. «Varias fechas en la celda» already comes with `SourceDate`.

- [ ] **Step 4: Implement the drawer changes** (`RowDetailDrawer.tsx`):
  - `const dirtyRef = useRef(false)`; `const [pendingRow, setPendingRow] = useState<ResumenRow | null>(null)`; `const switchTrigger = useRef<HTMLElement | null>(null)`.
  - `chooseRow(entry)`: `if (dirtyRef.current) { switchTrigger.current = document.activeElement as HTMLElement | null; setPendingRow(entry) } else setCurrent(entry)`; the «Ver la fila N» buttons call it.
  - The section element is built once:

    ```tsx
    const editables = (canEdit || (current.web_fields ?? []).length > 0) && (
      <EditableFieldsSection
        key={current.source_row_number}
        …existing props…
        onDirtyChange={(dirty) => { dirtyRef.current = dirty }}
        onSaved={(updated) => {
          // A save answers for the row its editor was opened on; if the reader
          // has moved to another row since, the drawer stays where it is.
          if (updated.source_row_number === currentRowRef.current) setCurrent(updated)
          setReloadToken((value) => value + 1)
          onRowEdited?.(updated)
        }}
      />
    )
    ```

    and rendered as `{canEdit && editables}` first inside `.drawer-sections`, and `{!canEdit && editables}` where it is today.
  - Tramitación wraps the `Fact`s of `estado`, `tipo_rechazo`, `numero_ingreso`, `fecha_ingreso`, `numero_ingreso_2`, `fecha_ingreso_2` and `fecha_90_dias` in `!canEdit`; the «Segundo ingreso» absence note, PAS, Empresa and Propietario stay for everyone.
  - The confirmation:

    ```tsx
    {pendingRow && (
      <DrawerConfirm
        title="¿Descartar el cambio sin guardar?"
        confirmLabel="Descartar el cambio"
        tone="danger"
        onConfirm={() => {
          dirtyRef.current = false
          setCurrent(pendingRow)
          setPendingRow(null)
        }}
        onCancel={() => {
          setPendingRow(null)
          switchTrigger.current?.focus()
        }}
      >
        <p>
          Hay un cambio sin guardar en la fila {formatInteger(current.source_row_number)}. Si abre
          la fila {formatInteger(pendingRow.source_row_number)}, ese cambio se pierde.
        </p>
      </DrawerConfirm>
    )}
    ```

- [ ] **Step 5: Run** `npx vitest run && npx tsc -b && npm run lint` — PASS. **Commit** — `git commit -m "fix(transelec): drawer puts editing first and never loses or misroutes a change"`

### Task 11: Suggestions without case or accent variants

**Files:** Modify `src/lib/webEdits.ts`, `src/lib/webEdits.test.ts`

- [ ] **Step 1: Failing tests**

```ts
describe('suggestionsFrom groups spellings of one value', () => {
  const rows = (values: (string | null)[]) =>
    values.map((estado, index) => makeRow({ source_row_number: index + 1, estado }))

  it('keeps the spelling the version uses most', () => {
    expect(
      suggestionsFrom(rows(['En Evaluacion', 'En evaluacion', 'En evaluacion', 'Aprobado']), 'estado'),
    ).toEqual(['Aprobado', 'En evaluacion'])
  })

  it('ignores accents, case, NBSP and repeated spaces', () => {
    expect(
      suggestionsFrom(rows(['En evaluación', 'EN  EVALUACION', 'En evaluacion ', 'En evaluación']), 'estado'),
    ).toEqual(['En evaluación'])
  })

  it('ties go to the first spelling in Spanish order', () => {
    const tie = suggestionsFrom(rows(['Rechazado', 'rechazado']), 'estado')
    expect(tie).toEqual([['Rechazado', 'rechazado'].sort((a, b) => a.localeCompare(b, 'es'))[0]])
  })

  it('skips blanks', () => {
    expect(suggestionsFrom(rows([null, '  ', ' ']), 'estado')).toEqual([])
  })
})
```

- [ ] **Step 2: Implement** — replace `suggestionsFrom`:

```ts
/** Spacing as the server compares it: NBSP is a space, runs collapse, ends trim. */
function spaced(value: string): string {
  return value.replace(/ /g, ' ').trim().replace(/\s+/g, ' ')
}

/** Two spellings of one value share this key: case, accents and spacing ignored. */
export function suggestionKey(value: string): string {
  return spaced(value).normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('es')
}

/**
 * One suggestion per value of `field` in `rows`, ignoring case, accents and
 * spacing (indicator spec §10): each group shows the spelling the rows use
 * most, ties going to the first in Spanish order. Picking one writes it as
 * shown; the server's own rules are unchanged.
 */
export function suggestionsFrom(rows: readonly ResumenRow[], field: EditableFieldName): string[] {
  const groups = new Map<string, Map<string, number>>()
  for (const row of rows) {
    const spelling = spaced(row[field] ?? '')
    if (!spelling) continue
    const key = suggestionKey(spelling)
    const counts = groups.get(key) ?? new Map<string, number>()
    counts.set(spelling, (counts.get(spelling) ?? 0) + 1)
    groups.set(key, counts)
  }
  const byUseThenOrder = ([a, uses]: [string, number], [b, other]: [string, number]) =>
    other - uses || a.localeCompare(b, 'es')
  return [...groups.values()]
    .map((counts) => [...counts.entries()].sort(byUseThenOrder)[0][0])
    .sort((a, b) => a.localeCompare(b, 'es'))
}
```

- [ ] **Step 3: Run, commit** — `git commit -m "fix(transelec): one suggestion per value, whatever its case or accents"`

### Task 12: End-to-end

**Files:** Modify `tests/e2e/stubs.ts`, `tests/e2e/web-edits.spec.ts`, `tests/e2e/navigation.spec.ts`

- [ ] **Step 1: Stub** — `StubOptions.history?: Record<string, unknown> | ((page: Page) => unknown)`; `summaryFixture` gains `web_edited_pmf_count: 0`; after the two `overrides` routes and before `options.extra`:

```ts
  // The header's edits log (indicator spec §1): nothing in force by default,
  // so the pill stays hidden unless a test supplies a history.
  await page.route('**/api/transelec/overrides/history*', (route) => {
    if (fail) return json(route, failBody, fail)
    return json(route, options.history ?? { in_force_count: 0, needs_review_count: 0, entries: [] })
  })
```

- [ ] **Step 2: Specs** (`web-edits.spec.ts`):
  1. *the pill opens the log; Esc and an outside click close it, and focus returns to the pill* — history with one `aplicada` and one `discarded` entry; pill «1 edición web»; click → `getByRole('dialog', { name: 'Ediciones web' })` visible, heading focused, `aria-expanded="true"`; Escape → hidden, pill focused, `aria-expanded="false"`; open again, `page.mouse.click(10, 400)` → hidden.
  2. *an entry opens the Explorador drawer on its row, and an edit there updates the pill* — `statefulEdits` extended so `GET /overrides/history` derives `{in_force_count: edits.length, entries}` from the in-memory edits; click the entry → URL contains `fila=1`, drawer shows «Fila de origen 1»; edit «Estado vigente», save → pill reads «2 ediciones web»; close the drawer → URL has no `fila`.
  3. *an entry whose row is gone shows the notice* — history entry `source_row_number: 999`; click → «No se encontró esta fila en la versión activa.», no drawer.
  4. *a viewer sees the pill and the log without the footer* — `me: VIEWER`.
- [ ] **Step 3: Bar fit** (`navigation.spec.ts`) — in «the shell bar at laptop widths», a second loop over `[1024, 1280, 1366, 1440]` with `history: { in_force_count: 5, needs_review_count: 2, entries: [] }`: the last section link ends left of `.shell-side`; the pill and the version chip do not overlap; at 1024 the pill reads only the numbers. New test: at 390 px, open the log; its box lies within `[0, 390]` and its height ≤ 70 % of the viewport. If 1280 fails, move `.edits-pill-words { display: none }` to the smallest breakpoint that passes and record it under "Deviations".
- [ ] **Step 4: Run** `npm run test:e2e` — PASS. **Commit** — `git commit -m "test(transelec): e2e for the edits pill, its log and the bar width"`

### Task 13: Docs and full verification

- [ ] **Step 1:** Spec status line → «Implemented by `docs/superpowers/plans/2026-10-05-transelec-web-edits-indicator.md` (PR #…)»; record deviations.
- [ ] **Step 2:** `products/transelect/docs/deployment.md` lists the Transelec routes a deploy smoke-checks; add `/transelec/overrides/history` beside `/transelec/overrides`.
- [ ] **Step 3:** `uv run python scripts/update_doc_nav.py && uv run python scripts/check_doc_links.py`.
- [ ] **Step 4: Full verification** — `uv run ruff format --check . && uv run ruff check . && uv run mypy . && uv run pytest`; `<integration prefix> uv run pytest -q apps/api/integration_tests`; dashboard `npm test && npm run lint && npx tsc -b && npm run build && npm run test:e2e`.
- [ ] **Step 5: Commit** — `git commit -m "docs(transelec): the web edits indicator is implemented"`

## Deviations from the spec (decided while planning)

- **Summary-count tests live in `test_transelec_overrides.py`**, not `test_transelec_reads_router.py`: that module already owns the override fixtures (`_publish`, `_put`, `_BASE_ROWS`) and the cleanup that deletes overrides first.
- **A log link whose row is not on the Explorador's first page** opens through `GET /pmfs/{pmf}` (the spec says only "once its rows load"). `?q=` is a substring search over every field, so a PMF's rows are not guaranteed to be on page 1.
- **A save that answers after a row switch** refreshes the drawer's data but does not switch it back (the spec says "a save always goes to the row the editor was opened on"; this is the matching rule for its response).
- **Download in the popover** shares one hook with Ediciones web instead of a second copy.

## Deviations from the plan (decided while building)

- **The provider derives its status** (idle without a version, loading until the first answer) and sets state only when an answer arrives, instead of calling `setStatus` inside `load()`. Same states, and oxlint stays at its baseline (no `set-state-in-effect`).
- **The Explorador's «fila» notice resets during render** on a filter change, for the same reason.
- **Ediciones web still clears its status message when a download starts**, as the old inline download did, so the live region does not re-announce a stale message afterwards.
- **`.estado-web-note` lives in `sections.css`** beside the Estado table rules (single-section rules belong there).
- **`products/transelect/docs/deployment.md` is not changed:** it records what production served on a date; the history route goes into the next deploy record.
- **Two existing `EditableFieldsSection` tests read the section's status by test id:** editors now get the CONAF link in the section, which has its own `role="status"`.
- **The e2e edit in «a log entry opens the Explorador drawer…» uses «Estado resumido»:** the stub's active version has a column for no other editable field.
