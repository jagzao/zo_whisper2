from dataclasses import replace

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.live_capture import models
from transcript_pipeline.security import MediaRoot, SafePathResolver


@pytest.fixture
def media_roots(tmp_path, monkeypatch):
    from transcript_pipeline import pipeline_metrics, upload_idempotency

    roots = {name: tmp_path / name for name in ("audio", "Videos", "Video_compress", "CarpetaTranscripciones")}
    for root in roots.values():
        root.mkdir()
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", roots["audio"])
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", roots["Videos"])
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", roots["Video_compress"])
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", roots["CarpetaTranscripciones"])
    monkeypatch.setattr(dashboard_app, "PROJECTS_PATH", tmp_path / "projects.json")
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "test-dashboard-token")
    (tmp_path / "projects.json").write_text('{"projects":[{"name":"P&G"}]}', encoding="utf-8")
    monkeypatch.setattr(pipeline_metrics, "_PATH", tmp_path / ".whisper" / "pipeline_metrics.json")
    monkeypatch.setattr(upload_idempotency, "_PATH", tmp_path / ".whisper" / "upload_ids.json")
    monkeypatch.setattr(dashboard_app, "RESOLVER", SafePathResolver({
        MediaRoot.AUDIO: roots["audio"],
        MediaRoot.VIDEOS: roots["Videos"],
        MediaRoot.VIDEO_COMPRESS: roots["Video_compress"],
        MediaRoot.TRANSCRIPTIONS: roots["CarpetaTranscripciones"],
    }))
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        yield client, roots


def test_logical_metrics_match_files_while_storage_diagnostics_keep_physical_counts(media_roots):
    client, roots = media_roots
    videos = roots["Videos"] / "general"
    videos.mkdir()
    for index in range(12):
        (videos / f"video-{index}.mp4").write_bytes(b"video")
    chunks = roots["Videos"] / "live_capture" / "unknown" / "fragments"
    chunks.mkdir(parents=True)
    for index in range(36):
        (chunks / f"chunk-{index}.webm").write_bytes(b"chunk")
    for index in range(3):
        (roots["Video_compress"] / f"queued-{index}.mp4").write_bytes(b"pending")

    raw_response = client.get("/api/files")
    assert raw_response.status_code == 200, raw_response.get_data(as_text=True)
    response = raw_response.get_json()
    diagnostics = client.get("/api/folders").get_json()

    assert len(response["files"]) == 12
    assert response["metrics"] == {"videos": 12, "audio": 0, "transcribed": 0}
    assert diagnostics["folders"][1] == {"name": "Videos", "count": 48}
    assert diagnostics["pending_count"] == 3
    html = client.get("/").get_data(as_text=True)
    assert "Storage diagnostics" in html
    assert "label: 'Transcribed'" in html
    assert "metric-videos" in html and "metrics.videos" in html


def test_logical_audio_and_transcribed_count_media_not_transcript_artifacts(media_roots):
    client, roots = media_roots
    video = roots["Videos"] / "clip.mp4"
    audio = roots["audio"] / "voice.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    (roots["CarpetaTranscripciones"] / "clip.txt").write_text("usable transcript", encoding="utf-8")
    (roots["CarpetaTranscripciones"] / "unrelated.txt").write_text("orphan", encoding="utf-8")
    (roots["CarpetaTranscripciones"] / "empty_voice.txt").write_text("", encoding="utf-8")

    response = client.get("/api/files").get_json()

    assert response["metrics"] == {"videos": 1, "audio": 1, "transcribed": 1}
    assert sum(row["media_kind"] == "audio" for row in response["files"]) == 1


def test_metrics_exclude_live_capture_chunks_with_final_and_test_sessions(media_roots):
    client, _ = media_roots
    normal = dashboard_app._get_capture_service()
    owner = client.post(
        "/api/capture/sessions",
        json={"title": "Owner capture", "project_id": "P&G"},
        headers={"X-Local-Dashboard-Token": "test-dashboard-token"},
    ).get_json()["session"]["sessionId"]
    normal.start_chunk(owner)
    normal.finalize_chunk(owner, 0, b"chunk")
    final = normal.store.final_media_path(owner, ".webm")
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"final")
    session = normal.get_session(owner)
    normal.store.save_session(replace(
        session,
        status=models.SessionStatus.FINALIZED,
        final_media={"relativePath": "final/recording.webm", "durationSec": 1.0},
    ))

    test_id = client.post(
        "/api/capture/sessions",
        json={"title": "Synthetic fixture", "project_id": "P&G", "is_test_session": True},
        headers={"X-Local-Dashboard-Token": "test-dashboard-token"},
    ).get_json()["session"]["sessionId"]
    normal.start_chunk(test_id)
    normal.finalize_chunk(test_id, 0, b"test chunk")

    result = client.get("/api/files").get_json()

    assert result["metrics"] == {"videos": 1, "audio": 0, "transcribed": 0}
    assert len(result["files"]) == 1
