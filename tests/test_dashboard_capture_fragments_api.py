"""W5 Flask API tests: multipart upload-fragment endpoint.

Exercises the real routes with an isolated tmp data root: create session,
first fragment ACK, duplicate same/different bytes, ordering via the
observability GET, oversize/validation rejection and durable-on-disk media.
Synthetic bytes only; no real media and no camera.
"""

from __future__ import annotations

import io
import json
import urllib.parse

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


def _create_session(client, title="Sesion", **extra):
    return client.post(
        "/api/capture/sessions",
        data=json.dumps({"title": title, "project_id": "Zo Interviews", **extra}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )


def _upload_fragment(client, session_id, fragment_id="fragment-000001", sequence=1, data=b"bytes", extension=".webm"):
    return client.post(
        f"/api/capture/sessions/{session_id}/fragments",
        data={
            "fragment_id": fragment_id,
            "sequence": str(sequence),
            "media_extension": extension,
            "media": (io.BytesIO(data), f"{fragment_id}{extension}"),
        },
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )


def _list_fragments(client, session_id):
    return client.get(f"/api/capture/sessions/{session_id}/fragments")


# ── first upload / ACK ───────────────────────────────────────────────────

def test_fragment_upload_acks_and_persists_media(client, env):
    session_id = _create_session(client, "Grabacion").get_json()["session"]["sessionId"]
    data = b"synthetic-fragment-bytes" * 16
    resp = _upload_fragment(client, session_id, data=data)
    assert resp.status_code == 200
    fragment = resp.get_json()["fragment"]
    assert fragment["fragmentId"] == "fragment-000001"
    assert fragment["sequence"] == 1
    assert fragment["state"] == "ACKED"
    assert fragment["mediaSizeBytes"] == len(data)

    media = env["videos"] / "live_capture" / session_id / "fragments" / "fragment-000001.webm"
    assert media.read_bytes() == data
    assert not list(media.parent.glob("*.tmp"))


def test_requested_microphone_missing_in_first_fragment_is_flagged(client, monkeypatch):
    session = _create_session(
        client,
        "Camera with mic",
        capture_metadata={"audioRequested": True, "micPermissionState": "granted"},
    ).get_json()["session"]
    monkeypatch.setattr(
        dashboard_app,
        "_probe_capture_fragment",
        lambda _path: {
            "fragmentProbeStatus": "VALIDATED", "actualVideoStreams": 1,
            "actualAudioStreams": 0, "videoCodec": "vp8", "width": 320,
            "height": 240, "fps": 30.0,
        },
    )

    response = _upload_fragment(client, session["sessionId"], data=b"synthetic video-only")

    assert response.status_code == 200
    assert response.get_json()["captureStatus"] == "AUDIO_CAPTURE_FAILED"
    saved = client.get(f"/api/capture/sessions/{session['sessionId']}").get_json()["session"]
    assert saved["audioAvailability"] == "MISSING"
    assert saved["captureMetadata"]["captureStatus"] == "AUDIO_CAPTURE_FAILED"
    assert saved["captureMetadata"]["firstFragmentProbe"]["actualAudioStreams"] == 0


def test_requested_microphone_with_audio_fragment_is_persisted(client, monkeypatch):
    session = _create_session(
        client,
        "Camera with audio",
        capture_metadata={"audioRequested": True, "micPermissionState": "granted"},
    ).get_json()["session"]
    monkeypatch.setattr(
        dashboard_app,
        "_probe_capture_fragment",
        lambda _path: {
            "fragmentProbeStatus": "VALIDATED", "actualVideoStreams": 1,
            "actualAudioStreams": 1, "videoCodec": "vp8", "audioCodec": "opus",
            "width": 320, "height": 240, "fps": 30.0,
            "audioChannels": 1, "audioSampleRate": "48000",
        },
    )

    response = _upload_fragment(client, session["sessionId"], data=b"synthetic video and audio")

    assert response.get_json().get("captureStatus") is None
    saved = client.get(f"/api/capture/sessions/{session['sessionId']}").get_json()["session"]
    assert saved["audioAvailability"] == "AVAILABLE"
    assert saved["captureMetadata"]["firstFragmentProbe"]["audioCodec"] == "opus"


def test_fragment_upload_requires_token(client, env):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    resp = client.post(
        f"/api/capture/sessions/{session_id}/fragments",
        data={"fragment_id": "fragment-000001", "sequence": "1", "media": (io.BytesIO(b"x"), "a.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_fragment_upload_requires_fragment_id(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    resp = client.post(
        f"/api/capture/sessions/{session_id}/fragments",
        data={"sequence": "1", "media": (io.BytesIO(b"x"), "a.webm")},
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


def test_fragment_upload_requires_media(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    resp = client.post(
        f"/api/capture/sessions/{session_id}/fragments",
        data={"fragment_id": "fragment-000001", "sequence": "1"},
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


def test_fragment_upload_rejects_bad_sequence(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    resp = _upload_fragment(client, session_id, sequence="not-an-int")
    assert resp.status_code == 400


def test_fragment_upload_rejects_unsafe_fragment_id(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    resp = _upload_fragment(client, session_id, fragment_id="../evil")
    assert resp.status_code == 400


def test_fragment_upload_unknown_session_is_not_found(client):
    resp = _upload_fragment(client, "sess-missing")
    assert resp.status_code == 404


def test_fragment_upload_oversize_is_rejected(client, env, monkeypatch):
    monkeypatch.setitem(dashboard_app.app.config, "MAX_CONTENT_LENGTH", 2000)
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    resp = _upload_fragment(client, session_id, data=b"x" * 8192)
    assert resp.status_code == 413
    assert _list_fragments(client, session_id).get_json()["fragments"] == []


# ── idempotency ──────────────────────────────────────────────────────────

def test_duplicate_identical_fragment_returns_same_ack(client, env):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    data = b"same-bytes"
    first = _upload_fragment(client, session_id, data=data).get_json()["fragment"]
    second_resp = _upload_fragment(client, session_id, data=data)
    assert second_resp.status_code == 200
    assert second_resp.get_json()["fragment"] == first
    frags = _list_fragments(client, session_id).get_json()["fragments"]
    assert len(frags) == 1


def test_duplicate_different_fragment_is_conflict(client, env):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _upload_fragment(client, session_id, data=b"original")
    resp = _upload_fragment(client, session_id, data=b"changed!")
    assert resp.status_code == 409
    assert resp.get_json()["ok"] is False
    media = env["videos"] / "live_capture" / session_id / "fragments" / "fragment-000001.webm"
    assert media.read_bytes() == b"original"


# ── ordering / observability ─────────────────────────────────────────────

def test_fragment_list_orders_by_sequence(client):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    _upload_fragment(client, session_id, fragment_id="fragment-000002", sequence=2, data=b"two")
    _upload_fragment(client, session_id, fragment_id="fragment-000001", sequence=1, data=b"one")
    resp = _list_fragments(client, session_id)
    assert resp.status_code == 200
    sequences = [f["sequence"] for f in resp.get_json()["fragments"]]
    ids = [f["fragmentId"] for f in resp.get_json()["fragments"]]
    assert sequences == [1, 2]
    assert ids == ["fragment-000001", "fragment-000002"]


def test_fragment_list_unknown_session_is_not_found(client):
    resp = client.get("/api/capture/sessions/sess-missing/fragments")
    assert resp.status_code == 404


# ── short fragments are not processing chunks ────────────────────────────

def test_short_fragments_do_not_create_processing_chunks(client, env):
    session_id = _create_session(client).get_json()["session"]["sessionId"]
    for seq, frag in ((1, "fragment-000001"), (2, "fragment-000002")):
        assert _upload_fragment(client, session_id, fragment_id=frag, sequence=seq, data=f"f{seq}".encode()).status_code == 200

    session = client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]
    # No processing chunk was created/finalized per short fragment.
    assert session["chunks"] == []
    # The session keeps the default 600s processing chunk duration.
    assert session["chunkDurationSec"] == 600
