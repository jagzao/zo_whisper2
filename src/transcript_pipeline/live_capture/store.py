"""Durable manifest + media store for Live Capture.

Layout under the supplied Videos root:

    {videos_root}/live_capture/{sessionId}/
        session.json                    versioned session manifest (atomic)
        chunks/chunk-000000.webm        finalized chunk media (atomic)

Every path is generated from a validated session ID and chunk index — a
caller never supplies a path. Media is written atomically and only
finalized media is ever exposed as playable; a session manifest whose
chunks don't resolve to real media files is reconciled, never trusted.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.atomic import atomic_write_bytes, atomic_write_json, read_json
from transcript_pipeline.live_capture.errors import (
    ManifestCorruptError,
    SessionConflictError,
    SessionNotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

LIVE_CAPTURE_DIR = "live_capture"
SESSION_FILE = "session.json"
CHUNKS_DIR = "chunks"

_ALLOWED_EXTENSIONS = frozenset({".webm", ".mp4", ".mkv", ".mov", ".m4a", ".wav", ".mp3", ".ogg", ".opus", ".flac"})


def normalize_extension(raw: str) -> str:
    ext = (raw or "").strip().lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if "/" in ext or "\\" in ext or "\x00" in ext or ext not in _ALLOWED_EXTENSIONS:
        raise ValidationError(f"unsupported media extension {raw!r}")
    return ext


class ManifestStore:
    """Pure persistence + safe path generation; no state transitions or locks."""

    def __init__(self, videos_root: Path):
        self.root = Path(videos_root).resolve(strict=False)

    def base_dir(self) -> Path:
        return self.root / LIVE_CAPTURE_DIR

    def session_dir(self, session_id: str) -> Path:
        return self.base_dir() / models.validate_session_id(session_id)

    def session_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / SESSION_FILE

    def chunks_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / CHUNKS_DIR

    def chunk_media_path(self, session_id: str, index: int, extension: str) -> Path:
        return self.chunks_dir(session_id) / f"{models.chunk_id(index)}{normalize_extension(extension)}"

    # ── session manifest persistence ────────────────────────────────

    def create_session(self, session: models.Session) -> None:
        session_id = models.validate_session_id(session.session_id)
        if self.session_file(session_id).exists():
            raise SessionConflictError(f"session {session_id} already exists")
        self.save_session(session)

    def save_session(self, session: models.Session) -> None:
        session_id = models.validate_session_id(session.session_id)
        self.session_dir(session_id).mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.session_file(session_id), session.to_manifest())

    def load_session(self, session_id: str) -> models.Session:
        session_id = models.validate_session_id(session_id)
        path = self.session_file(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"session {session_id} not found")
        raw = read_json(path)
        if raw is None:
            raise ManifestCorruptError(f"session manifest {path} is not valid JSON")
        try:
            return models.Session.from_manifest(raw)
        except ValidationError as exc:
            raise ManifestCorruptError(f"session manifest {path} is malformed: {exc}") from exc

    def list_sessions(self) -> list[models.Session]:
        """Valid sessions, newest first; malformed manifests are skipped and
        reported, never deleted."""
        base = self.base_dir()
        if not base.exists():
            return []
        sessions: list[models.Session] = []
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            try:
                sessions.append(self.load_session(child.name))
            except (SessionNotFoundError, ManifestCorruptError, ValidationError) as exc:
                logger.warning("Skipping malformed live-capture session %s: %s", child.name, exc)
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    # ── chunk media persistence ─────────────────────────────────────

    def write_chunk_media(self, session_id: str, index: int, extension: str, data: bytes) -> tuple[str, int]:
        """Atomically writes finalized chunk media; returns (sha256, size)."""
        path = self.chunk_media_path(session_id, index, extension)
        atomic_write_bytes(path, data)
        return hashlib.sha256(data).hexdigest(), len(data)

    def chunk_media_exists(self, session_id: str, index: int, extension: str) -> bool:
        return self.chunk_media_path(session_id, index, extension).is_file()
