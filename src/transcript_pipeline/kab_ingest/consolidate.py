"""Session completion consolidation for the K'ab ingest.

When a session completes, the per-segment documentation artifacts already
produced by the worker (each a DocumentationSource + ProceduralStep list
persisted in completed/segment-NNNNNN/manual/steps.json) are consolidated
into one session-level manual and AI package:

- evidence fields (instruction, transcript_ref, ocr_text,
  visual_description, confidence, evidence_source, reviewed, tags) are
  preserved verbatim — no instruction invention, no LLM call anywhere;
- timestamps shift by the segment's startOffsetMs so steps land on the
  session timeline; global order is (segment index, original step order)
  and IDs are re-issued deterministically as step-NNNN;
- frame assets are copied once into a deterministic per-session folder and
  referenced by deterministic names;
- output is written through the existing engine.write_manual() /
  engine.write_ai_package() so MANUAL.md/MANUAL.pdf/steps.json/metadata.json
  and manifest.json/steps.json/chunks.jsonl/knowledge.md/assets stay in sync
  with the rest of the product.

completed/session.complete.json records safe relative paths and plain
availability booleans. Uploaded originals are never deleted.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.engine import load_steps, write_ai_package, write_manual
from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep
from transcript_pipeline.kab_ingest.atomic import atomic_write_json
from transcript_pipeline.kab_ingest.store import SessionStore
from transcript_pipeline.kab_ingest.transcripts import (
    MANIFEST_JSON,
    SEGMENTS_JSON,
    TRANSCRIPT_TXT,
    load_results,
    session_transcripts_dir,
)

COMPLETION_FILE = "session.complete.json"
MERGED_FRAMES_DIR = "_frames"


def consolidate_session(
    store: SessionStore,
    data_root: Path,
    session_id: str,
    *,
    ended_at: str,
    reason: str | None,
) -> dict[str, Any]:
    """Consolidates a fully processed session; idempotent and deterministic."""
    session = store.load_session(session_id)
    paths = store.paths(session_id)
    results = load_results(store, session_id)

    manual_dir = paths.completed / "manual"
    ai_package_dir = paths.completed / "ai-package"
    merged_frames_dir = paths.completed / MERGED_FRAMES_DIR
    merged_frames_dir.mkdir(parents=True, exist_ok=True)

    merged_steps: list[ProceduralStep] = []
    language: str | None = None
    max_local_end = 0.0
    for result in results:
        segment_index = int(result.get("segmentIndex", -1))
        offset_sec = float(result.get("startOffsetMs", 0)) / 1000.0
        transcription = result.get("transcription") or {}
        if language is None and transcription.get("language"):
            language = str(transcription["language"])
        for entry in transcription.get("segments") or []:
            max_local_end = max(max_local_end, offset_sec + float(entry.get("end", 0.0)))
        merged_steps.extend(
            _merge_segment_steps(
                result,
                segment_index,
                offset_sec,
                merged_frames_dir,
                data_root,
            )
        )
    merged_steps.sort(key=lambda s: (s.order, s.timestamp))
    merged_steps = [
        ProceduralStep(
            id=f"step-{position:04d}",
            order=position,
            title=step.title,
            instruction=step.instruction,
            timestamp=step.timestamp,
            frame_ref=step.frame_ref,
            transcript_ref=step.transcript_ref,
            confidence=step.confidence,
            tags=step.tags,
            visual_description=step.visual_description,
            ocr_text=step.ocr_text,
            evidence_source=step.evidence_source,
            reviewed=step.reviewed,
        )
        for position, step in enumerate(merged_steps, start=1)
    ]

    source = DocumentationSource(
        video_name=session["title"],
        duration=max_local_end,
        language=language or "unknown",
        extraction_method="kab-ingest-v1",
        generated_at=ended_at,
    )

    write_manual(manual_dir, source, merged_steps, merged_frames_dir, write_steps_json=True)
    write_ai_package(ai_package_dir, source, merged_steps, merged_frames_dir)

    transcripts_dir = session_transcripts_dir(data_root, session_id)
    completion = {
        "schemaVersion": 1,
        "sessionId": session_id,
        "status": "COMPLETED",
        "endedAt": ended_at,
        "reason": reason,
        "processedSegmentCount": len(results),
        "outputs": {
            "transcript": _data_root_relative(transcripts_dir / TRANSCRIPT_TXT, data_root),
            "segmentsJson": _data_root_relative(transcripts_dir / SEGMENTS_JSON, data_root),
            "manifestJson": _data_root_relative(transcripts_dir / MANIFEST_JSON, data_root),
            "manual": "completed/manual",
            "aiPackage": "completed/ai-package",
        },
        "availability": {
            "transcript": (transcripts_dir / TRANSCRIPT_TXT).is_file(),
            "segmentsJson": (transcripts_dir / SEGMENTS_JSON).is_file(),
            "manifestJson": (transcripts_dir / MANIFEST_JSON).is_file(),
            "manual": (manual_dir / "MANUAL.md").is_file(),
            "manualPdf": (manual_dir / "MANUAL.pdf").is_file(),
            "aiPackage": (ai_package_dir / "manifest.json").is_file(),
        },
    }
    atomic_write_json(paths.completed / COMPLETION_FILE, completion)
    return completion


def _merge_segment_steps(
    result: dict[str, Any],
    segment_index: int,
    offset_sec: float,
    merged_frames_dir: Path,
    data_root: Path,
) -> list[ProceduralStep]:
    manual_dir = _segment_manual_dir(result, data_root)
    if manual_dir is None or not (manual_dir / "steps.json").is_file():
        return []
    try:
        _source, steps = load_steps(manual_dir)
    except (OSError, ValueError, KeyError):
        return []

    frames_dir = _resolve_frames_dir(result, data_root)
    merged: list[ProceduralStep] = []
    for step in steps:
        frame_ref = _copy_frame(step.frame_ref, frames_dir, segment_index, merged_frames_dir)
        merged.append(
            ProceduralStep(
                id=f"seg{segment_index:06d}-{step.id}",
                order=_order_key(segment_index, step.order, len(steps)),
                title=step.title,
                instruction=step.instruction,
                timestamp=round(step.timestamp + offset_sec, 3),
                frame_ref=frame_ref,
                transcript_ref=step.transcript_ref,
                confidence=step.confidence,
                tags=list(step.tags),
                visual_description=step.visual_description,
                ocr_text=step.ocr_text,
                evidence_source=step.evidence_source,
                reviewed=step.reviewed,
            )
        )
    return merged


def _segment_manual_dir(result: dict[str, Any], data_root: Path) -> Path | None:
    rel = result.get("docsManualDir")
    if isinstance(rel, str) and rel.strip():
        candidate = (data_root / rel).resolve(strict=False)
        if (candidate / "steps.json").is_file():
            return candidate
    return None


def _resolve_frames_dir(result: dict[str, Any], data_root: Path) -> Path | None:
    rel = result.get("framesDir")
    if isinstance(rel, str) and rel.strip():
        candidate = (data_root / rel).resolve(strict=False)
        if candidate.is_dir():
            return candidate
    return None


def _copy_frame(
    frame_ref: str | None,
    frames_dir: Path | None,
    segment_index: int,
    merged_frames_dir: Path,
) -> str | None:
    if not frame_ref or frames_dir is None:
        return None
    src = frames_dir / Path(frame_ref).name
    if not src.is_file():
        return None
    dest_name = f"seg{segment_index:06d}_{src.name}"
    dest = merged_frames_dir / dest_name
    if not dest.is_file():
        shutil.copyfile(src, dest)
    return dest_name


def _order_key(segment_index: int, step_order: int, step_count: int) -> int:
    """Global dense order: segment-major, original step order within segment."""
    return segment_index * 100000 + step_order


def _data_root_relative(path: Path, data_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(data_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.name


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
