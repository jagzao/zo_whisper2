"""Deterministic synthesis input compactor (SPEC §6, PLAN WP-05).

Turns an EvidenceTimeline into bounded, ordered SynthesisBlocks:

- chronological transcript block construction;
- repeated OCR suppression (near-identical/repeated on-screen text never
  inflates the synthesis input);
- frame evidence references (evidence ids) on every entry;
- configurable character bounds (target 18,000 / hard 24,000 default);
- max block count (12 default);
- NO semantic invention, NO reordering, NO LLM calls.

When the source exceeds the bounds, redundant OCR is merged/truncated FIRST;
evidence ids are never dropped — a block always keeps the ids of every
evidence item it covers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from transcript_pipeline.documentation.evidence import EvidenceTimeline

DEFAULT_TARGET_BLOCK_CHARS = 18_000
DEFAULT_HARD_BLOCK_CHARS = 24_000
DEFAULT_MAX_BLOCKS = 12

_OCR_REDUCTION_LIMIT = 240


@dataclass(frozen=True)
class SynthesisBlock:
    index: int
    timestamp_start: float
    timestamp_end: float
    evidence_ids: tuple[str, ...]
    transcript_text: str
    ocr_text: str
    char_count: int

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "blockIndex": self.index,
            "timestampRange": [round(self.timestamp_start, 2), round(self.timestamp_end, 2)],
            "evidenceIds": list(self.evidence_ids),
            "transcript": self.transcript_text,
            "ocr": self.ocr_text,
        }


@dataclass
class CompactionResult:
    blocks: list[SynthesisBlock] = field(default_factory=list)
    dropped_redundant_ocr: int = 0
    truncated: bool = False
    coverage_complete: bool = True
    omitted_evidence_ids: list[str] = field(default_factory=list)
    truncated_transcript: bool = False


def _normalize_ocr(text: str) -> str:
    return " ".join(text.lower().split())


def build_synthesis_blocks(
    timeline: EvidenceTimeline,
    *,
    target_chars: int = DEFAULT_TARGET_BLOCK_CHARS,
    hard_chars: int = DEFAULT_HARD_BLOCK_CHARS,
    max_blocks: int = DEFAULT_MAX_BLOCKS,
) -> CompactionBlockBuilder:
    """Returns a builder bound to this timeline for fluent block assembly."""
    return CompactionBlockBuilder(
        timeline,
        target_chars=target_chars,
        hard_chars=hard_chars,
        max_blocks=max_blocks,
    )


class CompactionBlockBuilder:
    def __init__(
        self,
        timeline: EvidenceTimeline,
        *,
        target_chars: int,
        hard_chars: int,
        max_blocks: int,
    ) -> None:
        self.timeline = timeline
        self.target_chars = target_chars
        self.hard_chars = hard_chars
        self.max_blocks = max_blocks

    def build(self) -> CompactionResult:
        facts = self.timeline.facts()  # chronological, placeholders excluded
        if not facts:
            return CompactionResult()

        seen_ocr: set[str] = set()
        dropped = 0
        entries: list[dict[str, Any]] = []
        for item in facts:
            ocr = item.ocr_excerpt or ""
            if ocr:
                normalized = _normalize_ocr(ocr)
                if normalized in seen_ocr:
                    # Repeated OCR from near-identical frames: suppress.
                    ocr = ""
                    dropped += 1
                else:
                    seen_ocr.add(normalized)
            entries.append({
                "id": item.evidence_id,
                "start": item.timestamp_start,
                "end": item.timestamp_end,
                "transcript": item.transcript_excerpt or "",
                "ocr": ocr,
            })

        # Group entries into blocks: never reorder; cut only on entry
        # boundaries; OCR is reduced first when a block would exceed the
        # hard bound.
        blocks: list[SynthesisBlock] = []
        current: list[dict[str, Any]] = []
        current_chars = 0
        truncated = False
        truncated_transcript = False
        omitted_transcript_ids: list[str] = []

        def _entry_size(entry: dict[str, Any], with_ocr: bool) -> int:
            return len(entry["transcript"]) + (len(entry["ocr"]) if with_ocr else 0) + len(entry["id"]) + 24

        def _flush() -> None:
            nonlocal current, current_chars
            if not current:
                return
            blocks.append(SynthesisBlock(
                index=len(blocks) + 1,
                timestamp_start=current[0]["start"],
                timestamp_end=current[-1]["end"],
                evidence_ids=tuple(entry["id"] for entry in current),
                transcript_text="\n".join(
                    f"[{e['id']}] {e['transcript']}" for e in current if e["transcript"]
                ),
                ocr_text="\n".join(f"[{e['id']}] {e['ocr']}" for e in current if e["ocr"]),
                char_count=current_chars,
            ))
            current = []
            current_chars = 0

        for entry in entries:
            size = _entry_size(entry, with_ocr=True)
            if current and current_chars + size > self.target_chars:
                _flush()
            if not current:
                if size > self.hard_chars:
                    # Reduce redundant OCR first, then truncate the tail.
                    if entry["ocr"]:
                        entry = dict(entry, ocr=entry["ocr"][:_OCR_REDUCTION_LIMIT] + " …")
                        dropped += 1
                        size = _entry_size(entry, with_ocr=True)
                    if size > self.hard_chars:
                        entry = dict(entry, transcript=entry["transcript"][: self.hard_chars - _OCR_REDUCTION_LIMIT - 32] + " …")
                        truncated = True
                        truncated_transcript = True
                        omitted_transcript_ids.append(entry["id"])
                        size = _entry_size(entry, with_ocr=True)
                current.append(entry)
                current_chars = size
                if len(blocks) + 1 >= self.max_blocks and current_chars >= self.target_chars:
                    pass  # cap enforcement below
                continue
            # Block already open: reduce OCR when the hard bound demands it.
            if current_chars + size > self.hard_chars:
                if entry["ocr"]:
                    entry = dict(entry, ocr=entry["ocr"][:_OCR_REDUCTION_LIMIT] + " …")
                    dropped += 1
                    size = _entry_size(entry, with_ocr=True)
                if current_chars + size > self.hard_chars:
                    _flush()
                    current.append(entry)
                    current_chars = size
                    continue
            current.append(entry)
            current_chars += size
        _flush()

        omitted: list[str] = list(omitted_transcript_ids)
        if len(blocks) > self.max_blocks:
            omitted.extend(eid for block in blocks[self.max_blocks:] for eid in block.evidence_ids)
            blocks = blocks[:self.max_blocks]
            truncated = True

        return CompactionResult(
            blocks=blocks, dropped_redundant_ocr=dropped, truncated=truncated,
            coverage_complete=not truncated, omitted_evidence_ids=omitted,
            truncated_transcript=truncated_transcript,
        )
