"""Publisher transport boundary (SPEC §6, PLAN WP-03).

    publish(package) -> ACK | RETRYABLE_FAILURE | TERMINAL_FAILURE

Adapters:
- FilePublisher — deterministic local bridge for tests/air-gapped setups;
- ZaviApiPublisher — HTTP adapter behind explicit configuration.

Zo never holds a Supabase service-role credential: the Zavi API adapter only
carries an ingest token configured server-side by the owner, and even that is
never written to the ledger or logs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

from transcript_pipeline.knowledge.outbox import KnowledgeOutbox

logger = logging.getLogger(__name__)

ACK = "ACK"
RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
TERMINAL_FAILURE = "TERMINAL_FAILURE"


class Publisher(Protocol):
    def publish(self, package: dict) -> str: ...


class FilePublisher:
    """Local deterministic bridge: copies the package payload into a target
    directory atomically. Idempotent by filename (packageId)."""

    def __init__(self, target_dir: Path) -> None:
        self.target_dir = target_dir

    def publish(self, package: dict) -> str:
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
            package_id = str(package["packageId"])
            name = "".join(c if c.isalnum() or c in "-_." else "_" for c in package_id)
            dest = self.target_dir / f"{name}.json"
            tmp = dest.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(dest)
            return ACK
        except OSError as exc:
            logger.warning("[KNOWLEDGE] FilePublisher failed: %s", exc)
            return RETRYABLE_FAILURE


class ZaviApiPublisher:
    """HTTP adapter for Zavi `POST /api/knowledge/import`.

    Enabled only by explicit configuration (`ZAVI_KNOWLEDGE_URL` +
    `ZAVI_KNOWLEDGE_TOKEN`); a missing/unreachable endpoint is a retryable
    failure that never blocks documentation (ZK-16). Transport failures are
    classified: connection/5xx -> RETRYABLE; a definitive 4xx validation
    rejection -> TERMINAL.
    """

    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def publish(self, package: dict) -> str:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            f"{self.base_url}/api/knowledge/import",
            data=json.dumps(package, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                return TERMINAL_FAILURE
            return RETRYABLE_FAILURE
        except (urllib.error.URLError, OSError, TimeoutError):
            return RETRYABLE_FAILURE
        return ACK if 200 <= status < 300 else RETRYABLE_FAILURE


def run_publish_cycle(outbox: KnowledgeOutbox, publisher: Publisher, *, max_seconds: float = 120.0) -> dict:
    """One bounded publish pass: claim due payloads, deliver, record.

    Deterministic and LLM-free. Bounded by `max_seconds` so no caller can
    turn the outbox into a busy loop (ZK-18). One failed package never
    blocks later packages — each is handled independently.
    """
    import time

    started = time.monotonic()
    results = {"ack": 0, "retryable": 0, "terminal": 0, "skipped": 0}
    outbox.reclaim_stale_publishing()
    for payload, payload_path in outbox.claim_pending():
        if time.monotonic() - started > max_seconds:
            # Out of budget: put it back for the next cycle.
            outbox.mark_retryable_failure(payload_path, "cycle_budget_exhausted")
            results["skipped"] += 1
            continue
        try:
            outcome = publisher.publish(payload)
        except Exception as exc:  # noqa: BLE001 - publisher bugs must not kill the cycle
            logger.warning("[KNOWLEDGE] publisher raised: %s", exc)
            outcome = RETRYABLE_FAILURE
        if outcome == ACK:
            outbox.mark_published(payload_path)
            results["ack"] += 1
        elif outcome == TERMINAL_FAILURE:
            outbox.mark_terminal_failure(payload_path, "terminal_rejection")
            results["terminal"] += 1
        else:
            outbox.mark_retryable_failure(payload_path, "delivery_failed")
            results["retryable"] += 1
    return results


def publisher_from_env(env: dict[str, str] | None = None) -> Publisher | None:
    """Builds the configured publisher. Returns None when no publisher is
    configured — enqueue-only mode (packages accumulate in pending/)."""
    import os

    env = env if env is not None else dict(os.environ)
    url = env.get("ZAVI_KNOWLEDGE_URL", "")
    token = env.get("ZAVI_KNOWLEDGE_TOKEN", "")
    if url and token:
        return ZaviApiPublisher(url, token)
    return None


def enqueue_knowledge_package(
    outbox: KnowledgeOutbox, package_payload: dict[str, Any]
) -> dict:
    """Best-effort enqueue used by the documentation hook (WP-04).

    Never raises: an outbox problem must not fail documentation generation
    (ZK-16). The failure is recorded compactly instead.
    """
    try:
        return outbox.enqueue(package_payload)
    except OSError as exc:
        logger.warning("[KNOWLEDGE] outbox enqueue failed: %s", exc)
        return {"state": "ENQUEUE_FAILED", "lastErrorCode": type(exc).__name__}
