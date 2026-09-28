"""Tests for automatic local discovery of the LiDAR measurement report store.

``products/lidar/reports/out`` is gitignored per-worktree local state: each
git worktree checked out from this repository has its own copy, and only one
of them may actually hold locally persisted measurement runs. These tests
cover the precedence rules for finding a usable report store without the
developer having to set ``CAMPO_LIDAR_OUTPUT_ROOT`` by hand, and without ever
mutating report data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lidar_core.models import MeasurementRun, MeasurementRunStatus
from lidar_io import output_root_discovery
from lidar_io.output_root_discovery import (
    SOURCE_CURRENT_WORKTREE,
    SOURCE_DISCOVERED_WORKTREE,
    SOURCE_DISCOVERY_DISABLED,
    SOURCE_ENV,
    SOURCE_NONE,
    has_visible_measurements,
    parse_worktree_paths,
    resolve_report_root,
)
from lidar_io.run_store import write_measurement_run

SAMPLE_PORCELAIN = """\
worktree /home/user/campo-digital-platform
HEAD 9ba8b3615aa1f55e419c8ca891c9be11a55cb1c1
branch refs/heads/main

worktree /home/user/campo-digital-platform-portal-v1
HEAD 224f3b8
branch refs/heads/feat/platform-portal-v1

worktree /home/user/campo-digital-detached-scratch
HEAD 0000000000000000000000000000000000000000
detached
"""


def _write_run(output_root: Path, run_id: str = "run-001") -> None:
    write_measurement_run(
        MeasurementRun(
            run_id=run_id,
            source_path="/private/source/example.las",
            status=MeasurementRunStatus.COMPLETED,
        ),
        output_root,
    )


# ------------------------------------------------------------- parsing


def test_parse_worktree_paths_extracts_every_worktree() -> None:
    paths = parse_worktree_paths(SAMPLE_PORCELAIN)

    assert paths == [
        Path("/home/user/campo-digital-platform"),
        Path("/home/user/campo-digital-platform-portal-v1"),
        Path("/home/user/campo-digital-detached-scratch"),
    ]


def test_parse_worktree_paths_handles_empty_input() -> None:
    assert parse_worktree_paths("") == []


# ------------------------------------------------------- has_visible_measurements


def test_has_visible_measurements_true_for_direct_run(tmp_path: Path) -> None:
    _write_run(tmp_path)

    assert has_visible_measurements(tmp_path) is True


def test_has_visible_measurements_false_for_empty_directory(tmp_path: Path) -> None:
    assert has_visible_measurements(tmp_path) is False


def test_has_visible_measurements_false_for_missing_directory(tmp_path: Path) -> None:
    assert has_visible_measurements(tmp_path / "does-not-exist") is False


def test_has_visible_measurements_ignores_nested_only_runs(tmp_path: Path) -> None:
    """A ``measurement.json`` nested more than one level below the root does
    not satisfy the API's ``glob("*/measurement.json")`` discovery contract,
    so it must not make a candidate look valid either."""

    _write_run(tmp_path / "measurements" / "nested", run_id="run-nested")

    assert has_visible_measurements(tmp_path) is False


# ------------------------------------------------------------- resolve_report_root


def test_explicit_env_value_always_wins(tmp_path: Path) -> None:
    sibling = tmp_path / "sibling"
    _write_run(sibling)

    explicit = tmp_path / "explicit-empty-override"

    resolution = resolve_report_root(
        tmp_path / "current",
        env_value=str(explicit),
        worktree_paths=[tmp_path / "current", sibling.parent],
    )

    assert resolution.path == explicit
    assert resolution.source == SOURCE_ENV


def test_current_worktree_wins_when_it_already_has_valid_data(tmp_path: Path) -> None:
    current_repo = tmp_path / "current"
    current_reports = current_repo / "products" / "lidar" / "reports" / "out"
    _write_run(current_reports)

    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"
    _write_run(sibling_reports, run_id="run-sibling")

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo, sibling_repo],
    )

    assert resolution.path == current_reports
    assert resolution.source == SOURCE_CURRENT_WORKTREE


def test_valid_sibling_worktree_is_discovered_when_current_is_empty(tmp_path: Path) -> None:
    current_repo = tmp_path / "current"

    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"
    _write_run(sibling_reports, run_id="run-sibling")

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo, sibling_repo],
    )

    assert resolution.path == sibling_reports
    assert resolution.source == SOURCE_DISCOVERED_WORKTREE


def test_empty_current_worktree_loses_to_valid_sibling_even_when_current_dir_exists(
    tmp_path: Path,
) -> None:
    current_repo = tmp_path / "current"
    current_reports = current_repo / "products" / "lidar" / "reports" / "out"
    current_reports.mkdir(parents=True)

    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"
    _write_run(sibling_reports, run_id="run-sibling")

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo, sibling_repo],
    )

    assert resolution.path == sibling_reports
    assert resolution.source == SOURCE_DISCOVERED_WORKTREE


def test_sibling_with_only_nested_runs_does_not_count_as_valid(tmp_path: Path) -> None:
    current_repo = tmp_path / "current"

    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"
    _write_run(sibling_reports / "measurements" / "nested", run_id="run-nested")

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo, sibling_repo],
    )

    current_reports = current_repo / "products" / "lidar" / "reports" / "out"
    assert resolution.path == current_reports
    assert resolution.source == SOURCE_NONE


def test_no_valid_candidate_anywhere_falls_back_to_current_worktree_clean_state(
    tmp_path: Path,
) -> None:
    current_repo = tmp_path / "current"
    sibling_repo = tmp_path / "sibling"

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo, sibling_repo],
    )

    assert resolution.path == current_repo / "products" / "lidar" / "reports" / "out"
    assert resolution.source == SOURCE_NONE


# ------------------------------------------------- app_env staging/production hardening


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_non_development_env_never_discovers_sibling_worktree_data(
    app_env: str, tmp_path: Path
) -> None:
    """QA regression: a hosted (staging/production) API process must not
    auto-discover LiDAR report data from sibling git worktrees, even when
    such data genuinely exists on disk."""

    current_repo = tmp_path / "current"

    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"
    _write_run(sibling_reports, run_id="run-sibling")

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo, sibling_repo],
        app_env=app_env,
    )

    current_reports = current_repo / "products" / "lidar" / "reports" / "out"
    assert resolution.path == current_reports
    assert resolution.source == SOURCE_DISCOVERY_DISABLED


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_non_development_env_never_trusts_own_worktree_data_either(
    app_env: str, tmp_path: Path
) -> None:
    """The invariant is not just "no siblings": with no explicit
    ``CAMPO_LIDAR_OUTPUT_ROOT``, staging/production must behave as if no
    local report store exists at all, even if the current worktree's own
    (gitignored) reports directory happens to contain data."""

    current_repo = tmp_path / "current"
    current_reports = current_repo / "products" / "lidar" / "reports" / "out"
    _write_run(current_reports, run_id="run-current")

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo],
        app_env=app_env,
    )

    assert resolution.path == current_reports
    assert resolution.source == SOURCE_DISCOVERY_DISABLED


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_non_development_env_never_shells_out_to_git_worktree_list(
    app_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even the read-only ``git worktree list`` probe itself must not run:
    inspecting sibling worktrees is disallowed, not just using their data."""

    def _fail_if_called(repo_root: Path) -> list[Path]:
        raise AssertionError("discover_worktree_paths must not be called outside development")

    monkeypatch.setattr(output_root_discovery, "discover_worktree_paths", _fail_if_called)

    resolution = resolve_report_root(
        tmp_path / "current",
        env_value=None,
        worktree_paths=None,
        app_env=app_env,
    )

    assert resolution.source == SOURCE_DISCOVERY_DISABLED


