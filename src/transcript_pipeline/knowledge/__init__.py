"""Knowledge-to-Action producer domain (SPEC-ZO-KNOWLEDGE-001).

Builds Knowledge Package v2 artifacts from completed documentation and
enqueues them on a durable local outbox for a Second Brain publisher.
Raw transcripts/media are never published; only bounded evidence excerpts.
"""
from transcript_pipeline.knowledge.identity import (
    canonical_json,
    package_id_for,
    source_id_for,
    stable_knowledge_id,
)
from transcript_pipeline.knowledge.models import (
    KnowledgeActionability,
    KnowledgeArtifactType,
    KnowledgePackage,
    KnowledgeScope,
    Procedure,
    ProcedureStep,
    StepEvidence,
)
from transcript_pipeline.knowledge.package_builder import build_knowledge_package
from transcript_pipeline.knowledge.policy import validate_publish_context

__all__ = [
    "canonical_json",
    "package_id_for",
    "source_id_for",
    "stable_knowledge_id",
    "KnowledgeActionability",
    "KnowledgeArtifactType",
    "KnowledgeScope",
    "KnowledgePackage",
    "Procedure",
    "ProcedureStep",
    "StepEvidence",
    "build_knowledge_package",
    "validate_publish_context",
]
