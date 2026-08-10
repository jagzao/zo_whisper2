"""E2E harness: starts the dashboard, runs Playwright smoke test, stops server.

Run:
    python scripts/e2e.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
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


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")

    print("Starting dashboard...")
    server = subprocess.Popen(
        _server_cmd(),
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        if not _wait_for_server():
            out, err = server.communicate(timeout=2)
            report = {
                "status": "FAIL",
                "detail": "dashboard did not start",
                "stdout": out,
                "stderr": err,
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
