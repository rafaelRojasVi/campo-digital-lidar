"""Tests for scripts/platform_local.py's collision guard.

DB readiness and process exec are monkeypatched so these tests run fast and
never touch Docker, a database, or replace the test process.
"""

from __future__ import annotations

import pytest
from scripts import platform_local
from scripts._local_process import ManagedProcess


def test_main_refuses_when_lidar_dev_owns_a_running_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running = ManagedProcess(name="api", pid=123, port=8000, marker="m")
    monkeypatch.setattr(platform_local, "load_process", lambda _dir, _name: running)
    monkeypatch.setattr(platform_local, "is_ours", lambda _p: True)

    def fail_if_called(*_a: object, **_k: object) -> None:
        raise AssertionError("must not touch the database when refusing to start")

    monkeypatch.setattr(platform_local, "ensure_platform_database_ready", fail_if_called)

    def fail_if_exec(*_a: object, **_k: object) -> None:
        raise AssertionError("must not exec uvicorn when refusing to start")

    monkeypatch.setattr(platform_local.os, "execvpe", fail_if_exec)

    assert platform_local.main() == 1


def test_main_reports_database_failure_without_execing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_local, "load_process", lambda _dir, _name: None)

    def raise_db_error() -> None:
        raise platform_local.PlatformDatabaseError("db not ready")

    monkeypatch.setattr(platform_local, "ensure_platform_database_ready", raise_db_error)

    def fail_if_exec(*_a: object, **_k: object) -> None:
        raise AssertionError("must not exec uvicorn when the database is not ready")

    monkeypatch.setattr(platform_local.os, "execvpe", fail_if_exec)

    assert platform_local.main() == 1


def test_main_execs_uvicorn_when_clear_and_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_local, "load_process", lambda _dir, _name: None)
    monkeypatch.setattr(platform_local, "ensure_platform_database_ready", lambda: None)

    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        platform_local.os,
        "execvpe",
        lambda program, args, env: calls.append((program, args)),
    )

    platform_local.main()

    assert len(calls) == 1
    program, args = calls[0]
    assert program == "uv"
    assert args[:3] == ["uv", "run", "uvicorn"]
    assert "app.main:app" in args
    assert "--reload" in args
