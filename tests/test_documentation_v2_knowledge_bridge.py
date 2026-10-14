"""DV2-34/36..39 — Knowledge Package v2 semantic bridge (TEST-MATRIX)."""
from __future__ import annotations

import json
from dataclasses import replace as _replace

from tests.fixtures.documentation_v2 import materialize_frames_dir
from tests.fixtures.documentation_v2.mock_synthesis import (
    MockAllowAllGuard,
    MockKTSynthesisProvider,
    MockTutorialSynthesisProvider,
)
from transcript_pipeline.documentation.evidence import (
    build_evidence_timeline,
    load_persisted_steps,
)
from transcript_pipeline.documentation.knowledge_models import (
    KnowledgeClaim,
    KnowledgeDocument,
)
from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2
from transcript_pipeline.documentation.synthesis import SynthesisService
from transcript_pipeline.knowledge.models import KnowledgePackage
from transcript_pipeline.knowledge.outbox import KnowledgeOutbox
from transcript_pipeline.knowledge.package_builder import (
    build_knowledge_package_from_document,
    procedure_from_package,
    write_package_files,
)
from transcript_pipeline.knowledge.publisher import enqueue_knowledge_package

ACME_SB = {
    "enabled": True, "scope": "PROJECT", "project_id": "acme",
    "domain": "second-brain/acme", "default_artifact_type": "KT",
    "default_actionability": "REFERENCE", "publish_assets": False,
}
KT_CONFIG = {"name": "Acme", "documentation": {"mode": "KT_SESSION"}, "second_brain": ACME_SB}
TUTORIAL_CONFIG = {
    "name": "Acme", "documentation": {"mode": "TUTORIAL"},
    "second_brain": dict(ACME_SB, default_artifact_type="TUTORIAL", default_actionability="GUIDED"),
}


def _semantic_run(fixture, tmp_path, config, provider):
    frames_dir = materialize_frames_dir(fixture, tmp_path)
    result = generate_documentation_v2(
        frames_dir, json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))["video_info"]["name"],
        project_config=config, synthesis_service=SynthesisService(provider, MockAllowAllGuard(), model_name="mock"),
    )
    assert result["semantic"]["ready"] is True
    document = KnowledgeDocument.from_json((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))
    return frames_dir, document, result


def _timeline_for(frames_dir, source_media):
    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    return build_evidence_timeline(mapping, steps=load_persisted_steps(frames_dir / "manual"),
                                   source_media=source_media)


# ── DV2-34 semantic package ───────────────────────────────────────────────

