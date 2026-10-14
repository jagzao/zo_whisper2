"""Deterministic synthesis input compactor.

Creates bounded SynthesisBlocks from evidence timeline.
Preserves chronology, deduplicates repeated OCR, respects character bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SynthesisBlock:
    """One block of evidence to send to synthesis provider."""
    order: int
    timestamp_start: float
    timestamp_end: float
    transcript_excerpts: list[str]
    deduped_ocr: list[str]
    evidence_ids: list[str]
    frame_refs: list[str]
    character_count: int


def compact_evidence_timeline(
    timeline: dict,  # EvidenceTimeline dict representation
    max_chars_per_block: int = 18000,
    hard_max_chars: int = 24000,
    max_blocks: int = 12,
) -> list[SynthesisBlock]:
    """Create ordered blocks respecting bounds.
    
    Steps:
    - group evidence items chronologically
    - merge overlapping/nearby items
    - deduplicate OCR text (identical or near-identical)
    - split when char limit exceeded
    - enforce max block count
    """
    # TODO: implement actual compaction logic
    # For now return a single placeholder block
    return [
        SynthesisBlock(
            order=1,
            timestamp_start=0.0,
            timestamp_end=timeline.get("sourceDuration", 0.0),
            transcript_excerpts=[],
            deduped_ocr=[],
            evidence_ids=[],
            frame_refs=[],
            character_count=0,
        )
    ]