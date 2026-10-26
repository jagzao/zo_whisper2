import re
from pathlib import Path

import pytest

from transcript_pipeline.documentation.session_pack import (
    MediaEvidenceBundle,
    consolidate_claims_across_sessions,
    deduplicate_source_artifacts,
    discover_application_candidates,
    extract_claims,
    extract_diagram_graphs,
    generate_application_mission_pack,
    generate_cross_session_knowledge,
    generate_session_pack,
    merge_cross_session_facts,
    normalize_evidence_bundle,
    resolve_application_identity,
    sort_evidence_timeline,
    validate_application_claim_isolation,
    validate_diagram_provenance,
    validate_diagram_relations,
    validate_pack_claim_provenance,
    validate_source_artifact_dedup,
    validate_timeline_chronology,
)


def _bundle(*, transcript_state="VALID", speech_gate="PASS", semantic_gate="PASS"):
    return MediaEvidenceBundle(
        media_id="media-alpha",
        video_metadata={"basename": "alpha.mp4", "duration": 120, "media_valid": True},
        transcript_segments=[
            {"start": 10, "end": 15, "text": "The service is called Service Alpha."},
            {"start": 16, "end": 20, "text": "Service Alpha provides order status reports."},
        ],
        speech_coverage={"transcript_state": transcript_state, "speech_quality_gate": speech_gate,
                         "semantic_topic_coverage_gate": semantic_gate},
        frames=[{"frame_id": "f-a", "timestamp": 14, "visual_type": "APPLICATION_UI",
                 "ocr_status": "SUCCESS", "ocr_text": "Service Alpha order status", "ocr_confidence": .9,
                 "source_image": "f-a.png", "semantic_topic": "ORDER_STATUS"}],
        visual_topics=[{"topic": "ORDER_STATUS", "source_frame": "f-a"}],
    )


def test_media_evidence_bundle_normalizes_ids_and_chronological_events():
    evidence = normalize_evidence_bundle(_bundle())
    assert evidence.transcript_segments[0]["segment_id"].startswith("seg-")
    assert evidence.evidence_events == sort_evidence_timeline(evidence.evidence_events)
    assert validate_timeline_chronology(evidence.evidence_events) == []


def test_generic_application_discovery_uses_explicit_source_phrase():
    evidence = normalize_evidence_bundle(_bundle())
    apps = discover_application_candidates(evidence)
    assert [item["name"] for item in apps] == ["Service Alpha"]
    assert apps[0]["provenance"][0]["segment_id"] == evidence.transcript_segments[0]["segment_id"]


def test_application_resolution_uses_exact_aliases_and_keeps_ambiguous_matches_open():
    known = [{"application_id": "app-a", "name": "Service Alpha", "aliases": ["Alpha"]}]
    assert resolve_application_identity({"name": "Alpha", "aliases": []}, known)["status"] == "MATCH_CONFIRMED"
    assert resolve_application_identity({"name": "Service Alph", "aliases": []}, known)["status"] == "NEW_APPLICATION"
    duplicate = [*known, {"application_id": "app-b", "name": "Alpha", "aliases": []}]
    assert resolve_application_identity({"name": "Alpha", "aliases": []}, duplicate)["status"] == "AMBIGUOUS"


def test_generic_claim_extraction_has_transcript_provenance_and_preserves_uncertainty():
    evidence = normalize_evidence_bundle(_bundle())
    apps = discover_application_candidates(evidence)
    claims = extract_claims(evidence, apps)
    assert claims
    assert claims[-1]["application_id"] == "service-alpha"
    assert claims[-1]["supporting_sources"][0]["segments"][0]["segment_id"] == evidence.transcript_segments[1]["segment_id"]
    evidence.transcript_segments.append({"start": 22, "end": 25, "text": "Maybe the service could be unavailable."})
    normalized = normalize_evidence_bundle(evidence)
    uncertain = extract_claims(normalized, apps)[-1]
    assert uncertain["verification_state"] == "SOURCE_UNCERTAIN"


def test_uncertain_claim_is_retained_for_review_but_not_rendered_as_canonical(tmp_path):
    evidence = _bundle()
    evidence.transcript_segments.append({"start": 22, "end": 25,
                                         "text": "Maybe the service could be unavailable."})
    result = generate_session_pack(evidence, tmp_path)
    assert any(item["verification_state"] == "SOURCE_UNCERTAIN" for item in result["pack"]["ambiguities"])
    assert all(item["verification_state"] != "SOURCE_UNCERTAIN"
               for app in result["pack"]["applications"] for section in app["sections"] for item in section["claims"])


