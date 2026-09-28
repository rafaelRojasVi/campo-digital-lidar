"""Minimal local dev launcher for the Transelec dashboard (frontend only).

Usage (via the Makefile):

    make transelec-dev       # scripts/transelec_dev.py up
    make transelec-status    # scripts/transelec_dev.py status
    make transelec-stop      # scripts/transelec_dev.py stop

Transelec's real backend is the SAME shared FastAPI app LiDAR already uses:
``apps/api/app/main.py`` mounts ``app.routers.transelec`` alongside the LiDAR
and ingestion routers on one process, so there is no separate Transelec
backend to start here. This launcher:

- adopts the shared platform API if ``lidar-dev``/``campo-demo``/
  ``platform-local`` already started one (checked the same way
  ``scripts/platform_local.py`` does, against ``.lidar-dev/api.json``), or
  starts it itself if nothing is running yet;
- starts the existing Vite dev server for ``products/transelect/dashboard``
  on a free port, pointed at that API via the ``CAMPO_PLATFORM_API_PORT``
  environment variable the dashboard's own ``vite.config.ts`` already reads.

It does NOT:

- ingest or write any source/workbook data;
- change any Transelec domain/business logic;
- stop the shared API on ``transelec-stop`` — that same API process may
  still be serving LiDAR or another Transelec session. Stop it explicitly
  with ``make lidar-stop`` (or ``make campo-stop``) once nothing needs it.

Safety model mirrors ``scripts/_local_process.py`` / ``scripts/lidar_dev.py``:
``stop`` re-verifies its recorded PID against ``/proc/<pid>/cmdline`` before
signaling it, so it only ever stops a process this launcher itself started.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _local_process import (  # noqa: E402
    find_free_port,
    is_ours,
    load_process,
    spawn,
    stop_process,
    wait_for_http,
)
from _platform_db import PlatformDatabaseError, ensure_platform_database_ready  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = REPO_ROOT / "products" / "transelect" / "dashboard"
STATE_DIR = REPO_ROOT / ".transelec-dev"

# Same shared-API state location scripts/lidar_dev.py and
# scripts/platform_local.py already use — there is only ever one shared
# platform API process in local dev, owned by whichever launcher started it
# first, and every other launcher adopts it instead of starting a second one.
SHARED_API_STATE_DIR = REPO_ROOT / ".lidar-dev"

API_PREFERRED_PORT = 8000
FRONTEND_PREFERRED_PORT = 5200  # matches the dashboard's own vite.config.ts default


class LauncherError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[transelec-dev] {message}")


def start_api() -> tuple[int, int]:
    """Returns (port, pid). Adopts the shared platform API if lidar-dev,
    campo-demo, platform-local, or a previous transelec-dev already started
    one; starts a new one under the same shared state location otherwise."""

    existing = load_process(SHARED_API_STATE_DIR, "api")
    if existing is not None and is_ours(existing):
        log(f"shared platform API already running on port {existing.port}")
        return existing.port, existing.pid

    try:
        ensure_platform_database_ready()
    except PlatformDatabaseError as exc:
        raise LauncherError(str(exc)) from exc

    port = find_free_port(API_PREFERRED_PORT)
    marker = f"uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port {port}"
    command = ["uv", "run", "--extra", "api", *marker.split(" ")]

    # APP_ENV is required and fails closed if unset (see app.main and
    # app.config.Settings) — set it explicitly here, like lidar_dev.py and
    # platform_local.py do, so this keeps working from a shell that hasn't
    # exported it.
    env = dict(os.environ)
    env["APP_ENV"] = env.get("APP_ENV", "development")

    log(f"starting shared platform API on 127.0.0.1:{port}…")
    process = spawn(SHARED_API_STATE_DIR, "api", command, REPO_ROOT, port, marker, env)

    if not wait_for_http(f"http://127.0.0.1:{port}/health", 60):
        raise LauncherError(
            f"The API did not become ready on port {port}. See {SHARED_API_STATE_DIR / 'api.log'}"
        )

    return process.port, process.pid


def ensure_frontend_dependencies() -> None:
    if (DASHBOARD_ROOT / "node_modules").is_dir():
        return

    log("installing dashboard dependencies (npm install)…")
    result = subprocess.run(["npm", "install"], cwd=DASHBOARD_ROOT, capture_output=True, text=True)

    if result.returncode != 0:
        raise LauncherError(f"npm install failed:\n{result.stdout}\n{result.stderr}")


def start_frontend(api_port: int) -> tuple[int, int]:
    existing = load_process(STATE_DIR, "frontend")
    if existing is not None and is_ours(existing):
        log(f"dashboard already running on port {existing.port}")
        return existing.port, existing.pid

    ensure_frontend_dependencies()

    port = find_free_port(FRONTEND_PREFERRED_PORT)
    marker = f"--port {port} --strictPort"
    command = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--strictPort",
    ]

    env = dict(os.environ)
    env["CAMPO_PLATFORM_API_PORT"] = str(api_port)

    log(f"starting dashboard on 127.0.0.1:{port}…")
    process = spawn(STATE_DIR, "frontend", command, DASHBOARD_ROOT, port, marker, env)

    if not wait_for_http(f"http://127.0.0.1:{port}/", 60):
        raise LauncherError(
            f"The dashboard did not start on port {port}. See {STATE_DIR / 'frontend.log'}"
        )

    return process.port, process.pid


def open_browser(url: str) -> None:
    for opener in (["wslview", url], ["xdg-open", url], ["powershell.exe", "Start-Process", url]):
        if shutil.which(opener[0]) is None:
            continue
        try:
            subprocess.Popen(
                opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
            )
            return
        except OSError:
            continue
    log("could not open a browser automatically; open the URL manually.")


def command_up() -> int:
    api_port, _ = start_api()
    frontend_port, _ = start_frontend(api_port)

    frontend_url = f"http://127.0.0.1:{frontend_port}/"
    log("ready:")
    log(f"  dashboard  {frontend_url}")
    log(f"  API        http://127.0.0.1:{api_port}/health")
    log(f"  logs       {STATE_DIR}/frontend.log · {SHARED_API_STATE_DIR}/api.log")
    log("stop with: make transelec-stop (leaves the shared API running — see module docstring)")
    open_browser(frontend_url)
    return 0


def command_status() -> int:
    api = load_process(SHARED_API_STATE_DIR, "api")
    if api is None:
        print("Platform API: not started")
    elif not is_ours(api):
        print(f"Platform API: stale record (PID {api.pid} is gone)")
    else:
        healthy = wait_for_http(f"http://127.0.0.1:{api.port}/health", 2)
        state = "running" if healthy else "process alive, not responding"
        print(f"Platform API: {state} (PID {api.pid} · port {api.port})")

    frontend = load_process(STATE_DIR, "frontend")
    if frontend is None:
        print("Dashboard: not started")
    elif not is_ours(frontend):
        print(f"Dashboard: stale record (PID {frontend.pid} is gone)")
    else:
        healthy = wait_for_http(f"http://127.0.0.1:{frontend.port}/", 2)
        state = "running" if healthy else "process alive, not responding"
        print(f"Dashboard: {state} (PID {frontend.pid} · port {frontend.port})")

    return 0


def command_stop() -> int:
    outcome = stop_process(STATE_DIR, "frontend")
    log(f"frontend: {outcome}")
    log("shared platform API left running — stop it with `make lidar-stop` or `make campo-stop`")
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "up"

    try:
        if command == "up":
            return command_up()
        if command == "status":
            return command_status()
        if command == "stop":
            return command_stop()
    except LauncherError as error:
        print(f"[transelec-dev] ERROR: {error}", file=sys.stderr)
        return 1

    print(f"usage: {sys.argv[0]} [up|status|stop]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
