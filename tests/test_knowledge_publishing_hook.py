"""Legacy Whisper publishing stays inert; privacy guard remains fail-closed."""
from __future__ import annotations

from pathlib import Path

import pytest

from transcript_pipeline import config as config_mod
from transcript_pipeline.documentation import engine
from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep
from transcript_pipeline.knowledge.outbox import KnowledgeOutbox
from transcript_pipeline.knowledge.policy import PublishPolicyError, assert_no_forbidden_payload

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


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_ROOT", tmp_path)
    return tmp_path


def _run_hook(tmp_path: Path, project_config: dict | None = PG_CONFIG) -> dict:
    return engine.publish_knowledge_from_documentation(
        tmp_path / "ai-package", _source(), _steps(), project_config
    )


def test_legacy_v2_publisher_is_inert_even_when_project_config_enables_it(tmp_path: Path):
    result = _run_hook(tmp_path)

    assert result == {
        "published": False,
        "reason": "knowledge_service_intake_required",
        "knowledgeState": "KNOWLEDGE_SERVICE_REQUIRED",
    }
    outbox = KnowledgeOutbox(tmp_path)
    assert not list(outbox.pending.glob("*.json"))
    assert not list(outbox.published.glob("*.json"))


@pytest.mark.parametrize(
    "nested_key",
    ["rawTranscript", "rawVtt", "mediaPath", "vtt", "transcript", "mediaBytes", "media"],
)
def test_nested_raw_fields_are_rejected_recursively(nested_key: str):
    payload = {
        "packageId": "sha256:x",
        "knowledge": {
            "procedures": [
                {"steps": [{"evidence": {nested_key: "leak"}}]},
            ]
        },
    }
    with pytest.raises(PublishPolicyError):
        assert_no_forbidden_payload(payload)


def test_bounded_transcript_excerpt_is_accepted():
    payload = {
        "packageId": "sha256:x",
        "knowledge": {"procedures": [{"steps": [{"evidence": {"transcriptExcerpt": "bounded"}}]}]},
    }
    assert_no_forbidden_payload(payload)  # must not raise
