"""PLV5 heavy validation runner tests (TEST-MATRIX PLV5-H04..H08, T02)."""
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
def _clean_summary():
    if SUMMARY_PATH.exists():
        SUMMARY_PATH.unlink()
    yield
    if SUMMARY_PATH.exists():
        SUMMARY_PATH.unlink()


def test_h04_deferred_run_starts_no_heavy_child():
    calls: list[str] = []

    def _forbidden_gate(gate):
        calls.append(gate)
        raise AssertionError("deferred run must not start any heavy gate")

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=_forbidden_gate):
        with mock.patch.object(
            heavy_validation_runner.gate_runner.subprocess, "run", side_effect=_forbidden_gate
        ):
            rc = heavy_validation_runner.run(available_gib_override=5.0)

    assert rc == 3
    assert calls == []
    data = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    assert data["terminal_state"] == "DEFERRED_LOW_RAM"
    assert data["gates"] == []
    assert data["ram"]["heavy_validation"] == "DEFERRED_LOW_RAM"


def test_h05_allowed_run_invokes_configured_heavy_gates():
    invoked: list[str] = []

    def _fake_gate(gate):
        invoked.append(gate)
        return 0

    with mock.patch.object(heavy_validation_runner, "_run_gate", side_effect=_fake_gate):
        rc = heavy_validation_runner.run(available_gib_override=7.5)

    assert rc == 0
    assert invoked == list(heavy_validation_runner.HEAVY_GATE_ORDER)
    data = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    assert data["terminal_state"] == "PASS"
    assert all(g["status"] == "PASS" for g in data["gates"])


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
    data = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
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
    data = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    assert data["terminal_state"] == "BLOCKED"
    assert all(g["status"] == "NOT_CONFIGURED" for g in data["gates"])
