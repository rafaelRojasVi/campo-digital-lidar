"""Tests for scripts/lidar_dev.py's adopt-vs-start decisions.

Process spawning and HTTP waits are monkeypatched at the module level so
these tests run fast and never start a real uvicorn/vite process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import lidar_dev
from scripts._local_process import ManagedProcess

from lidar_io.output_root_discovery import ReportRootResolution


def test_start_api_adopts_an_already_running_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = ManagedProcess(name="api", pid=123, port=8000, marker="m")

    monkeypatch.setattr(lidar_dev, "load_process", lambda _dir, _name: existing)
    monkeypatch.setattr(lidar_dev, "is_ours", lambda _p: True)

    def fail_if_spawned(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not spawn a new API when one is already running")

    monkeypatch.setattr(lidar_dev, "spawn", fail_if_spawned)

    def fail_if_db_checked() -> None:
        raise AssertionError("must not touch the database when adopting an existing process")

    monkeypatch.setattr(lidar_dev, "ensure_platform_database_ready", fail_if_db_checked)

    port, pid = lidar_dev.start_api()

    assert (port, pid) == (8000, 123)


def test_start_api_spawns_a_new_process_when_none_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lidar_dev, "load_process", lambda _dir, _name: None)
    monkeypatch.setattr(lidar_dev, "find_free_port", lambda _preferred: 8123)
    monkeypatch.setattr(lidar_dev, "ensure_platform_database_ready", lambda: None)

    spawned = ManagedProcess(name="api", pid=555, port=8123, marker="m")
    monkeypatch.setattr(lidar_dev, "spawn", lambda *a, **k: spawned)
    monkeypatch.setattr(lidar_dev, "wait_for_http", lambda _url, _timeout: True)

    port, pid = lidar_dev.start_api()

    assert (port, pid) == (8123, 555)


def test_start_api_raises_when_it_never_becomes_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lidar_dev, "load_process", lambda _dir, _name: None)
    monkeypatch.setattr(lidar_dev, "find_free_port", lambda _preferred: 8123)
    monkeypatch.setattr(lidar_dev, "ensure_platform_database_ready", lambda: None)
    monkeypatch.setattr(lidar_dev, "spawn", lambda *a, **k: ManagedProcess("api", 555, 8123, "m"))
    monkeypatch.setattr(lidar_dev, "wait_for_http", lambda _url, _timeout: False)

    with pytest.raises(lidar_dev.LauncherError):
        lidar_dev.start_api()


def test_start_api_raises_when_database_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lidar_dev, "load_process", lambda _dir, _name: None)

    def raise_db_error() -> None:
        raise lidar_dev.PlatformDatabaseError("db not ready")

    monkeypatch.setattr(lidar_dev, "ensure_platform_database_ready", raise_db_error)

    def fail_if_spawned(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not spawn the API when the database is not ready")

    monkeypatch.setattr(lidar_dev, "spawn", fail_if_spawned)

    with pytest.raises(lidar_dev.LauncherError, match="db not ready"):
        lidar_dev.start_api()


def test_command_stop_stops_both_recorded_processes_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    def fake_stop(_dir: object, name: str) -> str:
        order.append(name)
        return f"stopped {name}"

    monkeypatch.setattr(lidar_dev, "stop_process", fake_stop)

    assert lidar_dev.command_stop() == 0
    assert order == ["viewer", "api"]


# ------------------------------------------------------------- measurement_status


def test_measurement_status_reports_count_and_human_readable_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_root = tmp_path / "reports" / "out"
    output_root.mkdir(parents=True)

    monkeypatch.setattr(
        lidar_dev,
        "resolve_report_root",
        lambda repo_root, *, env_value: ReportRootResolution(output_root, "discovered-worktree"),
    )
    monkeypatch.setattr(lidar_dev, "discover_measurement_paths", lambda _root: [1, 2, 3])

    count, source_label, path = lidar_dev.measurement_status()

    assert count == 3
    assert source_label == "discovered local report store"
    assert path == output_root


def test_measurement_status_reports_zero_when_nothing_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_root = tmp_path / "reports" / "out"

    monkeypatch.setattr(
        lidar_dev,
        "resolve_report_root",
        lambda repo_root, *, env_value: ReportRootResolution(output_root, "none"),
    )
    monkeypatch.setattr(lidar_dev, "discover_measurement_paths", lambda _root: [])

    count, source_label, path = lidar_dev.measurement_status()

    assert count == 0
    assert source_label == "none found"
    assert path == output_root


# ------------------------------------------------------------- command_status


def test_command_status_distinguishes_service_state_from_data_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(lidar_dev, "load_process", lambda _dir, _name: None)
    monkeypatch.setattr(
        lidar_dev, "measurement_status", lambda: (14, "discovered local report store", Path("/x"))
    )

    assert lidar_dev.command_status() == 0

    out = capsys.readouterr().out
    assert "LiDAR API" in out
    assert "Viewer" in out
    assert "Persisted measurements: 14" in out
    assert "Report source: discovered local report store" in out
