import math

import pytest

from transcript_pipeline.knowledge.second_brain import (
    DIMENSIONS,
    SecondBrainError,
    SupabaseSecondBrainStore,
    index_curated_chunks,
    stable_uuid,
)


class FakeStore:
    def __init__(self):
        self.embedded = set()
        self.upserts = 0
        self.writes = 0
        self.retired = 0

    def register_embedding_space(self):
        return "space-id"

    def upsert_curated_chunk(self, chunk):
        self.upserts += 1
        return "chunk-id"

    def has_embedding(self, space_id, chunk_id, source_hash, digest):
        return (space_id, chunk_id, source_hash, digest) in self.embedded

    def write_embedding(self, *, space_id, chunk_id, source_hash, content_digest, vector, run_id):
        self.writes += 1
        self.embedded.add((space_id, chunk_id, source_hash, content_digest))
        return "written"

    def retire_superseded_chunks(self, project_id, knowledge_id, current_chunk_id, current_version):
        return self.retired


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        assert len(texts) == 1
        return [[1 / math.sqrt(DIMENSIONS)] * DIMENSIONS]


def _chunk(**changes):
    chunk = {
        "curated": True, "knowledge_id": "k1", "chunk_id": "c1", "project_id": "P&G",
        "application_id": "app1", "application": "Synthetic App", "application_aliases": [],
        "topic": "authentication", "canonical_fact": "Uses SSO.", "content": "Synthetic curated fact.",
        "content_hash": "sha256:" + "a" * 64, "confidence": 0.9, "version": 1,
        "verification_status": "HUMAN_REVIEWED", "observed_at": "2026-10-29T10:00:00Z",
        "current_live_validation_required": True, "source_session_ids": ["session-1"],
        "source_evidence_refs": [{"id": "e1"}],
    }
    chunk.update(changes)
    return chunk


def test_indexing_is_idempotent_and_never_embeds_ineligible_facts():
    store, provider = FakeStore(), FakeProvider()
    report = index_curated_chunks([_chunk()], owner_content_uat="PASS", second_brain_ready="PASS", store=store, provider=provider)
    repeated = index_curated_chunks([_chunk()], owner_content_uat="PASS", second_brain_ready="PASS", store=store, provider=provider)
    assert report == {"intended": 1, "embedded": 1, "unchanged": 0, "retired": 0, "failed": 0}
    assert repeated == {"intended": 1, "embedded": 0, "unchanged": 1, "retired": 0, "failed": 0}
    assert (provider.calls, store.upserts, store.writes) == (1, 2, 1)

    with pytest.raises(SecondBrainError, match="owner_or_readiness_gate_failed"):
        index_curated_chunks([_chunk()], owner_content_uat="FAIL", second_brain_ready="PASS", store=store, provider=provider)
    with pytest.raises(SecondBrainError, match="chunk_not_embedding_eligible"):
        index_curated_chunks([_chunk(curated=False)], owner_content_uat="PASS", second_brain_ready="PASS", store=store, provider=provider)
    assert provider.calls == 1


def test_register_space_includes_instruction_identity():
    class Store(SupabaseSecondBrainStore):
        def __init__(self):
            self.payload = None

        def rpc(self, name, payload):
            self.payload = (name, payload)
            return "space-id"

    store = Store()
    assert store.register_embedding_space() == "space-id"
    assert store.payload[1]["p_instruction_version"] == "retrieval-v1"


def test_newer_canonical_version_retires_only_older_version_and_records_link():
    store = SupabaseSecondBrainStore("https://db.example", "key")
    patches = []
    prior = [{"id": "old-row", "metadata": {"knowledgeId": "k1", "version": 1}}]
    store.list_project_chunks = lambda project_id: prior

    def request(resource, *, query=None, method="GET", body=None, prefer=None):
        if method == "GET":
            return [{"id": "new-row", "metadata": {"knowledgeId": "k1", "version": 2}}]
        patches.append((query, method, body))
        return None

    store.request = request
    assert store.retire_superseded_chunks("p1", "k1", "new-row", 2) == 1
    assert patches[0][2]["supersedes"] == "old-row"
    assert patches[0][2]["metadata"]["supersedesChunkIds"] == ["old-row"]
    assert patches[1][2]["status"] == "superseded"
    assert patches[1][2]["metadata"]["supersededByChunkId"] == "new-row"


def test_external_chunk_id_is_written_to_canonical_row():
    store = SupabaseSecondBrainStore("https://db.example", "key")
    bodies = []

    def request(resource, *, query=None, method="GET", body=None, prefer=None):
        bodies.append((resource, body))
        return None

    store.request = request
    row_id = store.upsert_curated_chunk(_chunk())
    chunk_row = next(body for resource, body in bodies if resource == "zavi_knowledge_chunks")
    assert chunk_row["id"] == row_id
    assert chunk_row["external_chunk_id"] == "c1"


def test_second_brain_rest_adapter_requires_https_and_server_key():
    with pytest.raises(SecondBrainError, match="second_brain_https_required"):
        SupabaseSecondBrainStore("http://db.example", "secret")
    with pytest.raises(SecondBrainError, match="second_brain_config_missing"):
        SupabaseSecondBrainStore("https://db.example", "")
    assert stable_uuid("chunk", "same") == stable_uuid("chunk", "same")
    assert stable_uuid("chunk", "same") != stable_uuid("chunk", "other")
