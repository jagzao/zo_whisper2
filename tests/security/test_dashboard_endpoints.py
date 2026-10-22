import json
import urllib.parse

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}
# Captured before any test monkeypatches it away (see `env` fixture below).
_REAL_IS_VALID_MEDIA_FILE = dashboard_app._is_valid_media_file


@pytest.fixture
def env(tmp_path, monkeypatch):
    from transcript_pipeline import pipeline_metrics
    from transcript_pipeline import upload_idempotency

    monkeypatch.setattr(pipeline_metrics, "_PATH", tmp_path / ".whisper" / "pipeline_metrics.json")
    monkeypatch.setattr(upload_idempotency, "_PATH", tmp_path / ".whisper" / "upload_ids.json")
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
    # These tests use fake byte content (not real media) for upload fixtures
    # — dedicated tests below cover _is_valid_media_file's ffprobe logic
    # itself with explicit mocking; here it would just reject every upload.
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", lambda path: True)
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


def test_frames_nonexistent_media_rejected(client, env):
    resp = client.get("/api/frames" + q(mid(MediaRoot.VIDEOS, "missing.mp4")))
    assert resp.status_code == 404


def test_frames_valid_media_without_frames_returns_success_empty_payload(client, env):
    # Regression: this used to 404, which the browser logged as a console
    # error on every frames-tab open for valid media without keyframes.
    video = env["videos"] / "clip.mp4"
    video.write_bytes(b"fake video")
    resp = client.get("/api/frames" + q(mid(MediaRoot.VIDEOS, "clip.mp4")))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["frames"] == []
    assert body["count"] == 0


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


def test_dashboard_exposes_current_build_and_disables_html_caching(client):
    response = client.get("/")
    assert response.headers["X-Whisper-Build"] == dashboard_app.BUILD_REVISION
    assert "whisper-build" in response.get_data(as_text=True)
    assert "no-store" in response.headers["Cache-Control"]


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


