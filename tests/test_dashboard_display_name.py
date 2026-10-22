import json

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    audio, videos, compressed, transcripts = [tmp_path / name for name in ("audio", "Videos", "Video_compress", "CarpetaTranscripciones")]
    for folder in (audio, videos, compressed, transcripts):
        folder.mkdir()
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", audio)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", compressed)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcripts)
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
    monkeypatch.setattr(dashboard_app, "PROJECTS_PATH", tmp_path / "projects.json")
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", AUTH_HEADERS["X-Local-Dashboard-Token"])
    monkeypatch.setattr(dashboard_app, "RESOLVER", SafePathResolver({
        MediaRoot.AUDIO: audio, MediaRoot.VIDEOS: videos,
        MediaRoot.VIDEO_COMPRESS: compressed, MediaRoot.TRANSCRIPTIONS: transcripts,
    }))
    (tmp_path / "projects.json").write_text(json.dumps({"projects": [{
        "name": "Alpha", "match": {"prefix": ["alpha_"], "filename_contains": []}, "language": "en",
    }]}), encoding="utf-8")
    video = videos / "alpha_demo.webm"
    video.write_bytes(b"playable-bytes")
    transcript = transcripts / "alpha_demo.txt"
    transcript.write_text("linked transcript", encoding="utf-8")
    docs = transcripts / "alpha_demo_Frames" / "alpha_demo" / "manual"
    docs.mkdir(parents=True)
    (docs / "metadata.json").write_text("{}", encoding="utf-8")
    return {"root": tmp_path, "videos": videos, "transcripts": transcripts, "video": video, "transcript": transcript}


@pytest.fixture
def client(media_env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def test_display_name_preserves_extension_identity_and_artifacts(client, media_env):
    media_id = "videos:alpha_demo.webm"
    response = client.post("/api/media/display-name", json={"id": media_id, "name": "  AMS KAP App Support - Session 42  "}, headers=AUTH_HEADERS)
    assert response.status_code == 200
    row = next(row for row in client.get("/api/files").json["files"] if row["media_id"] == media_id)
    assert row["name"] == "AMS KAP App Support - Session 42.webm"
    assert row["project"] == "Alpha"
    assert row["transcription"]["id"] == "transcriptions:alpha_demo.txt"
    assert row["documentation"] is not None
    assert media_env["video"].read_bytes() == b"playable-bytes"
    assert client.get("/stream?id=videos%3Aalpha_demo.webm").data == b"playable-bytes"
    assert media_env["transcript"].read_text(encoding="utf-8") == "linked transcript"


@pytest.mark.parametrize("name,error", [("   ", "empty"), ("bad/name", "unsafe"), ("bad:name", "unsafe")])
def test_display_name_rejects_invalid_values(client, name, error):
    response = client.post("/api/media/display-name", json={"id": "videos:alpha_demo.webm", "name": name}, headers=AUTH_HEADERS)
    assert response.status_code == 400
    assert error in response.json["error"].lower() or "characters" in response.json["error"].lower()


def test_display_name_rejects_case_insensitive_collision(client, media_env):
    (media_env["videos"] / "other.webm").write_bytes(b"other")
    client.post("/api/media/display-name", json={"id": "videos:other.webm", "name": "Target"}, headers=AUTH_HEADERS)
    response = client.post("/api/media/display-name", json={"id": "videos:alpha_demo.webm", "name": "target"}, headers=AUTH_HEADERS)
    assert response.status_code == 409
    assert "already exists" in response.json["error"]


def test_display_name_is_idempotent_and_reset_to_original(client):
    payload = {"id": "videos:alpha_demo.webm", "name": "New name"}
    assert client.post("/api/media/display-name", json=payload, headers=AUTH_HEADERS).status_code == 200
    assert client.post("/api/media/display-name", json=payload, headers=AUTH_HEADERS).status_code == 200
    assert client.post("/api/media/display-name", json={**payload, "name": "alpha_demo"}, headers=AUTH_HEADERS).status_code == 200
    row = next(row for row in client.get("/api/files").json["files"] if row["media_id"] == payload["id"])
    assert row["name"] == "alpha_demo.webm"


def test_edit_file_view_has_name_validation_field(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="editMediaName"' in response.data
    assert b'id="editMediaNameError"' in response.data
    assert b"/api/media/display-name" in response.data
