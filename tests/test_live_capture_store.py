"""Integration tests: Live Capture manifest store and CaptureService."""

from __future__ import annotations

import json

import pytest

from transcript_pipeline.live_capture.errors import (
    ChunkNotFoundError,
    InvalidTransitionError,
    ManifestCorruptError,
    SessionConflictError,
    SessionNotFoundError,
    ValidationError,
)
from transcript_pipeline.live_capture.models import AudioAvailability, ChunkState, CropRegion, Session, SessionStatus
from transcript_pipeline.live_capture.service import CaptureService


@pytest.fixture()
def service(tmp_path):
    return CaptureService(videos_root=tmp_path / "Videos")


def _session_dir(tmp_path, session_id):
    return tmp_path / "Videos" / "live_capture" / session_id


# ── create / persist / reload ─────────────────────────────────────

def test_create_session_persists_and_reloads(service, tmp_path):
    session = service.create_session(
        "Clase de prueba", chunk_duration_sec=900, recorded_at="2026-10-15T09:00:00+00:00"
    )
    assert session.status is SessionStatus.ACTIVE
    assert session.session_id.startswith("sess-")

    manifest_path = _session_dir(tmp_path, session.session_id) / "session.json"
    assert manifest_path.exists()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert raw["schemaVersion"] == 1
    assert raw["recordedAt"] == "2026-10-15T09:00:00+00:00"

    reloaded = service.get_session(session.session_id)
    assert reloaded == session
    assert reloaded.created_at == session.created_at
    assert reloaded.recorded_at == "2026-10-15T09:00:00+00:00"
    assert reloaded.chunk_duration_sec == 900


def test_unknown_session_raises_not_found(service):
    with pytest.raises(SessionNotFoundError):
        service.get_session("sess-missing")


def test_duplicate_session_create_is_conflict(service):
    session = Session(
        session_id="sess-dup000",
        title="uno",
        status=SessionStatus.ACTIVE,
        created_at="2026-10-15T10:00:00+00:00",
        chunk_duration_sec=600,
    )
    service.store.create_session(session)
    with pytest.raises(SessionConflictError):
        service.store.create_session(session)


# ── chunk finalization and media persistence ──────────────────────

def test_chunk_lifecycle_and_media_persistence(service, tmp_path):
    session = service.create_session("grabacion")
    chunk = service.start_chunk(session.session_id)
    assert chunk.index == 0
    assert chunk.state is ChunkState.RECORDING

    data = b"synthetic-webm-bytes" * 10
    finalized = service.finalize_chunk(session.session_id, 0, data, media_extension=".webm")
    assert finalized.state is ChunkState.FINALIZED
    assert finalized.media_size_bytes == len(data)
    assert finalized.media_sha256 is not None

    media_path = _session_dir(tmp_path, session.session_id) / "chunks" / "chunk-000000.webm"
    assert media_path.read_bytes() == data
    assert not list(media_path.parent.glob("*.tmp"))

    reloaded = service.get_session(session.session_id)
    assert reloaded.chunks[0].state is ChunkState.FINALIZED
    assert reloaded.chunks[0].media_sha256 == finalized.media_sha256
    assert service.finalized_chunks(session.session_id) == [reloaded.chunks[0]]


def test_finalize_chunk_rejects_empty_bytes(service):
    session = service.create_session("vacio")
    service.start_chunk(session.session_id)
    with pytest.raises(ValidationError):
        service.finalize_chunk(session.session_id, 0, b"")
    assert service.get_session(session.session_id).chunks[0].state is ChunkState.RECORDING


def test_finalize_unknown_chunk_raises(service):
    session = service.create_session("sinchunks")
    with pytest.raises(ChunkNotFoundError):
        service.finalize_chunk(session.session_id, 0, b"data")


def test_finalize_requires_recording_state(service):
    session = service.create_session("ya")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"data")
    with pytest.raises(InvalidTransitionError):
        service.finalize_chunk(session.session_id, 0, b"mas-data")


