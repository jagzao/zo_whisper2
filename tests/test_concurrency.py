"""Concurrency guards (AC11): a second run/documentation/upload must not
silently collide with an in-flight one. Same isolated-tmp-path fixture
pattern as tests/test_project_override.py.
"""
from __future__ import annotations

import io
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
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", audio)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", video_compress)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcriptions)
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
    monkeypatch.setattr(dashboard_app, "PROJECTS_PATH", tmp_path / "projects.json")
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
    return {
        "root": tmp_path,
        "audio": audio,
        "videos": videos,
        "video_compress": video_compress,
        "transcriptions": transcriptions,
    }


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def test_run_full_twice_rejected(client, monkeypatch):
    monkeypatch.setitem(dashboard_app._run_state, "running", True)

    resp = client.post("/api/run/full", headers=AUTH_HEADERS)
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "A run is already in progress"


def test_double_generate_docs_rejected(client, env):
    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")
    frames_parent = env["transcriptions"] / "demo_Frames" / "demo"
    frames_parent.mkdir(parents=True)
    (frames_parent / "frame_mapping.json").write_text(
        json.dumps({"frames": []}), encoding="utf-8"
    )

    media_id = "videos:demo.mp4"
    with dashboard_app._doc_generation_lock:
        dashboard_app._doc_generation_inflight.add(media_id)
    try:
        resp = client.post(
            f"/api/documentation/generate?id={media_id}", headers=AUTH_HEADERS
        )
        assert resp.status_code == 409
        assert "already generating" in resp.get_json()["error"]
    finally:
        with dashboard_app._doc_generation_lock:
            dashboard_app._doc_generation_inflight.discard(media_id)


def test_duplicate_upload_gets_unique_name(client, env, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", lambda path: True)

    def upload(filename: str):
        return client.post(
            "/api/upload",
            data={"file": (io.BytesIO(b"fake"), filename)},
            headers=AUTH_HEADERS,
            content_type="multipart/form-data",
        )

    first = upload("demo.mp4")
    assert first.status_code == 200
    assert first.get_json()["name"] == "demo.mp4"

    second = upload("demo.mp4")
    assert second.status_code == 200
    assert second.get_json()["name"] == "demo_01.mp4"

    assert (env["video_compress"] / "demo.mp4").exists()
    assert (env["video_compress"] / "demo_01.mp4").exists()
