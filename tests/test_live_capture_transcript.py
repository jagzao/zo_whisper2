"""Unit tests: W8 late transcript association.

Covers the `Transcript` value object (always loosely-aligned, no fabricated
second-level sync), its durable round-trip through the session manifest, and
`CaptureService.associate_transcript` — associating a transcript after
finalized media clears TRANSCRIPT_REQUIRED and marks availability without
forcing a chunk's processing `state` to PROCESSED, persists durably, writes a
plain-text sidecar, and is idempotent on retry.
"""

from __future__ import annotations

import pytest

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.errors import SessionNotFoundError, ValidationError
from transcript_pipeline.live_capture.service import CaptureService

A = models.AudioAvailability


# ── Transcript value object ─────────────────────────────────────────

def test_transcript_roundtrips_manifest():
    transcript = models.Transcript("hola mundo", "2026-10-15T10:00:00+00:00", language="es")
    assert models.Transcript.from_manifest(transcript.to_manifest()) == transcript


def test_transcript_alignment_is_always_loose():
    transcript = models.Transcript("hola", "2026-10-15T10:00:00+00:00")
    manifest = transcript.to_manifest()
    assert manifest["alignment"] == models.TRANSCRIPT_ALIGNMENT_LOOSE
    assert models.TRANSCRIPT_ALIGNMENT_LOOSE == "loose"


def test_transcript_manifest_has_no_fabricated_timing():
    # No per-segment start/end/timestamp/segments keys may ever exist — the
    # transcript is one opaque text block with only its arrival time.
    manifest = models.Transcript("hola", "2026-10-15T10:00:00+00:00").to_manifest()
    for forbidden in ("start", "end", "timestamp", "timestamps", "segments", "segment"):
        assert forbidden not in manifest


@pytest.mark.parametrize("bad", ["", "   ", 123, None, ["text"]])
def test_transcript_rejects_nonempty_text(bad):
    with pytest.raises(ValidationError):
        models.Transcript(bad, "2026-10-15T10:00:00+00:00")


@pytest.mark.parametrize("bad", ["", "   ", None, 123])
def test_transcript_rejects_invalid_supplied_at(bad):
    with pytest.raises(ValidationError):
        models.Transcript("hola", bad)


def test_transcript_language_is_optional_but_nonempty():
    assert models.Transcript("hola", "2026-10-15T10:00:00+00:00").language is None
    assert models.Transcript("hola", "2026-10-15T10:00:00+00:00", language="es").language == "es"
    with pytest.raises(ValidationError):
        models.Transcript("hola", "2026-10-15T10:00:00+00:00", language="   ")


# ── session-level durability ────────────────────────────────────────

def _chunk(index: int = 0, **overrides):
    defaults = dict(index=index, state=models.ChunkState.FINALIZED, created_at="2026-10-15T10:00:00+00:00")
    defaults.update(overrides)
    return models.Chunk(**defaults)


def _session(**overrides):
    defaults = dict(
        session_id="sess-abc123",
        title="Sesion",
        status=models.SessionStatus.FINALIZED,
        created_at="2026-10-15T10:00:00+00:00",
        chunk_duration_sec=600,
    )
    defaults.update(overrides)
    return models.Session(**defaults)


def test_session_with_transcript_roundtrips_manifest():
    transcript = models.Transcript("texto", "2026-10-15T11:00:00+00:00")
    session = _session(transcript=transcript, chunks=(_chunk(0, transcript_available=True),))
    manifest = session.to_manifest()
    assert manifest["transcriptAvailable"] is True
    assert manifest["transcript"]["text"] == "texto"
    assert models.Session.from_manifest(manifest) == session


def test_session_transcript_available_is_derived():
    assert _session().transcript_available is False
    assert _session(transcript=models.Transcript("x", "2026-10-15T11:00:00+00:00")).transcript_available is True
    assert _session(chunks=(_chunk(0, transcript_available=True),)).transcript_available is True


def test_session_without_transcript_key_loads_none():
    raw = _session().to_manifest()
    raw.pop("transcript", None)
    assert models.Session.from_manifest(raw).transcript is None


