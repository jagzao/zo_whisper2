import json

import pytest

from transcript_pipeline.knowledge.gemini_embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_INSTRUCTION_VERSION,
    GeminiEmbeddingProvider,
    build_curated_chunks,
    document_input,
    evaluate_pack_readiness,
    query_input,
)
from transcript_pipeline.knowledge.zavi_curated_import import build_import_payload, publisher_from_env


def _pack():
    return {
        "applications": [{"application_id": "app-a", "name": "App A"}],
        "canonical_facts": [
            {"knowledge_id": "k1", "version": 1, "application_id": "app-a", "topic": "Purpose",
             "canonical_fact": "App A serves users.", "confidence": .91,
             "verification_state": "SOURCE_CONFIRMED", "source_session": "s41",
             "source_evidence_refs": [{"event_id": "e1"}]},
            {"knowledge_id": "k2", "version": 1, "application_id": "app-a", "topic": "Access",
             "canonical_fact": "App A has unresolved access details.", "confidence": .75,
             "verification_state": "SOURCE_CONFIRMED", "source_session": "s41",
             "source_evidence_refs": [{"event_id": "e2"}]},
        ],
    }


def test_curated_chunking_requires_owner_and_package_readiness():
    report = build_curated_chunks(_pack(), owner_content_uat="PENDING", second_brain_ready="PASS")
    assert not report["eligible_chunks"]
    assert report["rejected_chunks"][0]["rejection_reasons"] == ["OWNER_OR_PACKAGE_NOT_APPROVED"]


def test_second_brain_readiness_requires_owner_and_producer_quality_gates():
    pack = _pack()
    pack["quality_gates"] = {"QUALITY_GATE": "PASS", "CLAIM_LEDGER": "PASS",
                             "APPLICATION_RESOLUTION": "PASS", "PROCEDURE_GROUNDING": "NOT_APPLICABLE",
                             "KAV_RUNBOOK_VALIDATION": "NOT_APPLICABLE"}
    assert evaluate_pack_readiness(pack, owner_content_uat="PENDING")["SECOND_BRAIN_READY"] == "FAIL"
    assert evaluate_pack_readiness(pack, owner_content_uat="PASS")["SECOND_BRAIN_READY"] == "PASS"


def test_curated_chunk_carries_identity_provenance_and_embedding_contract():
    report = build_curated_chunks(_pack(), owner_content_uat="PASS", second_brain_ready="PASS")
    assert len(report["eligible_chunks"]) == 1
    chunk = report["eligible_chunks"][0]
    assert chunk["chunk_id"].startswith("chunk-")
    assert chunk["project_id"] == "P&G"
    assert chunk["source_evidence_refs"] == [{"event_id": "e1"}]
    assert chunk["embedding_model"] == "gemini-embedding-2"
    assert chunk["embedding_dimensions"] == EMBEDDING_DIMENSIONS == 768
    assert chunk["embedding_instruction_version"] == EMBEDDING_INSTRUCTION_VERSION
    assert "LOW_CONFIDENCE" in next(iter(report["accepted_exclusions"].values()))
    assert report["DOCUMENT_EMBEDDING_READY"]
    assert report["accepted_exclusions"]


def test_document_and_query_inputs_use_versioned_retrieval_instructions():
    assert "title: App A | text:" in document_input("App A", "Purpose", "Serves users")
    assert "task: question answering | query:" in query_input("What is App A for?")


def test_gemini_provider_uses_supported_embedding2_request_and_validates_vectors():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"embedding": {"values": [0.25] * 768}}).encode()

    observed = {}

    def opener(request, timeout):
        observed["request"] = request
        observed["timeout"] = timeout
        return Response()

    vectors = GeminiEmbeddingProvider("test-secret", opener=opener).embed(["curated content"])
    body = json.loads(observed["request"].data)
    assert len(vectors[0]) == 768
    assert observed["request"].get_header("X-goog-api-key") == "test-secret"
    assert observed["request"].full_url.endswith("gemini-embedding-2:embedContent")
    assert body["output_dimensionality"] == 768
    assert "task_type" not in body


def test_gemini_provider_rejects_nonfinite_or_wrong_length_vectors():
    class Response:
        def __init__(self, values):
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"embedding": {"values": self.values}}).encode()

    with pytest.raises(RuntimeError, match="gemini_dimension_mismatch"):
        GeminiEmbeddingProvider("key", opener=lambda *_args, **_kwargs: Response([0.1])).embed(["x"])
    with pytest.raises(RuntimeError, match="gemini_invalid_vector"):
        GeminiEmbeddingProvider("key", opener=lambda *_args, **_kwargs: Response([float("nan")] * 768)).embed(["x"])


def test_zavi_handoff_contains_only_eligible_curated_chunks_and_full_accounting():
    pack = _pack()
    pack["quality_gates"] = {"QUALITY_GATE": "PASS", "CLAIM_LEDGER": "PASS",
                             "APPLICATION_RESOLUTION": "PASS", "PROCEDURE_GROUNDING": "NOT_APPLICABLE",
                             "KAV_RUNBOOK_VALIDATION": "NOT_APPLICABLE"}
    readiness = evaluate_pack_readiness(pack, owner_content_uat="PASS")
    chunks = build_curated_chunks(pack, owner_content_uat="PASS",
                                  second_brain_ready=readiness["SECOND_BRAIN_READY"])
    payload = build_import_payload(package_id="pkg-test", readiness=readiness, chunk_report=chunks)
    assert payload["intendedChunkIds"] == chunks["intended_chunk_ids"]
    assert payload["acceptedExclusions"] == chunks["accepted_exclusions"]
    assert len(payload["chunks"]) == 1
    assert not any("transcript" in key.casefold() or "ocr" in key.casefold()
                   for chunk in payload["chunks"] for key in chunk)
    with pytest.raises(ValueError, match="knowledge_not_owner_approved"):
        build_import_payload(package_id="pkg-test", readiness={**readiness, "OWNER_CONTENT_UAT": "PENDING"},
                             chunk_report=chunks)


def test_zavi_publisher_requires_backend_url_and_token():
    assert publisher_from_env({}) is None
    assert publisher_from_env({"ZAVI_KNOWLEDGE_URL": "https://zavi.example"}) is None
