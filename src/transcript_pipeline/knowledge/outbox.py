"""Durable knowledge outbox (SPEC §5, PLAN WP-03).

Layout under `DATA_ROOT/knowledge-outbox/`:

    pending/    enqueued, not yet delivered
    publishing/ claimed by a publisher run (crash-safe via reclaim)
    published/  acknowledged
    failed/     terminal or exhausted retries (inspectable)
    ledger.json global idempotency + observability ledger

Guarantees:
- atomic writes/moves only (tmp + os.replace / Path.replace);
- packageId idempotency: the same package is never logically enqueued twice;
- bounded retry with bounded backoff — no busy loop;
- a publisher outage never corrupts documentation (enqueue is best-effort
  from the caller's perspective: failures are recorded, not raised upward);
- no secret ever enters the ledger.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from transcript_pipeline.knowledge.ledger import KnowledgeLedger

PENDING_DIR = "pending"
PUBLISHING_DIR = "publishing"
PUBLISHED_DIR = "published"
FAILED_DIR = "failed"

MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 3600.0
# Publisher loops are bounded by wall clock, never unbounded (ZK-18).
MAX_PUBLISH_LOOP_SECONDS = 120.0


@dataclass(frozen=True)
class OutboxEntry:
    package_id: str
    knowledge_id: str
    state: str = "PENDING"
    attempt: int = 0
    created_at: str = ""
    next_attempt_at: str = ""
    last_error_code: str | None = None
    last_result_code: str | None = None

    def to_dict(self) -> dict:
        return {
            "packageId": self.package_id,
            "knowledgeId": self.knowledge_id,
            "attempt": self.attempt,
            "state": self.state,
            "createdAt": self.created_at,
            "nextAttemptAt": self.next_attempt_at,
            "lastErrorCode": self.last_error_code,
            "lastResultCode": self.last_result_code,
        }


class KnowledgeOutbox:
    def __init__(self, data_root: Path) -> None:
        self.root = data_root / "knowledge-outbox"
        self.pending = self.root / PENDING_DIR
        self.publishing = self.root / PUBLISHING_DIR
        self.published = self.root / PUBLISHED_DIR
        self.failed = self.root / FAILED_DIR
        self.ledger = KnowledgeLedger(self.root)

    def ensure_layout(self) -> None:
        for directory in (self.pending, self.publishing, self.published, self.failed):
            directory.mkdir(parents=True, exist_ok=True)

    def enqueue(self, package_payload: dict, *, now_iso: str = "") -> dict:
        """Enqueues a package atomically; idempotent by packageId.

        Reprocessing an unchanged package returns the existing entry as a
        logical no-op (ZK-08): nothing is duplicated, no new attempt starts.
        """
        self.ensure_layout()
        package_id = str(package_payload["packageId"])
        existing = self.ledger.get(package_id)
        terminal_states = {"PUBLISHED", "FAILED"}
        if existing and existing.get("state") in terminal_states:
            return existing
        if existing and existing.get("state") == "PENDING":
            # Already queued: keep the original schedule — a reprocessed
            # unchanged package must not fast-track a backed-off retry.
            # (If the payload file vanished, re-enqueue it below.)
            if (self.pending / f"{_safe_name(package_id)}.json").exists() or (
                self.publishing / f"{_safe_name(package_id)}.json"
            ).exists():
                return existing

        entry = OutboxEntry(
            package_id=package_id,
            knowledge_id=str(package_payload.get("knowledgeId", "")),
            state="PENDING",
            attempt=0,
            created_at=existing.get("createdAt") if existing else (now_iso or _now_iso()),
            next_attempt_at=now_iso or _now_iso(),
        )
        # Atomic payload write: tmp inside the same pending dir, then rename.
        payload_path = self.pending / f"{_safe_name(package_id)}.json"
        _atomic_write_json(payload_path, package_payload)
        self.ledger.upsert(entry.to_dict())
        return entry.to_dict()

    def claim_pending(self) -> list[tuple[dict, Path]]:
        """Moves due pending payloads to publishing/ and returns them.

        A crash between write and move can only leave a payload in pending/
        or publishing/ — never a half state (ZK-17): moves are atomic
        renames on the same filesystem, and `reclaim_stale_publishing`
        recovers leftovers on the next run.
        """
        self.ensure_layout()
        claimed: list[tuple[dict, Path]] = []
        now = time.time()
        for payload_path in sorted(self.pending.glob("*.json")):
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # Corrupt payload is quarantined to failed/, never retried.
                _move(payload_path, self.failed)
                continue
            entry = self.ledger.get(str(payload.get("packageId", ""))) or {}
            next_at = entry.get("nextAttemptAt") or ""
            if next_at and _parse_iso(next_at) > now:
                continue
            target = self.publishing / payload_path.name
            _move(payload_path, self.publishing)
            claimed.append((payload, target))
        return claimed

    def reclaim_stale_publishing(self) -> int:
        """Returns payloads stuck in publishing/ back to pending/ — the
        crash-recovery path that makes the outbox restartable."""
        self.ensure_layout()
        reclaimed = 0
        for payload_path in sorted(self.publishing.glob("*.json")):
            _move(payload_path, self.pending)
            reclaimed += 1
        return reclaimed

    def mark_published(self, payload_path: Path) -> None:
        entry = self._entry_for(payload_path)
        package_id = entry.get("packageId") or payload_path.stem
        _move(payload_path, self.published)
        record = {
            **entry,
            "packageId": package_id,
            "state": "PUBLISHED",
            "lastResultCode": "ACK",
            "lastErrorCode": None,
        }
        self.ledger.upsert(record)

    def mark_retryable_failure(self, payload_path: Path, error_code: str) -> str:
        """Records a retryable failure; moves to failed/ when attempts are
        exhausted. Returns the new state ('PENDING' or 'FAILED')."""
        entry = self._entry_for(payload_path)
        package_id = entry.get("packageId") or payload_path.stem
        attempt = int(entry.get("attempt", 0)) + 1
        if attempt >= MAX_ATTEMPTS:
            _move(payload_path, self.failed)
            record = {
                **entry,
                "packageId": package_id,
                "state": "FAILED",
                "attempt": attempt,
                "lastResultCode": "RETRYABLE_FAILURE",
                "lastErrorCode": error_code,
            }
            self.ledger.upsert(record)
            return "FAILED"
        backoff = min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
        _move(payload_path, self.pending)
        record = {
            **entry,
            "packageId": package_id,
            "state": "PENDING",
            "attempt": attempt,
            "nextAttemptAt": _iso_plus_seconds(backoff),
            "lastResultCode": "RETRYABLE_FAILURE",
            "lastErrorCode": error_code,
        }
        self.ledger.upsert(record)
        return "PENDING"

    def mark_terminal_failure(self, payload_path: Path, error_code: str) -> None:
        entry = self._entry_for(payload_path)
        package_id = entry.get("packageId") or payload_path.stem
        _move(payload_path, self.failed)
        record = {
            **entry,
            "packageId": package_id,
            "state": "FAILED",
            "lastResultCode": "TERMINAL_FAILURE",
            "lastErrorCode": error_code,
        }
        self.ledger.upsert(record)

    def _entry_for(self, payload_path: Path) -> dict:
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return self.ledger.get(str(payload.get("packageId", ""))) or {
            "packageId": payload.get("packageId", payload_path.stem),
            "knowledgeId": payload.get("knowledgeId", ""),
        }

    def observability_snapshot(self) -> dict:
        return self.ledger.snapshot()


def _safe_name(package_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in package_id)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _move(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    src.replace(target)
    return target


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_iso(value: str) -> float:
    import datetime as _dt

    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _iso_plus_seconds(seconds: float) -> str:
    import datetime as _dt

    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
