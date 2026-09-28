"""Tests for scripts/campo_demo.py, the company-portal demo orchestrator.

These tests exercise the pure/testable seams: worktree discovery parsing,
branch matching, the adopt-vs-start-vs-unavailable decision, ownership
bookkeeping, and generated runtime config -- all without starting real
product processes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import campo_demo

# ------------------------------------------------------------- worktrees


SAMPLE_PORCELAIN = """\
worktree /home/user/campo-digital-platform
HEAD 9ba8b3615aa1f55e419c8ca891c9be11a55cb1c1
branch refs/heads/main

worktree /home/user/campo-digital-forestry-dashboard-v1
HEAD a46e87a7134d0441a7557eb8b6c5f6ec9668ab4b
branch refs/heads/feat/forestry-dashboard-v1

worktree /home/user/campo-digital-transelec-ui-parity-v1
HEAD adc61788fa9eec388de8149d60facfe4f9e7b050
branch refs/heads/feat/transelec-ui-reference-parity-v1

worktree /home/user/campo-digital-detached-scratch
HEAD 0000000000000000000000000000000000000000
detached
"""


def test_parse_worktree_porcelain_extracts_paths_and_branches() -> None:
    worktrees = campo_demo.parse_worktree_porcelain(SAMPLE_PORCELAIN)

    assert len(worktrees) == 4
    assert worktrees[0].path == Path("/home/user/campo-digital-platform")
    assert worktrees[0].branch == "main"
    assert worktrees[0].detached is False

    assert worktrees[1].branch == "feat/forestry-dashboard-v1"
    assert worktrees[2].branch == "feat/transelec-ui-reference-parity-v1"

    assert worktrees[3].branch is None
    assert worktrees[3].detached is True


def test_parse_worktree_porcelain_handles_empty_input() -> None:
    assert campo_demo.parse_worktree_porcelain("") == []


def test_find_worktree_for_branch_matches_exact_branch() -> None:
    worktrees = campo_demo.parse_worktree_porcelain(SAMPLE_PORCELAIN)

    found = campo_demo.find_worktree_for_branch(worktrees, "feat/forestry-dashboard-v1")

    assert found == Path("/home/user/campo-digital-forestry-dashboard-v1")


def test_find_worktree_for_branch_returns_none_when_absent() -> None:
    worktrees = campo_demo.parse_worktree_porcelain(SAMPLE_PORCELAIN)

    assert campo_demo.find_worktree_for_branch(worktrees, "feat/does-not-exist") is None


# ---------------------------------------------------------------- ensure_module


def test_ensure_module_adopts_an_already_running_module(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_probe(_worktree: Path | None) -> tuple[bool, str | None]:
        return True, "http://127.0.0.1:5175/"

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        calls.append("run_make_target")
        raise AssertionError("must not start a module that is already running")

    monkeypatch.setattr(campo_demo, "run_make_target", fail_if_called)

    result = campo_demo.ensure_module(
        "forestal", Path("/some/worktree"), fake_probe, Path("/some/worktree"), "forestry-dev"
    )

    assert result.status == "available"
    assert result.url == "http://127.0.0.1:5175/"
    assert result.owned is False
    assert calls == []


def test_ensure_module_reports_unavailable_when_worktree_is_missing() -> None:
    def never_running(_worktree: Path | None) -> tuple[bool, str | None]:
        return False, None

    result = campo_demo.ensure_module("forestal", None, never_running, None, "forestry-dev")

    assert result.status == "unavailable"
    assert result.owned is False
    assert result.url is None


def test_ensure_module_starts_and_confirms_a_new_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probe_calls: list[int] = []

    def probe(_worktree: Path | None) -> tuple[bool, str | None]:
        probe_calls.append(1)
        # Not running on the first probe, running after `run_make_target`.
        if len(probe_calls) == 1:
            return False, None
        return True, "http://127.0.0.1:5175/"

    started: list[tuple[Path, str]] = []

    def fake_run_make_target(cwd: Path, target: str, timeout: float = 240.0) -> None:
        started.append((cwd, target))

    monkeypatch.setattr(campo_demo, "run_make_target", fake_run_make_target)

    result = campo_demo.ensure_module("forestal", tmp_path, probe, tmp_path, "forestry-dev")

    assert started == [(tmp_path, "forestry-dev")]
    assert result.status == "available"
    assert result.owned is True
    assert result.url == "http://127.0.0.1:5175/"


def test_ensure_module_reports_unavailable_when_the_launcher_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def never_running(_worktree: Path | None) -> tuple[bool, str | None]:
        return False, None

    def failing_launcher(cwd: Path, target: str, timeout: float = 240.0) -> None:
        raise campo_demo.LauncherError("boom: docker not available")

    monkeypatch.setattr(campo_demo, "run_make_target", failing_launcher)

    result = campo_demo.ensure_module(
        "transelec", tmp_path, never_running, tmp_path, "transelec-dev"
    )

    assert result.status == "unavailable"
    assert result.owned is False
    assert "boom" in result.detail


def test_ensure_module_reports_unavailable_when_launcher_succeeds_but_probe_still_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def never_running(_worktree: Path | None) -> tuple[bool, str | None]:
        return False, None

    monkeypatch.setattr(campo_demo, "run_make_target", lambda *a, **k: None)

    result = campo_demo.ensure_module(
        "transelec", tmp_path, never_running, tmp_path, "transelec-dev"
    )

    assert result.status == "unavailable"
    assert result.owned is False


# ---------------------------------------------------------------------- probes


def test_probe_lidar_delegates_to_shared_process_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts._local_process import ManagedProcess

    process = ManagedProcess(name="viewer", pid=1, port=5174, marker="m")
    monkeypatch.setattr(campo_demo, "load_process", lambda _dir, _name: process)
    monkeypatch.setattr(campo_demo, "is_ours", lambda _p: True)
    monkeypatch.setattr(campo_demo, "wait_for_http", lambda _url, _timeout: True)

    running, url = campo_demo.probe_lidar(tmp_path)

    assert running is True
    assert url == "http://127.0.0.1:5174/"


def test_probe_lidar_false_when_recorded_process_is_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(campo_demo, "load_process", lambda _dir, _name: None)

    running, url = campo_demo.probe_lidar(tmp_path)

    assert running is False
    assert url is None


def test_probe_forestry_returns_false_without_a_worktree() -> None:
    assert campo_demo.probe_forestry(None) == (False, None)


def test_probe_transelec_delegates_to_shared_process_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Transelec's real dashboard now lives in this same worktree (see
    scripts/transelec_dev.py), so probing it mirrors probe_lidar exactly —
    no sibling-worktree lookup, unlike Forestry."""

    from scripts._local_process import ManagedProcess

    process = ManagedProcess(name="frontend", pid=1, port=5200, marker="m")
    monkeypatch.setattr(campo_demo, "load_process", lambda _dir, _name: process)
    monkeypatch.setattr(campo_demo, "is_ours", lambda _p: True)
    monkeypatch.setattr(campo_demo, "wait_for_http", lambda _url, _timeout: True)

    running, url = campo_demo.probe_transelec(tmp_path)

    assert running is True
    assert url == "http://127.0.0.1:5200/"


