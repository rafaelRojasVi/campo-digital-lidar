"""Tests for app.dashboard_static against a standalone FastAPI app, so they
control the dist directories without a database or a session."""

from __future__ import annotations

import re
from pathlib import Path

from app.dashboard_static import PrefixedDashboard, mount_dashboards
from fastapi import FastAPI
from fastapi.testclient import TestClient

TRANSELEC_PAGES = frozenset({"transelec", "transelec/pendientes"})
RESERVED = frozenset({"api", "health", "transelec"})


def _build(tmp_path: Path, name: str, marker: str) -> Path:
    dist = tmp_path / name
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(f"<html><body>{marker}</body></html>")
    # Both builds emit the same hashed name on purpose.
    (dist / "assets" / "index-abc123.js").write_text(f"console.log('{marker}')")
    return dist


def _client(tmp_path: Path, *, portal: bool = True, transelec: bool = True) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    prefixed = (
        [
            PrefixedDashboard(
                "transelec", _build(tmp_path, "transelec", "transelec shell"), TRANSELEC_PAGES
            )
        ]
        if transelec
        else []
    )
    mount_dashboards(
        app,
        root_dist=_build(tmp_path, "portal", "portal shell") if portal else None,
        prefixed=prefixed,
        reserved_root_segments=RESERVED,
    )
    return TestClient(app)


def test_no_dist_at_all_registers_nothing(tmp_path: Path) -> None:
    client = _client(tmp_path, portal=False, transelec=False)
    assert client.get("/").status_code == 404


def test_root_serves_the_portal(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/")
    assert response.status_code == 200
    assert "portal shell" in response.text


def test_unknown_top_level_path_falls_back_to_the_portal(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for path in ("/rodales", "/rodales/mapa", "/cualquier-cosa"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "portal shell" in response.text, path


def test_transelec_pages_serve_the_transelec_shell_with_or_without_trailing_slash(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    for path in ("/transelec", "/transelec/", "/transelec/pendientes", "/transelec/pendientes/"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "transelec shell" in response.text, path


def test_each_build_serves_its_own_asset_with_the_same_name(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert "portal shell" in client.get("/assets/index-abc123.js").text
    assert "transelec shell" in client.get("/transelec/assets/index-abc123.js").text


def test_unknown_path_under_transelec_is_a_404_not_a_shell(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/transelec/does-not-exist")
    assert response.status_code == 404
    assert "shell" not in response.text


def test_reserved_segments_404_instead_of_the_portal(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/ping").json() == {"ok": "yes"}
    assert client.get("/api/no-such-route").status_code == 404
    assert client.get("/health/anything").status_code == 404


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/transelec/..%2F..%2Fportal%2Findex.html").status_code == 404


def test_transelec_only_still_serves_transelec(tmp_path: Path) -> None:
    client = _client(tmp_path, portal=False)
    assert "transelec shell" in client.get("/transelec").text
    assert client.get("/").status_code == 404


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
