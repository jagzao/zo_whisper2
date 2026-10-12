"""Typed Knowledge Package v2 / Procedure v1 models (SPEC §3/§4).

These are plain JSON-serializable value objects: the package crosses a
process/repository boundary (Zo -> Zavi), so the wire shape is frozen by the
spec and must stay dict-stable (no dataclass asdict surprises, no runtime
defaults that silently change the contract).
"""
from __future__ import annotations

from typing import Any, Literal

KnowledgeScope = Literal["PROJECT", "GLOBAL"]
KnowledgeActionability = Literal["REFERENCE", "GUIDED", "EXECUTABLE"]
KnowledgeArtifactType = Literal[
    "TUTORIAL",
    "PROCEDURE",
    "KT",
    "TROUBLESHOOTING",
    "INCIDENT",
    "POLICY",
    "DECISION",
    "APPLICATION",
    "REFERENCE",
]

KNOWLEDGE_SCOPES: tuple[str, ...] = ("PROJECT", "GLOBAL")
KNOWLEDGE_ACTIONABILITY_VALUES: tuple[str, ...] = ("REFERENCE", "GUIDED", "EXECUTABLE")
KNOWLEDGE_ARTIFACT_TYPES: tuple[str, ...] = (
    "TUTORIAL",
    "PROCEDURE",
    "KT",
    "TROUBLESHOOTING",
    "INCIDENT",
    "POLICY",
    "DECISION",
    "APPLICATION",
    "REFERENCE",
)

# Whole-transcript/VTT payloads are forbidden inside evidence; only bounded
# excerpts are allowed (SPEC §4: "bounded evidence excerpts are allowed;
# whole raw transcript is not").
MAX_EVIDENCE_EXCERPT_CHARS = 1200


def bound_excerpt(text: str | None, limit: int = MAX_EVIDENCE_EXCERPT_CHARS) -> str | None:
    """Clips an evidence excerpt to the frozen bound; None stays None."""
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit]


class StepEvidence:
    """Bounded, reviewable evidence grounding one procedure step."""

    def __init__(
        self,
        *,
        transcript_excerpt: str | None = None,
        ocr_text: str | None = None,
        frame_ref: str | None = None,
        source_segment_index: int | None = None,
        confidence: str = "low",
        reviewed: bool = False,
    ) -> None:
        self.transcript_excerpt = bound_excerpt(transcript_excerpt)
        self.ocr_text = bound_excerpt(ocr_text)
        self.frame_ref = frame_ref
        self.source_segment_index = source_segment_index
        self.confidence = confidence
        self.reviewed = reviewed

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcriptExcerpt": self.transcript_excerpt,
            "ocrText": self.ocr_text,
            "frameRef": self.frame_ref,
            "sourceSegmentIndex": self.source_segment_index,
            "confidence": self.confidence,
            "reviewed": self.reviewed,
        }


class ProcedureStep:
    """One observed step. semanticAction/semanticTarget stay null unless a
    binding is explicitly known — Zo never invents executable tool calls."""

    def __init__(
        self,
        *,
        id: str,
        order: int,
        instruction: str,
        timestamp: float | None = None,
        evidence: StepEvidence | None = None,
        semantic_action: str | None = None,
        semantic_target: str | None = None,
    ) -> None:
        self.id = id
        self.order = order
        self.instruction = instruction
        self.timestamp = timestamp
        self.evidence = evidence or StepEvidence()
        self.semantic_action = semantic_action
        self.semantic_target = semantic_target

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order": self.order,
            "instruction": self.instruction,
            "timestamp": self.timestamp,
            "evidence": self.evidence.to_dict(),
            "semanticAction": self.semantic_action,
            "semanticTarget": self.semantic_target,
        }


class Procedure:
    """Procedure v1 (SPEC §4) — emitted as `ai-package/procedure.json`."""

    def __init__(
        self,
        *,
        procedure_id: str,
        knowledge_id: str,
        version: int,
        scope: str,
        project_id: str | None,
        actionability: str,
        title: str,
        steps: list[ProcedureStep],
        parameters: list[dict[str, Any]] | None = None,
        preconditions: list[str] | None = None,
        expected_outcomes: list[str] | None = None,
    ) -> None:
        self.schema_version = 1
        self.procedure_id = procedure_id
        self.knowledge_id = knowledge_id
        self.version = version
        self.scope = scope
        self.project_id = project_id
        self.actionability = actionability
        self.title = title
        self.steps = steps
        self.parameters = parameters or []
        self.preconditions = preconditions or []
        self.expected_outcomes = expected_outcomes or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "procedureId": self.procedure_id,
            "knowledgeId": self.knowledge_id,
            "version": self.version,
            "scope": self.scope,
            "projectId": self.project_id,
            "actionability": self.actionability,
            "title": self.title,
            "parameters": self.parameters,
            "steps": [step.to_dict() for step in self.steps],
            "preconditions": self.preconditions,
            "expectedOutcomes": self.expected_outcomes,
        }


class KnowledgePackage:
    """Knowledge Package v2 (SPEC §3)."""

    def __init__(
        self,
        *,
        package_id: str,
        knowledge_id: str,
        version: int,
        scope: str,
        project_id: str | None,
        domain: str,
        artifact_type: str,
        actionability: str,
        data_classification: str,
        source: dict[str, Any],
        provenance: dict[str, Any],
        knowledge: dict[str, Any],
        evidence: list[dict[str, Any]] | None = None,
        supersedes_knowledge_id: str | None = None,
        status: str = "ACTIVE",
    ) -> None:
        self.schema_version = 2
        self.package_id = package_id
        self.knowledge_id = knowledge_id
        self.version = version
        self.scope = scope
        self.project_id = project_id
        self.domain = domain
        self.artifact_type = artifact_type
        self.actionability = actionability
        self.data_classification = data_classification
        self.status = status
        self.source = source
        self.provenance = provenance
        self.knowledge = knowledge
        self.evidence = evidence or []
        self.supersedes_knowledge_id = supersedes_knowledge_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "packageId": self.package_id,
            "knowledgeId": self.knowledge_id,
            "version": self.version,
            "scope": self.scope,
            "projectId": self.project_id,
            "domain": self.domain,
            "artifactType": self.artifact_type,
            "actionability": self.actionability,
            "dataClassification": self.data_classification,
            "status": self.status,
            "source": self.source,
            "provenance": self.provenance,
            "knowledge": self.knowledge,
            "evidence": self.evidence,
            "supersedesKnowledgeId": self.supersedes_knowledge_id,
        }
