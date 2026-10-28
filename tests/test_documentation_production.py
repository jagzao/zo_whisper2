from __future__ import annotations

import json

from tests.test_documentation_session_pack import _bundle
from transcript_pipeline.documentation.production import (
    CORPUS_GATES,
    build_media_evidence_bundle,
    discover_application_groups,
    document_state,
    evaluate_corpus_gate,
    generate_cross_session_from_directory,
    generate_full_corpus,
    run_golden2,
    run_pilot,
    run_session_pack,
)


def test_media_evidence_adapter_and_status_are_gate_aware(tmp_path):
    bundle = _bundle(transcript_state="PARTIAL", speech_gate="FAIL")
    normalized = build_media_evidence_bundle(
        media_id=bundle.media_id, video_metadata=bundle.video_metadata,
        transcript_segments=bundle.transcript_segments, speech_coverage=bundle.speech_coverage,
        visual_report={"frames": bundle.frames}, evidence_events=[],
    )
    evidence = tmp_path / "media-evidence-bundle.json"
    evidence.write_text(json.dumps(normalized), encoding="utf-8")
    assert document_state(evidence)["documentation_state"] == "TRANSCRIPT_PARTIAL"


def test_corpus_gate_requires_all_owner_and_runtime_gates():
    assert evaluate_corpus_gate({})["corpus_generation"] == "FROZEN"
    assert evaluate_corpus_gate({gate: "PASS" for gate in CORPUS_GATES})["corpus_generation"] == "READY"


def test_session_generation_is_idempotent_and_golden2_waits_for_owner(tmp_path):
    bundle = _bundle()
    result = run_golden2(bundle, tmp_path)
    assert result["golden2_state"] == "TECHNICAL_PASS_OWNER_REVIEW_PENDING"
    manifest = json.loads((tmp_path / "generation-state.json").read_text())
    assert manifest["sources"][bundle.media_id]["GENERATION_STATE"] == "READY"
    second = run_session_pack(bundle, tmp_path)
    assert second["state"] == "RESUMED"


def test_failed_golden2_persists_diagnostic_without_pack_publication(tmp_path):
    bundle = _bundle(transcript_state="NEEDS_REVIEW", speech_gate="FAIL")
    result = run_golden2(bundle, tmp_path)
    assert result["golden2_state"] == "NEEDS_REVIEW"
    assert result["diagnostics_persisted"]
    assert result["diagnostic"].is_file()


def test_pilot_selects_three_and_blocks_on_failed_gate(tmp_path):
    bundles = [_bundle()]
    bundles[0].media_id = "m-1"
    bundles[0].video_metadata["basename"] = "one.mp4"
    failed = _bundle(transcript_state="PARTIAL", speech_gate="FAIL")
    failed.media_id = "m-2"
    failed.video_metadata["basename"] = "two.mp4"
    result = run_pilot([*bundles, failed], tmp_path)
    assert result["selected"] == ["m-1", "m-2"]
    assert result["status"] == "FAIL"
    assert result["prevents_corpus_generation"]


def test_cross_session_orchestrator_reports_missing_pair(tmp_path):
    assert generate_cross_session_from_directory(tmp_path, tmp_path / "out")["status"] == "BLOCKED_NO_ELIGIBLE_PAIR"
    blocked = generate_full_corpus(tmp_path, tmp_path / "corpus", {}, None)
    assert blocked["corpus_generation"] == "FROZEN"
    assert blocked["mission_packs"] == []


def test_cross_session_orchestrator_publishes_pair_from_ready_session_packs(tmp_path):
    pack_dir = tmp_path / "sessions"
    pack_dir.mkdir()
    for session_id in ("s1", "s2"):
        pack = {
            "document_type": "SESSION_KNOWLEDGE_PACK", "quality_state": "READY", "media_id": session_id,
            "application_candidates": [{"application_id": "service-alpha", "name": "Service Alpha",
                                         "aliases": [], "status": "NEW_APPLICATION"}],
            "claims": [{"claim_id": f"claim-{session_id}", "application_id": "service-alpha",
                        "claim": "Service Alpha provides order status reports.", "source_id": session_id,
                        "source_type": "TRANSCRIPT", "timestamp": 3, "confidence": 0.9,
                        "verification_state": "SOURCE_CONFIRMED", "first_seen": {"session_id": session_id},
                        "supporting_sources": [{"source_id": session_id, "segments": [{"segment_id": "seg"}]}],
                        "conflicts": []}],
        }
        (pack_dir / f"{session_id}.json").write_text(json.dumps(pack), encoding="utf-8")
    result = generate_cross_session_from_directory(pack_dir, tmp_path / "mission")
    assert result["status"] == "READY"
    assert len(result["mission_packs"]) == 1


def test_application_groups_do_not_fuzzy_merge_names():
    packs = [
        {"media_id": "s1", "application_candidates": [{"name": "Service Alpha"}]},
        {"media_id": "s2", "application_candidates": [{"name": "Service Alph"}]},
    ]
    groups = discover_application_groups(packs)
    assert len(groups) == 2
    assert all(group["candidate_state"] == "PROBABLE" for group in groups)
