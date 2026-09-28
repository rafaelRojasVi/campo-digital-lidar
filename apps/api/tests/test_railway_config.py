"""railway.json must build the Dockerfile and start through its entrypoint.

Railway replaces the image's ENTRYPOINT with any custom start command, and
the production service runs as root (RAILWAY_RUN_UID=0) so the entrypoint
can hand the volume to ``campo``. A start command that skipped the
entrypoint would therefore run the API as root. Pinning both in
config-as-code, which overrides the dashboard, keeps that from depending on
a dashboard field nobody can see from the repository.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _railway() -> dict[str, dict[str, str]]:
    return json.loads((REPO_ROOT / "railway.json").read_text(encoding="utf-8"))


def _dockerfile_json_instruction(name: str) -> list[str]:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(rf"^{name} (\[.*\])$", dockerfile, flags=re.MULTILINE)
    assert match, f"Dockerfile has no exec-form {name}"
    return list(json.loads(match.group(1)))


def test_railway_builds_the_repository_dockerfile() -> None:
    build = _railway()["build"]

    assert build["builder"] == "DOCKERFILE"
    assert build["dockerfilePath"] == "Dockerfile"


def test_railway_start_command_runs_through_the_image_entrypoint() -> None:
    argv = shlex.split(_railway()["deploy"]["startCommand"])

    assert argv[:1] == _dockerfile_json_instruction("ENTRYPOINT")


def test_railway_start_command_is_exactly_the_images_own_start() -> None:
    argv = shlex.split(_railway()["deploy"]["startCommand"])

    assert argv == _dockerfile_json_instruction("ENTRYPOINT") + _dockerfile_json_instruction("CMD")


def test_railway_health_check_is_readiness_not_liveness() -> None:
    # /ready fails without a mounted, writable object store; /health does not.
    assert _railway()["deploy"]["healthcheckPath"] == "/ready"
