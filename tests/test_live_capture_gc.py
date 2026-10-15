from __future__ import annotations

from datetime import datetime, timezone

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.gc import deletion_candidates
from transcript_pipeline.live_capture.service import CaptureService


def _completed_chunk(tmp_path):
    service = CaptureService(tmp_path / "Videos")
    session = service.create_session("retention", audio_availability=models.AudioAvailability.MISSING)
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"synthetic-media")
    service.mark_processing(session.session_id, 0)
    service.mark_processed(session.session_id, 0, transcript_available=True)
    service.finalize_session(session.session_id)
    path = service.store.chunk_media_path(session.session_id, 0, ".webm")
    return session, path


def test_gc_suggests_old_processed_documented_media_only(tmp_path):
    session, path = _completed_chunk(tmp_path)
    now = datetime(2028, 1, 1, tzinfo=timezone.utc)
    candidates = deletion_candidates(
        tmp_path / "Videos",
        now=now,
        retention_days=90,
        documentation_exists=lambda media: media == path,
    )
    assert len(candidates) == 1
    assert candidates[0]["session_id"] == session.session_id
    assert candidates[0]["requires_confirmation"] is True
    assert path.exists()


def test_gc_excludes_media_without_documentation(tmp_path):
    _, path = _completed_chunk(tmp_path)
    candidates = deletion_candidates(
        tmp_path / "Videos",
        now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        documentation_exists=lambda media: False,
    )
    assert candidates == []
    assert path.exists()
