"""Minimal local demo launcher for the LiDAR product (API + viewer).

Usage (via the Makefile):

    make lidar-dev       # scripts/lidar_dev.py up
    make lidar-status    # scripts/lidar_dev.py status
    make lidar-stop      # scripts/lidar_dev.py stop

This is intentionally narrow: it starts the existing FastAPI app and the
existing Vite viewer on dynamically chosen free ports, so LiDAR can run
alongside the Forestry and Transelec local demos without a port clash.

It does NOT:

- ingest or write any source/measurement data;
- change any scientific/measurement behavior.

Readiness is checked against ``/health`` (dependency-free liveness), not
``/ready`` (which requires a live PostgreSQL connection) — the viewer itself
never depends on the database.

``apps/api/app/main.py`` mounts the platform ingestion/access routers
(``/ingesta``, ``/auth``) alongside the LiDAR router on the same app, so
starting the API here also brings up the local ``postgres`` service and
applies migrations first (see ``scripts/_platform_db.py``), the one shared
readiness step every launcher of this app uses. This is the SAME process
``make platform-local`` starts (in foreground, with ``--reload``, for active
ingestion/access development instead); the two refuse to run at once — see
``scripts/platform_local.py``.

Safety model mirrors ``scripts/_local_process.py`` / the Forestry and
Transelec worktree launchers: ``stop`` re-verifies each recorded PID against
``/proc/<pid>/cmdline`` before signaling it, so it only ever stops processes
this launcher itself started.
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

from lidar_io.output_root_discovery import (  # noqa: E402
    SOURCE_CURRENT_WORKTREE,
    SOURCE_DISCOVERED_WORKTREE,
    SOURCE_ENV,
    SOURCE_NONE,
    resolve_report_root,
)
from lidar_io.run_store import discover_measurement_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = REPO_ROOT / "products" / "lidar" / "dashboard"
STATE_DIR = REPO_ROOT / ".lidar-dev"

API_PREFERRED_PORT = 8000
VIEWER_PREFERRED_PORT = 5174

REPORT_SOURCE_LABELS = {
    SOURCE_ENV: "explicit CAMPO_LIDAR_OUTPUT_ROOT",
    SOURCE_CURRENT_WORKTREE: "current worktree",
    SOURCE_DISCOVERED_WORKTREE: "discovered local report store",
    SOURCE_NONE: "none found",
}


class LauncherError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[lidar-dev] {message}")


def start_api() -> tuple[int, int]:
    """Returns (port, pid). Adopts an already-running API started by us."""

    existing = load_process(STATE_DIR, "api")
    if existing is not None and is_ours(existing):
        log(f"API already running on port {existing.port}")
        return existing.port, existing.pid

    try:
        ensure_platform_database_ready()
    except PlatformDatabaseError as exc:
        raise LauncherError(str(exc)) from exc

    port = find_free_port(API_PREFERRED_PORT)
    marker = f"uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port {port}"
    command = ["uv", "run", "--extra", "api", *marker.split(" ")]

    # APP_ENV is now required and fails closed if unset (see app.main and
    # app.config.Settings) — set it explicitly here, like
    # scripts/platform_local.py does, so this launcher keeps working from a
    # shell that hasn't exported it.
    env = dict(os.environ)
    env["APP_ENV"] = env.get("APP_ENV", "development")

    log(f"starting FastAPI on 127.0.0.1:{port}…")
    process = spawn(STATE_DIR, "api", command, REPO_ROOT, port, marker, env)

    if not wait_for_http(f"http://127.0.0.1:{port}/health", 60):
        raise LauncherError(
            f"The API did not become ready on port {port}. See {STATE_DIR / 'api.log'}"
        )

    return process.port, process.pid


def ensure_viewer_dependencies() -> None:
    if (DASHBOARD_ROOT / "node_modules").is_dir():
        return

    log("installing viewer dependencies (npm install)…")
    result = subprocess.run(["npm", "install"], cwd=DASHBOARD_ROOT, capture_output=True, text=True)

    if result.returncode != 0:
        raise LauncherError(f"npm install failed:\n{result.stdout}\n{result.stderr}")


def start_viewer(api_port: int) -> tuple[int, int]:
    existing = load_process(STATE_DIR, "viewer")
    if existing is not None and is_ours(existing):
        log(f"viewer already running on port {existing.port}")
        return existing.port, existing.pid

    ensure_viewer_dependencies()

    port = find_free_port(VIEWER_PREFERRED_PORT)
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
    env["LIDAR_API_PORT"] = str(api_port)

    log(f"starting viewer on 127.0.0.1:{port}…")
    process = spawn(STATE_DIR, "viewer", command, DASHBOARD_ROOT, port, marker, env)

    if not wait_for_http(f"http://127.0.0.1:{port}/", 60):
        raise LauncherError(
            f"The viewer did not start on port {port}. See {STATE_DIR / 'viewer.log'}"
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
    viewer_port, _ = start_viewer(api_port)

    viewer_url = f"http://127.0.0.1:{viewer_port}/"
    log("ready:")
    log(f"  viewer  {viewer_url}")
    log(f"  API     http://127.0.0.1:{api_port}/health")
    log(f"  logs    {STATE_DIR}/api.log · {STATE_DIR}/viewer.log")
    log("stop with: make lidar-stop")
    open_browser(viewer_url)
    return 0


def measurement_status() -> tuple[int, str, Path]:
    """Returns (persisted measurement count, human-readable report source, output root).

    Service state (is the API/viewer process running) and data state (are
    there any persisted measurements to show) are independent facts: an API
    can be up with zero measurements, or a report store can be discovered
    while the API itself is stopped.
    """

    resolution = resolve_report_root(
        REPO_ROOT,
        env_value=os.environ.get("CAMPO_LIDAR_OUTPUT_ROOT"),
    )
    count = len(discover_measurement_paths(resolution.path))
    source_label = REPORT_SOURCE_LABELS.get(resolution.source, resolution.source)
    return count, source_label, resolution.path


def command_status() -> int:
    service_labels = {"api": "LiDAR API", "viewer": "Viewer"}

    for name, probe in (("api", "/health"), ("viewer", "/")):
        label = service_labels[name]
        process = load_process(STATE_DIR, name)

        if process is None:
            print(f"{label}: not started")
            continue

        if not is_ours(process):
            print(f"{label}: stale record (PID {process.pid} is gone)")
            continue

        healthy = wait_for_http(f"http://127.0.0.1:{process.port}{probe}", 2)
        state = "running" if healthy else "process alive, not responding"
        print(f"{label}: {state} (PID {process.pid} · port {process.port})")

    count, source_label, output_root = measurement_status()
    print(f"Persisted measurements: {count}")
    print(f"Report source: {source_label}")
    print(f"  (path: {output_root})")

    return 0


def command_stop() -> int:
    for name in ("viewer", "api"):
        outcome = stop_process(STATE_DIR, name)
        log(f"{name}: {outcome}")
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
        print(f"[lidar-dev] ERROR: {error}", file=sys.stderr)
        return 1

    print(f"usage: {sys.argv[0]} [up|status|stop]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
