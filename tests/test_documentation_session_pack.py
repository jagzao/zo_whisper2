from transcript_pipeline.documentation.session_pack import (
    APPLICATION_TITLES,
    APPLICATIONS,
    build_derived_diagrams,
    deduplicate_source_artifacts,
    evaluate_session_pack_gates,
    sort_evidence_timeline,
    validate_application_claim_isolation,
    validate_diagram_provenance,
    validate_diagram_relations,
    validate_pack_claim_provenance,
    validate_source_artifact_dedup,
    validate_timeline_chronology,
)


def _claim():
    return {
        "claim_id": "C1", "application_id": "app", "claim": "Fact from source",
        "source_type": "TRANSCRIPT", "source_id": "S-TRANSCRIPT", "timestamp": 10.0,
        "frame_id": None, "confidence": .9, "verification_state": "SOURCE_CONFIRMED",
        "first_seen": {"timestamp": "00:00:10"}, "last_confirmed": None,
        "supporting_sources": [{"source_id": "S-TRANSCRIPT", "source_type": "TRANSCRIPT_SEGMENTS",
                                "timestamp": 10.0, "segments": [{"segment_id": "s1"}]}],
        "conflicts": [],
    }


def test_pack_claim_requires_resolvable_source_and_timestamped_segment():
    claim = _claim()
    assert validate_pack_claim_provenance([claim], {"S-TRANSCRIPT"}, set()) == []

    missing_segment = {**claim, "supporting_sources": [{**claim["supporting_sources"][0], "segments": []}]}
    errors = validate_pack_claim_provenance([missing_segment], {"S-TRANSCRIPT"}, set())
    assert any("transcript citation has no segment" in error for error in errors)

    unknown = {**claim, "source_id": "missing"}
    assert any("unknown source_id" in error for error in validate_pack_claim_provenance([unknown], {"S-TRANSCRIPT"}, set()))


def test_derived_diagrams_link_every_node_and_edge_to_claim_frame_and_event():
    diagrams = build_derived_diagrams()
    claim_ids = {claim_id for diagram in diagrams for edge in diagram["edges"] for claim_id in edge["claim_ids"]}
    frame_ids = {"frame_0005.png", "frame_0006.png", "frame_0021.png"}
    event_ids = {"E-008", "E-009", "E-020"}
    assert len(diagrams) == 3
    assert validate_diagram_provenance(diagrams, claim_ids, frame_ids, event_ids) == []
    assert validate_diagram_relations(diagrams) == []
    auth_edges = [edge for diagram in diagrams for edge in diagram["edges"] if edge["relation_type"] == "AUTHENTICATES_WITH"]
    assert auth_edges
    assert all(" ---|AUTHENTICATES_WITH:" in next(d["mermaid"] for d in diagrams if edge in d["edges"]) for edge in auth_edges)
    assert all(" -->|AUTHENTICATES_WITH:" not in next(d["mermaid"] for d in diagrams if edge in d["edges"]) for edge in auth_edges)

    diagrams[0]["edges"][0]["provenance"]["frame_ids"] = []
    assert any("frame provenance" in error for error in validate_diagram_provenance(diagrams, claim_ids, frame_ids, event_ids))


def test_session_pack_gate_requires_speech_visual_claim_and_diagram_passes():
    base = dict(
        transcript_state="VALID", speech_gate="PASS", visual_gate="PASS",
        claim_errors=[], diagram_errors=[],
        application_ids={"pg-regdoc", "north-america-central-product-research-testing-panelist-payments"},
        low_confidence_ratio=0, procedures=[],
        application_errors=[], source_map_errors=[], timeline_errors=[], relation_errors=[],
    )
    assert all(value == "PASS" for value in evaluate_session_pack_gates(**base).values())
    blocked = evaluate_session_pack_gates(**{**base, "visual_gate": "FAIL"})
    assert blocked["VISUAL_TOPIC_COVERAGE"] == "FAIL"
    blocked = evaluate_session_pack_gates(**{**base, "transcript_state": "PARTIAL"})
    assert blocked["TRANSCRIPT_SPEECH_COVERAGE"] == "FAIL"
    blocked = evaluate_session_pack_gates(**{**base, "application_errors": ["claim leaked"]})
    assert blocked["APPLICATION_CLAIM_ISOLATION"] == "FAIL"
    assert blocked["QUALITY_GATE"] == "FAIL"


def test_low_confidence_procedure_cannot_pass_pack_gate():
    base = dict(
        transcript_state="VALID", speech_gate="PASS", visual_gate="PASS",
        claim_errors=[], diagram_errors=[], application_ids={"pg-regdoc",
        "north-america-central-product-research-testing-panelist-payments"},
        low_confidence_ratio=.2, procedures=[],
        application_errors=[], source_map_errors=[], timeline_errors=[], relation_errors=[],
    )
    result = evaluate_session_pack_gates(**base)
    assert result["LOW_CONFIDENCE_FILLER"] == "FAIL"
    assert result["PROCEDURE_GROUNDING"] == "PASS"


def test_c008_cannot_leak_from_pg_regdoc_into_cprt_section():
    apps = [{"application_id": APPLICATIONS["north-america-central-product-research-testing-panelist-payments"],
             "sections": [{"title": "Risks / Limitations", "claim_ids": ["C-008"]}]}]
    c008 = {**_claim(), "claim_id": "C-008", "application_id": "pg-regdoc"}
    errors = validate_application_claim_isolation(apps, [c008])
    assert errors and "C-008 belongs to pg-regdoc" in errors[0]


def test_session_general_claim_must_name_relevant_application():
    app_id = APPLICATIONS["north-america-central-product-research-testing-panelist-payments"]
    apps = [{"application_id": app_id, "sections": [{"title": "Identity", "claim_ids": ["C1"]}]}]
    claim = {**_claim(), "claim_id": "C1", "application_id": "SESSION_GENERAL",
             "claim": "The recording covers both applications, including this overview."}
    assert validate_application_claim_isolation(apps, [claim]) == []


def test_source_artifact_dedup_preserves_alias_for_shared_frame():
    original = {"evidence_id": "V-004", "source_path": r"frames\\frame_0021.png", "sha256": "abc", "source_type": "VIDEO_FRAME"}
    duplicate = {"evidence_id": "V-005", "source_path": "frames/frame_0021.png", "sha256": "ABC", "source_type": "VIDEO_FRAME"}
    sources = deduplicate_source_artifacts([original, duplicate])
    assert len(sources) == 1
    assert sources[0]["evidence_id"] == "V-004"
    assert sources[0]["aliases"] == ["V-005"]
    assert validate_source_artifact_dedup(sources) == []
    assert validate_source_artifact_dedup([original, duplicate])


def test_evidence_timeline_is_sorted_by_start_end_then_id():
    events = [
        {"id": "E-2", "start": "00:20:51", "end": "00:20:51"},
        {"id": "E-3", "start": "00:18:23", "end": "00:20:34"},
        {"id": "E-1", "start": "00:18:23", "end": "00:20:34"},
    ]
    sorted_events = sort_evidence_timeline(events)
    assert [event["id"] for event in sorted_events] == ["E-1", "E-3", "E-2"]
    assert validate_timeline_chronology(sorted_events) == []


def test_pdf_application_title_has_intentional_readable_line_break():
    assert APPLICATION_TITLES[APPLICATIONS["north-america-central-product-research-testing-panelist-payments"]] == (
        "North America Central Product Research Testing<br/>Panelist Payments"
    )
