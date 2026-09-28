"""Shared local Postgres/Alembic readiness for Campo Digital dev launchers.

Used by ``scripts/lidar_dev.py`` (and therefore ``campo_demo.py``, which
starts LiDAR via ``make lidar-dev``), ``scripts/platform_local.py``, and the
``platform-worker``/``platform-worker-concurrency`` Makefile targets — every
entry point that starts the shared ``apps/api/app/main:app`` process, or a
worker consuming its job queue, brings the local ``platform`` Postgres
service up and applies migrations through this exact same code path first.

This is what gives migrations a single, predictable owner: not one process
that is uniquely allowed to run them, but one shared, idempotent step every
launcher performs identically, so the schema is never silently stale or
missing under whichever entry point happened to be used first.

Failure here must never let a caller proceed and silently serve/consume a
database that is not at head — raise with an actionable message instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent


class PlatformDatabaseError(RuntimeError):
    """The local platform Postgres service could not be brought to head."""


def ensure_platform_database_ready() -> None:
    """Bring the local ``postgres`` compose service up and apply migrations.

    Idempotent: safe to call every time a launcher starts, including when
    the database is already at head. Raises ``PlatformDatabaseError`` with
    an actionable message on any failure rather than let a caller proceed
    against a database that is not ready.
    """

    compose_result = subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "postgres"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if compose_result.returncode != 0:
        raise PlatformDatabaseError(
            "Could not bring up the local `postgres` service.\n"
            f"{compose_result.stdout}\n{compose_result.stderr}\n"
            "Run `docker compose up -d --wait postgres` yourself to see the "
            "underlying error (Docker not running? .env missing "
            "POSTGRES_PASSWORD? copy .env.example first)."
        )

    try:
        config = Config(str(REPO_ROOT / "alembic.ini"))
        command.upgrade(config, "head")
    except Exception as exc:  # noqa: BLE001 - re-raised with actionable guidance
        raise PlatformDatabaseError(
            "Could not apply database migrations to head.\n"
            f"{exc}\n"
            "Run `PYTHONPATH=apps/api uv run alembic upgrade head` yourself "
            "to see the underlying error."
        ) from exc
