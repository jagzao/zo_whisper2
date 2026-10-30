"""Whisper-owned adapter for the existing Second Brain Supabase store."""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from transcript_pipeline.config import PROJECT_ROOT
from transcript_pipeline.knowledge.gemini_embeddings import GeminiEmbeddingProvider, query_input

PROVIDER = "gemini-api"
MODEL = "gemini-embedding-2"
DIMENSIONS = 768
SPACE_VERSION = 2
NORMALIZATION = "l2"
INSTRUCTION_VERSION = "retrieval-v1"


class SecondBrainError(RuntimeError):
    pass


class SupabaseSecondBrainStore:
    def __init__(self, url: str | None = None, key: str | None = None, *, opener=None) -> None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        self.url = (url if url is not None else os.getenv("SECOND_BRAIN_SUPABASE_URL", "")).rstrip("/")
        self.key = key if key is not None else os.getenv("SECOND_BRAIN_SERVICE_ROLE_KEY", "")
        self.opener = opener or urllib.request.urlopen
        parsed = urllib.parse.urlparse(self.url)
        if not self.url or not self.key:
            raise SecondBrainError("second_brain_config_missing")
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise SecondBrainError("second_brain_https_required")

    def request(self, resource: str, *, query: dict[str, str] | None = None,
                method: str = "GET", body: dict[str, Any] | None = None,
                prefer: str | None = None) -> Any:
        suffix = "?" + urllib.parse.urlencode(query) if query else ""
        url = f"{self.url}/rest/v1/{resource}{suffix}"
        headers = {"apikey": self.key, "Accept": "application/json", "User-Agent": "Whisper-Knowledge/1.0"}
        if not self.key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.key}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if prefer:
            headers["Prefer"] = prefer
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener(req, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            try:
                error_payload = json.loads(exc.read())
                code = str(error_payload.get("code", "")) if isinstance(error_payload, dict) else ""
                message = str(error_payload.get("message", "")) if isinstance(error_payload, dict) else ""
            except (json.JSONDecodeError, UnicodeDecodeError):
                code, message = "", ""
            detail = ":".join(part for part in (code, message[:180]) if part)
            raise SecondBrainError(f"second_brain_http_{exc.code}" + (f":{detail}" if detail else "")) from None
        except (urllib.error.URLError, OSError, TimeoutError):
            raise SecondBrainError("second_brain_network_error") from None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SecondBrainError("second_brain_invalid_response") from None

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        return self.request(f"rpc/{name}", method="POST", body=payload)

    def register_embedding_space(self) -> str:
        result = self.rpc("register_zavi_knowledge_embedding_space", {
            "p_provider": PROVIDER, "p_model": MODEL, "p_dimensions": DIMENSIONS,
            "p_version": SPACE_VERSION, "p_normalization": NORMALIZATION,
        })
        if not isinstance(result, str) or not result:
            raise SecondBrainError("embedding_space_registration_failed")
        return result

    def list_project_chunks(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.request("zavi_knowledge_chunks", query={
            "select": "id,owner_id,project_id,status,source_type,content,content_hash,topic,confidence,effective_at,valid_until,metadata,document:zavi_knowledge_documents!document_id(title,status,source_type)",
            "owner_id": "eq.single-user", "project_id": f"eq.{project_id}",
            "status": "eq.current", "source_type": "eq.reviewed_canonical",
            "order": "id.asc", "limit": "1000",
        })
        if not isinstance(rows, list):
            raise SecondBrainError("second_brain_rows_invalid")
        return [row for row in rows if isinstance(row, dict)]

    def existing_embeddings(self, space_id: str, chunk_ids: list[str]) -> set[str]:
        if not chunk_ids:
            return set()
        rows = self.request("zavi_knowledge_embeddings", query={
            "select": "chunk_id", "embedding_space_id": f"eq.{space_id}",
            "chunk_id": f"in.({','.join(chunk_ids)})", "limit": "1000",
        })
        if not isinstance(rows, list):
            raise SecondBrainError("embedding_rows_invalid")
        return {str(row["chunk_id"]) for row in rows if isinstance(row, dict) and row.get("chunk_id")}

    def upsert_curated_chunk(self, chunk: dict[str, Any]) -> str:
        doc_id = stable_uuid("document", chunk["project_id"], chunk["content_hash"])
        doc = {
            "id": doc_id, "owner_id": "single-user", "project_id": chunk["project_id"],
            "source_type": "reviewed_canonical", "title": chunk["application"],
            "content_hash": chunk["content_hash"], "status": "current",
            "metadata": {"applicationId": chunk["application_id"], "application": chunk["application"],
                         "aliases": chunk["application_aliases"], "sourceSessionIds": chunk["source_session_ids"]},
        }
        self.request("zavi_knowledge_documents", query={"on_conflict": "id"}, method="POST", body=doc,
                     prefer="resolution=merge-duplicates,return=minimal")
        row_id = stable_uuid("chunk", chunk["chunk_id"])
        row = {
            "id": row_id, "document_id": doc_id, "owner_id": "single-user", "project_id": chunk["project_id"],
            "mode": "client", "kind": "fact", "source_type": "reviewed_canonical",
            "content": chunk["content"], "content_hash": chunk["content_hash"],
            "embedding_model": MODEL, "embedding_version": SPACE_VERSION, "embedding_dimensions": DIMENSIONS,
            "status": "current", "confidence": float(chunk.get("confidence") or 0.5), "authority": 1.0,
            "topic": chunk["topic"], "metadata": {
                "knowledgeId": chunk["knowledge_id"], "canonicalFact": chunk["canonical_fact"],
                "applicationId": chunk["application_id"], "application": chunk["application"],
                "applicationAliases": chunk["application_aliases"], "version": chunk["version"],
                "verificationStatus": chunk["verification_status"], "observedAt": chunk["observed_at"],
                "currentLiveValidationRequired": chunk["current_live_validation_required"],
                "sourceSessionIds": chunk["source_session_ids"], "provenanceRefs": chunk["source_evidence_refs"],
                "embeddingProvider": PROVIDER, "embeddingModel": MODEL,
                "embeddingDimensions": DIMENSIONS, "embeddingInstructionVersion": INSTRUCTION_VERSION,
            },
            "effective_at": chunk["observed_at"] if isinstance(chunk.get("observed_at"), str)
            else datetime.now(timezone.utc).isoformat(),
        }
        self.request("zavi_knowledge_chunks", query={"on_conflict": "id"}, method="POST", body=row,
                     prefer="resolution=merge-duplicates,return=minimal")
        return row_id

    def has_embedding(self, space_id: str, chunk_id: str, source_hash: str, content_digest: str) -> bool:
        rows = self.request("zavi_knowledge_embeddings", query={
            "select": "chunk_id", "embedding_space_id": f"eq.{space_id}", "chunk_id": f"eq.{chunk_id}",
            "source_content_hash": f"eq.{source_hash}", "content_sha256": f"eq.{content_digest}", "limit": "1",
        })
        return isinstance(rows, list) and bool(rows)

    def write_embedding(self, *, space_id: str, chunk_id: str, source_hash: str,
                        content_digest: str, vector: list[float], run_id: str) -> str:
        result = self.rpc("write_zavi_knowledge_embedding_cas", {
            "p_chunk_id": chunk_id, "p_embedding_space_id": space_id,
            "p_source_content_hash": source_hash, "p_content_sha256": content_digest,
            "p_embedding": vector, "p_run_id": run_id,
        })
        if result not in {"written", "exists", "raced", "content_changed", "source_version_changed", "ineligible", "dimension_mismatch"}:
            raise SecondBrainError("embedding_write_result_invalid")
        return result

    def search_vectors(self, *, space_id: str, query_vector: list[float], project_id: str, top_k: int) -> list[dict[str, Any]]:
        rows = self.rpc("search_zavi_knowledge_embedding_space", {
            "p_embedding_space_id": space_id, "p_query_embedding": query_vector,
            "p_project_id": project_id, "p_owner_id": "single-user", "p_top_k": top_k,
        })
        if not isinstance(rows, list):
            raise SecondBrainError("search_response_invalid")
        return [row for row in rows if isinstance(row, dict)]

    def search_vectors_fallback(self, *, space_id: str, query_vector: list[float], project_id: str,
                                current_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current = {str(row.get("id")): row for row in current_chunks if row.get("id")}
        rows = self.request("zavi_knowledge_embeddings", query={
            "select": "chunk_id,embedding,source_content_hash,content_sha256",
            "embedding_space_id": f"eq.{space_id}", "owner_id": "eq.single-user",
            "project_id": f"eq.{project_id}", "limit": "1000",
        })
        if not isinstance(rows, list):
            raise SecondBrainError("embedding_rows_invalid")
        hits = []
        for item in rows:
            chunk_id = str(item.get("chunk_id", ""))
            chunk = current.get(chunk_id)
            if not chunk or item.get("source_content_hash") != chunk.get("content_hash"):
                continue
            if item.get("content_sha256") != document_digest(str(chunk.get("content", ""))):
                continue
            try:
                vector = json.loads(item.get("embedding", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(vector, list) or len(vector) != DIMENSIONS:
                continue
            score = sum(float(left) * float(right) for left, right in zip(query_vector, vector))
            hits.append({"id": chunk_id, "score": score})
        return hits


def stable_uuid(kind: str, *parts: str) -> str:
    digest = bytearray(hashlib.sha256("|".join((kind, *parts)).encode("utf-8")).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x50
    digest[8] = (digest[8] & 0x3F) | 0x80
    value = bytes(digest).hex()
    return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}"


def normalized_vector(vector: list[float]) -> bool:
    return len(vector) == DIMENSIONS and all(math.isfinite(value) for value in vector) and abs(math.sqrt(sum(v * v for v in vector)) - 1) <= 0.01


def document_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def index_curated_chunks(chunks: list[dict[str, Any]], *, owner_content_uat: str,
                         second_brain_ready: str, store: SupabaseSecondBrainStore,
                         provider: GeminiEmbeddingProvider) -> dict[str, Any]:
    if owner_content_uat != "PASS" or second_brain_ready != "PASS":
        raise SecondBrainError("owner_or_readiness_gate_failed")
    for chunk in chunks:
        if (chunk.get("curated") is not True or not chunk.get("knowledge_id")
                or not chunk.get("application_id") or not chunk.get("topic")
                or not chunk.get("canonical_fact") or not chunk.get("source_evidence_refs")
                or not chunk.get("source_session_ids")):
            raise SecondBrainError("chunk_not_embedding_eligible")
    space_id = store.register_embedding_space()
    run_id = str(uuid.uuid4())
    report = {"intended": len(chunks), "embedded": 0, "unchanged": 0, "failed": 0}
    for chunk in chunks:
        row_id = store.upsert_curated_chunk(chunk)
        digest = document_digest(chunk["content"])
        if store.has_embedding(space_id, row_id, chunk["content_hash"], digest):
            report["unchanged"] += 1
            continue
        vectors = provider.embed([chunk["content"]])
        if len(vectors) != 1 or not normalized_vector(vectors[0]):
            report["failed"] += 1
            continue
        result = store.write_embedding(
            space_id=space_id, chunk_id=row_id, source_hash=chunk["content_hash"],
            content_digest=digest, vector=vectors[0], run_id=run_id,
        )
        if result == "written":
            report["embedded"] += 1
        elif result == "exists":
            report["unchanged"] += 1
        else:
            report["failed"] += 1
    return report


def search_knowledge(project_id: str, question: str, *, application_id: str | None = None,
                     topic: str | None = None, top_k: int = 8, store: SupabaseSecondBrainStore | None = None,
                     provider: GeminiEmbeddingProvider | None = None) -> dict[str, Any]:
    if not project_id or not question.strip() or not 1 <= top_k <= 50:
        raise SecondBrainError("search_input_invalid")
    db = store or SupabaseSecondBrainStore()
    embedder = provider or GeminiEmbeddingProvider()
    space_id = db.register_embedding_space()
    vector = embedder.embed([query_input(question)])[0]
    if not normalized_vector(vector):
        raise SecondBrainError("query_embedding_invalid")
    candidates = db.list_project_chunks(project_id)
    try:
        hits = db.search_vectors(space_id=space_id, query_vector=vector, project_id=project_id, top_k=100)
    except SecondBrainError as exc:
        if "42702" not in str(exc):
            raise
        hits = db.search_vectors_fallback(space_id=space_id, query_vector=vector,
                                          project_id=project_id, current_chunks=candidates)
    scores = {str(row.get("id")): float(row.get("score", 0)) for row in hits if row.get("id")}
    results: list[dict[str, Any]] = []
    for row in candidates:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        app_id = metadata.get("applicationId")
        if application_id and app_id != application_id:
            continue
        if topic and str(row.get("topic", "")).casefold() != topic.casefold():
            continue
        score = scores.get(str(row.get("id")), 0.0)
        if score <= 0:
            words = set(question.casefold().split())
            score = len(words & set(str(row.get("content", "")).casefold().split())) / max(len(words), 1) * 0.25
        document = row.get("document") if isinstance(row.get("document"), dict) else {}
        if isinstance(document, list):
            document = document[0] if document and isinstance(document[0], dict) else {}
        results.append({
            "knowledgeId": metadata.get("knowledgeId", row["id"]), "chunkId": row["id"],
            "projectId": row["project_id"], "applicationId": app_id,
            "applicationName": metadata.get("application") or document.get("title"), "topic": row.get("topic"),
            "canonicalKnowledge": metadata.get("canonicalFact") or row.get("content"), "content": row.get("content"),
            "score": score, "verificationStatus": metadata.get("verificationStatus", "UNKNOWN"),
            "observedAt": metadata.get("observedAt") or row.get("effective_at"),
            "currentLiveValidationRequired": bool(metadata.get("currentLiveValidationRequired")),
            "provenanceRefs": metadata.get("provenanceRefs", []),
            "sourceSessionIds": metadata.get("sourceSessionIds", []),
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    return {"results": results[:top_k], "semantic": bool(scores), "degraded": not bool(scores)}
