"""Evidence timeline writer.

Writes raw chronological captured evidence to:
- evidence/evidence.jsonl
- evidence/EVIDENCE_TIMELINE.md
- evidence/review-queue.json

Keeps manual/steps.json compatibility generation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from transcript_pipeline.documentation.evidence import EvidenceTimeline, EvidenceItem, ReviewQueue


def write_evidence_timeline(
    timeline: EvidenceTimeline,
    frames_dir: Path,
    manual_dir: Path,
    evidence_dir: Path | None = None,
) -> dict:
    """Write evidence artifacts.
    
    Returns summary dict with counts.
    """
    evidence_dir = evidence_dir or (frames_dir / "evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # Write evidence.jsonl
    evidence_lines = []
    for item in timeline.items:
        evidence_lines.append(json.dumps({
            "evidenceId": item.evidenceId,
            "ordinal": item.ordinal,
            "timestampStart": item.timestampStart,
            "timestampEnd": item.timestampEnd,
            "transcriptExcerpt": item.transcriptExcerpt,
            "ocrExcerpt": item.ocrExcerpt,
            "frameRef": item.frameRef,
            "confidence": item.confidence,
            "reviewed": item.reviewed,
            "source": item.source,
        }, ensure_ascii=False))
    
    (evidence_dir / "evidence.jsonl").write_text("\n".join(evidence_lines) + ("\n" if evidence_lines else ""), encoding="utf-8")
    
    # Write EVIDENCE_TIMELINE.md
    markdown_lines = ["# Evidence Timeline\n\n"]
    markdown_lines.append(f"Source duration: {timeline.sourceDuration:.1f}s\n")
    markdown_lines.append(f"Evidence items: {len(timeline.items)}\n")
    markdown_lines.append(f"Generated at: {timeline.generatedAt.isoformat()}\n\n")
    
    for item in timeline.items:
        reviewed = " ✓ reviewed" if item.reviewed else ""
        markdown_lines.append(f"## {item.ordinal}. Evidence {item.evidenceId}\n\n")
        markdown_lines.append(f"Timestamp: {item.timestampStart:.1f}s – {item.timestampEnd:.1f}s\n")
        markdown_lines.append(f"Confidence: **{item.confidence}**{reviewed}\n\n")
        if item.transcriptExcerpt:
            markdown_lines.append(f"Transcript: {item.transcriptExcerpt}\n\n")
        if item.ocrExcerpt:
            markdown_lines.append(f"OCR: {item.ocrExcerpt}\n\n")
        if item.frameRef:
            markdown_lines.append(f"Frame: {item.frameRef}\n\n")
    
    (evidence_dir / "EVIDENCE_TIMELINE.md").write_text("".join(markdown_lines), encoding="utf-8")
    
    # Build review queue (low confidence items)
    low_items = [item for item in timeline.items if item.confidence == "low"]
    review_queue = ReviewQueue(items=low_items, totalCount=len(low_items))
    (evidence_dir / "review-queue.json").write_text(
        json.dumps({
            "total": review_queue.totalCount,
            "items": [
                {
                    "evidenceId": item.evidenceId,
                    "ordinal": item.ordinal,
                    "timestampStart": item.timestampStart,
                    "timestampEnd": item.timestampEnd,
                    "reason": "low confidence",
                }
                for item in review_queue.items
            ],
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    
    # Keep compatibility steps.json in manual/ (TODO: convert EvidenceItem to ProceduralStep)
    # For now placeholder
    manual_dir.mkdir(parents=True, exist_ok=True)
    (manual_dir / "steps.json").write_text(
        json.dumps({"schema_version": "1.0", "steps": []}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    
    return {
        "evidence_items": len(timeline.items),
        "low_confidence_count": len(low_items),
        "evidence_dir": str(evidence_dir),
        "manual_dir": str(manual_dir),
    }