"""Owner-approved curated chunk handoff to Zavi's existing knowledge API."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


def build_import_payload(*, package_id: str, readiness: dict[str, Any], chunk_report: dict[str, Any]) -> dict[str, Any]:
    if readiness.get("OWNER_CONTENT_UAT") != "PASS" or readiness.get("SECOND_BRAIN_READY") != "PASS":
        raise ValueError("knowledge_not_owner_approved")
    if chunk_report.get("DOCUMENT_EMBEDDING_READY") is not True:
        raise ValueError("document_embedding_not_ready")
    chunks = chunk_report.get("eligible_chunks", [])
    if not chunks:
        raise ValueError("no_embedding_eligible_chunks")
    return {
        "schemaVersion": 1,
        "packageId": package_id,
        "ownerContentUat": "PASS",
        "secondBrainReady": "PASS",
        "embeddingReady": "YES",
        "projectId": "P&G",
        "intendedChunkIds": list(chunk_report["intended_chunk_ids"]),
        "acceptedExclusions": dict(chunk_report.get("accepted_exclusions", {})),
        "chunks": chunks,
    }


class ZaviCuratedImportPublisher:
    """Send curated-only input to Zavi; secrets stay in backend environment."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30,
                 opener: Callable[..., Any] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/api/knowledge/import",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token}"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                result = json.loads(response.read())
                return result if isinstance(result, dict) else {"success": False, "error": "invalid_response"}
        except urllib.error.HTTPError as exc:
            return {"success": False, "error": f"http_{exc.code}"}
        except (urllib.error.URLError, OSError, TimeoutError):
            return {"success": False, "error": "network_error"}


def publisher_from_env(env: dict[str, str] | None = None) -> ZaviCuratedImportPublisher | None:
    values = env if env is not None else os.environ
    url, token = values.get("ZAVI_KNOWLEDGE_URL", ""), values.get("ZAVI_KNOWLEDGE_TOKEN", "")
    if not url or not token:
        return None
    return ZaviCuratedImportPublisher(url, token)
