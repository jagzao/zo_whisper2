"""Unit tests: W9 bridge from finalized Live Capture chunks to the media
pipeline (`resolve_capture_context` + the processor's no-audio decision).

Synthetic fixtures only — no ffmpeg, no real media, no Whisper. Sessions are
built on disk through the real CaptureService/ManifestStore so the manifest
layout under test is exactly what production writes.
"""

from __future__ import annotations

import types
from pathlib import Path

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.pipeline import (
    CaptureContext,
    parse_chunk_index,
    resolve_capture_context,
)
from transcript_pipeline.live_capture.service import CaptureService
from transcript_pipeline.live_capture.store import ManifestStore
from transcript_pipeline.transcription import processor as processor_module

A = models.AudioAvailability


def _service(tmp_path) -> CaptureService:
    return CaptureService(videos_root=tmp_path / "Videos")


def _finalized_session(service: CaptureService, *, audio_availability: A, crop=None) -> models.Session:
    session = service.create_session("W9 unit", crop=crop, audio_availability=audio_availability)
    service.start_chunk(session.session_id, audio_availability=audio_availability)
    service.finalize_chunk(
        session.session_id, 0, b"\x00\x00", audio_availability=audio_availability
    )
    return session


# ── resolve_capture_context: rejection paths ───────────────────────


def test_resolve_returns_none_for_normal_video_path(tmp_path):
    assert resolve_capture_context(tmp_path / "Videos" / "normal.mp4") is None


def test_resolve_returns_none_for_live_capture_path_that_is_not_a_chunk(tmp_path):
    path = tmp_path / "Videos" / "live_capture" / "sess-xyz" / "clip.webm"
    assert resolve_capture_context(path) is None


def test_resolve_returns_none_when_manifest_missing(tmp_path):
    chunks_dir = tmp_path / "Videos" / "live_capture" / "sess-xyz" / "chunks"
    chunks_dir.mkdir(parents=True)
    chunk = chunks_dir / "chunk-000000.webm"
    chunk.write_bytes(b"\x00\x00")
    assert resolve_capture_context(chunk) is None


def test_resolve_returns_none_when_manifest_malformed(tmp_path):
    session_dir = tmp_path / "Videos" / "live_capture" / "sess-xyz"
    (session_dir / "chunks").mkdir(parents=True)
    chunk = session_dir / "chunks" / "chunk-000000.webm"
    chunk.write_bytes(b"\x00\x00")
    (session_dir / "session.json").write_text("not json", encoding="utf-8")
    assert resolve_capture_context(chunk) is None


def test_resolve_returns_none_for_recording_chunk(tmp_path):
    store = ManifestStore(tmp_path / "Videos")
    now = models.now_iso()
    session = models.Session(
        session_id="sess-rec",
        title="Recording session",
        status=models.SessionStatus.ACTIVE,
        created_at=now,
        chunk_duration_sec=600,
        chunks=(models.Chunk(index=0, state=models.ChunkState.RECORDING, created_at=now),),
    )
    store.save_session(session)
    chunk_path = store.chunk_media_path("sess-rec", 0, ".webm")
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_path.write_bytes(b"\x00\x00")
    assert resolve_capture_context(chunk_path) is None


def test_resolve_returns_none_for_failed_chunk(tmp_path):
    service = _service(tmp_path)
    session = _finalized_session(service, audio_availability=A.UNKNOWN)
    service.mark_failed(session.session_id, 0)
    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")
    assert resolve_capture_context(chunk_path) is None


# ── resolve_capture_context: happy paths ───────────────────────────


def test_resolve_returns_context_for_finalized_video_only_session(tmp_path):
    service = _service(tmp_path)
    session = _finalized_session(
        service,
        audio_availability=A.MISSING,
        crop=models.CropRegion(0.0, 0.0, 0.5, 0.5),
    )
    service.associate_transcript(session.session_id, "late text", language="es")

    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")
    ctx = resolve_capture_context(chunk_path)

    assert isinstance(ctx, CaptureContext)
    assert ctx.session_id == session.session_id
    assert ctx.chunk_index == 0
    assert ctx.crop is not None and ctx.crop.width == 0.5
    assert ctx.transcript is not None
    assert ctx.transcript.text == "late text"
    assert ctx.transcript.alignment == "loose"
    assert ctx.audio_availability is A.MISSING
    assert ctx.source == "live_capture_manifest"


def test_resolve_returns_context_for_processing_chunk(tmp_path):
    service = _service(tmp_path)
    session = _finalized_session(service, audio_availability=A.AVAILABLE)
    service.mark_processing(session.session_id, 0)
    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")
    ctx = resolve_capture_context(chunk_path)
    assert ctx is not None
    assert ctx.audio_availability is A.AVAILABLE


# ── parse_chunk_index ──────────────────────────────────────────────


def test_parse_chunk_index_extracts_index():
    assert parse_chunk_index(Path("chunk-000007.webm")) == 7


def test_parse_chunk_index_rejects_other_names():
    assert parse_chunk_index(Path("other.webm")) is None


# ── processor no-audio decision (W9) ───────────────────────────────


def _bare_processor():
    return processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)


def test_has_audio_manifest_missing_short_circuits_false():
    instance = _bare_processor()
    ctx = types.SimpleNamespace(audio_availability=A.MISSING)
    assert instance._has_audio(Path("x.webm"), ctx) is False


def test_has_audio_manifest_available_short_circuits_true():
    instance = _bare_processor()
    ctx = types.SimpleNamespace(audio_availability=A.AVAILABLE)
    assert instance._has_audio(Path("x.webm"), ctx) is True


def test_has_audio_unknown_availability_delegates_to_probe():
    instance = _bare_processor()
    ctx = types.SimpleNamespace(audio_availability=A.UNKNOWN)
    # An unprobable file yields None (unknown), never an exception.
    assert instance._has_audio(Path("definitely-missing-input.webm"), ctx) is None


def test_capture_context_on_bare_instance_never_raises():
    instance = _bare_processor()
    assert instance._capture_context(Path("plain.mp4")) is None
