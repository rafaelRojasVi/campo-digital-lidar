# Migration Graph Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the Alembic revision `"0003"` collision between the Forestry and
Transelec product branches into a single linear global migration chain on
`feat/platform-ingestion-access-v1`, without rewriting either product's
already-tested table definitions, and add a regression check so parallel
product branches cannot silently collide on a revision id again.

**Architecture:** Bring `migrations/versions/0003_establish_forestry_source_substrate.py`
into this worktree unchanged (verified via `git show
feat/forestry-dashboard-v1:...`). Bring Transelec's colliding migration in as
revision `"0004"` with `down_revision = "0003"`, keeping every table/column
definition byte-identical to `feat/transelec-hosted-pilot-v1` except the
revision header. Add a pure-Python test that loads every file in
`migrations/versions/` and asserts revision ids are unique and form one linear
chain, independent of Alembic's own `ScriptDirectory` construction. Record the
allocation convention as an ADR.

**Tech Stack:** Python 3.12, Alembic, SQLAlchemy Core (no ORM), pytest, `uv`.

**Spec:** PART 1 of the task brief given in this session (see conversation);
ground truth gathered via `git show` of
`feat/forestry-dashboard-v1:migrations/versions/0003_establish_forestry_source_substrate.py`
and
`feat/transelec-hosted-pilot-v1:migrations/versions/0003_establish_transelec_hosted_snapshots.py`.

## Global Constraints

- Do not modify any sibling worktree. Only read from other branches via `git show`.
- Do not rewrite table/column definitions of either colliding migration — only
  the revision header (`revision`, `down_revision`) and filename may change.
- The migration chain must have exactly one base and one head
  (`apps/api/app/migration_graph.py::inspect_migration_graph`,
  `scripts/migration_check.py`).
- IDs `0004` and `0005` are confirmed free across every branch inspected
  (main, feat/forestry-dashboard-v1, feat/forestry-source-evidence-v1,
  feat/transelec-hosted-pilot-v1, feat/transelec-ui-reference-parity-v1,
  feat/platform-portal-v1).
- Never skip hooks; never use `git push`.

---

### Task 1: Bring in the Forestry `0003` migration unchanged

**Files:**
- Create: `migrations/versions/0003_establish_forestry_source_substrate.py`
- Test: `apps/api/tests/test_migration_graph.py` (existing test must still pass)

**Interfaces:**
- Consumes: `platform.source_snapshot` (from `0002`, already present in this worktree).
- Produces: `forestry` schema, `forestry.shapefile_snapshot`,
  `forestry.source_feature` tables, for Task 2 to chain after.

- [ ] **Step 1: Copy the file verbatim from the forestry branch**

```bash
git show feat/forestry-dashboard-v1:migrations/versions/0003_establish_forestry_source_substrate.py \
  > migrations/versions/0003_establish_forestry_source_substrate.py
```

- [ ] **Step 2: Diff against the source branch to confirm byte-fidelity**

```bash
diff <(git show feat/forestry-dashboard-v1:migrations/versions/0003_establish_forestry_source_substrate.py) \
     migrations/versions/0003_establish_forestry_source_substrate.py
```

Expected: no output (files identical).

- [ ] **Step 3: Confirm the file's own revision header is unmodified**

Expected content includes exactly:
```python
revision: str = "0003"
down_revision: str | None = "0002"
```

- [ ] **Step 4: Commit is deferred to Task 5** (this task alone would leave the
  graph with a single head at `0003`, which is a valid intermediate state but
  not yet the final chain — do not commit yet).

---

### Task 2: Bring in the Transelec migration as `0004`, chained after Forestry

**Files:**
- Create: `migrations/versions/0004_establish_transelec_hosted_snapshots.py`

**Interfaces:**
- Consumes: `platform.source_snapshot` (from `0002`) and requires `0003` (Forestry) applied first — this is deployment ordering only, `transelec_workbook_snapshot` has no FK to any Forestry table.
- Produces: `platform.transelec_workbook_snapshot`, `platform.transelec_dashboard_state` tables. This becomes the new chain head after this task.

- [ ] **Step 1: Copy the file verbatim from the transelec branch under the new name**

```bash
git show feat/transelec-hosted-pilot-v1:migrations/versions/0003_establish_transelec_hosted_snapshots.py \
  > migrations/versions/0004_establish_transelec_hosted_snapshots.py
```

- [ ] **Step 2: Edit only the revision header**

In `migrations/versions/0004_establish_transelec_hosted_snapshots.py`, change:

```python
revision: str = "0003"
down_revision: str | None = "0002"
```

to:

```python
revision: str = "0004"
down_revision: str | None = "0003"
```

