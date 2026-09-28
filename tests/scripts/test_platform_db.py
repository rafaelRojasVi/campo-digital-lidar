"""Tests for scripts/_platform_db.py's readiness/failure decisions.

subprocess and Alembic calls are monkeypatched so these tests run fast and
never touch a real Docker daemon or database.
"""

from __future__ import annotations

import subprocess

import pytest
from scripts import _platform_db


def test_ensure_platform_database_ready_raises_on_compose_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(_platform_db.subprocess, "run", lambda *a, **k: failed)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not attempt migrations when postgres never came up")

    monkeypatch.setattr(_platform_db.command, "upgrade", fail_if_called)

    with pytest.raises(_platform_db.PlatformDatabaseError, match="postgres"):
        _platform_db.ensure_platform_database_ready()


def test_ensure_platform_database_ready_raises_on_migration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    succeeded = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(_platform_db.subprocess, "run", lambda *a, **k: succeeded)

    def raise_upgrade_error(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("migration exploded")

    monkeypatch.setattr(_platform_db.command, "upgrade", raise_upgrade_error)

    with pytest.raises(_platform_db.PlatformDatabaseError, match="migrations"):
        _platform_db.ensure_platform_database_ready()


def test_ensure_platform_database_ready_succeeds_when_both_steps_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    succeeded = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(_platform_db.subprocess, "run", lambda *a, **k: succeeded)

    calls: list[str] = []
    monkeypatch.setattr(_platform_db.command, "upgrade", lambda *a, **k: calls.append("upgraded"))

    _platform_db.ensure_platform_database_ready()

    assert calls == ["upgraded"]
