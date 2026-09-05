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


@dataclass(frozen=True)
class ProceduralStep:
    """One documented moment in the source video, grounded in evidence.

    `instruction` is always derived directly from `transcript_ref` (or a
    fixed placeholder when there is none) — never LLM-invented text — so a
    step can never assert something the evidence doesn't support.
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
        }


@dataclass(frozen=True)
class DocumentationSource:
    """Provenance header shared by the human manual and the AI package."""
    video_name: str
    duration: float
    language: str
    extraction_method: str
    generated_at: str