def test_upload_preserves_selected_project_id(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_load_projects", lambda: [{"name": "Zo Interviews", "match": {"prefix": ["zi_"]}}])
    data = {"file": (__import__("io").BytesIO(b"fake mp3 bytes"), "meeting.mp3"), "project_id": "Zo Interviews"}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()["project_id"] == "Zo Interviews"
    assert resp.get_json()["name"] == "zi_meeting.mp3"


def test_upload_rejects_unknown_selected_project(client, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_load_projects", lambda: [{"name": "Known project"}])
    data = {"file": (__import__("io").BytesIO(b"fake mp3 bytes"), "meeting.mp3"), "project_id": "Missing project"}
    response = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert response.status_code == 400


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


# ── /api/upload content validation (ffprobe, not just extension) ────────
# `env`'s _is_valid_media_file override doesn't apply here — these tests
# mock subprocess.run directly to exercise the real function.

def _fake_completed_process(stdout: str, returncode: int = 0):
    import subprocess as sp

    return sp.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_upload_rejects_renamed_non_media_file(client, env, monkeypatch):
    # env's fixture stubs _is_valid_media_file to always True — restore the
    # real function so this test actually exercises the ffprobe logic.
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", _REAL_IS_VALID_MEDIA_FILE)
    # ffprobe recognizes no streams at all — e.g. a renamed .exe.
    monkeypatch.setattr(
        dashboard_app.subprocess, "run",
        lambda *a, **k: _fake_completed_process('{"streams": []}'),
    )
    data = {"file": (__import__("io").BytesIO(b"MZ\x90\x00fake exe bytes"), "payload.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 400
    assert not (env["video_compress"] / "payload.mp3").exists()


def test_upload_rejects_when_ffprobe_fails(client, env, monkeypatch):
    import subprocess as sp

    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", _REAL_IS_VALID_MEDIA_FILE)

    def _raise(*a, **k):
        raise sp.CalledProcessError(1, "ffprobe")

    monkeypatch.setattr(dashboard_app.subprocess, "run", _raise)
    data = {"file": (__import__("io").BytesIO(b"not media"), "broken.mp4")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 400
    assert not (env["video_compress"] / "broken.mp4").exists()


def test_upload_rejects_on_ffprobe_timeout(client, env, monkeypatch):
    import subprocess as sp

    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", _REAL_IS_VALID_MEDIA_FILE)

    def _raise(*a, **k):
        raise sp.TimeoutExpired(cmd="ffprobe", timeout=30)

    monkeypatch.setattr(dashboard_app.subprocess, "run", _raise)
    data = {"file": (__import__("io").BytesIO(b"data"), "hangs.mp4")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 400
    assert not (env["video_compress"] / "hangs.mp4").exists()


def test_upload_accepts_file_ffprobe_confirms_as_media(client, env, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", _REAL_IS_VALID_MEDIA_FILE)
    monkeypatch.setattr(
        dashboard_app.subprocess, "run",
        lambda *a, **k: _fake_completed_process('{"streams": [{"codec_type": "audio"}]}'),
    )
    data = {"file": (__import__("io").BytesIO(b"real-ish audio bytes"), "real.mp3")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert (env["video_compress"] / "real.mp3").exists()


def test_v2_regenerate_uses_saved_evidence_without_media_processing(client, env, monkeypatch):
    video = env["videos"] / "sample.mp4"
    video.write_bytes(b"synthetic video")
    frames = env["transcriptions"] / "sample_Frames" / "sample"
    frames.mkdir(parents=True)
    (frames / "frame_mapping.json").write_text('{"frames": []}', encoding="utf-8")
    calls = []
    monkeypatch.setattr(dashboard_app, "_effective_project", lambda *args: ({"name": "Demo"}, "test"))
    from transcript_pipeline.documentation import regenerate_v2
    monkeypatch.setattr(regenerate_v2, "regenerate_documentation_v2", lambda path, **kwargs: calls.append((path, kwargs)) or {"status": "EVIDENCE_READY"})
    route = "/api/documentation/v2/regenerate" + q(mid(MediaRoot.VIDEOS, "sample.mp4"))
    for expected_version in (1, 2):
        response = client.post(route, headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert response.get_json()["pipeline"] == "documentation-v2"
        assert response.get_json()["result"]["version"]["documentation_version"] == expected_version
    assert calls == [(frames, {"project_config": {"name": "Demo"}})] * 2


def test_v2_regenerate_requires_existing_evidence(client, env):
    (env["videos"] / "sample.mp4").write_bytes(b"synthetic video")
    response = client.post("/api/documentation/v2/regenerate" + q(mid(MediaRoot.VIDEOS, "sample.mp4")), headers=AUTH_HEADERS)
    assert response.status_code == 409


def test_documentation_versions_are_selectable_from_video_detail_api(client, env):
    video = env["videos"] / "sample.mp4"
    video.write_bytes(b"synthetic video")
    frames = env["transcriptions"] / "sample_Frames" / "sample"
    version = frames / "documentation_versions" / "000001"
    (version / "manual").mkdir(parents=True)
    (version / "manual" / "MANUAL.md").write_text("Synthetic version one", encoding="utf-8")
    (version / "version.json").write_text(
        '{"documentation_version": 1, "pipeline_version": "documentation-v2", "status": "COMPLETED"}',
        encoding="utf-8",
    )
    listing = client.get("/api/documentation/versions" + q(mid(MediaRoot.VIDEOS, "sample.mp4")))
    selected = client.get("/api/documentation/versions" + q(mid(MediaRoot.VIDEOS, "sample.mp4")) + "&version=1")
    assert listing.get_json()["versions"][0]["documentation_version"] == 1
    assert selected.get_json()["manual"] == "Synthetic version one"


def test_video_list_exposes_user_state_and_stage_metrics(client, env):
    video = env["videos"] / "sample.mp4"
    video.write_bytes(b"synthetic video")
    from transcript_pipeline.pipeline_metrics import record_stage
    record_stage(None, video.name, "upload", 1.25)
    response = client.get("/api/files")
    row = next(item for item in response.get_json()["files"] if item["name"] == "sample.mp4")
    assert row["user_state"] == "READY"
    assert row["timings"]["stages"]["upload"]["duration_seconds"] == 1.25


def test_reprocess_video_queues_one_forced_media_run(client, env, monkeypatch):
    import threading
    from transcript_pipeline.transcription import processor

    video = env["videos"] / "sample.mp4"
    video.write_bytes(b"synthetic video")
    finished = threading.Event()
    calls = []

    class FakeProcessor:
        def process_file(self, target, *, force=False):
            calls.append((target, force))
            finished.set()
            return True

    monkeypatch.setattr(processor, "SimpleScanProcessor", FakeProcessor, raising=False)
    response = client.post("/api/video/reprocess" + q(mid(MediaRoot.VIDEOS, "sample.mp4")), headers=AUTH_HEADERS)
    assert response.status_code == 202
    assert response.get_json()["state"] == "PROCESSING_MEDIA"
    assert finished.wait(3)
    assert calls == [(video, True)]


def test_repeated_upload_id_returns_existing_file_without_duplicate(client, env):
    first = client.post(
        "/api/upload", data={"file": (__import__("io").BytesIO(b"first bytes"), "same.mp3"), "upload_id": "stable-test-upload-001"},
        content_type="multipart/form-data", headers=AUTH_HEADERS,
    ).get_json()
    retry = client.post(
        "/api/upload", data={"file": (__import__("io").BytesIO(b"different payload"), "same.mp3"), "upload_id": "stable-test-upload-001"},
        content_type="multipart/form-data", headers=AUTH_HEADERS,
    ).get_json()
    assert first["name"] == retry["name"]
    assert retry["duplicate"] is True
    assert len(list(env["video_compress"].glob("same*.mp3"))) == 1
