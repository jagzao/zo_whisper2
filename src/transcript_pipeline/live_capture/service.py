"""Capture service API — the single entry point W4 (browser UI) and W5
(chunking/upload) call.

Wraps the `ManifestStore` with the validated chunk/session state machine.
Recording bytes are accepted only through `finalize_chunk`, which writes
media atomically and flips the chunk RECORDING -> FINALIZED. Incomplete
(never-finalized) chunks are never exposed as playable.
"""

from __future__ import annotations

import io
import threading
from dataclasses import replace
from pathlib import Path

from transcript_pipeline.config import VIDEOS_DIR
from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.errors import ChunkTooLargeError, InvalidTransitionError, ValidationError
from transcript_pipeline.live_capture.store import ManifestStore, normalize_extension

# Bounded read size for streamed uploads: the server never holds more than
# this many bytes of a chunk body in memory at once.
STREAM_BLOCK_SIZE = 64 * 1024


def _stream_blocks(source, max_bytes: int | None):
    """Reads `source` (a `.read(n)` file-like) in bounded blocks.

    Enforces the empty-body and size-limit invariants lazily, before any byte
    is persisted: an empty stream raises `ValidationError`; exceeding
    `max_bytes` raises `ChunkTooLargeError` (and the caller's atomic write
    removes its temp file).
    """
    total = 0
    while True:
        block = source.read(STREAM_BLOCK_SIZE)
        if not block:
            if total == 0:
                raise ValidationError("media bytes must not be empty")
            return
        total += len(block)
        if max_bytes is not None and total > max_bytes:
            raise ChunkTooLargeError(f"chunk media exceeds {max_bytes} bytes")
        yield block


