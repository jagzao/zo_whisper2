"""DocumentationMode and section-type contracts (SPEC-ZMI-DOCS-V2-001 §2/§4/§8).

Typed documentation-domain constants. Deliberately independent from the
cross-repo `KnowledgeArtifactType` enum: human document shape and knowledge
artifact type are related but not identical (EPIC-ZMI-DOCS-V2-001).
"""
from __future__ import annotations

from typing import Any

DOCUMENTATION_MODES: tuple[str, ...] = (
    "AUTO",
    "TUTORIAL",
    "KT_SESSION",
    "PROCESS_WALKTHROUGH",
    "MEETING",
    "ARCHITECTURE",
    "INCIDENT",
    "REFERENCE",
)

SECTION_TYPES: tuple[str, ...] = (
    "EXECUTIVE_SUMMARY",
    "CONTEXT_SCOPE",
    "GOAL",
    "PREREQUISITES",
    "CONCEPT",
    "PROCESS",
    "PROCEDURE",
    "SYSTEM",
    "ROLE_RESPONSIBILITY",
    "DECISION",
    "RISK",
    "OPEN_QUESTION",
    "ACTION_ITEM",
    "TROUBLESHOOTING",
    "ARCHITECTURE_COMPONENT",
    "DEPENDENCY",
    "DATA_FLOW",
    "EXPECTED_RESULT",
    "GLOSSARY",
    "REFERENCE",
)

EVIDENCE_SOURCES: tuple[str, ...] = ("transcript", "ocr", "transcript_ocr", "frame", "none")
CONFIDENCE_LEVELS: tuple[str, ...] = ("high", "medium", "low")
VERIFICATION_STATUSES: tuple[str, ...] = ("SYNTHESIZED_UNREVIEWED", "HUMAN_REVIEWED")

# Documentation result status values (SPEC §15).
DOCUMENTATION_STATUSES: tuple[str, ...] = (
    "EVIDENCE_READY",
    "SYNTHESIS_READY",
    "SYNTHESIS_NOT_AVAILABLE",
    "SYNTHESIS_BLOCKED_PRIVACY",
    "SYNTHESIS_INVALID",
    "MANUAL_READY",
    "PUBLISH_ENQUEUED",
    "PUBLISH_ACK",
    "PUBLISH_PENDING_RETRY",
)

# ── Config block (SPEC §2 defaults) ──────────────────────────────────────

DEFAULT_DOCUMENTATION_CONFIG: dict[str, Any] = {
    "mode": "AUTO",
    "synthesis_enabled": True,
    "max_screenshots": 24,
    "max_screenshots_per_section": 2,
}


