"""Documentation mode resolver.

Resolution order (SPEC §2):
1. explicit project `documentation.mode`
2. explicit `second_brain.default_artifact_type` mapping
3. optional allowed synthesis classifier when mode=AUTO
4. safe fallback REFERENCE

Modes are independent from cross-repo KnowledgeArtifactType.
"""

from __future__ import annotations

from typing import Literal

from transcript_pipeline.documentation.models import DocumentationMode

ClassifierResult = Literal[
    "TUTORIAL", "KT_SESSION", "PROCESS_WALKTHROUGH",
    "MEETING", "ARCHITECTURE", "INCIDENT", "REFERENCE"
]


def resolve_documentation_mode(
    project_config: dict | None,
    evidence_timeline: dict | None = None,
) -> tuple[DocumentationMode, str | None]:
    """Determine documentation mode.
    
    Returns (mode, reason).
    Reason can be 'explicit', 'artifact_mapping', 'classifier', 'fallback'.
    """
    if project_config and "documentation" in project_config:
        doc_config = project_config["documentation"]
        if isinstance(doc_config, dict) and "mode" in doc_config:
            mode_str = doc_config["mode"]
            try:
                mode = DocumentationMode(mode_str)
                return mode, "explicit"
            except ValueError:
                # invalid mode falls through
                pass
    
    # Map default_artifact_type from second_brain config
    if project_config and "second_brain" in project_config:
        sb = project_config["second_brain"]
        if isinstance(sb, dict) and "default_artifact_type" in sb:
            artifact = sb["default_artifact_type"]
            mapping = {
                "TUTORIAL": DocumentationMode.TUTORIAL,
                "KT": DocumentationMode.KT_SESSION,
                "PROCEDURE": DocumentationMode.PROCESS_WALKTHROUGH,
                "INCIDENT": DocumentationMode.INCIDENT,
                "APPLICATION": DocumentationMode.ARCHITECTURE,
                "REFERENCE": DocumentationMode.REFERENCE,
                # others map to REFERENCE
            }
            mode = mapping.get(artifact, DocumentationMode.REFERENCE)
            return mode, "artifact_mapping"
    
    # If mode is AUTO (or unspecified) and classifier available
    # For now, no classifier implemented
    # Fallback to REFERENCE
    return DocumentationMode.REFERENCE, "fallback"


def classifier_available() -> bool:
    """Check if a classifier provider is configured and allowed."""
    # Not implemented in this epic
    return False


def classify_from_evidence(evidence_timeline: dict) -> ClassifierResult:
    """Stub classifier.
    
    In future, could examine compact textual evidence to infer mode.
    """
    # Always return REFERENCE for safety
    return "REFERENCE"