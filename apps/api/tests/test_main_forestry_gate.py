"""The forestry read API is mounted in every ``APP_ENV``, production included.

It was limited to ``development`` and ``test`` until every route required a
session and a ``forestry`` grant (``app.routers.forestry.require_forestry_viewer``;
see test_forestry_route_access.py). Runs ``app.main`` in a subprocess because
``APP_ENV`` is read at import time.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]

_CHECK_SCRIPT = """
import sys
sys.path.insert(0, {api_root!r})
from app.main import app
from app.routers.forestry import require_forestry_viewer, router
from app.routers.forestry_workflow import router as workflow_router
paths = [p for p in app.openapi()["paths"] if p.startswith("/api/forestry")]
guarded = all(
    require_forestry_viewer in {{d.dependency for d in r.dependencies}}
    for r in (router, workflow_router)
)
print(len(paths), guarded)
"""


@pytest.mark.parametrize("app_env", ["development", "test", "staging", "production"])
def test_every_environment_mounts_the_guarded_forestry_api(app_env: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT.format(api_root=str(API_ROOT))],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "APP_ENV": app_env},
        cwd=API_ROOT,
        check=True,
    )
    assert result.stdout.split() == ["14", "True"]
