import hashlib

from transcript_pipeline.documentation.kav_contract import (
    build_runbooks,
    embedding_chunk_id,
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
        {"segment_id": "b", "start": 2, "text": "Click the access Identity Federation section."},
        {"segment_id": "c", "start": 3, "text": "Select the access connection modification."},
        {"segment_id": "d", "start": 4, "text": "The cafeteria closes at five."},
        {"segment_id": "e", "start": 80, "text": "Open the payroll report."},
    ], media_id="s1", application_id="app-a")
    assert len(procedures) == 1
    assert [step["order"] for step in procedures[0]["steps"]] == [1, 2, 3]
    assert all(step["evidence_refs"] for step in procedures[0]["steps"])
    assert procedures[0]["actionability"] == "GUIDED"


def test_extraction_finds_multiple_independent_procedures_without_evidence_leakage():
    segments = [
        {"segment_id": "a1", "start": 5, "text": "First, open the access request.", "application_id": "app-access"},
        {"segment_id": "a2", "start": 6, "text": "Click the access details."},
        {"segment_id": "a3", "start": 8, "text": "Finally submit the access request."},
        {"segment_id": "b1", "start": 1200, "text": "First, review retention settings.", "application_id": "app-records"},
        {"segment_id": "b2", "start": 1202, "text": "Open retention evidence."},
        {"segment_id": "b3", "start": 1204, "text": "Finally attach the retention evidence."},
        {"segment_id": "info", "start": 2400, "text": "The discussion also covered general planning."},
    ]
    procedures = extract_procedures(segments, media_id="multi")
    assert len(procedures) == 2
    assert procedures[0]["procedure_id"] != procedures[1]["procedure_id"]
    assert [procedure["application_id"] for procedure in procedures] == ["app-access", "app-records"]
    assert set(procedures[0]["evidence_refs"]).isdisjoint(procedures[1]["evidence_refs"])
    books = build_runbooks(procedures, source_session="multi")
    assert len(books) == 2
    assert [set(book["source_evidence"]) for book in books] == [
        set(procedure["evidence_refs"]) for procedure in procedures
    ]
    assert validate_runbooks(books, {segment["segment_id"] for segment in segments})[0] == "PASS"


def test_invalid_early_anchor_does_not_hide_later_valid_workflow():
    procedures = extract_procedures([
        {"segment_id": "bad1", "start": 1, "text": "First, open the access form."},
        {"segment_id": "bad2", "start": 500, "text": "First, review retention settings."},
        {"segment_id": "good2", "start": 502, "text": "Open retention evidence."},
    ], media_id="recovery")
    assert len(procedures) == 1
    assert procedures[0]["evidence_refs"] == ["good2"] or set(procedures[0]["evidence_refs"]) == {"bad2", "good2"}


def test_long_procedure_and_topic_transition_closure():
    procedures = extract_procedures([
        {"segment_id": "l1", "start": 1, "text": "First, open access settings."},
        {"segment_id": "l2", "start": 110, "text": "Select access role configuration."},
        {"segment_id": "l3", "start": 220, "text": "Finally save the access configuration."},
        {"segment_id": "t1", "start": 400, "text": "First, review retention policy."},
        {"segment_id": "t2", "start": 402, "text": "Open retention evidence."},
        {"segment_id": "t3", "start": 450, "text": "Open payroll report."},
        {"segment_id": "t4", "start": 500, "text": "First, review vendor qualification."},
        {"segment_id": "t5", "start": 502, "text": "Open vendor records."},
    ], media_id="long")
    assert len(procedures) == 3
    assert len(procedures[0]["steps"]) == 3
    assert procedures[0]["steps"][-1]["source_timestamp"] - procedures[0]["steps"][0]["source_timestamp"] > 45
    assert "t3" not in procedures[1]["evidence_refs"]
    assert "t4" not in procedures[1]["evidence_refs"]


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
    supplied = {"Confirm the request": "approved input"}
    assert evaluate_runbook_preflight(runbooks[0], supplied_values=supplied, current_live_matches=None)["reason"] == "CURRENT_LIVE_VALIDATION_REQUIRED"
    assert evaluate_runbook_preflight(runbooks[0], supplied_values=supplied, current_live_matches=True)["reason"] == "APPROVAL_REQUIRED"
    assert evaluate_runbook_preflight(runbooks[0], supplied_values=supplied, current_live_matches=False)["reason"] == "HISTORICAL_INSTRUCTION_CONFLICT_REVIEW"


def test_unknown_required_value_stops_without_inventing_a_value():
    runbook = {"actionability": "EXECUTABLE_WITH_CONFIRMATION", "approval_required_before": [],
               "steps": [{"required_values": [{"key": "approved_role", "status": "REQUIRED_UNRESOLVED"}]}]}
    result = evaluate_runbook_preflight(runbook, supplied_values={}, current_live_matches=True)
    assert result == {"status": "STOP", "reason": "MISSING_REQUIRED_VALUES", "missing_values": ["approved_role"]}


