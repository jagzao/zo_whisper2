"""Evaluate curated candidates from an intake without embedding meeting text."""
from __future__ import annotations

import hashlib
from typing import Any

from transcript_pipeline.knowledge.learning_decisions import (
    LearningCandidate,
    evaluate_learning_candidate,
)


def evaluate_meeting_candidates(
    package: dict[str, Any],
    existing: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    candidates = package.get("canonicalCandidates", [])
    extraction_source = "canonical_candidate"
    if not isinstance(candidates, list) or not candidates:
        candidates = _unreviewed_decision_candidates(package, existing)
        extraction_source = "zavi_decision_unreviewed"
    outcomes: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        fact = item.get("canonicalFact") if isinstance(item.get("canonicalFact"), str) else ""
        topic = item.get("topic") if isinstance(item.get("topic"), str) else ""
        application_id = item.get("applicationId") if isinstance(item.get("applicationId"), str) else ""
        evidence = item.get("evidenceRefs")
        evidence_refs = tuple(ref for ref in evidence if isinstance(ref, str) and ref) if isinstance(evidence, list) else ()
        match = next((row for row in existing if
            row.get("projectId") == package.get("projectId")
            and row.get("applicationId") == application_id
            and isinstance(row.get("topic"), str)
            and row["topic"].casefold() == topic.casefold()), None)
        relation = None
        if existing is None:
            relation = None
        elif match is None:
            relation = "NONE"
        elif _normalized(match.get("canonicalFact", "")) == _normalized(fact):
            relation = "EXACT"
        elif item.get("comparison") in ("SUPPORTING", "CONTRADICTING", "REPLACES"):
            relation = item["comparison"]

        candidate = LearningCandidate(
            canonical_fact=fact,
            topic=topic,
            application_id=application_id,
            evidence_refs=evidence_refs,
            useful=item.get("useful") if isinstance(item.get("useful"), bool) else None,
            quality_passed=item.get("qualityPassed") is True,
            confidence_passed=item.get("confidencePassed") is True,
            owner_approved=False,
        )
        outcome = evaluate_learning_candidate(candidate, relation)
        fact_id = str(item.get("knowledgeId") or "knowledge-" + hashlib.sha256(
            f"{package.get('projectId')}|{application_id}|{topic}|{_normalized(fact)}".encode()
        ).hexdigest()[:24])
        outcomes.append({
            "knowledgeId": fact_id,
            "projectId": package.get("projectId"),
            "applicationId": application_id or None,
            "topic": topic or None,
            "canonicalFact": fact,
            "decision": outcome.decision,
            "embeddingEligible": outcome.embedding_eligible,
            "ownerApproved": False,
            "sourceSessionIds": [package.get("sessionId")],
            "sourceEvidenceRefs": list(evidence_refs),
            "observedAt": package.get("endedAt"),
            "currentLiveValidationRequired": item.get("currentLiveValidationRequired") is True,
            "extractionSource": item.get("_extractionSource", extraction_source),
            "comparisonRelation": relation,
        })

    needs_review = any(item["decision"] == "NEEDS_REVIEW" for item in outcomes)
    state = "NEEDS_REVIEW" if needs_review else "EVALUATED"
    return {
        "state": state,
        "sessionId": package.get("sessionId"),
        "candidateCount": len(outcomes),
        "embeddingEligibleCount": sum(item["embeddingEligible"] for item in outcomes),
        "outcomes": outcomes,
    }


def _unreviewed_decision_candidates(
    package: dict[str, Any], existing: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    decisions = package.get("decisions")
    if not isinstance(decisions, list):
        return []
    candidates = []
    for decision in decisions:
        if not isinstance(decision, dict) or not isinstance(decision.get("text"), str):
            continue
        evidence = decision.get("evidenceRefs")
        evidence_refs = [ref for ref in evidence if isinstance(ref, str) and ref.strip()] if isinstance(evidence, list) else []
        if not evidence_refs:
            continue
        application_id = decision.get("applicationId", "")
        if not application_id:
            application_id = _resolve_application_hint(package, existing)
        topic = decision.get("topic", "")
        package_topics = package.get("topics")
        if not topic and isinstance(package_topics, list) and len(package_topics) == 1:
            topic = package_topics[0]
        candidates.append({
            "canonicalFact": decision["text"],
            "topic": topic,
            "applicationId": application_id,
            "evidenceRefs": evidence_refs,
            "_extractionSource": "zavi_decision_unreviewed",
        })
    return candidates


def _resolve_application_hint(package: dict[str, Any], existing: list[dict[str, Any]] | None) -> str:
    context = package.get("contextHints")
    hints = context.get("applicationHints") if isinstance(context, dict) else None
    if not isinstance(hints, list) or existing is None:
        return ""
    normalized_hints = {_normalized(hint) for hint in hints if isinstance(hint, str) and _normalized(hint)}
    matches = set()
    for row in existing:
        if row.get("projectId") != package.get("projectId") or not isinstance(row.get("applicationId"), str):
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        names = [metadata.get("applicationName"), *(
            metadata.get("applicationAliases") if isinstance(metadata.get("applicationAliases"), list) else []
        )]
        if any(isinstance(name, str) and _normalized(name) in normalized_hints for name in names):
            matches.add(row["applicationId"])
    return next(iter(matches)) if len(matches) == 1 else ""


def _normalized(value: object) -> str:
    return " ".join(str(value or "").casefold().split())
