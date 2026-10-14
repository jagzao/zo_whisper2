"""Semantic Markdown writer.

V2 MANUAL.md reads KnowledgeDocument.
Renders mode-appropriate sections.
"""

from __future__ import annotations

from pathlib import Path

from transcript_pipeline.documentation.synthesis_models import KnowledgeDocument


def write_semantic_manual(
    manual_dir: Path,
    knowledge_document: KnowledgeDocument,
    screenshot_map: dict[str, str],  # evidence id -> screenshot path
    review_queue_count: int,
) -> None:
    """Write MANUAL.md from KnowledgeDocument."""
    lines = [f"# {knowledge_document.title}\n\n"]
    
    if knowledge_document.executiveSummary:
        lines.append(f"## Executive Summary\n\n{knowledge_document.executiveSummary}\n\n")
    
    if review_queue_count > 0:
        lines.append(
            f"> ⚠ {review_queue_count} evidence item(s) require review before trusting.\n\n"
        )
    
    for section in knowledge_document.sections:
        lines.append(f"## {section.title}\n\n")
        lines.append(f"{section.summary}\n\n")
        
        for claim in section.claims:
            # Show evidence references
            refs = ", ".join(f"[{ref}]" for ref in claim.evidenceRefs)
            lines.append(f"- {claim.text} ({refs})\n")
        
        # Add representative screenshots for this section
        screenshot_paths = [
            screenshot_map[ref] for ref in section.screenshotCandidates
            if ref in screenshot_map
        ]
        for path in screenshot_paths[:2]:  # cap per section
            lines.append(f"![{path}](assets/{Path(path).name})\n")
        
        lines.append("\n")
    
    # Add glossary if present
    if knowledge_document.glossary:
        lines.append("## Glossary\n\n")
        for entry in knowledge_document.glossary:
            lines.append(f"**{entry['term']}**: {entry['definition']}\n")
        lines.append("\n")
    
    # Evidence index appendix
    lines.append("## Evidence Index\n\n")
    for idx, evidence in enumerate(knowledge_document.evidenceIndex, start=1):
        lines.append(f"{idx}. {evidence.get('evidenceId')} - {evidence.get('timestampStart')}s\n")
    
    (manual_dir / "MANUAL.md").write_text("".join(lines), encoding="utf-8")