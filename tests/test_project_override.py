"""Coverage for the manual project override (Edit File) feature.

A manual assignment persisted in `project_overrides.json` must win over
filename-based auto-detection, survive dashboard restarts, be removable
back to Auto-detect, and never touch the transcript/frames/docs artifacts.
Same isolated-tmp-path fixture pattern as tests/test_dashboard_new_endpoints.py.
"""
from __future__ import annotations

import json
import time

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.security import MediaRoot, SafePathResolver

AUTH_HEADERS = {"X-Local-Dashboard-Token": "test-dashboard-token"}

PROJECTS = {
    "projects": [
        {
            "name": "Alpha",
            "match": {"prefix": ["alpha_"], "filename_contains": []},
            "language": "en",
        },
        {
            "name": "Beta",
            "match": {"prefix": ["beta_"], "filename_contains": []},
            "language": "es",
        },
    ]
}


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
    (tmp_path / "projects.json").write_text(json.dumps(PROJECTS), encoding="utf-8")
    return {"root": tmp_path, "audio": audio, "videos": videos, "transcriptions": transcriptions}


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


@pytest.fixture
def media(env):
    """A video auto-detected as Alpha plus its transcription on disk."""
    video = env["videos"] / "alpha_demo.mp4"
    video.write_bytes(b"fake-video")
    tx = env["transcriptions"] / "alpha_demo.txt"
    tx.write_text("original transcription text", encoding="utf-8")
    return {
        "media_id": "videos:alpha_demo.mp4",
        "tx_id": "transcriptions:alpha_demo.txt",
        "video": video,
        "tx": tx,
    }


def _save(client, media, project, text="edited text"):
    return client.post(
        "/api/transcription",
        json={"id": media["tx_id"], "text": text, "project": project, "media_id": media["media_id"]},
        headers=AUTH_HEADERS,
    )


def _file_row(client, media_id):
    files = client.get("/api/files").get_json()["files"]
    return next(f for f in files if f["media_id"] == media_id)


# ── auto detection ───────────────────────────────────────────────────────

def test_auto_detection_without_override(client, media):
    row = _file_row(client, media["media_id"])
    assert row["project"] == "Alpha"
    assert row["project_source"] == "auto"


def test_no_project_when_nothing_matches(client, env):
    video = env["videos"] / "unmatched.mp4"
    video.write_bytes(b"fake")
    row = _file_row(client, "videos:unmatched.mp4")
    assert row["project"] is None
    assert row["project_source"] == "none"


# ── manual override ──────────────────────────────────────────────────────

def test_manual_wins_over_auto(client, media):
    resp = _save(client, media, "Beta")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["project"] == "Beta"
    assert data["project_source"] == "manual"

    row = _file_row(client, media["media_id"])
    assert row["project"] == "Beta"
    assert row["project_source"] == "manual"


def test_override_persists_across_reload(client, media, env):
    _save(client, media, "Beta")

    # Simulate a dashboard restart: the module keeps no in-memory cache, so a
    # fresh read must come from disk.
    overrides = dashboard_app._load_project_overrides()
    assert overrides == {media["media_id"]: "Beta"}

    persisted = json.loads((env["root"] / "project_overrides.json").read_text(encoding="utf-8"))
    assert persisted == {"overrides": {media["media_id"]: "Beta"}}

    # And a brand-new client (fresh request cycle) still sees the override.
    with dashboard_app.app.test_client() as c2:
        row = _file_row(c2, media["media_id"])
        assert row["project"] == "Beta"
        assert row["project_source"] == "manual"


def test_autodetect_removes_override(client, media, env):
    _save(client, media, "Beta")
    resp = _save(client, media, "")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["project"] == "Alpha"
    assert data["project_source"] == "auto"

    assert dashboard_app._load_project_overrides() == {}
    row = _file_row(client, media["media_id"])
    assert row["project"] == "Alpha"
    assert row["project_source"] == "auto"


def test_autodetect_accepts_null_and_auto(client, media):
    for value in (None, "auto", "Auto"):
        _save(client, media, "Beta")
        resp = _save(client, media, value)
        assert resp.status_code == 200
        assert resp.get_json()["project_source"] == "auto"
        assert dashboard_app._load_project_overrides() == {}


def test_inexistent_project_returns_400(client, media):
    resp = _save(client, media, "NoSuchProject")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "Project not found: NoSuchProject"

    # Nothing was persisted and the transcription was not touched.
    assert dashboard_app._load_project_overrides() == {}
    assert media["tx"].read_text(encoding="utf-8") == "original transcription text"


def test_stale_override_dropped_and_reports_none(client, media, env):
    _save(client, media, "Beta")
    # Remove Beta from projects.json — the override now points nowhere.
    (env["root"] / "projects.json").write_text(
        json.dumps({"projects": [PROJECTS["projects"][0]]}), encoding="utf-8"
    )

    row = _file_row(client, media["media_id"])
    assert row["project"] is None
    assert row["project_source"] == "none"
    assert dashboard_app._load_project_overrides() == {}


# ── no side effects on artifacts ─────────────────────────────────────────

def test_project_change_does_not_modify_transcript_or_artifacts(client, media, env):
    frames_parent = env["transcriptions"] / "alpha_demo_Frames" / "alpha_demo"
    manual_dir = frames_parent / "manual"
    (manual_dir / "assets").mkdir(parents=True)
    frame = frames_parent / "frame_0000.png"
    frame.write_bytes(b"fake-png")
    manual_md = manual_dir / "MANUAL.md"
    manual_md.write_text("# alpha_demo.mp4\n\n## 1. Step\n", encoding="utf-8")
    asset = manual_dir / "assets" / "step-0001.png"
    asset.write_bytes(b"fake-asset")

    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in (frame, manual_md, asset)
    }
    time.sleep(0.01)

    resp = _save(client, media, "Beta", text="edited transcription text")
    assert resp.status_code == 200

    # The transcription itself was updated (that is the point of the save)…
    assert media["tx"].read_text(encoding="utf-8") == "edited transcription text"
    # …but frames/docs/assets are byte-identical and untouched.
    for p, (content, mtime_ns) in before.items():
        assert p.read_bytes() == content, f"{p.name} content changed"
        assert p.stat().st_mtime_ns == mtime_ns, f"{p.name} mtime changed"