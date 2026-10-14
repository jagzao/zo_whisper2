"""Knowledge Package v2 builder (SPEC §3, PLAN WP-02/WP-04).

One builder for every producer path: the standard documentation pipeline AND
the K'ab consolidated-session path call this same function — there is no
second knowledge implementation anywhere in Zo (PLAN WP-04).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep
from transcript_pipeline.knowledge.identity import (
    package_id_for,
    source_id_for,
    stable_knowledge_id,
)
from transcript_pipeline.knowledge.models import (
    KnowledgePackage,
    Procedure,
    ProcedureStep,
    StepEvidence,
)
from transcript_pipeline.knowledge.policy import (
    validate_enums,
    validate_publish_context,
)

PIPELINE_PRODUCER = "zo-media-intelligence"


def resolve_second_brain(project_config: dict | None) -> dict | None:
    """Returns the effective second_brain config, or None when publishing is
    disabled/absent (legacy projects publish nothing)."""
    if not isinstance(project_config, dict):
        return None
    sb = project_config.get("second_brain")
    if not isinstance(sb, dict) or not sb.get("enabled", False):
        return None
    return sb


def _source_hash(source: DocumentationSource, steps: list[ProceduralStep]) -> str:
    """Hash over the derived content that actually feeds the package — this
    is what 'unchanged derivation' means for idempotency (ZK-07/ZK-08)."""
    from transcript_pipeline.knowledge.identity import canonical_json

    payload = canonical_json(
        {
            "video_name": source.video_name,
            "duration": source.duration,
            "language": source.language,
            "steps": [
                {
                    "id": s.id,
                    "instruction": s.instruction,
                    "timestamp": s.timestamp,
                    "confidence": s.confidence,
                    "reviewed": s.reviewed,
                }
                for s in steps
            ],
        }
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def build_knowledge_package(
    *,
    source: DocumentationSource,
    steps: list[ProceduralStep],
    project_config: dict | None,
    project_match: str = "routing",
    existing_knowledge: dict[str, Any] | None = None,
    supersedes_knowledge_id: str | None = None,
) -> KnowledgePackage | None:
    """Builds a Knowledge Package v2 (and its embedded procedure data).

    Returns None when publishing is disabled for the matched project —
    the caller treats that as a no-op, never as an error (ZK-01).

    `existing_knowledge` (optional, from a prior package for the same source)
    drives the version rule: unchanged derived content -> same version and a
    byte-identical packageId; changed content -> version increments for the
    same knowledgeId (ZK-09). A brand-new recording gets a fresh knowledgeId
    and never auto-supersedes anything (ZK-10) unless `supersedes_knowledge_id`
    is explicitly provided.
    """
    sb = resolve_second_brain(project_config)
    if sb is None:
        return None

    scope = sb.get("scope", "PROJECT")
    project_id = sb.get("project_id") if scope == "PROJECT" else sb.get("project_id")
    domain = sb.get("domain", "")
    data_classification = (project_config or {}).get("data_classification", "internal")

    # Fail closed on policy violations before anything is built.
    validate_publish_context(
        scope=scope, project_id=project_id, domain=domain, data_classification=data_classification
    )

    artifact_type = sb.get("default_artifact_type", "KT")
    actionability = sb.get("default_actionability", "REFERENCE")
    validate_enums(artifact_type=artifact_type, actionability=actionability)

    derived_hash = _source_hash(source, steps)
    source_id = source_id_for(
        media_name=source.video_name, source_hash=derived_hash, project_match=project_match
    )

    knowledge_id = stable_knowledge_id(source_id)
    version = 1
    if existing_knowledge:
        knowledge_id = existing_knowledge.get("knowledgeId", knowledge_id)
        content_changed = existing_knowledge.get("sourceHash") != derived_hash
        version = int(existing_knowledge.get("version", 1))
        if content_changed:
            version += 1

    procedure_steps = [
        ProcedureStep(
            id=step.id,
            order=step.order,
            instruction=step.instruction,
            timestamp=step.timestamp,
            evidence=StepEvidence(
                transcript_excerpt=step.transcript_ref or None,
                ocr_text=step.ocr_text,
                frame_ref=step.frame_ref,
                confidence=step.confidence,
                reviewed=step.reviewed,
            ),
        )
        for step in steps
    ]

    package = KnowledgePackage(
        package_id="",  # computed below over the payload itself
        knowledge_id=knowledge_id,
        version=version,
        scope=scope,
        project_id=project_id,
        domain=domain,
        artifact_type=artifact_type,
        actionability=actionability,
        data_classification=data_classification,
        source={
            "sourceId": source_id,
            "sourceHash": derived_hash,
            "mediaName": source.video_name,
            "mediaType": "video",
            "durationSeconds": source.duration,
            "language": source.language,
            "generatedAt": source.generated_at,
            "pipelineVersion": PIPELINE_PRODUCER,
        },
        provenance={
            "producer": PIPELINE_PRODUCER,
            "projectMatch": project_match,
            # Raw material never leaves Zo (SPEC §3, security tests).
            "rawTranscriptPublished": False,
            "rawMediaPublished": False,
        },
        knowledge={
            "title": source.video_name,
            "summary": (
                f"{len(steps)} documented steps derived from {source.video_name} "
                f"({source.language}, {source.duration:.0f}s)."
            ),
            "tags": [],
            "procedures": [],
        },
        evidence=[],
        supersedes_knowledge_id=supersedes_knowledge_id,
    )

    payload = package.to_dict()
    payload["packageId"] = package_id_for(payload)
    package.package_id = payload["packageId"]

    procedure = Procedure(
        procedure_id=f"{knowledge_id}:proc",
        knowledge_id=knowledge_id,
        version=version,
        scope=scope,
        project_id=project_id,
        actionability=actionability,
        title=source.video_name,
        steps=procedure_steps,
    )
    payload["knowledge"]["procedures"] = [procedure.to_dict()]  # type: ignore[union-attr]

    # Recompute the id with the embedded procedure data included, then
    # re-guard the final payload against raw-material fields.
    payload["packageId"] = package_id_for(payload)
    package.package_id = payload["packageId"]
    from transcript_pipeline.knowledge.policy import assert_no_forbidden_payload

    assert_no_forbidden_payload(payload)
    return package


def procedure_from_package(package: KnowledgePackage) -> Procedure | None:
    """Extracts the embedded Procedure for `ai-package/procedure.json`."""
    procedures = package.knowledge.get("procedures") or []
    if not procedures:
        return None
    data = procedures[0]
    return Procedure(
        procedure_id=data["procedureId"],
        knowledge_id=data["knowledgeId"],
        version=data["version"],
        scope=data["scope"],
        project_id=data.get("projectId"),
        actionability=data["actionability"],
        title=data["title"],
        steps=[
            ProcedureStep(
                id=step["id"],
                order=step["order"],
                instruction=step["instruction"],
                timestamp=step.get("timestamp"),
                evidence=StepEvidence(
                    transcript_excerpt=(step.get("evidence") or {}).get("transcriptExcerpt"),
                    ocr_text=(step.get("evidence") or {}).get("ocrText"),
                    frame_ref=(step.get("evidence") or {}).get("frameRef"),
                    source_segment_index=(step.get("evidence") or {}).get("sourceSegmentIndex"),
                    confidence=(step.get("evidence") or {}).get("confidence", "low"),
                    reviewed=(step.get("evidence") or {}).get("reviewed", False),
                ),
                semantic_action=step.get("semanticAction"),
                semantic_target=step.get("semanticTarget"),
            )
            for step in data.get("steps", [])
        ],
        parameters=data.get("parameters", []),
        preconditions=data.get("preconditions", []),
        expected_outcomes=data.get("expectedOutcomes", []),
    )


def write_package_files(ai_package_dir: Path, package: KnowledgePackage) -> dict[str, Path]:
    """Writes `knowledge-package.json` (+ `procedure.json` when applicable)
    next to the existing v1 package outputs — backward compatible, nothing
    existing is removed or rewritten (PLAN WP-02)."""
    import json

    ai_package_dir.mkdir(parents=True, exist_ok=True)
    package_path = ai_package_dir / "knowledge-package.json"
    package_path.write_text(
        json.dumps(package.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    written = {"package": package_path}
    procedure = procedure_from_package(package)
    if procedure is not None:
        procedure_path = ai_package_dir / "procedure.json"
        procedure_path.write_text(
            json.dumps(procedure.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        written["procedure"] = procedure_path
    return written


# Documentation Synthesis V2 integration

try:
    from transcript_pipeline.documentation.synthesis_models import KnowledgeDocument
except ImportError:
    # optional dependency
    KnowledgeDocument = None


def build_knowledge_package_from_document(
    *,
    knowledge_document: KnowledgeDocument,
    evidence_timeline: dict,
    project_config: dict | None,
    project_match: str = "routing",
    existing_knowledge: dict[str, Any] | None = None,
    supersedes_knowledge_id: str | None = None,
) -> KnowledgePackage | None:
    """Build Knowledge Package from V2 KnowledgeDocument.
    
    Uses synthesized title/summary/sections and only real procedure candidates.
    """
    if KnowledgeDocument is None:
        raise ImportError("KnowledgeDocument not available")
    
    sb = resolve_second_brain(project_config)
    if sb is None:
        return None
    
    scope = sb.get("scope", "PROJECT")
    project_id = sb.get("project_id") if scope == "PROJECT" else sb.get("project_id")
    domain = sb.get("domain", "")
    data_classification = (project_config or {}).get("data_classification", "internal")
    
    # Validate publish context
    from transcript_pipeline.knowledge.policy import validate_publish_context, validate_enums
    validate_publish_context(
        scope=scope, project_id=project_id, domain=domain, data_classification=data_classification
    )
    
    artifact_type = sb.get("default_artifact_type", "KT")
    actionability = sb.get("default_actionability", "REFERENCE")
    validate_enums(artifact_type=artifact_type, actionability=actionability)
    
    # Compute source hash from normalized semantic document + relevant evidence identity
    from transcript_pipeline.knowledge.identity import canonical_json
    payload = canonical_json({
        "documentation_mode": knowledge_document.documentationMode,
        "title": knowledge_document.title,
        "summary": knowledge_document.executiveSummary,
        "sections": [
            {
                "id": s.id,
                "type": s.sectionType,
                "title": s.title,
                "summary": s.summary,
            }
            for s in knowledge_document.sections
        ],
        "procedures": [
            {
                "id": p.id,
                "title": p.title,
                "steps": len(p.steps),
            }
            for p in knowledge_document.procedures
        ],
        "evidence_hash": "TODO",  # hash over referenced evidence ids
    })
    derived_hash = f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
    
    # Use media name from source field
    media_name = knowledge_document.source.get("video_name", "unknown")
    from transcript_pipeline.knowledge.identity import source_id_for, stable_knowledge_id
    source_id = source_id_for(
        media_name=media_name, source_hash=derived_hash, project_match=project_match
    )
    
    knowledge_id = stable_knowledge_id(source_id)
    version = 1
    if existing_knowledge:
        knowledge_id = existing_knowledge.get("knowledgeId", knowledge_id)
        content_changed = existing_knowledge.get("sourceHash") != derived_hash
        version = int(existing_knowledge.get("version", 1))
        if content_changed:
            version += 1
    
    # Build package
    package = KnowledgePackage(
        package_id="",  # computed later
        knowledge_id=knowledge_id,
        version=version,
        scope=scope,
        project_id=project_id,
        domain=domain,
        artifact_type=artifact_type,
        actionability=actionability,
        data_classification=data_classification,
        source={
            "sourceId": source_id,
            "sourceHash": derived_hash,
            "mediaName": media_name,
            "mediaType": "video",
            "durationSeconds": evidence_timeline.get("sourceDuration", 0.0),
            "language": knowledge_document.source.get("language", "unknown"),
            "generatedAt": knowledge_document.source.get("generated_at", ""),
            "pipelineVersion": PIPELINE_PRODUCER,
        },
        provenance={
            "producer": PIPELINE_PRODUCER,
            "projectMatch": project_match,
            "rawTranscriptPublished": False,
            "rawMediaPublished": False,
        },
        knowledge={
            "title": knowledge_document.title,
            "summary": knowledge_document.executiveSummary,
            "tags": [],
            "procedures": [],  # filled below
        },
        evidence=[],  # TODO: include referenced evidence
        supersedes_knowledge_id=supersedes_knowledge_id,
    )
    
    # Embed procedures if any
    procedure_steps = []
    for proc in knowledge_document.procedures:
        # Convert SynthesizedProcedure to Procedure
        steps = [
            ProcedureStep(
                id=f"{proc.id}-step-{step.order}",
                order=step.order,
                instruction=step.instruction,
                timestamp=None,  # not available
                evidence=StepEvidence(
                    transcript_excerpt=None,
                    ocr_text=None,
                    frame_ref=None,
                    confidence="high",  # TODO: derive from evidence
                    reviewed=False,
                ),
                semantic_action=step.semanticAction,
                semantic_target=step.semanticTarget,
            )
            for step in proc.steps
        ]
        procedure = Procedure(
            procedure_id=f"{knowledge_id}:proc:{proc.id}",
            knowledge_id=knowledge_id,
            version=version,
            scope=scope,
            project_id=project_id,
            actionability=proc.actionability,
            title=proc.title,
            steps=steps,
            parameters=proc.prerequisites,
            expected_outcomes=proc.expectedOutcomes,
        )
        procedure_steps.append(procedure.to_dict())
    
    if procedure_steps:
        package.knowledge["procedures"] = procedure_steps
    
    # Compute final package id
    payload = package.to_dict()
    from transcript_pipeline.knowledge.identity import package_id_for
    payload["packageId"] = package_id_for(payload)
    package.package_id = payload["packageId"]
    
    # Guard against forbidden payload
    from transcript_pipeline.knowledge.policy import assert_no_forbidden_payload
    assert_no_forbidden_payload(payload)
    
    return package
