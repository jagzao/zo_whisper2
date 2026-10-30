import io
import json

import pytest

from transcript_pipeline.knowledge.service_client import (
    KnowledgeServiceError,
    search_knowledge,
    submit_documents_v3,
    submit_intake,
)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_generic_client_uses_service_contract_and_hides_provider_details(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_SERVICE_URL", "https://knowledge.example.test")
    monkeypatch.setenv("KNOWLEDGE_SERVICE_TOKEN", "client-token")
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, request.get_header("Authorization"), json.loads(request.data), timeout))
        return Response(b'{"status":"EVALUATED","results":[],"semantic":true}')

    result = submit_intake({"schemaVersion": 1, "sourceSystem": "ticketing"}, opener=opener)
    found = search_knowledge({"projectId": "synthetic", "question": "Synthetic?"}, opener=opener)
    assert result["status"] == "EVALUATED"
    assert found["semantic"] is True
    assert seen[0][0] == "https://knowledge.example.test/api/v1/knowledge/intake"
    assert seen[1][0] == "https://knowledge.example.test/api/v1/knowledge/search"
    assert all(item[1] == "Bearer client-token" for item in seen)


def test_client_rejects_http_nonlocal_and_missing_configuration(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_SERVICE_URL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_SERVICE_TOKEN", raising=False)
    with pytest.raises(KnowledgeServiceError, match="not_configured"):
        submit_intake({})
    monkeypatch.setenv("KNOWLEDGE_SERVICE_URL", "http://knowledge.example.test")
    monkeypatch.setenv("KNOWLEDGE_SERVICE_TOKEN", "token")
    with pytest.raises(KnowledgeServiceError, match="invalid_scheme"):
        search_knowledge({})


def test_documents_v3_adapter_uses_generic_source_envelope(monkeypatch):
    from transcript_pipeline.knowledge import gemini_embeddings

    monkeypatch.setattr(gemini_embeddings, "build_curated_chunks", lambda *_args, **_kwargs: {
        "DOCUMENT_EMBEDDING_READY": True,
        "eligible_chunks": [{
            "chunk_id": "chunk-1", "knowledge_id": "knowledge-1", "version": 1,
            "application_id": "synthetic-app", "application": "Synthetic App", "application_aliases": [],
            "topic": "deployment", "canonical_fact": "Synthetic deployments use a canary.",
            "source_evidence_refs": [{"id": "source:1"}], "verification_status": "HUMAN_REVIEWED",
            "confidence": 0.9, "current_live_validation_required": False, "source_session_ids": ["source-1"],
        }],
        "accepted_exclusions": {"excluded-1": "CURATION_POLICY"},
        "rejected_chunks": [],
    })
    sent = []

    def submit(envelope):
        sent.append(envelope)
        return {"status": "EVALUATED"}

    result = submit_documents_v3(
        {"applications": [{"name": "Synthetic App"}], "canonical_facts": []},
        project_id="synthetic-project", source_id="doc-1", owner_content_uat="PASS",
        second_brain_ready="PASS", submit=submit,
    )
    assert result["eligible"] == 1
    assert result["excluded"] == 1
    assert sent[0]["sourceSystem"] == "whisper"
    assert sent[0]["sourceType"] == "documents-v3"
    assert sent[0]["candidateKnowledge"][0]["applicationId"] == "synthetic-app"
    assert sent[0]["approvalContext"] == {"ownerContentUat": "PASS", "secondBrainReady": "PASS"}