class CaptureService:
    def __init__(self, videos_root: Path | None = None):
        self.store = ManifestStore(videos_root if videos_root is not None else VIDEOS_DIR)
        self._session_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, session_id: str) -> threading.Lock:
        models.validate_session_id(session_id)
        with self._locks_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._session_locks[session_id] = lock
            return lock

    # ── sessions ────────────────────────────────────────────────────

    def create_session(
        self,
        title: str,
        *,
        chunk_duration_sec: int = models.DEFAULT_CHUNK_DURATION_SEC,
        crop: models.CropRegion | None = None,
        recorded_at: str | None = None,
        created_at: str | None = None,
        audio_availability: models.AudioAvailability = models.AudioAvailability.UNKNOWN,
    ) -> models.Session:
        created_at = created_at or models.now_iso()
        session = models.Session(
            session_id=models.new_session_id(),
            title=title,
            status=models.SessionStatus.ACTIVE,
            created_at=created_at,
            recorded_at=recorded_at or created_at,
            chunk_duration_sec=chunk_duration_sec,
            audio_availability=audio_availability,
            crop=crop,
        )
        self.store.create_session(session)
        return session

    def get_session(self, session_id: str) -> models.Session:
        return self.store.load_session(session_id)

    def list_sessions(self) -> list[models.Session]:
        return self.store.list_sessions()

    def finalize_session(
        self,
        session_id: str,
        *,
        recorded_at: str | None = None,
        ended_at: str | None = None,
        reason: str | None = None,
    ) -> models.Session:
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            updated = session.transition_to(models.SessionStatus.FINALIZED)
            updated = replace(
                updated,
                ended_at=ended_at or models.now_iso(),
                recorded_at=recorded_at or updated.recorded_at or updated.created_at,
                reason=reason,
            )
            self.store.save_session(updated)
            return updated

    def set_crop(self, session_id: str, crop: models.CropRegion | None) -> models.Session:
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            updated = replace(session, crop=crop)
            self.store.save_session(updated)
            return updated

    def set_audio_availability(
        self, session_id: str, availability: models.AudioAvailability | str
    ) -> models.Session:
        value = availability.value if isinstance(availability, models.AudioAvailability) else availability
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            updated = replace(session, audio_availability=models.AudioAvailability(str(value)))
            self.store.save_session(updated)
            return updated

    # ── chunks ──────────────────────────────────────────────────────

    def start_chunk(
        self,
        session_id: str,
        *,
        recorded_at: str | None = None,
        audio_availability: models.AudioAvailability = models.AudioAvailability.UNKNOWN,
    ) -> models.Chunk:
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            if session.status is not models.SessionStatus.ACTIVE:
                raise InvalidTransitionError(
                    f"session {session_id} is {session.status.value}, not ACTIVE"
                )
            created = models.now_iso()
            chunk = models.Chunk(
                index=session.next_chunk_index,
                state=models.ChunkState.RECORDING,
                created_at=created,
                recorded_at=recorded_at or created,
                audio_availability=audio_availability,
            )
            self.store.save_session(session.with_chunk(chunk))
            return chunk

    def finalize_chunk(
        self,
        session_id: str,
        index: int,
        media_bytes: bytes,
        *,
        media_extension: str = ".webm",
        audio_availability: models.AudioAvailability | None = None,
        recorded_at: str | None = None,
    ) -> models.Chunk:
        if not isinstance(media_bytes, (bytes, bytearray)):
            raise ValidationError("media bytes must be bytes")
        return self.finalize_chunk_stream(
            session_id,
            index,
            io.BytesIO(bytes(media_bytes)),
            media_extension=media_extension,
            audio_availability=audio_availability,
            recorded_at=recorded_at,
        )

    def finalize_chunk_stream(
        self,
        session_id: str,
        index: int,
        source,
        *,
        media_extension: str = ".webm",
        audio_availability: models.AudioAvailability | None = None,
        recorded_at: str | None = None,
        max_bytes: int | None = None,
    ) -> models.Chunk:
        """Streams `source` (a `.read(n)` file-like) into finalized chunk media.

        Reads in bounded blocks, hashes/counts incrementally and writes
        atomically — the whole body is never buffered. RECORDING -> FINALIZED
        is persisted only after the media lands; an empty or oversized stream
        leaves the chunk RECORDING and writes nothing.
        """
        extension = normalize_extension(media_extension)
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            chunk = session.get_chunk(index)
            updated = chunk.transition_to(models.ChunkState.FINALIZED)
            sha256, size = self.store.write_chunk_media_stream(
                session_id, index, extension, _stream_blocks(source, max_bytes)
            )
            finalized = replace(
                updated,
                finalized_at=models.now_iso(),
                recorded_at=recorded_at if recorded_at else updated.recorded_at,
                audio_availability=audio_availability if audio_availability else updated.audio_availability,
                media_extension=extension,
                media_size_bytes=size,
                media_sha256=sha256,
            )
            self.store.save_session(session.with_chunk(finalized))
            return finalized

    def _transition_chunk(self, session_id: str, index: int, target: models.ChunkState, **updates) -> models.Chunk:
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            updated = session.get_chunk(index).transition_to(target)
            if updates:
                updated = replace(updated, **updates)
            self.store.save_session(session.with_chunk(updated))
            return updated

    def mark_processing(self, session_id: str, index: int) -> models.Chunk:
        return self._transition_chunk(session_id, index, models.ChunkState.PROCESSING)

    def mark_processed(self, session_id: str, index: int) -> models.Chunk:
        return self._transition_chunk(session_id, index, models.ChunkState.PROCESSED, transcript_available=True)

    def mark_failed(self, session_id: str, index: int) -> models.Chunk:
        return self._transition_chunk(session_id, index, models.ChunkState.FAILED)

    # ── recovery / read model ───────────────────────────────────────

    def reconcile(self, session_id: str) -> models.Session:
        """Reconciles a session from disk without claiming incomplete data.

        - RECORDING chunks (interrupted before finalization) become FAILED.
        - FINALIZED-or-later chunks whose media file is missing become FAILED.
        - An ACTIVE session with no remaining recording work is closed as
          FAILED with reason "interrupted"; finalized chunks stay recoverable.
        """
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            corrected: list[models.Chunk] = []
            for chunk in session.chunks:
                if chunk.state is models.ChunkState.RECORDING:
                    corrected.append(replace(chunk, state=models.ChunkState.FAILED))
                elif (
                    chunk.playable
                    and chunk.media_extension is not None
                    and not self.store.chunk_media_exists(session_id, chunk.index, chunk.media_extension)
                ):
                    corrected.append(
                        replace(chunk, state=models.ChunkState.FAILED, media_size_bytes=None, media_sha256=None)
                    )
                else:
                    corrected.append(chunk)
            updated = replace(session, chunks=tuple(sorted(corrected, key=lambda c: c.index)))
            if session.status is models.SessionStatus.ACTIVE:
                updated = replace(
                    updated,
                    status=models.SessionStatus.FAILED,
                    ended_at=models.now_iso(),
                    reason=updated.reason or "interrupted",
                )
            self.store.save_session(updated)
            return updated

    def finalized_chunks(self, session_id: str) -> list[models.Chunk]:
        """Only playable chunks whose finalized media exists on disk."""
        session = self.store.load_session(session_id)
        result = [
            chunk
            for chunk in session.chunks
            if chunk.playable
            and chunk.media_extension is not None
            and self.store.chunk_media_exists(session_id, chunk.index, chunk.media_extension)
        ]
        return sorted(result, key=lambda c: c.index)
