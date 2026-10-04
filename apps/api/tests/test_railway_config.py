""".railway/railway.ts must build the Dockerfile and start through its entrypoint.

Railway replaces the image's ENTRYPOINT with any custom start command, and
the production service runs as root (RAILWAY_RUN_UID=0) so the entrypoint
can hand the volume to ``campo``. A start command that skipped the
entrypoint would therefore run the API as root. Declaring it as
Infrastructure as Code keeps that from depending on a dashboard field nobody
can see from the repository. (It replaced railway.json, Config as Code,
which Railway stops reading on 2026-12-01.)
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _dockerfile_json_instruction(name: str) -> list[str]:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(rf"^{name} (\[.*\])$", dockerfile, flags=re.MULTILINE)
    assert match, f"Dockerfile has no exec-form {name}"
    return list(json.loads(match.group(1)))


def _railway_ts() -> str:
    return (REPO_ROOT / ".railway" / "railway.ts").read_text(encoding="utf-8")


def _ts_string_option(name: str) -> str:
    match = re.search(rf'\b{name}:\s*("(?:[^"\\]|\\.)*")', _railway_ts())
    assert match, f".railway/railway.ts declares no string {name}"
    return str(json.loads(match.group(1)))


def _ts_env() -> dict[str, str]:
    match = re.search(r"\benv:\s*\{(.*?)\n\s*\}", _railway_ts(), flags=re.DOTALL)
    assert match, ".railway/railway.ts declares no env block"
    return dict(re.findall(r"^\s*(\w+):\s*(.+?),\s*$", match.group(1), flags=re.MULTILINE))


def test_config_as_code_is_gone() -> None:
    # Two sources of truth for the same service is how they drift apart.
    assert not (REPO_ROOT / "railway.json").exists()
    assert not (REPO_ROOT / "railway.toml").exists()


def test_iac_builds_the_repository_dockerfile() -> None:
    assert re.search(
        r'build:\s*\{\s*builder:\s*"DOCKERFILE",\s*dockerfilePath:\s*"/Dockerfile"\s*\}',
        _railway_ts(),
    )
    assert (REPO_ROOT / "Dockerfile").is_file()


def test_iac_start_command_runs_through_the_image_entrypoint() -> None:
    argv = shlex.split(_ts_string_option("start"))

    assert argv[:1] == _dockerfile_json_instruction("ENTRYPOINT")


def test_iac_start_command_is_exactly_the_images_own_start() -> None:
    argv = shlex.split(_ts_string_option("start"))

    assert argv == _dockerfile_json_instruction("ENTRYPOINT") + _dockerfile_json_instruction("CMD")


def test_iac_health_check_is_readiness_not_liveness() -> None:
    # /ready fails without a mounted, writable object store; /health does not.
    assert _ts_string_option("healthcheck") == "/ready"


def test_iac_runs_migrations_as_a_pre_deploy_step() -> None:
    assert _ts_string_option("preDeploy") == ".venv/bin/alembic upgrade head"


def test_iac_keeps_the_object_store_volume_and_its_variable() -> None:
    assert re.search(r'volumeMounts:\s*\{\s*"/data":', _railway_ts())
    assert "CAMPO_OBJECT_STORE_ROOT" in _ts_env()


def test_iac_never_writes_a_variable_value_into_the_repository() -> None:
    # An apply deletes any variable the file leaves out, so every production
    # variable is declared; preserve() keeps its value in Railway only.
    env = _ts_env()

    assert env
    assert {name: value for name, value in env.items() if value != "preserve()"} == {}
