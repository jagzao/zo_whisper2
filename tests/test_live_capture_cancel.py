from __future__ import annotations

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.service import CaptureService


def _processing_chunk(tmp_path):
    service = CaptureService(tmp_path / "Videos")
    session = service.create_session("processing-cancel")
    service.start_chunk(session.session_id)
    service.finalize_chunk(session.session_id, 0, b"synthetic")
    return service, session.session_id


def test_active_cancel_request_wins_against_processing_completion(tmp_path):
    service, session_id = _processing_chunk(tmp_path)
    service.mark_processing(session_id, 0)
    requested = service.cancel_processing(session_id, 0)
    assert requested.state is models.ChunkState.CANCEL_REQUESTED
    assert service.cancel_processing(session_id, 0).state is models.ChunkState.CANCEL_REQUESTED

    completed = service.complete_processing(session_id, 0, transcript_available=True)
    assert completed.state is models.ChunkState.CANCELLED
    assert service.get_session(session_id).chunks[0].state is models.ChunkState.CANCELLED


def test_queued_processing_can_cancel_and_retry(tmp_path):
    service, session_id = _processing_chunk(tmp_path)
    cancelled = service.cancel_processing(session_id, 0)
    assert cancelled.state is models.ChunkState.CANCELLED
    retried = service.retry_cancelled_processing(session_id, 0)
    assert retried.state is models.ChunkState.FINALIZED
    assert service.mark_processing(session_id, 0).state is models.ChunkState.PROCESSING


def test_cancel_after_completion_is_idempotent(tmp_path):
    service, session_id = _processing_chunk(tmp_path)
    service.mark_processing(session_id, 0)
    service.complete_processing(session_id, 0, transcript_available=True)
    assert service.cancel_processing(session_id, 0).state is models.ChunkState.PROCESSED
