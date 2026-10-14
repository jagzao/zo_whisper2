from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request

from transcript_pipeline.capture.models import (
    ROI,
    CaptureConfig,
    CaptureSegment,
    SegmentStatus,
    SessionStatus,
    utc_now,
)
from transcript_pipeline.capture.service import CaptureService
from transcript_pipeline.capture.store import CaptureStore
from transcript_pipeline.media.utils import run_ffprobe

MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_SESSION_SECONDS = 6 * 60 * 60


def create_capture_blueprint(store: CaptureStore | None = None) -> Blueprint:
    blueprint = Blueprint("capture_api", __name__)
    capture_store = store or CaptureStore()
    service = CaptureService(capture_store)

    @blueprint.post("/api/capture/sessions")
    def create_session():
        data = request.get_json(silent=True) or {}
        try:
            config_data = dict(data.get("captureConfig") or {})
            if isinstance(config_data.get("roi"), dict):
                config_data["roi"] = ROI(**config_data["roi"])
            session = service.create_session(
                str(data.get("title", "")), data.get("projectName"), CaptureConfig(**config_data)
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "session": session.to_dict()}), 201

    @blueprint.get("/api/capture/sessions")
    def list_sessions():
        return jsonify({"ok": True, "sessions": [session.to_dict() for session in capture_store.list_sessions()]})

    @blueprint.get("/api/capture/sessions/<session_id>")
    def get_session(session_id: str):
        try:
            session = capture_store.get_session(session_id)
        except (ValueError, OSError, json.JSONDecodeError):
            return jsonify({"ok": False, "error": "session not found"}), 404
        segments = [segment.to_dict() for segment in capture_store.list_segments(session_id)]
        return jsonify({"ok": True, "session": session.to_dict(), "segments": segments})

    @blueprint.post("/api/capture/sessions/<session_id>/start")
    def start_session(session_id: str):
        try:
            session = capture_store.get_session(session_id)
            if session.status not in {SessionStatus.CREATED, SessionStatus.PAUSED, SessionStatus.RECOVERABLE}:
                return jsonify({"ok": False, "error": "session cannot start from current state"}), 409
            if session.totalRecordedSeconds >= MAX_SESSION_SECONDS:
                return jsonify({"ok": False, "error": "session duration limit reached"}), 409
            segments = capture_store.list_segments(session_id)
            sequence = max((segment.sequence for segment in segments), default=0) + 1
            segment = CaptureSegment(
                sessionId=session_id,
                sequence=sequence,
                startOffsetSeconds=session.totalRecordedSeconds,
                expectedDurationSeconds=session.captureConfig.logicalSegmentSeconds,
            )
            capture_store.save_segment(segment)
            service.transition(session_id, SessionStatus.RECORDING)
            return jsonify({"ok": True, "segment": segment.to_dict()}), 201
        except (ValueError, OSError, json.JSONDecodeError):
            return jsonify({"ok": False, "error": "session not found or invalid"}), 404

    @blueprint.put("/api/capture/sessions/<session_id>/segments/<int:sequence>/chunks/<int:chunk_index>")
    def upload_chunk(session_id: str, sequence: int, chunk_index: int):
        if sequence < 1 or sequence > MAX_SESSION_SECONDS // 300 or chunk_index < 0 or chunk_index >= 10000:
            return jsonify({"ok": False, "error": "invalid chunk coordinates"}), 400
        if request.content_length is not None and request.content_length > MAX_CHUNK_BYTES:
            return jsonify({"ok": False, "error": "chunk too large"}), 413
        content = request.stream.read(MAX_CHUNK_BYTES + 1)
        if not content or len(content) > MAX_CHUNK_BYTES:
            return jsonify({"ok": False, "error": "chunk size outside allowed bounds"}), 413
        try:
            session = capture_store.get_session(session_id)
            segment = capture_store.get_segment(session_id, sequence)
            if session.status is not SessionStatus.RECORDING or segment.status is not SegmentStatus.RECEIVING:
                return jsonify({"ok": False, "error": "segment is not receiving"}), 409
            chunk_dir = capture_store.session_root(session_id) / "segments" / f"{sequence:06d}" / "chunks"
            chunk_dir.mkdir(parents=True, exist_ok=True)
            chunk_path = chunk_dir / f"{chunk_index:06d}.part"
            content_hash = hashlib.sha256(content).hexdigest()
            try:
                _create_chunk(chunk_path, content)
            except FileExistsError:
                existing_hash = hashlib.sha256(chunk_path.read_bytes()).hexdigest()
                if existing_hash != content_hash:
                    return jsonify({"ok": False, "error": "chunk index already contains different bytes"}), 409
                return jsonify({"ok": True, "chunkIndex": chunk_index, "contentHash": content_hash, "idempotent": True})
            segment.receivedChunkCount += 1
            segment.receivedBytes += len(content)
            session.totalReceivedBytes += len(content)
            segment.mimeType = request.headers.get("Content-Type", "application/octet-stream")[:120]
            capture_store.save_segment(segment)
            capture_store.save_session(session)
            return jsonify({"ok": True, "chunkIndex": chunk_index, "contentHash": content_hash, "idempotent": False})
        except (ValueError, OSError, json.JSONDecodeError):
            return jsonify({"ok": False, "error": "session or segment not found"}), 404

    @blueprint.post("/api/capture/sessions/<session_id>/segments/<int:sequence>/seal")
    def seal_segment(session_id: str, sequence: int):
        data = request.get_json(silent=True) or {}
        try:
            session = capture_store.get_session(session_id)
            segment = capture_store.get_segment(session_id, sequence)
            if segment.status in {SegmentStatus.SEALED, SegmentStatus.QUEUED, SegmentStatus.PROCESSING, SegmentStatus.PROCESSED}:
                return jsonify({"ok": True, "segment": segment.to_dict(), "idempotent": True})
            count = data.get("expectedChunkCount")
            duration = float(data.get("recordedDurationSeconds", 0))
            if not isinstance(count, int) or count < 1 or count > 10000 or duration <= 0:
                return jsonify({"ok": False, "error": "invalid seal metadata"}), 400
            if duration > session.captureConfig.logicalSegmentSeconds + 2 or segment.startOffsetSeconds + duration > MAX_SESSION_SECONDS:
                return jsonify({"ok": False, "error": "session duration limit exceeded"}), 413
            root = capture_store.session_root(session_id)
            chunk_dir = root / "segments" / f"{sequence:06d}" / "chunks"
            chunks = [chunk_dir / f"{index:06d}.part" for index in range(count)]
            actual_chunks = set(chunk_dir.glob("*.part"))
            if not all(path.is_file() for path in chunks) or actual_chunks != set(chunks):
                return jsonify({"ok": False, "error": "segment has missing chunks"}), 409
            media_path = root / "segments" / f"{sequence:06d}" / "media.webm"
            descriptor, temporary = tempfile.mkstemp(prefix=".media-", suffix=".tmp", dir=media_path.parent)
            digest = hashlib.sha256()
            try:
                with os.fdopen(descriptor, "wb") as output:
                    for chunk in chunks:
                        with chunk.open("rb") as stream:
                            while data_chunk := stream.read(1024 * 1024):
                                output.write(data_chunk)
                                digest.update(data_chunk)
                    output.flush()
                    os.fsync(output.fileno())
                _validate_media(Path(temporary))
                os.replace(temporary, media_path)
            except Exception:
                Path(temporary).unlink(missing_ok=True)
                raise
            segment.status = SegmentStatus.QUEUED
            segment.expectedChunkCount = count
            segment.actualDurationSeconds = duration
            segment.mimeType = str(data.get("mimeType", segment.mimeType or "application/octet-stream"))[:120]
            segment.mediaRelativePath = media_path.relative_to(root).as_posix()
            segment.contentHash = digest.hexdigest()
            segment.receivedChunkCount = count
            capture_store.save_segment(segment)
            session.totalRecordedSeconds += duration
            session.segmentCount = max(session.segmentCount, sequence)
            session.updatedAt = utc_now()
            capture_store.save_session(session)
            return jsonify({"ok": True, "segment": segment.to_dict(), "idempotent": False})
        except (ValueError, OSError, json.JSONDecodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return jsonify({"ok": False, "error": f"media validation or seal failed: {type(exc).__name__}"}), 422

    @blueprint.post("/api/capture/sessions/<session_id>/pause")
    def pause_session(session_id: str):
        try:
            session = capture_store.get_session(session_id)
            if session.status is not SessionStatus.RECORDING:
                return jsonify({"ok": False, "error": "session is not recording"}), 409
            if any(segment.status is SegmentStatus.RECEIVING for segment in capture_store.list_segments(session_id)):
                return jsonify({"ok": False, "error": "seal current segment before pausing"}), 409
            session = service.transition(session_id, SessionStatus.PAUSED)
            return jsonify({"ok": True, "session": session.to_dict()})
        except (ValueError, OSError, json.JSONDecodeError):
            return jsonify({"ok": False, "error": "session not found"}), 404

    @blueprint.post("/api/capture/sessions/<session_id>/stop")
    def stop_session(session_id: str):
        try:
            session = capture_store.get_session(session_id)
            if session.status not in {SessionStatus.RECORDING, SessionStatus.PAUSED}:
                return jsonify({"ok": False, "error": "session cannot stop from current state"}), 409
            if any(segment.status is SegmentStatus.RECEIVING for segment in capture_store.list_segments(session_id)):
                return jsonify({"ok": False, "error": "seal current segment before stopping"}), 409
            session = service.transition(session_id, SessionStatus.STOPPED)
            return jsonify({"ok": True, "session": session.to_dict()})
        except (ValueError, OSError, json.JSONDecodeError):
            return jsonify({"ok": False, "error": "session not found"}), 404

    return blueprint


def _atomic_bytes(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _create_chunk(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _validate_media(path: Path) -> dict:
    result = run_ffprobe(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        retry_on_timeout=False,
    )
    data = json.loads(result.stdout)
    if not any(stream.get("codec_type") in {"audio", "video"} for stream in data.get("streams", [])):
        raise ValueError("media contains no audio or video stream")
    return data
