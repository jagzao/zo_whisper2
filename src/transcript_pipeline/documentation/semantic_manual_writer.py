"""Semantic MANUAL writer (SPEC §11, PLAN WP-10).

V2 MANUAL.md/PDF render the KnowledgeDocument — semantic sections, concise
grounded claims, representative screenshots, compact evidence references
like `[E-001 @ 00:13:34]` — NOT one heading per captured frame.

Also persists:
- manual/knowledge-document.json  (the editable semantic document, AC-22);
- manual/metadata.json            (existing keys + V2 additions);
- compatibility manual/steps.json stays written by the engine (WP-03/WP-14).
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.evidence import EvidenceTimeline
from transcript_pipeline.documentation.evidence_writer import format_timestamp
from transcript_pipeline.documentation.knowledge_models import KnowledgeDocument, executive_summary_evidence_refs
from transcript_pipeline.documentation.models import DocumentationSource
from transcript_pipeline.documentation.screenshots import ScreenshotSelection

logger = logging.getLogger(__name__)

try:
    from transcript_pipeline.documentation.semantic_pdf_writer import write_semantic_manual_pdf
    _PDF_AVAILABLE = True
except ImportError:  # pragma: no cover - reportlab optional
    _PDF_AVAILABLE = False

SYNTHESIS_STATUS = "synthesis_status"


def write_semantic_manual(
    manual_dir: Path,
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    frames_dir: Path,
    selection: ScreenshotSelection,
    source: DocumentationSource,
    *,
    write_steps_json: bool = False,
) -> dict[str, Any]:
    """Writes MANUAL.md, knowledge-document.json, metadata.json (+ PDF when
    reportlab is available) from the KnowledgeDocument."""
    manual_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = manual_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    asset_names = _copy_assets(assets_dir, selection)

    markdown = _render_markdown(document, timeline, asset_names)
    document_stem = Path(source.video_name).stem
    (manual_dir / f"{document_stem}.md").write_text(markdown, encoding="utf-8")
    (manual_dir / "MANUAL.md").write_text(markdown, encoding="utf-8")
    document_json = document.to_json()
    (manual_dir / f"{document_stem}.json").write_text(document_json, encoding="utf-8")
    (manual_dir / "knowledge-document.json").write_text(document_json, encoding="utf-8")

    metadata = {
        "schema_version": 2,
        "video_name": source.video_name,
        "duration": source.duration,
        "language": source.language,
        "extraction_method": source.extraction_method,
        "generated_at": source.generated_at,
        "step_count": timeline.item_count,
        "documentation_mode": document.documentation_mode,
        SYNTHESIS_STATUS: "MANUAL_READY",
        "review_required_count": timeline.review_required_count,
        "evidence_item_count": timeline.item_count,
        "semantic_section_count": len(document.sections),
        "semantic_procedure_count": len(document.procedures),
        "manual_pdf": "ok",
    }

    if _PDF_AVAILABLE:
        try:
            write_semantic_manual_pdf(manual_dir, document, timeline, selection, source)
        except Exception as e:  # noqa: BLE001
            logger.warning("[DOCS-V2] MANUAL.pdf generation failed: %s", e)
            metadata["manual_pdf"] = "failed"
    else:
        logger.warning("[DOCS-V2] reportlab not installed; skipping MANUAL.pdf")
        metadata["manual_pdf"] = "missing"

    (manual_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if write_steps_json:
        from transcript_pipeline.documentation.engine import _write_steps_json  # local import: avoid cycle

        _write_steps_json(manual_dir, source, [])

    return metadata


def _copy_assets(assets_dir: Path, selection: ScreenshotSelection) -> dict[tuple[str, str], str]:
    """Copies selected source frames into manual/assets as
    `<evidence_id><ext>`. Originals are never touched."""
    names: dict[tuple[str, str], str] = {}
    for pick in selection.picks:
        dest_name = f"{pick.evidence_id}{pick.source_path.suffix}"
        try:
            shutil.copyfile(pick.source_path, assets_dir / dest_name)
            names[(pick.section_id, pick.evidence_id)] = dest_name
        except OSError as e:
            logger.warning("[DOCS-V2] asset copy failed for %s: %s", pick.source_path.name, e)
    return names


def _evidence_ref_label(evidence_id: str, timeline: EvidenceTimeline) -> str:
    item = timeline.by_id().get(evidence_id)
    ts = format_timestamp(item.timestamp_start) if item else "?"
    return f"[{evidence_id} @ {ts}]"


def _render_markdown(
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    asset_names: dict[tuple[str, str], str],
) -> str:
    lines: list[str] = [f"# {document.title}\n\n"]
    mode_label = document.documentation_mode.replace("_", " ").title()
    lines.append(f"> Documentation mode: **{mode_label}** · schema v{document.schema_version}\n\n")

    if timeline.review_required_count:
        lines.append(
            f"> ⚠ Review queue: {timeline.review_required_count} captured moment(s) lack transcript/on-screen-text "
            "evidence. They are isolated in `evidence/review-queue.json` and are not used as factual support "
            "in this manual.\n\n"
        )

    if document.executive_summary:
        lines.append("## Executive Summary\n\n")
        refs = " ".join(_evidence_ref_label(r, timeline) for r in executive_summary_evidence_refs(document))
        lines.append(f"{document.executive_summary} {refs}\n\n")

    for section in document.sections:
        if section.section_type == "EXECUTIVE_SUMMARY" and not section.claims and not section.summary:
            continue
        heading = section.title or section.section_type.replace("_", " ").title()
        lines.append(f"## {heading}\n\n")
        if section.summary:
            refs = " ".join(_evidence_ref_label(r, timeline) for r in section.summary_evidence_refs)
            lines.append(f"{section.summary} {refs}\n\n")
        for claim in section.claims:
            refs = " ".join(_evidence_ref_label(r, timeline) for r in claim.evidence_refs)
            badge = " ✓" if claim.verification_status == "HUMAN_REVIEWED" else ""
            lines.append(f"- {claim.text} {refs}{badge}\n")
        if section.claims:
            lines.append("\n")
        for (section_id, _), asset_name in asset_names.items():
            if section_id == section.id:
                lines.append(f"![{section.id}](assets/{asset_name})\n\n")

    for procedure in document.procedures:
        lines.append(f"## Procedure: {procedure.title}\n\n")
        if procedure.purpose:
            lines.append(f"{procedure.purpose}\n\n")
        if procedure.prerequisites:
            lines.append("**Prerequisites**\n\n")
            for prerequisite in procedure.prerequisites:
                lines.append(f"- {prerequisite}\n")
            lines.append("\n")
        for step in procedure.steps:
            refs = " ".join(_evidence_ref_label(r, timeline) for r in step.evidence_refs)
            lines.append(f"{step.order}. {step.instruction} {refs}\n")
        lines.append("\n")
        if procedure.expected_outcomes:
            lines.append("**Expected outcomes**\n\n")
            for outcome in procedure.expected_outcomes:
                lines.append(f"- {outcome}\n")
            lines.append("\n")
        if procedure.metadata_evidence_refs:
            refs = " ".join(_evidence_ref_label(r, timeline) for r in procedure.metadata_evidence_refs)
            lines.append(f"**Procedure evidence:** {refs}\n\n")
        for (section_id, _), asset_name in asset_names.items():
            if section_id == procedure.id:
                lines.append(f"![{procedure.id}](assets/{asset_name})\n\n")

    if document.glossary:
        lines.append("## Glossary\n\n")
        for entry in document.glossary:
            refs = " ".join(_evidence_ref_label(r, timeline) for r in entry.evidence_refs)
            lines.append(f"- **{entry.term}** — {entry.definition} {refs}\n")
        lines.append("\n")

    # Compact evidence index: ids + timestamps + source only. Never the raw
    # transcript/OCR dump (SPEC §11).
    lines.append("## Evidence Index\n\n")
    lines.append("| Evidence | Timestamp | Source | Confidence |\n")
    lines.append("|---|---|---|---|\n")
    for item in timeline.items:
        ts = "untimed" if item.untimed else format_timestamp(item.timestamp_start)
        lines.append(
            f"| {item.evidence_id} | {ts} | {item.evidence_source} | {item.confidence} |\n"
        )
    lines.append(
        "\nRaw chronological evidence: `evidence/EVIDENCE_TIMELINE.md` · "
        "machine-readable: `evidence/evidence.jsonl`.\n"
    )
    return "".join(lines)
