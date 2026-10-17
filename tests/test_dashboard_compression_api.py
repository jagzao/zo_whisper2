"""Compression retention API tests (L07 / AC-03).

Proves the dashboard surfaces bytes saved and the cleanup outcome/reason, and
that the cleanup-retry control is restricted to a provenance-matched record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.media import optimize
from transcript_pipeline.media.optimize import ProvenanceStore
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}


def _valid_prober(path):
    """Non-ffmpeg prober: any file on disk is a valid, complete video."""
    p = Path(path)
    ok = p.is_file()
    return optimize.Probe(
        path=p,
        ok=ok,
        has_video=ok,
        has_audio=True,
        duration=10.0 if ok else None,
        size_bytes=p.stat().st_size if ok else 0,
    )


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
        dashboard_app, "RESOLVER",
        SafePathResolver({
            MediaRoot.AUDIO: audio,
            MediaRoot.VIDEOS: videos,
            MediaRoot.VIDEO_COMPRESS: video_compress,
            MediaRoot.TRANSCRIPTIONS: transcriptions,
        }),
    )
    monkeypatch.setattr(optimize, "default_prober", _valid_prober)
    return tmp_path


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def _seed_provenance(base, *, cleanup_state="CLEANUP_PENDING"):
    (base / "Videos" / "general").mkdir(parents=True, exist_ok=True)
    source = base / "Video_compress" / "clip.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"S" * 1000)
    output = base / "Videos" / "general" / "clip.mp4"
    output.write_bytes(b"O" * 400)
    store = ProvenanceStore(base / "compression_provenance.json")
    store.save({"Videos/general/clip.mp4": {
        "sourceRelative": "Video_compress/clip.mp4",
        "outputRelative": "Videos/general/clip.mp4",
        "sourceSha256": _sha(source),
        "outputSha256": _sha(output),
        "sourceSize": 1000,
        "outputSize": 400,
        "sourceDuration": 10.0,
        "outputDuration": 10.0,
        "bytesSaved": 600,
        "cleanupState": cleanup_state,
        "reason": "optimized output published; source cleanup pending",
        "updatedAt": "2026-10-17T00:00:00+00:00",
    }})
    return source, output


def _sha(path):
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_provenance_endpoint_reports_savings_and_cleanup_state(client, env):
    _seed_provenance(env)
    resp = client.get("/api/compression/provenance")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    record = body["records"][0]
    assert record["bytes_saved"] == 600
    assert record["cleanup_state"] == "CLEANUP_PENDING"
    assert record["reason"]
    assert record["retry_allowed"] is True


def test_retry_cleanup_requires_output_relative(client, env):
    resp = client.post("/api/compression/retry-cleanup", headers=AUTH_HEADERS, json={})
    assert resp.status_code == 400


def test_retry_cleanup_rejects_unknown_record(client, env):
    resp = client.post(
        "/api/compression/retry-cleanup", headers=AUTH_HEADERS,
        json={"output_relative": "Videos/general/nope.mp4"},
    )
    assert resp.status_code == 404


def test_retry_cleanup_removes_provenance_matched_source(client, env):
    source, _output = _seed_provenance(env)
    resp = client.post(
        "/api/compression/retry-cleanup", headers=AUTH_HEADERS,
        json={"output_relative": "Videos/general/clip.mp4"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["cleanup_state"] == "OPTIMIZED_SOURCE_REMOVED"
    assert not source.exists()


def test_retry_cleanup_refuses_when_source_changed(client, env):
    source, _output = _seed_provenance(env)
    source.write_bytes(b"changed")
    resp = client.post(
        "/api/compression/retry-cleanup", headers=AUTH_HEADERS,
        json={"output_relative": "Videos/general/clip.mp4"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["cleanup_state"] == "CLEANUP_PENDING"
    assert source.exists()


def test_retry_cleanup_rejects_retained_state(client, env):
    source, _output = _seed_provenance(env, cleanup_state="OPTIMIZED_SOURCE_RETAINED")
    resp = client.post(
        "/api/compression/retry-cleanup", headers=AUTH_HEADERS,
        json={"output_relative": "Videos/general/clip.mp4"},
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert body["cleanup_state"] == "OPTIMIZED_SOURCE_RETAINED"
    assert source.exists() and source.read_bytes() == b"S" * 1000


def test_retry_cleanup_rejects_already_removed_state(client, env):
    source, _output = _seed_provenance(env, cleanup_state="OPTIMIZED_SOURCE_REMOVED")
    resp = client.post(
        "/api/compression/retry-cleanup", headers=AUTH_HEADERS,
        json={"output_relative": "Videos/general/clip.mp4"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["cleanup_state"] == "OPTIMIZED_SOURCE_REMOVED"
    assert source.exists()


def test_retry_cleanup_cannot_remove_arbitrary_base_file(client, env):
    output = env / "Videos" / "general" / "clip.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"O" * 400)
    stray = env / "notes.txt"
    stray.write_bytes(b"KEEP")
    store = ProvenanceStore(env / "compression_provenance.json")
    store.save({"Videos/general/clip.mp4": {
        "sourceRelative": "notes.txt",
        "outputRelative": "Videos/general/clip.mp4",
        "sourceSha256": _sha(stray),
        "outputSha256": _sha(output),
        "sourceSize": 4,
        "outputSize": 400,
        "bytesSaved": 0,
        "cleanupState": "CLEANUP_PENDING",
        "reason": "pending",
    }})
    resp = client.post(
        "/api/compression/retry-cleanup", headers=AUTH_HEADERS,
        json={"output_relative": "Videos/general/clip.mp4"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["cleanup_state"] == "FAILED"
    assert stray.exists() and stray.read_bytes() == b"KEEP"
