"""Tests that the LiDAR API's output-root dependency delegates to automatic
local report-store discovery, instead of hard-coding a path or an env
fallback inline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.routers import lidar as lidar_router  # noqa: E402

from lidar_io.output_root_discovery import (  # noqa: E402
    SOURCE_DISCOVERED_WORKTREE,
    ReportRootResolution,
)


def test_get_output_root_delegates_to_resolve_report_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_resolve_report_root(
        repo_root: Path,
        *,
        env_value: str | None,
        worktree_paths: list[Path] | None = None,
        app_env: str = "development",
    ) -> ReportRootResolution:
        captured["repo_root"] = repo_root
        captured["env_value"] = env_value
        captured["app_env"] = app_env
        return ReportRootResolution(
            tmp_path / "resolved",
            SOURCE_DISCOVERED_WORKTREE,
        )

    monkeypatch.setattr(lidar_router, "resolve_report_root", fake_resolve_report_root)
    monkeypatch.delenv("CAMPO_LIDAR_OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    result = lidar_router.get_output_root()

    assert result == tmp_path / "resolved"
    assert captured["repo_root"] == lidar_router.REPO_ROOT
    assert captured["env_value"] is None
    assert captured["app_env"] == "development"


@pytest.mark.parametrize("app_env", ["staging", "production", "test"])
def test_get_output_root_passes_through_app_env(
    app_env: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_resolve_report_root(
        repo_root: Path,
        *,
        env_value: str | None,
        worktree_paths: list[Path] | None = None,
        app_env: str = "development",
    ) -> ReportRootResolution:
        captured["app_env"] = app_env
        return ReportRootResolution(tmp_path / "resolved", SOURCE_DISCOVERED_WORKTREE)

    monkeypatch.setattr(lidar_router, "resolve_report_root", fake_resolve_report_root)
    monkeypatch.delenv("CAMPO_LIDAR_OUTPUT_ROOT", raising=False)
    monkeypatch.setenv("APP_ENV", app_env)

    lidar_router.get_output_root()

    assert captured["app_env"] == app_env


def test_get_output_root_passes_through_explicit_env_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit = tmp_path / "explicit-does-not-need-to-exist"
    monkeypatch.setenv("CAMPO_LIDAR_OUTPUT_ROOT", str(explicit))

    result = lidar_router.get_output_root()

    assert result == explicit


def test_repo_root_points_at_the_actual_repository_root() -> None:
    assert (lidar_router.REPO_ROOT / "products" / "lidar").is_dir()
    assert (lidar_router.REPO_ROOT / "apps" / "api").is_dir()


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_production_list_runs_ignores_real_sibling_worktree_data(
    app_env: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end regression for the QA finding: with no
    ``CAMPO_LIDAR_OUTPUT_ROOT``, a staging/production process must return the
    zero-data state from ``/runs`` even though a sibling worktree genuinely
    holds API-visible measurement data on disk, and it must not touch that
    sibling data at all.

    Exercises the real (non-monkeypatched) ``resolve_report_root`` and
    ``list_runs`` through ``get_output_root`` — the exact call chain QA
    exercised — not a stubbed-out double.
    """

    from lidar_core.models import MeasurementRun, MeasurementRunStatus
    from lidar_io.run_store import write_measurement_run

    current_repo = tmp_path / "current"
    sibling_repo = tmp_path / "sibling"
    sibling_reports = sibling_repo / "products" / "lidar" / "reports" / "out"

    write_measurement_run(
        MeasurementRun(
            run_id="run-sibling",
            source_path="/private/source/example.las",
            status=MeasurementRunStatus.COMPLETED,
        ),
        sibling_reports,
    )
    marker = sibling_reports / "run-sibling" / "measurement.json"
    before_bytes = marker.read_bytes()
    before_mtime = marker.stat().st_mtime_ns

    monkeypatch.setattr(lidar_router, "REPO_ROOT", current_repo)
    monkeypatch.delenv("CAMPO_LIDAR_OUTPUT_ROOT", raising=False)
    monkeypatch.setenv("APP_ENV", app_env)

    output_root = lidar_router.get_output_root()
    runs = lidar_router.list_runs(output_root)

    assert runs == []
    assert marker.read_bytes() == before_bytes
    assert marker.stat().st_mtime_ns == before_mtime
