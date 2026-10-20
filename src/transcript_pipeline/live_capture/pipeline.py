"""Bridge from finalized Live Capture chunks to the existing media pipeline (W9)."""
from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.store import CHUNKS_DIR, LIVE_CAPTURE_DIR, ManifestStore

_CHUNK_STEM_RE = re.compile(r"^chunk-(\d{6})$")


@dataclass(frozen=True)
class CaptureContext:
    """Resolved Live Capture session context for one media path (W9).

    `chunk_index` is the finalized chunk index for chunk-level resolution, or
    ``None`` for a session-level context (the whole session, no single chunk).
    Every field is a plain value object so the context is JSON-safe and can be
    compared/reused across the processor and documentation flow.
    """

    session_id: str
    chunk_index: int | None
    crop: models.CropRegion | None
    transcript: models.Transcript | None
    audio_availability: models.AudioAvailability | None
    source: str = "live_capture_manifest"
    logical_videos: tuple[dict, ...] = ()
    project_id: str | None = None

    @property
    def audio_missing(self) -> bool:
        """True only when the manifest explicitly recorded MISSING audio.

        UNKNOWN (never probed / probe failed) is *not* missing — the caller
        must still probe before deciding to skip Whisper.
        """
        return self.audio_availability is models.AudioAvailability.MISSING

    @property
    def has_loose_transcript(self) -> bool:
        """True when a late (loose, no-sync) session transcript is present."""
        return (
            self.transcript is not None
            and self.transcript.alignment == models.TRANSCRIPT_ALIGNMENT_LOOSE
        )

    def provenance(self) -> dict[str, object]:
        """JSON-safe provenance to persist into `frame_mapping.json`."""
        return {
            "source": "live_capture",
            "sessionId": self.session_id,
            "projectId": self.project_id,
            "chunkIndex": self.chunk_index,
            "crop": self.crop.to_manifest() if self.crop else None,
            "audioAvailability": self.audio_availability.value if self.audio_availability else None,
            "transcriptAlignment": self.transcript.alignment if self.transcript else None,
            "logicalVideos": [dict(item) for item in self.logical_videos],
        }


def parse_chunk_index(path: Path) -> int | None:
    match = _CHUNK_STEM_RE.match(path.stem)
    return int(match.group(1)) if match else None


def resolve_capture_context(media_path: Path, *, videos_root: Path | None = None) -> CaptureContext | None:
    """Session context for a finalized capture chunk, or None (never raises).

    Only media at `<videos_root>/live_capture/<sessionId>/chunks/chunk-NNNNNN.<ext>`
    resolves; RECORDING/FAILED chunks are not processable media, and a
    missing/malformed manifest means the caller must fall back to the
    pipeline's default (non-capture) behavior instead of failing.

    `videos_root` overrides the root derived from the media path. It is only
    a convenience for callers that already know the root; the chunk shape is
    still validated on the path itself.
    """
    try:
        path = Path(media_path)
        parts = path.parts
        if LIVE_CAPTURE_DIR not in parts:
            return None
        lc_index = parts.index(LIVE_CAPTURE_DIR)
        # Exactly <sessionId>/chunks/<file> after live_capture/, and at least
        # one segment before it to form a non-empty videos_root.
        if lc_index < 1 or lc_index + 4 != len(parts):
            return None
        if parts[lc_index + 2] != CHUNKS_DIR:
            return None
        chunk_index = parse_chunk_index(path)
        if chunk_index is None:
            return None
        session_id = parts[lc_index + 1]
        root = Path(videos_root) if videos_root is not None else Path(*parts[:lc_index])
        store = ManifestStore(root)
        session = store.load_session(session_id)
        chunk = session.get_chunk(chunk_index)
        if chunk.state in (models.ChunkState.RECORDING, models.ChunkState.FAILED):
            return None
        playlist_path = store.session_dir(session_id) / "playlist.json"
        logical_videos = ()
        if playlist_path.is_file():
            playlist = json.loads(playlist_path.read_text(encoding="utf-8"))
            chunk_id = models.chunk_id(chunk_index)
            logical_videos = tuple(
                {key: value for key, value in video.items() if key in {
                    "id", "title", "category", "sessionNumber", "recordedAt", "confidence",
                    "status", "startOffsetMs", "endOffsetMs", "processingChunkIds",
                    "projectId",
                }}
                for video in playlist.get("logicalVideos", [])
                if video.get("status") == "CONFIRMED"
                and chunk_id in _logical_processing_chunk_ids(video, playlist, session.chunk_duration_sec)
            )
        return CaptureContext(
            session_id=session_id,
            chunk_index=chunk_index,
            crop=session.crop,
            transcript=session.transcript,
            audio_availability=chunk.audio_availability,
            logical_videos=logical_videos,
            project_id=session.project_id,
        )
    except Exception:
        return None


def _logical_processing_chunk_ids(video: dict, playlist: dict, chunk_duration_sec: int) -> list[str]:
    duration_ms = max(1, int(chunk_duration_sec)) * 1000
    start = max(0, int(video.get("startOffsetMs", 0)))
    end = video.get("endOffsetMs")
    if end is None:
        end = playlist.get("currentOffsetMs", start)
    first = start // duration_ms
    last = max(first, max(0, int(end) - 1) // duration_ms)
    return [models.chunk_id(index) for index in range(first, last + 1)]