def test_chunk_processing_transitions(service):
    session = service.create_session("procesa")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"data")
    assert service.mark_processing(session.session_id, 0).state is ChunkState.PROCESSING
    processed = service.mark_processed(session.session_id, 0)
    assert processed.state is ChunkState.PROCESSED
    assert processed.transcript_available is True
    assert service.get_session(session.session_id).chunks[0].transcript_available is True


def test_failed_chunk_is_retryable(service):
    session = service.create_session("retry")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"data")
    service.mark_processing(session.session_id, 0)
    assert service.mark_failed(session.session_id, 0).state is ChunkState.FAILED
    assert service.mark_processing(session.session_id, 0).state is ChunkState.PROCESSING


# ── reconciliation / playability ──────────────────────────────────

def test_reconcile_marks_interrupted_recording_not_playable(service):
    session = service.create_session("interrumpida")
    service.start_chunk(session.session_id)  # chunk 0
    service.start_chunk(session.session_id)  # chunk 1, never finalized
    service.finalize_chunk(session.session_id, 0, b"data-0")

    reconciled = service.reconcile(session.session_id)
    assert reconciled.status is SessionStatus.FAILED
    assert reconciled.reason == "interrupted"
    assert reconciled.get_chunk(0).state is ChunkState.FINALIZED
    assert reconciled.get_chunk(1).state is ChunkState.UPLOAD_CANCELLED
    assert service.finalized_chunks(session.session_id) == [reconciled.get_chunk(0)]


def test_reconcile_demotes_finalized_without_media(service, tmp_path):
    session = service.create_session("sinmedia")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"data")
    media = _session_dir(tmp_path, session.session_id) / "chunks" / "chunk-000000.webm"
    media.unlink()

    reconciled = service.reconcile(session.session_id)
    assert reconciled.chunks[0].state is ChunkState.FAILED
    assert service.finalized_chunks(session.session_id) == []


def test_reconcile_is_idempotent(service):
    session = service.create_session("idem")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"data")
    assert service.reconcile(session.session_id) == service.reconcile(session.session_id)


# ── corrupt manifest handling ─────────────────────────────────────

def test_malformed_manifest_raises_and_does_not_delete_media(service, tmp_path):
    session = service.create_session("corrupta")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"media-bytes")
    manifest = _session_dir(tmp_path, session.session_id) / "session.json"
    media = _session_dir(tmp_path, session.session_id) / "chunks" / "chunk-000000.webm"
    manifest.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ManifestCorruptError):
        service.get_session(session.session_id)
    assert media.exists()  # media is never deleted


def test_list_sessions_newest_first(service):
    a = service.create_session("primera", created_at="2026-10-15T10:00:00+00:00")
    b = service.create_session("segunda", created_at="2026-10-15T11:00:00+00:00")
    assert [s.session_id for s in service.list_sessions()] == [b.session_id, a.session_id]


def test_test_session_cleanup_requires_marker_and_explicit_confirmation(service):
    user_session = service.create_session("user media")
    test_session = service.create_session("synthetic fixture", is_test_session=True)
    with pytest.raises(ValidationError):
        service.store.delete_test_session(user_session.session_id, confirmed=True)
    with pytest.raises(ValidationError):
        service.store.delete_test_session(test_session.session_id, confirmed=False)
    service.store.delete_test_session(test_session.session_id, confirmed=True)
    assert service.store.session_file(user_session.session_id).exists()
    assert not service.store.session_dir(test_session.session_id).exists()


def test_list_sessions_skips_malformed(service, tmp_path):
    a = service.create_session("corruptible")
    b = service.create_session("intacta")
    manifest = _session_dir(tmp_path, a.session_id) / "session.json"
    manifest.write_text("corrupt", encoding="utf-8")
    assert [s.session_id for s in service.list_sessions()] == [b.session_id]


# ── crop / audio availability persist ─────────────────────────────

def test_crop_and_audio_availability_persist(service):
    session = service.create_session("crop")
    service.set_crop(session.session_id, CropRegion(0.0, 0.0, 0.5, 0.5))
    service.set_audio_availability(session.session_id, AudioAvailability.MISSING)

    reloaded = service.get_session(session.session_id)
    assert reloaded.crop == CropRegion(0.0, 0.0, 0.5, 0.5)
    assert reloaded.audio_availability is AudioAvailability.MISSING
