from transcript_pipeline.documentation.mission_pack import (
    QUALITY_GATES,
    assess_content_quality,
    assess_transcript_quality,
    classify_trailing_gap,
    evaluate_quality_gates,
    measure_source_coverage,
    merge_application_facts,
    validate_claim_records,
)


def test_transcript_state_calculates_gaps_and_requires_near_complete_coverage():
    partial = assess_transcript_quality(1000, [{"start": 10, "end": 600}])
    assert partial["transcript_state"] == "PARTIAL"
    assert partial["transcript_coverage_percent"] == 60.0
    assert partial["final_gap"] == 400.0
    assert partial["speech_gaps"][-1]["kind"] == "final"

    valid = assess_transcript_quality(1000, [{"start": 0, "end": 970}])
    assert valid["transcript_state"] == "VALID"
    late = assess_transcript_quality(1000, [{"start": 400, "end": 990}])
    assert late["transcript_state"] == "PARTIAL"
    assert late["speech_gaps"][0]["kind"] == "leading"
    assert assess_transcript_quality(1000, [])["transcript_state"] == "MISSING"
    assert assess_transcript_quality(1000, [{"start": "bad", "end": 10}])["transcript_state"] == "FAILED"


def test_transcript_gate_distinguishes_speech_gaps_from_gallery_or_silence_tail():
    samples = [
        {"timestamp": 400, "visual_type": "MEETING_GALLERY"},
        {"timestamp": 600, "visual_type": "MEETING_GALLERY"},
        {"timestamp": 800, "visual_type": "BLACK_OR_EMPTY"},
        {"timestamp": 990, "visual_type": "BLACK_OR_EMPTY"},
    ]
    nonspeech = classify_trailing_gap(400, 1000, [], samples, vad_completed=True)
    assert nonspeech["classification"] == "NON_SPEECH_TRAILING_MEDIA"
    quality = assess_transcript_quality(
        1000,
        [{"start": 0, "end": 400}],
        trailing_gap_classification=nonspeech["classification"],
        vad_speech_segments=[{"start": 0, "end": 100}, {"start": 300, "end": 400}],
    )
    assert quality["transcript_state"] == "VALID"
    assert quality["transcript_coverage_percent"] == 40.0
    assert quality["vad_speech_coverage_percent"] == 100.0

    speech = classify_trailing_gap(400, 1000, [{"start": 700, "end": 710}], samples, vad_completed=True)
    assert speech["classification"] == "UNTRANSCRIBED_SPEECH_GAP"
    unknown = classify_trailing_gap(400, 1000, [], samples[:1], vad_completed=False)
    assert unknown["classification"] == "NEEDS_REVIEW"


def test_supplemental_asr_can_validate_speech_coverage_without_full_media_coverage():
    result = assess_transcript_quality(
        100,
        [{"start": 5, "end": 50}],
        supplemental_segments=[{"start": 50, "end": 95}],
        trailing_gap_classification="NON_SPEECH_TRAILING_MEDIA",
        vad_speech_segments=[{"start": 5, "end": 95}],
    )

    assert result["media_coverage_percent"] == 95.0
    assert result["speech_coverage_percent"] == 100.0
    assert result["transcribed_speech_seconds"] == 90.0
    assert result["uncovered_speech_seconds"] == 0.0
    assert result["transcript_state"] == "VALID"


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
        "claim_id": "C1", "application_id": "app-1",
        "claim": "Definition is uncertain",
        "source_id": "S41", "timestamp": "00:01:49", "frame_id": None,
        "source_type": "TRANSCRIPT", "first_seen": "S41", "last_confirmed": None,
        "supporting_sources": [{"source_id": "S41", "timestamp": "00:01:49"}], "conflicts": [],
        "confidence": "LOW",
        "verification_state": "SOURCE_UNCERTAIN",
    }
    assert validate_claim_records([base]) == []
    external = {**base, "verification_state": "EXTERNAL_VERIFIED", "supporting_sources": []}
    assert "EXTERNAL_VERIFIED without external_sources" in validate_claim_records([external])[0]

    unsupported = {**base, "source_id": None, "supporting_sources": []}
    assert "missing provenance" in validate_claim_records([unsupported])[0]


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


def test_cross_session_conflict_is_preserved_and_filler_ratio_blocks_ready():
    old = [{"application_id": "app-1", "fact_key": "hosting", "fact": "Hosted on Azure",
            "supporting_sessions": ["S18"], "supporting_frames": ["f1"], "status": "CONFIRMED"}]
    new = [{"application_id": "app-1", "fact_key": "hosting", "fact": "Hosted on AWS",
            "supporting_sessions": ["S41"], "supporting_frames": ["f2"]}]
    merged = merge_application_facts(old, new)
    assert len(merged) == 2
    assert all(item["status"] == "CONFLICTING" for item in merged)
    assert all(item["conflicts"] for item in merged)

    quality = assess_content_quality([
        {"instruction": "Step at 00:10:00", "confidence": "low", "evidence_source": "none"},
        {"instruction": "Step at 00:11:00", "confidence": "low", "evidence_source": "none"},
    ])
    assert quality["status"] == "FAIL"
    assert quality["timestamp_filler_count"] == 2
    assert quality["low_confidence_content_ratio"] == 1.0


def test_generic_cross_session_consolidation_keeps_exact_application_identity():
    from transcript_pipeline.documentation.mission_pack import consolidate_application_claims

    claims = [
        {"application_id": "app-alpha", "claim_id": "a1", "claim": "Hosted in Azure",
         "source_id": "video-a", "session_id": "session-a", "timestamp": 10,
         "frame_id": "frame-a", "confidence": .9, "verification_state": "SOURCE_CONFIRMED"},
        {"application_id": "app-beta", "claim_id": "b1", "claim": "Hosted in Azure",
         "source_id": "video-b", "session_id": "session-b", "timestamp": 20,
         "frame_id": "frame-b", "confidence": .9, "verification_state": "SOURCE_CONFIRMED"},
    ]

    facts = consolidate_application_claims(claims)

    assert len(facts) == 2
    assert {fact["application_id"] for fact in facts} == {"app-alpha", "app-beta"}
    assert all(fact["supporting_claims"] and fact["supporting_frames"] for fact in facts)


def test_golden_overfit_audit_detects_session_specific_production_literals(tmp_path):
    from transcript_pipeline.documentation.mission_pack import golden_overfit_violations

    (tmp_path / "generic.py").write_text('APP = "PGRegDoc"\n', encoding="utf-8")

    assert golden_overfit_violations(tmp_path) == ["generic.py:PGRegDoc"]
