"""One-command local Forestry demo: database, migrations, ingestion, API, frontend.

Usage (via the Makefile):

    make forestry-dev       # scripts/forestry_dev.py up
    make forestry-status    # scripts/forestry_dev.py status
    make forestry-stop      # scripts/forestry_dev.py stop

Safety model:

- The external source root is only ever read (observed + fingerprinted);
  ingestion is idempotent by family fingerprint.
- Migrations and ingestion run only when APP_ENV=development and the
  configured PostgreSQL host is local.
- `stop` kills only the exact processes this launcher started (PID files are
  re-verified against /proc cmdline before any signal). The shared dev
  PostgreSQL container is deliberately left running.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
DASHBOARD_ROOT = REPO_ROOT / "products" / "forestry" / "dashboard"
STATE_DIR = REPO_ROOT / ".forestry-dev"

FORESTRY_SOURCE_ZIP = (
    "01_Gestion_Predial_Forestal/02_Datos_Entrada/01_SAF_DEGENFELD/001_DEGENFELD_2026.zip"
)
FORESTRY_SYSTEM_KEY = "campo_digital_onedrive"

API_PREFERRED_PORT = 8000
FRONTEND_PREFERRED_PORT = 5173

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


class LauncherError(RuntimeError):
    """Fatal launcher condition with a user-facing message."""


def log(message: str) -> None:
    print(f"[forestry-dev] {message}")


# ---------------------------------------------------------------- environment


def ensure_env_file() -> None:
    """Create .env from .env.example with a generated local password."""

    env_path = REPO_ROOT / ".env"

    if env_path.exists():
        return

    example = REPO_ROOT / ".env.example"

    if not example.exists():
        raise LauncherError(".env is missing and .env.example was not found")

    password = secrets.token_urlsafe(24)
    content = example.read_text(encoding="utf-8").replace(
        "replace-with-local-random-password", password
    )
    env_path.write_text(content, encoding="utf-8")
    log(
        ".env created from .env.example with a generated local password. "
        "If the postgres_data volume already exists with another password, "
        "remove it or restore the original .env."
    )


def guard_development_environment() -> None:
    """Load API settings (.env-aware) and refuse non-local configurations."""

    os.chdir(REPO_ROOT)

    # APP_ENV is required and fails closed if unset (see app.main); this
    # launcher only ever runs locally, so default it the way the Transelec and
    # LiDAR launchers do. The API subprocess inherits os.environ.
    os.environ.setdefault("APP_ENV", "development")

    from app.config import get_settings

    settings = get_settings()

    if settings.app_env != "development":
        raise LauncherError(
            f"APP_ENV is {settings.app_env!r}; the local demo only runs in 'development'."
        )

    if settings.postgres_host not in {"127.0.0.1", "localhost"}:
        raise LauncherError(
            f"POSTGRES_HOST is {settings.postgres_host!r}; the local demo only "
            "touches a local database."
        )


def validate_external_source() -> Path:
    """Resolve and read-only-validate the real Forestry source ZIP."""

    from app.source_discovery import observe_source_file, source_root_from_environment

    try:
        root = source_root_from_environment()
    except Exception as exc:
        raise LauncherError(
            "CAMPO_DIGITAL_SOURCE_ROOT is not usable. Set it to the OneDrive "
            f"hub before running the demo. ({exc})"
        ) from exc

    try:
        observation = observe_source_file(root, FORESTRY_SOURCE_ZIP)
    except Exception as exc:
        raise LauncherError(
            f"The Forestry source ZIP was not found under the source root: "
            f"{FORESTRY_SOURCE_ZIP} ({exc})"
        ) from exc

    log(
        f"external source OK: {observation.relative_path} "
        f"({observation.byte_size:,} bytes, read-only)"
    )
    return root


# ------------------------------------------------------------------ database


def start_database() -> None:
    log("starting local PostgreSQL/PostGIS (docker compose, service 'postgres')…")
    result = subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "postgres"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise LauncherError(
            f"docker compose could not start the dev database:\n{result.stdout}\n{result.stderr}"
        )


def run_migrations() -> None:
    log("applying migrations (alembic upgrade head)…")
    result = subprocess.run(
        ["uv", "run", "--extra", "api", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise LauncherError(f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}")


def ingest_snapshot(source_root: Path) -> None:
    """Idempotently ingest the real Forestry ZIP into the dev database."""

    from app.config import get_settings
    from app.database import build_engine
    from app.forestry_persistence import ingest_forestry_snapshot

    engine = build_engine(get_settings())

    try:
        with engine.connect() as connection, connection.begin():
            result = ingest_forestry_snapshot(
                connection,
                source_root=source_root,
                zip_relative_path=FORESTRY_SOURCE_ZIP,
                system_key=FORESTRY_SYSTEM_KEY,
            )
    finally:
        engine.dispose()

    state = "already persisted (idempotent)" if result.already_persisted else "newly persisted"
    log(
        f"snapshot {state}: id={result.shapefile_snapshot_id}, "
        f"features={result.feature_count}, fingerprint={result.family_fingerprint[:8]}…"
    )


# ----------------------------------------------------------------- processes


@dataclass(frozen=True, slots=True)
class ManagedProcess:
    name: str
    pid: int
    port: int
    marker: str


def state_file(name: str) -> Path:
    return STATE_DIR / f"{name}.json"


def save_process(process: ManagedProcess) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    state_file(process.name).write_text(
        json.dumps({"pid": process.pid, "port": process.port, "marker": process.marker}),
        encoding="utf-8",
    )


def load_process(name: str) -> ManagedProcess | None:
    path = state_file(name)

    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ManagedProcess(
            name=name,
            pid=int(data["pid"]),
            port=int(data["port"]),
            marker=str(data["marker"]),
        )
    except (ValueError, KeyError):
        return None


def process_cmdline(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None

    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")


def is_ours(process: ManagedProcess) -> bool:
    cmdline = process_cmdline(process.pid)
    return cmdline is not None and process.marker in cmdline


def find_free_port(preferred: int) -> int:
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
                return int(sock.getsockname()[1])
            except OSError:
                continue

    raise LauncherError("no free local port available")


def wait_for_http(url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)

    return False


def spawn(
    name: str,
    command: list[str],
    cwd: Path,
    port: int,
    marker: str,
    env: dict[str, str],
) -> ManagedProcess:
    STATE_DIR.mkdir(exist_ok=True)
    log_path = STATE_DIR / f"{name}.log"

    with log_path.open("ab") as log_handle:
        popen = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )

    process = ManagedProcess(name=name, pid=popen.pid, port=port, marker=marker)
    save_process(process)
    return process


def stop_process(name: str) -> None:
    process = load_process(name)

    if process is None:
        log(f"{name}: no recorded process")
        return

    if not is_ours(process):
        log(f"{name}: PID {process.pid} is not the recorded process anymore; not touching it")
        state_file(name).unlink(missing_ok=True)
        return

    log(f"stopping {name} (PID {process.pid})…")

    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGTERM)

    for _ in range(40):
        if process_cmdline(process.pid) is None:
            break
        time.sleep(0.25)
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)

    state_file(name).unlink(missing_ok=True)


# ------------------------------------------------------------------ commands


def start_api() -> ManagedProcess:
    existing = load_process("api")

    if existing is not None and is_ours(existing):
        log(f"API already running on port {existing.port}")
        return existing

    port = find_free_port(API_PREFERRED_PORT)
    marker = f"uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port {port}"
    command = ["uv", "run", "--extra", "api", *marker.split(" ")]

    log(f"starting FastAPI on 127.0.0.1:{port}…")
    process = spawn("api", command, REPO_ROOT, port, marker, dict(os.environ))

    if not wait_for_http(f"http://127.0.0.1:{port}/ready", 60):
        raise LauncherError(
            f"The API did not become ready on port {port}. See {STATE_DIR / 'api.log'}"
        )

    return process


def ensure_frontend_dependencies() -> None:
    if (DASHBOARD_ROOT / "node_modules").is_dir():
        return

    log("installing frontend dependencies (npm install)…")
    result = subprocess.run(
        ["npm", "install"],
        cwd=DASHBOARD_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise LauncherError(f"npm install failed:\n{result.stdout}\n{result.stderr}")


def start_frontend(api_port: int) -> ManagedProcess:
    existing = load_process("frontend")

    if existing is not None and is_ours(existing):
        log(f"frontend already running on port {existing.port}")
        return existing

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
    env["FORESTRY_API_PORT"] = str(api_port)

    log(f"starting frontend on 127.0.0.1:{port}…")
    process = spawn("frontend", command, DASHBOARD_ROOT, port, marker, env)

    if not wait_for_http(f"http://127.0.0.1:{port}/rodales/", 60):
        raise LauncherError(
            f"The frontend did not start on port {port}. See {STATE_DIR / 'frontend.log'}"
        )

    return process


def open_browser(url: str) -> None:
    for opener in (["wslview", url], ["xdg-open", url], ["powershell.exe", "Start-Process", url]):
        if shutil.which(opener[0]) is None:
            continue
        try:
            subprocess.Popen(
                opener,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        except OSError:
            continue

    log("could not open a browser automatically; open the URL manually.")


def command_up() -> int:
    ensure_env_file()
    guard_development_environment()
    source_root = validate_external_source()
    start_database()
    run_migrations()
    ingest_snapshot(source_root)

    api = start_api()
    frontend = start_frontend(api.port)

    # Served under /rodales/ like the platform; the API needs a session with
    # a forestry grant, so the page offers the development sign-in first.
    frontend_url = f"http://127.0.0.1:{frontend.port}/rodales/"
    log("ready:")
    log(f"  frontend  {frontend_url}  (sign in as Dev Admin or Dev Operator)")
    log(f"  API       http://127.0.0.1:{api.port}/api/forestry/snapshots (needs a session)")
    log(f"  logs      {STATE_DIR}/api.log · {STATE_DIR}/frontend.log")
    log("stop with: make forestry-stop (the dev database stays up)")
    open_browser(frontend_url)
    return 0


def command_status() -> int:
    for name in ("api", "frontend"):
        process = load_process(name)

        if process is None:
            print(f"{name:9} not started")
            continue

        if not is_ours(process):
            print(f"{name:9} stale record (PID {process.pid} is gone)")
            continue

        probe = "/ready" if name == "api" else "/"
        healthy = wait_for_http(f"http://127.0.0.1:{process.port}{probe}", 2)
        state = "responding" if healthy else "process alive, not responding"
        print(f"{name:9} PID {process.pid} · port {process.port} · {state}")

    compose = subprocess.run(
        ["docker", "compose", "ps", "--status", "running", "--format", "{{.Service}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    postgres_running = "postgres" in compose.stdout.split()
    print(f"{'postgres':9} {'running (docker compose)' if postgres_running else 'not running'}")
    return 0


def command_stop() -> int:
    stop_process("frontend")
    stop_process("api")
    log("dev database left running (stop it with: docker compose stop postgres)")
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
        print(f"[forestry-dev] ERROR: {error}", file=sys.stderr)
        return 1

    print(f"usage: {sys.argv[0]} [up|status|stop]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
