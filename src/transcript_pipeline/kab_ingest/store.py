"""Session storage engine for the K'ab ingest (all filesystem state).

Layout under the storage root (`KAB_INGEST_ROOT`, default DATA_ROOT/kab-inbox):

    {sessionId}/
        session.json                     created by the receiver (atomic)
        state.json                       written only by the worker (atomic)
        chunks/NNNNNN/{video,audio}/     raw uploaded chunks (atomic replace)
        segments/                        assembled per-track media + .meta.json
        ready/segment-NNNNNN.ready.json  worker pickup markers (atomic)
        processing/                      worker claim markers (atomic rename)
        failed/                          worker failure markers
        completed/                       worker results (result.json, docs, mux)

Invariants enforced here:
- session IDs, indexes, tracks and extensions are validated before any path
  is built — a client never supplies a path component that reaches the disk;
- every write is temp-file + fsync + os.replace in the destination directory;
- a corrupt chunk (hash/size mismatch) is never persisted and a segment is
  never marked complete unless count/size/hash all verify;
- a ready marker exists only after every required track of the segment is
  persisted and verified;
- per-session and per-chunk size caps are enforced before bytes hit disk.

The receiver (server process) owns session.json and everything under
chunks/segments/ready; the worker owns state.json, processing/, failed/ and
completed/. No file has two writer processes.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from transcript_pipeline.kab_ingest import validation
from transcript_pipeline.kab_ingest.atomic import atomic_write_json, read_json
from transcript_pipeline.kab_ingest.errors import (
    KabIngestConflict,
    KabIngestNotFound,
    KabIngestPayloadTooLarge,
    KabIngestRequestTimeout,
    KabIngestValidationError,
)

READ_BLOCK_SIZE = 64 * 1024
DEFAULT_READ_DEADLINE_SECONDS = 120.0

SEGMENT_DIR_PREFIX = "segment-"
CHUNK_SUFFIX = ".chunk"
STATE_FILE = "state.json"
SESSION_FILE = "session.json"
READY_DIR = "ready"
PROCESSING_DIR = "processing"
FAILED_DIR = "failed"
COMPLETED_DIR = "completed"
CHUNKS_DIR = "chunks"
SEGMENTS_DIR = "segments"
RESULT_SUFFIX = ".result.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def segment_dir_name(index: int) -> str:
    return f"{SEGMENT_DIR_PREFIX}{index:06d}"


def parse_segment_index(name: str) -> int | None:
    if not name.startswith(SEGMENT_DIR_PREFIX):
        return None
    rest = name[len(SEGMENT_DIR_PREFIX):]
    if not rest.isdigit() or len(rest) != 6:
        return None
    return int(rest)


@dataclass(frozen=True)
class SessionPaths:
    root: Path
    session_id: str

    @property
    def base(self) -> Path:
        return self.root / self.session_id

    @property
    def session_file(self) -> Path:
        return self.base / SESSION_FILE

    @property
    def state_file(self) -> Path:
        return self.base / STATE_FILE

    @property
    def chunks(self) -> Path:
        return self.base / CHUNKS_DIR

    @property
    def segments(self) -> Path:
        return self.base / SEGMENTS_DIR

    @property
    def ready(self) -> Path:
        return self.base / READY_DIR

    @property
    def processing(self) -> Path:
        return self.base / PROCESSING_DIR

    @property
    def failed(self) -> Path:
        return self.base / FAILED_DIR

    @property
    def completed(self) -> Path:
        return self.base / COMPLETED_DIR

    def segment_chunks_dir(self, segment_index: int, track: str) -> Path:
        return self.chunks / f"{segment_index:06d}" / track

    def chunk_file(self, segment_index: int, track: str, chunk_index: int) -> Path:
        return self.segment_chunks_dir(segment_index, track) / f"{chunk_index:06d}{CHUNK_SUFFIX}"

    def segment_track_meta(self, segment_index: int, track: str) -> Path:
        return self.segments / f"{segment_dir_name(segment_index)}.{track}.meta.json"

    def assembled_segment(self, segment_index: int, track: str, ext: str) -> Path:
        return self.segments / f"{segment_dir_name(segment_index)}.{track}{ext}"

    def ready_marker(self, segment_index: int) -> Path:
        return self.ready / f"{segment_dir_name(segment_index)}.ready.json"

    def processing_marker(self, segment_index: int) -> Path:
        return self.processing / f"{segment_dir_name(segment_index)}.processing.json"

    def failed_marker(self, segment_index: int) -> Path:
        return self.failed / f"{segment_dir_name(segment_index)}.failed.json"

    def result_file(self, segment_index: int) -> Path:
        return self.completed / f"{segment_dir_name(segment_index)}{RESULT_SUFFIX}"


class SessionStore:
    """Single-machine session store; one writer process per file family."""

    def __init__(self, root: Path, *, max_chunk_bytes: int, max_session_bytes: int):
        if max_chunk_bytes <= 0 or max_session_bytes <= 0:
            raise ValueError("max_chunk_bytes and max_session_bytes must be positive")
        self.root = root.resolve(strict=False)
        self.max_chunk_bytes = max_chunk_bytes
        self.max_session_bytes = max_session_bytes
        self._usage_lock = threading.Lock()
        self._session_locks: dict[str, threading.Lock] = {}
        self._usage: dict[str, int] = {}

    # ── locks / usage accounting ─────────────────────────────────────

    def _lock_for(self, session_id: str) -> threading.Lock:
        with self._usage_lock:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._session_locks[session_id] = lock
            return lock

    def _session_usage(self, session_id: str) -> int:
        with self._usage_lock:
            if session_id in self._usage:
                return self._usage[session_id]
        total = _dir_size(self.paths(session_id).base)
        with self._usage_lock:
            self._usage[session_id] = total
            return total

    def _add_usage(self, session_id: str, delta: int) -> None:
        self._session_usage(session_id)
        with self._usage_lock:
            self._usage[session_id] = self._usage[session_id] + delta

    def paths(self, session_id: str) -> SessionPaths:
        return SessionPaths(root=self.root, session_id=validation.validate_session_id(session_id))

    # ── session lifecycle (receiver-owned) ───────────────────────────

    def create_session(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Creates a session or returns the existing one (metadata-idempotent).

        Returns (stored_session, created). Raises Conflict when a session
        with the same ID exists but the metadata differs.
        """
        session_id = validation.validate_session_id(payload["sessionId"])
        paths = self.paths(session_id)
        with self._lock_for(session_id):
            existing = read_json(paths.session_file)
            if existing is not None:
                if _canonical_session_payload(existing) != _canonical_session_payload(payload):
                    raise KabIngestConflict(
                        "session already exists with different metadata", code="session_metadata_conflict"
                    )
                return existing, False
            record = {
                "schemaVersion": validation.SCHEMA_VERSION,
                "sessionId": session_id,
                "title": payload["title"],
                "createdAt": payload["createdAt"],
                "segmentDurationSec": payload["segmentDurationSec"],
                "requiredTracks": payload["requiredTracks"],
                "status": "ACTIVE",
                "expectedSegmentCount": None,
                "endedAt": None,
                "reason": None,
            }
            for directory in (
                paths.base,
                paths.chunks,
                paths.segments,
                paths.ready,
                paths.processing,
                paths.failed,
                paths.completed,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            atomic_write_json(paths.session_file, record)
            with self._usage_lock:
                self._usage[session_id] = 0
            return record, True

    def load_session(self, session_id: str) -> dict[str, Any]:
        session_id = validation.validate_session_id(session_id)
        record = read_json(self.paths(session_id).session_file)
        if record is None:
            raise KabIngestNotFound("session not found", code="session_not_found")
        return record

    def finalize_session(
        self, session_id: str, *, expected_segment_count: int, ended_at: str, reason: str | None, status: str
    ) -> dict[str, Any]:
        """Persists completion metadata on session.json (receiver-owned)."""
        paths = self.paths(session_id)
        with self._lock_for(session_id):
            record = self.load_session(session_id)
            record["expectedSegmentCount"] = expected_segment_count
            record["endedAt"] = ended_at
            record["reason"] = reason
            record["status"] = status
            atomic_write_json(paths.session_file, record)
            return record

    # ── chunk upload (receiver-owned) ────────────────────────────────

    def put_chunk(
        self,
        session_id: str,
        segment_index: int,
        track: str,
        chunk_index: int,
        *,
        read: Callable[[int], bytes],
        expected_sha256: str,
        expected_size: int,
        deadline: float = DEFAULT_READ_DEADLINE_SECONDS,
    ) -> dict[str, Any]:
        """Streams a chunk body to disk with streaming SHA-256 verification.

        `read(n)` is the raw body reader (Flask's request.stream.read). The
        chunk is written to a temp file, fsynced, hash-verified and only
        then atomically moved into place; a corrupt body never persists.
        """
        validation.validate_index(segment_index, what="segmentIndex")
        validation.validate_index(chunk_index, what="chunkIndex")
        validation.validate_track(track)
        expected_sha256 = validation.validate_sha256(expected_sha256)
        if expected_size <= 0:
            raise KabIngestValidationError("chunk size must be positive", code="invalid_chunk_size")
        if expected_size > self.max_chunk_bytes:
            raise KabIngestPayloadTooLarge(
                f"chunk exceeds KAB_INGEST_MAX_CHUNK_MB limit ({self.max_chunk_bytes} bytes)",
                code="chunk_too_large",
            )

        session_id = validation.validate_session_id(session_id)
        paths = self.paths(session_id)
        self.load_session(session_id)
        final = paths.chunk_file(segment_index, track, chunk_index)
        started = time.monotonic()

        with self._lock_for(session_id):
            existing_sha = _sha256_of_file(final) if final.exists() else None
            if existing_sha is not None:
                if existing_sha == expected_sha256:
                    return {
                        "segmentIndex": segment_index,
                        "track": track,
                        "chunkIndex": chunk_index,
                        "sizeBytes": expected_size,
                        "sha256": expected_sha256,
                        "idempotent": True,
                    }
                raise KabIngestConflict(
                    "chunk already exists with different content", code="chunk_content_conflict"
                )

            projected = self._session_usage(session_id) + expected_size
            if projected > self.max_session_bytes:
                raise KabIngestPayloadTooLarge(
                    f"session exceeds KAB_INGEST_MAX_SESSION_GB limit ({self.max_session_bytes} bytes)",
                    code="session_too_large",
                )

            final.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=f".{final.name}.", suffix=".tmp", dir=str(final.parent))
            tmp = Path(tmp_name)
            digest = hashlib.sha256()
            total = 0
            try:
                with os.fdopen(fd, "wb") as out:
                    while True:
                        if time.monotonic() - started > deadline:
                            raise KabIngestRequestTimeout("chunk body read timed out", code="body_timeout")
                        block = read(READ_BLOCK_SIZE)
                        if not block:
                            break
                        total += len(block)
                        if total > expected_size:
                            raise KabIngestValidationError(
                                "body larger than declared chunk size", code="chunk_size_mismatch"
                            )
                        digest.update(block)
                        out.write(block)
                    if total != expected_size:
                        raise KabIngestValidationError(
                            "body smaller than declared chunk size", code="chunk_size_mismatch"
                        )
                    actual_sha = digest.hexdigest()
                    if actual_sha != expected_sha256:
                        raise KabIngestValidationError(
                            "chunk body does not match X-Chunk-SHA256", code="chunk_hash_mismatch"
                        )
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(str(tmp), str(final))
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
            self._add_usage(session_id, total)

        return {
            "segmentIndex": segment_index,
            "track": track,
            "chunkIndex": chunk_index,
            "sizeBytes": total,
            "sha256": expected_sha256,
            "idempotent": False,
        }

    # ── segment completion (receiver-owned) ──────────────────────────

    def complete_segment(
        self,
        session_id: str,
        segment_index: int,
        track: str,
        *,
        total_chunks: int,
        size_bytes: int,
        sha256: str,
        extension: str,
        duration_ms: int,
        start_offset_ms: int,
    ) -> dict[str, Any]:
        """Verifies and assembles one segment track; emits the ready marker
        only once every required track of the segment is persisted."""
        validation.validate_index(segment_index, what="segmentIndex")
        validation.validate_track(track)
        session_id = validation.validate_session_id(session_id)
        paths = self.paths(session_id)
        session = self.load_session(session_id)
        required_tracks: list[str] = session["requiredTracks"]
        sha256 = validation.validate_sha256(sha256)
        extension = validation.validate_extension(track, extension)
        if total_chunks < 1 or total_chunks > validation.MAX_INDEX:
            raise KabIngestValidationError("totalChunks must be a positive integer", code="invalid_total_chunks")
        if size_bytes < 1:
            raise KabIngestValidationError("sizeBytes must be positive", code="invalid_segment_size")

        with self._lock_for(session_id):
            meta_path = paths.segment_track_meta(segment_index, track)
            existing_meta = read_json(meta_path)
            payload = {
                "totalChunks": total_chunks,
                "sizeBytes": size_bytes,
                "sha256": sha256,
                "extension": extension,
                "durationMs": duration_ms,
                "startOffsetMs": start_offset_ms,
            }
            if existing_meta is not None:
                if _segment_meta_payload(existing_meta) != payload:
                    raise KabIngestConflict(
                        "segment track already completed with different metadata",
                        code="segment_metadata_conflict",
                    )
                return self._segment_complete_summary(paths, session, segment_index, track, existing_meta)

            other_meta = self._cross_track_offset_conflict(
                paths, required_tracks, segment_index, track, start_offset_ms, duration_ms
            )
            if other_meta is not None:
                raise KabIngestConflict(
                    "segment startOffsetMs/durationMs differ between required tracks",
                    code="segment_offset_conflict",
                )

            missing = [i for i in range(total_chunks) if not paths.chunk_file(segment_index, track, i).exists()]
            if missing:
                raise KabIngestValidationError(
                    f"segment is missing {len(missing)} chunk(s)", code="missing_chunks"
                )

            final = paths.assembled_segment(segment_index, track, extension)
            final.parent.mkdir(parents=True, exist_ok=True)
            assembled_size, assembled_sha = _assemble(
                [paths.chunk_file(segment_index, track, i) for i in range(total_chunks)], final
            )
            if assembled_size != size_bytes or assembled_sha != sha256:
                final.unlink(missing_ok=True)
                if assembled_size != size_bytes:
                    raise KabIngestValidationError(
                        f"assembled size mismatch: {assembled_size} != {size_bytes}", code="segment_size_mismatch"
                    )
                raise KabIngestValidationError(
                    "assembled content does not match declared sha256", code="segment_hash_mismatch"
                )
            self._add_usage(session_id, assembled_size)

            meta = {
                "schemaVersion": validation.SCHEMA_VERSION,
                "segmentIndex": segment_index,
                "track": track,
                **payload,
                "assembledAt": now_iso(),
            }
            atomic_write_json(meta_path, meta)

            ready = self._maybe_write_ready_marker(paths, session, segment_index)
        return self._segment_complete_summary(paths, session, segment_index, track, meta, ready=ready)

    def _cross_track_offset_conflict(
        self,
        paths: SessionPaths,
        required_tracks: list[str],
        segment_index: int,
        incoming_track: str,
        start_offset_ms: int,
        duration_ms: int,
    ) -> str | None:
        for other in required_tracks:
            if other == incoming_track:
                continue
            meta = read_json(_meta_path_for(paths, other, segment_index))
            if not isinstance(meta, dict):
                continue
            if meta.get("startOffsetMs") != start_offset_ms or meta.get("durationMs") != duration_ms:
                return other
        return None

    def _maybe_write_ready_marker(self, paths: SessionPaths, session: dict[str, Any], segment_index: int) -> bool:
        required_tracks: list[str] = session["requiredTracks"]
        metas: dict[str, dict[str, Any]] = {}
        for track in required_tracks:
            meta = read_json(_meta_path_for(paths, track, segment_index))
            if not isinstance(meta, dict):
                return False
            metas[track] = meta
        offsets = {(m.get("startOffsetMs"), m.get("durationMs")) for m in metas.values()}
        if len(offsets) != 1:
            return False
        tracks_payload = {
            track: {
                "file": assembled_relative_name(segment_index, track, metas[track]["extension"]),
                "sizeBytes": metas[track]["sizeBytes"],
                "sha256": metas[track]["sha256"],
                "extension": metas[track]["extension"],
                "durationMs": metas[track]["durationMs"],
                "startOffsetMs": metas[track]["startOffsetMs"],
            }
            for track in required_tracks
        }
        marker = {
            "schemaVersion": validation.SCHEMA_VERSION,
            "segmentIndex": segment_index,
            "requiredTracks": required_tracks,
            "tracks": tracks_payload,
            "createdAt": now_iso(),
        }
        atomic_write_json(paths.ready_marker(segment_index), marker)
        return True

    def _segment_complete_summary(
        self,
        paths: SessionPaths,
        session: dict[str, Any],
        segment_index: int,
        track: str,
        meta: dict[str, Any],
        ready: bool | None = None,
    ) -> dict[str, Any]:
        if ready is None:
            ready = paths.ready_marker(segment_index).exists()
        present: list[str] = []
        for required in session["requiredTracks"]:
            if _meta_path_for(paths, required, segment_index).exists():
                present.append(required)
        missing = [t for t in session["requiredTracks"] if t not in present]
        return {
            "segmentIndex": segment_index,
            "track": track,
            "assembledTracks": present,
            "missingTracks": missing,
            "ready": ready,
            "sizeBytes": meta.get("sizeBytes"),
            "sha256": meta.get("sha256"),
        }

    # ── safe read model (GET /sessions/{id}) ─────────────────────────

    def session_state(self, session_id: str) -> dict[str, Any]:
        session_id = validation.validate_session_id(session_id)
        paths = self.paths(session_id)
        session = self.load_session(session_id)
        worker_state = read_json(paths.state_file)
        segment_states: dict[str, Any] = {}
        if isinstance(worker_state, dict):
            raw = worker_state.get("segments")
            if isinstance(raw, dict):
                segment_states = raw

        indexes: set[int] = set()
        if paths.chunks.exists():
            for child in paths.chunks.iterdir():
                if child.is_dir() and child.name.isdigit():
                    indexes.add(int(child.name))
        indexes |= _indexes_from_dir(paths.segments, ".meta.json")
        indexes |= _indexes_from_dir(paths.ready, ".ready.json")
        indexes |= {int(k) for k in segment_states if str(k).isdigit()}
        for marker_dir in (paths.ready, paths.processing, paths.failed):
            indexes |= _indexes_from_dir(marker_dir, ".json")

        segments_payload: list[dict[str, Any]] = []
        completed: list[int] = []
        failed: list[int] = []
        pending: list[int] = []
        for index in sorted(indexes):
            state_entry = segment_states.get(str(index))
            if not isinstance(state_entry, dict):
                state_entry = {}
            derived = self._derived_segment_state(paths, index, state_entry)
            if derived["state"] == "PROCESSED":
                completed.append(index)
            elif derived["state"] == "FAILED":
                failed.append(index)
            else:
                pending.append(index)
            segments_payload.append(derived)

        return {
            "schemaVersion": validation.SCHEMA_VERSION,
            "sessionId": session["sessionId"],
            "title": session["title"],
            "createdAt": session["createdAt"],
            "segmentDurationSec": session["segmentDurationSec"],
            "requiredTracks": session["requiredTracks"],
            "status": session.get("status") or "ACTIVE",
            "expectedSegmentCount": session.get("expectedSegmentCount"),
            "endedAt": session.get("endedAt"),
            "reason": session.get("reason"),
            "segments": segments_payload,
            "completedSegmentIndexes": completed,
            "pendingSegmentIndexes": pending,
            "failedSegmentIndexes": failed,
        }

    def _derived_segment_state(self, paths: SessionPaths, index: int, state_entry: dict[str, Any]) -> dict[str, Any]:
        worker_state = state_entry.get("state")
        if worker_state not in ("PROCESSING", "PROCESSED", "FAILED"):
            worker_state = "RECEIVED"
        session = read_json(paths.session_file) or {}
        required_tracks: list[str] = session.get("requiredTracks") or []
        tracks: dict[str, Any] = {}
        for track in validation.TRACKS:
            meta = read_json(_meta_path_for(paths, track, index))
            if isinstance(meta, dict):
                tracks[track] = {
                    "receivedChunkIndexes": self._received_chunk_indexes(paths, index, track),
                    "totalChunks": meta.get("totalChunks"),
                    "assembled": True,
                    "sizeBytes": meta.get("sizeBytes"),
                    "sha256": meta.get("sha256"),
                    "extension": meta.get("extension"),
                }
            elif any_chunk := self._received_chunk_indexes(paths, index, track):
                tracks[track] = {
                    "receivedChunkIndexes": any_chunk,
                    "totalChunks": None,
                    "assembled": False,
                    "sizeBytes": None,
                    "sha256": None,
                    "extension": None,
                }
        return {
            "segmentIndex": index,
            "state": worker_state,
            "errorCode": state_entry.get("errorCode"),
            "attempts": state_entry.get("attempts"),
            "ready": paths.ready_marker(index).exists(),
            "tracks": tracks,
        }

    def _received_chunk_indexes(self, paths: SessionPaths, index: int, track: str) -> list[int]:
        chunk_dir = paths.segment_chunks_dir(index, track)
        if not chunk_dir.exists():
            return []
        out = []
        for child in chunk_dir.iterdir():
            if child.is_file() and child.name.endswith(CHUNK_SUFFIX):
                stem = child.name[: -len(CHUNK_SUFFIX)]
                if stem.isdigit():
                    out.append(int(stem))
        return sorted(out)

    # ── completion verification (receiver-owned read) ────────────────

    def processed_segment_indexes(self, session_id: str) -> set[int]:
        """Segments verified as done: worker state PROCESSED plus a parseable
        persisted result (the ready marker is consumed by the claim rename)."""
        paths = self.paths(session_id)
        worker_state = read_json(paths.state_file)
        processed: set[int] = set()
        if isinstance(worker_state, dict):
            raw = worker_state.get("segments")
            if isinstance(raw, dict):
                for key, entry in raw.items():
                    if isinstance(entry, dict) and entry.get("state") == "PROCESSED" and str(key).isdigit():
                        index = int(key)
                        if paths.result_file(index).is_file():
                            processed.add(index)
        return processed

    # ── worker-facing helpers (worker-owned mutations) ───────────────

    def read_worker_state(self, session_id: str) -> dict[str, Any]:
        raw = read_json(self.paths(session_id).state_file)
        return raw if isinstance(raw, dict) else {}

    def write_worker_state(self, session_id: str, state: dict[str, Any]) -> None:
        state["updatedAt"] = now_iso()
        atomic_write_json(self.paths(session_id).state_file, state)

    def update_segment_state(
        self, session_id: str, segment_index: int, *, state: str, attempts: int, error_code: str | None = None
    ) -> None:
        current = self.read_worker_state(session_id)
        segments = current.setdefault("segments", {})
        entry = segments.get(str(segment_index)) or {}
        entry.update(
            {
                "state": state,
                "attempts": attempts,
                "updatedAt": now_iso(),
                "errorCode": error_code,
            }
        )
        segments[str(segment_index)] = entry
        current["schemaVersion"] = validation.SCHEMA_VERSION
        self.write_worker_state(session_id, current)


