"""Deterministic tests for the delivery wrapper (DELTA-ZMI-DKR-002 section C).

Proves: frozen execution order, independent-failure continuation, forced
LLM-off environment, isolated host E2E data root, always-run summary,
summary-driven exit status, prerequisite-based SKIPPED, and zero
Jenkins/network/LLM calls issued by the wrapper itself.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import run_delivery  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEST_BUILD = "unittest-run-delivery"

EXPECTED_ORDER = (
    "targeted",
    "pytest",
    "quality",
    "security",
    "docker-config",
    "docker-build",
    "docker-smoke",
    "docker-persistence",
    "docker-asr-smoke",
    "e2e",
    "docker-e2e",
)


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture()
def delivery_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"BUILD_NUMBER", "BUILD_ID", "ALLOW_EXTERNAL_LLM"}
    }
    env["BUILD_NUMBER"] = TEST_BUILD
    yield env
    shutil.rmtree(run_delivery.build_dir(TEST_BUILD), ignore_errors=True)


def _record(fake_run: mock.MagicMock) -> list[tuple[list[str], dict[str, str]]]:
    calls: list[tuple[list[str], dict[str, str]]] = []
    for call in fake_run.call_args_list:
        cmd = list(call.args[0]) if call.args else list(call.kwargs["cmd"])
        calls.append((cmd, call.kwargs.get("env") or {}))
    return calls


def _gate_names(calls: list[tuple[list[str], dict[str, str]]]) -> list[str]:
    return [cmd[2] for cmd, _ in calls if len(cmd) >= 3 and Path(cmd[1]).name != "summarize_gates.py"]


def test_execution_order_is_frozen(delivery_env):
    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(0)) as fake:
        rc = run_delivery.run_delivery(delivery_env)

    calls = _record(fake)
    assert _gate_names(calls) == list(EXPECTED_ORDER)
    assert calls[-1][0][1].endswith("summarize_gates.py")
    assert "--email-status" in calls[-1][0] and "NOT_CONFIGURED" in calls[-1][0]
    assert rc == 0


def test_independent_gate_failure_does_not_stop_later_gates(delivery_env):
    def fake_run(cmd, **_kwargs):
        if len(cmd) > 2 and cmd[2] == "targeted":
            return _FakeCompleted(1, "", "1 failed")
        return _FakeCompleted(0)

    with mock.patch.object(run_delivery.subprocess, "run", side_effect=fake_run) as fake:
        run_delivery.run_delivery(delivery_env)

    # Every gate was still attempted (nothing after the failure was dropped).
    assert _gate_names(_record(fake)) == list(EXPECTED_ORDER)
    # The failure only reaches the exit code through the real summary process.
    assert any(cmd[1].endswith("summarize_gates.py") for cmd, _ in _record(fake))


def test_environment_forces_external_llm_off(delivery_env):
    delivery_env["ALLOW_EXTERNAL_LLM"] = "true"
    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(0)) as fake:
        run_delivery.run_delivery(delivery_env)

    for cmd, env in _record(fake):
        if len(cmd) >= 3 and Path(cmd[1]).name != "summarize_gates.py":
            assert env["ALLOW_EXTERNAL_LLM"] == "false"
            assert env["BUILD_NUMBER"] == TEST_BUILD
            assert env["BUILD_ID"] == TEST_BUILD


def test_isolated_e2e_data_root_is_used(delivery_env):
    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(0)) as fake:
        run_delivery.run_delivery(delivery_env)

    calls = _record(fake)
    e2e_env = next(env for cmd, env in calls if len(cmd) > 2 and cmd[2] == "e2e")
    expected_root = run_delivery.build_dir(TEST_BUILD) / "host-e2e-data"
    assert e2e_env["ZMI_DATA_ROOT"] == str(expected_root)
    assert e2e_env["ZMI_TEST_DATA_ROOT"] == str(expected_root)
    assert e2e_env["ZMI_CONFIG_ENV"] == str(expected_root / "scan_config.env")
    assert e2e_env["DASHBOARD_HOST"] == "127.0.0.1"
    assert e2e_env["DASHBOARD_PORT"] == "5500"
    assert e2e_env["ZMI_BASE_URL"] == "http://127.0.0.1:5500"
    assert (expected_root / "projects.json").exists()
    assert any(cmd[1].endswith("generate_mock_data.py") for cmd, _ in calls)


def test_host_e2e_port_override_is_respected(delivery_env):
    delivery_env["DASHBOARD_PORT"] = "5599"
    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(0)) as fake:
        run_delivery.run_delivery(delivery_env)

    e2e_env = next(env for cmd, env in _record(fake) if len(cmd) > 2 and cmd[2] == "e2e")
    assert e2e_env["DASHBOARD_PORT"] == "5599"
    assert e2e_env["ZMI_BASE_URL"] == "http://127.0.0.1:5599"


def test_summary_always_runs_even_when_gates_fail(delivery_env):
    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(1)) as fake:
        rc = run_delivery.run_delivery(delivery_env)

    calls = _record(fake)
    assert calls[-1][0][1].endswith("summarize_gates.py")
    assert rc == 1


def test_exit_status_follows_summary(delivery_env):
    def fake_run(cmd, **_kwargs):
        if cmd[1].endswith("summarize_gates.py"):
            return _FakeCompleted(3)
        return _FakeCompleted(0)

    with mock.patch.object(run_delivery.subprocess, "run", side_effect=fake_run):
        assert run_delivery.run_delivery(delivery_env) == 3

    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(0)):
        assert run_delivery.run_delivery(delivery_env) == 0


def test_prerequisite_failure_skips_dependents_and_continues(delivery_env):
    def fake_run(cmd, **_kwargs):
        if len(cmd) > 2 and cmd[2] == "docker-config":
            return _FakeCompleted(1, "", "compose config invalid")
        return _FakeCompleted(0)

    with mock.patch.object(run_delivery.subprocess, "run", side_effect=fake_run) as fake:
        rc = run_delivery.run_delivery(delivery_env)

    ran = _gate_names(_record(fake))
    assert "docker-config" in ran
    assert "docker-build" not in ran
    dependents = ("docker-build", "docker-smoke", "docker-persistence", "docker-asr-smoke", "docker-e2e")
    build_dir = run_delivery.build_dir(TEST_BUILD)
    expected_reason = {
        "docker-build": "prerequisite docker-config status=FAIL",
        "docker-smoke": "prerequisite docker-build status=SKIPPED",
        "docker-persistence": "prerequisite docker-build status=SKIPPED",
        "docker-asr-smoke": "prerequisite docker-build status=SKIPPED",
        "docker-e2e": "prerequisite docker-build status=SKIPPED",
    }
    for gate in dependents:
        report = json.loads((build_dir / f"{gate}.json").read_text(encoding="utf-8"))
        assert report["status"] == "SKIPPED"
        assert report["check"] == "prerequisite-failed"
        assert report["error_signature"] == expected_reason[gate]


def test_mock_data_cleanup_always_runs(delivery_env):
    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(1)) as fake:
        run_delivery.run_delivery(delivery_env)

    assert any(cmd[1].endswith("cleanup_mock_data.py") for cmd, _ in _record(fake))


def test_wrapper_never_calls_jenkins_network_or_llm(delivery_env):
    with mock.patch.object(run_delivery.subprocess, "run", return_value=_FakeCompleted(0)) as fake:
        run_delivery.run_delivery(delivery_env)

    for cmd, env in _record(fake):
        joined = " ".join(cmd).lower()
        assert "jenkins" not in joined
        assert "http" not in joined
        assert "curl" not in joined
        if len(cmd) >= 3 and Path(cmd[1]).name != "summarize_gates.py":
            assert env.get("ALLOW_EXTERNAL_LLM") == "false"
    for banned in ("urllib", "socket", "requests", "httpx", "http.client"):
        assert banned not in run_delivery.__dict__
