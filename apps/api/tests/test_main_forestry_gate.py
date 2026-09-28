"""The forestry read API has no authentication yet, so ``app.main`` mounts it
only in ``development`` and CI's ``test``, never in the deployed staging and
production environments.

Runs ``app.main`` in a subprocess because ``APP_ENV`` is read at import time.
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
print(any(p.startswith("/api/forestry") for p in app.openapi()["paths"]))
"""


def _forestry_mounted(app_env: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT.format(api_root=str(API_ROOT))],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "APP_ENV": app_env},
        cwd=API_ROOT,
        check=True,
    )
    return result.stdout.strip() == "True"


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_undeployed_environments_mount_the_forestry_api(app_env: str) -> None:
    assert _forestry_mounted(app_env) is True


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_other_environments_do_not_mount_the_forestry_api(app_env: str) -> None:
    assert _forestry_mounted(app_env) is False
