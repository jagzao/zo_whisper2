from transcript_pipeline.knowledge.learning_decisions import (
    LearningCandidate,
    evaluate_learning_candidate,
)


def candidate(**changes):
    values = {
        "canonical_fact": "The service uses SSO.",
        "topic": "authentication",
        "application_id": "app-1",
        "evidence_refs": ("utterance-3",),
        "useful": True,
        "quality_passed": True,
        "confidence_passed": True,
        "owner_approved": True,
    }
    values.update(changes)
    return LearningCandidate(**values)


def test_classifies_all_learning_decisions_and_embedding_gate():
    cases = {
        "NONE": ("NEW", True),
        "EXACT": ("CONFIRMS", False),
        "SUPPORTING": ("EXTENDS", True),
        "CONTRADICTING": ("CONFLICTS", False),
        "REPLACES": ("SUPERSEDES", True),
    }
    for relation, expected in cases.items():
        outcome = evaluate_learning_candidate(candidate(), relation)
        assert (outcome.decision, outcome.embedding_eligible) == expected

    outcome = evaluate_learning_candidate(candidate(useful=False), "NONE")
    assert (outcome.decision, outcome.embedding_eligible) == ("NOT_USEFUL", False)

    outcome = evaluate_learning_candidate(candidate(useful=None), "NONE")
    assert (outcome.decision, outcome.embedding_eligible) == ("NEEDS_REVIEW", False)


def test_unapproved_or_unqualified_candidate_cannot_be_embedded():
    for changes in (
        {"owner_approved": False},
        {"quality_passed": False},
        {"confidence_passed": False},
        {"evidence_refs": ()},
    ):
        outcome = evaluate_learning_candidate(candidate(**changes), "NONE")
        assert outcome.embedding_eligible is False
        if changes.get("owner_approved") is not False:
            assert outcome.decision == "NEEDS_REVIEW"
