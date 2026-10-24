from __future__ import annotations

import hashlib
import os
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from transcript_pipeline.dashboard import app as dashboard_app
from transcript_pipeline.dashboard import resumable_uploads as upload_module

AUTH = {"X-Local-Dashboard-Token": "test-dashboard-token"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    video_compress = tmp_path / "Video_compress"
    video_compress.mkdir()
    monkeypatch.setattr(dashboard_app, "ROOT", tmp_path)
    monkeypatch.setattr(dashboard_app, "VIDEO_COMPRESS", video_compress)
    monkeypatch.setattr(dashboard_app, "_processing_worker", None)
    monkeypatch.setattr(dashboard_app, "_processing_worker_root", None)
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_TOKEN", AUTH["X-Local-Dashboard-Token"])
    monkeypatch.setattr(dashboard_app, "_is_valid_media_file", lambda _path: True)
    monkeypatch.setattr(upload_module, "CHUNK_SIZE", 4)
    monkeypatch.setattr(upload_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=10 * 1024**3))
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def _new_session(client, filename="sample.mp4", size=10):
    result = client.post("/api/uploads", json={"filename": filename, "size": size}, headers=AUTH)
    assert result.status_code == 200
    return result.get_json()["session"]["id"]


def _put(client, session_id, index, chunk, digest=None):
    return client.put(f"/api/uploads/{session_id}/chunks/{index}", data=chunk, headers={
        **AUTH, "X-Chunk-SHA256": digest or hashlib.sha256(chunk).hexdigest(),
        "Content-Type": "application/octet-stream",
    })


def test_chunk_split_ack_is_idempotent_and_rejects_bad_hash(client):
    session_id = _new_session(client)
    chunks = [b"abcd", b"efgh", b"ij"]
    for index, chunk in enumerate(chunks):
        assert _put(client, session_id, index, chunk).status_code == 200
    assert _put(client, session_id, 1, chunks[1]).get_json()["received"] == [0, 1, 2]
    bad = _put(client, session_id, 1, b"xxxx")
    assert bad.status_code == 409
    assert bad.get_json()["error"] == "Chunk conflicts with an acknowledged chunk"
    assert _put(client, session_id, 2, b"12345").status_code == 413


