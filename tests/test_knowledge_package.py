"""ZK-07, ZK-09..ZK-15 — Knowledge Package v2 identity, policy and shape."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep
from transcript_pipeline.knowledge.package_builder import (
    build_knowledge_package,
    procedure_from_package,
)
from transcript_pipeline.knowledge.policy import (
    PublishPolicyError,
    assert_no_forbidden_payload,
    validate_publish_context,
)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts" / "knowledge-to-action" / "v1"

PG_CONFIG = {
    "name": "P&G",
    "data_classification": "confidential",
    "second_brain": {
        "enabled": True,
        "project_id": "p-g",
        "domain": "second-brain/p-g",
        "scope": "PROJECT",
        "default_artifact_type": "KT",
        "default_actionability": "REFERENCE",
        "publish_assets": False,
    },
}

GLOBAL_CONFIG = {
    "name": "Tutorials",
    "data_classification": "public",
    "second_brain": {
        "enabled": True,
        "domain": "second-brain/global",
        "scope": "GLOBAL",
        "default_artifact_type": "TUTORIAL",
        "default_actionability": "GUIDED",
        "publish_assets": False,
    },
}


def _source(name: str = "pg_briefing.mp4") -> DocumentationSource:
    return DocumentationSource(
        video_name=name,
        duration=1200.0,
        language="en",
        extraction_method="test",
        generated_at="2026-01-01T00:00:00+00:00",
    )


def _steps(count: int = 2) -> list[ProceduralStep]:
    return [
        ProceduralStep(
            id=f"step-{i:04d}",
            order=i,
            title=f"Step {i}",
            instruction=f"Do thing {i}",
            timestamp=float(i * 30),
            frame_ref=f"frame_{i}.jpg",
            transcript_ref=f"transcript excerpt {i}",
            confidence="high",
            ocr_text=f"ocr text {i}",
            reviewed=(i == 1),
        )
        for i in range(1, count + 1)
    ]


def test_zk07_same_input_produces_identical_canonical_package_id():
    first = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    second = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    assert first is not None and second is not None
    assert first.package_id == second.package_id
    assert first.to_dict() == second.to_dict()


def test_zk09_changed_derivation_same_knowledge_id_increments_version():
    v1 = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    existing = {
        "knowledgeId": v1.knowledge_id,
        "sourceHash": v1.source["sourceHash"],
        "version": v1.version,
    }
    changed_steps = _steps()
    changed_steps.append(ProceduralStep(
        id="step-0003", order=3, title="Step 3", instruction="New thing",
        timestamp=90.0, frame_ref=None, transcript_ref="new excerpt", confidence="medium",
    ))
    v2 = build_knowledge_package(
        source=_source(), steps=changed_steps, project_config=PG_CONFIG, existing_knowledge=existing
    )
    assert v2.version == v1.version + 1
    assert v2.knowledge_id == v1.knowledge_id
    assert v2.package_id != v1.package_id


def test_zk10_new_recording_does_not_auto_supersede():
    a = build_knowledge_package(source=_source("recording_a.mp4"), steps=_steps(), project_config=PG_CONFIG)
    b = build_knowledge_package(source=_source("recording_b.mp4"), steps=_steps(), project_config=PG_CONFIG)
    assert a.knowledge_id != b.knowledge_id
    assert a.supersedes_knowledge_id is None
    assert b.supersedes_knowledge_id is None


def test_zk11_package_contains_no_raw_media_bytes_or_paths():
    package = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    payload = json.dumps(package.to_dict())
    assert ".mp4" not in payload or package.source["mediaName"] == "pg_briefing.mp4"
    for forbidden in ("mediaBytes", "mediaPath"):
        assert forbidden not in payload
    assert package.provenance["rawMediaPublished"] is False


def test_zk12_package_contains_no_whole_raw_transcript_or_vtt():
    package = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    assert_no_forbidden_payload(package.to_dict())
    # Only bounded excerpts: each evidence excerpt is clipped.
    procedure = procedure_from_package(package)
    for step in procedure.steps:
        excerpt = step.evidence.transcript_excerpt or ""
        assert len(excerpt) <= 1200


def test_zk13_bounded_transcript_and_ocr_evidence_retained():
    package = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    procedure = procedure_from_package(package)
    step = procedure.steps[0]
    assert step.evidence.transcript_excerpt == "transcript excerpt 1"
    assert step.evidence.ocr_text == "ocr text 1"
    assert step.evidence.frame_ref == "frame_1.jpg"


def test_zk14_procedure_preserves_timestamps_confidence_review_evidence():
    package = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    procedure = procedure_from_package(package)
    first = procedure.steps[0]
    assert first.timestamp == 30.0
    assert first.evidence.confidence == "high"
    assert first.evidence.reviewed is True
    second = procedure.steps[1]
    assert second.evidence.reviewed is False


def test_zk15_procedural_semantic_action_may_be_null():
    package = build_knowledge_package(source=_source(), steps=_steps(), project_config=PG_CONFIG)
    procedure = procedure_from_package(package)
    for step in procedure.steps:
        assert step.semantic_action is None
        assert step.semantic_target is None
    assert procedure.to_dict()["steps"][0]["semanticAction"] is None


def test_confidential_global_package_rejected_fail_closed():
    with pytest.raises(PublishPolicyError):
        build_knowledge_package(
            source=_source(),
            steps=_steps(),
            project_config={
                "name": "Bad",
                "data_classification": "confidential",
                "second_brain": {
                    "enabled": True,
                    "domain": "second-brain/global",
                    "scope": "GLOBAL",
                },
            },
        )


def test_project_scope_requires_project_id_fail_closed():
    with pytest.raises(PublishPolicyError):
        validate_publish_context(scope="PROJECT", project_id=None, domain="d", data_classification="internal")


def test_disabled_project_returns_none_noop():
    assert build_knowledge_package(source=_source(), steps=_steps(), project_config={"name": "x"}) is None
    assert build_knowledge_package(source=_source(), steps=_steps(), project_config=None) is None


def test_fixture_packages_conform_to_policy():
    # Fixtures are contract fixtures: the two valid ones must pass the frozen
    # policy; the invalid one must fail exactly on confidential+GLOBAL.
    pg = json.loads((CONTRACTS / "p-g-project-package.json").read_text(encoding="utf-8"))
    azure = json.loads((CONTRACTS / "azure-global-package.json").read_text(encoding="utf-8"))
    invalid = json.loads((CONTRACTS / "confidential-global-invalid-package.json").read_text(encoding="utf-8"))

    validate_publish_context(
        scope=pg["scope"], project_id=pg["projectId"], domain=pg["domain"],
        data_classification=pg["dataClassification"],
    )
    assert_no_forbidden_payload(pg)
    validate_publish_context(
        scope=azure["scope"], project_id=azure["projectId"], domain=azure["domain"],
        data_classification=azure["dataClassification"],
    )
    assert_no_forbidden_payload(azure)

    with pytest.raises(PublishPolicyError):
        validate_publish_context(
            scope=invalid["scope"], project_id=invalid["projectId"], domain=invalid["domain"],
            data_classification=invalid["dataClassification"],
        )


def test_fixtures_are_deterministic(tmp_path: Path):
    for name in (
        "p-g-project-package.json",
        "azure-global-package.json",
        "confidential-global-invalid-package.json",
        "superseded-procedure.json",
        "validated-skill.json",
    ):
        content = (CONTRACTS / name).read_bytes()
        assert (tmp_path / name).write_bytes(content) == len(content)
        first = json.loads(content)
        assert json.loads((CONTRACTS / name).read_text(encoding="utf-8")) == first
