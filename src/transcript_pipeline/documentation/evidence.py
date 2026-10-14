"""Evidence Plane V2 models.

Evidence is immutable captured source material:
- transcript excerpts
- OCR text
- frame references
- timestamps
- confidence/provenance

This plane is derived from persisted `frame_mapping.json` and related transcription
segment files, without re-transcribing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

EvidenceSource = Literal["transcript", "ocr", "transcript_ocr", "frame", "none"]
Confidence = Literal["high", "medium", "low"]
VerificationStatus = Literal["SYNTHESIZED_UNREVIEWED", "HUMAN_REVIEWED"]


def deterministic_evidence_id(
    timestamp_start: float,
    timestamp_end: float,
    transcript_excerpt: str,
    ocr_excerpt: str,
    frame_ref: str | None,
    source: str,
) -> str:
    """Deterministic ID for unchanged persisted evidence."""
    key = f"{timestamp_start:.3f}-{timestamp_end:.3f}-{transcript_excerpt}-{ocr_excerpt}-{frame_ref}-{source}"
    return "E-" + hashlib.sha256(key.encode()).hexdigest()[:8]


@dataclass(frozen=True)
class EvidenceRef:
    """Reference to a captured evidence item."""
    evidenceId: str
    timestampStart: float
    timestampEnd: float
    evidenceSource: EvidenceSource
    confidence: Confidence
    reviewed: bool
    frameRef: str | None = None
    transcriptExcerpt: str | None = None
    ocrExcerpt: str | None = None
    sourceSegmentIds: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceItem:
    """Immutable captured evidence entry."""
    evidenceId: str
    ordinal: int
    timestampStart: float
    timestampEnd: float
    transcriptExcerpt: str
    ocrExcerpt: str
    frameRef: str | None
    confidence: Confidence
    reviewed: bool
    source: str  # provenance identifier
    # Optional extra fields
    visual_description: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceTimeline:
    """Chronological collection of evidence items."""
    items: list[EvidenceItem]
    sourceDuration: float
    generatedAt: datetime


@dataclass(frozen=True)
class ReviewQueue:
    """Low-confidence/no-evidence items requiring human review."""
    items: list[EvidenceItem]
    totalCount: int


# Evidence timeline builder

def build_evidence_timeline(
    mapping_data: dict,
    frames_dir: Path | None = None,
    project_config: dict | None = None,
) -> EvidenceTimeline:
    """Construct evidence timeline from frame_mapping.json data.
    
    Follows SPEC §6 evidence resolver precedence:
    1. timestamped saved segments (if persisted)
    2. unique transcription_mapping segments
    3. full transcription fallback
    
    Returns EvidenceTimeline with deterministic ids.
    """
    # TODO: implement segment resolution
    # For now, create placeholder items from frames
    frames = sorted(mapping_data.get("frames", []), key=lambda f: f["timestamp"])
    transcription_mapping = mapping_data.get("transcription_mapping", {})
    transcription_summary = mapping_data.get("transcription_summary", {})
    video_info = mapping_data.get("video_info", {})
    
    items = []
    for idx, frame in enumerate(frames, start=1):
        frame_file = frame["frame_file"]
        timestamp = frame["timestamp"]
        # assume timestamp range = +/- 2 seconds
        timestamp_start = max(0.0, timestamp - 2.0)
        timestamp_end = timestamp + 2.0
        
        transcript_entry = transcription_mapping.get(frame_file, {})
        transcript_excerpt = (transcript_entry.get("full_text") or "").strip()
        
        # OCR not available without frames_dir; placeholder
        ocr_excerpt = ""
        
        # Determine confidence and source
        if transcript_excerpt:
            confidence = "high"
            evidence_source = "transcript"
        else:
            confidence = "low"
            evidence_source = "none"
        
        evidence_id = deterministic_evidence_id(
            timestamp_start, timestamp_end,
            transcript_excerpt, ocr_excerpt,
            frame_file,
            source="frame_mapping"
        )
        
        items.append(EvidenceItem(
            evidenceId=evidence_id,
            ordinal=idx,
            timestampStart=timestamp_start,
            timestampEnd=timestamp_end,
            transcriptExcerpt=transcript_excerpt,
            ocrExcerpt=ocr_excerpt,
            frameRef=frame_file,
            confidence=confidence,
            reviewed=False,
            source="frame_mapping"
        ))
    
    return EvidenceTimeline(
        items=items,
        sourceDuration=video_info.get("duration", 0.0),
        generatedAt=datetime.now()
    )