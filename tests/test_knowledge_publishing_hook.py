"""ZK-01/ZK-16 + DELTA-ZO-KNOWLEDGE-002 — publish wakeup and recursive privacy.

Covers:
- configured publisher ACK moves the package to published (PUBLISHED);
- configured retryable publisher leaves the package pending/backoff
  (PENDING_RETRY);
- unconfigured publisher remains enqueue-only (ENQUEUED);
- publisher failure never fails documentation;
- disabled second_brain returns SECOND_BRAIN_DISABLED;
- nested raw transcript/VTT/media fields are rejected recursively while a
  bounded transcriptExcerpt stays valid.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from transcript_pipeline import config as config_mod
from transcript_pipeline.documentation import engine
from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep
from transcript_pipeline.knowledge import publisher as publisher_mod
from transcript_pipeline.knowledge.outbox import KnowledgeOutbox
from transcript_pipeline.knowledge.policy import PublishPolicyError, assert_no_forbidden_payload
from transcript_pipeline.knowledge.publisher import ACK, RETRYABLE_FAILURE

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


class _AckPublisher:
    def publish(self, package: dict) -> str:
        return ACK


class _RetryPublisher:
    def publish(self, package: dict) -> str:
        return RETRYABLE_FAILURE


class _BoomPublisher:
    def publish(self, package: dict) -> str:
        raise ConnectionError("Second Brain unreachable")


def test_configured_publisher_ack_moves_package_to_published(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(publisher_mod, "publisher_from_env", lambda env=None: _AckPublisher())
    result = _run_hook(tmp_path)

    assert result["published"] is True
    assert result["knowledgeState"] == "PUBLISHED"
    outbox = KnowledgeOutbox(tmp_path)
    assert len(list(outbox.published.glob("*.json"))) == 1
    assert not list(outbox.pending.glob("*.json"))


def test_configured_retryable_publisher_leaves_pending_backoff(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(publisher_mod, "publisher_from_env", lambda env=None: _RetryPublisher())
    result = _run_hook(tmp_path)

    assert result["knowledgeState"] == "PENDING_RETRY"
    outbox = KnowledgeOutbox(tmp_path)
    entry = outbox.ledger.get(result["packageId"])
    assert entry["state"] == "PENDING"
    assert entry["nextAttemptAt"]  # bounded backoff scheduled
    assert len(list(outbox.pending.glob("*.json"))) == 1


def test_unconfigured_publisher_is_enqueue_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(publisher_mod, "publisher_from_env", lambda env=None: None)
    result = _run_hook(tmp_path)

    assert result["knowledgeState"] == "ENQUEUED"
    assert result["publishCycle"] is None
    outbox = KnowledgeOutbox(tmp_path)
    assert len(list(outbox.pending.glob("*.json"))) == 1
    assert not list(outbox.published.glob("*.json"))


def test_publisher_failure_does_not_fail_documentation(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(publisher_mod, "publisher_from_env", lambda env=None: _BoomPublisher())
    result = _run_hook(tmp_path)

    # No exception escapes; the package is preserved as retryable.
    assert result["published"] is True
    assert result["knowledgeState"] == "PENDING_RETRY"


def test_disabled_second_brain_is_clean_noop(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(publisher_mod, "publisher_from_env", lambda env=None: _AckPublisher())
    result = _run_hook(tmp_path, project_config={"name": "legacy"})

    assert result["published"] is False
    assert result["knowledgeState"] == "SECOND_BRAIN_DISABLED"


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