def test_dv2_34_package_summary_title_sections_originate_from_knowledge_document(tmp_path):
    frames_dir, document, _ = _semantic_run("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    package = json.loads((frames_dir / "ai-package" / "knowledge-package.json").read_text(encoding="utf-8"))
    assert package["knowledge"]["title"] == document.title
    assert package["knowledge"]["summary"] == document.executive_summary
    package_sections = package["knowledge"]["sections"]
    assert [s["id"] for s in package_sections] == [s.id for s in document.sections]
    assert package["source"]["documentationMode"] == "KT_SESSION"
    assert package["provenance"]["synthesized"] is True


# ── DV2-36 real procedure bridge ──────────────────────────────────────────

def test_dv2_36_tutorial_procedure_maps_to_procedure_v1_preserving_evidence(tmp_path):
    frames_dir, document, _ = _semantic_run("tutorial", tmp_path, TUTORIAL_CONFIG, MockTutorialSynthesisProvider())
    assert document.procedures, "tutorial fixture must yield a real procedure"

    package_path = frames_dir / "ai-package" / "knowledge-package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert package["knowledge"]["procedures"], "SynthesizedProcedure must reach the package"
    assert (frames_dir / "ai-package" / "procedure.json").exists()

    built = build_knowledge_package_from_document(
        knowledge_document=document,
        evidence_timeline=_timeline_for(frames_dir, document.source),
        project_config=TUTORIAL_CONFIG,
    )
    assert built is not None
    procedure = procedure_from_package(built)
    by_id = _timeline_for(frames_dir, document.source).by_id()
    for step, synth_step in zip(procedure.steps, document.procedures[0].steps):
        assert step.instruction == synth_step.instruction
        first_ref = synth_step.evidence_refs[0]
        assert step.timestamp == by_id[first_ref].timestamp_start
        assert step.evidence.confidence == by_id[first_ref].confidence
        assert step.evidence.transcript_excerpt == by_id[first_ref].transcript_excerpt
        assert step.semantic_action is None and step.semantic_target is None


# ── DV2-37 identity timestamp-independent ─────────────────────────────────

def test_dv2_37_generatedat_change_alone_does_not_create_new_knowledge_version(tmp_path):
    frames_dir, document, _ = _semantic_run("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    timeline = _timeline_for(frames_dir, document.source)

    first = build_knowledge_package_from_document(
        knowledge_document=document, evidence_timeline=timeline, project_config=KT_CONFIG,
    )
    later_doc = _replace(document, synthesis=_replace(
        document.synthesis, generated_at="2099-12-31T00:00:00+00:00",
    ))
    second = build_knowledge_package_from_document(
        knowledge_document=later_doc, evidence_timeline=timeline, project_config=KT_CONFIG,
        existing_knowledge={"knowledgeId": first.knowledge_id, "sourceHash": first.source["sourceHash"],
                             "version": first.version},
    )
    assert first is not None and second is not None
    assert second.version == first.version, "timestamp-only change must not version-bump"
    assert second.knowledge_id == first.knowledge_id


# ── DV2-38 semantic version change ────────────────────────────────────────

def test_dv2_38_material_semantic_change_increments_knowledge_version(tmp_path):
    frames_dir, document, _ = _semantic_run("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    timeline = _timeline_for(frames_dir, document.source)

    first = build_knowledge_package_from_document(
        knowledge_document=document, evidence_timeline=timeline, project_config=KT_CONFIG,
    )
    # Material semantic change: an edited claim text with the same evidence.
    edited_section = document.sections[0]
    edited_claims = list(edited_section.claims)
    assert edited_claims
    edited_claims[0] = KnowledgeClaim(
        id=edited_claims[0].id,
        text="EDITED: the transition plan was extended by two weeks.",
        evidence_refs=edited_claims[0].evidence_refs,
        evidence_confidence=edited_claims[0].evidence_confidence,
        verification_status=edited_claims[0].verification_status,
        tags=edited_claims[0].tags,
    )
    changed = _replace(document, sections=[
        _replace(document.sections[0], claims=tuple(edited_claims))
    ] + document.sections[1:])
    second = build_knowledge_package_from_document(
        knowledge_document=changed, evidence_timeline=timeline, project_config=KT_CONFIG,
        existing_knowledge={"knowledgeId": first.knowledge_id, "sourceHash": first.source["sourceHash"],
                             "version": first.version},
    )
    assert first is not None and second is not None
    assert second.version == first.version + 1
    assert second.knowledge_id == first.knowledge_id
    assert second.package_id != first.package_id


# ── DV2-39 publisher compatibility ────────────────────────────────────────

def test_dv2_39_existing_outbox_receives_semantic_package_unchanged(tmp_path, monkeypatch):
    frames_dir, document, _ = _semantic_run("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())

    package = build_knowledge_package_from_document(
        knowledge_document=document,
        evidence_timeline=_timeline_for(frames_dir, document.source),
        project_config=KT_CONFIG,
    )
    assert package is not None

    # The transport layer (durable outbox) receives the same dict shape any
    # v1 producer enqueues: schemaVersion/packageId/state machinery unchanged.
    outbox = KnowledgeOutbox(tmp_path)
    entry = enqueue_knowledge_package(outbox, package.to_dict())
    assert entry["state"] == "PENDING"
    persisted = json.loads(next(iter(outbox.pending.glob("*.json"))).read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 2
    assert persisted["packageId"] == package.package_id
    assert persisted["knowledgeId"] == package.knowledge_id
    assert persisted["scope"] == "PROJECT" and persisted["projectId"] == "acme"

    # write_package_files keeps writing the same file set as v1 producers.
    written = write_package_files(frames_dir / "ai-package", package)
    assert written["package"].name == "knowledge-package.json"
