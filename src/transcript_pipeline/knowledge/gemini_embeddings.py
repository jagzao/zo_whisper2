"""Curated retrieval chunks and Gemini Embedding 2 API adapter."""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from transcript_pipeline.documentation.kav_contract import embedding_ready
from transcript_pipeline.documentation.kav_contract import second_brain_ready as evaluate_second_brain_ready

EMBEDDING_PROVIDER = "Gemini"
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_INSTRUCTION_VERSION = "retrieval-v1"
PROJECT_ID = "P&G"


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def document_input(application: str, topic: str, fact: str) -> str:
    return f"title: {application} | text: Application: {application} | Topic: {topic} | Knowledge: {_normalized(fact)}"


def query_input(query: str) -> str:
    return f"task: question answering | query: {_normalized(query)}"


def evaluate_pack_readiness(pack: dict[str, Any], *, owner_content_uat: str) -> dict[str, Any]:
    gates = pack.get("quality_gates", {})
    facts = pack.get("canonical_facts", [])
    policy_pass = bool(facts) and all(
        isinstance(item.get("canonical_fact"), str) and item["canonical_fact"].strip()
        and isinstance(item.get("source_evidence_refs"), list) and item["source_evidence_refs"]
        and not any(secret in item["canonical_fact"].casefold()
                    for secret in ("password:", "token:", "secret:", "api key:"))
        for item in facts
    )
    procedure_gate = gates.get("PROCEDURE_GROUNDING", "FAIL")
    runbook_gate = gates.get("KAV_RUNBOOK_VALIDATION", "FAIL")
    status = "PASS" if owner_content_uat == "PASS" else "FAIL"
    if status == "PASS":
        status = evaluate_second_brain_ready(
            quality_gate=gates.get("QUALITY_GATE", "FAIL"),
            claim_provenance=gates.get("CLAIM_LEDGER", "FAIL"),
            application_resolution=gates.get("APPLICATION_RESOLUTION", "FAIL"),
            has_application=bool(pack.get("applications")),
            conflicts_promoted=any(item.get("verification_state") == "CONFLICTING" for item in facts),
            package_policy="PASS" if policy_pass else "FAIL",
            raw_transcript_published=False,
            raw_media_published=False,
            procedure_gate=procedure_gate,
            runbook_gate=runbook_gate,
        )
    return {"SECOND_BRAIN_READY": status, "OWNER_CONTENT_UAT": owner_content_uat,
            "PACKAGE_POLICY": "PASS" if policy_pass else "FAIL"}


