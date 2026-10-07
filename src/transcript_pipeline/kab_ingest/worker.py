"""Local, single-machine worker for the K'ab ingest.

The worker scans every session's ready/ markers, claims them by atomic
rename into processing/, muxes video+external-audio when both tracks are
required (FFmpeg argv array, fail closed), transcribes the resulting media
with the existing local SimpleScanProcessor (local Whisper, language
detection, keyframes, privacy-guarded docs), and writes per-segment results
under completed/. After each segment it atomically regenerates the session
transcripts, so processing stays incremental while later segments upload.

Crash/restart semantics:
- a PROCESSED segment is never processed twice;
- a stale processing/ marker (crash mid-processing) is retried exactly once
  on restart; a second failure marks the segment FAILED permanently — no
  infinite retry loop;
- a segment whose required tracks are all assembled but whose ready marker
  is missing (crash between marker writes) is reconciled back into ready/.

Everything is local: no queue, no remote database, no network access.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from transcript_pipeline.kab_ingest import transcripts
from transcript_pipeline.kab_ingest.atomic import atomic_write_json, read_json
from transcript_pipeline.kab_ingest.mux import MuxError, mux_video_with_external_audio
from transcript_pipeline.kab_ingest.store import (
    SessionStore,
    parse_segment_index,
)

logger = logging.getLogger(__name__)

MAX_PROCESSING_ATTEMPTS = 2
TranscribeFn = Callable[[Path], dict]


class WhisperBridge:
    """Lazy default transcription backend: the existing local processor.

    `SimpleScanProcessor` (faster-whisper, language detection, keyframes)
    is imported and instantiated only when the first segment is actually
    processed, so importing/starting the worker never requires the ML stack.
    """

    def __init__(self) -> None:
        self._processor: Any = None

    def __call__(self, media_path: Path) -> dict:
        if self._processor is None:
            from transcript_pipeline.transcription.processor import SimpleScanProcessor

            self._processor = SimpleScanProcessor()
        return self._processor.transcribe_file(media_path)


class KabIngestWorker:
    def __init__(
        self,
        store: SessionStore,
        data_root: Path,
        *,
        transcribe: TranscribeFn | None = None,
        poll_seconds: float = 5.0,
    ):
        self.store = store
        self.data_root = data_root.resolve(strict=False)
        self._transcribe = transcribe or WhisperBridge()
        self.poll_seconds = poll_seconds

    # ── scheduling ───────────────────────────────────────────────────

    def run_once(self) -> int:
        """One scan pass over all sessions; returns segments finished (any state)."""
        finished = 0
        for session_id in self._session_ids():
            self.reconcile_session(session_id)
            finished += self._recover_stale(session_id)
            finished += self._drain_ready(session_id)
        return finished

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("[KAB-WORKER] scan pass failed; continuing")
            time.sleep(self.poll_seconds)

    def _session_ids(self) -> list[str]:
        if not self.store.root.exists():
            return []
        out = []
        for child in sorted(self.store.root.iterdir()):
            if child.is_dir() and (child / "session.json").is_file():
                out.append(child.name)
        return out

    # ── reconciliation / recovery ────────────────────────────────────

    def reconcile_session(self, session_id: str) -> None:
        """Recreates missing ready markers for fully-assembled segments."""
        session = self.store.load_session(session_id)
        paths = self.store.paths(session_id)
        required_tracks: list[str] = session["requiredTracks"]
        if not paths.segments.exists():
            return
        indexes = set()
        for child in paths.segments.iterdir():
            if child.name.endswith(".meta.json"):
                stem = child.name[: -len(".meta.json")]
                if stem.startswith("segment-"):
                    base = stem.split(".", 1)[0]
                    index = parse_segment_index(base)
                    if index is not None:
                        indexes.add(index)
        state = self.store.read_worker_state(session_id)
        for index in sorted(indexes):
            if paths.ready_marker(index).exists() or paths.processing_marker(index).exists():
                continue
            entry = (state.get("segments") or {}).get(str(index))
            if isinstance(entry, dict) and entry.get("state") in ("PROCESSED", "PROCESSING", "FAILED"):
                continue
            metas = [read_json(_meta_path(paths, track, index)) for track in required_tracks]
            if not all(isinstance(m, dict) for m in metas):
                continue
            offsets = {(m.get("startOffsetMs"), m.get("durationMs")) for m in metas if isinstance(m, dict)}
            if len(offsets) != 1:
                continue
            self._emit_ready_marker(session_id, index, session, {t: m for t, m in zip(required_tracks, metas) if m})
            logger.info("[KAB-WORKER] reconciled ready marker for %s segment %06d", session_id, index)

    def _recover_stale(self, session_id: str) -> int:
        """Stale PROCESSING markers retry once, then FAIL permanently."""
        paths = self.store.paths(session_id)
        if not paths.processing.exists():
            return 0
        finished = 0
        for marker in sorted(paths.processing.glob("segment-*.processing.json")):
            payload = read_json(marker)
            if not isinstance(payload, dict):
                continue
            index = int(payload.get("segmentIndex", -1))
            if index < 0:
                continue
            entry = (self.store.read_worker_state(session_id).get("segments") or {}).get(str(index))
            if isinstance(entry, dict) and entry.get("state") == "PROCESSED":
                marker.unlink(missing_ok=True)
                continue
            attempts = int(payload.get("attempts", 1) or 1)
            if attempts >= MAX_PROCESSING_ATTEMPTS:
                self._mark_failed(session_id, index, attempts, "stale_processing_exhausted", marker)
                finished += 1
                continue
            payload["attempts"] = attempts + 1
            atomic_write_json(marker, payload)
            logger.warning(
                "[KAB-WORKER] retrying stale PROCESSING segment %06d of %s (attempt %d)",
                index, session_id, attempts + 1,
            )
            self._process(session_id, index, payload, attempts + 1, marker)
            finished += 1
        return finished

    # ── main processing ──────────────────────────────────────────────

    def _drain_ready(self, session_id: str) -> int:
        paths = self.store.paths(session_id)
        if not paths.ready.exists():
            return 0
        finished = 0
        for marker in sorted(paths.ready.glob("segment-*.ready.json")):
            state = self.store.read_worker_state(session_id)
            payload = read_json(marker)
            if not isinstance(payload, dict):
                continue
            index = int(payload.get("segmentIndex", -1))
            if index < 0:
                continue
            entry = (state.get("segments") or {}).get(str(index))
            if isinstance(entry, dict) and entry.get("state") == "PROCESSED":
                marker.unlink(missing_ok=True)
                continue
            claimed = self._claim(session_id, index, payload)
            if not claimed:
                continue
            attempts = int(claimed.get("attempts", 1) or 1)
            self._process(session_id, index, claimed, attempts, self.store.paths(session_id).processing_marker(index))
            finished += 1
        return finished

    def _claim(self, session_id: str, index: int, ready_payload: dict) -> dict | None:
        """ready/ -> processing/ by atomic rename; writes attempt count."""
        paths = self.store.paths(session_id)
        source = paths.ready_marker(index)
        target = paths.processing_marker(index)
        if not source.exists() or target.exists():
            return None
        try:
            source.rename(target)
        except OSError:
            return None
        payload = dict(ready_payload)
        payload["attempts"] = 1
        payload["claimedAt"] = _now()
        atomic_write_json(target, payload)
        self.store.update_segment_state(session_id, index, state="PROCESSING", attempts=1)
        return payload

    def _process(
        self,
        session_id: str,
        index: int,
        payload: dict,
        attempts: int,
        marker_path: Path,
    ) -> None:
        paths = self.store.paths(session_id)
        try:
            media_path, media_kind = self._prepare_media(session_id, index, payload)
            session = self.store.load_session(session_id)
            transcription = self._transcribe(media_path)
            result = self._build_result(
                session_id, session, index, payload, media_path, media_kind, transcription, attempts
            )
            atomic_write_json(paths.result_file(index), result)
            self.store.update_segment_state(session_id, index, state="PROCESSED", attempts=attempts)
            marker_path.unlink(missing_ok=True)
            transcripts.regenerate(self.store, self.data_root, session_id)
            logger.info("[KAB-WORKER] processed %s segment %06d", session_id, index)
        except Exception as exc:
            logger.error("[KAB-WORKER] segment %06d of %s failed: %s", index, session_id, type(exc).__name__)
            self._mark_failed(session_id, index, attempts, "processing_failed", marker_path)
            transcripts.regenerate(self.store, self.data_root, session_id)

    def _prepare_media(self, session_id: str, index: int, payload: dict) -> tuple[Path, str]:
        tracks: dict[str, dict] = payload.get("tracks") or {}
        paths = self.store.paths(session_id)
        video = tracks.get("video")
        audio = tracks.get("audio")
        if video and audio:
            video_file = paths.segments / str(video["file"])
            audio_file = paths.segments / str(audio["file"])
            out_ext = str(video.get("extension", ".mp4"))
            out = paths.completed / f"segment-{index:06d}{out_ext}"
            mux_video_with_external_audio(video_file, audio_file, out)
            return out, "muxed"
        if video:
            return paths.segments / str(video["file"]), "video"
        if audio:
            return paths.segments / str(audio["file"]), "audio"
        raise MuxError("segment ready marker has no usable track")

    def _build_result(
        self,
        session_id: str,
        session: dict,
        index: int,
        payload: dict,
        media_path: Path,
        media_kind: str,
        transcription: dict,
        attempts: int,
    ) -> dict:
        paths = self.store.paths(session_id)
        tracks: dict[str, dict] = payload.get("tracks") or {}
        first_track = "video" if "video" in tracks else "audio"
        first_meta = tracks.get(first_track) or {}
        start_offset_ms = int(first_meta.get("startOffsetMs", 0) or 0)
        duration_ms = int(first_meta.get("durationMs", 0) or 0)

        clean_segments = [
            {
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": str(seg.get("text", "")),
            }
            for seg in (transcription.get("segments") or [])
        ]

        docs_generated = False
        docs_manual_dir: str | None = None
        frames_dir_rel: str | None = None
        frame_info = transcription.get("frame_info")
        if isinstance(frame_info, dict) and frame_info.get("frames_dir"):
            docs_generated, docs_manual_dir, frames_dir_rel = self._generate_docs(
                session, index, Path(str(frame_info["frames_dir"]))
            )

        return {
            "schemaVersion": 1,
            "sessionId": session_id,
            "segmentIndex": index,
            "processedAt": _now(),
            "attempts": attempts,
            "startOffsetMs": start_offset_ms,
            "durationMs": duration_ms,
            "media": {
                "kind": media_kind,
                "file": media_path.relative_to(paths.base).as_posix(),
            },
            "transcription": {
                "text": str(transcription.get("text", "")),
                "language": transcription.get("language"),
                "durationSec": float(transcription.get("duration", 0.0) or 0.0),
                "segments": clean_segments,
            },
            "docsGenerated": docs_generated,
            "docsManualDir": docs_manual_dir,
            "framesDir": frames_dir_rel,
        }

    def _generate_docs(self, session: dict, index: int, frames_dir: Path) -> tuple[bool, str | None, str | None]:
        """Per-segment manual + AI package via the existing engine (privacy-gated)."""
        if not frames_dir.is_dir() or not (frames_dir / "frame_mapping.json").is_file():
            return False, None, None
        try:
            from transcript_pipeline.documentation.engine import generate_documentation

            session_id = str(session["sessionId"])
            paths = self.store.paths(session_id)
            manual_dir = paths.completed / f"segment-{index:06d}" / "manual"
            ai_package_dir = paths.completed / f"segment-{index:06d}" / "ai-package"
            generate_documentation(
                frames_dir,
                f"{session['title']} - segment {index:06d}",
                manual_dir=manual_dir,
                ai_package_dir=ai_package_dir,
                project_config=None,
            )
            frames_rel = _relative_to_data_root(frames_dir, self.data_root)
            manual_rel = _relative_to_data_root(manual_dir, self.data_root)
            return True, manual_rel, frames_rel
        except Exception as exc:
            logger.warning("[KAB-WORKER] docs generation skipped for segment %06d: %s", index, type(exc).__name__)
            return False, None, None

    def _mark_failed(
        self, session_id: str, index: int, attempts: int, error_code: str, marker_path: Path
    ) -> None:
        self.store.update_segment_state(
            session_id, index, state="FAILED", attempts=attempts, error_code=error_code
        )
        paths = self.store.paths(session_id)
        failed_marker = paths.failed_marker(index)
        failed_marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            failed_marker,
            {
                "schemaVersion": 1,
                "segmentIndex": index,
                "attempts": attempts,
                "errorCode": error_code,
                "failedAt": _now(),
            },
        )
        marker_path.unlink(missing_ok=True)
        logger.error("[KAB-WORKER] segment %06d of %s marked FAILED (%s)", index, session_id, error_code)

    def _emit_ready_marker(self, session_id: str, index: int, session: dict, metas: dict[str, dict]) -> None:
        paths = self.store.paths(session_id)
        tracks_payload = {
            track: {
                "file": f"segment-{index:06d}.{track}{meta['extension']}",
                "sizeBytes": meta["sizeBytes"],
                "sha256": meta["sha256"],
                "extension": meta["extension"],
                "durationMs": meta["durationMs"],
                "startOffsetMs": meta["startOffsetMs"],
            }
            for track, meta in metas.items()
        }
        atomic_write_json(
            paths.ready_marker(index),
            {
                "schemaVersion": 1,
                "segmentIndex": index,
                "requiredTracks": session["requiredTracks"],
                "tracks": tracks_payload,
                "createdAt": _now(),
                "reconciled": True,
            },
        )


def _meta_path(paths: Any, track: str, index: int) -> Path:
    return paths.segments / f"segment-{index:06d}.{track}.meta.json"


def _relative_to_data_root(path: Path, data_root: Path) -> str | None:
    try:
        return path.resolve(strict=False).relative_to(data_root.resolve(strict=False)).as_posix()
    except ValueError:
        return None


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