Also update the module docstring's `Revision ID:` / `Revises:` lines if present, to `0004` / `0003`, for consistency with the Forestry migration's docstring convention. Do not touch anything in `upgrade()` or `downgrade()`.

- [ ] **Step 3: Diff the body (excluding the header) against the source branch**

```bash
diff <(git show feat/transelec-hosted-pilot-v1:migrations/versions/0003_establish_transelec_hosted_snapshots.py | tail -n +6) \
     <(tail -n +6 migrations/versions/0004_establish_transelec_hosted_snapshots.py)
```

Expected: no output beyond the header lines already excluded by `tail -n +6`
(adjust the offset if the docstring edit shifts line numbers — the goal is
zero differences in `upgrade()`/`downgrade()`).

- [ ] **Step 4: Sanity-check the graph loads with one base and one head**

```bash
uv run python -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
config = Config('alembic.ini')
script = ScriptDirectory.from_config(config)
print('bases:', script.get_bases())
print('heads:', script.get_heads())
"
```

Expected: `bases: ('0001',)` and `heads: ('0004',)`.

---

### Task 3: Add a pure-Python regression test against duplicate/broken revision ids

**Files:**
- Modify: `apps/api/tests/test_migration_graph.py`

**Interfaces:**
- Consumes: `migrations/versions/*.py` files directly (via `importlib`), independent of Alembic's `ScriptDirectory`.
- Produces: two new test functions other tasks/tests do not depend on.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/test_migration_graph.py`:

```python
import importlib.util
from types import ModuleType


def _load_migration_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_all_migrations(root: Path) -> dict[str, tuple[str | None, Path]]:
    versions_dir = root / "migrations" / "versions"
    revisions: dict[str, tuple[str | None, Path]] = {}
    for path in sorted(versions_dir.glob("*.py")):
        module = _load_migration_module(path)
        revision = module.revision
        if revision in revisions:
            _, existing_path = revisions[revision]
            raise AssertionError(
                f"Duplicate Alembic revision id {revision!r} declared in "
                f"both {existing_path.name} and {path.name}."
            )
        revisions[revision] = (module.down_revision, path)
    return revisions


def test_migration_revision_ids_are_unique() -> None:
    root = Path(__file__).resolve().parents[3]
    revisions = _load_all_migrations(root)

    assert len(revisions) >= 1


def test_migration_chain_is_single_linear_sequence() -> None:
    root = Path(__file__).resolve().parents[3]
    revisions = _load_all_migrations(root)

    bases = [rev for rev, (down, _) in revisions.items() if down is None]
    assert len(bases) == 1, f"Expected exactly one base revision, found {bases!r}"

    down_revisions = {down for down, _ in revisions.values() if down is not None}
    all_targets = set(revisions)
    dangling = down_revisions - all_targets
    assert not dangling, f"down_revision references missing revisions: {dangling!r}"

    referenced_as_down = [down for down, _ in revisions.values() if down is not None]
    assert len(referenced_as_down) == len(set(referenced_as_down)), (
        "More than one migration shares the same down_revision — "
        "this is a branch, not a linear chain."
    )

    heads = all_targets - down_revisions
    assert len(heads) == 1, f"Expected exactly one head revision, found {heads!r}"
```

- [ ] **Step 2: Run the tests to verify they pass against the now-reconciled chain**

```bash
uv run pytest apps/api/tests/test_migration_graph.py -v
```

Expected: all four tests pass (the original `test_repository_has_one_migration_base_and_one_head`, plus the two new ones). If Task 1/2 were not done correctly (e.g. duplicate id or broken chain), this must fail with a clear `AssertionError` naming the exact colliding files/ids.

- [ ] **Step 3: Prove the test actually catches the original collision**

Temporarily verify the test's failure mode by pointing it at a synthetic
duplicate (do this in a scratch directory, not the real `migrations/`
folder — do NOT modify real migration files for this check):

```bash
mkdir -p /tmp/claude-scratch-migration-check/versions
cp migrations/versions/0001_establish_platform_database_foundation.py /tmp/claude-scratch-migration-check/versions/0001_a.py
cp migrations/versions/0001_establish_platform_database_foundation.py /tmp/claude-scratch-migration-check/versions/0001_b.py
uv run python -c "
from pathlib import Path
import importlib.util

versions_dir = Path('/tmp/claude-scratch-migration-check/versions')
revisions = {}
for path in sorted(versions_dir.glob('*.py')):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    revision = module.revision
    if revision in revisions:
        print('CAUGHT: duplicate', revision, 'in', path.name)
    revisions[revision] = path
