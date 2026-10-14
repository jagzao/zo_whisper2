"""Semantic Knowledge Plane models (SPEC §4, PLAN WP-06).

Typed, deterministically serializable synthesis domain:

- KnowledgeClaim        — factual claim, >=1 evidence ref REQUIRED;
- KnowledgeSection      — semantic section with claims + evidence refs;
- SynthesizedProcedure  — only when the source supports ordered actions;
- SynthesizedStep       — procedure step, evidence-grounded;
- SynthesisMetadata     — compact provider/model metadata, no secrets;
- KnowledgeDocument     — the V2 document consumed by MANUAL/AI package.

The model may never mark its own output HUMAN_REVIEWED: `verificationStatus`
is coerced to SYNTHESIZED_UNREVIEWED at parse time (SPEC §5.6, DV2-18), and
only the explicit local review API (documentation/review.py) may set
HUMAN_REVIEWED afterwards.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from transcript_pipeline.documentation.modes import (
    CONFIDENCE_LEVELS,
    SECTION_TYPES,
    VERIFICATION_STATUSES,
)

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class KnowledgeClaim:
    id: str
    text: str
    evidence_refs: tuple[str, ...]
    evidence_confidence: str = "low"
    verification_status: str = "SYNTHESIZED_UNREVIEWED"
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "evidenceRefs": list(self.evidence_refs),
            "evidenceConfidence": self.evidence_confidence,
            "verificationStatus": self.verification_status,
            "tags": list(self.tags),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> KnowledgeClaim:
        return KnowledgeClaim(
            id=str(data["id"]),
            text=str(data.get("text", "")),
            evidence_refs=tuple(data.get("evidenceRefs", [])),
            evidence_confidence=data.get("evidenceConfidence", "low"),
            verification_status=data.get("verificationStatus", "SYNTHESIZED_UNREVIEWED"),
            tags=tuple(data.get("tags", [])),
        )


@dataclass(frozen=True)
class KnowledgeSection:
    id: str
    section_type: str
    title: str
    summary: str = ""
    claims: tuple[KnowledgeClaim, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    screenshot_candidates: tuple[str, ...] = ()
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sectionType": self.section_type,
            "title": self.title,
            "summary": self.summary,
            "claims": [claim.to_dict() for claim in self.claims],
            "evidenceRefs": list(self.evidence_refs),
            "screenshotCandidates": list(self.screenshot_candidates),
            "order": self.order,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> KnowledgeSection:
        return KnowledgeSection(
            id=str(data["id"]),
            section_type=str(data.get("sectionType", "REFERENCE")),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            claims=tuple(KnowledgeClaim.from_dict(c) for c in data.get("claims", [])),
            evidence_refs=tuple(data.get("evidenceRefs", [])),
            screenshot_candidates=tuple(data.get("screenshotCandidates", [])),
            order=int(data.get("order", 0)),
        )


@dataclass(frozen=True)
class SynthesizedStep:
    order: int
    instruction: str
    evidence_refs: tuple[str, ...]
    semantic_action: str | None = None
    semantic_target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "instruction": self.instruction,
            "evidenceRefs": list(self.evidence_refs),
            "semanticAction": self.semantic_action,
            "semanticTarget": self.semantic_target,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SynthesizedStep:
        return SynthesizedStep(
            order=int(data.get("order", 0)),
            instruction=str(data.get("instruction", "")),
            evidence_refs=tuple(data.get("evidenceRefs", [])),
            semantic_action=data.get("semanticAction"),
            semantic_target=data.get("semanticTarget"),
        )


@dataclass(frozen=True)
class SynthesizedProcedure:
    id: str
    title: str
    purpose: str = ""
    prerequisites: tuple[str, ...] = ()
    steps: tuple[SynthesizedStep, ...] = ()
    expected_outcomes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    actionability: str = "GUIDED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "purpose": self.purpose,
            "prerequisites": list(self.prerequisites),
            "steps": [step.to_dict() for step in self.steps],
            "expectedOutcomes": list(self.expected_outcomes),
            "evidenceRefs": list(self.evidence_refs),
            "actionability": self.actionability,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SynthesizedProcedure:
        return SynthesizedProcedure(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            purpose=str(data.get("purpose", "")),
            prerequisites=tuple(data.get("prerequisites", [])),
            steps=tuple(SynthesizedStep.from_dict(s) for s in data.get("steps", [])),
            expected_outcomes=tuple(data.get("expectedOutcomes", [])),
            evidence_refs=tuple(data.get("evidenceRefs", [])),
            actionability=str(data.get("actionability", "GUIDED")),
        )


@dataclass(frozen=True)
class SynthesisMetadata:
    provider_type: str = "unknown"
    model: str = "unknown"
    generated_at: str = ""
    status: str = "SYNTHESIZED_UNREVIEWED"
    input_hash: str = ""
    invocation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        # Compact, no secrets: provider type + model name only.
        return {
            "providerType": self.provider_type,
            "model": self.model,
            "generatedAt": self.generated_at,
            "status": self.status,
            "inputHash": self.input_hash,
            "invocationCount": self.invocation_count,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SynthesisMetadata:
        return SynthesisMetadata(
            provider_type=str(data.get("providerType", "unknown")),
            model=str(data.get("model", "unknown")),
            generated_at=str(data.get("generatedAt", "")),
            status=str(data.get("status", "SYNTHESIZED_UNREVIEWED")),
            input_hash=str(data.get("inputHash", "")),
            invocation_count=int(data.get("invocationCount", 0)),
        )


@dataclass
class GlossaryEntry:
    term: str
    definition: str
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"term": self.term, "definition": self.definition, "evidenceRefs": list(self.evidence_refs)}


@dataclass
class KnowledgeDocument:
    schema_version: int = SCHEMA_VERSION
    document_id: str = ""
    source: str = ""
    documentation_mode: str = "REFERENCE"
    title: str = ""
    purpose: str | None = None
    executive_summary: str = ""
    sections: list[KnowledgeSection] = field(default_factory=list)
    procedures: list[SynthesizedProcedure] = field(default_factory=list)
    glossary: list[GlossaryEntry] = field(default_factory=list)
    evidence_index: list[dict[str, Any]] = field(default_factory=list)
    synthesis: SynthesisMetadata = field(default_factory=SynthesisMetadata)
    review_status: str = "SYNTHESIZED_UNREVIEWED"

    def all_evidence_refs(self) -> set[str]:
        refs: set[str] = set()
        for section in self.sections:
            refs.update(section.evidence_refs)
            for claim in section.claims:
                refs.update(claim.evidence_refs)
        for procedure in self.procedures:
            refs.update(procedure.evidence_refs)
            for step in procedure.steps:
                refs.update(step.evidence_refs)
        return refs

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "documentId": self.document_id,
            "source": self.source,
            "documentationMode": self.documentation_mode,
            "title": self.title,
            "purpose": self.purpose,
            "executiveSummary": self.executive_summary,
            "sections": [section.to_dict() for section in self.sections],
            "procedures": [procedure.to_dict() for procedure in self.procedures],
            "glossary": [entry.to_dict() for entry in self.glossary],
            "evidenceIndex": list(self.evidence_index),
            "synthesis": self.synthesis.to_dict(),
            "reviewStatus": self.review_status,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> KnowledgeDocument:
        return KnowledgeDocument(
            schema_version=int(data.get("schemaVersion", SCHEMA_VERSION)),
            document_id=str(data.get("documentId", "")),
            source=str(data.get("source", "")),
            documentation_mode=str(data.get("documentationMode", "REFERENCE")),
            title=str(data.get("title", "")),
            purpose=data.get("purpose"),
            executive_summary=str(data.get("executiveSummary", "")),
            sections=[KnowledgeSection.from_dict(s) for s in data.get("sections", [])],
            procedures=[SynthesizedProcedure.from_dict(p) for p in data.get("procedures", [])],
            glossary=[
                GlossaryEntry(term=str(e.get("term", "")), definition=str(e.get("definition", "")),
                              evidence_refs=tuple(e.get("evidenceRefs", [])))
                for e in data.get("glossary", [])
            ],
            evidence_index=list(data.get("evidenceIndex", [])),
            synthesis=SynthesisMetadata.from_dict(data.get("synthesis", {})),
            review_status=str(data.get("reviewStatus", "SYNTHESIZED_UNREVIEWED")),
        )

    def to_json(self, *, indent: int | None = 2) -> str:
        """Deterministic, versioned serialization."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=False)

    @staticmethod
    def from_json(text: str) -> KnowledgeDocument:
        return KnowledgeDocument.from_dict(json.loads(text))

    def semantic_hash(self) -> str:
        """Content identity over the semantic payload, excluding
        synthesis.generatedAt (DV2-37: timestamp changes alone never create
        a new knowledge version)."""
        import hashlib

        payload = self.to_dict()
        synthesis = dict(payload.get("synthesis", {}))
        synthesis.pop("generatedAt", None)
        payload["synthesis"] = synthesis
        payload.pop("documentId", None)
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def coerce_generated_claim(claim: KnowledgeClaim) -> KnowledgeClaim:
    """Model-provided authority coercion (SPEC §5.6): generated claims are
    always SYNTHESIZED_UNREVIEWED; confidence clipped to the frozen enum."""
    status = claim.verification_status if claim.verification_status in VERIFICATION_STATUSES else "SYNTHESIZED_UNREVIEWED"
    if status == "HUMAN_REVIEWED":
        status = "SYNTHESIZED_UNREVIEWED"
    confidence = claim.evidence_confidence if claim.evidence_confidence in CONFIDENCE_LEVELS else "low"
    return replace(claim, verification_status=status, evidence_confidence=confidence)


def coerce_section_type(section_type: str) -> str | None:
    value = str(section_type or "").strip().upper()
    return value if value in SECTION_TYPES else None