def test_resume_partial_upload_and_finalize_hash_size(client):
    session_id = _new_session(client)
    assert _put(client, session_id, 0, b"abcd").status_code == 200
    listing = client.get("/api/uploads").get_json()["sessions"]
    saved = next(item for item in listing if item["id"] == session_id)
    assert saved["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}
    for index, chunk in enumerate((b"efgh", b"ij"), start=1):
        _put(client, session_id, index, chunk)
    finalized = client.post(f"/api/uploads/{session_id}/finalize", headers=AUTH).get_json()
    assert finalized["size"] == 10
    assert finalized["sha256"] == hashlib.sha256(b"abcdefghij").hexdigest()
    assert (dashboard_app.VIDEO_COMPRESS / finalized["name"]).read_bytes() == b"abcdefghij"
    duplicate = client.post(f"/api/uploads/{session_id}/finalize", headers=AUTH).get_json()
    assert duplicate["duplicate"] is True
    assert duplicate["job_id"] == finalized["job_id"]


@pytest.mark.parametrize("state", ["PAUSED", "FAILED", "FINALIZING"])
def test_resume_endpoint_reactivates_incomplete_session_and_preserves_acks(client, state):
    session_id = _new_session(client)
    assert _put(client, session_id, 0, b"abcd").status_code == 200
    service = dashboard_app._resumable_uploads()
    directory, manifest = service._manifest(session_id)
    manifest["state"] = state
    service._save(directory / "session.json", manifest)

    response = client.post(f"/api/uploads/{session_id}/resume", headers=AUTH)

    assert response.status_code == 200
    resumed = response.get_json()["session"]
    assert resumed["state"] == "UPLOADING"
    assert resumed["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}
    assert _put(client, session_id, 1, b"efgh").status_code == 200


def test_completed_upload_cannot_be_resumed(client):
    session_id = _new_session(client)
    for index, chunk in enumerate((b"abcd", b"efgh", b"ij")):
        assert _put(client, session_id, index, chunk).status_code == 200
    assert client.post(f"/api/uploads/{session_id}/finalize", headers=AUTH).status_code == 200

    response = client.post(f"/api/uploads/{session_id}/resume", headers=AUTH)

    assert response.status_code == 409
    assert response.get_json()["error"] == "Completed upload cannot be resumed"


def test_stale_upload_session_resumes_from_acknowledged_map(client):
    import time

    session_id = _new_session(client)
    assert _put(client, session_id, 0, b"abcd").status_code == 200
    service = dashboard_app._resumable_uploads()
    directory, manifest = service._manifest(session_id)
    manifest["last_ack_at"] = time.time() - 600
    service._save(directory / "session.json", manifest)
    stale = next(item for item in service.list() if item["id"] == session_id)
    assert stale["logical_state"] == "STALE_RESUMABLE"

    resumed = client.post(f"/api/uploads/{session_id}/resume", json={"project_id": "P&G"}, headers=AUTH)

    assert resumed.status_code == 200
    assert resumed.get_json()["session"]["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}
    assert resumed.get_json()["session"]["project_id"] == "P&G"
    assert _put(client, session_id, 1, b"efgh").status_code == 200


def test_cancel_one_session_preserves_another(client):
    first, second = _new_session(client, "one.mp4"), _new_session(client, "two.mp4")
    _put(client, first, 0, b"abcd")
    assert client.delete(f"/api/uploads/{first}", headers=AUTH).status_code == 200
    assert [row["id"] for row in client.get("/api/uploads").get_json()["sessions"]] == [second]


def test_failed_chunk_request_recovers_without_restarting_file(client, monkeypatch):
    original = upload_module.ResumableUploads.acknowledge
    failed = False

    def flaky(self, *args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("simulated upstream 502")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(upload_module.ResumableUploads, "acknowledge", flaky)
    session_id = _new_session(client)
    first = _put(client, session_id, 0, b"abcd")
    assert first.status_code == 502
    recovered = _put(client, session_id, 0, b"abcd")
    assert recovered.status_code == 200
    saved = next(row for row in client.get("/api/uploads").get_json()["sessions"] if row["id"] == session_id)
    assert saved["size"] == 10
    assert saved["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}


def test_retry_adopts_matching_chunk_file_left_before_manifest_ack(client):
    session_id = _new_session(client)
    part = dashboard_app.VIDEO_COMPRESS / ".upload_sessions" / session_id / "00000000.part"
    part.write_bytes(b"abcd")

    response = _put(client, session_id, 0, b"abcd")

    assert response.status_code == 200
    saved = client.get(f"/api/uploads/{session_id}").get_json()["session"]
    assert saved["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}
    assert part.read_bytes() == b"abcd"


def test_retry_replaces_incomplete_orphan_chunk_before_ack(client):
    session_id = _new_session(client)
    part = dashboard_app.VIDEO_COMPRESS / ".upload_sessions" / session_id / "00000000.part"
    part.write_bytes(b"old!")

    response = _put(client, session_id, 0, b"abcd")

    assert response.status_code == 200
    saved = client.get(f"/api/uploads/{session_id}").get_json()["session"]
    assert saved["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}
    assert part.read_bytes() == b"abcd"


def test_synthetic_multigb_upload_resumes_without_resending_acked_chunks(client, monkeypatch):
    size = 5 * 1024**3
    session_id = _new_session(client, "synthetic-large.mp4", size)
    acknowledged = _put(client, session_id, 0, b"abcd")
    assert acknowledged.status_code == 200
    original = upload_module.ResumableUploads.acknowledge
    fail_once = True

    def flaky(self, upload_id, index, *args, **kwargs):
        nonlocal fail_once
        if index == 1 and fail_once:
            fail_once = False
            raise OSError("simulated upstream 502")
        return original(self, upload_id, index, *args, **kwargs)

    monkeypatch.setattr(upload_module.ResumableUploads, "acknowledge", flaky)
    failed = _put(client, session_id, 1, b"efgh")
    assert failed.status_code == 502
    resumed = client.get(f"/api/uploads/{session_id}")
    assert resumed.get_json()["session"]["size"] == size
    assert resumed.get_json()["session"]["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}
    assert _put(client, session_id, 1, b"efgh").status_code == 200
    final_state = client.get(f"/api/uploads/{session_id}").get_json()["session"]
    assert final_state["chunks"] == {
        "0": hashlib.sha256(b"abcd").hexdigest(),
        "1": hashlib.sha256(b"efgh").hexdigest(),
    }


def test_storage_preflight_sums_batch_and_rejects_before_session_creation(client, monkeypatch):
    monkeypatch.setattr(upload_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=3 * 1024**3))
    response = client.post("/api/uploads/preflight", json={"uploads": [{"size": 800 * 1024**2}, {"size": 800 * 1024**2}]}, headers=AUTH)
    assert response.status_code == 507
    assert response.is_json
    assert response.get_json()["error"].startswith("Insufficient storage: 3.0 GiB free, 3.6 GiB required.")
    created = client.post("/api/uploads", json={"filename": "unsafe.mp4", "size": 2 * 1024**3}, headers=AUTH)
    assert created.status_code == 507
    assert created.is_json
    assert not client.get("/api/uploads").get_json()["sessions"]


def test_finalize_storage_failure_preserves_acknowledged_chunks(client, monkeypatch):
    session_id = _new_session(client)
    for index, chunk in enumerate((b"abcd", b"efgh", b"ij")):
        assert _put(client, session_id, index, chunk).status_code == 200
    monkeypatch.setattr(upload_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=1))
    response = client.post(f"/api/uploads/{session_id}/finalize", headers=AUTH)
    assert response.status_code == 507
    assert response.is_json
    state = client.get(f"/api/uploads/{session_id}").get_json()["session"]
    assert state["state"] == "UPLOADING"
    assert state["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest(),
                                "1": hashlib.sha256(b"efgh").hexdigest(),
                                "2": hashlib.sha256(b"ij").hexdigest()}


def test_chunk_storage_failure_rejects_new_chunk_and_preserves_prior_ack(client, monkeypatch):
    session_id = _new_session(client)
    assert _put(client, session_id, 0, b"abcd").status_code == 200
    monkeypatch.setattr(upload_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=1))
    response = _put(client, session_id, 1, b"efgh")
    assert response.status_code == 507
    assert response.is_json
    saved = client.get(f"/api/uploads/{session_id}").get_json()["session"]
    assert saved["chunks"] == {"0": hashlib.sha256(b"abcd").hexdigest()}


def test_enospc_is_json_507_for_chunk_and_finalize(client, monkeypatch):
    session_id = _new_session(client)

    def no_space(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(upload_module.ResumableUploads, "acknowledge", no_space)
    chunk = _put(client, session_id, 0, b"abcd")
    assert chunk.status_code == 507
    assert chunk.is_json
    assert chunk.get_json()["error"].startswith("Insufficient storage:")
    monkeypatch.setattr(upload_module.ResumableUploads, "acknowledge", lambda *_args, **_kwargs: {"ok": True})
    for index, data in enumerate((b"abcd", b"efgh", b"ij")):
        _put(client, session_id, index, data)
    monkeypatch.setattr(upload_module.ResumableUploads, "finalize", no_space)
    finalized = client.post(f"/api/uploads/{session_id}/finalize", headers=AUTH)
    assert finalized.status_code == 507
    assert finalized.is_json
    assert finalized.get_json()["error"].startswith("Insufficient storage:")
    session = client.get(f"/api/uploads/{session_id}").get_json()["session"]
    assert session["state"] == "UPLOADING"


def test_upload_javascript_is_in_installed_package_data():
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert "static/*.js" in config["tool"]["setuptools"]["package-data"]["transcript_pipeline.dashboard"]


def test_upload_session_list_reports_semantic_state_and_ack_activity(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_module, "CHUNK_SIZE", 4)
    service = upload_module.ResumableUploads(tmp_path / "sessions")
    session = service.create("video.mp4", 8)
    listed = service.list()[0]
    assert listed["logical_state"] == "STALE_RESUMABLE"
    assert listed["received"] == []

    first = b"1234"
    service.acknowledge(session["id"], 0, first, hashlib.sha256(first).hexdigest())
    listed = service.list()[0]
    assert listed["logical_state"] == "ACTIVE_TRANSFERRING"
    assert listed["received"] == [0]
    assert listed["last_ack_at"]

    directory, manifest = service._manifest(session["id"])
    manifest["state"] = "PAUSED"
    service._save(directory / "session.json", manifest)
    assert service.list()[0]["logical_state"] == "PAUSED_RESUMABLE"


def test_legacy_upload_session_activity_uses_chunk_write_time(tmp_path, monkeypatch):
    import time

    monkeypatch.setattr(upload_module, "CHUNK_SIZE", 4)
    service = upload_module.ResumableUploads(tmp_path / "sessions")
    session = service.create("legacy.mp4", 4)
    directory, manifest = service._manifest(session["id"])
    manifest.pop("last_ack_at")
    manifest.pop("last_activity_at")
    service._save(directory / "session.json", manifest)
    part = directory / "00000000.part"
    part.write_bytes(b"data")
    os.utime(part, (time.time(), time.time()))
    assert service.list()[0]["logical_state"] == "ACTIVE_TRANSFERRING"

    old = time.time() - 300
    os.utime(part, (old, old))
    assert service.list()[0]["logical_state"] == "STALE_RESUMABLE"
