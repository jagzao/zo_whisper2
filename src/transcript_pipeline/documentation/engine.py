"""Builds the human manual and AI-ready knowledge package from a tutorial
video's persisted `frame_mapping.json`, and supports human review/edit of
the result without re-transcribing (US-001 §4.6/§4.7/§4.8).

Evidence layering (§4.5), most-grounded first:
1. Transcript excerpt already stored in `frame_mapping.json` by
   `processor._integrate_transcription_with_frames` — used as `instruction`
   verbatim, confidence "high". Never LLM-touched.
2. OCR text read directly off the frame (`pytesseract`, local) — ALWAYS
   attempted when a frame is available, regardless of the transcript — also
   used as `instruction` (labeled as on-screen text), confidence "medium".
   When BOTH transcript and OCR exist the instruction combines them
   (evidence_source "transcript_ocr", confidence stays "high"). Still
   *captured* evidence, not an interpretation.
3. Vision LLM description (`AIEnrichmentService.describe_frame_with_prompt`,
   privacy-gated, only attempted when 1 and 2 both came up empty) — stored
   separately as `visual_description`, an unverified AI *interpretation*.
   Never merged into `instruction`, never raises `confidence` above "low".

Action/target are never inferred — this module only quotes captured evidence
verbatim as `instruction`; it never guesses at what a step does.

This module itself never calls an LLM for *wording that becomes the
instruction* — only for the clearly-labeled, separate `visual_description`
field, gated exactly like every other outbound AI call in this codebase.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"

try:
    import pytesseract
    from PIL import Image as PILImage

    from transcript_pipeline.settings import SETTINGS
    if SETTINGS.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = SETTINGS.tesseract_cmd
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

try:
    from transcript_pipeline.llm.enrichment import AIEnrichmentService
    from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
    from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
    from transcript_pipeline.settings import SETTINGS as _LLM_SETTINGS
    _ai_service = AIEnrichmentService(OpenAICompatibleProvider(_LLM_SETTINGS), PrivacyGuard(_LLM_SETTINGS), _LLM_SETTINGS)
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False

try:
    from transcript_pipeline.documentation.pdf_writer import write_manual_pdf
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

_STEP_VISION_PROMPT = (
    "Describe concisely what UI state or action is shown in this screenshot "
    "from a software tutorial. One or two factual sentences. Do not guess at "
    "text you cannot actually read, and do not invent menu items, values, or "
    "commands that are not clearly visible."
)


def _ocr_text(frame_path: Path) -> str:
    if not _OCR_AVAILABLE or not frame_path.exists():
        return ""
    try:
        img = PILImage.open(frame_path)
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        logger.warning("[DOCS] OCR failed for %s: %s", frame_path.name, e)
        return ""


def _vision_description(frame_path: Path, project_config: dict | None) -> str | None:
    if not _VISION_AVAILABLE or not frame_path.exists():
        return None
    try:
        return _ai_service.describe_frame_with_prompt(
            frame_path, _STEP_VISION_PROMPT, project_config, max_tokens=150, temperature=0
        ).strip() or None
    except ExternalLLMBlockedError as e:
        logger.info("[DOCS] Vision description blocked by privacy guard for %s: %s", frame_path.name, e)
        return None
    except Exception as e:
        logger.warning("[DOCS] Vision description failed for %s: %s", frame_path.name, e)
        return None


def _gather_visual_evidence(
    frames_dir: Path | None, frame_file: str | None, project_config: dict | None, transcript_text: str
) -> tuple[str, str | None]:
    """Returns (ocr_text, vision_description).

    OCR is local/cheap and always attempted (given a frame) regardless of
    whether the transcript already grounds the step — a frame can carry
    genuinely additional captured evidence (an on-screen value, an error
    message) worth combining with what was said out loud. The privacy-gated
    vision LLM is the one thing still skipped whenever *either* transcript
    or OCR already ground the step (§4.5's "avoid redundant vision calls" —
    OCR is not the expensive/privacy-sensitive step, the vision call is).
    """
    if frames_dir is None or not frame_file:
        return "", None
    frame_path = frames_dir / frame_file
    ocr = _ocr_text(frame_path)
    if transcript_text or ocr:
        return ocr, None
    return ocr, _vision_description(frame_path, project_config)


def build_steps(
    mapping_data: dict,
    frames_dir: Path | None = None,
    project_config: dict | None = None,
) -> list[ProceduralStep]:
    """Turns `frame_mapping.json`'s frames + transcription_mapping into
    grounded, ordered ProceduralStep objects.

    `frames_dir`/`project_config` are optional: when omitted, no visual
    evidence is gathered and behavior is exactly the transcript-only
    grounding this module started with (keeps existing callers/tests that
    don't care about visual evidence unaffected).

    When both the transcript *and* OCR ground the same frame, `instruction`
    combines them (evidence_source "transcript_ocr") rather than discarding
    the on-screen text just because the transcript was non-empty — every
    word in `instruction` still traces to one of these two captured-evidence
    sources. `action`/`target` are never populated from either: this module
    only ever quotes evidence verbatim, it never infers a structured action/
    target that the evidence doesn't literally state (see ProceduralStep.to_dict).
    """
    frames = sorted(mapping_data.get("frames", []), key=lambda f: f["timestamp"])
    transcription_mapping = mapping_data.get("transcription_mapping", {})

    steps: list[ProceduralStep] = []
    for order, frame in enumerate(frames, start=1):
        frame_file = frame["frame_file"]
        transcript_entry = transcription_mapping.get(frame_file, {})
        transcript_text = (transcript_entry.get("full_text") or "").strip()

        ocr_text, vision_description = _gather_visual_evidence(frames_dir, frame_file, project_config, transcript_text)

        if transcript_text and ocr_text:
            instruction = f"{transcript_text}\n\nOn-screen text: {ocr_text}"
            confidence = "high"
            evidence_source = "transcript_ocr"
            title_source = transcript_text
        elif transcript_text:
            instruction = transcript_text
            confidence = "high"
            evidence_source = "transcript"
            title_source = transcript_text
        elif ocr_text:
            instruction = f"On-screen text: {ocr_text}"
            confidence = "medium"
            evidence_source = "ocr"
            title_source = ocr_text
        else:
            instruction = "(no transcript or on-screen text captured near this moment — review evidence before trusting this step)"
            confidence = "low"
            evidence_source = "none"
            title_source = ""

        title = _shorten(title_source) if title_source else f"Step at {frame['timestamp_formatted']}"

        steps.append(ProceduralStep(
            id=f"step-{order:04d}",
            order=order,
            title=title,
            instruction=instruction,
            timestamp=frame["timestamp"],
            frame_ref=frame_file,
            transcript_ref=transcript_text,
            confidence=confidence,
            evidence_source=evidence_source,
            ocr_text=ocr_text or None,
            visual_description=vision_description,
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
    project_config: dict | None = None,
) -> dict:
    """Reads `frames_dir/frame_mapping.json` and writes MANUAL.md + the
    AI-ready package next to it. Returns a small summary dict.

    Safe to call again later purely from the persisted `steps.json` via
    `regenerate_from_steps` — this function is the only one that re-derives
    steps from frame_mapping.json (i.e. it's the only path that would need
    re-transcription-adjacent data or re-run OCR/vision evidence gathering).
    """
    mapping_path = frames_dir / "frame_mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(f"frame_mapping.json not found in {frames_dir}")

    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    video_info = mapping_data.get("video_info", {})
    transcription_summary = mapping_data.get("transcription_summary", {})

    steps = build_steps(mapping_data, frames_dir, project_config)

    source = DocumentationSource(
        video_name=video_name,
        duration=video_info.get("duration", 0.0),
        language=transcription_summary.get("language", "unknown"),
        extraction_method=video_info.get("extraction_method", "unknown"),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    manual_dir = manual_dir or (frames_dir / "manual")
    ai_package_dir = ai_package_dir or (frames_dir / "ai-package")

    _write_steps_json(manual_dir, source, steps)  # editable source of truth for regeneration
    write_manual(manual_dir, source, steps, frames_dir, write_steps_json=False)
    write_ai_package(ai_package_dir, source, steps, frames_dir)

    return {
        "manual_dir": str(manual_dir),
        "ai_package_dir": str(ai_package_dir),
        "step_count": len(steps),
        "low_confidence_count": sum(1 for s in steps if s.confidence == "low"),
    }


def load_steps(manual_dir: Path) -> tuple[DocumentationSource, list[ProceduralStep]]:
    """Reads the persisted, human-editable `manual/steps.json`."""
    payload = json.loads((manual_dir / "steps.json").read_text(encoding="utf-8"))
    steps = [ProceduralStep.from_dict(s) for s in payload["steps"]]
    source = DocumentationSource.from_dict(
        payload.get("source", {}),
        video_name=payload.get("source", {}).get("video_name", "unknown"),
        generated_at=payload.get("source", {}).get("generated_at", datetime.now(timezone.utc).isoformat()),
    )
    return source, steps


def regenerate_from_steps(manual_dir: Path, ai_package_dir: Path, frames_dir: Path, video_name: str) -> dict:
    """Rebuilds MANUAL.md / knowledge package from a (possibly human-edited)
    `steps.json` without touching frame_mapping.json, re-transcribing, or
    re-running OCR/vision evidence gathering."""
    source, steps = load_steps(manual_dir)
    source = DocumentationSource(
        video_name=video_name or source.video_name,
        duration=source.duration,
        language=source.language,
        extraction_method=source.extraction_method,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    write_manual(manual_dir, source, steps, frames_dir, write_steps_json=True)
    write_ai_package(ai_package_dir, source, steps, frames_dir)
    return {"step_count": len(steps)}


def update_step(
    manual_dir: Path, ai_package_dir: Path, frames_dir: Path, step_id: str,
    *, title: str | None = None, instruction: str | None = None, reviewed: bool | None = None,
) -> dict:
    """Human-review edit (§4.8): updates one step's title/instruction/
    reviewed flag, persists it, and regenerates both bundles from the
    updated steps.json — no re-transcription, no re-running OCR/vision.
    Raises KeyError if `step_id` doesn't exist."""
    source, steps = load_steps(manual_dir)
    updated = None
    new_steps = []
    for step in steps:
        if step.id == step_id:
            step = ProceduralStep(
                id=step.id, order=step.order,
                title=title if title is not None else step.title,
                instruction=instruction if instruction is not None else step.instruction,
                timestamp=step.timestamp, frame_ref=step.frame_ref, transcript_ref=step.transcript_ref,
                confidence=step.confidence, tags=step.tags,
                visual_description=step.visual_description, ocr_text=step.ocr_text,
                evidence_source=step.evidence_source,
                reviewed=reviewed if reviewed is not None else (True if (title is not None or instruction is not None) else step.reviewed),
            )
            updated = step
        new_steps.append(step)
    if updated is None:
        raise KeyError(f"step {step_id!r} not found")

    _write_steps_json(manual_dir, source, new_steps)
    write_manual(manual_dir, source, new_steps, frames_dir, write_steps_json=False)
    write_ai_package(ai_package_dir, source, new_steps, frames_dir)
    return updated.to_dict()


def remove_step(manual_dir: Path, ai_package_dir: Path, frames_dir: Path, step_id: str) -> dict:
    """Human-review removal (§4.8): deletes an invalid step, renumbers the
    rest, persists, and regenerates both bundles. Raises KeyError if
    `step_id` doesn't exist."""
    source, steps = load_steps(manual_dir)
    remaining = [s for s in steps if s.id != step_id]
    if len(remaining) == len(steps):
        raise KeyError(f"step {step_id!r} not found")

    renumbered = [
        ProceduralStep(
            id=s.id, order=i, title=s.title, instruction=s.instruction, timestamp=s.timestamp,
            frame_ref=s.frame_ref, transcript_ref=s.transcript_ref, confidence=s.confidence, tags=s.tags,
            visual_description=s.visual_description, ocr_text=s.ocr_text,
            evidence_source=s.evidence_source, reviewed=s.reviewed,
        )
        for i, s in enumerate(remaining, start=1)
    ]
    _write_steps_json(manual_dir, source, renumbered)
    write_manual(manual_dir, source, renumbered, frames_dir, write_steps_json=False)
    write_ai_package(ai_package_dir, source, renumbered, frames_dir)
    return {"step_count": len(renumbered)}


def _write_steps_json(manual_dir: Path, source: DocumentationSource, steps: list[ProceduralStep]) -> None:
    manual_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": source.to_dict(),
        "steps": [s.to_dict() for s in steps],
    }
    (manual_dir / "steps.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_manual(
    manual_dir: Path,
    source: DocumentationSource,
    steps: list[ProceduralStep],
    frames_dir: Path,
    write_steps_json: bool = True,
) -> None:
    """Writes MANUAL.md (+ MANUAL.pdf when reportlab is available) and the
    manual metadata/steps.json from the same domain objects. Every caller
    (generate_documentation, regenerate_from_steps, update_step, remove_step)
    goes through here, so the PDF stays in sync with the Markdown by
    construction — no re-transcription, no re-running OCR/vision."""
    assets_dir = manual_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"# {source.video_name}\n\n"]
    review_count = sum(1 for s in steps if s.confidence == "low")
    if review_count:
        lines.append(
            f"> ⚠ {review_count} of {len(steps)} step(s) below have no transcript/on-screen-text "
            "evidence and are marked `confidence: low` — review before treating them as accurate.\n\n"
        )

    for step in steps:
        reviewed_badge = " ✓ reviewed" if step.reviewed else ""
        lines.append(f"## {step.order}. {step.title}\n\n")
        lines.append(f"`{_format_ts(step.timestamp)}` — confidence: **{step.confidence}**{reviewed_badge}\n\n")

        asset_name = _copy_frame_asset(frames_dir, assets_dir, step)
        if asset_name:
            lines.append(f"![{step.id}](assets/{asset_name})\n\n")

        lines.append(f"{step.instruction}\n\n")

        if step.visual_description:
            lines.append(
                f"> 🤖 AI-generated interpretation of this frame (unverified, not evidence): "
                f"{step.visual_description}\n\n"
            )

    (manual_dir / "MANUAL.md").write_text("".join(lines), encoding="utf-8")

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "video_name": source.video_name,
        "duration": source.duration,
        "language": source.language,
        "extraction_method": source.extraction_method,
        "generated_at": source.generated_at,
        "step_count": len(steps),
        # Written after the PDF attempt below so the API can distinguish
        # "generated", "failed", and "reportlab not installed" instead of
        # silently pretending the human bundle is complete.
        "manual_pdf": "ok",
    }

    if write_steps_json:
        _write_steps_json(manual_dir, source, steps)

    if _PDF_AVAILABLE:
        try:
            write_manual_pdf(manual_dir, source, steps, frames_dir)
        except Exception as e:
            logger.warning("[DOCS] MANUAL.pdf generation failed: %s", e)
            metadata["manual_pdf"] = "failed"
    else:
        logger.warning(
            "[DOCS] reportlab not installed; skipping MANUAL.pdf "
            "(install with: pip install 'transcript-pipeline[pdf]')"
        )
        metadata["manual_pdf"] = "missing"

    (manual_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


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
        "source": source.to_dict(),
        "procedures": [
            {"id": s.id, "order": s.order, "title": s.title, "confidence": s.confidence,
             "evidence_source": s.evidence_source, "reviewed": s.reviewed}
            for s in steps
        ],
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
                "evidence_source": step.evidence_source,
                "reviewed": step.reviewed,
                "source_video": source.video_name,
            },
        }, ensure_ascii=False))

        knowledge_lines.append(f"## {step.order}. {step.title}\n\n{step.instruction}\n\n")
        if step.visual_description:
            knowledge_lines.append(f"_AI interpretation (unverified): {step.visual_description}_\n\n")

    (ai_package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (ai_package_dir / "steps.json").write_text(json.dumps(steps_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (ai_package_dir / "chunks.jsonl").write_text("\n".join(chunks_lines) + ("\n" if chunks_lines else ""), encoding="utf-8")
    (ai_package_dir / "knowledge.md").write_text("".join(knowledge_lines), encoding="utf-8")


def _copy_frame_asset(frames_dir: Path, assets_dir: Path, step: ProceduralStep) -> str | None:
    if not step.frame_ref:
        return None
    # frame_ref may already be an assets-relative path (e.g. after a prior
    # write_ai_package pass mutated a *copy* of step_dict — the step object
    # itself here still holds the original frames_dir-relative filename) or,
    # defensively, just the bare frame filename either way.
    src = frames_dir / Path(step.frame_ref).name
    if not src.exists():
        return None
    dest_name = f"{step.id}{src.suffix}"
    shutil.copyfile(src, assets_dir / dest_name)
    return dest_name


def _format_ts(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
