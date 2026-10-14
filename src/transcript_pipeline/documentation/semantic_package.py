"""Semantic AI knowledge package writer (SPEC §12, PLAN WP-12).

Outputs under `<frames_dir>/ai-package/`:
- knowledge.md    — mirrors semantic sections, NOT raw steps;
- chunks.jsonl    — one chunk per semantic section/claim/procedure with full
                    retrieval metadata (scope/project/artifact/actionability/
                    evidence refs/confidence/review/source media/timestamps);
- manifest.json   — V2 manifest of the semantic package;
- evidence.jsonl  — bounded evidence items (no raw whole transcript);
- assets/         — copies of the selected representative screenshots;
- procedure.json  — ONLY when a real SynthesizedProcedure exists (written by
                    the Knowledge Package bridge).

Chunk rules:
- coherent semantic unit, <= 4,000 chars default; long sections split by
  claims, not arbitrary character slices;
- low-confidence evidence that supports no valid synthesized claim is NOT an
  independent retrieval chunk (it stays in evidence.jsonl/review queue).
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
from transcript_pipeline.documentation.modes import ARTIFACT_TYPE_FOR_MODE
from transcript_pipeline.documentation.screenshots import ScreenshotSelection

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0"
DEFAULT_CHUNK_MAX_CHARS = 4000


def write_semantic_ai_package(
    ai_package_dir: Path,
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    selection: ScreenshotSelection,
    source: DocumentationSource,
    *,
    project_config: dict | None = None,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
) -> dict[str, Any]:
    ai_package_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = ai_package_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    scope, project_id, actionability = _publish_context(project_config)
    artifact_type = ARTIFACT_TYPE_FOR_MODE.get(document.documentation_mode, "REFERENCE")

    # Assets: only the selected representative screenshots.
    artifacts: list[str] = []
    for pick in selection.picks:
        dest = assets_dir / f"{pick.evidence_id}{pick.source_path.suffix}"
        try:
            shutil.copyfile(pick.source_path, dest)
            artifacts.append(f"assets/{dest.name}")
        except OSError as e:
            logger.warning("[DOCS-V2] package asset copy failed for %s: %s", pick.source_path.name, e)

    chunks = _build_chunks(document, timeline, source, scope, project_id, artifact_type, actionability, chunk_max_chars)
    with (ai_package_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    (ai_package_dir / "knowledge.md").write_text(
        _render_knowledge_md(document, timeline), encoding="utf-8"
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": source.to_dict(),
        "documentId": document.document_id,
        "documentationMode": document.documentation_mode,
        "semanticSections": [
            {"id": s.id, "type": s.section_type, "title": s.title, "order": s.order}
            for s in document.sections
        ],
        "procedures": [
            {"id": p.id, "title": p.title, "stepCount": len(p.steps)}
            for p in document.procedures
        ],
        "chunkCount": len(chunks),
        "evidenceItemCount": timeline.item_count,
        "artifacts": artifacts,
        "generated_at": source.generated_at,
    }
    (ai_package_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    with (ai_package_dir / "evidence.jsonl").open("w", encoding="utf-8") as fh:
        for item in timeline.items:
            fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    return {"chunk_count": len(chunks), "artifacts": artifacts}


def _publish_context(project_config: dict | None) -> tuple[str, str | None, str]:
    sb = (project_config or {}).get("second_brain")
    if not isinstance(sb, dict) or not sb.get("enabled", False):
        return "PROJECT", None, "REFERENCE"
    scope = sb.get("scope", "PROJECT")
    project_id = sb.get("project_id") if scope == "PROJECT" else None
    return scope, project_id, sb.get("default_actionability", "REFERENCE")


def _chunk_metadata(
    document: KnowledgeDocument,
    source: DocumentationSource,
    scope: str,
    project_id: str | None,
    artifact_type: str,
    actionability: str,
    evidence_refs: list[str],
    timeline: EvidenceTimeline,
    timestamp_range: tuple[float, float] | None,
) -> dict[str, Any]:
    by_id = timeline.by_id()
    confidences = [by_id[r].confidence for r in evidence_refs if r in by_id]
    evidence_confidence = (
        "high" if "high" in confidences else ("medium" if "medium" in confidences else "low")
    ) if confidences else "low"
    reviewed = all(by_id[r].reviewed for r in evidence_refs if r in by_id) if evidence_refs else False
    return {
        "documentId": document.document_id,
        "scope": scope,
        "projectId": project_id,
        "artifactType": artifact_type,
        "actionability": actionability,
        "evidenceRefs": evidence_refs,
        "evidenceConfidence": evidence_confidence,
        "reviewStatus": document.review_status,
        "evidenceReviewed": reviewed,
        "sourceMedia": source.video_name,
        "timestampRange": (
            [round(timestamp_range[0], 3), round(timestamp_range[1], 3)] if timestamp_range else None
        ),
        "documentationMode": document.documentation_mode,
    }


def _refs_time_range(evidence_refs: list[str], timeline: EvidenceTimeline) -> tuple[float, float] | None:
    by_id = timeline.by_id()
    stamps = [by_id[r].timestamp_start for r in evidence_refs if r in by_id]
    if not stamps:
        return None
    return min(stamps), max(stamps)


def _build_chunks(
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    source: DocumentationSource,
    scope: str,
    project_id: str | None,
    artifact_type: str,
    actionability: str,
    chunk_max_chars: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    for section in document.sections:
        if not section.summary and not section.claims:
            continue
        base_meta = _chunk_metadata(
            document, source, scope, project_id, artifact_type, actionability,
            list(section.evidence_refs), timeline,
            _refs_time_range(list(section.evidence_refs), timeline),
        )
        base_meta["summaryEvidenceRefs"] = list(section.summary_evidence_refs)
        header = f"[{section.section_type}] {section.title}"

        # Split long sections on claim boundaries, never arbitrary slices.
        parts: list[list[str]] = []
        refs_per_part: list[list[str]] = []
        current: list[str] = [header]
        current_refs: list[str] = list(section.evidence_refs)
        if section.summary:
            current.append(section.summary)
        for claim in section.claims:
            claim_line = f"{claim.text} ({', '.join(claim.evidence_refs)})"
            if len("\n".join(current + [claim_line])) > chunk_max_chars and len(current) > 1:
                parts.append(current)
                refs_per_part.append(sorted(set(current_refs)))
                current = [header]
                current_refs = list(section.evidence_refs)
            current.append(claim_line)
            current_refs.extend(claim.evidence_refs)
        parts.append(current)
        refs_per_part.append(sorted(set(current_refs)))

        for part_index, (part_lines, part_refs) in enumerate(zip(parts, refs_per_part), start=1):
            meta = dict(base_meta)
            meta["sectionId"] = section.id
            meta["sectionType"] = section.section_type
            meta["chunkPart"] = part_index
            meta["evidenceRefs"] = part_refs or list(section.evidence_refs)
            time_range = _refs_time_range(meta["evidenceRefs"], timeline)
            meta["timestampRange"] = [round(time_range[0], 3), round(time_range[1], 3)] if time_range else None
            chunks.append({
                "id": f"{section.id}-c{part_index:02d}",
                "text": "\n".join(part_lines),
                "metadata": meta,
            })

    for procedure in document.procedures:
        refs = sorted(set(procedure.evidence_refs))
        meta = _chunk_metadata(
            document, source, scope, project_id, artifact_type, actionability,
            refs, timeline, _refs_time_range(refs, timeline),
        )
        meta["sectionId"] = procedure.id
        meta["sectionType"] = "PROCEDURE"
        meta["metadataEvidenceRefs"] = list(procedure.metadata_evidence_refs)
        lines = [f"[PROCEDURE] {procedure.title}"]
        if procedure.purpose:
            lines.append(procedure.purpose)
        lines.extend(f"Prerequisite: {value}" for value in procedure.prerequisites)
        for step in procedure.steps:
            lines.append(f"{step.order}. {step.instruction} ({', '.join(step.evidence_refs)})")
        lines.extend(f"Expected outcome: {value}" for value in procedure.expected_outcomes)
        if procedure.metadata_evidence_refs:
            lines.append(f"Evidence: {', '.join(procedure.metadata_evidence_refs)}")
        text = "\n".join(lines)
        if len(text) > chunk_max_chars:
            # Split on step boundaries, not arbitrary slices.
            prefix = [f"[PROCEDURE] {procedure.title}"]
            if procedure.purpose:
                prefix.append(procedure.purpose)
            prefix.extend(f"Prerequisite: {value}" for value in procedure.prerequisites)
            if refs:
                prefix.append(f"Evidence: {', '.join(refs)}")
            part: list[str] = list(prefix)
            for step in procedure.steps:
                line = f"{step.order}. {step.instruction} ({', '.join(step.evidence_refs)})"
                if len("\n".join(part + [line])) > chunk_max_chars and len(part) > 1:
                    chunks.append({
                        "id": f"{procedure.id}-c{len(chunks) + 1:02d}",
                        "text": "\n".join(part),
                        "metadata": meta,
                    })
                    part = [f"[PROCEDURE] {procedure.title} (cont.)", *prefix[1:]]
                part.append(line)
            part.extend(f"Expected outcome: {value}" for value in procedure.expected_outcomes)
            text = "\n".join(part)
        chunks.append({"id": f"{procedure.id}-c{len(chunks) + 1:02d}", "text": text, "metadata": meta})

    return chunks


def _render_knowledge_md(document: KnowledgeDocument, timeline: EvidenceTimeline) -> str:
    lines = [f"# {document.title} — AI knowledge package\n\n"]
    if document.executive_summary:
        refs = " ".join(
            f"[{r} @ {format_timestamp(timeline.by_id()[r].timestamp_start)}]"
            if r in timeline.by_id() else f"[{r}]"
            for r in executive_summary_evidence_refs(document)
        )
        lines.append(f"## Executive Summary\n\n{document.executive_summary} {refs}\n\n")
    for section in document.sections:
        if not section.summary and not section.claims:
            continue
        lines.append(f"## {section.title}\n\n")
        if section.summary:
            summary_refs = " ".join(
                f"[{r} @ {format_timestamp(timeline.by_id()[r].timestamp_start)}]"
                if r in timeline.by_id() else f"[{r}]"
                for r in section.summary_evidence_refs
            )
            lines.append(f"{section.summary} {summary_refs}\n\n")
        for claim in section.claims:
            ts_refs = " ".join(
                f"[{r} @ {format_timestamp(timeline.by_id()[r].timestamp_start)}]" if r in timeline.by_id() else f"[{r}]"
                for r in claim.evidence_refs
            )
            lines.append(f"- {claim.text} {ts_refs}\n")
        lines.append("\n")
    for procedure in document.procedures:
        lines.append(f"## Procedure: {procedure.title}\n\n")
        if procedure.purpose:
            lines.append(f"{procedure.purpose}\n\n")
        if procedure.prerequisites:
            lines.append("Prerequisites: " + "; ".join(procedure.prerequisites) + "\n\n")
        if procedure.metadata_evidence_refs:
            lines.append("Evidence: " + ", ".join(procedure.metadata_evidence_refs) + "\n\n")
        for step in procedure.steps:
            lines.append(f"{step.order}. {step.instruction} ({', '.join(step.evidence_refs)})\n")
        if procedure.expected_outcomes:
            lines.append("Expected outcomes: " + "; ".join(procedure.expected_outcomes) + "\n")
        lines.append("\n")
    if document.glossary:
        lines.append("## Glossary\n\n")
        for entry in document.glossary:
            lines.append(f"- **{entry.term}** — {entry.definition} ({', '.join(entry.evidence_refs)})\n")
    return "".join(lines)
