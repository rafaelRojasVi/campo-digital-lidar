"""app.main must refuse to start under APP_ENV=production when Entra sign-in
is not fully configured -- "no way to authenticate anyone in production"
must fail closed at startup (app.identity_safety), not surface later as an
unexplained 503 on the first real sign-in attempt.

Runs each case in a subprocess (matching test_main_dev_auth_gate.py's
pattern): the check only matters at ASGI lifespan startup, which needs a
controlled, isolated process environment to vary APP_ENV/Entra settings
without leaking into the rest of this test run's process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]

_CHECK_SCRIPT = """
import sys
sys.path.insert(0, {api_root!r})
from app.main import app
from fastapi.testclient import TestClient
try:
    with TestClient(app):
        pass
except Exception as exc:
    print("LIFESPAN_FAILED=True")
    print("ERROR_TYPE=" + type(exc).__name__)
else:
    print("LIFESPAN_FAILED=False")
"""


def _run_with_env(extra_env: dict[str, str]) -> str:
    env: dict[str, str] = {"PATH": "/usr/bin:/bin", "APP_ENV": "production", **extra_env}

    result = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT.format(api_root=str(API_ROOT))],
        cwd=API_ROOT.parent.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_production_refuses_to_start_with_no_identity_configuration() -> None:
    output = _run_with_env({"POSTGRES_PASSWORD": "x"})

    assert "LIFESPAN_FAILED=True" in output
    assert "ProductionIdentityNotConfiguredError" in output


def test_production_starts_with_full_identity_configuration() -> None:
    output = _run_with_env(
        {
            "POSTGRES_PASSWORD": "x",
            "ENTRA_CLIENT_ID": "11111111-1111-1111-1111-111111111111",
            "ENTRA_CLIENT_SECRET": "fake-secret",
            "PLATFORM_TOKEN_ENCRYPTION_KEY": "fake-key",
        }
    )

    assert "LIFESPAN_FAILED=False" in output


def test_production_starts_with_google_sign_in_alone() -> None:
    # The Transelec hosted pilot's real shape: Google Workspace configured,
    # no Entra tenant in existence (see
    # docs/platform/entra-app-registration-handoff.md). This must start.
    output = _run_with_env(
        {
            "POSTGRES_PASSWORD": "x",
            "GOOGLE_CLIENT_ID": "1234567890-abcdef.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "fake-google-secret",
            "PLATFORM_TOKEN_ENCRYPTION_KEY": "fake-key",
        }
    )

    assert "LIFESPAN_FAILED=False" in output


def test_production_refuses_to_start_with_a_half_configured_google_client() -> None:
    output = _run_with_env(
        {
            "POSTGRES_PASSWORD": "x",
            "GOOGLE_CLIENT_ID": "1234567890-abcdef.apps.googleusercontent.com",
            "PLATFORM_TOKEN_ENCRYPTION_KEY": "fake-key",
        }
    )

    assert "LIFESPAN_FAILED=True" in output
    assert "ProductionIdentityNotConfiguredError" in output
