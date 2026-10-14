"""AI package V2.

Generates semantic knowledge.md and chunks.jsonl from KnowledgeDocument.
"""

from __future__ import annotations

import json
from pathlib import Path

from transcript_pipeline.documentation.synthesis_models import KnowledgeDocument


def write_semantic_ai_package(
    ai_package_dir: Path,
    knowledge_document: KnowledgeDocument,
    evidence_index: dict,
) -> None:
    """Write semantic AI package."""
    assets_dir = ai_package_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # Write knowledge.md
    knowledge_lines = [f"# {knowledge_document.title}\n\n"]
    for section in knowledge_document.sections:
        knowledge_lines.append(f"## {section.title}\n\n{section.summary}\n\n")
        for claim in section.claims:
            knowledge_lines.append(f"- {claim.text}\n")
        knowledge_lines.append("\n")
    
    (ai_package_dir / "knowledge.md").write_text("".join(knowledge_lines), encoding="utf-8")
    
    # Write chunks.jsonl
    chunks = []
    chunk_id = 0
    for section in knowledge_document.sections:
        # One chunk per section (or split by claims if large)
        chunk_text = f"{section.title}\n{section.summary}"
        if section.claims:
            chunk_text += "\n\nClaims:\n" + "\n".join(c.text for c in section.claims)
        
        chunks.append({
            "id": f"chunk-{chunk_id}",
            "text": chunk_text,
            "metadata": {
                "sectionId": section.id,
                "sectionType": section.sectionType,
                "evidenceRefs": section.evidenceRefs,
                "confidence": "high",  # TODO: compute from evidence
                "reviewStatus": "UNREVIEWED",
            },
        })
        chunk_id += 1
    
    lines = [json.dumps(chunk, ensure_ascii=False) for chunk in chunks]
    (ai_package_dir / "chunks.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    
    # Write manifest
    manifest = {
        "schema_version": "2",
        "knowledge_document_id": "TODO",
        "sections": len(knowledge_document.sections),
        "procedures": len(knowledge_document.procedures),
    }
    (ai_package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Copy evidence.jsonl from evidence dir (placeholder)
    # Write procedure.json only if procedures exist
    if knowledge_document.procedures:
        procedure_data = [
            {
                "id": proc.id,
                "title": proc.title,
                "steps": [
                    {
                        "order": step.order,
                        "instruction": step.instruction,
                        "evidenceRefs": step.evidenceRefs,
                    }
                    for step in proc.steps
                ],
            }
            for proc in knowledge_document.procedures
        ]
        (ai_package_dir / "procedure.json").write_text(
            json.dumps(procedure_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )