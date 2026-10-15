"""Capture service API — the single entry point W4 (browser UI) and W5
(chunking/upload) call.

Wraps the `ManifestStore` with the validated chunk/session state machine.
Recording bytes are accepted only through `finalize_chunk`, which writes
media atomically and flips the chunk RECORDING -> FINALIZED. Incomplete
(never-finalized) chunks are never exposed as playable.
"""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import replace
from pathlib import Path

from transcript_pipeline.config import VIDEOS_DIR
from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.audio import transcript_required
from transcript_pipeline.live_capture.errors import (
    ChunkTooLargeError,
    FragmentConflictError,
    FragmentTooLargeError,
    InvalidTransitionError,
    UploadCancelledError,
    ValidationError,
)
from transcript_pipeline.live_capture.store import ManifestStore, normalize_extension
from transcript_pipeline.media.utils import media_has_audio_stream

# Bounded read size for streamed uploads: the server never holds more than
# this many bytes of a chunk body in memory at once.
STREAM_BLOCK_SIZE = 64 * 1024

logger = logging.getLogger(__name__)


def _stream_blocks(source, max_bytes: int | None, cancelled=None, too_large_error=ChunkTooLargeError):
    """Reads `source` (a `.read(n)` file-like) in bounded blocks.

    Enforces the empty-body and size-limit invariants lazily, before any byte
    is persisted: an empty stream raises `ValidationError`; exceeding
    `max_bytes` raises `too_large_error` (and the caller's atomic write
    removes its temp file).
    """
    total = 0
    while True:
        if cancelled is not None and cancelled.is_set():
            raise UploadCancelledError("upload cancelled")
        block = source.read(STREAM_BLOCK_SIZE)
        if not block:
            if total == 0:
                raise ValidationError("media bytes must not be empty")
            return
        total += len(block)
        if max_bytes is not None and total > max_bytes:
            raise too_large_error(f"media exceeds {max_bytes} bytes")
        yield block


