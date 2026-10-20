"""Focused Flask API tests for the W8 late transcript association endpoint.

Same isolated-tmp-path fixture pattern as tests/test_dashboard_capture_api.py:
the dashboard resolves VIDEOS_BASE (and friends) under a per-test tmp dir, and
the association is exercised through the real Flask route — auth required,
validation, availability/TRANSCRIPT_REQUIRED clearing, and durable persistence
(manifest + transcript.txt sidecar). Media bytes are synthetic.
"""

from __future__ import annotations

import json

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}


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
    return {"root": tmp_path, "videos": videos}


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def _session_id(client, title="Sesion", audio_availability="MISSING"):
    resp = client.post(
        "/api/capture/sessions",
        data=json.dumps({"title": title, "audio_availability": audio_availability, "project_id": "Zo Interviews"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    return resp.get_json()["session"]["sessionId"]


def _finalized_missing_audio(client, session_id):
    start = client.post(f"/api/capture/sessions/{session_id}/chunks/start", headers=AUTH_HEADERS)
    assert start.status_code == 200
    fin = client.post(
        f"/api/capture/sessions/{session_id}/chunks/0/finalize",
        data=b"synthetic-webm-bytes",
        content_type="application/octet-stream",
        headers=dict(AUTH_HEADERS, **{"X-Audio-Availability": "MISSING"}),
    )
    assert fin.status_code == 200
    assert fin.get_json()["chunk"]["transcriptRequired"] is True


def _associate(client, session_id, payload, headers=AUTH_HEADERS):
    return client.post(
        f"/api/capture/sessions/{session_id}/transcript",
        data=json.dumps(payload),
        content_type="application/json",
        headers=headers,
    )


# ── happy path ──────────────────────────────────────────────────────

def test_associate_transcript_clears_transcript_required(client, env):
    session_id = _session_id(client)
    _finalized_missing_audio(client, session_id)

    resp = _associate(client, session_id, {"text": "transcripcion tardia", "language": "es"})
    assert resp.status_code == 200
    session = resp.get_json()["session"]
    assert session["transcriptAvailable"] is True
    assert session["transcriptRequired"] is False
    assert session["transcript"]["text"] == "transcripcion tardia"
    assert session["transcript"]["alignment"] == "loose"
    chunk = session["chunks"][0]
    assert chunk["transcriptAvailable"] is True
    assert chunk["transcriptRequired"] is False
    assert chunk["state"] == "FINALIZED"  # processing state NOT forced to PROCESSED

    sidecar = env["videos"] / "live_capture" / session_id / "transcript.txt"
    assert sidecar.read_text(encoding="utf-8") == "transcripcion tardia"


def test_associate_transcript_persists_across_get(client):
    session_id = _session_id(client)
    _finalized_missing_audio(client, session_id)
    _associate(client, session_id, {"text": "persistido"})

    got = client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]
    assert got["transcript"]["text"] == "persistido"
    assert got["transcriptAvailable"] is True
    assert got["transcriptRequired"] is False
    assert got["chunks"][0]["transcriptAvailable"] is True


# ── auth / validation / security ────────────────────────────────────

def test_associate_transcript_requires_dashboard_token(client):
    session_id = _session_id(client)
    resp = _associate(client, session_id, {"text": "x"}, headers={})
    assert resp.status_code == 403


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "   "}, {"text": None}])
def test_associate_transcript_rejects_missing_or_empty_text(client, payload):
    session_id = _session_id(client)
    resp = _associate(client, session_id, payload)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_associate_transcript_rejects_invalid_language(client):
    session_id = _session_id(client)
    resp = _associate(client, session_id, {"text": "x", "language": "   "})
    assert resp.status_code == 400


def test_associate_transcript_unknown_session_is_not_found(client):
    resp = _associate(client, "sess-doesnotexist", {"text": "x"})
    assert resp.status_code == 404


def test_associate_transcript_invalid_session_id_rejected(client):
    resp = _associate(client, "../evil", {"text": "x"})
    assert resp.status_code in (400, 404)


def test_associate_transcript_does_not_leak_absolute_path(client, env):
    session_id = _session_id(client)
    resp = _associate(client, session_id, {"text": "texto"})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # The resolved session directory lives under env["root"]; it must never
    # appear in the response (only the opaque session id may).
    assert str(env["root"]) not in body
