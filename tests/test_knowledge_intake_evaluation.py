from transcript_pipeline.knowledge.meeting_intake import (
    evaluate_intake,
    store_meeting_package,
)


def test_empty_meeting_evaluation_is_successful_and_idempotent(tmp_path):
    package = {
        "schemaVersion": 1,
        "sessionId": "synthetic-empty-1",
        "projectId": "p1",
        "meetingType": "WORK_MEETING",
        "startedAt": "2026-10-29T10:00:00Z",
        "endedAt": "2026-10-29T10:30:00Z",
        "utterances": [{"id": "u1", "text": "Only logistics."}],
    }
    assert store_meeting_package(tmp_path, package)["status"] == "RECEIVED_PENDING_EVALUATION"
    first = evaluate_intake(tmp_path, package["sessionId"], existing=[])
    second = evaluate_intake(tmp_path, package["sessionId"], existing=[])
    assert first == second
    assert first["state"] == "EVALUATED"
    assert first["candidateCount"] == 0
    assert first["embeddingEligibleCount"] == 0