def _meta_path_for(paths: SessionPaths, track: str, segment_index: int) -> Path:
    return paths.segments / f"{segment_dir_name(segment_index)}.{track}.meta.json"


def assembled_relative_name(segment_index: int, track: str, extension: str) -> str:
    return f"{segment_dir_name(segment_index)}.{track}{extension}"


def _canonical_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "sessionId": payload.get("sessionId"),
        "title": payload.get("title"),
        "createdAt": payload.get("createdAt"),
        "segmentDurationSec": payload.get("segmentDurationSec"),
        "requiredTracks": payload.get("requiredTracks"),
        "schemaVersion": payload.get("schemaVersion"),
    }


def _segment_meta_payload(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "totalChunks": meta.get("totalChunks"),
        "sizeBytes": meta.get("sizeBytes"),
        "sha256": meta.get("sha256"),
        "extension": meta.get("extension"),
        "durationMs": meta.get("durationMs"),
        "startOffsetMs": meta.get("startOffsetMs"),
    }


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(READ_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def _assemble(chunk_files: list[Path], final: Path) -> tuple[int, str]:
    """Concatenates chunks in the given exact order into `final` (atomic)."""
    digest = hashlib.sha256()
    total = 0
    fd, tmp_name = tempfile.mkstemp(prefix=f".{final.name}.", suffix=".tmp", dir=str(final.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in chunk_files:
                with chunk.open("rb") as src:
                    while block := src.read(READ_BLOCK_SIZE):
                        digest.update(block)
                        out.write(block)
                        total += len(block)
            out.flush()
            os.fsync(out.fileno())
        os.replace(str(tmp), str(final))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return total, digest.hexdigest()


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _indexes_from_dir(directory: Path, suffix: str) -> set[int]:
    out: set[int] = set()
    if not directory.exists():
        return out
    for child in directory.iterdir():
        if not child.name.endswith(suffix):
            continue
        stem = child.name[: -len(suffix)]
        index = parse_segment_index(stem)
        if index is None and stem.isdigit():
            index = int(stem)
        if index is not None:
            out.add(index)
    return out
