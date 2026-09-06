"""E2E harness: starts the dashboard, runs Playwright smoke test, stops server.

Run:
    python scripts/e2e.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "e2e_report.json"
DASHBOARD_URL = "http://127.0.0.1:5000"
PYTHON = sys.executable


def _server_cmd() -> list[str]:
    return [PYTHON, str(ROOT / "dashboard.py")]


def _wait_for_server(timeout: float = 30.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(DASHBOARD_URL, timeout=1.0) as _:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _drain_output(stream, sink: list[str]) -> None:
    """Continuously reads lines from `stream` into `sink` for the process's
    whole lifetime.

    Without this, subprocess.PIPE has a small OS buffer (~64KB on Windows)
    — Werkzeug logs a line per HTTP request to stderr, and a Playwright
    smoke run makes enough requests (page polling + explicit calls) to fill
    it well before the run ends. Once full, the *server process itself*
    blocks on its next write() to the pipe, unable to handle any further
    request, until something reads from the other end — exactly the
    "dashboard stops responding partway through the run" symptom this fixes
    (reproduced identically on a fresh CI runner with no prior state, always
    at roughly the same point in a run — the buffer filling, not a load- or
    memory-dependent flake). See Python docs' own subprocess deadlock
    warning for stdout=PIPE/stderr=PIPE.
    """
    try:
        for line in iter(stream.readline, ""):
            sink.append(line)
    except (ValueError, OSError):
        pass  # stream closed under us as the process exits — fine


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")

    print("Starting dashboard...")
    server = subprocess.Popen(
        _server_cmd(),
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    server_output: list[str] = []
    drain_thread = threading.Thread(target=_drain_output, args=(server.stdout, server_output), daemon=True)
    drain_thread.start()

    try:
        if not _wait_for_server():
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()
            report = {
                "status": "FAIL",
                "detail": "dashboard did not start",
                "server_output": "".join(server_output)[-4000:],
                "ok": False,
            }
            REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
            return 1

        print("Running E2E smoke test...")
        result = subprocess.run(
            [PYTHON, str(ROOT / "tests" / "e2e" / "smoke_dashboard.py")],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        ok = result.returncode == 0
        report = {
            "status": "PASS" if ok else "FAIL",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "server_output": "".join(server_output)[-4000:],
            "ok": ok,
        }
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report["stdout"][-2000:])
    if report["stderr"]:
        print(report["stderr"][-1000:])
    print(f"Report saved: {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
