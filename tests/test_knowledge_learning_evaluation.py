from transcript_pipeline.knowledge.learning_evaluation import evaluate_meeting_candidates


def _package(*candidates):
    return {"sessionId": "synthetic-1", "projectId": "p1", "endedAt": "2026-10-29T11:00:00Z",
            "canonicalCandidates": list(candidates)}


def _candidate(**changes):
    value = {
        "applicationId": "app1", "topic": "authentication", "canonicalFact": "Uses SSO.",
        "evidenceRefs": ["u1"], "useful": True, "qualityPassed": True, "confidencePassed": True,
    }
    value.update(changes)
    return value


def test_new_candidate_is_evaluated_but_never_auto_approved_or_embedded():
    result = evaluate_meeting_candidates(_package(_candidate()), [])
    fact = result["outcomes"][0]
    assert result["state"] == "EVALUATED"
    assert fact["decision"] == "NEW"
    assert fact["ownerApproved"] is False
    assert fact["embeddingEligible"] is False


def test_exact_match_conflict_hint_and_not_useful_are_classified_safely():
    existing = [{"projectId": "p1", "applicationId": "app1", "topic": "authentication", "canonicalFact": "Uses SSO."}]
    confirmed = evaluate_meeting_candidates(_package(_candidate()), existing)["outcomes"][0]
    assert (confirmed["decision"], confirmed["embeddingEligible"]) == ("CONFIRMS", False)

    conflict = evaluate_meeting_candidates(_package(_candidate(
        canonicalFact="Uses password authentication.", comparison="CONTRADICTING"
    )), existing)["outcomes"][0]
    assert (conflict["decision"], conflict["embeddingEligible"]) == ("CONFLICTS", False)

    useless = evaluate_meeting_candidates(_package(_candidate(useful=False)), [])["outcomes"][0]
    assert (useless["decision"], useless["embeddingEligible"]) == ("NOT_USEFUL", False)


def test_same_topic_without_reconciliation_is_held_for_review():
    existing = [{"projectId": "p1", "applicationId": "app1", "topic": "authentication", "canonicalFact": "Uses SSO."}]
    result = evaluate_meeting_candidates(_package(_candidate(canonicalFact="Uses password authentication.")), existing)
    assert result["state"] == "NEEDS_REVIEW"
    assert result["outcomes"][0]["decision"] == "NEEDS_REVIEW"
    assert result["embeddingEligibleCount"] == 0
