"""One-command local demo orchestrator for the Campo Digital company portal.

Usage (via the Makefile):

    make campo-demo      # scripts/campo_demo.py up
    make campo-status    # scripts/campo_demo.py status
    make campo-stop      # scripts/campo_demo.py stop

This script is a company-level composition shell over independently owned
product launchers. It does not implement product logic and does not touch
product persistence, migrations, or source ingestion itself:

- LiDAR is started via ``make lidar-dev`` in this worktree.
- Forestry is started via ``make forestry-dev`` in the sibling worktree
  checked out at ``feat/forestry-dashboard-v1``.
- Transelec is started via ``make transelec-dev`` in this same worktree (see
  ``scripts/transelec_dev.py``): the real, session-authenticated Transelec
  dashboard now lives alongside LiDAR here, backed by the same shared
  platform API, so — unlike Forestry — it needs no sibling worktree lookup.
  The old ``feat/transelec-ui-reference-parity-v1`` worktree was a
  backend-less UI reference used only to discover pixel-parity requirements
  (see Task 5's report); it is not wired here.

Sibling worktrees are discovered with ``git worktree list --porcelain`` and
are treated as read-only: this script never clones, modifies, or resets
them. If a required worktree is missing, the corresponding module is simply
reported unavailable.

Process ownership: a product is only ever adopted (left alone on ``stop``)
if it was already running before this script tried to start it. Only
modules this script itself started are stopped by ``make campo-stop``. The
portal's own dev server is always owned by this launcher.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
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

from lidar_io.output_root_discovery import resolve_report_root  # noqa: E402
from lidar_io.run_store import discover_measurement_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
PORTAL_ROOT = REPO_ROOT / "apps" / "portal"
CAMPO_STATE_DIR = REPO_ROOT / ".campo-demo"
CAMPO_STATE_FILE = CAMPO_STATE_DIR / "state.json"

PORTAL_PREFERRED_PORT = 5100

FORESTRY_BRANCH = "feat/forestry-dashboard-v1"

MODULE_IDS = ("lidar", "forestal", "transelec")


class LauncherError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[campo-demo] {message}")


# --------------------------------------------------------------- worktrees


@dataclass(frozen=True, slots=True)
class Worktree:
    path: Path
    branch: str | None
    detached: bool


def parse_worktree_porcelain(text: str) -> list[Worktree]:
    """Parses ``git worktree list --porcelain`` output.

    Pure function: takes text, returns data. No subprocess calls, so it is
    directly unit-testable against recorded/synthetic output.
    """

    worktrees: list[Worktree] = []
    path: Path | None = None
    branch: str | None = None
    detached = False

    def flush() -> None:
        nonlocal path, branch, detached
        if path is not None:
            worktrees.append(Worktree(path=path, branch=branch, detached=detached))
        path, branch, detached = None, None, False

    for line in text.splitlines():
        if not line.strip():
            flush()
            continue

        if line.startswith("worktree "):
            flush()
            path = Path(line[len("worktree ") :].strip())
        elif line.startswith("branch "):
            ref = line[len("branch ") :].strip()
            branch = ref.removeprefix("refs/heads/")
        elif line == "detached":
            detached = True

    flush()
    return worktrees


def find_worktree_for_branch(worktrees: list[Worktree], branch: str) -> Path | None:
    for worktree in worktrees:
        if worktree.branch == branch:
            return worktree.path
    return None


def discover_worktrees() -> list[Worktree]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise LauncherError(f"`git worktree list --porcelain` failed:\n{result.stderr}")

    return parse_worktree_porcelain(result.stdout)


# ---------------------------------------------------------------- probing


def probe_lidar(repo_root: Path = REPO_ROOT, probe_timeout: float = 1.5) -> tuple[bool, str | None]:
    """Read-only check: is a LiDAR viewer this launcher's format recognizes
    already running? Never starts or signals anything."""

    state_dir = repo_root / ".lidar-dev"
    viewer = load_process(state_dir, "viewer")

    if viewer is None or not is_ours(viewer):
        return False, None

    url = f"http://127.0.0.1:{viewer.port}/"
    if not wait_for_http(url, probe_timeout):
        return False, None

    return True, url


def lidar_measurement_count(repo_root: Path = REPO_ROOT) -> int:
    """Counts API-visible persisted LiDAR measurements, independent of
    whether the LiDAR API/viewer processes are currently running."""

    resolution = resolve_report_root(
        repo_root,
        env_value=os.environ.get("CAMPO_LIDAR_OUTPUT_ROOT"),
    )
    return len(discover_measurement_paths(resolution.path))


def probe_forestry(
    worktree_root: Path | None, probe_timeout: float = 1.5
) -> tuple[bool, str | None]:
    if worktree_root is None:
        return False, None

    state_dir = worktree_root / ".forestry-dev"
    frontend = load_process(state_dir, "frontend")

    if frontend is None or not is_ours(frontend):
        return False, None

    url = f"http://127.0.0.1:{frontend.port}/"
    if not wait_for_http(url, probe_timeout):
        return False, None

    return True, url


def probe_transelec(
    repo_root: Path = REPO_ROOT, probe_timeout: float = 1.5
) -> tuple[bool, str | None]:
    """Read-only check: is the real Transelec dashboard's dev server (this
    launcher's format) already running? Never starts or signals anything.

    Mirrors ``probe_lidar`` exactly: Transelec's real dashboard lives in this
    same worktree (``products/transelect/dashboard``), started by
    ``scripts/transelec_dev.py`` via ``make transelec-dev``, not in a
    separate sibling worktree the way Forestry still is.
    """

    state_dir = repo_root / ".transelec-dev"
    frontend = load_process(state_dir, "frontend")

    if frontend is None or not is_ours(frontend):
        return False, None

    url = f"http://127.0.0.1:{frontend.port}/"
    if not wait_for_http(url, probe_timeout):
        return False, None

    return True, url


# ---------------------------------------------------------- starting/stopping


def run_make_target(cwd: Path, target: str, timeout: float = 240.0) -> None:
    try:
        result = subprocess.run(
            ["make", "-C", str(cwd), target],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise LauncherError(f"`make -C {cwd} {target}` timed out after {timeout:.0f}s") from exc

    if result.returncode != 0:
        tail_out = "\n".join(result.stdout.splitlines()[-20:])
        tail_err = "\n".join(result.stderr.splitlines()[-20:])
        raise LauncherError(f"`make -C {cwd} {target}` failed:\n{tail_out}\n{tail_err}")


@dataclass(frozen=True, slots=True)
class ModuleResult:
    status: str  # "available" | "unavailable"
    url: str | None
    owned: bool
    detail: str
    measurement_count: int | None = None


ProbeFn = Callable[[Path | None], tuple[bool, str | None]]


def ensure_module(
    name: str,
    worktree: Path | None,
    probe: ProbeFn,
    dev_cwd: Path | None,
    dev_target: str,
) -> ModuleResult:
    running_before, url = probe(worktree)

    if running_before:
        log(f"{name}: already running, adopting ({url})")
        return ModuleResult("available", url, owned=False, detail="adopted existing demo")

    if dev_cwd is None:
        log(f"{name}: worktree not found locally; module will be unavailable")
        return ModuleResult(
            "unavailable",
            None,
            owned=False,
            detail="expected worktree for branch not found locally",
        )

    log(f"{name}: starting via `make -C {dev_cwd} {dev_target}`…")
    try:
        run_make_target(dev_cwd, dev_target)
    except LauncherError as exc:
        log(f"{name}: failed to start ({exc})")
        return ModuleResult("unavailable", None, owned=False, detail=str(exc))

    running_after, url_after = probe(worktree)
    if running_after:
        return ModuleResult("available", url_after, owned=True, detail="started by campo-demo")

    return ModuleResult(
        "unavailable", None, owned=False, detail="launcher exited but module did not come up"
    )


# --------------------------------------------------------------------- portal


def ensure_npm_install(project_root: Path) -> None:
    if (project_root / "node_modules").is_dir():
        return

    log(f"installing dependencies in {project_root}…")
    result = subprocess.run(["npm", "install"], cwd=project_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise LauncherError(
            f"npm install failed in {project_root}:\n{result.stdout}\n{result.stderr}"
        )


def start_portal() -> tuple[int, int]:
    existing = load_process(CAMPO_STATE_DIR, "portal")
    if existing is not None and is_ours(existing):
        log(f"portal already running on port {existing.port}")
        return existing.port, existing.pid

    ensure_npm_install(PORTAL_ROOT)

    port = find_free_port(PORTAL_PREFERRED_PORT)
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

    log(f"starting portal on 127.0.0.1:{port}…")
    process = spawn(CAMPO_STATE_DIR, "portal", command, PORTAL_ROOT, port, marker, dict(os.environ))

    if not wait_for_http(f"http://127.0.0.1:{port}/", 60):
        raise LauncherError(
            f"portal did not start on port {port}. See {CAMPO_STATE_DIR / 'portal.log'}"
        )

    return process.port, process.pid


def _module_payload(result: ModuleResult) -> dict[str, str | bool | int | None]:
    payload: dict[str, str | bool | int | None] = {
        "status": result.status,
        "url": result.url,
        "owned": result.owned,
    }
    if result.measurement_count is not None:
        payload["measurementCount"] = result.measurement_count
    return payload


def write_runtime_config(portal_port: int, modules: dict[str, ModuleResult]) -> None:
    payload = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "portal": {"port": portal_port},
        "modules": {module_id: _module_payload(result) for module_id, result in modules.items()},
    }

    public_dir = PORTAL_ROOT / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "campo-runtime.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_ownership_state(modules: dict[str, ModuleResult]) -> None:
    CAMPO_STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, bool | str] = {
        f"{module_id}_owned": result.owned for module_id, result in modules.items()
    }
    payload["startedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    CAMPO_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_ownership_state() -> dict[str, bool]:
    if not CAMPO_STATE_FILE.is_file():
        return {f"{module_id}_owned": False for module_id in MODULE_IDS}

    try:
        data = json.loads(CAMPO_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {f"{module_id}_owned": False for module_id in MODULE_IDS}

    return {
        f"{module_id}_owned": bool(data.get(f"{module_id}_owned", False))
        for module_id in MODULE_IDS
    }


def open_browser(url: str) -> None:
    import shutil

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


# ---------------------------------------------------------------- commands


def resolve_modules(read_only: bool) -> dict[str, ModuleResult]:
    worktrees = discover_worktrees()
    forestry_worktree = find_worktree_for_branch(worktrees, FORESTRY_BRANCH)

    if read_only:
        modules: dict[str, ModuleResult] = {}
        for module_id, worktree, probe in (
            ("lidar", REPO_ROOT, lambda _w: probe_lidar()),
            ("forestal", forestry_worktree, probe_forestry),
            ("transelec", REPO_ROOT, lambda _w: probe_transelec()),
        ):
            running, url = probe(worktree)
            modules[module_id] = ModuleResult(
                "available" if running else "unavailable",
                url,
                owned=False,
                detail="observed only (status is read-only)",
                measurement_count=lidar_measurement_count() if module_id == "lidar" else None,
            )
        return modules

    modules = {
        "lidar": ensure_module(
            "lidar", REPO_ROOT, lambda _w: probe_lidar(), REPO_ROOT, "lidar-dev"
        ),
        "forestal": ensure_module(
            "forestal", forestry_worktree, probe_forestry, forestry_worktree, "forestry-dev"
        ),
        "transelec": ensure_module(
            "transelec", REPO_ROOT, lambda _w: probe_transelec(), REPO_ROOT, "transelec-dev"
        ),
    }
    modules["lidar"] = replace(modules["lidar"], measurement_count=lidar_measurement_count())
    return modules


def print_summary(portal_port: int | None, modules: dict[str, ModuleResult]) -> None:
    labels = {"lidar": "LiDAR", "forestal": "Forestal", "transelec": "Transelec"}

    if portal_port is not None:
        mark = "✓"
        print(f"[campo-demo] portal      {mark} http://127.0.0.1:{portal_port}/")

    for module_id in MODULE_IDS:
        result = modules[module_id]
        mark = "✓" if result.status == "available" else "✗"
        detail = result.url or "no disponible localmente"
        print(f"[campo-demo] {labels[module_id]:<10} {mark} {detail}")

    lidar_measurements = modules["lidar"].measurement_count
    if lidar_measurements is not None:
        print(f"[campo-demo] LiDAR measurements: {lidar_measurements}")

    if portal_port is not None:
        print()
        print("Campo Digital:")
        print(f"  http://127.0.0.1:{portal_port}/")


def command_up() -> int:
    modules = resolve_modules(read_only=False)

    portal_port, _ = start_portal()
    write_runtime_config(portal_port, modules)
    save_ownership_state(modules)

    print_summary(portal_port, modules)
    open_browser(f"http://127.0.0.1:{portal_port}/")
    return 0


def command_status() -> int:
    modules = resolve_modules(read_only=True)

    portal = load_process(CAMPO_STATE_DIR, "portal")
    portal_port: int | None = None
    if (
        portal is not None
        and is_ours(portal)
        and wait_for_http(f"http://127.0.0.1:{portal.port}/", 1.5)
    ):
        portal_port = portal.port
        write_runtime_config(portal_port, modules)

    print_summary(portal_port, modules)
    if portal_port is None:
        print("[campo-demo] portal      ✗ not started (run: make campo-demo)")
    return 0


def command_stop() -> int:
    ownership = load_ownership_state()

    if ownership["lidar_owned"]:
        for name in ("viewer", "api"):
            outcome = stop_process(REPO_ROOT / ".lidar-dev", name)
            log(f"lidar {name}: {outcome}")
    else:
        log("lidar: not owned by campo-demo, leaving it running")

    worktrees = discover_worktrees()

    forestry_worktree = find_worktree_for_branch(worktrees, FORESTRY_BRANCH)
    if ownership["forestal_owned"] and forestry_worktree is not None:
        try:
            run_make_target(forestry_worktree, "forestry-stop")
            log("forestal: stopped")
        except LauncherError as exc:
            log(f"forestal: failed to stop cleanly ({exc})")
    else:
        log("forestal: not owned by campo-demo, leaving it running")

    if ownership["transelec_owned"]:
        try:
            run_make_target(REPO_ROOT, "transelec-stop")
            log("transelec: stopped")
        except LauncherError as exc:
            log(f"transelec: failed to stop cleanly ({exc})")
    else:
        log("transelec: not owned by campo-demo, leaving it running")

    outcome = stop_process(CAMPO_STATE_DIR, "portal")
    log(f"portal: {outcome}")

    CAMPO_STATE_FILE.unlink(missing_ok=True)
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
        print(f"[campo-demo] ERROR: {error}", file=sys.stderr)
        return 1

    print(f"usage: {sys.argv[0]} [up|status|stop]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