# ── service association ─────────────────────────────────────────────

@pytest.fixture()
def service(tmp_path):
    return CaptureService(videos_root=tmp_path / "Videos")


def _finalized_missing_audio(service, title="video-only"):
    session = service.create_session(title, audio_availability=A.MISSING)
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"bytes", audio_availability=A.MISSING)
    return session.session_id


def test_associate_transcript_after_finalized_media(service):
    session_id = _finalized_missing_audio(service)
    assert service.get_session(session_id).transcript_required is True

    updated = service.associate_transcript(session_id, "transcripcion tardia", language="es")

    assert updated.transcript is not None
    assert updated.transcript.text == "transcripcion tardia"
    assert updated.transcript.language == "es"
    chunk = updated.get_chunk(0)
    assert chunk.transcript_available is True
    assert chunk.transcript_required is False
    assert updated.transcript_required is False
    assert updated.transcript_available is True


def test_associate_transcript_does_not_force_processed_state(service):
    session_id = _finalized_missing_audio(service)
    service.mark_processing(session_id, 0)  # PROCESSING, awaiting transcription

    updated = service.associate_transcript(session_id, "tarde")

    # The transcript arrived, but the chunk's processing state is untouched —
    # a late transcript must never masquerade as completed media processing.
    assert updated.get_chunk(0).state is models.ChunkState.PROCESSING
    assert updated.get_chunk(0).transcript_available is True
    assert updated.get_chunk(0).transcript_required is False


def test_associate_transcript_keeps_finalized_state(service):
    session_id = _finalized_missing_audio(service)
    updated = service.associate_transcript(session_id, "tarde")
    assert updated.get_chunk(0).state is models.ChunkState.FINALIZED


def test_associate_transcript_persists_and_reloads(service):
    session_id = _finalized_missing_audio(service)
    service.associate_transcript(session_id, "persistido", language="es")

    reloaded = service.get_session(session_id)
    assert reloaded.transcript.text == "persistido"
    assert reloaded.transcript.language == "es"
    assert reloaded.transcript.alignment == "loose"
    assert reloaded.chunks[0].transcript_available is True
    assert reloaded.chunks[0].transcript_required is False
    assert reloaded.transcript_required is False


def test_associate_transcript_writes_sidecar(service, tmp_path):
    session_id = _finalized_missing_audio(service)
    service.associate_transcript(session_id, "texto plano")

    sidecar = tmp_path / "Videos" / "live_capture" / session_id / "transcript.txt"
    assert sidecar.read_text(encoding="utf-8") == "texto plano"


def test_associate_transcript_is_idempotent(service):
    session_id = _finalized_missing_audio(service)
    first = service.associate_transcript(session_id, "primera")
    second = service.associate_transcript(session_id, "primera")

    assert second.transcript.text == "primera"
    assert second.transcript is not None
    assert second.get_chunk(0).transcript_available is True
    assert first.transcript.supplied_at != second.transcript.supplied_at  # arrival time advances, content does not duplicate


def test_associate_transcript_marks_all_chunks_available(service):
    session = service.create_session("multi", audio_availability=A.MISSING)
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"c0", audio_availability=A.MISSING)
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 1, b"c1", audio_availability=A.MISSING)

    updated = service.associate_transcript(session.session_id, "todas")

    assert all(c.transcript_available for c in updated.chunks)
    assert all(not c.transcript_required for c in updated.chunks)


def test_associate_transcript_rejects_empty_text(service):
    session_id = _finalized_missing_audio(service)
    with pytest.raises(ValidationError):
        service.associate_transcript(session_id, "   ")
    # Nothing changed: the session still requires a transcript.
    assert service.get_session(session_id).transcript is None
    assert service.get_session(session_id).transcript_required is True


def test_associate_transcript_unknown_session_raises(service):
    with pytest.raises(SessionNotFoundError):
        service.associate_transcript("sess-doesnotexist", "hola")


def test_associate_transcript_supplied_at_defaults_to_now(service):
    session_id = _finalized_missing_audio(service)
    updated = service.associate_transcript(session_id, "ahora")
    assert updated.transcript.supplied_at
