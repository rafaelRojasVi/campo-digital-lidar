"""CLI entrypoint: ensure the local platform Postgres service is up and at
Alembic head.

Usage (via the Makefile):

    make ensure-platform-db

A prerequisite step for ``platform-worker``/``platform-worker-concurrency``,
mirroring the same readiness step ``scripts/lidar_dev.py`` and
``scripts/platform_local.py`` already run before starting the shared API —
see ``scripts/_platform_db.py`` for the shared implementation and why this
gives migrations one predictable owner rather than several independently
guessing entry points.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _platform_db import PlatformDatabaseError, ensure_platform_database_ready  # noqa: E402


def main() -> int:
    try:
        ensure_platform_database_ready()
    except PlatformDatabaseError as exc:
        print(f"[ensure-platform-db] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
