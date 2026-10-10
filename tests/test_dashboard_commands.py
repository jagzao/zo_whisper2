"""Unit tests for WP-03 command construction: the dashboard RUN endpoints
must invoke installed package modules (`python -m transcript_pipeline...`)
with the current interpreter, never repo-root script names nor cwd-based
resolution. No real subprocess/transcription runs — subprocess.Popen is
monkeypatched with fakes (same pattern as test_dashboard_new_endpoints.py).
"""
from __future__ import annotations

import io
import subprocess
import sys
import threading
import time
from pathlib import Path

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
    monkeypatch.setattr(dashboard_app, "_queue_worker_active", False)
    monkeypatch.setattr(
        dashboard_app,
        "_run_state",
        {"running": False, "queued": False, "stages": {}},
    )
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
            yield from self._lines
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


def test_upload_waits_for_approval_then_starts_full_pipeline(client, env, monkeypatch):
    calls = []
    _install_fake_popen(monkeypatch, calls)
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", lambda _: True)

    response = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(b"media"), "pg_meeting.mp4")},
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["processing"] == "awaiting_approval"
    upload_id = response.get_json()["upload_id"]
    assert (env["root"] / ".upload_sessions" / f"{upload_id}.part").read_bytes() == b"media"
    assert not (env["root"] / "Video_compress" / "pg_meeting.mp4").exists()
    held = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(b"held"), "other.mp4")},
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    ).get_json()

    queued = client.post(
        "/api/run/full", json={"upload_ids": [upload_id]}, headers=AUTH_HEADERS
    )
    assert queued.get_json()["processing"] == "started"
    status = _wait_until_finished(client)
    assert status["running"] is False
    assert calls == [COMPRESSOR_CMD, MASTER_CMD]
    listed = client.get("/api/files").get_json()["files"]
    assert len(listed) == 1
    assert listed[0]["name"] == "pg_meeting.mp4"
    assert Path(listed[0]["relative"]) == Path("Video_compress") / "pg_meeting.mp4"
    assert listed[0]["media_id"].startswith("video_compress:")
    assert (env["root"] / ".upload_sessions" / f"{held['upload_id']}.part").exists()


def test_upload_during_run_queues_full_followup(client, env, monkeypatch):
    first_command_started = threading.Event()
    release_first_command = threading.Event()
    calls = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            first_command_started.set()
            assert release_first_command.wait(timeout=5)
        return _FakeCompletedProcess(["stub line\n"])

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", lambda _: True)

    response = client.post("/api/run/transcribe", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert first_command_started.wait(timeout=2)

    upload = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(b"media"), "pg_second.mp4")},
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )
    assert upload.get_json()["processing"] == "awaiting_approval"
    assert client.get("/api/status").get_json()["queued"] is False
    queue_request = client.post(
        "/api/run/full", json={"upload_ids": [upload.get_json()["upload_id"]]}, headers=AUTH_HEADERS
    )
    assert queue_request.get_json()["processing"] == "queued"
    assert client.get("/api/status").get_json()["queued"] is True

    release_first_command.set()
    status = _wait_until_finished(client)
    assert status["running"] is False
    assert calls == [MASTER_CMD, COMPRESSOR_CMD, MASTER_CMD]


def test_pending_media_is_detected_for_startup_recovery(client, env):
    sessions = env["root"] / ".upload_sessions"
    sessions.mkdir(exist_ok=True)
    upload_id = "a" * 32
    (sessions / f"{upload_id}.part").write_bytes(b"staged")
    (sessions / f"{upload_id}.json").write_text(
        '{"filename":"unapproved.mp4","size":6,"received":6,"ready_for_processing":true}'
    )
    assert dashboard_app._has_pending_media() is False
    queued = env["root"] / "Video_compress" / "pending.mp4"
    queued.write_bytes(b"pending")

    assert dashboard_app._has_pending_media() is True


def test_resumable_upload_waits_for_approval_before_processing(client, env, monkeypatch):
    calls = []
    _install_fake_popen(monkeypatch, calls)
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", lambda _: True)
    payload = b"sample media bytes"
    created = client.post(
        "/api/upload-sessions",
        json={"filename": "pg_meeting.mp4", "size": len(payload)},
        headers=AUTH_HEADERS,
    )
    upload_id = created.get_json()["upload_id"]
    chunk = client.put(
        f"/api/upload-sessions/{upload_id}",
        data=payload,
        headers={**AUTH_HEADERS, "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}"},
    )
    assert chunk.status_code == 200

    complete = client.post(
        f"/api/upload-sessions/{upload_id}/complete", json={}, headers=AUTH_HEADERS
    )
    assert complete.status_code == 200
    assert complete.get_json()["processing"] == "awaiting_approval"
    assert (env["root"] / ".upload_sessions" / f"{upload_id}.part").read_bytes() == payload
    assert not (env["root"] / "Video_compress" / "pg_meeting.mp4").exists()

    queue_request = client.post(
        "/api/run/full", json={"upload_ids": [upload_id]}, headers=AUTH_HEADERS
    )
    assert queue_request.get_json()["processing"] == "started"
    assert (env["root"] / "Video_compress" / "pg_meeting.mp4").read_bytes() == payload
    assert _wait_until_finished(client)["running"] is False
    assert calls == [COMPRESSOR_CMD, MASTER_CMD]


def test_audio_upload_goes_to_scanned_audio_root(client, env, monkeypatch):
    calls = []
    _install_fake_popen(monkeypatch, calls)
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", lambda _: True)
    response = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(b"audio"), "meeting.mp3")},
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["processing"] == "awaiting_approval"
    assert not (env["audio"] / "meeting.mp3").exists()
    client.post("/api/run/full", headers=AUTH_HEADERS)
    assert (env["audio"] / "meeting.mp3").exists()
    assert not (env["root"] / "Video_compress" / "meeting.mp3").exists()
