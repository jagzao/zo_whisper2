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


def test_documents_v3_adapter_sends_grounded_candidates_pending_owner_approval():
    sent = []

    def submit(envelope):
        sent.append(envelope)
        return {"status": "EVALUATED"}

    result = submit_documents_v3(
        {
            "quality_state": "READY", "media_id": "source-1", "quality_gates": {"QUALITY_GATE": "PASS"},
            "applications": [{"application_id": "synthetic-app", "name": "Synthetic App", "aliases": []}],
            "canonical_facts": [{
                "knowledge_id": "knowledge-1", "version": 1, "application_id": "synthetic-app",
                "topic": "deployment", "canonical_fact": "Synthetic deployments use a canary.",
                "source_evidence_refs": [{"id": "source:1"}], "verification_state": "SOURCE_CONFIRMED",
                "confidence": 0.9, "source_session": "source-1",
            }],
        },
        project_id="synthetic-project", source_id="doc-1", owner_content_uat="PASS",
        second_brain_ready="PASS", submit=submit,
    )
    assert result["submitted"] == 1
    assert result["excluded"] == 0
    assert sent[0]["sourceSystem"] == "whisper"
    assert sent[0]["sourceType"] == "documents-v3"
    assert sent[0]["candidateKnowledge"][0]["applicationId"] == "synthetic-app"
    assert sent[0]["approvalContext"] == {"ownerContentUat": "PENDING", "secondBrainReady": "PENDING"}
