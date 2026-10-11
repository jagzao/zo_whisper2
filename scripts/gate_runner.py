"""Compact deterministic gate runner.

Executes a named gate (an existing authoritative script/test) and emits a
normalized machine-readable report at ``artifacts/gates/latest.json``. It
invokes existing scripts — it never reimplements their logic.

Gates are split into two PLV5 categories:

- LIGHT (implementation phase): targeted, unit, lint, quality, typecheck,
  security, smoke. The local coder may run these before ChatGPT review.
- HEAVY (post-review, RAM-gated): pytest, e2e, playwright, sonar, jenkins,
  docker*, soak. Never run before /review.

A gate whose authoritative command is not installed reports NOT_CONFIGURED.
NOT_CONFIGURED is never silently reported as PASS.

Run:
    python scripts/gate_runner.py <gate> [paths...]
    python scripts/gate_runner.py --list
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts" / "gates"
LOGS_DIR = ARTIFACTS_DIR / "logs"
LATEST_PATH = ARTIFACTS_DIR / "latest.json"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"

# Gate registry: each entry is the authoritative existing command for that gate.
GATES: dict[str, list[str]] = {
    "pytest": [sys.executable, "-m", "pytest", "tests/", "-q"],
    "quality": [sys.executable, "scripts/quality.py"],
    "security": [sys.executable, "scripts/security.py"],
    "smoke": [sys.executable, "scripts/smoke.py"],
    "playwright": [sys.executable, "scripts/e2e.py"],
    "e2e": [sys.executable, "scripts/e2e.py"],
    "sonar": ["sonar-scanner"],
    "lint": [sys.executable, "-m", "ruff", "check", "scripts", "tests"],
    "typecheck": [sys.executable, "-m", "compileall", "-q", "src", "scripts"],
    "docker-build": ["docker", "build", "."],
    "docker-e2e": ["docker", "compose", "-f", "watcher/docker-compose.yml", "up", "--abort-on-container-exit"],
    "jenkins": ["jenkins-cli", "build"],
    "soak": ["soak-runner"],
}

# PLV5 gate categories: implementation/light vs heavy (post-review only).
LIGHT_GATES: frozenset[str] = frozenset(
    {"targeted", "unit", "lint", "quality", "typecheck", "security", "smoke"}
)
HEAVY_GATES: frozenset[str] = frozenset(
    {"pytest", "e2e", "playwright", "sonar", "docker-build", "docker-e2e", "jenkins", "soak"}
)

GATE_CATEGORY: dict[str, str] = {
    **{name: "light" for name in LIGHT_GATES},
    **{name: "heavy" for name in HEAVY_GATES},
}


def category_of(gate: str) -> str:
    return GATE_CATEGORY.get(gate, "unknown")


def _command_is_configured(cmd: list[str]) -> bool:
    """True when the authoritative command exists on this machine."""
    if not cmd:
        return False
    head = cmd[0]
    if head == sys.executable:
        if len(cmd) >= 2 and cmd[1] == "-m":
            module = cmd[2].split(".")[0]
            return importlib.util.find_spec(module) is not None
        return Path(head).exists()
    if head.endswith(".py") or "/" in head or "\\" in head:
        return (ROOT / head).exists() or Path(head).exists()
    return shutil.which(head) is not None


def list_gates() -> int:
    registry = {
        name: {
            "command": " ".join(GATES[name]),
            "category": category_of(name),
            "configured": _command_is_configured(GATES[name]),
        }
        for name in sorted(GATES)
    }
    registry["targeted"] = {
        "command": "pytest <paths...>",
        "category": "light",
        "configured": True,
    }
    registry["unit"] = {
        "command": "pytest <paths...>",
        "category": "light",
        "configured": True,
    }
    print(json.dumps(registry, ensure_ascii=False, indent=2))
    return 0

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
                if gate in {"e2e", "playwright"}:
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

    Returns 0 on PASS, 1 on FAIL, 2 on unknown gate, 4 on NOT_CONFIGURED.
    """
    extra_args = extra_args or []

    if gate in {"targeted", "unit"}:
        if not extra_args:
            return 2
        cmd = [sys.executable, "-m", "pytest", *extra_args, "-q"]
    elif gate in GATES:
        cmd = list(GATES[gate])
        if not _command_is_configured(cmd):
            LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            LATEST_PATH.write_text(
                json.dumps(
                    {
                        "status": STATUS_NOT_CONFIGURED,
                        "gate": gate,
                        "category": category_of(gate),
                        "check": gate,
                        "error_signature": "authoritative command not installed on this machine",
                        "affected_files": [],
                        "artifact": None,
                        "duration_seconds": 0.0,
                        "command": " ".join(cmd),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"[{STATUS_NOT_CONFIGURED}] {gate} -> artifacts/gates/latest.json")
            return 4
    else:
        return 2

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

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

    status = STATUS_PASS if returncode == 0 else STATUS_FAIL
    if status == STATUS_PASS:
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
                "category": category_of(gate),
                "check": check,
                "error_signature": error_signature,
                "affected_files": affected_files,
                "artifact": f"artifacts/gates/logs/{gate}.log",
                "duration_seconds": round(duration, 2),
                "command": " ".join(cmd),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[{status}] {gate} ({round(duration, 2)}s) -> artifacts/gates/latest.json")
    return 0 if status == STATUS_PASS else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--list":
        return list_gates()
    if not argv:
        return 2
    gate = argv[0]
    extra_args = argv[1:]
    return run_gate(gate, extra_args)


if __name__ == "__main__":
    sys.exit(main())
