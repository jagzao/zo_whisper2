"""Run all harnesses and produce a combined report.

Run:
    python scripts/run_harness.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "harness_report.json"

STAGES = [
    ("quality", [sys.executable, str(ROOT / "scripts" / "quality.py")]),
    ("security", [sys.executable, str(ROOT / "scripts" / "security.py")]),
    ("ut", [sys.executable, str(ROOT / "scripts" / "ut.py")]),
    ("e2e", [sys.executable, str(ROOT / "scripts" / "e2e.py")]),
]


def run_stage(name: str, cmd: list[str]) -> dict:
    print(f"\n=== {name.upper()} ===")
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    return {
        "name": name,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-1000:],
    }


def main() -> int:
    stages = [run_stage(name, cmd) for name, cmd in STAGES]
    ok = all(s["status"] == "PASS" for s in stages)
    report = {"stages": stages, "ok": ok}
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nCombined report saved: {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
