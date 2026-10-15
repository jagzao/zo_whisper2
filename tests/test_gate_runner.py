"""Deterministic tests for the compact gate runner (US-PLV4-001 WP-01).

AC-1: named runner emits valid compact JSON for PASS and FAIL.
AC-2: it invokes existing scripts, it does not duplicate their logic.
AC-6: repeated validation makes zero LLM/provider calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import gate_runner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "artifacts" / "gates" / "latest.json"


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _clean_latest():
    if LATEST_PATH.exists():
        LATEST_PATH.unlink()
    yield
    if LATEST_PATH.exists():
        LATEST_PATH.unlink()


def _read_latest() -> dict:
    return json.loads(LATEST_PATH.read_text(encoding="utf-8"))


def test_pass_emits_valid_compact_json():
    with mock.patch.object(gate_runner.subprocess, "run", return_value=_FakeCompleted(0, "ok", "")):
        rc = gate_runner.run_gate("pytest")

    assert rc == 0
    data = _read_latest()
    assert data["status"] == "PASS"
    assert data["gate"] == "pytest"
    assert data["check"] == "pytest"
    assert data["error_signature"] == ""
    assert data["affected_files"] == []
    assert data["artifact"] == "artifacts/gates/logs/pytest.log"
    assert isinstance(data["duration_seconds"], float)
    assert data["command"].endswith("-m pytest tests/ -q")


def test_fail_emits_valid_compact_json_with_signature():
    with mock.patch.object(
        gate_runner.subprocess, "run", return_value=_FakeCompleted(1, "", "E   assert 1 == 0\n1 failed")
    ):
        rc = gate_runner.run_gate("pytest")

    assert rc == 1
    data = _read_latest()
    assert data["status"] == "FAIL"
    assert data["gate"] == "pytest"
    assert data["check"] == "pytest"
    assert data["error_signature"] == "1 failed"
    assert data["artifact"] == "artifacts/gates/logs/pytest.log"


def test_fail_extracts_structured_report():
    report_path = ROOT / "quality_report.json"
    original = report_path.read_text(encoding="utf-8") if report_path.exists() else None
    report_path.write_text(
        json.dumps({"checks": [{"name": "ruff_lint", "status": "FAIL", "detail": "boom: bad import"}], "ok": False}),
        encoding="utf-8",
    )
    try:
        with mock.patch.object(gate_runner.subprocess, "run", return_value=_FakeCompleted(1, "", "")):
            rc = gate_runner.run_gate("quality")
    finally:
        if original is None:
            report_path.unlink(missing_ok=True)
        else:
            report_path.write_text(original, encoding="utf-8")

    assert rc == 1
    data = _read_latest()
    assert data["status"] == "FAIL"
    assert data["check"] == "ruff_lint"
    assert data["error_signature"].startswith("boom")


def test_unknown_gate_returns_2_and_writes_no_artifact():
    rc = gate_runner.run_gate("nope")
    assert rc == 2
    assert not LATEST_PATH.exists()


def test_targeted_gate_requires_paths():
    assert gate_runner.run_gate("targeted") == 2


def test_named_gate_registry_uses_authoritative_commands():
    assert {"quality", "security", "smoke", "e2e", "sonar"} <= gate_runner.GATES.keys()
    assert gate_runner.GATES["quality"][-1] == "scripts/quality.py"
    assert gate_runner.GATES["security"][-1] == "scripts/security.py"
    assert gate_runner.GATES["smoke"][-1] == "scripts/smoke.py"
    assert gate_runner.GATES["e2e"][-1] == "scripts/e2e.py"
    for gate in ("docker-build", "docker-e2e"):
        assert gate_runner.GATES[gate][:2] == [sys.executable, "scripts/docker_gate.py"]
        assert "watcher/docker-compose.yml" not in gate_runner.GATES[gate]


def test_playwright_alias_removed_so_e2e_runs_once():
    # `playwright` was a duplicate alias of `e2e` (same command). It must be gone
    # so the full E2E never runs twice, and exactly one gate maps to e2e.py.
    assert "playwright" not in gate_runner.GATES
    e2e_commands = [cmd for cmd in gate_runner.GATES.values() if cmd[-1] == "scripts/e2e.py"]
    assert len(e2e_commands) == 1


def test_gate_categories_split_implementation_from_heavy():
    heavy = {"pytest", "security", "smoke", "e2e", "sonar", "docker-build", "docker-e2e", "jenkins", "soak"}
    light = {"targeted", "unit", "lint", "quality", "typecheck"}
    assert heavy <= gate_runner.HEAVY_GATES
    assert light <= gate_runner.LIGHT_GATES
    assert not (gate_runner.HEAVY_GATES & gate_runner.LIGHT_GATES)
    for gate in heavy | light:
        assert gate_runner.category_of(gate) in ("light", "heavy")
    assert gate_runner.category_of("e2e") == "heavy"
    assert gate_runner.category_of("targeted") == "light"


def test_security_and_smoke_are_not_light_gates():
    # Frozen V5 split: security and smoke are heavy-only. They must never be
    # selectable as implementation/light gates.
    for gate in ("security", "smoke"):
        assert gate not in gate_runner.LIGHT_GATES
        assert gate in gate_runner.HEAVY_GATES
        assert gate_runner.category_of(gate) == "heavy"
    assert gate_runner.LIGHT_GATES == frozenset(
        {"targeted", "unit", "lint", "quality", "typecheck"}
    )


def test_not_configured_gate_is_never_reported_as_pass():
    # sonar-scanner is not installed in this repo's dev environment; if it ever
    # IS on PATH this test asserts the stronger property directly via stubbing.
    with mock.patch.object(gate_runner, "_command_is_configured", return_value=False):
        with mock.patch.object(
            gate_runner.subprocess, "run", side_effect=AssertionError("must not spawn")
        ):
            rc = gate_runner.run_gate("sonar")

    assert rc == 4
    data = _read_latest()
    assert data["status"] == "NOT_CONFIGURED"
    assert data["category"] == "heavy"


def test_list_registry_reports_categories():
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert gate_runner.main(["--list"]) == 0
    registry = json.loads(buffer.getvalue())
    assert registry["e2e"]["category"] == "heavy"
    assert registry["quality"]["category"] == "light"


def test_gate_runner_imports_no_provider_sdk():
    source = (ROOT / "scripts" / "gate_runner.py").read_text(encoding="utf-8")
    for forbidden in ("import openai", "import anthropic", "import requests", "import httpx", "import litellm"):
        assert forbidden not in source


def test_no_llm_calls_on_repeat_with_network_disabled():
    def _no_socket(*_args, **_kwargs):
        raise AssertionError("gate runner must not open a network socket")

    with mock.patch.object(gate_runner.subprocess, "run", return_value=_FakeCompleted(0, "ok", "")):
        with mock.patch("socket.socket", side_effect=_no_socket):
            rc = gate_runner.run_gate("pytest")

    assert rc == 0
    assert _read_latest()["status"] == "PASS"


def test_duration_seconds_rounded():
    with mock.patch.object(gate_runner.subprocess, "run", return_value=_FakeCompleted(0, "ok", "")):
        with mock.patch.object(gate_runner.time, "monotonic", side_effect=[1.0, 2.234]):
            rc = gate_runner.run_gate("pytest")

    assert rc == 0
    assert _read_latest()["duration_seconds"] == 1.23


def test_validation_environment_prepends_src_and_sanitizes_host_values(tmp_path):
    env = gate_runner.validation_environment(
        "pytest",
        {
            "PYTHONPATH": "existing-path",
            "DASHBOARD_HOST": "0.0.0.0",
            "ZMI_CONTAINER_MODE": "true",
            "ALLOW_EXTERNAL_LLM": "true",
            "SENSITIVE_IDENTIFIERS": "private-value",
        },
    )

    assert env["PYTHONPATH"].split(gate_runner.os.pathsep) == [str(ROOT / "src"), "existing-path"]
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["DASHBOARD_HOST"] == "127.0.0.1"
    assert env["ZMI_CONTAINER_MODE"] == "false"
    assert env["ALLOW_EXTERNAL_LLM"] == "false"
    assert env["SENSITIVE_IDENTIFIERS"] == "private-value"
    assert not Path(env["ZMI_CONFIG_ENV"]).exists()


def test_gate_environment_imports_transcript_pipeline():
    import subprocess

    result = subprocess.run(
        [sys.executable, "-c", "import transcript_pipeline; print(transcript_pipeline.__name__)"],
        cwd=ROOT,
        env=gate_runner.validation_environment("pytest", {}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "transcript_pipeline"


def test_subprocess_capture_is_utf8_and_replaces_invalid_output(monkeypatch):
    monkeypatch.setitem(gate_runner.GATES, "pytest", [sys.executable, "-c", "print('Prueba: café')"])
    with mock.patch.object(gate_runner, "_command_is_configured", return_value=True):
        assert gate_runner.run_gate("pytest") == 0
    log = (ROOT / "artifacts" / "gates" / "logs" / "pytest.log").read_text(encoding="utf-8")
    assert "café" in log


def test_e2e_validation_environment_forces_host_mode_and_isolated_roots():
    env = gate_runner.validation_environment("e2e", {"ZMI_E2E_EXTERNAL_SERVER": "1"})
    assert env["ZMI_E2E_EXTERNAL_SERVER"] == "0"
    assert env["ZMI_DATA_ROOT"] == str(ROOT / "artifacts" / "gates" / "e2e-host-data")
    assert env["ZMI_TEST_DATA_ROOT"] == env["ZMI_DATA_ROOT"]
