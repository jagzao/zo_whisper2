import json
import urllib.parse

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver


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
    monkeypatch.setattr(dashboard_app, "PROJECTS_PATH", tmp_path / "projects.json")
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
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


def q(path: str) -> str:
    return "?path=" + urllib.parse.quote(path, safe="")


# ── GET /api/transcription ──────────────────────────────────────────────

def test_read_allowed_transcription(client, env):
    tx = env["transcriptions"] / "meeting.txt"
    tx.write_text("hello world", encoding="utf-8")
    resp = client.get("/api/transcription" + q(str(tx)))
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "hello world"


def test_read_forbidden_file_outside_root(client, env):
    secret = env["root"].parent / "outside_secret.txt"
    secret.write_text("do not leak", encoding="utf-8")
    try:
        resp = client.get("/api/transcription" + q(str(secret)))
        assert resp.status_code in (400, 404)
        assert "do not leak" not in resp.get_data(as_text=True)
    finally:
        secret.unlink()


def test_read_missing_path_param_rejected(client):
    resp = client.get("/api/transcription")
    assert resp.status_code in (400, 404)


def test_read_traversal_from_transcriptions_root(client, env):
    outside = env["root"] / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    traversal = str(env["transcriptions"] / ".." / "outside.txt")
    resp = client.get("/api/transcription" + q(traversal))
    assert resp.status_code in (400, 404)
    assert "secret" not in resp.get_data(as_text=True)


def test_read_windows_absolute_path_rejected(client):
    resp = client.get("/api/transcription" + q(r"C:\Windows\win.ini"))
    assert resp.status_code in (400, 404)


# ── POST /api/transcription ─────────────────────────────────────────────

