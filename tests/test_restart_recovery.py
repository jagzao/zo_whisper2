"""Restart/recovery integrity (AC12): a fresh dashboard starts from a clean
run state, and a mid-run kill must never fabricate "processed" statuses.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from transcript_pipeline.dashboard import app as dashboard_app


@pytest.fixture
def env(tmp_path, monkeypatch):
    videos = tmp_path / "Videos"
    transcriptions = tmp_path / "CarpetaTranscripciones"
    for d in (videos, transcriptions):
        d.mkdir(parents=True)

    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", videos)
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", transcriptions)
    monkeypatch.setattr(dashboard_app, "PROCESSED_DB", tmp_path / "processed_files.json")
    return {"root": tmp_path, "videos": videos, "transcriptions": transcriptions}


def test_run_state_resets_on_restart(monkeypatch):
    assert len(dashboard_app.PIPELINE_STAGES) == 8
    fresh = dashboard_app._fresh_stages()
    assert set(fresh) == set(dashboard_app.PIPELINE_STAGES)
    assert all(entry == {"status": "pending", "progress": None} for entry in fresh.values())

    # Simulate a process restart: brand-new module-level state, no carry-over
    # from a previous run's stages/log/error.
    restarted = {
        "running": False,
        "mode": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "log_tail": "",
        "stage": None,
        "stages": dashboard_app._fresh_stages(),
    }
    monkeypatch.setattr(dashboard_app, "_run_state", restarted)

    status = dashboard_app.app.test_client().get("/api/status").get_json()
    assert status["running"] is False
    assert status["finished_at"] is None
    assert status["error"] is None
    assert all(entry["status"] == "pending" for entry in status["stages"].values())


def test_file_status_never_fabricates_processed(env):
    unknown = env["videos"] / "unknown.mp4"
    unknown.write_bytes(b"data")

    # No database at all -> pending, never an assumed "processed".
    assert dashboard_app._file_status(unknown) == "pending"

    # Database exists but holds unrelated entries -> still pending.
    dashboard_app.PROCESSED_DB.write_text(
        json.dumps({"deadbeef": {"status": "completed"}}), encoding="utf-8"
    )
    assert dashboard_app._file_status(unknown) == "pending"


def test_file_status_reads_real_db_entry(env):
    known = env["videos"] / "known.mp4"
    known.write_bytes(b"data")

    size = known.stat().st_size
    mtime = int(known.stat().st_mtime)
    chunk = known.read_bytes()[:8192]
    content = f"{size}_{mtime}_{hashlib.md5(chunk).hexdigest()}"
    file_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    dashboard_app.PROCESSED_DB.write_text(
        json.dumps({file_hash: {"status": "completed"}}), encoding="utf-8"
    )
    assert dashboard_app._file_status(known) == "completed"


def test_atomic_write_text_uses_temp_then_replace(env, monkeypatch):
    target = env["root"] / "atomic.txt"
    target.write_text("original", encoding="utf-8")

    replaced: dict[str, Path] = {}
    real_replace = os.replace

    def spy(src, dst):
        replaced["src"] = Path(src)
        replaced["dst"] = Path(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(dashboard_app.os, "replace", spy)
    dashboard_app._atomic_write_text(target, "new content")

    assert target.read_text(encoding="utf-8") == "new content"
    assert replaced["dst"] == target
    assert replaced["src"] != target
    assert replaced["src"].name.startswith(".atomic.txt.")
    assert [p.name for p in env["root"].iterdir() if p.name.startswith(".atomic.txt.")] == []


def test_atomic_write_text_keeps_original_on_failure(env, monkeypatch):
    target = env["root"] / "atomic.txt"
    target.write_text("original", encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(dashboard_app.os, "replace", boom)

    with pytest.raises(OSError):
        dashboard_app._atomic_write_text(target, "new content")

    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in env["root"].iterdir() if p.name.startswith(".atomic.txt.")] == []
