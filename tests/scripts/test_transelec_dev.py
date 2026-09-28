"""Tests for scripts/transelec_dev.py's adopt-vs-start decisions.

Process spawning and HTTP waits are monkeypatched at the module level so
these tests run fast and never start a real uvicorn/vite process.
"""

from __future__ import annotations

import pytest
from scripts import transelec_dev
from scripts._local_process import ManagedProcess


def test_start_api_adopts_the_shared_api_if_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = ManagedProcess(name="api", pid=123, port=8000, marker="m")

    monkeypatch.setattr(transelec_dev, "load_process", lambda _dir, _name: existing)
    monkeypatch.setattr(transelec_dev, "is_ours", lambda _p: True)

    def fail_if_spawned(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not spawn a new API when one is already running")

    monkeypatch.setattr(transelec_dev, "spawn", fail_if_spawned)

    def fail_if_db_checked() -> None:
        raise AssertionError("must not touch the database when adopting an existing process")

    monkeypatch.setattr(transelec_dev, "ensure_platform_database_ready", fail_if_db_checked)

    port, pid = transelec_dev.start_api()

    assert (port, pid) == (8000, 123)


def test_start_api_spawns_a_new_shared_api_when_none_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transelec_dev, "load_process", lambda _dir, _name: None)
    monkeypatch.setattr(transelec_dev, "find_free_port", lambda _preferred: 8123)
    monkeypatch.setattr(transelec_dev, "ensure_platform_database_ready", lambda: None)

    spawned = ManagedProcess(name="api", pid=555, port=8123, marker="m")
    spawn_calls: list[tuple[object, ...]] = []

    def fake_spawn(*args: object, **kwargs: object) -> ManagedProcess:
        spawn_calls.append(args)
        return spawned

    monkeypatch.setattr(transelec_dev, "spawn", fake_spawn)
    monkeypatch.setattr(transelec_dev, "wait_for_http", lambda _url, _timeout: True)

    port, pid = transelec_dev.start_api()

    assert (port, pid) == (8123, 555)
    # Written under the SAME shared state dir lidar_dev.py/platform_local.py
    # use, so any of those launchers correctly adopts this instance too.
    assert spawn_calls[0][0] == transelec_dev.SHARED_API_STATE_DIR


def test_start_api_raises_when_it_never_becomes_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transelec_dev, "load_process", lambda _dir, _name: None)
    monkeypatch.setattr(transelec_dev, "find_free_port", lambda _preferred: 8123)
    monkeypatch.setattr(transelec_dev, "ensure_platform_database_ready", lambda: None)
    monkeypatch.setattr(
        transelec_dev, "spawn", lambda *a, **k: ManagedProcess("api", 555, 8123, "m")
    )
    monkeypatch.setattr(transelec_dev, "wait_for_http", lambda _url, _timeout: False)

    with pytest.raises(transelec_dev.LauncherError):
        transelec_dev.start_api()


def test_start_api_raises_when_database_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transelec_dev, "load_process", lambda _dir, _name: None)

    def raise_db_error() -> None:
        raise transelec_dev.PlatformDatabaseError("db not ready")

    monkeypatch.setattr(transelec_dev, "ensure_platform_database_ready", raise_db_error)

    def fail_if_spawned(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not spawn the API when the database is not ready")

    monkeypatch.setattr(transelec_dev, "spawn", fail_if_spawned)

    with pytest.raises(transelec_dev.LauncherError, match="db not ready"):
        transelec_dev.start_api()


def test_start_frontend_adopts_an_already_running_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = ManagedProcess(name="frontend", pid=321, port=5200, marker="m")

    monkeypatch.setattr(transelec_dev, "load_process", lambda _dir, _name: existing)
    monkeypatch.setattr(transelec_dev, "is_ours", lambda _p: True)

    def fail_if_spawned(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not spawn a new dashboard when one is already running")

    monkeypatch.setattr(transelec_dev, "spawn", fail_if_spawned)

    port, pid = transelec_dev.start_frontend(api_port=8000)

    assert (port, pid) == (5200, 321)


def test_start_frontend_passes_the_resolved_api_port_to_the_dashboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transelec_dev, "load_process", lambda _dir, _name: None)
    monkeypatch.setattr(transelec_dev, "ensure_frontend_dependencies", lambda: None)
    monkeypatch.setattr(transelec_dev, "find_free_port", lambda _preferred: 5299)
    monkeypatch.setattr(transelec_dev, "wait_for_http", lambda _url, _timeout: True)

    captured_env: dict[str, str] = {}

    def fake_spawn(state_dir, name, command, cwd, port, marker, env):  # noqa: ANN001
        captured_env.update(env)
        return ManagedProcess(name=name, pid=777, port=port, marker=marker)

    monkeypatch.setattr(transelec_dev, "spawn", fake_spawn)

    port, pid = transelec_dev.start_frontend(api_port=8123)

    assert (port, pid) == (5299, 777)
    assert captured_env["CAMPO_PLATFORM_API_PORT"] == "8123"


def test_command_stop_only_stops_the_frontend_and_leaves_the_shared_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped: list[tuple[object, str]] = []

    def fake_stop(state_dir: object, name: str) -> str:
        stopped.append((state_dir, name))
        return f"stopped {name}"

    monkeypatch.setattr(transelec_dev, "stop_process", fake_stop)

    assert transelec_dev.command_stop() == 0
    # Exactly one stop call, and it must never touch the shared API's state
    # dir — another module (or another transelec-dev session) may still
    # depend on that process.
    assert stopped == [(transelec_dev.STATE_DIR, "frontend")]
