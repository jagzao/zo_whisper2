"""Capture service API — the single entry point W4 (browser UI) and W5
(chunking/upload) call.

Wraps the `ManifestStore` with the validated chunk/session state machine.
Recording bytes are accepted only through `finalize_chunk`, which writes
media atomically and flips the chunk RECORDING -> FINALIZED. Incomplete
(never-finalized) chunks are never exposed as playable.
"""

from __future__ import annotations

import io
import hashlib
import logging
import os
import threading
from dataclasses import replace
from pathlib import Path

from transcript_pipeline.config import VIDEOS_DIR
from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.assembly import assemble_media, ensure_seekable_audio
from transcript_pipeline.live_capture.audio import transcript_required
from transcript_pipeline.live_capture.errors import (
    AssemblyError,
    ChunkNotFoundError,
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(STREAM_BLOCK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _optional_nonnegative_ms(value: int | None, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{label} must be a nonnegative integer or omitted")
    return value


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
    def __init__(self, videos_root: Path | None = None, audio_probe=None, assembler=None):
        self.store = ManifestStore(videos_root if videos_root is not None else VIDEOS_DIR)
        # Injectable ffprobe-based audio-stream detector (path -> bool | None).
        # Defaults to the real ffprobe helper; tests inject a fake so no
        # ffprobe binary or real media is required.
        self._audio_probe = audio_probe if audio_probe is not None else media_has_audio_stream
        # Injectable fragment assembler (list[Path], dest Path) -> None. The
        # default uses FFmpeg concat/remux with a validated fallback; tests
        # inject a synthetic assembler so boundary/mapping/retry logic is
        # deterministic without any real media.
        self._assembler = assembler if assembler is not None else assemble_media
        self._session_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._upload_events: dict[tuple[str, int], threading.Event] = {}
        self._upload_events_lock = threading.Lock()
        # Serializes processing-chunk aggregation per session. Distinct from
        # `_lock_for` so aggregation can call the (lock-taking) finalize path
        # without deadlocking while still preventing two concurrent assemblies
        # of the same fragment range.
        self._aggregation_locks: dict[str, threading.Lock] = {}

    def _lock_for(self, session_id: str) -> threading.Lock:
        models.validate_session_id(session_id)
        with self._locks_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._session_locks[session_id] = lock
            return lock

    def _aggregation_lock_for(self, session_id: str) -> threading.Lock:
        models.validate_session_id(session_id)
        with self._locks_guard:
            lock = self._aggregation_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._aggregation_locks[session_id] = lock
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
        capture_mode: str = "normal",
        project_id: str | None = None,
        is_test_session: bool = False,
        capture_kind: str = "video",
        capture_source: str | None = None,
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
            capture_mode=capture_mode,
            project_id=project_id,
            is_test_session=is_test_session,
            capture_kind=capture_kind,
            capture_source=capture_source,
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
            if session.status is models.SessionStatus.FINALIZED:
                return session
            updated = session.transition_to(models.SessionStatus.FINALIZED)
            updated = replace(
                updated,
                ended_at=ended_at or models.now_iso(),
                recorded_at=recorded_at or updated.recorded_at or updated.created_at,
                reason=reason,
            )
            self.store.save_session(updated)
            return updated

    def finalize_session_media(self, session_id: str) -> dict:
        """Create one durable, validated media file for the whole capture."""
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            if session.status is not models.SessionStatus.FINALIZED:
                raise InvalidTransitionError("capture session must be finalized before media assembly")
            chunks = sorted((c for c in session.chunks if c.media_extension), key=lambda c: c.index)
            if not chunks:
                raise AssemblyError("capture has no finalized processing chunks")
            extensions = {chunk.media_extension for chunk in chunks}
            if len(extensions) != 1:
                raise AssemblyError("capture processing chunks use mixed media formats")
            extension = next(iter(extensions))
            final_path = self.store.final_media_path(session_id, extension)
            existing = session.final_media or {}
            if final_path.is_file() and existing.get("extension") == extension:
                digest = _sha256_file(final_path)
                if digest == existing.get("sha256") and final_path.stat().st_size == existing.get("sizeBytes"):
                    return dict(existing)

            mappings = self.store.load_processing_map(session_id)
            if mappings and any(not entry.finalized for entry in mappings):
                raise AssemblyError("processing chunks are not all finalized")
            sources = [self.store.chunk_media_path(session_id, c.index, extension) for c in chunks]
            if any(not path.is_file() for path in sources):
                raise AssemblyError("a processing chunk is missing; source media was preserved")
            staging = self.store.final_staging_path(session_id, extension)
            staging.unlink(missing_ok=True)
            duration_seconds = None
            try:
                self._assembler(sources, staging)
                if session.capture_kind == "audio" and self._assembler is assemble_media:
                    normalized = self.store.final_normalized_path(session_id, extension)
                    duration_seconds = ensure_seekable_audio(staging, normalized)
                    if normalized.is_file():
                        staging.unlink(missing_ok=True)
                        os.replace(normalized, staging)
                final_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging, final_path)
            except Exception:
                staging.unlink(missing_ok=True)
                self.store.final_normalized_path(session_id, extension).unlink(missing_ok=True)
                raise
            metadata = {
                "relativePath": final_path.relative_to(self.store.session_dir(session_id)).as_posix(),
                "extension": extension,
                "sizeBytes": final_path.stat().st_size,
                "sha256": _sha256_file(final_path),
                "durationSec": duration_seconds,
                "createdAt": existing.get("createdAt") or models.now_iso(),
                "processingChunkIds": [models.chunk_id(chunk.index) for chunk in chunks],
                "fragmentIds": [fid for entry in mappings for fid in entry.fragment_ids],
            }
            self.store.save_session(replace(session, final_media=metadata))
            return metadata

    def cleanup_temporary_media_if_safe(self, session_id: str) -> bool:
        """Delete blobs only after validated final media and completed processing."""
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            metadata = session.final_media or {}
            extension = metadata.get("extension")
            final_path = self.store.final_media_path(session_id, extension) if extension else None
            if not final_path or not final_path.is_file() or _sha256_file(final_path) != metadata.get("sha256"):
                return False
            if not session.chunks or any(c.state is not models.ChunkState.PROCESSED for c in session.chunks):
                return False
            mappings = self.store.load_processing_map(session_id)
            if mappings and any(not entry.finalized for entry in mappings):
                return False
            for fragment in self.store.load_fragments(session_id):
                self.store.fragment_media_path(session_id, fragment.fragment_id, fragment.media_extension).unlink(missing_ok=True)
            for chunk in session.chunks:
                if chunk.media_extension:
                    self.store.chunk_media_path(session_id, chunk.index, chunk.media_extension).unlink(missing_ok=True)
            return True

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

    def set_capture_source(self, session_id: str, source: str) -> models.Session:
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            updated = replace(session, capture_source=source)
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
                project_id=session.project_id,
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
                return self._finalize_chunk_stream_locked(
                    session_id, index, source, extension,
                    event, audio_availability, recorded_at, max_bytes,
                )
            finally:
                with self._upload_events_lock:
                    self._upload_events.pop(key, None)

    def _finalize_chunk_stream_locked(
        self,
        session_id: str,
        index: int,
        source,
        extension: str,
        cancelled: threading.Event | None,
        audio_availability: models.AudioAvailability | None,
        recorded_at: str | None,
        max_bytes: int | None,
    ) -> models.Chunk:
        """FINALIZED commit; the caller already holds the per-session lock.

        Shared by the browser upload path and server-side processing-chunk
        assembly (W6), so both write media atomically and persist the exact
        same finalized record.
        """
        session = self.store.load_session(session_id)
        chunk = session.get_chunk(index)
        updated = chunk.transition_to(models.ChunkState.FINALIZED)
        sha256, size = self.store.write_chunk_media_stream(
            session_id, index, extension, _stream_blocks(source, max_bytes, cancelled)
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
        duration_ms: int | None = None,
        recorded_offset_ms: int | None = None,
        recorded_at: str | None = None,
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

        The optional recorded-timeline fields (W6) are stored on the fragment
        for server-side processing-chunk aggregation; they never change the
        ACK/idempotency semantics (a replay returns the already-stored record).

        After the fragment is durable, aggregation is attempted (best-effort):
        a full processing chunk may finalize on the recorded duration threshold
        while capture continues. Aggregation failure never fails the upload —
        the fragment stays ACKed and the chunk stays retryable.
        """
        normalized_id = models.validate_fragment_id(fragment_id)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValidationError("fragment sequence must be a nonnegative integer")
        duration_ms = _optional_nonnegative_ms(duration_ms, "duration_ms")
        recorded_offset_ms = _optional_nonnegative_ms(recorded_offset_ms, "recorded_offset_ms")
        if recorded_at is not None and (not isinstance(recorded_at, str) or not recorded_at.strip()):
            raise ValidationError("recorded_at must be a non-empty string or omitted")
        extension = normalize_extension(media_extension)
        # A missing session must fail before any bytes are staged.
        self.store.load_session(session_id)

        tmp_path = None
        result: models.Fragment
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
                    result = existing
                else:
                    fragment = models.Fragment(
                        fragment_id=normalized_id,
                        sequence=sequence,
                        created_at=models.now_iso(),
                        media_extension=extension,
                        media_size_bytes=size,
                        media_sha256=sha256,
                        duration_ms=duration_ms,
                        recorded_offset_ms=recorded_offset_ms,
                        recorded_at=recorded_at,
                        project_id=self.store.load_session(session_id).project_id,
                    )
                    self.store.commit_staged_fragment(tmp_path, session_id, normalized_id, extension)
                    tmp_path = None
                    self.store.save_fragments(session_id, [*fragments, fragment])
                    result = fragment
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        self._aggregate_best_effort(session_id)
        return result

    # ── processing chunks: fragment aggregation (W6) ────────────────

    def list_processing_chunks(self, session_id: str) -> list[models.ProcessingChunkMapping]:
        """Durable fragment->processing-chunk map, ordered by chunk index."""
        self.store.load_session(session_id)
        return self.store.load_processing_map(session_id)

    def finalize_processing_chunk(self, session_id: str) -> models.Chunk | None:
        """Finalizes the next duration-complete processing chunk, if any.

        Non-forcing: it only assembles when the accumulated *recorded*
        duration of the not-yet-assigned fragments already reaches the
        session's configured `chunk_duration_sec`. Safe to call after every
        fragment ACK; a no-op while the current chunk is still filling up.
        """
        return self._aggregate(session_id, force=False)

    def drain_processing_chunks(self, session_id: str) -> models.Chunk | None:
        """Assembles every pending fragment, force-finalizing a partial tail.

        Called on session stop: complete chunks finalize first, then the
        remaining fragments become one final partial chunk. Returns the last
        finalized chunk (or None when there was nothing to assemble).
        """
        return self._aggregate(session_id, force=True)

    def _aggregate_best_effort(self, session_id: str) -> None:
        try:
            self.finalize_processing_chunk(session_id)
        except Exception:  # noqa: BLE001 - upload must never fail on aggregation
            logger.warning(
                "[CAPTURE] processing-chunk aggregation failed for %s", session_id, exc_info=True
            )

    def _aggregate(self, session_id: str, *, force: bool) -> models.Chunk | None:
        models.validate_session_id(session_id)
        last: models.Chunk | None = None
        with self._aggregation_lock_for(session_id):
            while True:
                plan = self._reserve_processing_plan(session_id, force=force)
                if plan is None:
                    return last
                staging = self._run_assembly(session_id, plan)
                if staging is None:
                    # Assembly failed and the entry was marked retryable; the
                    # source fragments survive and a later call reruns this.
                    return last
                chunk = self._commit_processing_plan(session_id, plan, staging)
                if chunk is not None:
                    last = chunk
                if not force:
                    return last

    def _reserve_processing_plan(self, session_id: str, *, force: bool):
        """Reserves (durably) the next processing chunk range, or returns None.

        Retries the lowest unfinished mapping entry first; otherwise selects
        the leading unassigned fragments whose recorded durations reach the
        configured threshold (or, when forcing, the whole remaining tail).
        """
        with self._lock_for(session_id):
            session = self.store.load_session(session_id)
            fragments = self.store.load_fragments(session_id)
            entries = self.store.load_processing_map(session_id)

            for entry in entries:
                if entry.retryable:
                    return entry

            assigned = {fid for e in entries for fid in e.fragment_ids}
            lead = [f for f in fragments if f.fragment_id not in assigned]
            if not lead:
                return None

            threshold_ms = session.chunk_duration_sec * 1000
            selection = _select_fragment_range(lead, threshold_ms, force=force)
            if selection is None:
                return None
            selected, duration_ms = selection

            index = _next_processing_index(session, entries)
            entry = models.ProcessingChunkMapping(
                chunk_index=index,
                fragment_ids=tuple(f.fragment_id for f in selected),
                start_offset_ms=_start_offset_ms(lead, selected),
                duration_ms=duration_ms,
                state=models.PROCESSING_STATE_PENDING,
                created_at=models.now_iso(),
                recorded_at=selected[0].recorded_at,
                project_id=session.project_id,
            )
            self.store.save_processing_map(session_id, [*entries, entry])
            return entry

    def _run_assembly(self, session_id: str, plan: models.ProcessingChunkMapping):
        """Runs the injected assembler into a staging file; None on failure.

        Reads only the surviving ACKed fragments — nothing is deleted and no
        browser data is requested again. On failure the mapping entry becomes
        RETRYABLE and the staging file is removed.
        """
        fragments = {f.fragment_id: f for f in self.store.load_fragments(session_id)}
        paths: list[Path] = []
        extension: str | None = None
        for fid in plan.fragment_ids:
            frag = fragments.get(fid)
            if frag is None:
                return self._mark_processing_retryable(session_id, plan, "source fragment is missing")
            if extension is None:
                extension = frag.media_extension
            elif frag.media_extension != extension:
                return self._mark_processing_retryable(
                    session_id, plan, "fragments use mixed media extensions"
                )
            path = self.store.fragment_media_path(session_id, fid, frag.media_extension)
            if not path.is_file():
                return self._mark_processing_retryable(
                    session_id, plan, f"fragment media is missing: {fid}"
                )
            paths.append(path)

        assert extension is not None
        staging = self.store.assembly_staging_path(session_id, plan.chunk_index, extension)
        try:
            self._assembler(paths, staging)
        except AssemblyError as exc:
            staging.unlink(missing_ok=True)
            return self._mark_processing_retryable(session_id, plan, str(exc)[:300])
        except Exception as exc:  # noqa: BLE001 - any assembler failure is retryable
            staging.unlink(missing_ok=True)
            return self._mark_processing_retryable(session_id, plan, str(exc)[:300])
        return staging

    def _mark_processing_retryable(
        self, session_id: str, plan: models.ProcessingChunkMapping, error: str
    ):
        message = error.strip() or "assembly failed"
        with self._lock_for(session_id):
            entries = self.store.load_processing_map(session_id)
            updated = [
                replace(e, state=models.PROCESSING_STATE_RETRYABLE, last_error=message)
                if e.chunk_index == plan.chunk_index
                else e
                for e in entries
            ]
            self.store.save_processing_map(session_id, updated)
        logger.warning(
            "[CAPTURE] processing chunk %s is retryable: %s",
            models.chunk_id(plan.chunk_index),
            message,
        )
        return None

    def _commit_processing_plan(
        self, session_id: str, plan: models.ProcessingChunkMapping, staging: Path
    ) -> models.Chunk | None:
        """Finalizes the reused `models.Chunk` and marks the mapping FINALIZED.

        Never overwrites an existing playable chunk at that index. The staging
        assembly is removed afterwards whether or not it was consumed.
        """
        try:
            with self._lock_for(session_id):
                extension = plan.chunk_extension or staging.suffix
                session = self.store.load_session(session_id)
                chunk = self._ensure_processing_chunk_locked(
                    session_id,
                    plan.chunk_index,
                    staging,
                    extension,
                    session.audio_availability,
                    plan.recorded_at,
                )
                entries = self.store.load_processing_map(session_id)
                finalized_at = models.now_iso()
                updated = [
                    replace(
                        e,
                        state=models.PROCESSING_STATE_FINALIZED,
                        finalized_at=finalized_at,
                        last_error=None,
                        chunk_extension=extension,
                    )
                    if e.chunk_index == plan.chunk_index
                    else e
                    for e in entries
                ]
                self.store.save_processing_map(session_id, updated)
                return chunk
        finally:
            staging.unlink(missing_ok=True)

    def _ensure_processing_chunk_locked(
        self,
        session_id: str,
        index: int,
        media_source_path: Path,
        extension: str,
        audio_availability: models.AudioAvailability,
        recorded_at: str | None,
    ) -> models.Chunk:
        session = self.store.load_session(session_id)
        try:
            chunk = session.get_chunk(index)
        except ChunkNotFoundError:
            chunk = None

        if (
            chunk is not None
            and chunk.playable
            and chunk.media_extension is not None
            and self.store.chunk_media_exists(session_id, index, chunk.media_extension)
        ):
            # Already finalized by a previous attempt: never rewrite it.
            return chunk

        if chunk is None:
            created = models.Chunk(
                index=index,
                state=models.ChunkState.RECORDING,
                created_at=models.now_iso(),
                recorded_at=recorded_at or models.now_iso(),
                audio_availability=audio_availability,
                project_id=session.project_id,
            )
            self.store.save_session(session.with_chunk(created))
        elif chunk.state is models.ChunkState.UPLOAD_CANCELLED:
            self.store.save_session(
                session.with_chunk(chunk.transition_to(models.ChunkState.RECORDING))
            )
        elif chunk.state is not models.ChunkState.RECORDING:
            # A chunk already in a downstream state (or terminally failed) is
            # preserved as-is; the mapping is still marked finalized.
            return chunk

        with open(media_source_path, "rb") as fh:
            return self._finalize_chunk_stream_locked(
                session_id,
                index,
                fh,
                extension,
                None,
                audio_availability,
                recorded_at,
                None,
            )


def _select_fragment_range(
    lead: list[models.Fragment], threshold_ms: int, *, force: bool
) -> tuple[list[models.Fragment], int] | None:
    """Prefix of `lead` whose recorded durations reach `threshold_ms`.

    Returns None when the threshold is not reached and `force` is False. When
    forcing, the entire remaining tail is returned even if it is partial.
    """
    if threshold_ms <= 0:
        threshold_ms = 0
    selected: list[models.Fragment] = []
    accumulated = 0
    for fragment in lead:
        selected.append(fragment)
        accumulated += fragment.duration_ms or 0
        if accumulated >= threshold_ms and threshold_ms > 0:
            return selected, accumulated
    if force and selected:
        return selected, accumulated
    return None


def _start_offset_ms(lead: list[models.Fragment], selected: list[models.Fragment]) -> int:
    first = selected[0]
    if first.recorded_offset_ms is not None:
        return first.recorded_offset_ms
    offset = 0
    for fragment in lead:
        if fragment.fragment_id == first.fragment_id:
            break
        offset += fragment.duration_ms or 0
    return offset


def _next_processing_index(
    session: models.Session, entries: list[models.ProcessingChunkMapping]
) -> int:
    indexes = [c.index for c in session.chunks] + [e.chunk_index for e in entries]
    return (max(indexes) + 1) if indexes else 0