def test_low_confidence_ocr_cannot_ground_visual_claim_or_diagram(tmp_path):
    evidence = _bundle()
    evidence.frames[0]["ocr_status"] = "LOW_CONFIDENCE"
    evidence.frames[0]["nodes"] = [{"id": "a", "label": "A"}]
    evidence.frames[0]["edges"] = [{"source": "a", "target": "b", "relation_type": "CALLS",
                                     "provenance": {"frame_id": "f-a"}}]
    evidence = normalize_evidence_bundle(evidence)
    assert extract_diagram_graphs(evidence.frames) == []
    result = generate_session_pack(evidence, tmp_path)
    assert result["status"] == "NEEDS_REVIEW"
    assert all(claim["source_type"] == "TRANSCRIPT" for claim in result["pack"]["claims"])
    assert not any(claim.get("frame_id") for claim in result["pack"]["claims"])


def test_suppressed_gallery_topic_does_not_block_semantic_visual_coverage(tmp_path):
    evidence = _bundle()
    evidence.frames.append({"frame_id": "gallery", "timestamp": 30, "visual_type": "MEETING_GALLERY",
                            "ocr_status": "NOT_REQUIRED", "semantic_topic": "MEETING_GALLERY:SESSION_GENERAL",
                            "selected": False})
    result = generate_session_pack(evidence, tmp_path)
    assert result["gates"]["VISUAL_TOPIC_COVERAGE"] == "PASS"


def test_unresolved_application_identity_blocks_ready(tmp_path):
    evidence = _bundle()
    evidence.transcript_segments = [
        {"start": 10, "end": 15, "text": "This application provides order status reports."}
    ]
    result = generate_session_pack(evidence, tmp_path)
    assert result["gates"]["APPLICATION_RESOLUTION"] == "FAIL"
    assert result["status"] == "NEEDS_REVIEW"


def test_claim_provenance_requires_known_sources_and_segments():
    claim = {"claim_id": "cl-1", "application_id": "app-a", "claim": "Known fact",
             "source_id": "media-a", "source_type": "TRANSCRIPT", "timestamp": 4,
             "frame_id": None, "confidence": .9, "verification_state": "SOURCE_CONFIRMED",
             "first_seen": "session-a", "last_confirmed": None,
             "supporting_sources": [{"source_id": "media-a", "source_type": "TRANSCRIPT", "segments": [{"segment_id": "s1"}]}],
             "conflicts": []}
    assert validate_pack_claim_provenance([claim], {"media-a"}, set()) == []
    broken = {**claim, "supporting_sources": [{"source_id": "media-a", "source_type": "TRANSCRIPT", "segments": []}]}
    assert validate_pack_claim_provenance([broken], {"media-a"}, set())


def test_duplicate_physical_sources_have_one_canonical_id():
    items = [{"evidence_id": "v1", "source_path": "frames/f.png", "sha256": "abc"},
             {"evidence_id": "v2", "source_path": "frames\\f.png", "sha256": "ABC"}]
    result = deduplicate_source_artifacts(items)
    assert len(result) == 1 and result[0]["aliases"] == ["v2"]
    assert validate_source_artifact_dedup(result) == []
    assert validate_source_artifact_dedup(items)


def test_application_claim_isolation_rejects_cross_application_claim():
    apps = [{"application_id": "app-b", "sections": [{"title": "Risks", "claim_ids": ["cl-a"]}]}]
    claims = [{"claim_id": "cl-a", "application_id": "app-a", "claim": "Fact"}]
    assert validate_application_claim_isolation(apps, claims)


def test_neutral_diagram_relations_never_claim_direction():
    frame = {"frame_id": "f1", "timestamp": 4, "source_image": "f1.png", "ocr_status": "SUCCESS",
             "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
             "edges": [{"source": "a", "target": "b", "relation_type": "DEPENDS_ON", "directed": False,
                        "provenance": {"frame_id": "f1"}}]}
    diagrams = extract_diagram_graphs([frame])
    assert validate_diagram_provenance(diagrams, set(), {"f1"}, set()) == []
    assert validate_diagram_relations(diagrams) == []
    frame["edges"][0]["directed"] = True
    assert validate_diagram_relations(extract_diagram_graphs([frame]))


