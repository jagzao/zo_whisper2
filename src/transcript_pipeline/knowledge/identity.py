"""Deterministic identity for knowledge packages (SPEC §3 Identity).

- sourceId: stable hash of the source media/session identity.
- packageId: deterministic hash of the canonical package payload + schema
  version — same input must always produce the identical packageId.
- knowledgeId: stable logical identity for a source; derived once and then
  persisted/assigned by the caller. Reprocessing unchanged content keeps it;
  changed derivation increments `version` instead of minting a new id.
- fuzzy similarity NEVER auto-supersedes; a new recording is a new
  knowledgeId unless `supersedesKnowledgeId` is explicitly provided.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """Stable JSON canonicalization: sorted keys, fixed separators, no
    incidental formatting differences changing the hash."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_id_for(*, media_name: str, source_hash: str, project_match: str = "default") -> str:
    """Stable source identity: media name + content hash + routing provenance."""
    payload = canonical_json(
        {
            "kind": "zo-knowledge-source",
            "mediaName": media_name,
            "sourceHash": source_hash,
            "projectMatch": project_match,
        }
    )
    return f"sha256:{_sha256_hex(payload)}"


def stable_knowledge_id(source_id: str) -> str:
    """Deterministic logical identity for one source's knowledge artifact.

    Same source (same recording) -> same knowledgeId across reprocessing,
    which is what lets `version` increment instead of duplicating knowledge.
    """
    payload = canonical_json({"kind": "zo-knowledge-id", "sourceId": source_id})
    return f"kn-{_sha256_hex(payload)[:24]}"


def package_id_for(package_payload: dict) -> str:
    """Deterministic package hash over the canonical payload + schema version.

    Two builds from the same derived content must produce the identical
    packageId (idempotent no-op on reprocessing).
    """
    schema_version = package_payload.get("schemaVersion", 2)
    body = {k: v for k, v in package_payload.items() if k != "packageId"}
    payload = canonical_json({"schemaVersion": schema_version, "body": body})
    return f"sha256:{_sha256_hex(payload)}"


def next_version(current_version: int | None, *, content_changed: bool) -> int:
    """Version rule: unchanged derivation keeps the version (idempotent);
    changed derivation for the same knowledgeId increments it."""
    version = current_version or 1
    return version + 1 if content_changed and current_version else version