def test_unknown_parameters_preserved_and_actual_secret_redacted():
    procedure = extract_procedures([
        {"segment_id": "a", "start": 1, "text": "First, open the access settings for ACS URL, entity ID, role, group and password."},
        {"segment_id": "b", "start": 2, "text": "Click the access role and group configuration."},
        {"segment_id": "c", "start": 3, "text": "Then enter the access password hunter2."},
    ], media_id="s1")[0]
    values = {value["key"] for step in procedure["steps"] for value in step["required_values"]}
    assert {"acs_url", "entity_id", "role", "group", "credential"} <= values
    assert "hunter2" not in str(procedure)


def test_claim_provenance_capture_separation_and_generic_escalation():
    claim = {"claim_id": "c1", "supporting_sources": [{"segment_id": "e1"}]}
    proc = {"procedure_id": "p1", "title": "Update", "actionability": "GUIDED",
            "steps": [{"order": 1, "instruction": "Submit request", "semantic_action": "SUBMIT", "evidence_refs": ["e1"]}]}
    book = build_runbooks([proc], source_session="s1", claims=[claim])[0]
    assert book["source_claims"] == ["c1"]
    assert book["source_evidence"] == ["e1"]
    assert "e1" not in book["evidence_to_capture"]
    assert book["escalation"]["target"] == "AUTHORIZED_REVIEWER"
    assert "Juan" not in str(book)
    assert book["actionability"] == "GUIDED"
    assert book["execution_ready"] is False


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
               "provenance_pointers": ["e1"], "curated": True,
               "content_hash": "sha256:" + hashlib.sha256(b"Reviewed access workflow.").hexdigest()}
    curated["chunk_id"] = embedding_chunk_id(curated)
    report = embedding_ready([curated, {**curated, "knowledge_id": "raw", "raw_transcript": True},
                              {**curated, "knowledge_id": "state", "execution_state": True}],
                             second_brain_ready_state="PASS")
    assert len(report["eligible_chunks"]) == 1
    assert report["eligible_chunks"][0]["content_hash"].startswith("sha256:")
    assert not report["DOCUMENT_EMBEDDING_READY"]
    assert embedding_ready([{**curated, "content": "  "}], second_brain_ready_state="PASS")["rejected_chunks"]
    assert not embedding_ready([curated], second_brain_ready_state="FAIL")["DOCUMENT_EMBEDDING_READY"]
    assert embedding_ready([curated], second_brain_ready_state="PASS")["DOCUMENT_EMBEDDING_READY"]
    assert not embedding_ready([{**curated, "conflicting": True}], second_brain_ready_state="PASS")["DOCUMENT_EMBEDDING_READY"]
    assert not embedding_ready([{**curated, "confidence": 0.4}], second_brain_ready_state="PASS")["DOCUMENT_EMBEDDING_READY"]


def test_embedding_accounting_uses_chunk_ids_for_same_knowledge_document():
    chunks = []
    for topic, content, confidence in (
        ("access-a", "Reviewed access workflow A.", 0.95),
        ("access-b", "Reviewed access workflow B.", 0.9),
        ("access-c", "Reviewed access workflow C.", 0.2),
    ):
        chunk = {"knowledge_id": "one-document", "version": 1, "project_id": "p1",
                 "canonical_topic": topic, "content": content, "source_knowledge_ids": ["k0"],
                 "verification_status": "HUMAN_REVIEWED", "confidence": confidence,
                 "provenance_pointers": [topic], "curated": True,
                 "content_hash": "sha256:" + hashlib.sha256(content.encode()).hexdigest()}
        chunk["chunk_id"] = embedding_chunk_id(chunk)
        chunks.append(chunk)
    intended = {chunk["chunk_id"] for chunk in chunks}
    rejected_id = chunks[2]["chunk_id"]
    report = embedding_ready(chunks, second_brain_ready_state="PASS", intended_chunk_ids=intended)
    assert len({chunk["knowledge_id"] for chunk in chunks}) == 1
    assert len({chunk["chunk_id"] for chunk in chunks}) == 3
    assert not report["DOCUMENT_EMBEDDING_READY"]
    assert report["rejected_chunks"][0]["chunk_id"] == rejected_id
    assert not embedding_ready(chunks, second_brain_ready_state="PASS", intended_chunk_ids=intended,
                               accepted_exclusions={"wrong-id": "excluded"})["DOCUMENT_EMBEDDING_READY"]
    assert embedding_ready(chunks, second_brain_ready_state="PASS", intended_chunk_ids=intended,
                           accepted_exclusions={rejected_id: "low confidence"})["DOCUMENT_EMBEDDING_READY"]