def test_probe_transelec_false_when_recorded_process_is_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(campo_demo, "load_process", lambda _dir, _name: None)

    running, url = campo_demo.probe_transelec(tmp_path)

    assert running is False
    assert url is None


# ------------------------------------------------------------- runtime config


def test_write_runtime_config_produces_a_stakeholder_safe_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    portal_root = tmp_path / "apps" / "portal"
    monkeypatch.setattr(campo_demo, "PORTAL_ROOT", portal_root)

    modules = {
        "lidar": campo_demo.ModuleResult("available", "http://127.0.0.1:5174/", True, "started"),
        "forestal": campo_demo.ModuleResult("unavailable", None, False, "missing worktree"),
        "transelec": campo_demo.ModuleResult(
            "available", "http://127.0.0.1:5180/", False, "adopted"
        ),
    }

    campo_demo.write_runtime_config(5100, modules)

    written = json.loads((portal_root / "public" / "campo-runtime.json").read_text())

    assert written["portal"]["port"] == 5100
    assert written["modules"]["lidar"] == {
        "status": "available",
        "url": "http://127.0.0.1:5174/",
        "owned": True,
    }
    assert written["modules"]["forestal"]["status"] == "unavailable"
    assert written["modules"]["forestal"]["url"] is None
    # Only status/url/owned are exposed -- no PIDs, log paths, or launcher detail.
    assert set(written["modules"]["lidar"].keys()) == {"status", "url", "owned"}


