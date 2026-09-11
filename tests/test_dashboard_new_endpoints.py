"""Coverage for the US-001 dashboard additions: operational metrics
(§3.3), documentation links (§3.5/§3.6), and real-log-derived pipeline
stage inference (§3.4). Same isolated-tmp-path fixture pattern as
tests/security/test_dashboard_endpoints.py.
"""
from __future__ import annotations

import json
import re
import time
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
    return {"root": tmp_path, "audio": audio, "videos": videos, "transcriptions": transcriptions}


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def mid(root: MediaRoot, relative: str) -> str:
    return f"{root.value}:{relative}"


def q(media_id: str) -> str:
    return "?id=" + urllib.parse.quote(media_id, safe="")


# ── /api/metrics ─────────────────────────────────────────────────────────

def test_metrics_empty_state_reports_none_rates(client, env):
    resp = client.get("/api/metrics")
    data = resp.get_json()
    assert data["files_processed"] == 0
    assert data["success_rate_pct"] is None
    assert data["avg_processing_time_seconds"] is None


def test_metrics_computed_from_processed_db_and_metadata(client, env):
    db = {
        "hash1": {"hash": "hash1", "status": "completed"},
        "hash1_bypath": {"hash": "hash1", "status": "completed"},  # duplicate entry, same file
        "hash2": {"hash": "hash2", "status": "completed_routed"},
        "hash3": {"hash": "hash3", "status": "failed_routed"},
    }
    dashboard_app.PROCESSED_DB.write_text(json.dumps(db), encoding="utf-8")

    out_folder = env["transcriptions"] / "demo"
    out_folder.mkdir()
    (out_folder / "a_metadata.json").write_text(
        json.dumps({"duration": 60.0, "processing_time": 10.0}), encoding="utf-8"
    )
    (out_folder / "b_metadata.json").write_text(
        json.dumps({"duration": 40.0, "processing_time": 6.0}), encoding="utf-8"
    )

    resp = client.get("/api/metrics")
    data = resp.get_json()

    assert data["files_processed"] == 2  # hash1 (deduped) + hash2
    assert data["files_failed"] == 1
    assert data["success_rate_pct"] == pytest.approx(66.7, abs=0.1)
    assert data["duration_processed_seconds"] == pytest.approx(100.0)
    assert data["avg_processing_time_seconds"] == pytest.approx(8.0)


# ── /api/documentation ───────────────────────────────────────────────────

def test_documentation_endpoint_returns_manual_and_manifest(client, env):
    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")

    frames_parent = env["transcriptions"] / "demo_Frames" / "demo"
    manual_dir = frames_parent / "manual"
    ai_dir = frames_parent / "ai-package"
    (manual_dir / "assets").mkdir(parents=True)
    ai_dir.mkdir(parents=True)

    (manual_dir / "assets" / "step-0001.png").write_bytes(b"fake-png")
    (manual_dir / "MANUAL.md").write_text(
        "# demo.mp4\n\n## 1. Click New Project\n\n![step-0001](assets/step-0001.png)\n", encoding="utf-8"
    )
    (ai_dir / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0", "procedures": [{"id": "step-0001"}]}), encoding="utf-8"
    )

    video_id = mid(MediaRoot.VIDEOS, "demo.mp4")
    resp = client.get(f"/api/documentation{q(video_id)}")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert "Click New Project" in data["manual_markdown"]
    assert data["manifest"]["procedures"][0]["id"] == "step-0001"
    assert "/doc-asset?id=" in data["manual_markdown"]
    assert "assets/step-0001.png" not in data["manual_markdown"]

    # And that rewritten URL must actually be servable.
    asset_match = re.search(r"/doc-asset\?id=[^)\s]+", data["manual_markdown"])
    asset_resp = client.get(asset_match.group(0))
    assert asset_resp.status_code == 200


def test_documentation_endpoint_404_when_nothing_generated(client, env):
    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")
    video_id = mid(MediaRoot.VIDEOS, "demo.mp4")
    resp = client.get(f"/api/documentation{q(video_id)}")
    assert resp.status_code == 404


