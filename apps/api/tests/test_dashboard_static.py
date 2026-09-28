"""Tests for app.dashboard_static, exercised against a standalone FastAPI
app rather than the real app.main:app, so these tests can freely control
CAMPO_TRANSELEC_DASHBOARD_DIST without needing a database or a session.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.dashboard_static import mount_dashboard
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_dist(tmp_path: Path) -> Path:
    dist_dir = tmp_path / "dist"
    (dist_dir / "assets").mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html><body>dashboard shell</body></html>")
    (dist_dir / "assets" / "index-abc123.js").write_text("console.log('app')")
    return dist_dir


def test_mount_dashboard_is_a_no_op_when_no_dist_directory_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CAMPO_TRANSELEC_DASHBOARD_DIST", str(tmp_path / "does-not-exist"))

    app = FastAPI()
    mount_dashboard(app, reserved_root_segments=frozenset())

    client = TestClient(app)
    response = client.get("/")

    # No catch-all was registered, so FastAPI's own default 404 applies.
    assert response.status_code == 404


def test_mount_dashboard_serves_index_html_at_the_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = _build_dist(tmp_path)
    monkeypatch.setenv("CAMPO_TRANSELEC_DASHBOARD_DIST", str(dist_dir))

    app = FastAPI()
    mount_dashboard(app, reserved_root_segments=frozenset())

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "dashboard shell" in response.text


def test_mount_dashboard_falls_back_to_index_html_for_an_spa_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = _build_dist(tmp_path)
    monkeypatch.setenv("CAMPO_TRANSELEC_DASHBOARD_DIST", str(dist_dir))

    app = FastAPI()
    mount_dashboard(
        app,
        reserved_root_segments=frozenset({"health", "widgets"}),
        spa_page_paths=frozenset({"widgets/detail"}),
    )

    # /widgets/detail is a client-side route, not a build file, and its
    # first segment is NOT reserved here — the SPA fallback serves index.html
    # for it either way, independent of spa_page_paths.
    response = TestClient(app).get("/widgets/detail")

    assert response.status_code == 200
    assert "dashboard shell" in response.text


def test_mount_dashboard_serves_spa_page_paths_despite_a_reserved_first_segment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression test for a real bug found in manual browser QA: the
    Transelec dashboard's own page routes (/transelec, /transelec/importar,
    /transelec/versiones — see ROUTES in the dashboard's src/router.tsx)
    share their first path segment with the real /transelec/* API prefix,
    which is a reserved backend segment. Before spa_page_paths existed, a
    hard navigation or browser refresh on any of those pages 404'd instead
    of loading the app, because the reserved-segment check ran unconditionally.
    """

    dist_dir = _build_dist(tmp_path)
    monkeypatch.setenv("CAMPO_TRANSELEC_DASHBOARD_DIST", str(dist_dir))

    app = FastAPI()
    mount_dashboard(
        app,
        reserved_root_segments=frozenset({"transelec"}),
        spa_page_paths=frozenset({"transelec", "transelec/importar", "transelec/versiones"}),
    )

    client = TestClient(app)

    for path in ("/transelec", "/transelec/importar", "/transelec/versiones"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "dashboard shell" in response.text, path

    # An unmatched path under the same reserved segment that is NOT one of
    # the frontend's known page paths must still 404, not silently serve HTML.
    still_reserved = client.get("/transelec/does-not-exist")
    assert still_reserved.status_code == 404
    assert "dashboard shell" not in still_reserved.text


def test_mount_dashboard_serves_a_real_build_asset_verbatim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = _build_dist(tmp_path)
    monkeypatch.setenv("CAMPO_TRANSELEC_DASHBOARD_DIST", str(dist_dir))

    app = FastAPI()
    mount_dashboard(app, reserved_root_segments=frozenset())

    response = TestClient(app).get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert "console.log" in response.text


def test_mount_dashboard_returns_404_for_a_reserved_backend_segment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A path whose first segment belongs to a real router (e.g. an
    unmatched /transelec/... call) must 404, never silently serve the SPA
    shell — that would hide a real backend error behind a 200."""

    dist_dir = _build_dist(tmp_path)
    monkeypatch.setenv("CAMPO_TRANSELEC_DASHBOARD_DIST", str(dist_dir))

    app = FastAPI()
    mount_dashboard(app, reserved_root_segments=frozenset({"transelec"}))

    response = TestClient(app).get("/transelec/does-not-exist")

    assert response.status_code == 404
    assert "dashboard shell" not in response.text


def test_mount_dashboard_rejects_a_path_traversal_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = _build_dist(tmp_path)
    (tmp_path / "secret.txt").write_text("outside the dist directory")
    monkeypatch.setenv("CAMPO_TRANSELEC_DASHBOARD_DIST", str(dist_dir))

    app = FastAPI()
    mount_dashboard(app, reserved_root_segments=frozenset())

    response = TestClient(app).get("/../secret.txt")

    assert "outside the dist directory" not in response.text


def test_spa_page_paths_match_every_dashboard_route() -> None:
    """A dashboard route missing here 404s on reload or on a shared link."""

    from app.main import TRANSELEC_SPA_PAGE_PATHS

    router_source = (
        Path(__file__).resolve().parents[3]
        / "products"
        / "transelect"
        / "dashboard"
        / "src"
        / "router.tsx"
    ).read_text(encoding="utf-8")
    routes_block = router_source.split("export const ROUTES = {", 1)[1].split("} as const", 1)[0]
    dashboard_paths = {path.lstrip("/") for path in re.findall(r"'(/[^']*)'", routes_block)}

    assert dashboard_paths
    assert dashboard_paths == TRANSELEC_SPA_PAGE_PATHS