def test_non_development_env_still_honors_explicit_env_override(tmp_path: Path) -> None:
    """The one explicitly-configured hosted report source must still work in
    staging/production — only implicit discovery is restricted."""

    explicit = tmp_path / "hosted-report-source"
    _write_run(explicit)

    resolution = resolve_report_root(
        tmp_path / "current",
        env_value=str(explicit),
        worktree_paths=[tmp_path / "current"],
        app_env="production",
    )

    assert resolution.path == explicit
    assert resolution.source == SOURCE_ENV


def test_development_env_keeps_existing_sibling_discovery_behavior(tmp_path: Path) -> None:
    """Explicit non-regression check: the developer-convenience default
    (``app_env`` defaults to development) must remain exactly as before."""

    current_repo = tmp_path / "current"

    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"
    _write_run(sibling_reports, run_id="run-sibling")

    resolution = resolve_report_root(
        current_repo,
        env_value=None,
        worktree_paths=[current_repo, sibling_repo],
    )

    assert resolution.path == sibling_reports
    assert resolution.source == SOURCE_DISCOVERED_WORKTREE


def test_resolve_report_root_never_writes_or_touches_candidate_files(tmp_path: Path) -> None:
    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"
    _write_run(sibling_reports, run_id="run-sibling")

    marker = sibling_reports / "run-sibling" / "measurement.json"
    before = marker.read_bytes()
    before_mtime = marker.stat().st_mtime_ns

    resolve_report_root(
        tmp_path / "current",
        env_value=None,
        worktree_paths=[tmp_path / "current", sibling_repo],
    )

    assert marker.read_bytes() == before
    assert marker.stat().st_mtime_ns == before_mtime
    # No copies were made into the current (candidate-losing) worktree.
    assert not (tmp_path / "current").exists()
