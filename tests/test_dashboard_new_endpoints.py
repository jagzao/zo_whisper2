"""Coverage for the US-001 dashboard additions: operational metrics
(§3.3), documentation links (§3.5/§3.6), and real-log-derived pipeline
stage inference (§3.4). Same isolated-tmp-path fixture pattern as
tests/security/test_dashboard_endpoints.py.
"""
from __future__ import annotations

import json
import re
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
