from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from transcript_pipeline.capture.models import CaptureSegment, CaptureSession
from transcript_pipeline.config import CAPTURE_ROOT


class CaptureStore:
    def __init__(self, root: Path = CAPTURE_ROOT):
        self.root = root.resolve()
        self.sessions_root = self.root / "sessions"

    def session_root(self, session_id: str) -> Path:
        canonical = str(UUID(session_id))
        path = (self.sessions_root / canonical).resolve()
        if path.parent != self.sessions_root.resolve():
            raise ValueError("invalid capture session id")
        return path

    def create(self, session: CaptureSession) -> CaptureSession:
        root = self.session_root(session.sessionId)
        root.mkdir(parents=True, exist_ok=False)
        for child in ("segments", "transcripts", "aggregate"):
            (root / child).mkdir()
        self.save_session(session)
        return session

    def save_session(self, session: CaptureSession) -> None:
        self._atomic_json(self.session_root(session.sessionId) / "session.json", session.to_dict())

    def get_session(self, session_id: str) -> CaptureSession:
        path = self.session_root(session_id) / "session.json"
        return CaptureSession.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_sessions(self) -> list[CaptureSession]:
        if not self.sessions_root.exists():
            return []
        result = []
        for path in sorted(self.sessions_root.glob("*/session.json")):
            try:
                result.append(CaptureSession.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError, KeyError):
                continue
        return result

    def save_segment(self, segment: CaptureSegment) -> None:
        path = self.session_root(segment.sessionId) / "segments" / f"{segment.sequence:06d}"
        path.mkdir(parents=True, exist_ok=True)
        self._atomic_json(path / "segment.json", segment.to_dict())

    def get_segment(self, session_id: str, sequence: int) -> CaptureSegment:
        if sequence < 1:
            raise ValueError("invalid segment sequence")
        path = self.session_root(session_id) / "segments" / f"{sequence:06d}" / "segment.json"
        return CaptureSegment.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_segments(self, session_id: str) -> list[CaptureSegment]:
        root = self.session_root(session_id) / "segments"
        if not root.exists():
            return []
        return [self.get_segment(session_id, int(path.parent.name)) for path in sorted(root.glob("*/segment.json"))]

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