def test_cross_session_merge_confirms_repeats_and_preserves_conflict():
    def pack(session, text):
        return {"media_id": session, "claims": [{"claim_id": f"{session}-c1", "application_id": "app-a",
                 "claim": text, "fact_key": "hosting", "source_id": session, "source_type": "TRANSCRIPT",
                 "timestamp": 1, "frame_id": None, "confidence": .9, "verification_state": "SOURCE_CONFIRMED",
                 "first_seen": {"session_id": session}, "last_confirmed": {"session_id": session},
                 "supporting_sources": [{"source_id": session, "source_type": "TRANSCRIPT", "segments": [{"segment_id": "s1"}]}], "conflicts": []}]}
    merged = consolidate_claims_across_sessions([pack("s1", "Hosted on a managed server"), pack("s2", "Hosted on a managed server")])
    assert len(merged) == 1 and merged[0]["status"] == "CONFIRMED"
    conflict = consolidate_claims_across_sessions([pack("s1", "Hosted on a managed server"), pack("s2", "Hosted in a local data center")])
    assert len(conflict) == 2 and all(item["status"] == "CONFLICTING" for item in conflict)


def test_mission_pack_requires_session_provenance_and_renders_artifacts(tmp_path):
    facts = [{"application_id": "app-a", "canonical_fact": "Hosted on a managed server", "fact": "Hosted on a managed server",
              "fact_id": "fact-1", "status": "CONFIRMED", "confidence": .9,
              "supporting_sessions": ["s1", "s2"], "evidence_refs": [{"session_id": "s1", "source_id": "s1", "timestamp": 3}],
              "supporting_claims": ["c1", "c2"], "supporting_frames": [], "conflicts": []}]
    output = generate_application_mission_pack("app-a", facts, tmp_path)
    assert output["status"] == "READY"
    assert all(path.exists() for path in output["paths"].values())
    with pytest.raises(ValueError):
        generate_application_mission_pack("app-b", facts, tmp_path)


def test_cross_session_fact_extension_supersession_and_ambiguous_identity_are_explicit():
    base = {"fact_id": "f1", "application_id": "app-a", "fact_key": "hosting", "canonical_text": "Hosted in cloud A",
            "status": "NEEDS_REVIEW", "supporting_sessions": ["s1"], "supporting_claims": ["c1"],
            "supporting_evidence": [{"source_id": "s1"}], "conflicts": [], "supersedes": [], "superseded_by": []}
    extended = merge_cross_session_facts([base], [{**base, "canonical_text": "Hosted in cloud A with zone redundancy",
        "merge_relation": "EXTENDED", "supporting_sessions": ["s2"], "supporting_claims": ["c2"]}])
    assert extended[0]["status"] == "EXTENDED"
    superseded = merge_cross_session_facts([base], [{**base, "fact_id": "f2", "canonical_text": "Hosted in cloud B",
        "merge_relation": "SUPERSEDED", "supporting_sessions": ["s2"], "supporting_claims": ["c2"]}])
    assert superseded[0]["status"] == "SUPERSEDED"
    assert superseded[1]["supersedes"] == ["f1"]


def test_cross_session_pipeline_resolves_exact_identity_and_generates_provenance_graph_and_pack(tmp_path):
    def pack(session_id):
        return {
            "media_id": session_id,
            "application_candidates": [{"application_id": "service-alpha", "name": "Service Alpha",
                                        "aliases": ["Alpha"], "status": "NEW_APPLICATION"}],
            "claims": [{"claim_id": f"c-{session_id}", "application_id": "service-alpha",
                        "claim": "Service Alpha provides order status reports.",
                        "source_id": session_id, "source_type": "TRANSCRIPT", "timestamp": 12,
                        "frame_id": None, "confidence": .9, "verification_state": "SOURCE_CONFIRMED",
                        "first_seen": {"session_id": session_id, "timestamp": 12},
                        "supporting_sources": [{"source_id": session_id, "source_type": "TRANSCRIPT",
                                                "timestamp": 12, "segments": [{"segment_id": f"seg-{session_id}"}]}],
                        "conflicts": []}],
        }

    result = generate_cross_session_knowledge([pack("s1"), pack("s2")], tmp_path)
    assert result["status"] == "READY"
    assert result["facts"][0]["status"] == "CONFIRMED"
    assert result["facts"][0]["supporting_sessions"] == ["s1", "s2"]
    assert result["application_knowledge_graph"].is_file()
    assert len(result["mission_packs"]) == 1
    assert all(path.is_file() for path in result["mission_packs"][0]["paths"].values())


