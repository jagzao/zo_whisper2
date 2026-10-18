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
from dataclasses import replace

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
    payload = {"title": title, "project_id": "Zo Interviews", **extra}
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


def test_create_session_persists_continuous_playlist_mode(client, env):
    response = _create_session(client, "Playlist", capture_mode="playlist")
    assert response.status_code == 200
    session = response.get_json()["session"]
    assert session["captureMode"] == "playlist"
    persisted = capture_models.Session.from_manifest(
        json.loads((env["videos"] / "live_capture" / session["sessionId"] / "session.json").read_text())
    )
    assert persisted.capture_mode == "playlist"


def test_create_session_persists_existing_project(client):
    missing_selection = _create_session(client, "No project", project_id="")
    assert missing_selection.status_code == 400
    missing = _create_session(client, "Invalid project", project_id="missing-project")
    assert missing.status_code == 400
    response = _create_session(client, "Project-owned", project_id="Zo Interviews")
    assert response.status_code == 200
    session = response.get_json()["session"]
    assert session["projectId"] == "Zo Interviews"


def test_create_session_rejects_invalid_capture_mode(client):
    response = _create_session(client, "Invalid mode", capture_mode="loop")
    assert response.status_code == 400


def test_audio_capture_session_persists_kind_source_and_project(client, env):
    response = _create_session(
        client, "Audio capture", project_id="Zo Interviews",
        capture_kind="audio", capture_source="microphone",
    )
    assert response.status_code == 200
    session = response.get_json()["session"]
    assert session["captureKind"] == "audio"
    assert session["captureSource"] == "microphone"
    assert session["projectId"] == "Zo Interviews"
    source = client.put(
        f"/api/capture/sessions/{session['sessionId']}/source",
        data=json.dumps({"capture_source": "user"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert source.status_code == 200
    assert source.get_json()["session"]["captureSource"] == "user"
    stored = capture_models.Session.from_manifest(
        json.loads((env["videos"] / "live_capture" / session["sessionId"] / "session.json").read_text())
    )
    assert stored.capture_kind == "audio"
    assert stored.capture_source == "user"


def test_playlist_title_samples_confirm_boundary_and_persist_review_actions(client):
    session_id = _create_session(client, "Playlist title sample", capture_mode="playlist", project_id="Zo Interviews").get_json()["session"]["sessionId"]
    url = f"/api/capture/sessions/{session_id}/title-samples"
    headers = {**AUTH_HEADERS, "Content-Type": "application/json"}
    one = "AMS KAP\nCompliance\nSession 1\n2026-08-05 12:29 UTC"
    two = "AMS KAP\nCompliance\nSession 2\n2026-08-05 12:44 UTC"
    client.post(url, data=json.dumps({"ocr_text": one, "confidence": 0.98, "offset_ms": 1000, "fragment_sequence": 1}), headers=headers)
    first = client.post(url, data=json.dumps({"ocr_text": one, "confidence": 0.98, "offset_ms": 5000, "fragment_sequence": 1}), headers=headers).get_json()
    assert len(first["logicalVideos"]) == 1
    client.post(url, data=json.dumps({"ocr_text": two, "confidence": 0.98, "offset_ms": 12000, "fragment_sequence": 2}), headers=headers)
    boundary = client.post(url, data=json.dumps({"ocr_text": two, "confidence": 0.98, "offset_ms": 14000, "fragment_sequence": 2}), headers=headers).get_json()
    assert len(boundary["logicalVideos"]) == 2
    assert boundary["logicalVideos"][0]["endOffsetMs"] == 12000
    assert boundary["logicalVideos"][1]["processingChunkIds"] == ["chunk-000000"]
    assert all(item["projectId"] == "Zo Interviews" for item in boundary["logicalVideos"])
    client.post(url, data=json.dumps({"ocr_text": "unclear slide", "confidence": 0.4, "offset_ms": 18000, "fragment_sequence": 2}), headers=headers)
    low = client.post(url, data=json.dumps({"ocr_text": "unclear slide", "confidence": 0.4, "offset_ms": 22000, "fragment_sequence": 2}), headers=headers).get_json()
    candidate = low["reviewCandidates"][0]
    assert candidate["status"] == "NEEDS_TITLE_REVIEW"
    confirmed = client.post(
        f"/api/capture/sessions/{session_id}/logical-videos/{candidate['id']}/confirm",
        data="{}", headers=headers,
    ).get_json()
    assert len(confirmed["logicalVideos"]) == 3
    assert confirmed["logicalVideos"][2]["manuallyReviewed"] is True


def test_confirmed_logical_video_is_listed_as_read_only_videos_entry(client):
    session_id = _create_session(client, "Playlist listing", capture_mode="playlist", project_id="Zo Interviews").get_json()["session"]["sessionId"]
    service = dashboard_app._get_capture_service()
    service.start_chunk(session_id)
    service.finalize_chunk(session_id, 0, b"synthetic video chunk")
    playlist = dashboard_app._get_playlist_service()
    title = "AMS KAP\nCompliance\nSession 8\n2026-08-05 12:29 UTC"
    playlist.observe(session_id, title, 0.98, 1000, 1)
    playlist.observe(session_id, title, 0.98, 5000, 1)

    response = client.get("/api/files")

    assert response.status_code == 200
    rows = response.get_json()["files"]
    logical = next(row for row in rows if row.get("logical_video", {}).get("title") == "AMS KAP Compliance Session 8")
    assert logical["logical_read_only"] is True
    assert logical["media_id"]
    assert logical["project"] == "Zo Interviews"
    assert not any(row["name"].startswith("chunk-") for row in rows if row.get("capture_session_id") == session_id)

    final_path = service.store.final_media_path(session_id, ".webm")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"synthetic finalized video")
    finalized = replace(
        service.get_session(session_id),
        status=capture_models.SessionStatus.FINALIZED,
        final_media={"relativePath": "final/recording.webm", "durationSec": 4.0},
    )
    service.store.save_session(finalized)

    finalized_rows = client.get("/api/files").get_json()["files"]
    finalized_logical = [row for row in finalized_rows if row.get("logical_video")]
    assert len(finalized_logical) == 1
    assert finalized_logical[0]["logical_video"]["title"] == "AMS KAP Compliance Session 8"
    assert finalized_logical[0]["logical_read_only"] is True
    assert finalized_logical[0]["duration"] == "00:04"
    assert not any(row["name"].startswith("chunk-") for row in finalized_rows)


def test_playlist_row_can_be_stopped_then_delete_enabled_for_single_video(client):
    session = _create_session(client, "Delete after stop", capture_mode="playlist").json["session"]
    session_id = session["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"synthetic playlist chunk")
    playlist = dashboard_app._get_playlist_service()
    title = "AMS KAP\nCompliance\nSession 8\n2026-08-05 12:29 UTC"
    playlist.observe(session_id, title, 0.98, 1000, 1)
    playlist.observe(session_id, title, 0.98, 5000, 1)
    _finalize_session(client, session_id)

    row = next(row for row in client.get("/api/files").json["files"] if row.get("capture_session_id") == session_id)
    assert row["logical_read_only"] is True
    assert row["logical_video_count"] == 1
    assert row["capture_status"] == "QUEUED"
    assert row["delete_allowed"] is False
    template = client.get("/").get_data(as_text=True)
    assert "cancelVideoCapture" in template
    assert "f.delete_allowed === false ? 'disabled' : ''" in template
    assert "Delete this capture session" in template

    stopped = client.post(
        f"/api/capture/sessions/{session_id}/cancel-processing", headers=AUTH_HEADERS,
    )
    assert stopped.status_code == 200
    stopped_row = next(row for row in client.get("/api/files").json["files"] if row.get("capture_session_id") == session_id)
    assert stopped_row["capture_status"] == "CANCELLED"
    assert stopped_row["delete_allowed"] is True

    deleted = client.delete(
        f"/api/file?id={urllib.parse.quote(stopped_row['media_id'], safe='')}&confirm=true",
        headers=AUTH_HEADERS,
    )
    assert deleted.status_code == 200
    assert deleted.json["capture_session_deleted"] is True


def test_video_listing_uses_session_rows_and_hides_marked_test_media(client):
    session = _create_session(client, "User recording", project_id="Zo Interviews").get_json()["session"]
    _start_chunk(client, session["sessionId"])
    _finalize_chunk(client, session["sessionId"], 0, b"synthetic fixture video")
    test_session = _create_session(
        client, "Test fixture recording", project_id="Zo Interviews", is_test_session=True,
    ).get_json()["session"]
    _start_chunk(client, test_session["sessionId"])
    _finalize_chunk(client, test_session["sessionId"], 0, b"synthetic fixture video")

    rows = client.get("/api/files").get_json()["files"]
    user_rows = [row for row in rows if row.get("capture_session_id") == session["sessionId"]]
    assert len(user_rows) == 1
    assert user_rows[0]["name"] == "User recording.webm"
    assert user_rows[0]["status"] == "QUEUED"
    assert user_rows[0]["capture_session_fallback"] is True
    assert not any(row.get("capture_session_id") == test_session["sessionId"] for row in rows)


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


def test_gc_suggestions_are_read_only(client):
    response = client.get("/api/capture/gc-candidates")
    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["deletes_media"] is False
    assert response.json["candidates"] == []


def test_cancel_upload_is_idempotent_and_retryable(client):
    session = _create_session(client, "cancelable").json["session"]
    session_id = session["sessionId"]
    _start_chunk(client, session_id)
    url = f"/api/capture/sessions/{session_id}/chunks/0/cancel-upload"
    first = client.post(url, headers=AUTH_HEADERS)
    second = client.post(url, headers=AUTH_HEADERS)
    assert first.json["chunk"]["state"] == "UPLOAD_CANCELLED"
    assert second.json["chunk"]["state"] == "UPLOAD_CANCELLED"
    retry = client.post(f"/api/capture/sessions/{session_id}/chunks/0/retry-upload", headers=AUTH_HEADERS)
    assert retry.json["chunk"]["state"] == "RECORDING"
    final = _finalize_chunk(client, session_id, 0, b"retry bytes")
    assert final.json["chunk"]["state"] == "FINALIZED"


def test_cancel_processing_queued_twice_and_retry(client):
    session = _create_session(client, "queued-cancel").json["session"]
    session_id = session["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"synthetic")
    url = f"/api/capture/sessions/{session_id}/chunks/0/cancel-processing"
    first = client.post(url, headers=AUTH_HEADERS)
    second = client.post(url, headers=AUTH_HEADERS)
    assert first.json["chunk"]["state"] == "CANCELLED"
    assert second.json["chunk"]["state"] == "CANCELLED"
    retry = client.post(f"/api/capture/sessions/{session_id}/chunks/0/retry-processing", headers=AUTH_HEADERS)
    assert retry.json["chunk"]["state"] == "FINALIZED"


def test_cancel_processing_active_returns_cancel_requested(client):
    session = _create_session(client, "active-cancel").json["session"]
    session_id = session["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"synthetic")
    dashboard_app._get_capture_service().mark_processing(session_id, 0)
    response = client.post(
        f"/api/capture/sessions/{session_id}/chunks/0/cancel-processing", headers=AUTH_HEADERS
    )
    assert response.json["chunk"]["state"] == "CANCEL_REQUESTED"


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
    assert failed[0]["chunks"][0]["state"] == "UPLOAD_CANCELLED"


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


# ── W7 audio availability / transcript-required ─────────────────────────

def test_create_session_persists_audio_availability(client, env):
    resp = _create_session(client, "Sin audio", audio_availability="MISSING")
    assert resp.status_code == 200
    session = resp.get_json()["session"]
    assert session["audioAvailability"] == "MISSING"

    got = client.get(f"/api/capture/sessions/{session['sessionId']}").get_json()["session"]
    assert got["audioAvailability"] == "MISSING"


def test_create_session_defaults_audio_unknown(client):
    session = _create_session(client).get_json()["session"]
    assert session["audioAvailability"] == "UNKNOWN"


def test_create_session_rejects_invalid_audio_availability(client):
    resp = _create_session(client, "malo", audio_availability="SOMETIMES")
    assert resp.status_code == 400


def test_finalize_chunk_with_missing_audio_marks_transcript_required(client, env):
    session_id = _create_session(client, "video-only", audio_availability="MISSING").get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    resp = _finalize_chunk(client, session_id, 0, b"bytes", headers={"X-Audio-Availability": "MISSING"})
    assert resp.status_code == 200
    chunk = resp.get_json()["chunk"]
    assert chunk["audioAvailability"] == "MISSING"
    assert chunk["transcriptRequired"] is True

    session = client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]
    assert session["audioAvailability"] == "MISSING"
    assert session["transcriptRequired"] is True


def test_finalize_chunk_rejects_invalid_audio_availability(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    resp = _finalize_chunk(client, session_id, 0, b"bytes", headers={"X-Audio-Availability": "NOPE"})
    assert resp.status_code == 400


def test_detect_chunk_audio_endpoint_marks_missing(client, env):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)
    _finalize_chunk(client, session_id, 0, b"bytes")

    service = dashboard_app._get_capture_service()
    service._audio_probe = lambda path: False

    resp = client.post(f"/api/capture/sessions/{session_id}/chunks/0/detect-audio", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    chunk = resp.get_json()["chunk"]
    assert chunk["audioAvailability"] == "MISSING"
    assert chunk["transcriptRequired"] is True


def test_detect_chunk_audio_endpoint_requires_finalized_chunk(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _start_chunk(client, session_id)  # still RECORDING, no media
    resp = client.post(f"/api/capture/sessions/{session_id}/chunks/0/detect-audio", headers=AUTH_HEADERS)
    assert resp.status_code == 409
