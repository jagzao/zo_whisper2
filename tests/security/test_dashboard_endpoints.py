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
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", audio)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", video_compress)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcriptions)
    monkeypatch.setattr(dashboard_app, "PROJECTS_PATH", tmp_path / "projects.json")
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


def mid(root: MediaRoot, relative: str) -> str:
    """Builds a `_to_media_id()`-shaped id without needing a real resolved file."""
    return f"{root.value}:{relative}"


def q(media_id: str) -> str:
    return "?id=" + urllib.parse.quote(media_id, safe="")


# ── GET /api/transcription ──────────────────────────────────────────────

def test_read_allowed_transcription(client, env):
    tx = env["transcriptions"] / "meeting.txt"
    tx.write_text("hello world", encoding="utf-8")
    resp = client.get("/api/transcription" + q(mid(MediaRoot.TRANSCRIPTIONS, "meeting.txt")))
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "hello world"


def test_read_does_not_leak_absolute_paths_in_response(client, env):
    tx = env["transcriptions"] / "meeting.txt"
    tx.write_text("hello world", encoding="utf-8")
    resp = client.get("/api/transcription" + q(mid(MediaRoot.TRANSCRIPTIONS, "meeting.txt")))
    assert str(env["root"]) not in resp.get_data(as_text=True)


def test_read_traversal_from_transcriptions_root(client, env):
    outside = env["root"] / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    resp = client.get("/api/transcription" + q(mid(MediaRoot.TRANSCRIPTIONS, "../outside.txt")))
    assert resp.status_code in (400, 404)
    assert "secret" not in resp.get_data(as_text=True)


def test_read_windows_absolute_path_in_relative_segment_rejected(client):
    resp = client.get("/api/transcription" + q(mid(MediaRoot.TRANSCRIPTIONS, r"C:\Windows\win.ini")))
    assert resp.status_code in (400, 404)


def test_read_missing_id_param_rejected(client):
    resp = client.get("/api/transcription")
    assert resp.status_code in (400, 404)


def test_read_malformed_id_rejected(client):
    resp = client.get("/api/transcription?id=" + urllib.parse.quote("not-a-valid-id", safe=""))
    assert resp.status_code in (400, 404)


def test_read_unknown_root_in_id_rejected(client):
    resp = client.get("/api/transcription" + q("nonexistent_root:meeting.txt"))
    assert resp.status_code in (400, 404)


def test_read_wrong_root_for_endpoint_rejected(client, env):
    # A valid, well-formed id — but for a root /api/transcription doesn't allow.
    media = env["videos"] / "clip.mp4"
    media.write_bytes(b"data")
    resp = client.get("/api/transcription" + q(mid(MediaRoot.VIDEOS, "clip.mp4")))
    assert resp.status_code in (400, 404)


# ── POST /api/transcription ─────────────────────────────────────────────