def normalize_documentation_config(
    documentation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Returns the effective `documentation` config with SPEC defaults
    applied. Values already validated upstream (projects.validate_project);
    unknown keys are ignored, never invented."""
    cfg = dict(DEFAULT_DOCUMENTATION_CONFIG)
    if isinstance(documentation, dict):
        if documentation.get("mode") in DOCUMENTATION_MODES:
            cfg["mode"] = documentation["mode"]
        if isinstance(documentation.get("synthesis_enabled"), bool):
            cfg["synthesis_enabled"] = documentation["synthesis_enabled"]
        for key in ("max_screenshots", "max_screenshots_per_section"):
            value = documentation.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                cfg[key] = value
    return cfg


def validate_documentation_block(project: dict) -> list[str]:
    """Validation rules for the optional `documentation` block (SPEC §2):

    - absent -> defaults apply (legacy projects stay valid);
    - unknown mode values rejected;
    - non-positive screenshot bounds rejected;
    - synthesis_enabled must be a boolean.

    Filename suffixes are never an authoritative mode and are not read here.
    """
    documentation = project.get("documentation")
    if documentation is None:
        return []

    if not isinstance(documentation, dict):
        return ["'documentation' must be an object"]

    errors: list[str] = []
    mode = documentation.get("mode")
    if mode is not None:
        if not isinstance(mode, str) or mode not in DOCUMENTATION_MODES:
            errors.append(f"'documentation.mode' must be one of {list(DOCUMENTATION_MODES)}")

    synthesis_enabled = documentation.get("synthesis_enabled")
    if synthesis_enabled is not None and not isinstance(synthesis_enabled, bool):
        errors.append("'documentation.synthesis_enabled' must be a boolean")

    for key in ("max_screenshots", "max_screenshots_per_section"):
        value = documentation.get(key)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(f"'documentation.{key}' must be a positive integer")

    return errors


# ── Mode templates (SPEC §8 preferred section order) ─────────────────────

MODE_SECTION_TEMPLATES: dict[str, tuple[str, ...]] = {
    "TUTORIAL": (
        "EXECUTIVE_SUMMARY",
        "GOAL",
        "PREREQUISITES",
        "PROCEDURE",
        "EXPECTED_RESULT",
        "TROUBLESHOOTING",
        "GLOSSARY",
    ),
    "KT_SESSION": (
        "EXECUTIVE_SUMMARY",
        "CONTEXT_SCOPE",
        "CONCEPT",
        "PROCESS",
        "SYSTEM",
        "ROLE_RESPONSIBILITY",
        "DECISION",
        "RISK",
        "OPEN_QUESTION",
        "ACTION_ITEM",
        "GLOSSARY",
    ),
    "PROCESS_WALKTHROUGH": (
        "EXECUTIVE_SUMMARY",
        "CONTEXT_SCOPE",
        "PREREQUISITES",
        "ROLE_RESPONSIBILITY",
        "PROCESS",
        "PROCEDURE",
        "REFERENCE",
        "EXPECTED_RESULT",
        "TROUBLESHOOTING",
    ),
    "MEETING": (
        "EXECUTIVE_SUMMARY",
        "CONTEXT_SCOPE",
        "DECISION",
        "ACTION_ITEM",
        "RISK",
        "OPEN_QUESTION",
        "REFERENCE",
    ),
    "ARCHITECTURE": (
        "EXECUTIVE_SUMMARY",
        "CONTEXT_SCOPE",
        "ARCHITECTURE_COMPONENT",
        "DEPENDENCY",
        "DATA_FLOW",
        "SYSTEM",
        "RISK",
        "REFERENCE",
    ),
    "INCIDENT": (
        "EXECUTIVE_SUMMARY",
        "CONTEXT_SCOPE",
        "PROCESS",
        "SYSTEM",
        "REFERENCE",
        "ACTION_ITEM",
        "TROUBLESHOOTING",
    ),
    "REFERENCE": (
        "EXECUTIVE_SUMMARY",
        "CONCEPT",
        "REFERENCE",
        "GLOSSARY",
    ),
    "AUTO": (
        "EXECUTIVE_SUMMARY",
        "CONTEXT_SCOPE",
        "CONCEPT",
        "PROCESS",
        "REFERENCE",
    ),
}

SECTION_TYPE_ORDER: dict[str, int] = {section_type: index for index, section_type in enumerate(SECTION_TYPES)}

# Preferred section order for a resolved mode; unknown section types sort last.
def section_sort_key(mode: str, section_type: str) -> tuple[int, int]:
    template = MODE_SECTION_TEMPLATES.get(mode, MODE_SECTION_TEMPLATES["AUTO"])
    if section_type in template:
        return (template.index(section_type), SECTION_TYPE_ORDER.get(section_type, len(SECTION_TYPES)))
    return (len(template), SECTION_TYPE_ORDER.get(section_type, len(SECTION_TYPES)))


# ── DocumentationMode <-> cross-repo KnowledgeArtifactType mapping ────────
# EPIC "Mapping defaults". No automatic cross-repo enum expansion is required.

MODE_FOR_ARTIFACT_TYPE: dict[str, str] = {
    "TUTORIAL": "TUTORIAL",
    "KT": "KT_SESSION",
    "PROCEDURE": "PROCESS_WALKTHROUGH",
    "TROUBLESHOOTING": "PROCESS_WALKTHROUGH",
    "INCIDENT": "INCIDENT",
    "POLICY": "REFERENCE",
    "DECISION": "MEETING",
    "APPLICATION": "REFERENCE",
    "REFERENCE": "REFERENCE",
}

ARTIFACT_TYPE_FOR_MODE: dict[str, str] = {
    "AUTO": "REFERENCE",
    "TUTORIAL": "TUTORIAL",
    "KT_SESSION": "KT",
    "PROCESS_WALKTHROUGH": "PROCEDURE",
    "MEETING": "REFERENCE",
    "ARCHITECTURE": "REFERENCE",
    "INCIDENT": "INCIDENT",
    "REFERENCE": "REFERENCE",
}
