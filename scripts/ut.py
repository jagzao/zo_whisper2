"""Unit-test harness: runs pytest and produces JSON report.

Run:
    python scripts/ut.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "ut_report.json"


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    ok = result.returncode == 0
    report = {
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "status": "PASS" if ok else "FAIL",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": ok,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(result.stdout[-2000:])
    if result.stderr:
        print(result.stderr[-1000:])
    print(f"Report saved: {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
