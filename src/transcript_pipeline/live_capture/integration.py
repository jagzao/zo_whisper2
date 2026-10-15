"""W9 bridge: finalized Live Capture sessions into the EXISTING media and
Documentation V2 flow.

This module does not build a second pipeline. It resolves a session's capture
context (from the durable manifest), injects it into the already-persisted
`frame_mapping.json` (crop/audio provenance and, when a late session
transcript exists, ONE untimed loose transcript block), and hands the frames
dir to the existing Docs V2 regeneration entry point.

Two distinct transcript mechanisms exist on purpose:

- a brand-new processing run (`processor.process_file`) writes the late
  transcript as `transcription_summary.full_transcription`, so the existing
  untimed full-transcript fallback in `documentation/evidence.py` consumes it;
- a regeneration run (`regenerate_capture_documentation`) keeps it as
  `session_transcript` for provenance, and the W9 evidence block reads it.

Neither ever fabricates per-frame/second-level alignment: a loose session
transcript is a single 0..duration block (or dropped when a real timed
transcript already exists).
"""
from __future__ import annotations

import json
from pathlib import Path

from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.pipeline import (
    CaptureContext,
    resolve_capture_context,
)
from transcript_pipeline.live_capture.store import ManifestStore

__all__ = [
    "CaptureContext",
    "apply_capture_context",
    "context_from_session",
    "load_session_capture_context",
    "regenerate_capture_documentation",
    "resolve_capture_context",
]

# Status values in the `apply_capture_context` return payload.
_LOCAL_SOURCE = "live_capture_session"


def context_from_session(
    session: models.Session, *, chunk_index: int | None = None
) -> CaptureContext:
    """Builds a `CaptureContext` from a loaded session manifest.

    With `chunk_index=None` the context is session-level (audio availability
    falls back to the session's own value); with an explicit index the
    chunk's own audio availability is used.
    """
    chunk = session.get_chunk(chunk_index) if chunk_index is not None else None
    audio_availability = (
        chunk.audio_availability if chunk is not None else session.audio_availability
    )
    return CaptureContext(
        session_id=session.session_id,
        chunk_index=chunk_index,
        crop=session.crop,
        transcript=session.transcript,
        audio_availability=audio_availability,
    )


def load_session_capture_context(
    session_id: str, *, videos_root: Path | None = None
) -> CaptureContext:
    """Loads a session manifest and returns its session-level capture context.

    Typed store errors (`SessionNotFoundError`, `ManifestCorruptError`) are
    propagated: unlike `resolve_capture_context` (which is called from an
    opportunistic processor hook and must never raise), this is an explicit
    caller asking for a specific session and a missing one is a real error.
    """
    store = ManifestStore(videos_root if videos_root is not None else _default_videos_root())
    session = store.load_session(session_id)
    return context_from_session(session)


def _default_videos_root() -> Path:
    from transcript_pipeline.config import VIDEOS_DIR

    return VIDEOS_DIR


def _has_timed_transcript(mapping: dict, summary: dict) -> bool:
    """True when a real (Whisper/segment) transcript is already persisted.

    Guards the loose session transcript from ever overwriting timed text:
    any non-empty `full_transcription`, any non-empty frame-mapped
    `full_text`, or any mapped segment counts as timed evidence.
    """
    if str(summary.get("full_transcription") or "").strip():
        return True
    existing_session = summary.get("session_transcript")
    if isinstance(existing_session, dict) and str(existing_session.get("text") or "").strip():
        return True
    for entry in (mapping.get("transcription_mapping") or {}).values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("full_text") or "").strip():
            return True
        if entry.get("transcription_segments"):
            return True
    return False


def apply_capture_context(mapping: dict, context: CaptureContext) -> dict:
    """Injects capture provenance (and a loose transcript) into a mapping.

    Always records `video_info.capture` (session, crop, availability,
    alignment). When the context carries a late session transcript and the
    mapping has no timed transcript yet, the text becomes the untimed
    `full_transcription` with explicit `alignment="loose"` and
    `source="live_capture_session"` — never per-frame segments. Idempotent:
    re-applying to an already-enriched mapping is a no-op.
    """
    video_info = mapping.setdefault("video_info", {})
    video_info["capture"] = context.provenance()

    summary = mapping.setdefault("transcription_summary", {})
    summary.setdefault("language", "unknown")

    status: dict[str, object] = {
        "sessionId": context.session_id,
        "chunkIndex": context.chunk_index,
        "audioMissing": context.audio_missing,
        "transcriptApplied": False,
        "alignment": None,
    }

    transcript = context.transcript
    if transcript is None or _has_timed_transcript(mapping, summary):
        return status

    summary["full_transcription"] = transcript.text
    summary["language"] = transcript.language or summary.get("language") or "unknown"
    summary["alignment"] = models.TRANSCRIPT_ALIGNMENT_LOOSE
    summary["source"] = _LOCAL_SOURCE
    status["transcriptApplied"] = True
    status["alignment"] = models.TRANSCRIPT_ALIGNMENT_LOOSE
    return status


def regenerate_capture_documentation(
    frames_dir: Path,
    session_id: str,
    *,
    videos_root: Path | None = None,
    evidence_only: bool = False,
    **kwargs,
) -> dict:
    """Re-runs Docs V2 over a processed capture frames dir with its session
    transcript applied first.

    Loads the session context, patches `frame_mapping.json` in place, and
    delegates to the existing deterministic regeneration entry point (no
    upstream transcription/FFmpeg/OCR/vision). The returned dict is the
    regeneration result plus a `capture` status (see `apply_capture_context`).
    """
    from transcript_pipeline.documentation.regenerate_v2 import regenerate_documentation_v2

    frames_dir = Path(frames_dir)
    context = load_session_capture_context(session_id, videos_root=videos_root)

    mapping_path = frames_dir / "frame_mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    status = apply_capture_context(mapping, context)
    mapping_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")

    result = regenerate_documentation_v2(frames_dir, evidence_only=evidence_only, **kwargs)
    result["capture"] = status
    return result
