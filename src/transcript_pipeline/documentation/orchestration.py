"""V2 pipeline orchestration.

Explicit staged result:
1. load persisted evidence
2. create evidence timeline
3. resolve mode
4. synthesize if allowed
5. validate grounding
6. select screenshots
7. write semantic manual/package
8. publish semantic Knowledge Package when enabled.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.classifier import resolve_documentation_mode
from transcript_pipeline.documentation.evidence import build_evidence_timeline
from transcript_pipeline.documentation.evidence_writer import write_evidence_timeline
from transcript_pipeline.documentation.synthesis import synthesize
from transcript_pipeline.documentation.grounding import validate_grounding
from transcript_pipeline.documentation.screenshots import select_representative_screenshots
from transcript_pipeline.documentation.semantic_manual_writer import write_semantic_manual
from transcript_pipeline.documentation.ai_package_v2 import write_semantic_ai_package
from transcript_pipeline.knowledge.package_builder import build_knowledge_package_from_document


def generate_documentation_v2(
    frames_dir: Path,
    video_name: str,
    manual_dir: Path | None = None,
    ai_package_dir: Path | None = None,
    evidence_dir: Path | None = None,
    project_config: dict | None = None,
) -> dict:
    """V2 documentation pipeline.
    
    Returns result dict with typed status.
    """
    mapping_path = frames_dir / "frame_mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(f"frame_mapping.json not found in {frames_dir}")
    
    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    
    # 1. Load persisted evidence
    # Already have mapping_data
    
    # 2. Create evidence timeline
    timeline = build_evidence_timeline(mapping_data, frames_dir, project_config)
    
    # 3. Write evidence artifacts
    manual_dir = manual_dir or (frames_dir / "manual")
    evidence_dir = evidence_dir or (frames_dir / "evidence")
    evidence_summary = write_evidence_timeline(timeline, frames_dir, manual_dir, evidence_dir)
    
    # 4. Resolve mode
    mode, reason = resolve_documentation_mode(project_config)
    
    # 5. Synthesize if allowed
    synthesis_result = synthesize(
        evidence_timeline=timeline,
        mode=mode.value,
        project_config=project_config,
    )
    
    if synthesis_result.status != "success":
        return {
            "status": synthesis_result.status,
            "error": synthesis_result.error,
            "evidence_ready": True,
            "evidence_summary": evidence_summary,
        }
    
    knowledge_document = synthesis_result.knowledge_document
    
    # 6. Validate grounding
    # TODO: build evidence index dict from timeline
    evidence_index = {}
    validation_errors = validate_grounding(knowledge_document, evidence_index)
    if validation_errors:
        return {
            "status": "synthesis_invalid",
            "validation_errors": validation_errors,
            "evidence_ready": True,
        }
    
    # 7. Select screenshots
    # TODO: implement screenshot mapping
    
    # 8. Write semantic manual/package
    write_semantic_manual(manual_dir, knowledge_document, {}, evidence_summary.get("low_confidence_count", 0))
    write_semantic_ai_package(ai_package_dir or (frames_dir / "ai-package"), knowledge_document, evidence_index)
    
    # 9. Publish semantic Knowledge Package when enabled
    package = build_knowledge_package_from_document(
        knowledge_document=knowledge_document,
        evidence_timeline=timeline,
        project_config=project_config,
    )
    
    publish_status = "published" if package else "second_brain_disabled"
    
    return {
        "status": "ready",
        "evidence_ready": True,
        "synthesis_ready": True,
        "manual_ready": True,
        "package_ready": True,
        "publish_status": publish_status,
        "evidence_summary": evidence_summary,
    }