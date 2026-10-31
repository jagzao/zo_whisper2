"""Source adapter for the generic Knowledge Service API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class KnowledgeServiceError(RuntimeError):
    pass


def submit_intake(envelope: dict[str, Any], *, opener=None, timeout: float = 15.0) -> dict[str, Any]:
    base = os.getenv("KNOWLEDGE_SERVICE_URL", "").rstrip("/")
    token = os.getenv("KNOWLEDGE_SERVICE_TOKEN", "")
    if not base or not token:
        raise KnowledgeServiceError("knowledge_service_not_configured")
    parsed = urllib.parse.urlparse(base)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or (parsed.scheme != "https" and not (local and parsed.scheme == "http")):
        raise KnowledgeServiceError("knowledge_service_invalid_scheme")
    request = urllib.request.Request(
        f"{base}/api/v1/knowledge/intake",
        data=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            payload = json.loads(response.read())
            if not isinstance(payload, dict):
                raise KnowledgeServiceError("knowledge_service_invalid_response")
            return payload
    except urllib.error.HTTPError as exc:
        raise KnowledgeServiceError(f"knowledge_service_http_{exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise KnowledgeServiceError("knowledge_service_unavailable") from None


def search_knowledge(payload: dict[str, Any], *, opener=None, timeout: float = 15.0) -> dict[str, Any]:
    base = os.getenv("KNOWLEDGE_SERVICE_URL", "").rstrip("/")
    token = os.getenv("KNOWLEDGE_SERVICE_TOKEN", "")
    if not base or not token:
        raise KnowledgeServiceError("knowledge_service_not_configured")
    parsed = urllib.parse.urlparse(base)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or (parsed.scheme != "https" and not (local and parsed.scheme == "http")):
        raise KnowledgeServiceError("knowledge_service_invalid_scheme")
    request = urllib.request.Request(
        f"{base}/api/v1/knowledge/search",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            result = json.loads(response.read())
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                raise KnowledgeServiceError("knowledge_service_invalid_response")
            return result
    except urllib.error.HTTPError as exc:
        raise KnowledgeServiceError(f"knowledge_service_http_{exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise KnowledgeServiceError("knowledge_service_unavailable") from None


def submit_documents_v3(
    pack: dict[str, Any],
    *,
    project_id: str,
    source_id: str,
    owner_content_uat: str,
    second_brain_ready: str,
    submit=submit_intake,
) -> dict[str, Any]:
    gates = pack.get("quality_gates", {})
    facts = pack.get("canonical_facts", [])
    if (pack.get("quality_state") != "READY" or not isinstance(gates, dict)
            or gates.get("QUALITY_GATE") != "PASS" or not isinstance(facts, list)):
        raise KnowledgeServiceError("documents_v3_quality_gate_failed")
    candidates = []
    excluded = 0
    for fact in facts:
        if not isinstance(fact, dict):
            excluded += 1
            continue
        content = fact.get("canonical_fact")
        refs = fact.get("source_evidence_refs")
        confidence = fact.get("confidence")
        if (not isinstance(content, str) or not content.strip() or not isinstance(refs, list) or not refs
                or not isinstance(confidence, (int, float)) or isinstance(confidence, bool)):
            excluded += 1
            continue
        candidates.append(
            {
                "candidateId": fact.get("knowledge_id"),
                "knowledgeId": fact.get("knowledge_id"),
                "version": fact.get("version", 1),
                "applicationId": fact.get("application_id"),
                "applicationName": next((item.get("name") for item in pack.get("applications", [])
                                          if item.get("application_id") == fact.get("application_id")), None),
                "applicationAliases": next((item.get("aliases", []) for item in pack.get("applications", [])
                                             if item.get("application_id") == fact.get("application_id")), []),
                "topic": fact.get("topic"),
                "canonicalKnowledge": content,
                "evidenceRefs": refs,
                "qualityPassed": True,
                "confidencePassed": confidence >= 0.8,
                "useful": True,
                "confidence": confidence,
                "verificationStatus": ("HUMAN_REVIEWED" if fact.get("verification_state") == "SOURCE_CONFIRMED"
                                        else "SOURCE_UNCERTAIN"),
                "currentLiveValidationRequired": bool(fact.get("current_live_validation_required")),
                "sourceSessionIds": fact.get("source_sessions") or [fact.get("source_session", source_id)],
            }
        )
    if not candidates:
        raise KnowledgeServiceError("documents_v3_no_grounded_candidates")
    envelope = {
        "schemaVersion": 1,
        "sourceSystem": "whisper",
        "sourceType": "documents-v3",
        "sourceId": source_id,
        "projectId": project_id,
        "observedAt": None,
        "applicationContextHints": {"applicationHints": [item["name"] for item in pack.get("applications", [])]},
        "candidateKnowledge": candidates,
        "evidenceRefs": [],
        # Pack generation establishes technical quality only. Owner approval stays separate.
        "approvalContext": {"ownerContentUat": "PENDING", "secondBrainReady": "PENDING"},
        "metadata": {"sessionId": source_id, "documentType": "documents-v3", "mediaId": pack.get("media_id")},
    }
    result = submit(envelope)
    return {"submitted": len(candidates), "excluded": excluded, "approvalState": "PENDING", "result": result}
