"""Resource-aware, sequential release validation runner.

Deterministic, LLM-free orchestrator for required release gates.

Behavior:
1. run the RAM gate first;
2. below 4 GiB, write an ENV_BLOCKED summary and start no gate;
3. from 4 GiB, run configured heavy gates sequentially, rechecking RAM before
   each gate in LOW_MEMORY_SERIAL mode; continue after failures so independent gates execute;
4. emit a compact summary at artifacts/gates/heavy-validation.json;
5. never modify product code;
6. never invoke a model or LLM provider;
7. terminal state is PASS / FAIL / ENV_BLOCKED / BLOCKED.

Exit codes: 0 PASS, 1 FAIL, 3 ENV_BLOCKED, 5 BLOCKED, 2 config error.
"""
from __future__ import annotations

import argparse
import gc
import json
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # executed directly: python scripts/heavy_validation_runner.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate_runner
    import ram_gate
    import validation_env
else:  # imported as part of the scripts package from tests
    from . import gate_runner, ram_gate, validation_env

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "artifacts" / "gates" / "heavy-validation.json"

# Ordered heavy gates. Gates whose authoritative command is missing on this
# machine report NOT_CONFIGURED (never silently PASS).
HEAVY_GATE_ORDER: list[str] = [
    "pytest",
    "security",
    "smoke",
    "e2e",
    "sonar",
    "docker-build",
    "docker-e2e",
    "jenkins",
    "soak",
]


def _write_summary(payload: dict) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _gate_summary_fields(results: list[dict]) -> dict[str, object]:
    statuses = {entry["gate"]: entry["status"] for entry in results}
    return {
        "required_core_gates": {name: statuses.get(name, "NOT_RUN") for name in ("pytest", "security", "smoke", "e2e")},
        "configured_failures": [entry["gate"] for entry in results if entry["status"] == "FAIL"],
        "not_configured": [entry["gate"] for entry in results if entry["status"] == "NOT_CONFIGURED"],
    }


def _run_gate(gate: str) -> int:
    """Indirection point so tests can stub gate execution without spawning."""
    env = gate_runner.validation_environment(gate)
    return subprocess.run(
        [str(validation_env.python_path()), str(ROOT / "scripts" / "gate_runner.py"), gate],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


def run(available_gib_override: float | None = None, gates: list[str] | None = None) -> int:
    gate_list = gates if gates is not None else list(HEAVY_GATE_ORDER)
    started = time.monotonic()

    if available_gib_override is not None:
        available_gib = float(available_gib_override)
        ram_verdict = ram_gate.evaluate(available_gib)
    else:
        try:
            available_gib = ram_gate.measure_available_bytes() / ram_gate.GIB
        except OSError:
            _write_summary(
                {
                    "terminal_state": "BLOCKED",
                    "ram": {"heavy_validation": ram_gate.MEASUREMENT_ERROR},
                    "gates": [],
                    **_gate_summary_fields([]),
                    "reason": "RAM measurement failed; cannot authorize heavy validation",
                }
            )
            return 5
        ram_verdict = ram_gate.evaluate(available_gib)

    ram_info = {
        "available_gib": round(available_gib, 2),
        "threshold_gib": ram_gate.THRESHOLD_GIB,
        "minimum_gib": ram_gate.MINIMUM_GIB,
        "ram_mode": ram_verdict,
        "heavy_validation": ram_verdict,
    }

    if ram_verdict == ram_gate.ENV_BLOCKED:
        _write_summary(
            {
                "terminal_state": "ENV_BLOCKED",
                "ram": ram_info,
                "ram_mode": ram_gate.ENV_BLOCKED,
                "gates": [],
                **_gate_summary_fields([]),
                "reason": "available RAM below 4.0 GiB",
                "duration_seconds": round(time.monotonic() - started, 2),
            }
        )
        return 3

    try:
        validation_env.ensure()
    except Exception as exc:  # noqa: BLE001 - setup failure blocks heavy execution
        _write_summary({
            "terminal_state": "BLOCKED",
            "ram": ram_info,
            "gates": [],
            **_gate_summary_fields([]),
            "reason": f"validation environment setup failed: {type(exc).__name__}: {exc}",
        })
        return 5

    results: list[dict] = []
    any_configured = False
    any_failed = False
    effective_ram_mode = ram_verdict
    for gate in gate_list:
        gate_ram = available_gib
        gate_mode = ram_verdict
        if available_gib_override is None:
            try:
                gate_ram = ram_gate.measure_available_bytes() / ram_gate.GIB
            except OSError as exc:
                _write_summary({"terminal_state": "BLOCKED", "ram": ram_info, "gates": results,
                                **_gate_summary_fields(results),
                                "reason": f"RAM measurement failed before {gate}: {exc}"})
                return 5
            gate_mode = ram_gate.evaluate(gate_ram)
            if gate_mode == ram_gate.ENV_BLOCKED:
                _write_summary({
                    "terminal_state": "ENV_BLOCKED",
                    "ram": {**ram_info, "available_gib": round(gate_ram, 2)},
                    "ram_mode": gate_mode, "gates": results,
                    **_gate_summary_fields(results),
                    "reason": f"available RAM below 4.0 GiB before {gate}",
                    "duration_seconds": round(time.monotonic() - started, 2),
                })
                return 3
        if gate_mode == ram_gate.LOW_MEMORY_SERIAL:
            effective_ram_mode = ram_gate.LOW_MEMORY_SERIAL
        code = _run_gate(gate)
        gc.collect()
        if code == 4:
            status = "NOT_CONFIGURED"
        elif code == 0:
            status = "PASS"
            any_configured = True
        else:
            status = "FAIL"
            any_configured = True
            any_failed = True
        results.append({"gate": gate, "status": status, "exit_code": code,
                        "ram_before_gib": round(gate_ram, 2), "ram_mode": gate_mode})

    if not any_configured:
        terminal_state = "BLOCKED"
        exit_code = 5
    elif any_failed:
        terminal_state = "FAIL"
        exit_code = 1
    else:
        terminal_state = "PASS"
        exit_code = 0

    _write_summary(
        {
            "terminal_state": terminal_state,
            "ram": ram_info,
            "ram_mode": effective_ram_mode,
            "gates": results,
            **_gate_summary_fields(results),
            "duration_seconds": round(time.monotonic() - started, 2),
        }
    )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="Resource-aware release validation runner (LLM-free)")
    parser.add_argument(
        "--available-ram-gib",
        type=float,
        default=None,
        help="deterministic override for tests; skips physical measurement",
    )
    args = parser.parse_args(argv)
    return run(args.available_ram_gib)


if __name__ == "__main__":
    sys.exit(main())
