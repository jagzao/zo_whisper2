from transcript_pipeline.documentation.mission_pack import (
    QUALITY_GATES,
    evaluate_quality_gates,
    measure_source_coverage,
    merge_application_facts,
    validate_claim_records,
)


def test_source_coverage_flags_large_trailing_gap():
    coverage = measure_source_coverage(
        2105.366,
        [{"start": 47.04, "end": 1435.89}],
        [56.9, 113.8, 2048.4],
    )

    assert coverage["status"] == "SOURCE_INCOMPLETE"
    assert coverage["transcript_last_timestamp_coverage_percent"] == 68.2
    assert coverage["trailing_gap_seconds"] == 669.476
    assert coverage["visual_frame_count"] == 3
    assert coverage["visual_sampling_is_continuous"] is False


def test_all_quality_gates_must_be_explicit_and_source_complete_to_pass():
    evaluations = {gate: {"status": "PASS", "evidence": "checked"} for gate in QUALITY_GATES}
    complete = {"status": "READY", "trailing_gap_seconds": 0, "transcript_last_timestamp_seconds": 100}
    assert evaluate_quality_gates(evaluations, complete)["fully_grounded"] is True

    incomplete = {**complete, "status": "SOURCE_INCOMPLETE", "trailing_gap_seconds": 700}
    result = evaluate_quality_gates(evaluations, incomplete)
    assert result["status"] == "FAIL"
    assert result["fully_grounded"] is False
    assert result["gates"]["SOURCE_COVERAGE"]["status"] == "FAIL"

    del evaluations["ACCESS_AUTH"]
    assert evaluate_quality_gates(evaluations, complete)["gates"]["ACCESS_AUTH"]["status"] == "NOT_EVALUATED"


def test_claim_schema_keeps_uncertain_claims_distinct_from_external_facts():
    base = {
        "claim": "Definition is uncertain",
        "application": "pgregdoc.com",
        "source_timestamp": "00:01:49",
        "source_type": "TRANSCRIPT",
        "confidence": "LOW",
        "verification_state": "SOURCE_UNCERTAIN",
    }
    assert validate_claim_records([base]) == []
    external = {**base, "verification_state": "EXTERNAL_VERIFIED"}
    assert "EXTERNAL_VERIFIED without external_sources" in validate_claim_records([external])[0]


def test_cross_session_fact_merge_preserves_provenance_and_does_not_duplicate():
    old = [{"fact_key": "hosting", "fact": "Hosted on P&G Azure", "first_seen": "S18",
            "last_confirmed": "S18", "supporting_sessions": ["S18"], "evidence_refs": ["S18:E1"],
            "confidence": "HIGH", "verification_state": "SOURCE_CONFIRMED", "conflicts": []}]
    new = [{"fact_key": "S41:C002", "fact": "Hosted on P&G Azure", "first_seen": "S41",
            "last_confirmed": "S41", "supporting_sessions": ["S41"], "evidence_refs": ["S41:E2"],
            "confidence": "HIGH", "verification_state": "SOURCE_CONFIRMED", "conflicts": []}]

    result = merge_application_facts(old, new)

    assert len(result) == 1
    assert result[0]["first_seen"] == "S18"
    assert result[0]["last_confirmed"] == "S41"
    assert result[0]["supporting_sessions"] == ["S18", "S41"]
    assert result[0]["evidence_refs"] == ["S18:E1", "S41:E2"]