def test_cross_session_pipeline_waits_for_corroboration_before_mission_pack(tmp_path):
    pack = {"media_id": "s1", "application_candidates": [{"application_id": "service-alpha",
            "name": "Service Alpha", "aliases": [], "status": "NEW_APPLICATION"}],
            "claims": [{"claim_id": "c1", "application_id": "service-alpha", "claim": "Service Alpha provides reports.",
            "source_id": "s1", "source_type": "TRANSCRIPT", "timestamp": 1, "frame_id": None,
            "confidence": .9, "verification_state": "SOURCE_CONFIRMED", "first_seen": "s1",
            "supporting_sources": [{"source_id": "s1"}], "conflicts": []}]}
    result = generate_cross_session_knowledge([pack], tmp_path)
    assert result["status"] == "NEEDS_MORE_EVIDENCE"
    assert result["mission_packs"] == []


def test_cross_session_pipeline_keeps_conflicting_facts_in_mission_pack(tmp_path):
    def pack(session_id, statement):
        return {"media_id": session_id, "application_candidates": [
            {"application_id": "service-alpha", "name": "Service Alpha", "aliases": [],
             "status": "NEW_APPLICATION"}],
            "claims": [{"claim_id": session_id, "application_id": "service-alpha", "fact_key": "hosting",
                        "claim": statement, "source_id": session_id, "source_type": "TRANSCRIPT", "timestamp": 2,
                        "confidence": .9, "verification_state": "SOURCE_CONFIRMED",
                        "supporting_sources": [{"source_id": session_id, "segments": [{"segment_id": session_id}]}],
                        "conflicts": []}]}

    result = generate_cross_session_knowledge(
        [pack("s1", "The application runs in cloud A."), pack("s2", "The application runs in cloud B.")],
        tmp_path,
    )
    assert len(result["mission_packs"]) == 1
    assert len(result["facts"]) == 2
    assert all(fact["status"] == "CONFLICTING" for fact in result["facts"])


def test_ambiguous_application_claims_remain_needs_review_during_consolidation():
    pack = {"media_id": "s1", "application_candidates": [{"application_id": "app-a", "name": "Service Alpha",
            "aliases": ["Alpha"], "status": "AMBIGUOUS"}],
            "claims": [{"claim_id": "c1", "application_id": "app-a", "claim": "Service Alpha has a queue",
            "source_id": "s1", "source_type": "TRANSCRIPT", "timestamp": 5, "frame_id": None,
            "confidence": .6, "verification_state": "SOURCE_CONFIRMED", "supporting_sources": [], "conflicts": []}]}

    facts = consolidate_claims_across_sessions([pack])

    assert facts[0]["status"] == "NEEDS_REVIEW"
    assert facts[0]["application_id"] is None


def test_session_pack_is_generic_and_emits_diagnostic_when_quality_gates_fail(tmp_path):
    bundle = _bundle(transcript_state="PARTIAL", speech_gate="FAIL", semantic_gate="FAIL")
    result = generate_session_pack(bundle, tmp_path)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["diagnostic"].name == "alpha-diagnostic.json"
    assert not (tmp_path / "alpha.pdf").exists()


def test_production_documentation_modules_contain_no_golden_literals():
    production = Path(__file__).parents[1] / "src" / "transcript_pipeline" / "documentation"
    forbidden = (r"PG\s*RegDoc", r"\bregdoc\b", r"CPRT", r"kanban", r"production matrix",
                 r"recording and viewing", r"Session\s*41", r"AMS_KAP_-_App_Support_-_Session_41",
                 r"frame_0005", r"frame_0006", r"frame_0021", r"C-\d{3}",
                 r"\b\d{2}:\d{2}:\d{2}\b")
    violations = [f"{path}:{pattern}" for path in production.rglob("*.py")
                  for pattern in forbidden if re.search(pattern, path.read_text(encoding="utf-8"), re.I)]
    assert violations == []


def test_application_discovery_accepts_generic_identity_statement():
    evidence = _bundle()
    evidence.transcript_segments = [{"start": 2, "end": 5, "text": "So what this is essentially is AtlasDesk."}]
    candidates = discover_application_candidates(normalize_evidence_bundle(evidence))
    assert [item["name"] for item in candidates] == ["AtlasDesk"]
    assert candidates[0]["provenance"][0]["timestamp"] == 2
