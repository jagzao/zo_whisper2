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
    from transcript_pipeline.knowledge.gemini_embeddings import build_curated_chunks

    report = build_curated_chunks(
        pack, owner_content_uat=owner_content_uat, second_brain_ready=second_brain_ready, project_id=project_id
    )
    if not report["DOCUMENT_EMBEDDING_READY"] or report["rejected_chunks"]:
        raise KnowledgeServiceError("documents_v3_learning_gate_failed")
    candidates = []
    for chunk in report["eligible_chunks"]:
        candidates.append(
            {
                "candidateId": chunk["knowledge_id"],
                "knowledgeId": chunk["knowledge_id"],
                "version": chunk["version"],
                "applicationId": chunk["application_id"],
                "applicationName": chunk["application"],
                "applicationAliases": chunk["application_aliases"],
                "topic": chunk["topic"],
                "canonicalKnowledge": chunk["canonical_fact"],
                "evidenceRefs": chunk["source_evidence_refs"],
                "qualityPassed": True,
                "confidencePassed": True,
                "useful": True,
                "confidence": chunk["confidence"],
                "verificationStatus": chunk["verification_status"],
                "currentLiveValidationRequired": chunk["current_live_validation_required"],
                "sourceSessionIds": chunk["source_session_ids"],
            }
        )
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
        "approvalContext": {
            "ownerContentUat": owner_content_uat,
            "secondBrainReady": second_brain_ready,
        },
        "metadata": {"sessionId": source_id, "documentType": "documents-v3", "mediaId": pack.get("media_id")},
    }
    result = submit(envelope)
    return {"eligible": len(candidates), "excluded": len(report["accepted_exclusions"]), "result": result}