def test_write_allowed_transcription(client, env):
    tx = env["transcriptions"] / "meeting.txt"
    tx.write_text("old", encoding="utf-8")
    resp = client.post(
        "/api/transcription",
        data=json.dumps({"path": str(tx), "text": "new text"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert tx.read_text(encoding="utf-8") == "new text"


def test_write_forbidden_file_outside_root(client, env, tmp_path):
    target = tmp_path.parent / "should_not_be_writable.txt"
    target.write_text("original", encoding="utf-8")
    try:
        resp = client.post(
            "/api/transcription",
            data=json.dumps({"path": str(target), "text": "pwned"}),
            content_type="application/json",
        )
        assert resp.status_code in (400, 404)
        assert target.read_text(encoding="utf-8") == "original"
    finally:
        target.unlink()


def test_write_new_file_outside_root_not_created(client, env, tmp_path):
    target = tmp_path.parent / "new_arbitrary_file.txt"
    assert not target.exists()
    resp = client.post(
        "/api/transcription",
        data=json.dumps({"path": str(target), "text": "pwned"}),
        content_type="application/json",
    )
    assert resp.status_code in (400, 404)
    assert not target.exists()


# ── DELETE /api/file ─────────────────────────────────────────────────────

def test_delete_allowed_file(client, env):
    victim = env["videos"] / "clip.mp4"
    victim.write_text("data", encoding="utf-8")
    resp = client.delete("/api/file" + q(str(victim)))
    assert resp.status_code == 200
    assert not victim.exists()


def test_delete_forbidden_file_outside_root(client, env, tmp_path):
    target = tmp_path.parent / "do_not_delete.txt"
    target.write_text("keep me", encoding="utf-8")
    try:
        resp = client.delete("/api/file" + q(str(target)))
        assert resp.status_code in (400, 404)
        assert target.exists()
    finally:
        target.unlink()


def test_delete_missing_path_rejected(client):
    resp = client.delete("/api/file")
    assert resp.status_code in (400, 404)


# ── /stream/<filename> and /frame/<filename> ────────────────────────────

def test_stream_allowed_media(client, env):
    media = env["videos"] / "clip.mp4"
    media.write_bytes(b"fake-video-bytes")
    resp = client.get("/stream/clip.mp4")
    assert resp.status_code == 200


def test_stream_traversal_rejected(client, env, tmp_path):
    secret = tmp_path.parent / "secret.mp4"
    secret.write_bytes(b"nope")
    try:
        resp = client.get("/stream/" + urllib.parse.quote("../../secret.mp4", safe=""))
        assert resp.status_code in (400, 404)
    finally:
        secret.unlink()


def test_frame_traversal_rejected(client, env):
    resp = client.get("/frame/" + urllib.parse.quote("../../../etc/passwd", safe=""))
    assert resp.status_code in (400, 404)


# ── GET /api/frames ──────────────────────────────────────────────────────

def test_frames_forbidden_path_outside_root(client, env, tmp_path):
    target = tmp_path.parent / "not_media.mp4"
    target.write_bytes(b"x")
    try:
        resp = client.get("/api/frames" + q(str(target)))
        assert resp.status_code in (400, 404)
    finally:
        target.unlink()


def test_frames_missing_path_rejected(client):
    resp = client.get("/api/frames")
    assert resp.status_code in (400, 404)


def test_frame_urls_returned_by_api_frames_are_actually_servable(client, env):
    # Regression: _resolve_frames() used to build frame["url"] relative to
    # ROOT instead of TRANSCRIPTIONS_BASE, so every generated URL 404'd on
    # /frame/<filename> (which resolves relative to TRANSCRIPTIONS_BASE).
    video = env["videos"] / "clip.mp4"
    video.write_bytes(b"fake video")

    frames_dir = env["transcriptions"] / "clip_Frames" / "clip"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_0000.png").write_bytes(b"fake png")
    (frames_dir / "frame_mapping.json").write_text(
        json.dumps({"frames": [{"frame_file": "frame_0000.png", "timestamp": 0}]}),
        encoding="utf-8",
    )

    resp = client.get("/api/frames" + q(str(video)))
    assert resp.status_code == 200
    frame_url = resp.get_json()["frames"][0]["url"]

    frame_resp = client.get(frame_url)
    assert frame_resp.status_code == 200
    assert frame_resp.data == b"fake png"


# ── POST /api/upload ─────────────────────────────────────────────────────

def test_upload_rejects_invalid_extension(client):
    data = {"file": (__import__("io").BytesIO(b"not media"), "payload.exe")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_upload_accepts_supported_extension(client, env):
    data = {"file": (__import__("io").BytesIO(b"fake mp3 bytes"), "clip.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert (env["video_compress"] / "clip.mp3").exists()


# ── POST /api/projects (create/update reject malformed payloads) ────────

def test_create_project_rejects_missing_name(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"match": {}}}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_create_project_rejects_unknown_handler(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"name": "X", "handler": "evil"}}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_create_project_rejects_malformed_match(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"name": "X", "match": {"prefix": "not_a_list"}}}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_create_project_accepts_valid_payload(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"name": "Valid Project"}}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_upload_sanitizes_dangerous_filename(client, env):
    data = {"file": (__import__("io").BytesIO(b"data"), "../../evil.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    saved_name = resp.get_json()["name"]
    assert ".." not in saved_name
    assert (env["video_compress"] / saved_name).resolve().parent == env["video_compress"].resolve()


def test_upload_duplicate_filename_does_not_overwrite(client, env):
    data1 = {"file": (__import__("io").BytesIO(b"first"), "clip.mp3")}
    resp1 = client.post("/api/upload", data=data1, content_type="multipart/form-data")
    assert resp1.status_code == 200

    data2 = {"file": (__import__("io").BytesIO(b"second"), "clip.mp3")}
    resp2 = client.post("/api/upload", data=data2, content_type="multipart/form-data")
    assert resp2.status_code == 200
    assert resp2.get_json()["name"] != "clip.mp3"

    assert (env["video_compress"] / "clip.mp3").read_bytes() == b"first"
    assert (env["video_compress"] / resp2.get_json()["name"]).read_bytes() == b"second"


def test_upload_oversize_rejected(client, monkeypatch):
    monkeypatch.setitem(dashboard_app.app.config, "MAX_CONTENT_LENGTH", 1024)
    oversize = b"x" * 2048
    data = {"file": (__import__("io").BytesIO(oversize), "big.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 413
