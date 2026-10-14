"""Human review primitives for the semantic KnowledgeDocument (PLAN WP-16).

The legacy evidence-step review surface (update_step/remove_step) stays
untouched. This module adds the semantic layer:

- load/save the editable manual/knowledge-document.json (AC-22);
- edit a semantic claim's or section's text/title;
- mark a claim/section HUMAN_REVIEWED ONLY through these explicit local
  review functions — generated content can never do this (DV2-18);
- re-render MANUAL.md/PDF + AI package from the edited document with NO
  upstream work and NO new synthesis call.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from transcript_pipeline.documentation.evidence import EvidenceTimeline
from transcript_pipeline.documentation.knowledge_models import (
    KnowledgeClaim,
    KnowledgeDocument,
    KnowledgeSection,
)
from transcript_pipeline.documentation.models import DocumentationSource


def load_knowledge_document(manual_dir: Path) -> KnowledgeDocument:
    payload = json.loads((manual_dir / "knowledge-document.json").read_text(encoding="utf-8"))
    return KnowledgeDocument.from_dict(payload)


def save_knowledge_document(manual_dir: Path, document: KnowledgeDocument) -> Path:
    manual_dir.mkdir(parents=True, exist_ok=True)
    path = manual_dir / "knowledge-document.json"
    path.write_text(document.to_json(), encoding="utf-8")
    return path


def edit_claim(
    manual_dir: Path,
    claim_id: str,
    *,
    text: str | None = None,
) -> KnowledgeDocument:
    """Edits one claim's text. Editing never grants review status."""
    document = load_knowledge_document(manual_dir)
    new_sections: list[KnowledgeSection] = []
    found = False
    for section in document.sections:
        claims = []
        for claim in section.claims:
            if claim.id == claim_id:
                found = True
                claim = replace(claim, text=text if text is not None else claim.text)
            claims.append(claim)
        new_sections.append(replace(section, claims=tuple(claims)))
    if not found:
        raise KeyError(f"claim {claim_id!r} not found")
    document.sections = new_sections
    save_knowledge_document(manual_dir, document)
    return document


def edit_section(
    manual_dir: Path,
    section_id: str,
    *,
    title: str | None = None,
    summary: str | None = None,
) -> KnowledgeDocument:
    document = load_knowledge_document(manual_dir)
    new_sections = []
    found = False
    for section in document.sections:
        if section.id == section_id:
            found = True
            section = replace(
                section,
                title=title if title is not None else section.title,
                summary=summary if summary is not None else section.summary,
            )
        new_sections.append(section)
    if not found:
        raise KeyError(f"section {section_id!r} not found")
    document.sections = new_sections
    save_knowledge_document(manual_dir, document)
    return document


def mark_claim_reviewed(manual_dir: Path, claim_id: str) -> KnowledgeDocument:
    """EXPLICIT human review action (the only path to HUMAN_REVIEWED)."""
    document = load_knowledge_document(manual_dir)
    new_sections: list[KnowledgeSection] = []
    found = False
    for section in document.sections:
        claims: list[KnowledgeClaim] = []
        for claim in section.claims:
            if claim.id == claim_id:
                found = True
                claim = replace(claim, verification_status="HUMAN_REVIEWED")
            claims.append(claim)
        new_sections.append(replace(section, claims=tuple(claims)))
    if not found:
        raise KeyError(f"claim {claim_id!r} not found")
    document.sections = new_sections
    document.review_status = (
        "HUMAN_REVIEWED"
        if all(
            claim.verification_status == "HUMAN_REVIEWED"
            for section in new_sections for claim in section.claims
        ) and new_sections
        else document.review_status
    )
    save_knowledge_document(manual_dir, document)
    return document


def rerender_from_document(
    manual_dir: Path,
    ai_package_dir: Path,
    frames_dir: Path,
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    source: DocumentationSource | None = None,
    *,
    project_config: dict | None = None,
) -> dict:
    """Re-renders MANUAL.md/PDF + the AI package from an edited semantic
    document. No upstream work, no synthesis call, no evidence rewrite."""
    from transcript_pipeline.documentation.screenshots import select_screenshots
    from transcript_pipeline.documentation.semantic_manual_writer import write_semantic_manual
    from transcript_pipeline.documentation.semantic_package import write_semantic_ai_package

    if source is None:
        source = DocumentationSource(
            video_name=document.source or timeline.source_media,
            duration=timeline.duration,
            language=timeline.language,
            extraction_method="regenerated",
            generated_at=document.synthesis.generated_at,
        )

    selection = select_screenshots(document, timeline, frames_dir)
    metadata = write_semantic_manual(manual_dir, document, timeline, frames_dir, selection, source)
    package_result = write_semantic_ai_package(
        ai_package_dir, document, timeline, selection, source, project_config=project_config
    )
    return {"manual": metadata, "ai_package": package_result}
