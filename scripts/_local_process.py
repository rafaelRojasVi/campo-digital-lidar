"""Shared local-process management primitives for Campo Digital dev launchers.

Used by ``scripts/lidar_dev.py`` and ``scripts/campo_demo.py``. Mirrors the
ownership model already used by the Forestry and Transelec worktree
launchers: a PID is only ever treated as "ours" after re-verifying it
against ``/proc/<pid>/cmdline``, and ``stop`` never touches a process it did
not itself start (or that it cannot re-verify).

This module contains no product-specific behavior and performs no database
or ingestion actions.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ManagedProcess:
    name: str
    pid: int
    port: int
    marker: str


def state_file(state_dir: Path, name: str) -> Path:
    return state_dir / f"{name}.json"


def save_process(state_dir: Path, process: ManagedProcess) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file(state_dir, process.name).write_text(
        json.dumps({"pid": process.pid, "port": process.port, "marker": process.marker}),
        encoding="utf-8",
    )


def load_process(state_dir: Path, name: str) -> ManagedProcess | None:
    path = state_file(state_dir, name)

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
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def process_cmdline(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None

    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")


def is_ours(process: ManagedProcess) -> bool:
    """True only if the recorded PID is alive and still runs our command."""

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

    raise RuntimeError("no free local port available")


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
    state_dir: Path,
    name: str,
    command: list[str],
    cwd: Path,
    port: int,
    marker: str,
    env: dict[str, str],
) -> ManagedProcess:
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / f"{name}.log"

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
    save_process(state_dir, process)
    return process


def stop_process(state_dir: Path, name: str) -> str:
    """Stop a process this launcher owns. Returns a short human-readable outcome."""

    process = load_process(state_dir, name)

    if process is None:
        return "no recorded process"

    if not is_ours(process):
        state_file(state_dir, name).unlink(missing_ok=True)
        return f"PID {process.pid} is no longer the recorded process; not touching it"

    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGTERM)

    for _ in range(40):
        if process_cmdline(process.pid) is None:
            break
        time.sleep(0.25)
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)

    state_file(state_dir, name).unlink(missing_ok=True)
    return f"stopped PID {process.pid}"
