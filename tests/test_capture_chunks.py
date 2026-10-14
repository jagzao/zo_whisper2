from __future__ import annotations

import json

import pytest
from flask import Flask

from transcript_pipeline.capture import api as capture_api
from transcript_pipeline.capture.api import create_capture_blueprint
from transcript_pipeline.capture.models import SegmentStatus
from transcript_pipeline.capture.store import CaptureStore


@pytest.fixture
def client(tmp_path):
    app = Flask(__name__)
    store = CaptureStore(tmp_path / "capture")
    app.register_blueprint(create_capture_blueprint(store))
    return app.test_client(), store


def _start(client):
    response = client.post("/api/capture/sessions", json={"title": "Upload test"})
    assert response.status_code == 201
    session_id = response.json["session"]["sessionId"]
    started = client.post(f"/api/capture/sessions/{session_id}/start")
    assert started.status_code == 201
    return session_id


def test_chunk_hash_ack_conflict_gap_and_exact_seal(client, monkeypatch):
    http, store = client
    session_id = _start(http)
    first_url = f"/api/capture/sessions/{session_id}/segments/1/chunks/0"
    second_url = f"/api/capture/sessions/{session_id}/segments/1/chunks/1"
    assert http.put(first_url, data=b"first").status_code == 200
    duplicate = http.put(first_url, data=b"first")
    assert duplicate.status_code == 200 and duplicate.json["idempotent"] is True
    assert http.put(first_url, data=b"other").status_code == 409
    missing = http.post(
        f"/api/capture/sessions/{session_id}/segments/1/seal",
        json={"expectedChunkCount": 2, "recordedDurationSeconds": 10},
    )
    assert missing.status_code == 409
    assert http.put(second_url, data=b"second").status_code == 200
    probed = []
    monkeypatch.setattr(capture_api, "_validate_media", lambda path: probed.append(path.read_bytes()) or {"streams": []})
    sealed = http.post(
        f"/api/capture/sessions/{session_id}/segments/1/seal",
        json={"expectedChunkCount": 2, "recordedDurationSeconds": 10, "mimeType": "video/webm"},
    )
    assert sealed.status_code == 200
    assert probed == [b"firstsecond"]
    segment = store.get_segment(session_id, 1)
    assert segment.status is SegmentStatus.QUEUED
    assert segment.receivedBytes == len(b"firstsecond")
    assert (store.session_root(session_id) / segment.mediaRelativePath).read_bytes() == b"firstsecond"
    repeat = http.post(
        f"/api/capture/sessions/{session_id}/segments/1/seal",
        json={"expectedChunkCount": 2, "recordedDurationSeconds": 10},
    )
    assert repeat.status_code == 200 and repeat.json["idempotent"] is True


def test_chunk_size_and_sequence_bounds(client):
    http, _ = client
    session_id = _start(http)
    too_large = http.put(
        f"/api/capture/sessions/{session_id}/segments/1/chunks/0",
        data=b"x" * (capture_api.MAX_CHUNK_BYTES + 1),
    )
    assert too_large.status_code == 413
    invalid = http.put(f"/api/capture/sessions/{session_id}/segments/0/chunks/0", data=b"x")
    assert invalid.status_code == 400


def test_media_probe_checks_streams_not_browser_mime(tmp_path, monkeypatch):
    class Result:
        stdout = json.dumps({"streams": [{"codec_type": "video"}]})

    commands = []
    monkeypatch.setattr(capture_api, "run_ffprobe", lambda cmd, **kwargs: commands.append(cmd) or Result())
    path = tmp_path / "misleading.exe"
    path.write_bytes(b"synthetic")
    assert capture_api._validate_media(path)["streams"][0]["codec_type"] == "video"
    assert commands[0][-1] == str(path)

    class EmptyResult:
        stdout = json.dumps({"streams": []})

    monkeypatch.setattr(capture_api, "run_ffprobe", lambda *args, **kwargs: EmptyResult())
    with pytest.raises(ValueError, match="no audio or video"):
        capture_api._validate_media(path)


def test_dashboard_security_guards_mutating_capture_routes():
    from transcript_pipeline.dashboard import app as dashboard

    client = dashboard.app.test_client()
    path = "/api/capture/sessions"
    assert client.post(path, json={"title": "blocked"}).status_code == 403
    token = dashboard._DASHBOARD_TOKEN
    assert client.post(path, json={"title": "blocked"}, headers={
        "X-Local-Dashboard-Token": token,
        "Origin": "http://example.invalid",
    }).status_code == 403
    assert client.post(path, json={"title": "blocked"}, headers={
        "Host": "example.invalid",
        "X-Local-Dashboard-Token": token,
    }).status_code == 403