def test_write_allowed_transcription(client, env):
    tx = env["transcriptions"] / "meeting.txt"
    tx.write_text("old", encoding="utf-8")
    resp = client.post(
        "/api/transcription",
        data=json.dumps({"id": mid(MediaRoot.TRANSCRIPTIONS, "meeting.txt"), "text": "new text"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert tx.read_text(encoding="utf-8") == "new text"


def test_write_traversal_outside_root_not_created(client, env, tmp_path):
    target = tmp_path.parent / "new_arbitrary_file.txt"
    assert not target.exists()
    resp = client.post(
        "/api/transcription",
        data=json.dumps({"id": mid(MediaRoot.TRANSCRIPTIONS, "../../new_arbitrary_file.txt"), "text": "pwned"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code in (400, 404)
    assert not target.exists()


def test_write_missing_id_rejected(client):
    resp = client.post(
        "/api/transcription",
        data=json.dumps({"text": "pwned"}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code in (400, 404)


# ── DELETE /api/file ─────────────────────────────────────────────────────

def test_delete_allowed_file(client, env):
    victim = env["videos"] / "clip.mp4"
    victim.write_text("data", encoding="utf-8")
    resp = client.delete("/api/file" + q(mid(MediaRoot.VIDEOS, "clip.mp4")), headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert not victim.exists()


def test_delete_traversal_outside_root_rejected(client, env, tmp_path):
    target = tmp_path.parent / "do_not_delete.txt"
    target.write_text("keep me", encoding="utf-8")
    try:
        resp = client.delete("/api/file" + q(mid(MediaRoot.VIDEOS, "../../do_not_delete.txt")), headers=AUTH_HEADERS)
        assert resp.status_code in (400, 404)
        assert target.exists()
    finally:
        target.unlink()


def test_delete_missing_id_rejected(client):
    resp = client.delete("/api/file", headers=AUTH_HEADERS)
    assert resp.status_code in (400, 404)


# ── /stream and /frame ────────────────────────────────────────────────

def test_stream_allowed_media(client, env):
    media = env["videos"] / "clip.mp4"
    media.write_bytes(b"fake-video-bytes")
    resp = client.get("/stream" + q(mid(MediaRoot.VIDEOS, "clip.mp4")))
    assert resp.status_code == 200


def test_stream_traversal_rejected(client, env, tmp_path):
    secret = tmp_path.parent / "secret.mp4"
    secret.write_bytes(b"nope")
    try:
        resp = client.get("/stream" + q(mid(MediaRoot.VIDEOS, "../../secret.mp4")))
        assert resp.status_code in (400, 404)
    finally:
        secret.unlink()


def test_stream_missing_id_rejected(client):
    resp = client.get("/stream")
    assert resp.status_code in (400, 404)


def test_frame_traversal_rejected(client, env):
    resp = client.get("/frame" + q(mid(MediaRoot.TRANSCRIPTIONS, "../../../etc/passwd")))
    assert resp.status_code in (400, 404)


def test_frame_wrong_root_rejected(client, env):
    media = env["videos"] / "clip.mp4"
    media.write_bytes(b"data")
    resp = client.get("/frame" + q(mid(MediaRoot.VIDEOS, "clip.mp4")))
    assert resp.status_code in (400, 404)


# ── GET /api/frames ──────────────────────────────────────────────────────

def test_frames_traversal_rejected(client, env, tmp_path):
    target = tmp_path.parent / "not_media.mp4"
    target.write_bytes(b"x")
    try:
        resp = client.get("/api/frames" + q(mid(MediaRoot.VIDEOS, "../../not_media.mp4")))
        assert resp.status_code in (400, 404)
    finally:
        target.unlink()


def test_frames_missing_id_rejected(client):
    resp = client.get("/api/frames")
    assert resp.status_code in (400, 404)


def test_frame_urls_returned_by_api_frames_are_actually_servable(client, env):
    # Regression: _resolve_frames() used to build frame["url"] relative to
    # ROOT instead of TRANSCRIPTIONS_BASE, so every generated URL 404'd.
    video = env["videos"] / "clip.mp4"
    video.write_bytes(b"fake video")

    frames_dir = env["transcriptions"] / "clip_Frames" / "clip"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_0000.png").write_bytes(b"fake png")
    (frames_dir / "frame_mapping.json").write_text(
        json.dumps({"frames": [{"frame_file": "frame_0000.png", "timestamp": 0}]}),
        encoding="utf-8",
    )

    resp = client.get("/api/frames" + q(mid(MediaRoot.VIDEOS, "clip.mp4")))
    assert resp.status_code == 200
    frame_url = resp.get_json()["frames"][0]["url"]
    assert frame_url.startswith("/frame?id=")

    frame_resp = client.get(frame_url)
    assert frame_resp.status_code == 200
    assert frame_resp.data == b"fake png"


# ── /api/files and /api/folders don't leak absolute paths ───────────────

def test_files_response_has_no_absolute_paths(client, env):
    media = env["videos"] / "clip.mp4"
    media.write_bytes(b"data")
    resp = client.get("/api/files")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert str(env["root"]) not in body


def test_folders_response_has_no_absolute_paths(client, env):
    resp = client.get("/api/folders")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert str(env["root"]) not in body


# ── POST /api/upload ─────────────────────────────────────────────────────

def test_upload_rejects_invalid_extension(client):
    data = {"file": (__import__("io").BytesIO(b"not media"), "payload.exe")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 400


def test_upload_accepts_supported_extension(client, env):
    data = {"file": (__import__("io").BytesIO(b"fake mp3 bytes"), "clip.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert (env["video_compress"] / "clip.mp3").exists()


def test_upload_response_has_no_absolute_path(client, env):
    data = {"file": (__import__("io").BytesIO(b"fake mp3 bytes"), "clip2.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert "path" not in resp.get_json()


# ── POST /api/projects (create/update reject malformed payloads) ────────

def test_create_project_rejects_missing_name(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"match": {}}}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


def test_create_project_rejects_unknown_handler(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"name": "X", "handler": "evil"}}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


def test_create_project_rejects_malformed_match(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"name": "X", "match": {"prefix": "not_a_list"}}}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


def test_create_project_accepts_valid_payload(client):
    resp = client.post(
        "/api/projects",
        data=json.dumps({"action": "create", "project": {"name": "Valid Project"}}),
        content_type="application/json",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_upload_sanitizes_dangerous_filename(client, env):
    data = {"file": (__import__("io").BytesIO(b"data"), "../../evil.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    saved_name = resp.get_json()["name"]
    assert ".." not in saved_name
    assert (env["video_compress"] / saved_name).resolve().parent == env["video_compress"].resolve()


def test_upload_duplicate_filename_does_not_overwrite(client, env):
    data1 = {"file": (__import__("io").BytesIO(b"first"), "clip.mp3")}
    resp1 = client.post("/api/upload", data=data1, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp1.status_code == 200

    data2 = {"file": (__import__("io").BytesIO(b"second"), "clip.mp3")}
    resp2 = client.post("/api/upload", data=data2, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp2.status_code == 200
    assert resp2.get_json()["name"] != "clip.mp3"

    assert (env["video_compress"] / "clip.mp3").read_bytes() == b"first"
    assert (env["video_compress"] / resp2.get_json()["name"]).read_bytes() == b"second"


def test_upload_oversize_rejected(client, monkeypatch):
    monkeypatch.setitem(dashboard_app.app.config, "MAX_CONTENT_LENGTH", 1024)
    oversize = b"x" * 2048
    data = {"file": (__import__("io").BytesIO(oversize), "big.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 413
