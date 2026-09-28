"""Production must not publish the interactive API docs or the OpenAPI schema.

Swagger UI, ReDoc and ``/openapi.json`` describe every route, parameter and
model to anonymous callers. Production users only need the dashboard, so the
three are unmounted there and stay available in every other environment.

Runs ``app.main`` in a subprocess because ``APP_ENV`` is read at import time,
with a stub dashboard build mounted as in production, so the SPA catch-all
cannot answer those paths with ``index.html`` either.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

_CHECK_SCRIPT = """
import sys
sys.path.insert(0, {api_root!r})
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
for path in {docs_paths!r}:
    print(path + "=" + str(client.get(path).status_code))
"""


def _status_codes(app_env: str, dist_dir: Path) -> dict[str, int]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHECK_SCRIPT.format(api_root=str(API_ROOT), docs_paths=DOCS_PATHS),
        ],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "APP_ENV": app_env,
            "CAMPO_TRANSELEC_DASHBOARD_DIST": str(dist_dir),
        },
        cwd=API_ROOT,
        check=True,
    )
    codes: dict[str, int] = {}
    for line in result.stdout.splitlines():
        path, _, value = line.partition("=")
        codes[path] = int(value)
    return codes


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>dashboard shell</html>")
    return tmp_path


def test_production_does_not_serve_docs_or_schema(dist_dir: Path) -> None:
    assert _status_codes("production", dist_dir) == dict.fromkeys(DOCS_PATHS, 404)


@pytest.mark.parametrize("app_env", ["development", "test", "staging"])
def test_other_environments_keep_docs_and_schema(app_env: str, dist_dir: Path) -> None:
    assert _status_codes(app_env, dist_dir) == dict.fromkeys(DOCS_PATHS, 200)