@pytest.fixture
def real_docs(env):
    """A video with documentation generated by the real engine (not hand-
    crafted JSON) — frame_mapping.json + frame + generate_documentation()."""
    from transcript_pipeline.documentation.engine import generate_documentation

    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")
    frames_parent = env["transcriptions"] / "demo_Frames" / "demo"
    frames_parent.mkdir(parents=True)
    (frames_parent / "frame_0000.png").write_bytes(b"fake-png")
    mapping = {
        "video_info": {"name": "demo.mp4", "duration": 10.0, "extraction_method": "smart_scene"},
        "transcription_summary": {"language": "en"},
        "frames": [{"frame_file": "frame_0000.png", "timestamp": 1.0, "timestamp_formatted": "00:00:01.000"}],
        "transcription_mapping": {"frame_0000.png": {"full_text": "Click Save."}},
    }
    (frames_parent / "frame_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    generate_documentation(frames_parent, "demo.mp4")
    return mid(MediaRoot.VIDEOS, "demo.mp4")


def test_documentation_get_includes_ai_package_download_links(client, real_docs):
    resp = client.get(f"/api/documentation{q(real_docs)}")
    data = resp.get_json()
    files = data["ai_package_files"]
    assert files["manifest"] and files["chunks"] and files["knowledge"]
    for url in files.values():
        assert client.get(url).status_code == 200


def test_documentation_get_includes_manual_pdf_url(client, real_docs):
    """The real engine (reportlab installed) writes MANUAL.pdf — the API must
    expose it as a servable /doc-asset URL, never a filesystem path."""
    resp = client.get(f"/api/documentation{q(real_docs)}")
    data = resp.get_json()
    assert data["manual_pdf_available"] is True
    assert data["manual_pdf_error"] is None
    url = data["manual_pdf_url"]
    assert url and url.startswith("/doc-asset?id=")
    assert "CarpetaTranscripciones" not in url and "\\" not in url and ":" not in url.split("?")[0]
    pdf_resp = client.get(url)
    assert pdf_resp.status_code == 200
    assert pdf_resp.content_type == "application/pdf"
    assert len(pdf_resp.data) > 0


def test_documentation_get_reports_pdf_missing_with_reason(client, env):
    """No MANUAL.pdf on disk + metadata.json saying reportlab was absent must
    surface a clear reason instead of pretending the bundle is complete."""
    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")
    manual_dir = env["transcriptions"] / "demo_Frames" / "demo" / "manual"
    (manual_dir / "assets").mkdir(parents=True)
    (manual_dir / "MANUAL.md").write_text("# demo.mp4\n\n## 1. Step\n", encoding="utf-8")
    (manual_dir / "metadata.json").write_text(
        json.dumps({"manual_pdf": "missing"}), encoding="utf-8"
    )

    video_id = mid(MediaRoot.VIDEOS, "demo.mp4")
    data = client.get(f"/api/documentation{q(video_id)}").get_json()

    assert data["manual_pdf_available"] is False
    assert data["manual_pdf_url"] is None
    assert "reportlab" in data["manual_pdf_error"]


def test_documentation_get_reports_pdf_generation_failed(client, env):
    """reportlab present but the PDF write raised — the API must report the
    failure, not silently omit the PDF."""
    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")
    manual_dir = env["transcriptions"] / "demo_Frames" / "demo" / "manual"
    (manual_dir / "assets").mkdir(parents=True)
    (manual_dir / "MANUAL.md").write_text("# demo.mp4\n\n## 1. Step\n", encoding="utf-8")
    (manual_dir / "metadata.json").write_text(
        json.dumps({"manual_pdf": "failed"}), encoding="utf-8"
    )

    video_id = mid(MediaRoot.VIDEOS, "demo.mp4")
    data = client.get(f"/api/documentation{q(video_id)}").get_json()

    assert data["manual_pdf_available"] is False
    assert data["manual_pdf_url"] is None
    assert "failed" in data["manual_pdf_error"]


def test_documentation_get_includes_editable_steps(client, real_docs):
    resp = client.get(f"/api/documentation{q(real_docs)}")
    data = resp.get_json()
    assert data["ok"] is True
    assert len(data["steps"]) == 1
    step = data["steps"][0]
    assert step["id"] == "step-0001"
    assert step["instruction"] == "Click Save."
    assert step["reviewed"] is False
    assert "/doc-asset?id=" in step["frame_url"]
    assert client.get(step["frame_url"]).status_code == 200, "frame_url must actually be servable"


def test_patch_step_edits_instruction_and_persists(client, real_docs):
    resp = client.patch(
        f"/api/documentation/step{q(real_docs)}",
        json={"step_id": "step-0001", "instruction": "Confirmed: click the blue Save button."},
        headers=AUTH_HEADERS,
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["step"]["instruction"] == "Confirmed: click the blue Save button."
    assert data["step"]["reviewed"] is True
    # Regression: the frontend updates this one step's card in place from
    # this response (no full reload) — without frame_url here, the step's
    # thumbnail would vanish on every edit.
    assert "/doc-asset?id=" in data["step"]["frame_url"]
    assert client.get(data["step"]["frame_url"]).status_code == 200

    # Persisted — a fresh GET reflects the edit without any extra action.
    follow_up = client.get(f"/api/documentation{q(real_docs)}").get_json()
    assert "Confirmed: click the blue Save button." in follow_up["manual_markdown"]


def test_patch_step_requires_dashboard_token(client, real_docs):
    resp = client.patch(f"/api/documentation/step{q(real_docs)}", json={"step_id": "step-0001", "instruction": "x"})
    assert resp.status_code == 403


def test_patch_unknown_step_404(client, real_docs):
    resp = client.patch(
        f"/api/documentation/step{q(real_docs)}", json={"step_id": "step-9999", "instruction": "x"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404


def test_delete_step_removes_and_regenerates(client, real_docs):
    resp = client.delete(f"/api/documentation/step{q(real_docs)}&step_id=step-0001", headers=AUTH_HEADERS)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["step_count"] == 0

    follow_up = client.get(f"/api/documentation{q(real_docs)}").get_json()
    assert follow_up["steps"] == []
    assert "Click Save" not in follow_up["manual_markdown"]


def test_delete_step_requires_dashboard_token(client, real_docs):
    resp = client.delete(f"/api/documentation/step{q(real_docs)}&step_id=step-0001")
    assert resp.status_code == 403


def test_regenerate_endpoint_rebuilds_from_steps_json(client, real_docs):
    resp = client.post(f"/api/documentation/regenerate{q(real_docs)}", headers=AUTH_HEADERS)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["step_count"] == 1


# ── /api/documentation/generate (explicit Generate Documentation) ─────────

def test_generate_endpoint_succeeds_when_frame_mapping_exists(client, real_docs):
    """A video with frame_mapping.json on disk → generate produces (or
    regenerates) the manual + AI package and reports the row's doc state."""
    resp = client.post(f"/api/documentation/generate{q(real_docs)}", headers=AUTH_HEADERS)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["documentation"]["has_manual"] is True
    assert data["documentation"]["has_ai_package"] is True


def test_generate_endpoint_409_when_prerequisites_missing(client, env):
    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")
    video_id = mid(MediaRoot.VIDEOS, "demo.mp4")
    resp = client.post(f"/api/documentation/generate{q(video_id)}", headers=AUTH_HEADERS)
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["ok"] is False
    assert "frame_mapping.json" in data["error"]
    assert "RUN Full" in data["error"]


def test_generate_endpoint_rejects_concurrent_duplicate(client, real_docs, monkeypatch):
    """A second generate for the same media_id while one is in flight → 409.

    The Flask test client is synchronous, so a real concurrent request can't
    overlap — instead we simulate the in-flight state by seeding the guard
    set directly (as a background thread would leave it) and assert the
    endpoint rejects the duplicate.
    """
    import transcript_pipeline.dashboard.app as dash_app

    with dash_app._doc_generation_lock:
        dash_app._doc_generation_inflight.add(real_docs)
    try:
        resp = client.post(f"/api/documentation/generate{q(real_docs)}", headers=AUTH_HEADERS)
        assert resp.status_code == 409
        assert "already generating" in resp.get_json()["error"]
    finally:
        with dash_app._doc_generation_lock:
            dash_app._doc_generation_inflight.discard(real_docs)


def test_files_response_includes_documentation_flags(client, env):
    video = env["videos"] / "demo.mp4"
    video.write_bytes(b"fake")
    manual_dir = env["transcriptions"] / "demo_Frames" / "demo" / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "metadata.json").write_text("{}", encoding="utf-8")

    resp = client.get("/api/files")
    files = resp.get_json()["files"]
    assert files[0]["documentation"]["has_manual"] is True
    assert files[0]["documentation"]["has_ai_package"] is False


# ── stage inference (pure function, no Flask needed) ────────────────────

def test_infer_stage_tracks_furthest_stage_reached():
    log = "\n".join([
        "STEP 1: Compressing videos...",
        "[SCAN] Folder detected: audio/demo",
        "[INIT] Loading Whisper model large-v3...",
        "[KEYFRAMES] Extrayendo frames de: demo.mp4",
    ])
    assert dashboard_app._infer_stage(log) == "vision_ocr"


def test_infer_stage_does_not_regress_on_next_file_in_multi_file_run():
    log = "\n".join([
        "[DOCS] Generated manual + AI package for demo1.mp4",
        "[SAVE] demo1.txt",
        "[SCAN] Folder detected: audio/demo2",  # file #2 starting over at "analyze"
    ])
    assert dashboard_app._infer_stage(log) == "store"


def test_infer_stage_returns_none_for_empty_log():
    assert dashboard_app._infer_stage("") is None


# ── RUN pipeline trigger with a stubbed expensive stage ──────────────────
# US-001 §11.3 #4/#5: "Full pipeline can be triggered using a controlled
# test fixture/stubbed expensive stage" / "Pipeline state updates visibly".
# Deliberately NOT a real subprocess run (no real ffmpeg/faster-whisper) —
# that would mean CI/local test runs actually compressing+transcribing
# real media, which is exactly what "stubbed expensive stage" rules out.

class _FakeCompletedProcess:
    def __init__(self, lines: list[str], delay: float = 0.0):
        self._lines = lines
        self._delay = delay
        self.returncode = 0

    @property
    def stdout(self):
        def _gen():
            for line in self._lines:
                if self._delay:
                    time.sleep(self._delay)
                yield line
        return _gen()

    def wait(self) -> int:
        return self.returncode


def test_run_full_triggers_pipeline_and_stage_updates_visibly(client, env, monkeypatch):
    calls = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        if "compress_and_move.py" in cmd[1]:
            return _FakeCompletedProcess(["STEP 1 stub: nothing to compress\n"])
        return _FakeCompletedProcess([
            "[SCAN] Folder detected: audio/demo\n",
            "[INIT] Loading Whisper model large-v3...\n",
            "[KEYFRAMES] Extrayendo frames de: demo.mp4\n",
            "[DOCS] Generated manual + AI package for demo.mp4 (1 steps, 0 low-confidence)\n",
            "[SAVE] demo.txt\n",
        ], delay=0.05)

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)

    resp = client.post("/api/run/full", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    # Immediately after triggering, state must already reflect a running pipeline.
    status = client.get("/api/status").get_json()
    assert status["running"] is True
    assert status["mode"] == "full"

    for _ in range(50):
        status = client.get("/api/status").get_json()
        if not status["running"]:
            break
        time.sleep(0.05)

    assert status["running"] is False
    assert status["finished_at"] is not None
    assert status["stage"] == "store"  # furthest real marker seen: "[SAVE]"
    assert "[DOCS]" in status["log_tail"]
    assert len(calls) == 2  # compress step + transcribe step, both stubbed


def test_run_rejects_second_run_while_one_in_progress(client, env, monkeypatch):
    def slow_popen(cmd, **kwargs):
        time.sleep(0.3)
        return _FakeCompletedProcess(["ok\n"])

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", slow_popen)

    first = client.post("/api/run/transcribe", headers=AUTH_HEADERS)
    assert first.status_code == 200

    second = client.post("/api/run/transcribe", headers=AUTH_HEADERS)
    assert second.status_code == 409

    for _ in range(20):
        if not client.get("/api/status").get_json()["running"]:
            break
        time.sleep(0.05)
