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
    assert data["runner"] == "scripts/gate_runner.py"


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

    def _run_and_write_report(*_args, **_kwargs):
        report_path.write_text(
            json.dumps(
                {
                    "checks": [
                        {"name": "ruff_lint", "status": "FAIL", "detail": "boom: bad import"}
                    ],
                    "ok": False,
                }
            ),
            encoding="utf-8",
        )
        return _FakeCompleted(1, "", "")

    try:
        with mock.patch.object(gate_runner.subprocess, "run", side_effect=_run_and_write_report):
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


def test_stale_structured_report_is_not_reused():
    report_path = ROOT / "quality_report.json"
    original = report_path.read_text(encoding="utf-8") if report_path.exists() else None
    report_path.write_text(
        json.dumps({"checks": [{"name": "old_failure", "status": "FAIL", "detail": "stale"}], "ok": False}),
        encoding="utf-8",
    )
    try:
        with mock.patch.object(
            gate_runner.subprocess,
            "run",
            return_value=_FakeCompleted(1, "", "current process failed before writing report"),
        ):
            rc = gate_runner.run_gate("quality")
    finally:
        if original is None:
            report_path.unlink(missing_ok=True)
        else:
            report_path.write_text(original, encoding="utf-8")

    assert rc == 1
    data = _read_latest()
    assert data["check"] == "quality"
    assert data["error_signature"] == "current process failed before writing report"
