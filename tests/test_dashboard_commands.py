"""Unit tests for WP-03 command construction: the dashboard RUN endpoints
must invoke installed package modules (`python -m transcript_pipeline...`)
with the current interpreter, never repo-root script names nor cwd-based
resolution. No real subprocess/transcription runs — subprocess.Popen is
monkeypatched with fakes (same pattern as test_dashboard_new_endpoints.py).
"""
from __future__ import annotations

import subprocess
import sys
import time

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}

COMPRESSOR_CMD = [sys.executable, "-m", "transcript_pipeline.media.compressor"]
MASTER_CMD = [sys.executable, "-m", "transcript_pipeline.pipeline.master"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    audio = tmp_path / "audio"
    videos = tmp_path / "Videos"
    video_compress = tmp_path / "Video_compress"
    transcriptions = tmp_path / "CarpetaTranscripciones"
    for d in (audio, videos, video_compress, transcriptions):
        d.mkdir(parents=True)

    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "LOG_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", audio)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", video_compress)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcriptions)
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", AUTH_HEADERS["X-Local-Dashboard-Token"])
    monkeypatch.setattr(
        dashboard_app,
        "RESOLVER",
        SafePathResolver(
            {
                MediaRoot.AUDIO: audio,
                MediaRoot.VIDEOS: videos,
                MediaRoot.VIDEO_COMPRESS: video_compress,
                MediaRoot.TRANSCRIPTIONS: transcriptions,
            }
        ),
    )
    return {"root": tmp_path, "audio": audio, "videos": videos, "transcriptions": transcriptions}


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


class _FakeCompletedProcess:
    def __init__(self, lines: list[str]):
        self._lines = lines
        self.returncode = 0

    @property
    def stdout(self):
        def _gen():
            for line in self._lines:
                yield line
        return _gen()

    def wait(self) -> int:
        return self.returncode


def _install_fake_popen(monkeypatch, calls, kwargs_list=None):
    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        if kwargs_list is not None:
            kwargs_list.append(kwargs)
        return _FakeCompletedProcess(["stub line\n"])

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)


def _wait_until_finished(client):
    status = None
    for _ in range(50):
        status = client.get("/api/status").get_json()
        if not status["running"]:
            break
        time.sleep(0.05)
    return status


# ── /api/run/full: both module commands ───────────────────────────────────

def test_run_full_builds_module_commands(client, env, monkeypatch):
    calls = []
    _install_fake_popen(monkeypatch, calls)

    resp = client.post("/api/run/full", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    status = _wait_until_finished(client)
    assert status["running"] is False

    assert len(calls) == 2
    assert calls[0] == COMPRESSOR_CMD
    assert calls[1] == MASTER_CMD
    for cmd in calls:
        assert cmd[0] == sys.executable
        assert not any(str(part).endswith(".py") for part in cmd)


# ── /api/run/compress: compressor module only ─────────────────────────────

def test_run_compress_only_builds_only_compressor_module(client, env, monkeypatch):
    calls = []
    _install_fake_popen(monkeypatch, calls)

    resp = client.post("/api/run/compress", headers=AUTH_HEADERS)
    assert resp.status_code == 200

    status = _wait_until_finished(client)
    assert status["running"] is False

    assert calls == [COMPRESSOR_CMD]


# ── /api/run/transcribe: master module only ───────────────────────────────

def test_run_transcribe_only_builds_only_master_module(client, env, monkeypatch):
    calls = []
    _install_fake_popen(monkeypatch, calls)

    resp = client.post("/api/run/transcribe", headers=AUTH_HEADERS)
    assert resp.status_code == 200

    status = _wait_until_finished(client)
    assert status["running"] is False

    assert calls == [MASTER_CMD]


# ── Popen kwargs: streaming flags preserved, no cwd coupling ──────────────

def test_popen_preserves_streaming_and_cwd_independence(client, env, monkeypatch):
    calls = []
    kwargs_list = []
    _install_fake_popen(monkeypatch, calls, kwargs_list)

    resp = client.post("/api/run/transcribe", headers=AUTH_HEADERS)
    assert resp.status_code == 200

    status = _wait_until_finished(client)
    assert status["running"] is False

    assert len(kwargs_list) == 1
    kwargs = kwargs_list[0]
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.STDOUT
    assert kwargs["text"] is True
    assert kwargs.get("cwd") is None
