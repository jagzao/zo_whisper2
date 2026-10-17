"""W6 Flask API integration: processing-chunk drain/observability endpoints.

Exercises the real routes with an isolated tmp data root and an injected
deterministic assembler (no real media, no FFmpeg): fragment upload with
recorded-timeline metadata, automatic processing-chunk finalization at the
duration threshold during capture, the /drain stop endpoint that force
finalizes the partial tail, and the durable fragment->chunk map. Synthetic
bytes only.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.live_capture.service import CaptureService
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}


def _fake_assembler(paths, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"".join(Path(p).read_bytes() for p in paths))


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
    service = CaptureService(videos_root=videos, assembler=_fake_assembler)
    monkeypatch.setattr(dashboard_app, "_get_capture_service", lambda: service)
    return {"root": tmp_path, "videos": videos, "service": service}


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


def _upload_fragment(client, session_id, fragment_id, sequence, data, *, duration_ms=None, offset_ms=None):
    form = {
        "fragment_id": fragment_id,
        "sequence": str(sequence),
        "media_extension": ".webm",
        "media": (io.BytesIO(data), f"{fragment_id}.webm"),
    }
    if duration_ms is not None:
        form["duration_ms"] = str(duration_ms)
    if offset_ms is not None:
        form["recorded_offset_ms"] = str(offset_ms)
    return client.post(
        f"/api/capture/sessions/{session_id}/fragments",
        data=form,
        content_type="multipart/form-data",
        headers=AUTH_HEADERS,
    )


def _session(client, session_id):
    return client.get(f"/api/capture/sessions/{session_id}").get_json()["session"]


def _processing_chunks(client, session_id):
    return client.get(f"/api/capture/sessions/{session_id}/processing-chunks").get_json()[
        "processingChunks"
    ]


# ── automatic chunk finalization during capture ─────────────────────────

def test_auto_chunk_finalizes_at_threshold_during_capture(client, env):
    session_id = _create_session(client, "Grabacion", chunk_duration_sec=3).get_json()["session"][
        "sessionId"
    ]
    for seq in range(1, 4):
        resp = _upload_fragment(
            client, session_id, f"fragment-{seq:06d}", seq, f"seg-{seq}".encode(),
            duration_ms=1000, offset_ms=(seq - 1) * 1000,
        )
        assert resp.status_code == 200

    session = _session(client, session_id)
    finalized = [c for c in session["chunks"] if c["state"] == "FINALIZED"]
    assert len(finalized) == 1
    assert finalized[0]["mediaSizeBytes"] == len(b"seg-1seg-2seg-3")

    chunks = _processing_chunks(client, session_id)
    assert len(chunks) == 1
    assert chunks[0]["state"] == "FINALIZED"
    assert chunks[0]["fragmentIds"] == ["fragment-000001", "fragment-000002", "fragment-000003"]


def test_recording_continues_while_chunk_n_and_fragment_n1_progress(client, env):
    """Fragment N+1 uploads and a second chunk forms after chunk N finalizes."""
    session_id = _create_session(client, "concurrente", chunk_duration_sec=3).get_json()["session"][
        "sessionId"
    ]
    for seq in range(1, 7):
        assert _upload_fragment(
            client, session_id, f"fragment-{seq:06d}", seq, f"s{seq}".encode(),
            duration_ms=1000, offset_ms=(seq - 1) * 1000,
        ).status_code == 200

    chunks = _processing_chunks(client, session_id)
    assert [c["chunkIndex"] for c in chunks] == [0, 1]
    assert [c["state"] for c in chunks] == ["FINALIZED", "FINALIZED"]
    assert len(_session(client, session_id)["chunks"]) == 2


# ── stop / drain ────────────────────────────────────────────────────────

def test_drain_endpoint_finalizes_partial_tail(client, env):
    session_id = _create_session(client, "parcial", chunk_duration_sec=600).get_json()["session"][
        "sessionId"
    ]
    for seq in range(1, 3):
        assert _upload_fragment(
            client, session_id, f"fragment-{seq:06d}", seq, f"p{seq}".encode(),
            duration_ms=1000, offset_ms=(seq - 1) * 1000,
        ).status_code == 200
    assert _processing_chunks(client, session_id) == []

    resp = client.post(
        f"/api/capture/sessions/{session_id}/drain",
        data=json.dumps({"ended_at": "2026-10-15T09:30:00+00:00"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["session"]["status"] == "FINALIZED"
    assert len(payload["processingChunks"]) == 1
    assert payload["processingChunks"][0]["state"] == "FINALIZED"

    session = _session(client, session_id)
    finalized = [c for c in session["chunks"] if c["state"] == "FINALIZED"]
    assert len(finalized) == 1
    # Source fragments are retained after drain.
    frags = client.get(f"/api/capture/sessions/{session_id}/fragments").get_json()["fragments"]
    assert len(frags) == 2


def test_drain_requires_local_token(client, env):
    session_id = _create_session(client, "token").get_json()["session"]["sessionId"]
    resp = client.post(f"/api/capture/sessions/{session_id}/drain")
    assert resp.status_code == 403


def test_drain_after_finalize_does_not_duplicate(client, env):
    session_id = _create_session(client, "idem", chunk_duration_sec=600).get_json()["session"][
        "sessionId"
    ]
    _upload_fragment(client, session_id, "fragment-000001", 1, b"one", duration_ms=1000, offset_ms=0)
    first = client.post(f"/api/capture/sessions/{session_id}/drain", headers=AUTH_HEADERS)
    assert first.status_code == 200
    # A second drain cannot re-finalize an already-FINALIZED session (409) and
    # must not create a duplicate processing chunk.
    second = client.post(f"/api/capture/sessions/{session_id}/drain", headers=AUTH_HEADERS)
    assert second.status_code == 409
    assert len(_processing_chunks(client, session_id)) == 1
    assert len(_session(client, session_id)["chunks"]) == 1


# ── observability / validation ──────────────────────────────────────────

def test_processing_chunks_unknown_session_is_not_found(client):
    resp = client.get("/api/capture/sessions/sess-missing/processing-chunks")
    assert resp.status_code == 404


def test_fragment_duration_metadata_persists(client, env):
    session_id = _create_session(client, "meta").get_json()["session"]["sessionId"]
    _upload_fragment(client, session_id, "fragment-000001", 1, b"x", duration_ms=1234, offset_ms=50)
    frag = client.get(f"/api/capture/sessions/{session_id}/fragments").get_json()["fragments"][0]
    assert frag["durationMs"] == 1234
    assert frag["recordedOffsetMs"] == 50


def test_negative_duration_is_rejected(client, env):
    session_id = _create_session(client, "neg").get_json()["session"]["sessionId"]
    resp = _upload_fragment(client, session_id, "fragment-000001", 1, b"x", duration_ms=-5)
    assert resp.status_code == 400


def test_audio_capture_project_inherits_to_fragment_and_processing_chunk(client, env):
    created = _create_session(
        client, "Audio meeting", capture_kind="audio", capture_source="microphone",
        project_id="Zo Interviews",
    ).get_json()["session"]
    session_id = created["sessionId"]
    assert created["captureKind"] == "audio"
    assert _upload_fragment(
        client, session_id, "fragment-000001", 1, b"synthetic-audio",
        duration_ms=1000, offset_ms=0,
    ).status_code == 200
    fragments = client.get(f"/api/capture/sessions/{session_id}/fragments").get_json()["fragments"]
    assert fragments[0]["projectId"] == "Zo Interviews"
    drained = client.post(
        f"/api/capture/sessions/{session_id}/drain",
        data=json.dumps({"ended_at": "2026-10-15T09:30:00+00:00"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    ).get_json()
    assert drained["session"]["projectId"] == "Zo Interviews"
    assert drained["processingChunks"][0]["projectId"] == "Zo Interviews"
