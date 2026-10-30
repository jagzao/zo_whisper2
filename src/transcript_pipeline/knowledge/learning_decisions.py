"""Deterministic learning outcomes for already extracted candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LearningDecision = Literal[
    "NEW", "CONFIRMS", "EXTENDS", "CONFLICTS", "SUPERSEDES", "NOT_USEFUL", "NEEDS_REVIEW"
]
MatchRelation = Literal["NONE", "EXACT", "SUPPORTING", "CONTRADICTING", "REPLACES"]


@dataclass(frozen=True)
class LearningCandidate:
    canonical_fact: str
    topic: str
    application_id: str
    evidence_refs: tuple[str, ...]
    useful: bool | None
    quality_passed: bool
    confidence_passed: bool
    owner_approved: bool


@dataclass(frozen=True)
class LearningOutcome:
    decision: LearningDecision
    embedding_eligible: bool


_RELATION_DECISIONS: dict[MatchRelation, LearningDecision] = {
    "NONE": "NEW",
    "EXACT": "CONFIRMS",
    "SUPPORTING": "EXTENDS",
    "CONTRADICTING": "CONFLICTS",
    "REPLACES": "SUPERSEDES",
}


def evaluate_learning_candidate(
    candidate: LearningCandidate,
    relation: MatchRelation | None,
) -> LearningOutcome:
    """Classifies a candidate after comparison; uncertainty fails closed."""
    if candidate.useful is False:
        return LearningOutcome("NOT_USEFUL", False)
    if (
        candidate.useful is not True
        or not candidate.canonical_fact.strip()
        or not candidate.topic.strip()
        or not candidate.application_id.strip()
        or not candidate.evidence_refs
        or not candidate.quality_passed
        or not candidate.confidence_passed
        or relation is None
    ):
        return LearningOutcome("NEEDS_REVIEW", False)

    decision = _RELATION_DECISIONS[relation]
    eligible = candidate.owner_approved and decision in {"NEW", "EXTENDS", "SUPERSEDES"}
    return LearningOutcome(decision, eligible)
