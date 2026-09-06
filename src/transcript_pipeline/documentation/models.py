"""Typed evidence/documentation domain model.

Raw dicts (frame_mapping.json's own shape) stay internal to `engine.py`;
everything downstream of `build_steps` works with these frozen dataclasses
so callers (manual/AI-package writers, dashboard, tests) get a stable
contract instead of guessing dict keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["high", "medium", "low"]
# What grounds `instruction`, in order of preference — never upgraded by the
# presence of `visual_description` (an unverified AI interpretation, kept
# strictly separate; see US-001 §4.7).
EvidenceSource = Literal["transcript", "ocr", "transcript_ocr", "none"]


@dataclass(frozen=True)
class ProceduralStep:
    """One documented moment in the source video, grounded in evidence.

    `instruction` is derived only from directly-captured evidence — the
    transcript excerpt (`transcript_ref`) or, failing that, OCR text actually
    read off the frame (`ocr_text`) — never LLM-invented text, so a step can
    never assert something the evidence doesn't support. `visual_description`
    is a separate, clearly-labeled AI *interpretation* of the frame (vision
    LLM) that is never merged into `instruction` and never raises
    `confidence` — see `engine.build_steps`/`_gather_visual_evidence`.

    `reviewed` and `instruction`/`title` edits are the human-review surface
    (§4.8): a human can edit/approve a step without that being confused with
    the machine-computed `confidence` (evidence quality) or `evidence_source`
    (what evidence produced the original instruction).
    """
    id: str
    order: int
    title: str
    instruction: str
    timestamp: float
    frame_ref: str | None
    transcript_ref: str
    confidence: Confidence
    tags: list[str] = field(default_factory=list)
    visual_description: str | None = None
    ocr_text: str | None = None
    evidence_source: EvidenceSource = "transcript"
    reviewed: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order": self.order,
            "title": self.title,
            "instruction": self.instruction,
            "action": None,
            "target": None,
            "timestamp": self.timestamp,
            "transcript_ref": self.transcript_ref,
            "frame_ref": self.frame_ref,
            "confidence": self.confidence,
            "tags": self.tags,
            "visual_description": self.visual_description,
            "ocr_text": self.ocr_text,
            "evidence_source": self.evidence_source,
            "reviewed": self.reviewed,
        }

    @staticmethod
    def from_dict(data: dict) -> ProceduralStep:
        return ProceduralStep(
            id=data["id"], order=data["order"], title=data["title"], instruction=data["instruction"],
            timestamp=data["timestamp"], frame_ref=data.get("frame_ref"),
            transcript_ref=data.get("transcript_ref", ""), confidence=data.get("confidence", "low"),
            tags=data.get("tags", []), visual_description=data.get("visual_description"),
            ocr_text=data.get("ocr_text"), evidence_source=data.get("evidence_source", "transcript"),
            reviewed=data.get("reviewed", False),
        )


@dataclass(frozen=True)
class DocumentationSource:
    """Provenance header shared by the human manual and the AI package."""
    video_name: str
    duration: float
    language: str
    extraction_method: str
    generated_at: str

    def to_dict(self) -> dict:
        return {
            "video_name": self.video_name,
            "duration": self.duration,
            "language": self.language,
            "extraction_method": self.extraction_method,
            "generated_at": self.generated_at,
        }

    @staticmethod
    def from_dict(data: dict, *, video_name: str, generated_at: str) -> DocumentationSource:
        return DocumentationSource(
            video_name=data.get("video_name", video_name),
            duration=data.get("duration", 0.0),
            language=data.get("language", "unknown"),
            extraction_method=data.get("extraction_method", "unknown"),
            generated_at=generated_at,
        )
