"""Per-session transcript artifacts, regenerated atomically and
deterministically after each processed segment.

Outputs (under DATA_ROOT/CarpetaTranscripciones/kab/{sessionId}/):
- SESSION_TRANSCRIPT.txt   human-readable transcript, segments in order
- SESSION_SEGMENTS.json    machine-readable segments, sorted by
                           (sourceSegmentIndex, localStart), each with
                           provenance sourceSegmentIndex/localStart/localEnd
- SESSION_MANIFEST.json    per-segment processing manifest

Local timestamps are session timestamps: startOffsetMs/1000 plus the local
media timestamp inside the segment. Regeneration is a pure fold over the
persisted completed/segment-NNNNNN.result.json files — no transcription
re-run, no LLM, no fuzzy merging; text is quoted verbatim.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from transcript_pipeline.kab_ingest.atomic import atomic_write_json, atomic_write_text, read_json
from transcript_pipeline.kab_ingest.store import SessionStore

logger = logging.getLogger(__name__)

TRANSCRIPTS_SUBDIR = "CarpetaTranscripciones"
KAB_SUBDIR = "kab"
TRANSCRIPT_TXT = "SESSION_TRANSCRIPT.txt"
SEGMENTS_JSON = "SESSION_SEGMENTS.json"
MANIFEST_JSON = "SESSION_MANIFEST.json"


def session_transcripts_dir(data_root: Path, session_id: str) -> Path:
    return data_root / TRANSCRIPTS_SUBDIR / KAB_SUBDIR / session_id


def load_results(store: SessionStore, session_id: str) -> list[dict[str, Any]]:
    """Loads all completed/segment-NNNNNN.result.json, sorted by index."""
    completed = store.paths(session_id).completed
    results: list[dict[str, Any]] = []
    if not completed.exists():
        return results
    for child in sorted(completed.iterdir()):
        if not child.name.endswith(".result.json"):
            continue
        payload = read_json(child)
        if isinstance(payload, dict):
            results.append(payload)
    results.sort(key=lambda r: r.get("segmentIndex", -1))
    return results


def flatten_transcript_segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    """result.json transcription segments -> session-local timeline entries."""
    offset_sec = float(result.get("startOffsetMs", 0)) / 1000.0
    source_index = int(result.get("segmentIndex", -1))
    transcription = result.get("transcription") or {}
    raw_segments = transcription.get("segments") or []
    entries: list[dict[str, Any]] = []
    for seg in raw_segments:
        start = offset_sec + float(seg.get("start", 0.0))
        end = offset_sec + float(seg.get("end", 0.0))
        entries.append(
            {
                "sourceSegmentIndex": source_index,
                "localStart": round(start, 3),
                "localEnd": round(end, 3),
                "text": str(seg.get("text", "")).strip(),
            }
        )
    entries.sort(key=lambda e: (e["sourceSegmentIndex"], e["localStart"]))
    return entries


def regenerate(store: SessionStore, data_root: Path, session_id: str) -> Path:
    """Rebuilds all three transcript artifacts atomically from results."""
    session = store.load_session(session_id)
    results = load_results(store, session_id)
    entries: list[dict[str, Any]] = []
    for result in results:
        entries.extend(flatten_transcript_segments(result))
    entries.sort(key=lambda e: (e["sourceSegmentIndex"], e["localStart"]))

    out_dir = session_transcripts_dir(data_root, session_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"# K'ab Session Transcript: {session['title']}", ""]
    if not entries:
        lines.append("(no transcribed segments yet)")
        lines.append("")
    for entry in entries:
        lines.append(
            f"## [{_format_ts(entry['localStart'])} - {_format_ts(entry['localEnd'])}] "
            f"(segment {entry['sourceSegmentIndex']:06d})"
        )
        lines.append("")
        lines.append(entry["text"])
        lines.append("")
    atomic_write_text(out_dir / TRANSCRIPT_TXT, "\n".join(lines))

    language = _first_language(results)
    atomic_write_json(
        out_dir / SEGMENTS_JSON,
        {
            "schemaVersion": 1,
            "sessionId": session_id,
            "title": session["title"],
            "language": language,
            "segments": entries,
        },
    )

    atomic_write_json(
        out_dir / MANIFEST_JSON,
        {
            "schemaVersion": 1,
            "sessionId": session_id,
            "title": session["title"],
            "createdAt": session["createdAt"],
            "status": session.get("status") or "ACTIVE",
            "language": language,
            "segments": [
                {
                    "segmentIndex": int(r.get("segmentIndex", -1)),
                    "startOffsetSec": float(r.get("startOffsetMs", 0)) / 1000.0,
                    "durationMs": r.get("durationMs"),
                    "state": "PROCESSED",
                    "language": (r.get("transcription") or {}).get("language"),
                    "textLength": len((r.get("transcription") or {}).get("text") or ""),
                    "docsGenerated": bool(r.get("docsGenerated")),
                }
                for r in results
            ],
        },
    )
    logger.info("[KAB] transcripts regenerated for session %s (%d entries)", session_id, len(entries))
    return out_dir


def _first_language(results: list[dict[str, Any]]) -> str | None:
    for result in results:
        language = (result.get("transcription") or {}).get("language")
        if language:
            return str(language)
    return None


def _format_ts(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rest = divmod(total_ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
