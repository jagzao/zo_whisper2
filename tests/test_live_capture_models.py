"""Unit tests: Live Capture domain model and validated state transitions."""

from __future__ import annotations

import pytest

from transcript_pipeline.live_capture.errors import InvalidTransitionError, ValidationError
from transcript_pipeline.live_capture.models import (
    AudioAvailability,
    Chunk,
    ChunkState,
    CropRegion,
    Session,
    SessionStatus,
    chunk_id,
)


def _chunk(index: int = 0, state: ChunkState = ChunkState.RECORDING, **overrides):
    defaults: dict = dict(index=index, state=state, created_at="2026-10-15T10:00:00+00:00")
    defaults.update(overrides)
    return Chunk(**defaults)


def _session(**overrides):
    defaults: dict = dict(
        session_id="sess-abc123",
        title="Sesion",
        status=SessionStatus.ACTIVE,
        created_at="2026-10-15T10:00:00+00:00",
        chunk_duration_sec=600,
    )
    defaults.update(overrides)
    return Session(**defaults)


# ── chunk transitions ─────────────────────────────────────────────

def test_chunk_lifecycle_transitions_are_valid():
    chunk = _chunk()
    chunk = chunk.transition_to(ChunkState.FINALIZED)
    chunk = chunk.transition_to(ChunkState.PROCESSING)
    chunk = chunk.transition_to(ChunkState.PROCESSED)
    assert chunk.state is ChunkState.PROCESSED


def test_chunk_processing_can_fail_and_retry():
    chunk = _chunk().transition_to(ChunkState.FINALIZED).transition_to(ChunkState.PROCESSING)
    failed = chunk.transition_to(ChunkState.FAILED)
    assert failed.transition_to(ChunkState.PROCESSING).state is ChunkState.PROCESSING


def test_cancelled_upload_can_retry_but_is_not_playable():
    cancelled = _chunk().transition_to(ChunkState.UPLOAD_CANCELLED)
    assert cancelled.state is ChunkState.UPLOAD_CANCELLED
    assert cancelled.transition_to(ChunkState.RECORDING).state is ChunkState.RECORDING
    assert cancelled.playable is False


def test_chunk_invalid_transition_is_rejected():
    with pytest.raises(InvalidTransitionError):
        _chunk().transition_to(ChunkState.PROCESSING)  # RECORDING -> PROCESSING is invalid


def test_processed_chunk_is_terminal():
    processed = _chunk(state=ChunkState.PROCESSED, media_size_bytes=100)
    with pytest.raises(InvalidTransitionError):
        processed.transition_to(ChunkState.FAILED)


# ── session transitions ───────────────────────────────────────────

def test_session_lifecycle_transitions_are_valid():
    finalized = _session().transition_to(SessionStatus.FINALIZED)
    assert finalized.status is SessionStatus.FINALIZED
    with pytest.raises(InvalidTransitionError):
        finalized.transition_to(SessionStatus.ACTIVE)


def test_active_session_can_fail():
    assert _session().transition_to(SessionStatus.FAILED).status is SessionStatus.FAILED


# ── identity / order ──────────────────────────────────────────────

def test_chunk_id_is_zero_padded():
    assert chunk_id(0) == "chunk-000000"
    assert chunk_id(123) == "chunk-000123"


def test_session_chunks_are_unique_and_ordered():
    session = _session().with_chunk(_chunk(index=0))
    assert session.next_chunk_index == 1
    session = session.with_chunk(_chunk(index=1))
    assert [c.index for c in session.chunks] == [0, 1]
    session = session.with_chunk(_chunk(index=0, state=ChunkState.FINALIZED, media_size_bytes=10))
    assert [c.index for c in session.chunks] == [0, 1]
    assert session.chunks[0].state is ChunkState.FINALIZED


def test_invalid_session_id_is_rejected():
    with pytest.raises(ValidationError):
        _session(session_id="../evil")
    with pytest.raises(ValidationError):
        _session(session_id="")


# ── crop placeholder ──────────────────────────────────────────────

def test_crop_valid_region_roundtrips():
    crop = CropRegion(0.1, 0.2, 0.5, 0.4)
    assert CropRegion.from_manifest(crop.to_manifest()) == crop


def test_crop_out_of_bounds_is_rejected():
    with pytest.raises(ValidationError):
        CropRegion(0.0, 0.0, 1.1, 1.0)
    with pytest.raises(ValidationError):
        CropRegion(0.5, 0.5, 0.6, 0.5)  # x + width > 1


def test_crop_none_is_valid_placeholder():
    assert CropRegion.from_manifest(None) is None


# ── serialization roundtrip ───────────────────────────────────────

def test_session_manifest_roundtrip_preserves_metadata():
    session = _session(
        recorded_at="2026-10-15T09:59:00+00:00",
        audio_availability=AudioAvailability.AVAILABLE,
        crop=CropRegion(0.0, 0.0, 1.0, 1.0),
        chunks=(
            _chunk(
                index=0,
                state=ChunkState.FINALIZED,
                finalized_at="2026-10-15T10:10:00+00:00",
                media_size_bytes=42,
                media_extension=".webm",
                media_sha256="a" * 64,
            ),
            _chunk(index=1, state=ChunkState.RECORDING),
        ),
    )
    assert Session.from_manifest(session.to_manifest()) == session


def test_manifest_rejects_unknown_schema():
    with pytest.raises(ValidationError):
        Session.from_manifest({"schemaVersion": 999, "sessionId": "s", "title": "t"})


def test_playable_requires_finalized_and_sized():
    assert _chunk(state=ChunkState.RECORDING).playable is False
    assert _chunk(state=ChunkState.FINALIZED).playable is False  # no size -> incomplete
    assert _chunk(state=ChunkState.FINALIZED, media_size_bytes=10).playable is True
    assert _chunk(state=ChunkState.FAILED, media_size_bytes=10).playable is False
