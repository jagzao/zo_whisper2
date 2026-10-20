from __future__ import annotations

import os
from concurrent.futures import Future
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.live_capture.models import ChunkState
from transcript_pipeline.live_capture.service import CaptureService
from transcript_pipeline.security import MediaRoot, SafePathResolver


@pytest.fixture
def env(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in ("Videos", "audio", "Video_compress", "CarpetaTranscripciones")}
    for path in paths.values():
        path.mkdir()
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "VIDEOS_BASE", paths["Videos"])
    monkeypatch.setattr(dashboard_app, "AUDIO_BASE", paths["audio"])
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", paths["Video_compress"])
    monkeypatch.setattr(dashboard_app, "TRANSCRIPTIONS_BASE", paths["CarpetaTranscripciones"])
    monkeypatch.setattr(dashboard_app, "RESOLVER", SafePathResolver({
        MediaRoot.VIDEOS: paths["Videos"], MediaRoot.AUDIO: paths["audio"],
        MediaRoot.VIDEO_COMPRESS: paths["Video_compress"], MediaRoot.TRANSCRIPTIONS: paths["CarpetaTranscripciones"],
    }))
    monkeypatch.setattr(dashboard_app, "_capture_service", None)
    monkeypatch.setattr(dashboard_app, "_capture_service_root", None)
    return {"videos": paths["Videos"]}


@pytest.fixture
def client(env):
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def _capture(service, title, recorded_at):
    session = service.create_session(title, recorded_at=recorded_at)
    chunk = service.start_chunk(session.session_id, recorded_at=recorded_at)
    service.finalize_chunk(session.session_id, chunk.index, b"synthetic")
    service.finalize_session(session.session_id)
    return service.store.chunk_media_path(session.session_id, 0, ".webm")


def test_files_api_uses_capture_recorded_at_and_sorts_all_rows(client, env):
    service = CaptureService(env["videos"])
    older = _capture(service, "older", "2024-01-01T00:00:00+00:00")
    newer = _capture(service, "newer", "2025-01-01T00:00:00+00:00")
    legacy = env["videos"] / "legacy.mp4"
    legacy.write_bytes(b"legacy")
    os.utime(legacy, (datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp(),) * 2)

    desc = client.get("/api/files?sort_by=date&order=desc").json["files"]
    assert [item["name"] for item in desc] == ["newer.webm", "older.webm", legacy.name]
    assert all(not item["name"].startswith("chunk-") for item in desc)
    assert desc[0]["date_epoch"] == datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
    assert [item["name"] for item in client.get("/api/files").json["files"]] == [item["name"] for item in desc]
    asc = client.get("/api/files?sort_by=date&order=asc").json["files"]
    assert [item["name"] for item in asc] == [legacy.name, "older.webm", "newer.webm"]


def test_files_api_falls_back_to_created_at_when_capture_recorded_at_missing(client, env):
    service = CaptureService(env["videos"])
    session = service.create_session(
        "created fallback", created_at="2022-02-03T04:05:06+00:00", recorded_at="2022-02-03T04:05:06+00:00"
    )
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"synthetic")
    stored = service.store.load_session(session.session_id)
    chunk = replace(stored.get_chunk(0), recorded_at=None, created_at="2022-02-03T04:05:06+00:00")
    session = replace(stored.with_chunk(chunk), recorded_at=None)
    service.store.save_session(session)
    path = service.store.chunk_media_path(session.session_id, 0, ".webm")
    rows = client.get("/api/files").json["files"]
    row = next(item for item in rows if item.get("capture_session_id") == session.session_id)
    assert row["name"] == "created fallback.webm"
    assert row["date_epoch"] == datetime(2022, 2, 3, 4, 5, 6, tzinfo=timezone.utc).timestamp()
    assert service.get_session(session.session_id).get_chunk(0).state is ChunkState.FINALIZED


def test_files_api_exposes_actual_duration_and_sorts_it(client, env, monkeypatch):
    short = env["videos"] / "short.mp4"
    long = env["videos"] / "long.mp4"
    short.write_bytes(b"synthetic")
    long.write_bytes(b"synthetic")
    monkeypatch.setattr(dashboard_app, "_probe_media_duration", lambda path: 14.2 if path.name == "short.mp4" else 3862.0)

    rows = client.get("/api/files?sort_by=duration&order=desc").json["files"]

    assert [row["name"] for row in rows] == ["long.mp4", "short.mp4"]
    assert [row["duration"] for row in rows] == ["1:04:22", "00:14"]


def test_duration_probe_is_nonblocking_and_cache_refreshes(tmp_path, monkeypatch):
    path = tmp_path / "large.mp4"
    path.write_bytes(b"media")
    future = Future()

    class DeferredExecutor:
        def submit(self, _function, _path):
            return future

    monkeypatch.setattr(dashboard_app, "_MEDIA_DURATION_EXECUTOR", DeferredExecutor())
    assert dashboard_app._probe_media_duration(path) is None
    assert dashboard_app._media_duration_pending(path)
    future.set_result(42.8)
    assert dashboard_app._probe_media_duration(path) == 42.8
    assert not dashboard_app._media_duration_pending(path)


def test_capture_delete_action_is_explicit_and_state_based(client, env, monkeypatch):
    service = CaptureService(env["videos"])
    monkeypatch.setattr(dashboard_app, "_get_capture_service", lambda: service)
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", "unit-test-token")
    headers = {"X-Local-Dashboard-Token": "unit-test-token"}
    assert dashboard_app._delete_action("COMPLETED") == (True, None)
    assert dashboard_app._delete_action("READY") == (True, None)
    assert dashboard_app._delete_action("PROCESSING_MEDIA") == (False, "Stop processing before deleting")
    assert dashboard_app._delete_action("CAPTURING", capture_active=True) == (False, "Stop the recording before deleting")

    active = service.create_session("active session")
    active_final = service.store.final_media_path(active.session_id, ".webm")
    active_final.parent.mkdir(parents=True)
    active_final.write_bytes(b"synthetic")
    active_id = f"videos:live_capture/{active.session_id}/final/recording.webm"
    blocked = client.delete(f"/api/file?id={active_id}&confirm=true", headers=headers)
    assert blocked.status_code == 409
    assert active_final.exists()
    active_row = next(row for row in client.get("/api/files").json["files"]
                      if row.get("capture_session_id") == active.session_id)
    assert active_row["delete_allowed"] is False
    assert active_row["delete_reason"] == "Stop the recording before deleting"

    completed = service.create_session("completed session")
    chunk = service.start_chunk(completed.session_id)
    service.finalize_chunk(completed.session_id, chunk.index, b"synthetic")
    stored = service.store.load_session(completed.session_id)
    processed = replace(stored.chunks[0], state=ChunkState.PROCESSED)
    service.store.save_session(replace(stored, chunks=(processed,)))
    service.finalize_session(completed.session_id)
    final_path = service.store.final_media_path(completed.session_id, ".webm")
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"synthetic")
    media_id = f"videos:live_capture/{completed.session_id}/final/recording.webm"
    completed_row = next(row for row in client.get("/api/files").json["files"]
                         if row.get("capture_session_id") == completed.session_id)
    assert completed_row["delete_allowed"] is True
    deleted = client.delete(f"/api/file?id={media_id}&confirm=true", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json["capture_session_deleted"] is True
    assert not service.store.session_dir(completed.session_id).exists()
