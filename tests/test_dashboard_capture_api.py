"""Focused Flask API tests for the W4 browser camera capture endpoints.

Same isolated-tmp-path fixture pattern as
tests/security/test_dashboard_endpoints.py: the dashboard is monkeypatched to
resolve VIDEOS_BASE (and friends) under a per-test tmp dir, and the capture
service is exercised through the real Flask routes — session create/start/
finalize, strict ID validation, max upload size, and recorded_at persistence.
Media bytes are synthetic; no real camera or media is used.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.live_capture import models as capture_models
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


def _create_session(client, title="Sesion", **extra):
    payload = {"title": title, **extra}
    return client.post(
        "/api/capture/sessions",
        data=json.dumps(payload),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )


def _start_chunk(client, session_id):
    return client.post(f"/api/capture/sessions/{session_id}/chunks/start", headers=AUTH_HEADERS)


def _finalize_chunk(client, session_id, index, data, headers=None):
    return client.post(
        f"/api/capture/sessions/{session_id}/chunks/{index}/finalize",
        data=data,
        content_type="application/octet-stream",
        headers=dict(AUTH_HEADERS, **(headers or {})),
    )


def _finalize_session(client, session_id, **extra):
    return client.post(
        f"/api/capture/sessions/{session_id}/finalize",
        data=json.dumps(extra),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )


# ── session create ───────────────────────────────────────────────────────

def test_create_session_returns_active_session_with_recorded_at(client, env):
    resp = _create_session(client, "Clase", recorded_at="2026-10-15T09:00:00+00:00")
    assert resp.status_code == 200
    session = resp.get_json()["session"]
    assert session["status"] == "ACTIVE"
    assert session["title"] == "Clase"
    assert session["recordedAt"] == "2026-10-15T09:00:00+00:00"
    assert capture_models.validate_session_id(session["sessionId"]) == session["sessionId"]
    assert (env["videos"] / "live_capture" / session["sessionId"] / "session.json").exists()


def test_create_session_requires_dashboard_token(client):
    resp = client.post(
        "/api/capture/sessions",
        data=json.dumps({"title": "X"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_create_session_requires_title(client):
    resp = _create_session(client, "   ")
    assert resp.status_code == 400


def test_create_session_rejects_invalid_duration(client):
    resp = _create_session(client, "X", chunk_duration_sec="not-a-number")
    assert resp.status_code == 400


# ── chunk start + finalize ───────────────────────────────────────────────

def test_chunk_start_and_finalize_persist_media(client, env):
    session_id = _create_session(client, "Grabacion").get_json()["session"]["sessionId"]
    start = _start_chunk(client, session_id)
    assert start.status_code == 200
    chunk = start.get_json()["chunk"]
    assert chunk["index"] == 0
    assert chunk["state"] == "RECORDING"

    data = b"synthetic-webm-bytes" * 32
    fin = _finalize_chunk(client, session_id, 0, data, headers={"X-Media-Extension": ".webm"})
    assert fin.status_code == 200
    chunk = fin.get_json()["chunk"]
    assert chunk["state"] == "FINALIZED"
    assert chunk["mediaSizeBytes"] == len(data)

    media_path = env["videos"] / "live_capture" / session_id / "chunks" / "chunk-000000.webm"
    assert media_path.read_bytes() == data


def test_finalize_multiple_chunks_preserve_order(client, env):
    session_id = _create_session(client, "multi").get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"c0")
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 1, b"c1")

    session = client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]
    assert [c["index"] for c in session["chunks"]] == [0, 1]
    assert [c["state"] for c in session["chunks"]] == ["FINALIZED", "FINALIZED"]

    base = env["videos"] / "live_capture" / session_id / "chunks"
    assert (base / "chunk-000000.webm").read_bytes() == b"c0"
    assert (base / "chunk-000001.webm").read_bytes() == b"c1"
    assert not list(base.glob("*.tmp"))


def test_finalize_chunk_streams_not_buffered_whole_body(client, monkeypatch):
    # The streaming path enforces MAX_CONTENT_LENGTH incrementally (it no
    # longer reads request.get_data), so an oversized body is rejected before
    # the chunk is finalized and no media is persisted.
    monkeypatch.setitem(dashboard_app.app.config, "MAX_CONTENT_LENGTH", 64)
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    resp = _finalize_chunk(client, session_id, 0, b"x" * 128)
    assert resp.status_code == 413
    assert resp.get_json()["ok"] is False


def test_finalize_session_persists_recorded_at_and_ended_at(client):
    session_id = _create_session(
        client, "Clase", recorded_at="2026-10-15T09:00:00+00:00"
    ).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"bytes")

    resp = _finalize_session(client, session_id, ended_at="2026-10-15T09:30:00+00:00")
    assert resp.status_code == 200
    session = resp.get_json()["session"]
    assert session["status"] == "FINALIZED"
    assert session["recordedAt"] == "2026-10-15T09:00:00+00:00"
    assert session["endedAt"] == "2026-10-15T09:30:00+00:00"

    # Round-trip through GET.
    got = client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]
    assert got["status"] == "FINALIZED"
    assert got["recordedAt"] == "2026-10-15T09:00:00+00:00"


def test_finalize_chunk_rejects_empty_payload(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    resp = _finalize_chunk(client, session_id, 0, b"")
    assert resp.status_code == 400


def test_finalize_chunk_rejects_unsupported_extension(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    resp = _finalize_chunk(client, session_id, 0, b"bytes", headers={"X-Media-Extension": ".exe"})
    assert resp.status_code == 400


def test_finalize_chunk_before_start_is_not_found(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    resp = _finalize_chunk(client, session_id, 0, b"bytes")
    assert resp.status_code == 404


def test_finalize_chunk_twice_is_conflict(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"bytes")
    resp = _finalize_chunk(client, session_id, 0, b"more")
    assert resp.status_code == 409


def test_start_chunk_on_finalized_session_is_conflict(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"bytes")
    _finalize_session(client, session_id)
    resp = _start_chunk(client, session_id)
    assert resp.status_code == 409


# ── strict ID validation ─────────────────────────────────────────────────

@pytest.mark.parametrize("bad_id", ["../evil", "..%2Fevil", "sess with spaces", ""])
def test_invalid_session_id_is_rejected(client, bad_id):
    # A raw "../" may be normalized away by the router (404) or reach the
    # strict ID validator (400) — either way the request is rejected and no
    # filesystem path is ever built from it.
    resp = client.get(f"/api/capture/sessions/{urllib.parse.quote(bad_id, safe='')}")
    assert resp.status_code in (400, 404)


def test_missing_session_is_not_found(client):
    resp = client.get("/api/capture/sessions/sess-doesnotexist")
    assert resp.status_code == 404


# ── max upload size ──────────────────────────────────────────────────────

def test_finalize_chunk_oversize_is_rejected(client, monkeypatch):
    monkeypatch.setitem(dashboard_app.app.config, "MAX_CONTENT_LENGTH", 1024)
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    resp = _finalize_chunk(client, session_id, 0, b"x" * 2048)
    assert resp.status_code == 413


# ── listing ──────────────────────────────────────────────────────────────

def test_list_sessions_returns_newest_first(client):
    a = _create_session(client, "primera", recorded_at="2026-10-15T10:00:00+00:00").get_json()["session"]
    b = _create_session(client, "segunda", recorded_at="2026-10-15T11:00:00+00:00").get_json()["session"]
    ids = [s["sessionId"] for s in client.get("/api/capture/sessions").get_json()["sessions"]]
    assert ids[0] == b["sessionId"]
    assert ids[1] == a["sessionId"]


def test_list_sessions_surfaces_interrupted_failed_sessions(client, monkeypatch):
    session_id = _create_session(client, "interrumpida").get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    # Simulate a fresh dashboard process: lazy service initialization
    # reconciles any ACTIVE sessions left by the previous process.
    monkeypatch.setattr(dashboard_app, "_capture_service", None)
    monkeypatch.setattr(dashboard_app, "_capture_service_root", None)
    sessions = client.get("/api/capture/sessions").get_json()["sessions"]
    failed = [s for s in sessions if s["sessionId"] == session_id]
    assert failed and failed[0]["status"] == "FAILED"
    assert failed[0]["chunks"][0]["state"] == "FAILED"


# ── W6 crop selection / persistence ──────────────────────────────────────

def _set_crop(client, session_id, crop):
    return client.put(
        f"/api/capture/sessions/{session_id}/crop",
        data=json.dumps({"crop": crop}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )


def test_create_session_accepts_and_persists_crop(client, env):
    resp = _create_session(client, "Con crop", crop={"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4})
    assert resp.status_code == 200
    session = resp.get_json()["session"]
    assert session["crop"] == {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4}

    got = client.get(f"/api/capture/sessions/{session['sessionId']}").get_json()["session"]
    assert got["crop"] == {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.4}


def test_create_session_rejects_invalid_crop(client):
    resp = _create_session(client, "Crop malo", crop={"x": 0.5, "y": 0.5, "width": 0.9, "height": 0.5})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_set_crop_roundtrips(client):
    session_id = _create_session(client, "Set crop").get_json()["session"]["sessionId"]
    resp = _set_crop(client, session_id, {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5})
    assert resp.status_code == 200
    assert resp.get_json()["session"]["crop"] == {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}

    got = client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]
    assert got["crop"] == {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}


def test_clear_crop_via_null(client):
    session_id = _create_session(client, "Clear crop", crop={"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}).get_json()["session"]["sessionId"]
    resp = _set_crop(client, session_id, None)
    assert resp.status_code == 200
    assert resp.get_json()["session"]["crop"] is None

    got = client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]
    assert got["crop"] is None


def test_set_crop_rejects_out_of_bounds(client):
    session_id = _create_session(client, "Bad bounds").get_json()["session"]["sessionId"]
    resp = _set_crop(client, session_id, {"x": 0.0, "y": 0.0, "width": 1.1, "height": 1.0})
    assert resp.status_code == 400


def test_set_crop_requires_dashboard_token(client):
    session_id = _create_session(client, "Token").get_json()["session"]["sessionId"]
    resp = client.put(
        f"/api/capture/sessions/{session_id}/crop",
        data=json.dumps({"crop": {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}}),
        content_type="application/json",
    )
    assert resp.status_code == 403
