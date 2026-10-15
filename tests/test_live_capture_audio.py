"""Unit tests: W7 audio-state logic, transcript-required durability, and the
missing-audio capture flow.

Covers the pure `live_capture.audio` mapping, the `transcript_required`
durability on the domain model, and `CaptureService` behavior — finalize
derives transcript-required from audio availability, `mark_processed` clears
it, and `detect_chunk_audio` probes finalized media via an injected fake so
no ffprobe binary or real media is required.
"""

from __future__ import annotations

import pytest

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.audio import (
    audio_availability_from_track_count,
    resolve_audio_availability,
    transcript_required,
)
from transcript_pipeline.live_capture.errors import InvalidTransitionError, ValidationError
from transcript_pipeline.live_capture.service import CaptureService

A = models.AudioAvailability


# ── pure audio-state logic ─────────────────────────────────────────

@pytest.mark.parametrize(
    "count,expected",
    [
        (None, A.UNKNOWN),
        (0, A.MISSING),
        (1, A.AVAILABLE),
        (2, A.AVAILABLE),
    ],
)
def test_audio_availability_from_track_count(count, expected):
    assert audio_availability_from_track_count(count) is expected


@pytest.mark.parametrize("bad", [-1, True, False, 1.5, "1"])
def test_audio_availability_from_track_count_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        audio_availability_from_track_count(bad)


@pytest.mark.parametrize(
    "track_present,stream_present,expected",
    [
        # A confirmed absence dominates regardless of the other source.
        (False, None, A.MISSING),
        (False, False, A.MISSING),
        (False, True, A.MISSING),
        (None, False, A.MISSING),
        (True, False, A.MISSING),
        # A confirmed presence wins over unknown.
        (True, None, A.AVAILABLE),
        (None, True, A.AVAILABLE),
        (True, True, A.AVAILABLE),
        # Both unknown stays unknown.
        (None, None, A.UNKNOWN),
    ],
)
def test_resolve_audio_availability(track_present, stream_present, expected):
    assert resolve_audio_availability(track_present, stream_present) is expected


@pytest.mark.parametrize(
    "availability,transcript_available,expected",
    [
        (A.MISSING, False, True),
        (A.MISSING, True, False),
        (A.AVAILABLE, False, False),
        (A.UNKNOWN, False, False),
    ],
)
def test_transcript_required_derivation(availability, transcript_available, expected):
    assert transcript_required(availability, transcript_available) is expected


# ── domain model durability ─────────────────────────────────────────

def _chunk(index: int = 0, **overrides):
    defaults = dict(index=index, state=models.ChunkState.FINALIZED, created_at="2026-10-15T10:00:00+00:00")
    defaults.update(overrides)
    return models.Chunk(**defaults)


def test_chunk_transcript_required_roundtrips_manifest():
    chunk = _chunk(
        audio_availability=A.MISSING,
        transcript_required=True,
        media_size_bytes=10,
        media_extension=".webm",
    )
    reloaded = models.Chunk.from_manifest(chunk.to_manifest())
    assert reloaded.transcript_required is True
    assert reloaded.audio_availability is A.MISSING


def test_chunk_transcript_required_defaults_false_when_absent():
    raw = _chunk(media_size_bytes=10).to_manifest()
    raw.pop("transcriptRequired")
    assert models.Chunk.from_manifest(raw).transcript_required is False


def test_session_transcript_required_is_derived_from_chunks():
    session = models.Session(
        session_id="sess-abc123",
        title="Sesion",
        status=models.SessionStatus.FINALIZED,
        created_at="2026-10-15T10:00:00+00:00",
        chunk_duration_sec=600,
        chunks=(
            _chunk(0, audio_availability=A.AVAILABLE, transcript_required=False),
            _chunk(1, audio_availability=A.MISSING, transcript_required=True),
        ),
    )
    assert session.transcript_required is True
    assert session.to_manifest()["transcriptRequired"] is True
    assert models.Session.from_manifest(session.to_manifest()) == session


