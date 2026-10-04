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
    assert tuple(spec.column for spec in RESUMEN_ROW_PROJECTION) == migration.ROW_COLUMNS


def test_migration_follows_0011() -> None:
    migration = _load()
    assert (migration.revision, migration.down_revision) == ("0012", "0011")
