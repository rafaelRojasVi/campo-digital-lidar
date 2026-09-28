from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.migration_graph import inspect_migration_graph


def test_repository_has_one_migration_base_and_one_head() -> None:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    graph = inspect_migration_graph(script)

    assert len(graph.bases) == 1
    assert len(graph.heads) == 1
    assert graph.has_single_base_and_head


def _load_migration_module(path: Path) -> ModuleType:
    """Load a migration file as a standalone module, without Alembic."""

    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_all_migrations(root: Path) -> dict[str, tuple[str | None, Path]]:
    """Map each declared revision id to its down_revision and source file.

    Raises AssertionError naming both colliding files if two migration files
    declare the same revision id. This runs independently of Alembic's own
    ScriptDirectory construction, which may otherwise surface a collision as
    an opaque multi-heads or duplicate-revision error.
    """

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

    down_revisions = [down for down, _ in revisions.values() if down is not None]
    all_targets = set(revisions)
    dangling = set(down_revisions) - all_targets
    assert not dangling, f"down_revision references missing revisions: {dangling!r}"

    assert len(down_revisions) == len(set(down_revisions)), (
        "More than one migration shares the same down_revision — "
        "this is a branch, not a linear chain."
    )

    heads = all_targets - set(down_revisions)
    assert len(heads) == 1, f"Expected exactly one head revision, found {heads!r}"


def test_migration_0008_extends_0007() -> None:
    """Pin the chain through 0008 specifically.

    0008 (transelec_import / transelec_resumen_row / transelec_publish_event)
    must extend 0007 directly -- it does not fork off an earlier revision.
    """

    root = Path(__file__).resolve().parents[3]
    revisions = _load_all_migrations(root)

    assert "0008" in revisions, "Expected migration 0008 to be present."
    down_revision, _ = revisions["0008"]
    assert down_revision == "0007"


def test_migration_0009_extends_0008_as_the_single_head() -> None:
    """0009 (Transelec AEF fields + mapping report) extends 0008 directly."""

    root = Path(__file__).resolve().parents[3]
    revisions = _load_all_migrations(root)

    assert "0009" in revisions, "Expected migration 0009 to be present."
    down_revision, _ = revisions["0009"]
    assert down_revision == "0008"

    down_revisions = {down for down, _ in revisions.values() if down is not None}
    heads = set(revisions) - down_revisions
    assert heads == {"0009"}