def test_session_transcript_required_false_when_no_chunk_requires():
    session = models.Session(
        session_id="sess-abc123",
        title="Sesion",
        status=models.SessionStatus.FINALIZED,
        created_at="2026-10-15T10:00:00+00:00",
        chunk_duration_sec=600,
        chunks=(_chunk(0, audio_availability=A.AVAILABLE, transcript_required=False),),
    )
    assert session.transcript_required is False


# ── service missing-audio flow ─────────────────────────────────────

@pytest.fixture()
def service(tmp_path):
    return CaptureService(videos_root=tmp_path / "Videos")


def test_finalize_chunk_with_missing_audio_marks_transcript_required(service):
    session = service.create_session("video-only", audio_availability=A.MISSING)
    service.start_chunk(session.session_id)
    finalized = service.finalize_chunk(session.session_id, 0, b"bytes", audio_availability=A.MISSING)
    assert finalized.audio_availability is A.MISSING
    assert finalized.transcript_required is True

    reloaded = service.get_session(session.session_id).chunks[0]
    assert reloaded.transcript_required is True
    assert service.get_session(session.session_id).transcript_required is True


def test_finalize_chunk_with_audio_is_not_transcript_required(service):
    session = service.create_session("with-audio", audio_availability=A.AVAILABLE)
    service.start_chunk(session.session_id)
    finalized = service.finalize_chunk(session.session_id, 0, b"bytes", audio_availability=A.AVAILABLE)
    assert finalized.transcript_required is False


def test_mark_processed_without_transcript_keeps_transcript_required(service):
    session = service.create_session("late-transcript")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"bytes", audio_availability=A.MISSING)
    assert service.get_session(session.session_id).chunks[0].transcript_required is True

    service.mark_processing(session.session_id, 0)
    processed = service.mark_processed(session.session_id, 0, transcript_available=False)
    assert processed.transcript_available is False
    assert processed.transcript_required is True
    assert service.get_session(session.session_id).transcript_required is True


def test_mark_processed_with_late_transcript_clears_requirement(service):
    session = service.create_session("late-transcript-present")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"bytes", audio_availability=A.MISSING)
    service.mark_processing(session.session_id, 0)
    processed = service.mark_processed(session.session_id, 0, transcript_available=True)
    assert processed.transcript_available is True
    assert processed.transcript_required is False


# ── server-side ffprobe probe (injected fake) ───────────────────────

def _finalized(service):
    session = service.create_session("probe")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"bytes")
    return session.session_id


def test_detect_chunk_audio_marks_available(service):
    service._audio_probe = lambda path: True
    session_id = _finalized(service)
    chunk = service.detect_chunk_audio(session_id, 0)
    assert chunk.audio_availability is A.AVAILABLE
    assert chunk.transcript_required is False


def test_detect_chunk_audio_marks_missing_and_required(service):
    service._audio_probe = lambda path: False
    session_id = _finalized(service)
    chunk = service.detect_chunk_audio(session_id, 0)
    assert chunk.audio_availability is A.MISSING
    assert chunk.transcript_required is True
    assert service.get_session(session_id).transcript_required is True


def test_detect_chunk_audio_probe_failure_is_unknown_not_fatal(service):
    def _boom(path):
        raise OSError("ffprobe missing")

    service._audio_probe = _boom
    session_id = _finalized(service)
    chunk = service.detect_chunk_audio(session_id, 0)
    assert chunk.audio_availability is A.UNKNOWN
    assert chunk.transcript_required is False


def test_detect_chunk_audio_unknown_probe_stays_unknown(service):
    service._audio_probe = lambda path: None
    session_id = _finalized(service)
    chunk = service.detect_chunk_audio(session_id, 0)
    assert chunk.audio_availability is A.UNKNOWN


def test_detect_chunk_audio_rejects_recording_chunk(service):
    session = service.create_session("recording")
    service.start_chunk(session.session_id)
    with pytest.raises(InvalidTransitionError):
        service.detect_chunk_audio(session.session_id, 0)
