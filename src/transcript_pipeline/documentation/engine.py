"""Builds the human manual and AI-ready knowledge package from a tutorial
video's persisted `frame_mapping.json`.

Design constraint (US-001 §4.7 — confidence and hallucination control): step
`instruction` text is always the transcript excerpt already stored in
`frame_mapping.json["transcription_mapping"]` by
`processor._integrate_transcription_with_frames` — this module never calls
an LLM and never invents wording. A frame with no nearby transcript gets
`confidence="low"` instead of a guessed instruction, so it's clearly flagged
for human review (see §4.8) rather than silently presented as fact.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep

SCHEMA_VERSION = "1.0"


def build_steps(mapping_data: dict) -> list[ProceduralStep]:
    """Turns `frame_mapping.json`'s frames + transcription_mapping into
    grounded, ordered ProceduralStep objects."""
    frames = sorted(mapping_data.get("frames", []), key=lambda f: f["timestamp"])
    transcription_mapping = mapping_data.get("transcription_mapping", {})

    steps: list[ProceduralStep] = []
    for order, frame in enumerate(frames, start=1):
        frame_file = frame["frame_file"]
        transcript_entry = transcription_mapping.get(frame_file, {})
        transcript_text = (transcript_entry.get("full_text") or "").strip()

        if transcript_text:
            instruction = transcript_text
            confidence = "high"
        else:
            instruction = "(no transcript captured near this moment — review evidence before trusting this step)"
            confidence = "low"

        title = _shorten(transcript_text) if transcript_text else f"Step at {frame['timestamp_formatted']}"

        steps.append(ProceduralStep(
            id=f"step-{order:04d}",
            order=order,
            title=title,
            instruction=instruction,
            timestamp=frame["timestamp"],
            frame_ref=frame_file,
            transcript_ref=transcript_text,
            confidence=confidence,
        ))

    return steps


def _shorten(text: str, max_len: int = 70) -> str:
    text = text.strip()
    return text if len(text) <= max_len else text[:max_len].rsplit(" ", 1)[0] + "…"


def generate_documentation(
    frames_dir: Path,
    video_name: str,
    manual_dir: Path | None = None,
    ai_package_dir: Path | None = None,
) -> dict:
    """Reads `frames_dir/frame_mapping.json` and writes MANUAL.md + the
    AI-ready package next to it. Returns a small summary dict.

    Safe to call again later purely from the persisted `steps.json` via
    `regenerate_from_steps` — this function is the only one that re-derives
    steps from frame_mapping.json (i.e. it's the only path that would need
    re-transcription-adjacent data).
    """
    mapping_path = frames_dir / "frame_mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(f"frame_mapping.json not found in {frames_dir}")

    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    video_info = mapping_data.get("video_info", {})
    transcription_summary = mapping_data.get("transcription_summary", {})

    steps = build_steps(mapping_data)

    source = DocumentationSource(
        video_name=video_name,
        duration=video_info.get("duration", 0.0),
        language=transcription_summary.get("language", "unknown"),
        extraction_method=video_info.get("extraction_method", "unknown"),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    manual_dir = manual_dir or (frames_dir / "manual")
    ai_package_dir = ai_package_dir or (frames_dir / "ai-package")

    _write_steps_json(manual_dir, steps)  # editable source of truth for regeneration
    write_manual(manual_dir, source, steps, frames_dir)
    write_ai_package(ai_package_dir, source, steps, frames_dir)

    return {
        "manual_dir": str(manual_dir),
        "ai_package_dir": str(ai_package_dir),
        "step_count": len(steps),
        "low_confidence_count": sum(1 for s in steps if s.confidence == "low"),
    }


def regenerate_from_steps(manual_dir: Path, ai_package_dir: Path, frames_dir: Path, video_name: str) -> dict:
    """Rebuilds MANUAL.md / knowledge package from a (possibly human-edited)
    `steps.json` without touching frame_mapping.json or re-transcribing."""
    steps_path = manual_dir / "steps.json"
    payload = json.loads(steps_path.read_text(encoding="utf-8"))
    steps = [
        ProceduralStep(
            id=s["id"], order=s["order"], title=s["title"], instruction=s["instruction"],
            timestamp=s["timestamp"], frame_ref=s.get("frame_ref"), transcript_ref=s.get("transcript_ref", ""),
            confidence=s.get("confidence", "low"), tags=s.get("tags", []),
            visual_description=s.get("visual_description"),
        )
        for s in payload["steps"]
    ]
    source = DocumentationSource(
        video_name=video_name,
        duration=payload.get("source", {}).get("duration", 0.0),
        language=payload.get("source", {}).get("language", "unknown"),
        extraction_method=payload.get("source", {}).get("extraction_method", "unknown"),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    write_manual(manual_dir, source, steps, frames_dir, write_steps_json=False)
    write_ai_package(ai_package_dir, source, steps, frames_dir)
    return {"step_count": len(steps)}


def _write_steps_json(manual_dir: Path, steps: list[ProceduralStep]) -> None:
    manual_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": SCHEMA_VERSION, "steps": [s.to_dict() for s in steps]}
    (manual_dir / "steps.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_manual(
    manual_dir: Path,
    source: DocumentationSource,
    steps: list[ProceduralStep],
    frames_dir: Path,
    write_steps_json: bool = True,
) -> None:
    assets_dir = manual_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"# {source.video_name}\n\n"]
    review_count = sum(1 for s in steps if s.confidence == "low")
    if review_count:
        lines.append(
            f"> ⚠ {review_count} of {len(steps)} step(s) below have no transcript evidence and are "
            "marked `confidence: low` — review before treating them as accurate.\n\n"
        )

    for step in steps:
        lines.append(f"## {step.order}. {step.title}\n\n")
        lines.append(f"`{_format_ts(step.timestamp)}` — confidence: **{step.confidence}**\n\n")

        asset_name = _copy_frame_asset(frames_dir, assets_dir, step)
        if asset_name:
            lines.append(f"![{step.id}](assets/{asset_name})\n\n")

        lines.append(f"{step.instruction}\n\n")

    (manual_dir / "MANUAL.md").write_text("".join(lines), encoding="utf-8")

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "video_name": source.video_name,
        "duration": source.duration,
        "language": source.language,
        "extraction_method": source.extraction_method,
        "generated_at": source.generated_at,
        "step_count": len(steps),
    }
    (manual_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    if write_steps_json:
        _write_steps_json(manual_dir, steps)


def write_ai_package(
    ai_package_dir: Path,
    source: DocumentationSource,
    steps: list[ProceduralStep],
    frames_dir: Path,
) -> None:
    assets_dir = ai_package_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "video_name": source.video_name,
            "duration": source.duration,
            "language": source.language,
            "extraction_method": source.extraction_method,
        },
        "procedures": [{"id": s.id, "order": s.order, "title": s.title, "confidence": s.confidence} for s in steps],
        "artifacts": [],
        "generated_at": source.generated_at,
    }

    steps_payload = {"schema_version": SCHEMA_VERSION, "steps": []}
    chunks_lines = []
    knowledge_lines = [f"# {source.video_name} — AI knowledge package\n\n"]

    for step in steps:
        asset_name = _copy_frame_asset(frames_dir, assets_dir, step)
        if asset_name:
            manifest["artifacts"].append(f"assets/{asset_name}")

        step_dict = step.to_dict()
        step_dict["frame_ref"] = f"assets/{asset_name}" if asset_name else None
        steps_payload["steps"].append(step_dict)

        chunk_text = f"{step.title}\n{step.instruction}"
        chunks_lines.append(json.dumps({
            "id": step.id,
            "text": chunk_text,
            "metadata": {
                "order": step.order,
                "timestamp": step.timestamp,
                "confidence": step.confidence,
                "source_video": source.video_name,
            },
        }, ensure_ascii=False))

        knowledge_lines.append(f"## {step.order}. {step.title}\n\n{step.instruction}\n\n")

    (ai_package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (ai_package_dir / "steps.json").write_text(json.dumps(steps_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (ai_package_dir / "chunks.jsonl").write_text("\n".join(chunks_lines) + ("\n" if chunks_lines else ""), encoding="utf-8")
    (ai_package_dir / "knowledge.md").write_text("".join(knowledge_lines), encoding="utf-8")


def _copy_frame_asset(frames_dir: Path, assets_dir: Path, step: ProceduralStep) -> str | None:
    if not step.frame_ref:
        return None
    src = frames_dir / step.frame_ref
    if not src.exists():
        return None
    dest_name = f"{step.id}{src.suffix}"
    shutil.copyfile(src, assets_dir / dest_name)
    return dest_name


def _format_ts(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
