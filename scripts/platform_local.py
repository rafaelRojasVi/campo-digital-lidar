"""Foreground dev-server launcher for the shared Campo Digital platform API.

Usage (via the Makefile):

    make platform-local

Starts the same process ``scripts/lidar_dev.py``'s ``start_api()`` starts —
``apps/api/app/main:app`` — but attached to the terminal with ``--reload``,
for engineers actively iterating on the ingestion/access foundation. Ensures
the local ``postgres`` service is up and migrated to head first (see
``scripts/_platform_db.py``), the same way ``lidar-dev``/``campo-demo`` now
do, so migrations follow one consistent, predictable code path everywhere
the shared app is started.

Refuses to start if lidar-dev/campo-demo already owns a running instance of
this same app in this worktree, instead of crashing on a port bind
conflict: the two are not meant to run at the same time. Use `make
lidar-stop` (or `make campo-stop`) first, or just use that instance.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _local_process import is_ours, load_process  # noqa: E402
from _platform_db import PlatformDatabaseError, ensure_platform_database_ready  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
LIDAR_STATE_DIR = REPO_ROOT / ".lidar-dev"
PORT = 8000


def log(message: str) -> None:
    print(f"[platform-local] {message}")


def main() -> int:
    existing = load_process(LIDAR_STATE_DIR, "api")
    if existing is not None and is_ours(existing):
        log(
            f"The shared API is already running via lidar-dev/campo-demo on "
            f"port {existing.port}. Use that instance, or stop it first "
            f"with `make lidar-stop` (or `make campo-stop`)."
        )
        return 1

    try:
        ensure_platform_database_ready()
    except PlatformDatabaseError as exc:
        log(f"ERROR: {exc}")
        return 1

    env = dict(os.environ)
    env["APP_ENV"] = env.get("APP_ENV", "development")
    env["PYTHONPATH"] = "apps/api"

    log(f"starting on 127.0.0.1:{PORT} (--reload)…")
    os.execvpe(
        "uv",
        ["uv", "run", "uvicorn", "app.main:app", "--reload", "--port", str(PORT)],
        env,
    )
    return 0  # unreachable: execvpe replaces this process on success


if __name__ == "__main__":
    raise SystemExit(main())
