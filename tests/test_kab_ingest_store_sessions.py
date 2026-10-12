"""T29-T32: session creation idempotency, conflict, and safe GET state."""

from __future__ import annotations

import pytest

from tests.kab_ingest_utils import (
    auth_headers,
    chunk_bytes,
    make_settings,
    make_store,
    session_payload,
    sha256_hex,
)


@pytest.fixture()
def client(tmp_path):
    from transcript_pipeline.kab_ingest.server import create_app

    app = create_app(make_settings(tmp_path), store=make_store(tmp_path), data_root=tmp_path)
    app.testing = True
    return app.test_client()


def _upload(client, segment, track, chunk, body):
    return client.put(
        f"/kab/v1/sessions/sess-0001/segments/{segment}/{track}/chunks/{chunk}",
        headers={**auth_headers(), "X-Chunk-Size": str(len(body)), "X-Chunk-SHA256": sha256_hex(body)},
        data=body,
    )


def _complete_segment(client, segment, track, body, ext):
    return client.post(
        f"/kab/v1/sessions/sess-0001/segments/{segment}/{track}/complete",
        headers=auth_headers(),
        json={
            "schemaVersion": 1,
            "totalChunks": 1,
            "sizeBytes": len(body),
            "sha256": sha256_hex(body),
            "extension": ext,
            "durationMs": 1000,
            "startOffsetMs": segment * 1000,
        },
    )


def test_t29_create_session_is_idempotent_for_same_metadata(client):
    first = client.post("/kab/v1/sessions", headers=auth_headers(), json=session_payload())
    assert first.status_code == 201
    assert first.get_json()["created"] is True
    second = client.post("/kab/v1/sessions", headers=auth_headers(), json=session_payload())
    assert second.status_code == 200
    assert second.get_json()["created"] is False
    assert first.get_json()["session"]["sessionId"] == second.get_json()["session"]["sessionId"]


def test_t30_conflicting_metadata_same_id_is_409(client):
    client.post("/kab/v1/sessions", headers=auth_headers(), json=session_payload())
    conflict = client.post(
        "/kab/v1/sessions",
        headers=auth_headers(),
        json={**session_payload(), "title": "Otro titulo distinto"},
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error"]["code"] == "session_metadata_conflict"


def test_t31_get_returns_safe_state_without_paths(client, tmp_path):
    client.post("/kab/v1/sessions", headers=auth_headers(), json=session_payload())
    body_v = chunk_bytes("t31-v", 200)
    body_a = chunk_bytes("t31-a", 200)
    assert _upload(client, 0, "video", 0, body_v).status_code == 200
    assert _upload(client, 0, "audio", 0, body_a).status_code == 200
    assert _complete_segment(client, 0, "video", body_v, ".mp4").status_code == 200
    assert _complete_segment(client, 0, "audio", body_a, ".m4a").status_code == 200

    missing_upload = _upload(client, 1, "video", 0, chunk_bytes("t31-v1", 100))

    state = client.get("/kab/v1/sessions/sess-0001", headers=auth_headers()).get_json()
    assert state["status"] == "ACTIVE"
    assert state["requiredTracks"] == ["video", "audio"]
    segment_zero = next(s for s in state["segments"] if s["segmentIndex"] == 0)
    assert segment_zero["state"] == "RECEIVED"
    assert segment_zero["ready"] is True
    assert segment_zero["tracks"]["video"]["receivedChunkIndexes"] == [0]
    assert segment_zero["tracks"]["video"]["assembled"] is True
    assert segment_zero["tracks"]["video"]["extension"] == ".mp4"
    segment_one = next(s for s in state["segments"] if s["segmentIndex"] == 1)
    assert segment_one["state"] == "RECEIVED"
    assert segment_one["ready"] is False
    assert segment_one["tracks"]["video"]["receivedChunkIndexes"] == [0]
    assert segment_one["tracks"]["video"]["assembled"] is False
    assert state["pendingSegmentIndexes"] == [0, 1]
    assert state["completedSegmentIndexes"] == []

    text = str(state)
    root = str((tmp_path / "kab-inbox").resolve())
    assert root not in text
    assert str(tmp_path) not in text
    for forbidden in ("segments/", "chunks/", "session.json", "state.json"):
        assert forbidden not in text
    assert missing_upload.status_code == 200


def test_t32_unknown_session_is_uniform_404(client):
    assert client.get("/kab/v1/sessions/nope", headers=auth_headers()).status_code == 404
    response = client.put(
        "/kab/v1/sessions/nope/segments/0/video/chunks/0",
        headers={**auth_headers(), "X-Chunk-Size": "4", "X-Chunk-SHA256": sha256_hex(b"abcd")},
        data=b"abcd",
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "session_not_found"
