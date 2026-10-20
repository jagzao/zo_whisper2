"""Durable knowledge outbox ledger (SPEC §5).

One JSON ledger under `knowledge-outbox/ledger.json` records every package
ever enqueued. Writes are atomic (tmp + os.replace). The ledger never stores
secrets or raw transcripts — only ids, counters, timestamps and typed error
codes.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

LEDGER_FILE = "ledger.json"
MAX_LEDGER_ENTRIES = 5000


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class KnowledgeLedger:
    """Process-safe bounded ledger of outbox entries."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / LEDGER_FILE
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"entries": {}}
        if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
            return {"entries": {}}
        return data

    def upsert(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Adds/updates one package entry atomically; bounded size."""
        with self._lock:
            data = self.load()
            entries: dict[str, Any] = data["entries"]
            entries[str(entry["packageId"])] = entry
            # Bound the ledger: drop the oldest entries by createdAt.
            if len(entries) > MAX_LEDGER_ENTRIES:
                ordered = sorted(
                    entries.items(), key=lambda kv: kv[1].get("createdAt", "")
                )
                for key, _ in ordered[: len(entries) - MAX_LEDGER_ENTRIES]:
                    del entries[key]
            _atomic_write_json(self.path, data)
            return data

    def get(self, package_id: str) -> dict[str, Any] | None:
        return self.load()["entries"].get(package_id)

    def snapshot(self) -> dict[str, Any]:
        """Compact observability view (WP-17): counts + last typed result.
        Never includes secrets or transcripts."""
        data = self.load()
        entries = list(data["entries"].values())
        return {
            "pending": sum(1 for e in entries if e.get("state") == "PENDING"),
            "published": sum(1 for e in entries if e.get("state") == "PUBLISHED"),
            "failed": sum(1 for e in entries if e.get("state") == "FAILED"),
            "last_package_id": entries[-1]["packageId"] if entries else None,
            "last_result": (entries[-1].get("lastResultCode") if entries else None),
            "last_error_code": (entries[-1].get("lastErrorCode") if entries else None),
        }
