from transcript_pipeline.documentation.kav_contract import (
    build_runbooks,
    embedding_ready,
    evaluate_runbook_preflight,
    extract_procedures,
    procedure_grounding,
    second_brain_ready,
    validate_runbooks,
)


def test_procedure_extraction_needs_ordered_actions_and_ignores_information_only():
    assert extract_procedures([
        {"segment_id": "a", "start": 1, "text": "The application supports access reviews."},
        {"segment_id": "b", "start": 2, "text": "The service has an approval flow."},
    ], media_id="s1") == []
    procedures = extract_procedures([
        {"segment_id": "a", "start": 1, "text": "First, open the access form."},
        {"segment_id": "b", "start": 2, "text": "Next, review the requested role."},
    ], media_id="s1", application_id="app-a")
    assert len(procedures) == 1
    assert [step["order"] for step in procedures[0]["steps"]] == [1, 2]
    assert all(step["evidence_refs"] for step in procedures[0]["steps"])
    assert procedures[0]["actionability"] == "GUIDED"


def test_procedure_grounding_pass_fail_and_not_applicable():
    procedure = {"procedure_id": "p1", "evidence_refs": ["e1"],
                 "steps": [{"order": 1, "instruction": "Open form", "semantic_action": "NAVIGATE",
                            "evidence_refs": ["e1"]}]}
    assert procedure_grounding([], set())[0] == "NOT_APPLICABLE"
    assert procedure_grounding([procedure], {"e1"})[0] == "PASS"
    assert procedure_grounding([procedure], {"other"})[0] == "FAIL"
    partial = {**procedure, "steps": [*procedure["steps"],
              {"order": 2, "instruction": "Submit", "semantic_action": "SUBMIT", "evidence_refs": []}]}
    assert procedure_grounding([partial], {"e1"})[0] == "FAIL"


def test_kav_runbook_requires_inputs_preserves_approval_stops_and_escalates():
    procedure = {"procedure_id": "p1", "title": "Workflow", "application_id": "app-a",
                 "actionability": "GUIDED", "required_inputs": ["Confirm the request"],
                 "steps": [{"order": 1, "instruction": "Submit after review", "semantic_action": "SUBMIT",
                            "evidence_refs": ["e1"], "source_timestamp": 8, "frame_id": "f1"}]}
    runbooks = build_runbooks([procedure], source_session="s1")
    assert runbooks[0]["required_inputs"] == ["Confirm the request"]
    assert runbooks[0]["approval_required_before"] == ["SUBMIT"]
    assert runbooks[0]["steps"][0]["current_live_validation_required"]
    assert runbooks[0]["steps"][0]["historical_instruction"]
    assert runbooks[0]["stop_conditions"] and runbooks[0]["prohibitions"]
    assert runbooks[0]["escalation"]["target"]
    assert validate_runbooks(runbooks, {"e1"})[0] == "PASS"
    assert validate_runbooks([], set())[0] == "NOT_APPLICABLE"
    assert evaluate_runbook_preflight(runbooks[0], supplied_values={}, current_live_matches=None)["reason"] == "CURRENT_LIVE_VALIDATION_REQUIRED"
    assert evaluate_runbook_preflight(runbooks[0], supplied_values={}, current_live_matches=True)["reason"] == "APPROVAL_REQUIRED"
    assert evaluate_runbook_preflight(runbooks[0], supplied_values={}, current_live_matches=False)["reason"] == "HISTORICAL_INSTRUCTION_CONFLICT_REVIEW"


def test_unknown_required_value_stops_without_inventing_a_value():
    runbook = {"actionability": "EXECUTABLE_WITH_CONFIRMATION", "approval_required_before": [],
               "steps": [{"required_values": ["approved_role"]}]}
    result = evaluate_runbook_preflight(runbook, supplied_values={}, current_live_matches=True)
    assert result == {"status": "STOP", "reason": "MISSING_REQUIRED_VALUES", "missing_values": ["approved_role"]}


def test_unknown_sensitive_values_are_never_copied_into_procedures():
    assert extract_procedures([
        {"segment_id": "a", "start": 1, "text": "First, enter password hunter2."},
        {"segment_id": "b", "start": 2, "text": "Next, submit the request."},
    ], media_id="s1") == []


def test_second_brain_gate_includes_procedure_and_runbook_contract():
    common = dict(quality_gate="PASS", claim_provenance="PASS", application_resolution="PASS",
                 has_application=True, conflicts_promoted=False, package_policy="PASS",
                 raw_transcript_published=False, raw_media_published=False)
    assert second_brain_ready(**common, procedure_gate="NOT_APPLICABLE",
                              runbook_gate="NOT_APPLICABLE") == "PASS"
    assert second_brain_ready(**common, procedure_gate="PASS", runbook_gate="FAIL") == "FAIL"
    assert second_brain_ready(**common, procedure_gate="FAIL", runbook_gate="FAIL") == "FAIL"


def test_embedding_handoff_accepts_curated_chunks_only_and_hashes_content():
    curated = {"knowledge_id": "k1", "version": 1, "project_id": "p1", "canonical_topic": "access",
               "content": "Reviewed access workflow.", "source_knowledge_ids": ["k0"],
               "verification_status": "HUMAN_REVIEWED", "confidence": 0.95,
               "provenance_pointers": ["e1"], "curated": True}
    ready, chunks = embedding_ready([curated, {**curated, "knowledge_id": "raw", "raw_transcript": True},
                                     {**curated, "knowledge_id": "state", "execution_state": True}])
    assert ready and len(chunks) == 1 and chunks[0]["content_hash"].startswith("sha256:")
    assert embedding_ready([{**curated, "conflicting": True}]) == (False, [])
    assert embedding_ready([{**curated, "confidence": 0.4}]) == (False, [])
