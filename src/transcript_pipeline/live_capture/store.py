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
import shutil
from pathlib import Path

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.atomic import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_stream,
    commit_staged,
    read_json,
    stage_stream,
)
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
FRAGMENTS_DIR = "fragments"
FRAGMENT_MANIFEST_FILE = "fragments.json"
PROCESSING_MAP_FILE = "processing_chunks.json"
TRANSCRIPT_FILE = "transcript.txt"

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

    def fragments_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / FRAGMENTS_DIR

    def fragment_manifest_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / FRAGMENT_MANIFEST_FILE

    def fragment_media_path(self, session_id: str, fragment_id: str, extension: str) -> Path:
        return self.fragments_dir(session_id) / f"{models.validate_fragment_id(fragment_id)}{normalize_extension(extension)}"

    def transcript_path(self, session_id: str) -> Path:
        """Plain-text sidecar for a late-supplied transcript (W8).

        Mirrors the existing `.txt` transcription convention so the future
        Docs V2 integration (W9) can consume a session transcript through the
        same file-based flow — no duplicate processor is built here.
        """
        return self.session_dir(session_id) / TRANSCRIPT_FILE

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

    def delete_test_session(self, session_id: str, *, confirmed: bool) -> None:
        if not confirmed:
            raise ValidationError("explicit confirmation is required")
        session = self.load_session(session_id)
        if not session.is_test_session:
            raise ValidationError("only explicitly marked test sessions can be cleaned up")
        base = self.base_dir().resolve(strict=False)
        target = self.session_dir(session_id).resolve(strict=False)
        if target == base or base not in target.parents:
            raise ValidationError("test session path is outside the capture store")
        shutil.rmtree(target)

    # ── chunk media persistence ─────────────────────────────────────

    def write_chunk_media(self, session_id: str, index: int, extension: str, data: bytes) -> tuple[str, int]:
        """Atomically writes finalized chunk media; returns (sha256, size)."""
        path = self.chunk_media_path(session_id, index, extension)
        atomic_write_bytes(path, data)
        return hashlib.sha256(data).hexdigest(), len(data)

    def write_chunk_media_stream(self, session_id: str, index: int, extension: str, source) -> tuple[str, int]:
        """Atomically streams finalized chunk media from `source` (an iterable
        of bytes blocks) and returns (sha256, size) without whole-body
        buffering."""
        path = self.chunk_media_path(session_id, index, extension)
        return atomic_write_stream(path, source)

    def chunk_media_exists(self, session_id: str, index: int, extension: str) -> bool:
        return self.chunk_media_path(session_id, index, extension).is_file()

    def write_transcript(self, session_id: str, text: str) -> None:
        """Atomically writes the supplied transcript sidecar text file."""
        session_id = models.validate_session_id(session_id)
        path = self.transcript_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, text.encode("utf-8"))

    # ── upload fragment persistence (W5) ────────────────────────────

    def load_fragments(self, session_id: str) -> list[models.Fragment]:
        """Fragment manifest for a session, ordered by sequence then ID.

        A missing manifest is an empty list (no fragments uploaded yet); a
        present-but-malformed manifest is never trusted and is reported, so a
        corrupt file cannot be silently rewritten into a partial history.
        """
        session_id = models.validate_session_id(session_id)
        path = self.fragment_manifest_file(session_id)
        if not path.exists():
            return []
        raw = read_json(path)
        if not isinstance(raw, dict):
            raise ManifestCorruptError(f"fragment manifest {path} is not valid JSON")
        if raw.get("schemaVersion") != models.FRAGMENT_MANIFEST_SCHEMA_VERSION:
            raise ManifestCorruptError(
                f"unsupported fragment manifest schemaVersion {raw.get('schemaVersion')!r}"
            )
        fragments_raw = raw.get("fragments", [])
        if not isinstance(fragments_raw, list):
            raise ManifestCorruptError(f"fragment manifest {path} has no fragment list")
        try:
            fragments = [models.Fragment.from_manifest(item) for item in fragments_raw]
        except ValidationError as exc:
            raise ManifestCorruptError(f"fragment manifest {path} is malformed: {exc}") from exc
        fragments.sort(key=lambda f: (f.sequence, f.fragment_id))
        return fragments

    def save_fragments(self, session_id: str, fragments: list[models.Fragment]) -> None:
        session_id = models.validate_session_id(session_id)
        ordered = sorted(fragments, key=lambda f: (f.sequence, f.fragment_id))
        payload = {
            "schemaVersion": models.FRAGMENT_MANIFEST_SCHEMA_VERSION,
            "sessionId": session_id,
            "fragments": [f.to_manifest() for f in ordered],
        }
        self.fragments_dir(session_id).mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.fragment_manifest_file(session_id), payload)

    def stage_fragment_stream(self, session_id: str, fragment_id: str, source) -> tuple[Path, str, int]:
        """Streams a fragment body into a temp file under the session's
        fragments dir; returns `(temp_path, sha256, size)` without committing.
        """
        parent = self.fragments_dir(session_id)
        prefix = f".{models.validate_fragment_id(fragment_id)}."
        return stage_stream(parent, prefix, source)

    def commit_staged_fragment(
        self, tmp_path: Path, session_id: str, fragment_id: str, extension: str
    ) -> None:
        commit_staged(Path(tmp_path), self.fragment_media_path(session_id, fragment_id, extension))

    def fragment_media_exists(self, session_id: str, fragment_id: str, extension: str) -> bool:
        return self.fragment_media_path(session_id, fragment_id, extension).is_file()

    # ── processing-chunk mapping persistence (W6) ───────────────────

    def processing_map_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / PROCESSING_MAP_FILE

    def assembly_staging_path(self, session_id: str, chunk_index: int, extension: str) -> Path:
        """Hidden staging path for a processing chunk's assembled media.

        Lives beside the session manifest (never under `chunks/`), uses the
        real extension so the assembler can pick the container, and is
        removed after the chunk is finalized. A crash leaves only a dot-file
        that never resolves as playable media.
        """
        ext = normalize_extension(extension)
        return self.session_dir(session_id) / f".{models.chunk_id(chunk_index)}.assembling{ext}"

    def load_processing_map(self, session_id: str) -> list[models.ProcessingChunkMapping]:
        """Durable fragment->processing-chunk map, ordered by chunk index.

        Missing file means no processing chunk has been planned yet. A
        present-but-malformed file is reported, never silently rewritten into
        a partial history.
        """
        session_id = models.validate_session_id(session_id)
        path = self.processing_map_file(session_id)
        if not path.exists():
            return []
        raw = read_json(path)
        if not isinstance(raw, dict):
            raise ManifestCorruptError(f"processing map {path} is not valid JSON")
        if raw.get("schemaVersion") != models.PROCESSING_MAP_SCHEMA_VERSION:
            raise ManifestCorruptError(
                f"unsupported processing map schemaVersion {raw.get('schemaVersion')!r}"
            )
        entries_raw = raw.get("processingChunks", [])
        if not isinstance(entries_raw, list):
            raise ManifestCorruptError(f"processing map {path} has no processing chunk list")
        try:
            entries = [models.ProcessingChunkMapping.from_manifest(item) for item in entries_raw]
        except ValidationError as exc:
            raise ManifestCorruptError(f"processing map {path} is malformed: {exc}") from exc
        entries.sort(key=lambda e: e.chunk_index)
        return entries

    def save_processing_map(
        self, session_id: str, entries: list[models.ProcessingChunkMapping]
    ) -> None:
        payload = {
            "schemaVersion": models.PROCESSING_MAP_SCHEMA_VERSION,
            "sessionId": models.validate_session_id(session_id),
            "processingChunks": [e.to_manifest() for e in sorted(entries, key=lambda e: e.chunk_index)],
        }
        self.session_dir(session_id).mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.processing_map_file(session_id), payload)