"
rm -rf /tmp/claude-scratch-migration-check
```

Expected: prints `CAUGHT: duplicate 0001 ...`, confirming the detection logic
used inside the real test actually fires on a genuine collision.

---

### Task 4: Document the migration-id allocation convention

**Files:**
- Create: `docs/adr/ADR-003-migration-revision-allocation-convention.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: a durable convention future product branches must follow; referenced by commit message in Task 5.

- [ ] **Step 1: Write the ADR**

```markdown
# ADR-003 — Migration revision allocation convention

## Status

Accepted.

## Context

`feat/forestry-dashboard-v1` and `feat/transelec-hosted-pilot-v1` were
developed in parallel git worktrees sharing the same repository. Each branch
independently added a migration with `revision = "0003"` and
`down_revision = "0002"`, since `0002` was each branch's own most recent head
at the time. Alembic's migration graph, and this repository's
`scripts/migration_check.py` / `apps/api/app/migration_graph.py`, require
exactly one base and one head. Two independently authored `"0003"` files are
either a hard load-time collision or, if somehow both loaded, two heads —
both invalid.

## Decision

Migration revision ids are a single, globally linear sequence
(`0001`, `0002`, `0003`, ...) shared across every product context, even though
product contexts remain domain-independent. The sequence encodes deployment
ordering only — it must never encode or imply a business dependency between
products.

Before starting a new migration on a feature branch:

1. Run `git log --all --oneline -- migrations/versions/` from a worktree with
   all relevant branches fetched, and inspect `migrations/versions/` on every
   active sibling worktree, to find the current highest allocated revision id.
2. Claim the next integer id for the new migration's `revision` value, and set
   `down_revision` to the highest id found in step 1.
3. When two branches turn out to have allocated the same id in parallel (as
   happened here), the branch integrating second renumbers only its own
   migration's revision header (`revision`, `down_revision`, filename) to the
   next free id after the other branch's migration. The table/column bodies
   of neither migration are rewritten — only the header changes.
4. `apps/api/tests/test_migration_graph.py` enforces, independently of
   Alembic's own graph construction, that revision ids are unique and form a
   single linear chain with exactly one base and one head. A future collision
   fails this test with the names of the exact colliding files.

## Consequences

Product branches remain free to develop schema in isolation; only the
integration branch (or whichever branch merges second) pays the small cost of
renumbering a migration header. No merge revision or multi-head graph is
introduced, so `scripts/migration_check.py`'s single-base/single-head
assumption continues to hold without modification. The regression test in
`apps/api/tests/test_migration_graph.py` makes a future silent collision
fail fast in CI rather than surfacing as a confusing Alembic runtime error.
```

- [ ] **Step 2: Run the doc-link checker**

```bash
python scripts/check_doc_links.py
```

Expected: no new broken links reported.

---

### Task 5: Full migration lifecycle verification and commit

**Files:** none new — verification only, then commit everything from Tasks 1–4.

- [ ] **Step 1: Start the dedicated test database**

```bash
make db-test-up
```

- [ ] **Step 2: Run the full migration lifecycle check**

```bash
make migration-check
```

Expected: `migration-check: all checks passed`, with the printed graph
showing `bases: ['0001']` and `heads: ['0004']`.

- [ ] **Step 3: Run the persistence integration tests**

```bash
make persistence-check
```

Expected: all integration tests pass (these exercise `platform.source_*`
tables only — Forestry's `forestry.*` and Transelec's `platform.transelec_*`
tables are structurally created/dropped by `migration-check` but have no
dedicated integration tests in this worktree, since their test suites live on
their own product branches).

- [ ] **Step 4: Run the full local test/lint/type/architecture gate**

```bash
make check
```

Expected: passes. If `ruff format` reformats the two copied migration files
or the edited test file, re-run `make check` once more and inspect the diff
to confirm no semantic change was introduced (only formatting).

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0003_establish_forestry_source_substrate.py \
        migrations/versions/0004_establish_transelec_hosted_snapshots.py \
        apps/api/tests/test_migration_graph.py \
        docs/adr/ADR-003-migration-revision-allocation-convention.md \
        docs/superpowers/plans/2026-09-01-migration-reconciliation.md
git commit -m "$(cat <<'EOF'
fix: reconcile Campo Digital migration graph for product integration

Forestry and Transelec each independently allocated revision "0003" on
separate branches. Bring both into a single linear chain
(0001 -> 0002 -> 0003 forestry -> 0004 transelec) without altering either
product's table definitions, and add a regression test that fails fast on
a future duplicate-revision collision.
EOF
)"
```

- [ ] **Step 6: Verify the commit**

```bash
git log -1 --stat
git status --porcelain
```

Expected: clean working tree, one new commit on
`feat/platform-ingestion-access-v1`.
