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


# ── Documentation Synthesis V2 bridge (SPEC §13, PLAN WP-13) ─────────────

def _semantic_source_hash(knowledge_document, evidence_timeline) -> str:
    """Content identity over the normalized semantic document + the relevant
    evidence identity. Excludes generatedAt and any produced timestamp:
    regenerating the same synthesis must NOT mint a new knowledge version
    (DV2-37); a material semantic/evidence change must (DV2-38)."""
    from transcript_pipeline.knowledge.identity import canonical_json

    payload = knowledge_document.to_dict()
    synthesis = dict(payload.get("synthesis", {}))
    synthesis.pop("generatedAt", None)  # timestamp-independent identity
    payload["synthesis"] = synthesis
    payload.pop("documentId", None)
    payload.pop("evidenceIndex", None)  # derived; identity comes from items below
    evidence_identity = [
        {
            "evidenceId": item.evidence_id,
            "timestampStart": round(item.timestamp_start, 3),
            "timestampEnd": round(item.timestamp_end, 3),
            "evidenceSource": item.evidence_source,
            "confidence": item.confidence,
            "frameRef": item.frame_ref,
            "excerptHash": hashlib.sha256(
                (item.transcript_excerpt or item.ocr_excerpt or "").encode("utf-8")
            ).hexdigest()[:16],
        }
        for item in evidence_timeline.items
    ]
    canonical = canonical_json({"document": payload, "evidence": evidence_identity})
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def build_knowledge_package_from_document(
    *,
    knowledge_document,
    evidence_timeline,
    project_config: dict | None,
    project_match: str = "routing",
    existing_knowledge: dict[str, Any] | None = None,
    supersedes_knowledge_id: str | None = None,
) -> KnowledgePackage | None:
    """Builds a Knowledge Package v2 from a synthesized KnowledgeDocument.

    Differences vs the legacy all-steps builder (SPEC §13):
    - title from the synthesized document;
    - summary from the executive summary;
    - tags/glossary where applicable;
    - semantic sections/claims in the knowledge payload;
    - procedures ONLY from real SynthesizedProcedure objects — there is no
      all-evidence fake procedure, so KT/meeting/reference content may
      produce zero procedures (DV2-35);
    - source identity is timestamp-independent (DV2-37) and increments the
      knowledge version on material semantic/evidence change (DV2-38).

    Returns None when publishing is disabled (same no-op contract as the
    legacy builder). PROJECT/GLOBAL/policy/outbox behavior is preserved.
    """
    from transcript_pipeline.documentation.modes import ARTIFACT_TYPE_FOR_MODE

    sb = resolve_second_brain(project_config)
    if sb is None:
        return None

    scope = sb.get("scope", "PROJECT")
    project_id = sb.get("project_id")
    domain = sb.get("domain", "")
    data_classification = (project_config or {}).get("data_classification", "internal")

    validate_publish_context(
        scope=scope, project_id=project_id, domain=domain, data_classification=data_classification
    )

    artifact_type = sb.get("default_artifact_type") or ARTIFACT_TYPE_FOR_MODE.get(
        knowledge_document.documentation_mode, "REFERENCE"
    )
    actionability = sb.get("default_actionability", "REFERENCE")
    validate_enums(artifact_type=artifact_type, actionability=actionability)

    derived_hash = _semantic_source_hash(knowledge_document, evidence_timeline)
    source_id = source_id_for(
        media_name=knowledge_document.source or knowledge_document.title,
        source_hash=derived_hash,
        project_match=project_match,
    )

    knowledge_id = stable_knowledge_id(source_id)
    version = 1
    if existing_knowledge:
        knowledge_id = existing_knowledge.get("knowledgeId", knowledge_id)
        content_changed = existing_knowledge.get("sourceHash") != derived_hash
        version = int(existing_knowledge.get("version", 1))
        if content_changed:
            version += 1

    by_id = {item.evidence_id: item for item in evidence_timeline.items}

    def _step_evidence(evidence_id: str) -> StepEvidence:
        item = by_id.get(evidence_id)
        if item is None:
            return StepEvidence()
        return StepEvidence(
            transcript_excerpt=item.transcript_excerpt,
            ocr_text=item.ocr_excerpt,
            frame_ref=item.frame_ref,
            confidence=item.confidence,
            reviewed=item.reviewed,
        )

    # Procedures ONLY from SynthesizedProcedure (no fake all-evidence procedure).
    procedures = []
    for procedure in knowledge_document.procedures:
        steps = [
            ProcedureStep(
                id=f"{procedure.id}:step-{step.order:03d}",
                order=step.order,
                instruction=step.instruction,
                timestamp=by_id[step.evidence_refs[0]].timestamp_start
                if step.evidence_refs and step.evidence_refs[0] in by_id else None,
                evidence=_step_evidence(step.evidence_refs[0]) if step.evidence_refs else StepEvidence(),
                semantic_action=step.semantic_action,
                semantic_target=step.semantic_target,
            )
            for step in procedure.steps
        ]
        procedures.append(
            Procedure(
                procedure_id=f"{knowledge_id}:proc:{procedure.id}",
                knowledge_id=knowledge_id,
                version=version,
                scope=scope,
                project_id=project_id,
                actionability=procedure.actionability or actionability,
                title=procedure.title,
                steps=steps,
                preconditions=list(procedure.prerequisites),
                expected_outcomes=list(procedure.expected_outcomes),
            ).to_dict()
        )

    summary = knowledge_document.executive_summary or (
        f"{len(knowledge_document.sections)} semantic sections synthesized from "
        f"{knowledge_document.source}."
    )

    package = KnowledgePackage(
        package_id="",
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
            "mediaName": knowledge_document.source,
            "mediaType": "video",
            "durationSeconds": evidence_timeline.duration,
            "language": evidence_timeline.language,
            # NOTE: no generatedAt here on purpose — package content identity
            # is timestamp-independent (DV2-37).
            "documentationMode": knowledge_document.documentation_mode,
            "documentId": knowledge_document.document_id,
            "pipelineVersion": PIPELINE_PRODUCER,
        },
        provenance={
            "producer": PIPELINE_PRODUCER,
            "projectMatch": project_match,
            "rawTranscriptPublished": False,
            "rawMediaPublished": False,
            "synthesized": True,
            "reviewStatus": knowledge_document.review_status,
        },
        knowledge={
            "title": knowledge_document.title,
            "summary": summary,
            "tags": sorted({tag for section in knowledge_document.sections for claim in section.claims for tag in claim.tags}),
            "glossary": [
                {"term": entry.term, "definition": entry.definition}
                for entry in knowledge_document.glossary
            ],
            "sections": [section.to_dict() for section in knowledge_document.sections],
            "procedures": procedures,
        },
        evidence=[
            {
                "evidenceId": item.evidence_id,
                "timestampStart": round(item.timestamp_start, 3),
                "timestampEnd": round(item.timestamp_end, 3),
                "evidenceSource": item.evidence_source,
                "confidence": item.confidence,
                "reviewed": item.reviewed,
                "transcriptExcerpt": item.transcript_excerpt,
                "ocrExcerpt": item.ocr_excerpt,
                "frameRef": item.frame_ref,
            }
            for item in evidence_timeline.facts()
        ],
        supersedes_knowledge_id=supersedes_knowledge_id,
    )

    payload = package.to_dict()
    payload["packageId"] = package_id_for(payload)
    package.package_id = payload["packageId"]

    from transcript_pipeline.knowledge.policy import assert_no_forbidden_payload

    assert_no_forbidden_payload(payload)
    return package


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