def test_write_runtime_config_includes_measurement_count_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    portal_root = tmp_path / "apps" / "portal"
    monkeypatch.setattr(campo_demo, "PORTAL_ROOT", portal_root)

    modules = {
        "lidar": campo_demo.ModuleResult(
            "available", "http://127.0.0.1:5174/", True, "started", measurement_count=14
        ),
        "forestal": campo_demo.ModuleResult("unavailable", None, False, "missing worktree"),
        "transelec": campo_demo.ModuleResult(
            "available", "http://127.0.0.1:5180/", False, "adopted"
        ),
    }

    campo_demo.write_runtime_config(5100, modules)

    written = json.loads((portal_root / "public" / "campo-runtime.json").read_text())

    assert written["modules"]["lidar"]["measurementCount"] == 14
    # No filesystem path is ever exposed to the stakeholder-facing portal.
    assert "path" not in written["modules"]["lidar"]
    assert "measurementCount" not in written["modules"]["forestal"]


# ---------------------------------------------------------- lidar measurement count


def test_lidar_measurement_count_delegates_to_output_root_discovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from lidar_io.output_root_discovery import ReportRootResolution

    output_root = tmp_path / "reports" / "out"

    monkeypatch.setattr(
        campo_demo,
        "resolve_report_root",
        lambda repo_root, *, env_value: ReportRootResolution(output_root, "discovered-worktree"),
    )
    monkeypatch.setattr(campo_demo, "discover_measurement_paths", lambda _root: [1, 2, 3, 4])

    assert campo_demo.lidar_measurement_count() == 4


def test_resolve_modules_attaches_measurement_count_only_to_lidar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(campo_demo, "discover_worktrees", lambda: [])
    monkeypatch.setattr(campo_demo, "find_worktree_for_branch", lambda _wt, _b: None)
    monkeypatch.setattr(campo_demo, "probe_lidar", lambda: (True, "http://127.0.0.1:5174/"))
    monkeypatch.setattr(campo_demo, "probe_transelec", lambda: (False, None))
    monkeypatch.setattr(campo_demo, "lidar_measurement_count", lambda: 14)

    modules = campo_demo.resolve_modules(read_only=True)

    assert modules["lidar"].measurement_count == 14
    assert modules["forestal"].measurement_count is None
    assert modules["transelec"].measurement_count is None


# -------------------------------------------------------------- ownership state


def test_ownership_state_round_trips_and_defaults_to_unowned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(campo_demo, "CAMPO_STATE_DIR", tmp_path)
    monkeypatch.setattr(campo_demo, "CAMPO_STATE_FILE", tmp_path / "state.json")

    assert campo_demo.load_ownership_state() == {
        "lidar_owned": False,
        "forestal_owned": False,
        "transelec_owned": False,
    }

    modules = {
        "lidar": campo_demo.ModuleResult("available", "http://x/", True, "started"),
        "forestal": campo_demo.ModuleResult("available", "http://y/", False, "adopted"),
        "transelec": campo_demo.ModuleResult("unavailable", None, False, "missing"),
    }
    campo_demo.save_ownership_state(modules)

    assert campo_demo.load_ownership_state() == {
        "lidar_owned": True,
        "forestal_owned": False,
        "transelec_owned": False,
    }


# ---------------------------------------------------------------- print_summary


def test_print_summary_reports_lidar_measurements_separately_from_availability(
    capsys: pytest.CaptureFixture[str],
) -> None:
    modules = {
        "lidar": campo_demo.ModuleResult(
            "available", "http://127.0.0.1:5174/", True, "started", measurement_count=14
        ),
        "forestal": campo_demo.ModuleResult("available", "http://127.0.0.1:5175/", True, "started"),
        "transelec": campo_demo.ModuleResult("unavailable", None, False, "missing worktree"),
    }

    campo_demo.print_summary(5100, modules)

    out = capsys.readouterr().out
    assert "LiDAR measurements: 14" in out


def test_print_summary_omits_lidar_measurements_line_when_count_is_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    modules = {
        "lidar": campo_demo.ModuleResult("unavailable", None, False, "missing worktree"),
        "forestal": campo_demo.ModuleResult("unavailable", None, False, "missing worktree"),
        "transelec": campo_demo.ModuleResult("unavailable", None, False, "missing worktree"),
    }

    campo_demo.print_summary(5100, modules)

    out = capsys.readouterr().out
    assert "LiDAR measurements" not in out
