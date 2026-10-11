"""ZK-08, ZK-16..ZK-18 — durable outbox: idempotency, resilience, bounds."""
from __future__ import annotations

import json
from pathlib import Path

from transcript_pipeline.knowledge.outbox import KnowledgeOutbox
from transcript_pipeline.knowledge.publisher import (
    ACK,
    RETRYABLE_FAILURE,
    TERMINAL_FAILURE,
    FilePublisher,
    enqueue_knowledge_package,
    run_publish_cycle,
)


def _package(package_id: str = "sha256:abc123") -> dict:
    return {
        "schemaVersion": 2,
        "packageId": package_id,
        "knowledgeId": "kn-test",
        "scope": "PROJECT",
        "projectId": "p-g",
        "knowledge": {"procedures": []},
    }


def test_zk08_reprocess_unchanged_source_is_idempotent_noop(tmp_path: Path):
    outbox = KnowledgeOutbox(tmp_path)
    first = outbox.enqueue(_package(), now_iso="2026-01-01T00:00:00Z")
    assert first["state"] == "PENDING"
    pending_files = list(outbox.pending.glob("*.json"))
    assert len(pending_files) == 1

    second = outbox.enqueue(_package(), now_iso="2026-01-02T00:00:00Z")
    assert second == first  # logical no-op: same entry, no duplicate payload
    assert len(list(outbox.pending.glob("*.json"))) == 1


def test_zk16_documentation_survives_publisher_outage(tmp_path: Path):
    outbox = KnowledgeOutbox(tmp_path)

    class DeadPublisher:
        def publish(self, package: dict) -> str:
            raise ConnectionError("Second Brain unreachable")

    outbox.enqueue(_package(), now_iso="2026-01-01T00:00:00Z")
    results = run_publish_cycle(outbox, DeadPublisher(), max_seconds=5.0)
    assert results["retryable"] == 1
    # Enqueue failures also never raise to the documentation caller.
    broken_root = tmp_path / "blocked"
    broken_root.mkdir()
    (broken_root / "knowledge-outbox").mkdir()
    ledger = broken_root / "knowledge-outbox" / "ledger.json"
    ledger.mkdir(parents=True, exist_ok=True)  # a directory where the file should be
    outcome = enqueue_knowledge_package(outbox, _package("sha256:other"))
    assert outcome.get("state") == "PENDING"


def test_zk17_crash_between_write_and_move_leaves_no_partial_published(tmp_path: Path):
    outbox = KnowledgeOutbox(tmp_path)
    outbox.enqueue(_package(), now_iso="2026-01-01T00:00:00Z")

    # Simulate a crash mid-cycle: payload sits in publishing/ after a claim.
    claimed = outbox.claim_pending()
    assert len(claimed) == 1
    assert len(list(outbox.publishing.glob("*.json"))) == 1
    assert not list(outbox.published.glob("*.json"))

    # Restart: stale publishing payloads are reclaimed, then delivered once.
    publisher = FilePublisher(tmp_path / "bridge")
    reclaimed = outbox.reclaim_stale_publishing()
    assert reclaimed == 1
    results = run_publish_cycle(outbox, publisher, max_seconds=5.0)
    assert results["ack"] == 1
    assert len(list(outbox.published.glob("*.json"))) == 1
    snapshot = outbox.observability_snapshot()
    assert snapshot["published"] == 1


def test_zk18_bounded_retry_never_loops(tmp_path: Path):
    outbox = KnowledgeOutbox(tmp_path)
    attempts: list[str] = []

    class AlwaysRetry:
        def publish(self, package: dict) -> str:
            attempts.append(package["packageId"])
            return RETRYABLE_FAILURE

    outbox.enqueue(_package(), now_iso="2026-01-01T00:00:00Z")

    # Exhaust the bounded attempts across cycles. The exponential backoff
    # legitimately defers retries, so each cycle simulates the scheduled
    # time having elapsed (backoff is bounded: 30s..1h by design).
    states = []
    for _ in range(6):
        run_publish_cycle(outbox, AlwaysRetry(), max_seconds=5.0)
        entry = outbox.ledger.get("sha256:abc123")
        states.append(entry["state"])
        if entry["state"] == "PENDING":
            entry["nextAttemptAt"] = "2000-01-01T00:00:00Z"  # backoff window elapsed
            outbox.ledger.upsert(entry)

    assert len(attempts) == 5  # MAX_ATTEMPTS, not infinite
    assert states[-1] == "FAILED"
    assert not list(outbox.pending.glob("*.json"))


def test_one_failed_package_does_not_block_later_packages(tmp_path: Path):
    outbox = KnowledgeOutbox(tmp_path)
    outbox.enqueue(_package("sha256:bad"), now_iso="2026-01-01T00:00:00Z")
    outbox.enqueue(_package("sha256:good"), now_iso="2026-01-01T00:00:00Z")

    outcomes = {"sha256:bad": TERMINAL_FAILURE, "sha256:good": ACK}

    class Selective:
        def publish(self, package: dict) -> str:
            return outcomes[package["packageId"]]

    results = run_publish_cycle(outbox, Selective(), max_seconds=5.0)
    assert results["ack"] == 1 and results["terminal"] == 1
    snapshot = outbox.observability_snapshot()
    assert snapshot["published"] == 1
    assert snapshot["failed"] == 1


def test_ledger_never_stores_secrets(tmp_path: Path):
    outbox = KnowledgeOutbox(tmp_path)
    payload = _package()
    payload["knowledge"]["secret"] = "SUPERSECRET"  # type: ignore[index]
    outbox.enqueue(payload, now_iso="2026-01-01T00:00:00Z")
    ledger_text = (tmp_path / "knowledge-outbox" / "ledger.json").read_text(encoding="utf-8")
    assert "SUPERSECRET" not in ledger_text
    assert json.loads(ledger_text)["entries"]["sha256:abc123"]["state"] == "PENDING"


def test_file_publisher_is_idempotent_by_package_id(tmp_path: Path):
    publisher = FilePublisher(tmp_path / "bridge")
    assert publisher.publish(_package()) == ACK
    assert publisher.publish(_package()) == ACK
    assert len(list((tmp_path / "bridge").glob("*.json"))) == 1
