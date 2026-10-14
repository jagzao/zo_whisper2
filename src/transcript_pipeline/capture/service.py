from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from transcript_pipeline.capture.models import CaptureConfig, CaptureSession, SessionStatus
from transcript_pipeline.capture.store import CaptureStore

TRANSITIONS = {
    SessionStatus.CREATED: {SessionStatus.RECORDING, SessionStatus.FAILED},
    SessionStatus.RECORDING: {SessionStatus.PAUSED, SessionStatus.STOPPED, SessionStatus.RECOVERABLE, SessionStatus.FAILED},
    SessionStatus.PAUSED: {SessionStatus.RECORDING, SessionStatus.STOPPED, SessionStatus.RECOVERABLE, SessionStatus.FAILED},
    SessionStatus.STOPPED: {SessionStatus.PROCESSING, SessionStatus.WAITING_FOR_EXTERNAL_TRANSCRIPT, SessionStatus.FAILED},
    SessionStatus.PROCESSING: {SessionStatus.WAITING_FOR_EXTERNAL_TRANSCRIPT, SessionStatus.DOCUMENTING, SessionStatus.FAILED},
    SessionStatus.WAITING_FOR_EXTERNAL_TRANSCRIPT: {SessionStatus.PROCESSING, SessionStatus.DOCUMENTING, SessionStatus.FAILED},
    SessionStatus.DOCUMENTING: {SessionStatus.COMPLETE, SessionStatus.FAILED},
    SessionStatus.RECOVERABLE: {SessionStatus.RECORDING, SessionStatus.PROCESSING, SessionStatus.FAILED},
    SessionStatus.COMPLETE: set(),
    SessionStatus.FAILED: set(),
}


class CaptureService:
    def __init__(self, store: CaptureStore):
        self.store = store

    def create_session(
        self, title: str, project_name: str | None = None, capture_config: CaptureConfig | None = None
    ) -> CaptureSession:
        if any(session.status in {SessionStatus.CREATED, SessionStatus.RECORDING, SessionStatus.PAUSED} for session in self.store.list_sessions()):
            raise RuntimeError("an active capture session already exists")
        now = datetime.now(timezone.utc).isoformat()
        session = CaptureSession(
            sessionId=str(uuid4()), title=title, projectName=project_name,
            captureConfig=capture_config or CaptureConfig(), createdAt=now, updatedAt=now,
        )
        return self.store.create(session)

    def transition(self, session_id: str, status: SessionStatus) -> CaptureSession:
        session = self.store.get_session(session_id)
        if status not in TRANSITIONS[session.status]:
            raise ValueError(f"invalid session transition: {session.status} -> {status}")
        now = datetime.now(timezone.utc).isoformat()
        session.status = status
        session.updatedAt = now
        if status is SessionStatus.RECORDING and session.startedAt is None:
            session.startedAt = now
        if status is SessionStatus.STOPPED:
            session.stoppedAt = now
        if status is SessionStatus.COMPLETE:
            session.completedAt = now
        self.store.save_session(session)
        return session