def build_curated_chunks(pack: dict[str, Any], *, owner_content_uat: str,
                         second_brain_ready: str) -> dict[str, Any]:
    """Build one chunk per approved canonical fact; keep exclusions explicit."""
    facts = pack.get("canonical_facts", [])
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if owner_content_uat != "PASS" or second_brain_ready != "PASS":
        return {"eligible_chunks": [], "rejected_chunks": [
            {"knowledge_id": "*", "rejection_reasons": ["OWNER_OR_PACKAGE_NOT_APPROVED"]}
        ], "intended_chunk_ids": []}

    for fact in facts:
        application_id = str(fact.get("application_id") or "")
        app = next((item for item in pack.get("applications", [])
                    if item.get("application_id") == application_id), {})
        topic = str(fact.get("topic") or "").strip()
        text = str(fact.get("canonical_fact") or "").strip()
        if not application_id or not app.get("name") or not topic or not text:
            rejected.append({"knowledge_id": fact.get("knowledge_id"), "rejection_reasons": ["MISSING_SEMANTIC_IDENTITY"]})
            continue
        content = _normalized(document_input(str(app["name"]), topic, text))
        content_hash = "sha256:" + _hash(content)
        chunk = {
            "chunk_id": "chunk-" + _hash("|".join((str(fact.get("knowledge_id", "")),
                                                       str(fact.get("version", 1)), topic, content)))[:24],
            "knowledge_id": str(fact.get("knowledge_id") or ""),
            "version": int(fact.get("version") or 1),
            "project_id": PROJECT_ID,
            "application_id": application_id,
            "application": str(app["name"]),
            "application_aliases": [str(alias) for alias in app.get("aliases", []) if alias],
            "topic": topic,
            "canonical_topic": topic,
            "content": content,
            "canonical_fact": text,
            "verification_status": ("HUMAN_REVIEWED" if fact.get("verification_state") == "SOURCE_CONFIRMED"
                                     else "SOURCE_UNCERTAIN"),
            "source_verification_state": fact.get("verification_state"),
            "confidence": fact.get("confidence"),
            "observed_at": fact.get("observed_at"),
            "current_live_validation_required": bool(fact.get("current_live_validation_required")),
            "source_session_ids": list(fact.get("source_sessions") or [fact.get("source_session")]
                                        if fact.get("source_sessions") or fact.get("source_session") else []),
            "source_evidence_refs": [ref for ref in fact.get("source_evidence_refs", []) if isinstance(ref, dict)],
            "source_knowledge_ids": [str(fact.get("knowledge_id"))],
            "provenance_pointers": [ref for ref in fact.get("source_evidence_refs", []) if isinstance(ref, dict)],
            "content_hash": content_hash,
            "embedding_provider": EMBEDDING_PROVIDER,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "embedding_instruction_version": EMBEDDING_INSTRUCTION_VERSION,
            "curated": True,
        }
        candidates.append(chunk)
    intended = {item["chunk_id"] for item in candidates}
    first_pass = embedding_ready(candidates, second_brain_ready_state=second_brain_ready,
                                 intended_chunk_ids=intended)
    accepted_reasons = {"LOW_CONFIDENCE", "NOT_HUMAN_REVIEWED"}
    exclusions = {}
    for item in first_pass["rejected_chunks"]:
        reasons = item["rejection_reasons"]
        if reasons and set(reasons) <= accepted_reasons:
            exclusions[item["chunk_id"]] = "CURATION_POLICY:" + ",".join(reasons)
        else:
            rejected.append({"chunk_id": item["chunk_id"],
                             "knowledge_id": item["chunk"].get("knowledge_id"),
                             "rejection_reasons": reasons})
    result = embedding_ready(candidates, second_brain_ready_state=second_brain_ready,
                             intended_chunk_ids=intended, accepted_exclusions=exclusions)
    rejected.extend({"chunk_id": item["chunk_id"],
                     "knowledge_id": item["chunk"].get("knowledge_id"),
                     "rejection_reasons": item["rejection_reasons"]}
                    for item in result["rejected_chunks"]
                    if item["chunk_id"] not in exclusions)
    return {"eligible_chunks": result["eligible_chunks"], "rejected_chunks": rejected,
            "accepted_exclusions": exclusions, "intended_chunk_ids": sorted(intended),
            "DOCUMENT_EMBEDDING_READY": result["DOCUMENT_EMBEDDING_READY"]}


class GeminiEmbeddingProvider:
    """Gemini Embedding 2 REST adapter; key is read only by the backend."""

    model = EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS
    provider = EMBEDDING_PROVIDER
    instruction_version = EMBEDDING_INSTRUCTION_VERSION

    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0,
                 opener: Callable[..., Any] | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self._timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise RuntimeError("gemini_api_key_missing")
        if not texts:
            return []
        vectors = []
        for text in texts:
            body = {"content": {"parts": [{"text": text}]}, "output_dimensionality": self.dimensions}
            request = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key}, method="POST")
            try:
                with self._opener(request, timeout=self._timeout) as response:
                    payload = json.loads(response.read())
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"gemini_http_{exc.code}") from None
            except (urllib.error.URLError, OSError, TimeoutError):
                raise RuntimeError("gemini_network_error") from None
            values = payload.get("embedding", {}).get("values", [])
            if len(values) != self.dimensions:
                raise RuntimeError("gemini_dimension_mismatch")
            if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
                raise RuntimeError("gemini_invalid_vector")
            vectors.append([float(value) for value in values])
        return vectors
