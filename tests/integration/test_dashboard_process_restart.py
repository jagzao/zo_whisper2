"""Process-level dashboard restart smoke.

Unlike the in-memory restart unit tests, this starts the real composition
root in a child process, stops it, then starts a fresh process on the same
port. It intentionally performs no destructive product operation.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_status(port: int, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/status"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                assert response.status == 200
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # child may still be importing
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"dashboard did not become ready: {last_error}")


def _start_dashboard(port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DASHBOARD_HOST"] = "127.0.0.1"
    env["DASHBOARD_PORT"] = str(port)
    env["ALLOW_EXTERNAL_LLM"] = "false"
    return subprocess.Popen(
        [sys.executable, str(ROOT / "dashboard.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_dashboard_real_process_restart_has_fresh_run_state():
    port = _free_port()
    first = _start_dashboard(port)
    try:
        status1 = _wait_status(port)
        assert status1["running"] is False
        assert status1["error"] is None
    finally:
        _stop(first)

    second = _start_dashboard(port)
    try:
        status2 = _wait_status(port)
        assert status2["running"] is False
        assert status2["error"] is None
        assert all(stage["status"] == "pending" for stage in status2["stages"].values())
    finally:
        _stop(second)

    assert first.poll() is not None
    assert second.poll() is not None