class CaptureService:
    def __init__(self, videos_root: Path | None = None, audio_probe=None):
        self.store = ManifestStore(videos_root if videos_root is not None else VIDEOS_DIR)
        # Injectable ffprobe-based audio-stream detector (path -> bool | None).
        # Defaults to the real ffprobe helper; tests inject a fake so no
        # ffprobe binary or real media is required.
        self._audio_probe = audio_probe if audio_probe is not None else media_has_audio_stream
        self._session_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._upload_events: dict[tuple[str, int], threading.Event] = {}
        self._upload_events_lock = threading.Lock()

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

    # ── late transcript association (W8) ─────────────────────────────

    def associate_transcript(
        self,
        session_id: str,
        text: str,
        *,
        language: str | None = None,
        supplied_at: str | None = None,
    ) -> models.Session:
        """Associates a late, loosely-aligned transcript with a session.

        The transcript is persisted as one opaque text block (in the manifest
        plus a `transcript.txt` sidecar) with only its arrival time — no
        per-second sync is ever invented. Every chunk is marked
        transcript-available and has `transcript_required` cleared, but its
        processing `state` is left untouched: a FINALIZED/PROCESSING chunk is
        *not* forced to PROCESSED merely because a transcript arrived.
        Re-supplying the same (or an updated) transcript is idempotent — it
        overwrites the previous value rather than accumulating.
        """
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            transcript = models.Transcript(
                text=text,
                supplied_at=supplied_at or models.now_iso(),
                language=language,
            )
            updated_chunks = tuple(
                replace(c, transcript_available=True, transcript_required=False)
                for c in session.chunks
            )
            updated = replace(session, transcript=transcript, chunks=updated_chunks)
            self.store.write_transcript(session_id, transcript.text)
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
        key = (session_id, index)
        event = threading.Event()
        with self._upload_events_lock:
            self._upload_events[key] = event
        with self._lock_for(session_id):
            try:
                session = self.store.load_session(session_id)
                chunk = session.get_chunk(index)
                updated = chunk.transition_to(models.ChunkState.FINALIZED)
                sha256, size = self.store.write_chunk_media_stream(
                    session_id, index, extension, _stream_blocks(source, max_bytes, event)
                )
                finalized = replace(
                    updated,
                    finalized_at=models.now_iso(),
                    recorded_at=recorded_at if recorded_at else updated.recorded_at,
                    audio_availability=audio_availability if audio_availability else updated.audio_availability,
                    transcript_required=transcript_required(
                        audio_availability if audio_availability else updated.audio_availability,
                        updated.transcript_available,
                    ),
                    media_extension=extension,
                    media_size_bytes=size,
                    media_sha256=sha256,
                )
                self.store.save_session(session.with_chunk(finalized))
                return finalized
            finally:
                with self._upload_events_lock:
                    self._upload_events.pop(key, None)

    def cancel_upload(self, session_id: str, index: int) -> models.Chunk:
        key = (session_id, index)
        with self._upload_events_lock:
            event = self._upload_events.get(key)
            if event is not None:
                event.set()
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            chunk = session.get_chunk(index)
            if chunk.state is models.ChunkState.UPLOAD_CANCELLED:
                return chunk
            if chunk.state is models.ChunkState.RECORDING:
                cancelled = chunk.transition_to(models.ChunkState.UPLOAD_CANCELLED)
                self.store.save_session(session.with_chunk(cancelled))
                return cancelled
            return chunk

    def retry_cancelled_upload(self, session_id: str, index: int) -> models.Chunk:
        return self._transition_chunk(session_id, index, models.ChunkState.RECORDING)

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

    def mark_processed(
        self, session_id: str, index: int, *, transcript_available: bool = True
    ) -> models.Chunk:
        session = self.store.load_session(session_id)
        chunk = session.get_chunk(index)
        available = transcript_available or chunk.transcript_available
        return self._transition_chunk(
            session_id,
            index,
            models.ChunkState.PROCESSED,
            transcript_available=available,
            transcript_required=not available and chunk.audio_availability is models.AudioAvailability.MISSING,
        )

    def mark_failed(self, session_id: str, index: int) -> models.Chunk:
        return self._transition_chunk(session_id, index, models.ChunkState.FAILED)

    def cancel_processing(self, session_id: str, index: int) -> models.Chunk:
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            chunk = session.get_chunk(index)
            if chunk.state in (models.ChunkState.CANCELLED, models.ChunkState.CANCEL_REQUESTED,
                               models.ChunkState.PROCESSED, models.ChunkState.UPLOAD_CANCELLED):
                return chunk
            target = (
                models.ChunkState.CANCELLED
                if chunk.state is models.ChunkState.FINALIZED
                else models.ChunkState.CANCEL_REQUESTED
            )
            cancelled = chunk.transition_to(target)
            self.store.save_session(session.with_chunk(cancelled))
            return cancelled

    def retry_cancelled_processing(self, session_id: str, index: int) -> models.Chunk:
        return self._transition_chunk(session_id, index, models.ChunkState.FINALIZED)

    def mark_cancelled(self, session_id: str, index: int) -> models.Chunk:
        return self._transition_chunk(session_id, index, models.ChunkState.CANCELLED)

    def delete_cancelled_chunk(self, session_id: str, index: int, *, confirmed: bool) -> models.Chunk:
        if not confirmed:
            raise ValidationError("explicit confirmation is required")
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            chunk = session.get_chunk(index)
            if chunk.state is not models.ChunkState.CANCELLED:
                raise InvalidTransitionError("only CANCELLED media can be deleted")
            if chunk.media_extension:
                self.store.chunk_media_path(session_id, index, chunk.media_extension).unlink(missing_ok=True)
            self.store.save_session(replace(session, chunks=tuple(c for c in session.chunks if c.index != index)))
            return chunk

    def complete_processing(
        self, session_id: str, index: int, *, transcript_available: bool
    ) -> models.Chunk:
        """Atomically honor cancellation before committing successful completion."""
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            chunk = session.get_chunk(index)
            if chunk.state is models.ChunkState.CANCEL_REQUESTED:
                updated = chunk.transition_to(models.ChunkState.CANCELLED)
            elif chunk.state is models.ChunkState.PROCESSING:
                available = transcript_available or chunk.transcript_available
                updated = chunk.transition_to(models.ChunkState.PROCESSED)
                updated = replace(
                    updated,
                    transcript_available=available,
                    transcript_required=not available and chunk.audio_availability is models.AudioAvailability.MISSING,
                )
            else:
                return chunk
            self.store.save_session(session.with_chunk(updated))
            return updated

    # ── audio detection (W7) ─────────────────────────────────────────

    def detect_chunk_audio(self, session_id: str, index: int) -> models.Chunk:
        """Probes finalized chunk media for an audio stream and persists it.

        Uses the injected `_audio_probe` (the ffprobe helper by default). A
        probe that cannot decide — unreadable media, missing ffprobe, a
        transient crash — yields UNKNOWN and never raises, so an absent audio
        track is a valid state that cannot fail a caller. A confirmed absence
        marks the chunk MISSING and transcript-required; a confirmed presence
        marks it AVAILABLE. A RECORDING chunk has no media to probe and is
        rejected.
        """
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            chunk = session.get_chunk(index)
            if chunk.state is models.ChunkState.RECORDING:
                raise InvalidTransitionError(
                    f"chunk {models.chunk_id(index)} has no finalized media to probe"
                )
            if chunk.media_extension is None:
                return chunk

            path = self.store.chunk_media_path(session_id, index, chunk.media_extension)
            try:
                stream_present = self._audio_probe(str(path))
            except Exception:
                logger.warning("[CAPTURE] audio probe failed for chunk %s", models.chunk_id(index), exc_info=True)
                stream_present = None

            availability = models.AudioAvailability.UNKNOWN
            if stream_present is True:
                availability = models.AudioAvailability.AVAILABLE
            elif stream_present is False:
                availability = models.AudioAvailability.MISSING

            updated = replace(
                chunk,
                audio_availability=availability,
                transcript_required=transcript_required(availability, chunk.transcript_available),
            )
            self.store.save_session(session.with_chunk(updated))
            return updated

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
                    corrected.append(replace(chunk, state=models.ChunkState.UPLOAD_CANCELLED))
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

    # ── upload fragments (W5) ───────────────────────────────────────

    def list_fragments(self, session_id: str) -> list[models.Fragment]:
        """Durable fragments for a session, ordered by sequence then ID."""
        self.store.load_session(session_id)
        return self.store.load_fragments(session_id)

    def upload_fragment(
        self,
        session_id: str,
        fragment_id: str,
        sequence: int,
        source,
        *,
        media_extension: str = ".webm",
        max_bytes: int | None = None,
    ) -> models.Fragment:
        """Durably stores one upload fragment and returns its ACK record.

        The body is streamed in bounded blocks into a temp file (never
        buffered whole) and hashed incrementally. Only after the bytes are
        durable *and* the manifest entry is written is the fragment returned
        as ACKed. Replaying the same `fragment_id`:

        - with identical bytes returns the previously ACKed record without
          writing a duplicate or touching the stored media;
        - with different bytes, size or extension raises
          `FragmentConflictError` (-> 409) and never overwrites the original.

        Concurrent uploads for the same session are serialized around the
        manifest check/commit by the per-session lock; staging happens outside
        that lock so an in-flight body cannot block unrelated reads.
        """
        normalized_id = models.validate_fragment_id(fragment_id)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("fragment sequence must be a nonnegative integer")
        extension = normalize_extension(media_extension)
        # A missing session must fail before any bytes are staged.
        self.store.load_session(session_id)

        tmp_path = None
        try:
            tmp_path, sha256, size = self.store.stage_fragment_stream(
                session_id,
                normalized_id,
                _stream_blocks(source, max_bytes, too_large_error=FragmentTooLargeError),
            )
            with self._lock_for(session_id):
                # Re-validate under the lock: the session may have been
                # removed between staging and commit.
                self.store.load_session(session_id)
                fragments = self.store.load_fragments(session_id)
                existing = next((f for f in fragments if f.fragment_id == normalized_id), None)
                if existing is not None:
                    if (
                        existing.media_sha256 != sha256
                        or existing.media_size_bytes != size
                        or existing.media_extension != extension
                    ):
                        raise FragmentConflictError(
                            f"fragment {normalized_id} already exists with different bytes"
                        )
                    if not self.store.fragment_media_exists(session_id, normalized_id, extension):
                        # Manifest says stored but the file is gone: repair by
                        # committing the identical staged bytes, still ACK.
                        self.store.commit_staged_fragment(tmp_path, session_id, normalized_id, extension)
                        tmp_path = None
                    return existing

                fragment = models.Fragment(
                    fragment_id=normalized_id,
                    sequence=sequence,
                    created_at=models.now_iso(),
                    media_extension=extension,
                    media_size_bytes=size,
                    media_sha256=sha256,
                )
                self.store.commit_staged_fragment(tmp_path, session_id, normalized_id, extension)
                tmp_path = None
                self.store.save_fragments(session_id, [*fragments, fragment])
                return fragment
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
