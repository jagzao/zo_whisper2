from transcript_pipeline.documentation.session_pack import (
    build_derived_diagrams,
    evaluate_session_pack_gates,
    validate_diagram_provenance,
    validate_pack_claim_provenance,
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

    diagrams[0]["edges"][0]["provenance"]["frame_ids"] = []
    assert any("frame provenance" in error for error in validate_diagram_provenance(diagrams, claim_ids, frame_ids, event_ids))


def test_session_pack_gate_requires_speech_visual_claim_and_diagram_passes():
    base = dict(
        transcript_state="VALID", speech_gate="PASS", visual_gate="PASS",
        claim_errors=[], diagram_errors=[],
        application_ids={"pg-regdoc", "north-america-central-product-research-testing-panelist-payments"},
        low_confidence_ratio=0, procedures=[],
    )
    assert all(value == "PASS" for value in evaluate_session_pack_gates(**base).values())
    blocked = evaluate_session_pack_gates(**{**base, "visual_gate": "FAIL"})
    assert blocked["VISUAL_TOPIC_COVERAGE"] == "FAIL"
    blocked = evaluate_session_pack_gates(**{**base, "transcript_state": "PARTIAL"})
    assert blocked["TRANSCRIPT_SPEECH_COVERAGE"] == "FAIL"


def test_low_confidence_procedure_cannot_pass_pack_gate():
    base = dict(
        transcript_state="VALID", speech_gate="PASS", visual_gate="PASS",
        claim_errors=[], diagram_errors=[], application_ids={"pg-regdoc",
        "north-america-central-product-research-testing-panelist-payments"},
        low_confidence_ratio=.2, procedures=[],
    )
    result = evaluate_session_pack_gates(**base)
    assert result["LOW_CONFIDENCE_FILLER"] == "FAIL"
    assert result["PROCEDURE_GROUNDING"] == "PASS"
