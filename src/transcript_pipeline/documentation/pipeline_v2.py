"""Documentation Synthesis V2 staged orchestration (SPEC §10-§15, PLAN WP-14).

    1. load persisted evidence (frame_mapping.json [+ manual/steps.json]);
    2. build the EvidenceTimeline (deterministic resolver);
    3. write the Evidence Plane outputs;
    4. resolve the DocumentationMode;
    5. synthesize when allowed (privacy-guarded, bounded);
    6. validate grounding (fail closed, last-good protected);
    7. select representative screenshots;
    8. write the semantic MANUAL + AI package;
    9. publish the semantic Knowledge Package when enabled.

Documentation failure is never fatal to transcription: this module returns
typed statuses and never raises past the initial FileNotFoundError. When
synthesis is unavailable/blocked/invalid the Evidence Plane still succeeds
and the legacy compatibility bundles (manual/steps.json) are kept working.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation import engine
from transcript_pipeline.documentation.classifier import resolve_documentation_mode
from transcript_pipeline.documentation.evidence import (
    EvidenceTimeline,
    build_evidence_timeline,
    load_persisted_steps,
)
from transcript_pipeline.documentation.evidence_writer import write_evidence_outputs
from transcript_pipeline.documentation.grounding import (
    validate_knowledge_document,
    write_validation_report,
)
from transcript_pipeline.documentation.knowledge_models import KnowledgeDocument
from transcript_pipeline.documentation.models import DocumentationSource
from transcript_pipeline.documentation.modes import normalize_documentation_config
from transcript_pipeline.documentation.screenshots import select_screenshots
from transcript_pipeline.documentation.semantic_manual_writer import write_semantic_manual
from transcript_pipeline.documentation.semantic_package import write_semantic_ai_package
from transcript_pipeline.documentation.synthesis import (
    STATUS_INVALID,
    STATUS_OK,
    SynthesisResult,
    SynthesisService,
    default_synthesis_service,
)

logger = logging.getLogger(__name__)


def generate_documentation_v2(
    frames_dir: Path,
    video_name: str,
    *,
    manual_dir: Path | None = None,
    ai_package_dir: Path | None = None,
    project_config: dict | None = None,
    steps: list | None = None,
    synthesis_service: SynthesisService | None = None,
    evidence_only: bool = False,
    compatibility_bundles: bool = True,
    mode_override: str | None = None,
) -> dict[str, Any]:
    """Runs the staged V2 pipeline. Returns a staged result dict.

    `steps`: evidence adapter input (ProceduralStep list). When omitted, the
    persisted manual/steps.json is used when present, else steps are derived
    from frame_mapping.json WITHOUT frames_dir — i.e. without any OCR/vision
    upstream work (regeneration-safe).
    """
    mapping_path = frames_dir / "frame_mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(f"frame_mapping.json not found in {frames_dir}")
    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))

    manual_dir = manual_dir or (frames_dir / "manual")
    ai_package_dir = ai_package_dir or (frames_dir / "ai-package")
    video_info = mapping_data.get("video_info", {})
    transcription_summary = mapping_data.get("transcription_summary", {})

    if steps is None:
        steps = load_persisted_steps(manual_dir)
        if steps is None:
            # Regeneration-safe derivation: no OCR, no vision, no frames_dir.
            steps = engine.build_steps(mapping_data, None, None)

    source = DocumentationSource(
        video_name=video_name,
        duration=video_info.get("duration", 0.0),
        language=transcription_summary.get("language", "unknown"),
        extraction_method=video_info.get("extraction_method", "unknown"),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # 1-3. Evidence plane.
    timeline = build_evidence_timeline(mapping_data, steps=steps, source_media=video_name)
    evidence_paths = write_evidence_outputs(frames_dir, timeline)

    # Compatibility evidence source (SPEC §10: manual/steps.json).
    engine._write_steps_json(manual_dir, source, steps)

    doc_config = normalize_documentation_config(
        project_config.get("documentation") if isinstance(project_config, dict) else None
    )

    # 4. Mode resolution.
    service = synthesis_service
    if service is None and not evidence_only:
        service = default_synthesis_service()
    classifier = _classifier_for(service, project_config)
    resolution = resolve_documentation_mode(project_config, timeline, classifier=classifier)
    mode = resolution.mode
    mode_source = resolution.source
    if isinstance(mode_override, str) and mode_override:
        mode = mode_override
        mode_source = "explicit_override"

    # 5. Synthesis (only when allowed).
    synthesis_result: SynthesisResult | None = None
    status = "EVIDENCE_READY"
    document: KnowledgeDocument | None = None
    full_transcript = str(transcription_summary.get("full_transcription", "") or "")

    if evidence_only or not doc_config["synthesis_enabled"]:
        status = "EVIDENCE_READY" if not doc_config["synthesis_enabled"] else status
    else:
        timeline_identity_before = timeline.content_hash()
        synthesis_result = service.synthesize(timeline, mode, project_config)
        timeline_identity_after = timeline.content_hash()
        mutated = timeline_identity_before != timeline_identity_after
        if synthesis_result.status == STATUS_OK and synthesis_result.document is not None:
            candidate = synthesis_result.document
            # 6. Grounding validation (fail closed).
            report = validate_knowledge_document(
                candidate, timeline, full_transcript=full_transcript or None,
                source_evidence_mutated=mutated,
            )
            write_validation_report(manual_dir, report)
            if report.valid:
                document = candidate
                status = "SYNTHESIS_READY"
            else:
                status = STATUS_INVALID
                logger.warning("[DOCS-V2] synthesis rejected by grounding: %s", report.errors[:5])
        else:
            status = synthesis_result.status

    # 7-8. Semantic manual + package (with last-good protection).
    knowledge_result: dict[str, Any] = {"published": False, "reason": "not_attempted"}
    if document is not None:
        selection = select_screenshots(
            document, timeline, frames_dir,
            max_total=doc_config["max_screenshots"],
            max_per_section=doc_config["max_screenshots_per_section"],
        )
        write_semantic_manual(manual_dir, document, timeline, frames_dir, selection, source)
        write_semantic_ai_package(
            ai_package_dir, document, timeline, selection, source, project_config=project_config
        )
        status = "MANUAL_READY"
        # 9. Publish semantic Knowledge Package when enabled.
        if not evidence_only:
            knowledge_result = _publish_semantic_knowledge(
                ai_package_dir, document, timeline, project_config
            )
            state = knowledge_result.get("knowledgeState")
            if state == engine.KNOWLEDGE_STATE_PUBLISHED:
                status = "PUBLISH_ACK"
            elif state == engine.KNOWLEDGE_STATE_ENQUEUED:
                status = "PUBLISH_ENQUEUED"
            elif state == engine.KNOWLEDGE_STATE_PENDING_RETRY:
                status = "PUBLISH_PENDING_RETRY"
    elif status == STATUS_INVALID:
        # Last-good protection: never overwrite a previously valid semantic
        # document with an invalid synthesis.
        knowledge_result = {"published": False, "reason": "synthesis_invalid"}
    else:
        knowledge_result = {"published": False, "reason": f"synthesis_{status.lower()}"}

    # Compatibility bundles for evidence-only results (DV2-47: existing
    # manual/steps metadata callers keep working). Last-good protection
    # (DV2-20): a previously valid semantic manual is never overwritten by
    # an invalid synthesis's compatibility rendering.
    if document is None and compatibility_bundles and not _has_valid_semantic_manual(manual_dir):
        try:
            engine.write_manual(manual_dir, source, steps, frames_dir, write_steps_json=False)
            engine.write_ai_package(ai_package_dir, source, steps, frames_dir)
            metadata_path = manual_dir / "metadata.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["documentation_mode"] = mode
                metadata["synthesis_status"] = status
                metadata["evidence_item_count"] = timeline.item_count
                metadata_path.write_text(
                    json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except Exception as e:  # noqa: BLE001 - compat bundle failure is non-fatal
            logger.warning("[DOCS-V2] compatibility bundle write failed: %s", e)

    return {
        "status": status,
        "manual_dir": str(manual_dir),
        "ai_package_dir": str(ai_package_dir),
        "step_count": len(steps),
        "low_confidence_count": sum(1 for step in steps if step.confidence == "low"),
        "evidence": {
            "item_count": timeline.item_count,
            "review_required_count": timeline.review_required_count,
            "fidelity": timeline.fidelity,
            "paths": {key: str(path) for key, path in evidence_paths.items()},
        },
        "mode": {"mode": mode, "source": mode_source, "reason": resolution.reason},
        "synthesis": {
            "status": synthesis_result.status if synthesis_result else status,
            "invocation_count": synthesis_result.invocation_count if synthesis_result else 0,
            "errors": synthesis_result.errors if synthesis_result else [],
        } if synthesis_result else {"status": "SYNTHESIS_NOT_AVAILABLE", "invocation_count": 0, "errors": []},
        "semantic": {
            "ready": document is not None,
            "section_count": len(document.sections) if document else 0,
            "procedure_count": len(document.procedures) if document else 0,
        },
        "knowledge": knowledge_result,
    }


def _has_valid_semantic_manual(manual_dir: Path) -> bool:
    """A knowledge-document.json is only ever written after grounding passed,
    so its presence means a valid semantic manual exists (last good)."""
    return (manual_dir / "knowledge-document.json").exists()


def _classifier_for(service: SynthesisService | None, project_config: dict | None):
    """The AUTO classifier uses the same provider/privacy boundary as
    synthesis; without a provider there is no classifier (typed REFERENCE
    fallback inside the resolver)."""
    if service is None:
        return None
    provider = service._provider  # noqa: SLF001 - same-package orchestration
    guard = service._guard  # noqa: SLF001
    if provider is None or guard is None:
        return None
    from transcript_pipeline.documentation.classifier import LLMModeClassifier

    return LLMModeClassifier(provider, guard, project_config)


def _publish_semantic_knowledge(
    ai_package_dir: Path,
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    project_config: dict | None,
    *,
    existing_knowledge: dict | None = None,
    supersedes_knowledge_id: str | None = None,
) -> dict[str, Any]:
    """Same durable-outbox flow as the legacy hook, but the package is built
    by the semantic bridge (title/summary/sections from the
    KnowledgeDocument; procedures only from SynthesizedProcedure)."""
    try:
        from transcript_pipeline.knowledge.package_builder import (
            build_knowledge_package_from_document,
            resolve_second_brain,
            write_package_files,
        )
        from transcript_pipeline.knowledge.publisher import (
            enqueue_knowledge_package,
            publisher_from_env,
            run_publish_cycle,
        )

        if resolve_second_brain(project_config) is None:
            return {
                "published": False,
                "reason": "second_brain_disabled",
                "knowledgeState": engine.KNOWLEDGE_STATE_SECOND_BRAIN_DISABLED,
            }

        package = build_knowledge_package_from_document(
            knowledge_document=document,
            evidence_timeline=timeline,
            project_config=project_config,
            existing_knowledge=existing_knowledge,
            supersedes_knowledge_id=supersedes_knowledge_id,
        )
        if package is None:
            return {
                "published": False,
                "reason": "second_brain_disabled",
                "knowledgeState": engine.KNOWLEDGE_STATE_SECOND_BRAIN_DISABLED,
            }

        write_package_files(ai_package_dir, package)

        from transcript_pipeline.config import DATA_ROOT
        from transcript_pipeline.knowledge.outbox import KnowledgeOutbox

        outbox = KnowledgeOutbox(DATA_ROOT)
        entry = enqueue_knowledge_package(outbox, package.to_dict())
        entry_state = entry.get("state", "PENDING") if isinstance(entry, dict) else "PENDING"

        if entry_state == "PUBLISHED":
            return {
                "published": True, "packageId": package.package_id, "outbox": entry,
                "knowledgeState": engine.KNOWLEDGE_STATE_PUBLISHED, "publishCycle": None,
            }
        if entry_state == "FAILED":
            return {
                "published": True, "packageId": package.package_id, "outbox": entry,
                "knowledgeState": engine.KNOWLEDGE_STATE_TERMINAL_FAILURE, "publishCycle": None,
            }

        publisher = publisher_from_env()
        if publisher is None:
            return {
                "published": True, "packageId": package.package_id, "outbox": entry,
                "knowledgeState": engine.KNOWLEDGE_STATE_ENQUEUED, "publishCycle": None,
            }

        cycle = run_publish_cycle(outbox, publisher, max_seconds=engine.KNOWLEDGE_PUBLISH_WAKEUP_SECONDS)
        refreshed = outbox.ledger.get(package.package_id) or entry
        final_state = refreshed.get("state", "PENDING") if isinstance(refreshed, dict) else "PENDING"
        if final_state == "PUBLISHED":
            knowledge_state = engine.KNOWLEDGE_STATE_PUBLISHED
        elif final_state == "FAILED":
            knowledge_state = engine.KNOWLEDGE_STATE_TERMINAL_FAILURE
        else:
            knowledge_state = engine.KNOWLEDGE_STATE_PENDING_RETRY
        return {
            "published": True, "packageId": package.package_id, "outbox": refreshed,
            "knowledgeState": knowledge_state, "publishCycle": cycle,
        }
    except Exception as e:  # noqa: BLE001 - knowledge publishing is best-effort
        logger.warning("[KNOWLEDGE] semantic knowledge package skipped: %s", e)
        return {"published": False, "reason": f"error:{type(e).__name__}"}
