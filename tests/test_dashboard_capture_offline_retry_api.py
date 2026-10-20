"""W7 API tests: offline/reconnect replay contract for the durable buffer.

The browser keeps unacknowledged fragments in IndexedDB keyed by capture
session + stable fragment ID, and re-uploads them with the *same* ID after a
reconnect or reload. These deterministic API tests pin the server contract the
browser queue relies on:

- replaying an ID with identical bytes ACKs once and never duplicates media;
- a restore upload set (possibly out of order) is stored uniquely and ordered;
- replaying an ID with different bytes is rejected and keeps the original;
- an interrupted/offline fragment can be uploaded later to the same ACTIVE
  session with its original ID.

Synthetic bytes only; isolated tmp data root; no camera and no real media.
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


def _create_session(client, title="Sesion"):
    return client.post(
        "/api/capture/sessions",
        data=json.dumps({"title": title, "project_id": "Zo Interviews"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    ).get_json()["session"]["sessionId"]


def _upload_fragment(client, session_id, fragment_id, sequence, data, extension=".webm"):
    return client.post(
        f"/api/capture/sessions/{session_id}/fragments",
        data={
            "fragment_id": fragment_id,
            "sequence": str(sequence),
            "media_extension": extension,
            "duration_ms": "1000",
            "recorded_offset_ms": str((sequence - 1) * 1000),
            "media": (io.BytesIO(data), f"{fragment_id}{extension}"),
        },
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )


def _fragment_media_path(env, session_id, fragment_id, extension=".webm"):
    return env["videos"] / "live_capture" / session_id / "fragments" / f"{fragment_id}{extension}"


def _list_fragments(client, session_id):
    return client.get(f"/api/capture/sessions/{session_id}/fragments").get_json()["fragments"]


def test_reconnect_replay_same_id_acks_once_without_duplicate(client, env):
    session_id = _create_session(client)
    data = b"durable-pending-fragment" * 32
    first = _upload_fragment(client, session_id, "fragment-000001", 1, data)
    assert first.status_code == 200
    ack = first.get_json()["fragment"]

    # Simulated reconnect restore replays the very same ID and bytes.
    replay = _upload_fragment(client, session_id, "fragment-000001", 1, data)
    assert replay.status_code == 200
    assert replay.get_json()["fragment"] == ack

    fragments = _list_fragments(client, session_id)
    assert [f["fragmentId"] for f in fragments] == ["fragment-000001"]
    media = _fragment_media_path(env, session_id, "fragment-000001")
    assert media.read_bytes() == data
    assert not list(media.parent.glob("*.tmp"))


def test_restore_upload_set_is_unique_and_ordered(client, env):
    session_id = _create_session(client)
    # A restore can flush out of order; the server orders by sequence and keeps
    # each ID unique.
    _upload_fragment(client, session_id, "fragment-000002", 2, b"second")
    _upload_fragment(client, session_id, "fragment-000001", 1, b"first")
    fragments = _list_fragments(client, session_id)
    ids = [f["fragmentId"] for f in fragments]
    sequences = [f["sequence"] for f in fragments]
    assert ids == ["fragment-000001", "fragment-000002"]
    assert sequences == [1, 2]
    assert len(ids) == len(set(ids))


def test_reconnect_replay_different_bytes_conflict_keeps_original(client, env):
    session_id = _create_session(client)
    _upload_fragment(client, session_id, "fragment-000001", 1, b"original-bytes")
    conflict = _upload_fragment(client, session_id, "fragment-000001", 1, b"changed-bytes!")
    assert conflict.status_code == 409
    assert conflict.get_json()["ok"] is False
    assert _fragment_media_path(env, session_id, "fragment-000001").read_bytes() == b"original-bytes"


def test_offline_fragment_uploads_later_to_same_active_session(client, env):
    session_id = _create_session(client)
    # Nothing was uploaded while offline; the buffer flushes it later with its
    # original ID and recorded-timeline metadata intact.
    resp = _upload_fragment(client, session_id, "fragment-000001", 1, b"offline-then-online")
    assert resp.status_code == 200
    fragment = resp.get_json()["fragment"]
    assert fragment["state"] == "ACKED"
    assert fragment["durationMs"] == 1000
    assert fragment["recordedOffsetMs"] == 0
    assert _list_fragments(client, session_id)[0]["fragmentId"] == "fragment-000001"
