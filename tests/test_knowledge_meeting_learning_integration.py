from transcript_pipeline.knowledge.meeting_intake import evaluate_intake, store_meeting_package


def test_synthetic_meeting_intake_evaluation_keeps_evidence_separate_from_learning(tmp_path):
    package = {
        "schemaVersion": 1,
        "sessionId": "synthetic-integration-1",
        "projectId": "p1",
        "meetingType": "WORK_MEETING",
        "startedAt": "2026-10-29T10:00:00Z",
        "endedAt": "2026-10-29T10:30:00Z",
        "utterances": [{"id": "u1", "text": "Synthetic text only; never sent to Gemini."}],
        "canonicalCandidates": [
            {"applicationId": "app1", "topic": "deployment", "canonicalFact": "Uses blue-green releases.",
             "evidenceRefs": ["u1"], "useful": True, "qualityPassed": True, "confidencePassed": True},
            {"applicationId": "app1", "topic": "authentication", "canonicalFact": "Uses SSO.",
             "evidenceRefs": ["u1"], "useful": True, "qualityPassed": True, "confidencePassed": True},
            {"applicationId": "app2", "topic": "authentication", "canonicalFact": "Uses LDAP.",
             "evidenceRefs": ["u1"], "useful": True, "qualityPassed": True, "confidencePassed": True,
             "comparison": "CONTRADICTING"},
            {"applicationId": "app1", "topic": "small-talk", "canonicalFact": "Discussed the weather.",
             "evidenceRefs": ["u1"], "useful": False, "qualityPassed": True, "confidencePassed": True},
            {"applicationId": "app1", "topic": "runtime", "canonicalFact": "Uses a current runtime.",
             "evidenceRefs": ["u1"], "useful": True, "qualityPassed": True, "confidencePassed": True},
        ],
    }
    existing = [
        {"projectId": "p1", "applicationId": "app1", "topic": "authentication", "canonicalFact": "Uses SSO."},
        {"projectId": "p1", "applicationId": "app2", "topic": "authentication", "canonicalFact": "Uses SSO."},
        {"projectId": "p1", "applicationId": "app1", "topic": "runtime", "canonicalFact": "Uses Java 17."},
    ]
    assert store_meeting_package(tmp_path, package)["status"] == "RECEIVED_PENDING_EVALUATION"
    result = evaluate_intake(tmp_path, package["sessionId"], existing=existing)
    decisions = {item["decision"] for item in result["outcomes"]}
    assert decisions == {"NEW", "CONFIRMS", "CONFLICTS", "NOT_USEFUL", "NEEDS_REVIEW"}
    assert result["embeddingEligibleCount"] == 0
    assert all(item["ownerApproved"] is False and item["embeddingEligible"] is False for item in result["outcomes"])
    assert result["state"] == "NEEDS_REVIEW"
