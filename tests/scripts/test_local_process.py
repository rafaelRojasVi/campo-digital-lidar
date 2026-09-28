"""Tests for scripts/_local_process.py, the shared launcher ownership model.

Uses real short-lived subprocesses (rather than mocking /proc) so `is_ours`
and `stop_process` are exercised against actual process/cmdline semantics.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from scripts._local_process import (
    ManagedProcess,
    find_free_port,
    is_ours,
    load_process,
    process_cmdline,
    save_process,
    spawn,
    stop_process,
)


def spawn_marked_process(marker: str) -> subprocess.Popen[bytes]:
    """A real, short-lived process whose /proc cmdline contains `marker`.

    Waits for `/proc/<pid>/cmdline` to actually be populated before
    returning: right after `Popen()` returns, some platforms (observed
    under WSL2's procfs) have not yet execed the child, so `cmdline` can
    briefly read back empty.
    """

    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", marker],
        start_new_session=True,
    )

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        cmdline = process_cmdline(proc.pid)
        if cmdline and marker in cmdline:
            return proc
        time.sleep(0.02)

    raise RuntimeError(f"spawned process {proc.pid} never exposed its marked cmdline")


def wait_until_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process_cmdline(pid) is None:
            return True
        time.sleep(0.05)
    return False


def test_find_free_port_falls_back_when_preferred_is_taken() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        taken_port = blocker.getsockname()[1]

        chosen = find_free_port(taken_port)

        assert chosen != taken_port
        assert chosen > 0


def test_find_free_port_returns_preferred_when_available() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]

    assert find_free_port(free_port) == free_port


def test_save_and_load_process_round_trip(tmp_path: Path) -> None:
    process = ManagedProcess(name="api", pid=4242, port=8000, marker="a-marker")
    save_process(tmp_path, process)

    loaded = load_process(tmp_path, "api")

    assert loaded == process


def test_load_process_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_process(tmp_path, "nothing-here") is None


def test_is_ours_true_for_a_live_matching_process() -> None:
    marker = "campo-test-marker-alive"
    proc = spawn_marked_process(marker)
    try:
        assert is_ours(ManagedProcess(name="x", pid=proc.pid, port=1, marker=marker))
    finally:
        proc.kill()
        proc.wait()


def test_is_ours_false_when_marker_does_not_match() -> None:
    marker = "campo-test-marker-real"
    proc = spawn_marked_process(marker)
    try:
        stale = ManagedProcess(name="x", pid=proc.pid, port=1, marker="some-other-marker")
        assert is_ours(stale) is False
    finally:
        proc.kill()
        proc.wait()


def test_is_ours_false_for_a_dead_pid() -> None:
    proc = spawn_marked_process("campo-test-marker-dying")
    proc.kill()
    proc.wait()

    assert wait_until_gone(proc.pid)
    dead = ManagedProcess(name="x", pid=proc.pid, port=1, marker="campo-test-marker-dying")
    assert is_ours(dead) is False


def test_stop_process_only_signals_a_verified_owned_process(tmp_path: Path) -> None:
    marker = "campo-test-marker-stop-owned"
    proc = spawn_marked_process(marker)

    save_process(tmp_path, ManagedProcess(name="viewer", pid=proc.pid, port=9999, marker=marker))

    outcome = stop_process(tmp_path, "viewer")

    assert "stopped" in outcome
    # Reap the child ourselves: this test process is its parent, so the
    # kernel will not release it (leaving cmdline reading back as "" rather
    # than a clean OSError) until something waits on it -- exactly what a
    # real launcher process exiting shortly after `stop` accomplishes.
    assert proc.wait(timeout=6) is not None
    assert load_process(tmp_path, "viewer") is None


def test_stop_process_leaves_an_unowned_process_alone(tmp_path: Path) -> None:
    marker = "campo-test-marker-untouched"
    proc = spawn_marked_process(marker)
    try:
        # Recorded marker does not match this process's real cmdline, so it
        # must never be signaled even though the PID is alive.
        save_process(
            tmp_path,
            ManagedProcess(name="viewer", pid=proc.pid, port=9999, marker="not-the-real-marker"),
        )

        outcome = stop_process(tmp_path, "viewer")

        assert "not touching it" in outcome
        assert process_cmdline(proc.pid) is not None
    finally:
        proc.kill()
        proc.wait()


def test_stop_process_with_no_recorded_process_is_a_noop(tmp_path: Path) -> None:
    assert stop_process(tmp_path, "nothing") == "no recorded process"


def test_spawn_records_process_state(tmp_path: Path) -> None:
    process = spawn(
        tmp_path,
        "echoer",
        [sys.executable, "-c", "import time; time.sleep(5)"],
        tmp_path,
        1234,
        "spawn-test-marker",
        {},
    )

    try:
        assert load_process(tmp_path, "echoer") == process
        assert (tmp_path / "echoer.log").exists()
    finally:
        import contextlib
        import os
        import signal

        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
