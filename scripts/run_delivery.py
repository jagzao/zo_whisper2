"""Jenkins-independent deterministic delivery wrapper (DELTA-ZMI-DKR-002).

Runs the same product gates as the Jenkinsfile in a frozen order, with no
LLM, continuing past independent gate failures and always producing the
compact gate summary via ``scripts/summarize_gates.py``. It never triggers
Jenkins and never modifies expected behavior.

Run:
    python scripts/run_delivery.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATES_ROOT = ROOT / "artifacts" / "gates"
DEFAULT_BUILD_NUMBER = "overnight-local"
DEFAULT_HOST_E2E_PORT = "5500"
EMAIL_STATUS = "NOT_CONFIGURED"

TARGETED_TESTS: tuple[str, ...] = (
    "tests/test_gate_runner.py",
    "tests/test_summarize_gates.py",
    "tests/test_mock_data_root.py",
    "tests/test_docker_gate.py",
    "tests/test_project_override.py",
    "tests/integration/test_dashboard_process_restart.py",
)

DOCKER_BUILD = "docker-build"
# A failed prerequisite deterministically skips only its dependents.
PREREQUISITES: dict[str, str] = {
    DOCKER_BUILD: "docker-config",
    "docker-smoke": DOCKER_BUILD,
    "docker-persistence": DOCKER_BUILD,
    "docker-asr-smoke": DOCKER_BUILD,
    "docker-e2e": DOCKER_BUILD,
}

# Frozen execution order — section B of DELTA-ZMI-DKR-002.
GATE_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("targeted", ("targeted",) + TARGETED_TESTS),
    ("pytest", ("pytest",)),
    ("quality", ("quality",)),
    ("security", ("security",)),
    ("docker-config", ("docker-config",)),
    ("docker-build", ("docker-build",)),
    ("docker-smoke", ("docker-smoke",)),
    ("docker-persistence", ("docker-persistence",)),
    ("docker-asr-smoke", ("docker-asr-smoke",)),
    ("e2e", ("e2e",)),
    ("docker-e2e", ("docker-e2e",)),
)


def derive_build_id(build_number: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", build_number).strip("-_")
    return token or DEFAULT_BUILD_NUMBER


def build_dir(build_number: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", build_number)[:80] or "local"
    return GATES_ROOT / f"build-{safe}"


def gate_command(gate: str, args: tuple[str, ...]) -> list[str]:
    runner = "scripts/docker_gate.py" if gate.startswith("docker-") else "scripts/gate_runner.py"
    return [sys.executable, runner, *args]


def run_gate_cmd(gate: str, args: tuple[str, ...], env: dict[str, str]) -> str:
    result = subprocess.run(
        gate_command(gate, args),
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return "PASS" if result.returncode == 0 else "FAIL"


def write_report(build_number: str, gate: str, status: str, check: str, error_signature: str) -> Path:
    directory = build_dir(build_number)
    directory.mkdir(parents=True, exist_ok=True)
    report = {
        "status": status,
        "gate": gate,
        "check": check,
        "error_signature": error_signature[:500],
        "command": "",
        "artifact": "",
        "runner": "scripts/run_delivery.py",
    }
    path = directory / f"{gate}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def prepare_host_e2e(env: dict[str, str], build_number: str) -> tuple[bool, str]:
    """Isolate host E2E data, then generate mock data. Never raises."""
    host_root = build_dir(build_number) / "host-e2e-data"
    try:
        host_root.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "projects.json.example", host_root / "projects.json")
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    port = env.get("DASHBOARD_PORT") or DEFAULT_HOST_E2E_PORT
    env["ZMI_DATA_ROOT"] = str(host_root)
    env["ZMI_TEST_DATA_ROOT"] = str(host_root)
    env["ZMI_CONFIG_ENV"] = str(host_root / "scan_config.env")
    env["ZMI_BASE_URL"] = env.get("ZMI_BASE_URL") or f"http://127.0.0.1:{port}"
    env["DASHBOARD_HOST"] = "127.0.0.1"
    env["DASHBOARD_PORT"] = port
    result = subprocess.run(
        [sys.executable, "docs/assets/generate_mock_data.py"],
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        signature = lines[-1] if lines else f"exit={result.returncode}"
        return False, signature[:500]
    return True, ""


def run_host_e2e(env: dict[str, str], build_number: str) -> str:
    ok, detail = prepare_host_e2e(env, build_number)
    try:
        if not ok:
            write_report(build_number, "e2e", "FAIL", "host-e2e-setup", detail)
            print(f"[FAIL] e2e: host-e2e-setup: {detail}")
            return "FAIL"
        return run_gate_cmd("e2e", ("e2e",), env)
    finally:
        subprocess.run(
            [sys.executable, "docs/assets/cleanup_mock_data.py"],
            cwd=str(ROOT),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )


def run_summary(env: dict[str, str]) -> int:
    result = subprocess.run(
        [sys.executable, "scripts/summarize_gates.py", "--email-status", EMAIL_STATUS],
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode


def run_delivery(base_env: dict[str, str] | None = None) -> int:
    """Execute every gate in frozen order; return the summary exit status."""
    env = dict(os.environ if base_env is None else base_env)
    build_number = (env.get("BUILD_NUMBER") or DEFAULT_BUILD_NUMBER).strip() or DEFAULT_BUILD_NUMBER
    env["BUILD_NUMBER"] = build_number
    env["BUILD_ID"] = derive_build_id(build_number)
    env["ALLOW_EXTERNAL_LLM"] = "false"

    results: dict[str, str] = {}
    for gate, args in GATE_COMMANDS:
        if gate == "e2e":
            results[gate] = run_host_e2e(env, build_number)
            continue
        prereq = PREREQUISITES.get(gate)
        if prereq is not None and results.get(prereq) != "PASS":
            reason = f"prerequisite {prereq} status={results.get(prereq)}"
            write_report(build_number, gate, "SKIPPED", "prerequisite-failed", reason)
            print(f"[SKIPPED] {gate}: {reason}")
            results[gate] = "SKIPPED"
            continue
        results[gate] = run_gate_cmd(gate, args, env)
    return run_summary(env)


def main(argv: list[str] | None = None) -> int:
    del argv  # no options: frozen order, deterministic environment
    return run_delivery()


if __name__ == "__main__":
    sys.exit(main())
