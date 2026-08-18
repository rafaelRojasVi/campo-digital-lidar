"""Subprocess-based wrapper around the PDAL CLI.

PDAL is treated as an OPTIONAL external dependency: at the time this repo
was bootstrapped, `pdal` was not installed on the host (`which pdal` found
nothing, and it was not in the apt-installed package list). All functions
here check availability gracefully and raise a clear `PdalNotAvailable`
error (or let callers skip) rather than assuming the binary exists.

See docs/tooling.md for the manual install command.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class PdalNotAvailable(RuntimeError):
    """Raised when a PDAL operation is requested but the `pdal` CLI is not on PATH."""


def pdal_available() -> bool:
    return shutil.which("pdal") is not None


def pdal_version() -> str | None:
    if not pdal_available():
        return None
    result = subprocess.run(["pdal", "--version"], capture_output=True, text=True, check=False)
    return result.stdout.strip() or result.stderr.strip()


def _require_pdal() -> None:
    if not pdal_available():
        raise PdalNotAvailable(
            "The 'pdal' CLI is not installed. Install it with:\n"
            "  sudo apt update && sudo apt install -y pdal libpdal-dev\n"
            "See docs/tooling.md for details."
        )


def validate_pipeline(pipeline_path: str | Path) -> tuple[bool, str]:
    """Runs `pdal pipeline --validate` on a pipeline JSON file.

    Returns (is_valid, message). Raises PdalNotAvailable if pdal is absent
    -- callers (e.g. tests) should check `pdal_available()` first and skip.
    """
    _require_pdal()
    result = subprocess.run(
        ["pdal", "pipeline", "--validate", str(pipeline_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    ok = result.returncode == 0
    message = result.stdout.strip() or result.stderr.strip()
    return ok, message


def run_pipeline(pipeline_path: str | Path) -> subprocess.CompletedProcess[str]:
    """Executes a PDAL pipeline JSON file via `pdal pipeline <file>`."""
    _require_pdal()
    return subprocess.run(
        ["pdal", "pipeline", str(pipeline_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def pdal_info(las_path: str | Path) -> dict[str, Any]:
    """Runs `pdal info --metadata <file>` and parses the JSON output."""
    _require_pdal()
    result = subprocess.run(
        ["pdal", "info", "--metadata", str(las_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed
