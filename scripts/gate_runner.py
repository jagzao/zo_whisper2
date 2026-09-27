"""Compact deterministic gate runner.

Executes a named gate (an existing authoritative script/test) and emits a
normalized machine-readable report at ``artifacts/gates/latest.json``. It
invokes existing scripts — it never reimplements their logic.

Run:
    python scripts/gate_runner.py <gate> [paths...]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts" / "gates"
LOGS_DIR = ARTIFACTS_DIR / "logs"
LATEST_PATH = ARTIFACTS_DIR / "latest.json"

# Gate registry: each entry is the authoritative existing command for that gate.
GATES: dict[str, list[str]] = {
    "pytest": [sys.executable, "-m", "pytest", "tests/", "-q"],
    "quality": [sys.executable, "scripts/quality.py"],
    "security": [sys.executable, "scripts/security.py"],
    "smoke": [sys.executable, "scripts/smoke.py"],
    "e2e": [sys.executable, "scripts/e2e.py"],
}

# Gate scripts that emit a structured JSON report at repo root.
REPORT_FILES: dict[str, str] = {
    "quality": "quality_report.json",
    "security": "security_report.json",
    "smoke": "smoke_report.json",
    "e2e": "e2e_report.json",
}


def _truncate(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit]


def _existing_files_from_detail(detail: str) -> list[str]:
    """Best-effort: relative paths mentioned in a failure detail that exist."""
    found: list[str] = []
    for token in detail.replace(",", " ").replace(":", " ").split():
        candidate = token.strip("\"'()[]")
        if not candidate or len(candidate) > 260:
            continue
        if candidate in found:
            continue
        if (ROOT / candidate).exists():
            found.append(candidate)
        if len(found) >= 10:
            break
    return found


def _extract_structured_failure(gate: str, combined_output: str) -> tuple[str, str, list[str]]:
    """Extract (check, error_signature, affected_files) from a gate's own report.

    Falls back to a pytest-style signature scan when the report is missing,
    unreadable, or malformed.
    """
    report_name = REPORT_FILES.get(gate)
    if report_name:
        report_path = ROOT / report_name
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = None
            if isinstance(report, dict):
                if gate == "e2e":
                    detail = report.get("detail") or report.get("stdout") or report.get("stderr") or ""
                    return "e2e", _truncate(str(detail)), []
                checks = report.get("checks")
                if isinstance(checks, list):
                    for check in checks:
                        if isinstance(check, dict) and check.get("status") != "PASS":
                            detail = str(check.get("detail", ""))
                            return (
                                str(check.get("name", gate)),
                                _truncate(detail),
                                _existing_files_from_detail(detail),
                            )

    error_signature = ""
    for line in reversed((combined_output or "").splitlines()):
        if line.strip():
            error_signature = _truncate(line)
            break
    return gate, error_signature, []


def run_gate(gate: str, extra_args: list[str] | None = None) -> int:
    """Run a named gate, write compact report + raw log, return process status.

    Returns 0 on PASS, 1 on FAIL, 2 on unknown gate.
    """
    extra_args = extra_args or []

    if gate == "targeted":
        if not extra_args:
            return 2
        cmd = [sys.executable, "-m", "pytest", *extra_args, "-q"]
    elif gate in GATES:
        cmd = list(GATES[gate])
    else:
        return 2

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Never let a report from a previous run masquerade as evidence for the
    # current invocation when the authoritative script fails before writing
    # its own report.
    report_name = REPORT_FILES.get(gate)
    if report_name:
        (ROOT / report_name).unlink(missing_ok=True)

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        returncode = result.returncode
        stdout = result.stdout or ""
        stderr = result.stderr or ""
    except Exception as exc:  # noqa: BLE001 - a broken gate must not crash the runner
        returncode = 1
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
    duration = time.monotonic() - start

    combined_output = f"{stdout}\n{stderr}"
    (LOGS_DIR / f"{gate}.log").write_text(combined_output, encoding="utf-8")

    status = "PASS" if returncode == 0 else "FAIL"
    if status == "PASS":
        check = gate
        error_signature = ""
        affected_files: list[str] = []
    else:
        check, error_signature, affected_files = _extract_structured_failure(gate, combined_output)

    LATEST_PATH.write_text(
        json.dumps(
            {
                "status": status,
                "gate": gate,
                "check": check,
                "error_signature": error_signature,
                "affected_files": affected_files,
                "artifact": f"artifacts/gates/logs/{gate}.log",
                "duration_seconds": round(duration, 2),
                "command": " ".join(cmd),
                "runner": "scripts/gate_runner.py",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[{status}] {gate} ({round(duration, 2)}s) -> artifacts/gates/latest.json")
    return 0 if status == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return 2
    gate = argv[0]
    extra_args = argv[1:]
    return run_gate(gate, extra_args)


if __name__ == "__main__":
    sys.exit(main())
