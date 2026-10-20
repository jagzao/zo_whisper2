from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from scripts import validation_env


def test_fingerprint_tracks_lockfile_and_python_minor(tmp_path, monkeypatch):
    lock = tmp_path / "requirements.lock.txt"
    lock.write_text("pytest==8.0\n", encoding="utf-8")
    monkeypatch.setattr(validation_env, "LOCK_PATH", lock)
    first = validation_env.fingerprint()
    lock.write_text("pytest==8.1\n", encoding="utf-8")
    assert validation_env.fingerprint() != first


def test_ensure_reuses_matching_environment(tmp_path, monkeypatch):
    env_dir = tmp_path / ".venv-validation"
    executable = env_dir / "Scripts" / "python.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"python")
    lock = tmp_path / "requirements.lock.txt"
    lock.write_text("pytest==8.0\n", encoding="utf-8")
    stamp = env_dir / ".validation-fingerprint"
    monkeypatch.setattr(validation_env, "ENV_PATH", env_dir)
    monkeypatch.setattr(validation_env, "LOCK_PATH", lock)
    monkeypatch.setattr(validation_env, "STAMP_PATH", stamp)
    stamp.write_text(validation_env.fingerprint(), encoding="ascii")

    with mock.patch.object(validation_env.venv.EnvBuilder, "create", side_effect=AssertionError("must reuse")), \
            mock.patch.object(validation_env.subprocess, "run", side_effect=AssertionError("must not install")):
        assert validation_env.ensure() == executable


def test_ensure_installs_lock_only_in_local_venv(tmp_path, monkeypatch):
    env_dir = tmp_path / ".venv-validation"
    lock = tmp_path / "requirements.lock.txt"
    lock.write_text("pytest==8.0\n", encoding="utf-8")
    monkeypatch.setattr(validation_env, "ENV_PATH", env_dir)
    monkeypatch.setattr(validation_env, "LOCK_PATH", lock)
    monkeypatch.setattr(validation_env, "STAMP_PATH", env_dir / ".validation-fingerprint")

    def create(_builder, path):
        executable = Path(path) / "Scripts" / "python.exe"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"python")

    monkeypatch.setattr(validation_env.venv.EnvBuilder, "create", create)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(validation_env.subprocess, "run", run)
    assert validation_env.ensure() == env_dir / "Scripts" / "python.exe"
    assert calls[0][0][-3:] == ["--disable-pip-version-check", "-r", str(lock)]
    assert calls[0][1]["cwd"] == validation_env.ROOT
    assert validation_env.status()["ready"] is True


def test_dependency_smoke_imports_all_required_modules(monkeypatch):
    imported = []
    monkeypatch.setattr(
        validation_env.importlib,
        "import_module",
        lambda name: (imported.append(name) or type("Module", (), {"__version__": "1"})()),
    )
    assert set(validation_env.dependency_smoke()) == {
        "pytest", "markitdown", "openpyxl", "pptx", "transcript_pipeline"
    }
    assert set(imported) == {"pytest", "markitdown", "openpyxl", "pptx", "transcript_pipeline"}


def test_playwright_installer_runs_only_when_chromium_missing(monkeypatch, tmp_path):
    executable = tmp_path / "chromium.exe"
    class Chromium:
        executable_path = str(executable)
    class Playwright:
        chromium = Chromium()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
    monkeypatch.setitem(__import__("sys").modules, "playwright", type("P", (), {})())
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.async_api",
        type("A", (), {"async_playwright": staticmethod(lambda: Playwright())})(),
    )

    def install(args, **kwargs):
        executable.write_bytes(b"browser")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(validation_env.subprocess, "run", install)
    assert validation_env.ensure_playwright_chromium() is True
    with mock.patch.object(validation_env.subprocess, "run", side_effect=AssertionError("already installed")):
        assert validation_env.ensure_playwright_chromium() is False


def test_chromium_probe_exits_without_pending_task_warnings():
    pytest.importorskip("playwright")
    code = (
        "from scripts import validation_env\n"
        "print(validation_env._read_chromium_executable_path())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=validation_env.ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = f"{result.stdout}\n{result.stderr}"
    assert "TargetClosedError" not in output
    assert "Task was destroyed but it is pending" not in output
    assert "Future exception was never retrieved" not in output
    assert "was never awaited" not in output
