"""PLV5 heavy validation runner tests (TEST-MATRIX PLV5-H04..H08, T02).

DELTA-PLV5-001 additions:
- AC-1: heavy runner includes security and smoke, in order after pytest;
- AC-2: full E2E is invoked only once (no playwright duplicate);
- AC-3: < 4.0 GiB available RAM blocks heavy gates;
- AC-4: the heavy runner never invokes a model/provider.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import heavy_validation_runner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "artifacts" / "gates" / "heavy-validation.json"

FORBIDDEN_IMPORTS = ("import openai", "import anthropic", "import litellm", "import requests", "import httpx")


@pytest.fixture(autouse=True)
def _clean_summary(monkeypatch):
    monkeypatch.setattr(heavy_validation_runner.validation_env, "ensure", lambda: heavy_validation_runner.validation_env.python_path())
    if SUMMARY_PATH.exists():
        SUMMARY_PATH.unlink()
    yield
    if SUMMARY_PATH.exists():
        SUMMARY_PATH.unlink()


def _read_summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_h04_deferred_run_starts_no_heavy_child():
    calls: list[str] = []

    def _forbidden_gate(gate):
        calls.append(gate)
        raise AssertionError("deferred run must not start any heavy gate")

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=_forbidden_gate):
        with mock.patch.object(
            heavy_validation_runner.gate_runner.subprocess, "run", side_effect=_forbidden_gate
        ):
            rc = heavy_validation_runner.run(available_gib_override=3.99)

    assert rc == 3
    assert calls == []
    data = _read_summary()
    assert data["terminal_state"] == "ENV_BLOCKED"
    assert data["gates"] == []
    assert data["ram"]["heavy_validation"] == "ENV_BLOCKED"


def test_h05_allowed_run_invokes_configured_heavy_gates():
    invoked: list[str] = []

    def _fake_gate(gate):
        invoked.append(gate)
        return 0

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=_fake_gate):
        rc = heavy_validation_runner.run(available_gib_override=7.5)

    assert rc == 0
    assert invoked == list(heavy_validation_runner.HEAVY_GATE_ORDER)
    data = _read_summary()
    assert data["terminal_state"] == "PASS"
    assert all(g["status"] == "PASS" for g in data["gates"])
    assert data["required_core_gates"] == {
        "pytest": "PASS", "security": "PASS", "smoke": "PASS", "e2e": "PASS"
    }
    assert data["configured_failures"] == []
    assert data["not_configured"] == []


def test_h06_and_h07_gate_failure_does_not_repair_or_skip_independent_gates():
    invoked: list[str] = []

    def _fake_gate(gate):
        invoked.append(gate)
        return 1 if gate == "pytest" else 0

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=_fake_gate):
        rc = heavy_validation_runner.run(available_gib_override=7.5)

    assert rc == 1
    # H07: every configured heavy gate still ran after the pytest failure.
    assert invoked == list(heavy_validation_runner.HEAVY_GATE_ORDER)
    data = _read_summary()
    assert data["terminal_state"] == "FAIL"
    pytest_entry = next(g for g in data["gates"] if g["gate"] == "pytest")
    assert pytest_entry["status"] == "FAIL"
    # H06: no repair action is recorded or attempted by the runner.
    assert "repair" not in json.dumps(data).lower()


def test_h08_and_t02_no_llm_provider_imported_or_called():
    source = Path(heavy_validation_runner.__file__).read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_IMPORTS:
        assert forbidden not in source
    for module in ("openai", "anthropic", "litellm"):
        assert module not in sys.modules


def test_all_gates_not_configured_is_blocked_not_pass():
    with mock.patch.object(heavy_validation_runner, "_run_gate", return_value=4):
        rc = heavy_validation_runner.run(available_gib_override=7.5)

    assert rc == 5
    data = _read_summary()
    assert data["terminal_state"] == "BLOCKED"
    assert all(g["status"] == "NOT_CONFIGURED" for g in data["gates"])
    assert data["not_configured"] == list(heavy_validation_runner.HEAVY_GATE_ORDER)
    assert data["required_core_gates"]["pytest"] == "NOT_CONFIGURED"


def test_heavy_report_separates_failures_and_not_configured():
    def gate_result(gate: str) -> int:
        if gate == "pytest":
            return 1
        if gate == "sonar":
            return 4
        return 0

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=gate_result):
        assert heavy_validation_runner.run(available_gib_override=7.5) == 1
    data = _read_summary()
    assert data["configured_failures"] == ["pytest"]
    assert data["not_configured"] == ["sonar"]


def test_heavy_order_includes_security_and_smoke():
    order = heavy_validation_runner.HEAVY_GATE_ORDER
    assert order[:4] == ["pytest", "security", "smoke", "e2e"]
    assert "security" in order and "smoke" in order
    # e2e appears exactly once and the playwright duplicate is gone
    assert order.count("e2e") == 1
    assert "playwright" not in order


def test_below_four_gib_starts_no_heavy_child_process():
    calls: list[str] = []

    def _spy(gate: str) -> int:
        calls.append(gate)
        raise AssertionError("no heavy gate may start below 4.0 GiB")

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=_spy):
        rc = heavy_validation_runner.run(available_gib_override=3.99)

    assert rc == 3
    assert calls == []
    assert _read_summary()["terminal_state"] == "ENV_BLOCKED"


def test_allowed_ram_runs_security_and_smoke_in_order():
    seen: list[str] = []

    def _ok(gate: str) -> int:
        seen.append(gate)
        return 0

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=_ok):
        rc = heavy_validation_runner.run(available_gib_override=6.01)

    assert rc == 0
    assert seen == heavy_validation_runner.HEAVY_GATE_ORDER
    assert "security" in seen and "smoke" in seen
    assert seen.count("e2e") == 1


def test_ram_policy_boundaries_and_low_memory_serial_mode():
    from scripts import ram_gate

    assert ram_gate.evaluate(3.99) == ram_gate.ENV_BLOCKED
    assert ram_gate.evaluate(4.0) == ram_gate.LOW_MEMORY_SERIAL
    assert ram_gate.evaluate(5.99) == ram_gate.LOW_MEMORY_SERIAL
    assert ram_gate.evaluate(6.0) == ram_gate.ALLOWED


def test_low_memory_mode_rechecks_before_each_gate_and_stops_below_four():
    measured = iter((5.2, 4.8, 3.9))
    invoked = []
    with mock.patch.object(heavy_validation_runner.ram_gate, "measure_available_bytes",
                           side_effect=lambda: next(measured) * heavy_validation_runner.ram_gate.GIB):
        with mock.patch.object(heavy_validation_runner, "_run_gate",
                               side_effect=lambda gate: invoked.append(gate) or 0):
            rc = heavy_validation_runner.run(gates=["pytest", "security"])

    assert rc == 3
    assert invoked == ["pytest"]
    report = _read_summary()
    assert report["terminal_state"] == "ENV_BLOCKED"
    assert report["gates"][0]["ram_before_gib"] == 4.8
    assert report["reason"] == "available RAM below 4.0 GiB before security"


def test_standard_mode_rechecks_ram_before_next_gate_after_memory_drop():
    measured = iter((6.8, 6.2, 3.9))
    invoked = []
    with mock.patch.object(heavy_validation_runner.ram_gate, "measure_available_bytes",
                           side_effect=lambda: next(measured) * heavy_validation_runner.ram_gate.GIB):
        with mock.patch.object(heavy_validation_runner, "_run_gate",
                               side_effect=lambda gate: invoked.append(gate) or 0):
            rc = heavy_validation_runner.run(gates=["docker-build", "docker-e2e"])

    assert rc == 3
    assert invoked == ["docker-build"]
    report = _read_summary()
    assert report["terminal_state"] == "ENV_BLOCKED"
    assert report["gates"][0]["ram_mode"] == heavy_validation_runner.ram_gate.ALLOWED
    assert report["reason"] == "available RAM below 4.0 GiB before docker-e2e"


def test_standard_mode_transitions_to_low_memory_serial_between_gates():
    measured = iter((6.8, 5.7, 5.4))
    invoked = []
    with mock.patch.object(heavy_validation_runner.ram_gate, "measure_available_bytes",
                           side_effect=lambda: next(measured) * heavy_validation_runner.ram_gate.GIB):
        with mock.patch.object(heavy_validation_runner, "_run_gate",
                               side_effect=lambda gate: invoked.append(gate) or 0):
            rc = heavy_validation_runner.run(gates=["pytest", "security"])

    assert rc == 0
    assert invoked == ["pytest", "security"]
    report = _read_summary()
    assert report["ram_mode"] == heavy_validation_runner.ram_gate.LOW_MEMORY_SERIAL
    assert [gate["ram_mode"] for gate in report["gates"]] == ["LOW_MEMORY_SERIAL", "LOW_MEMORY_SERIAL"]
