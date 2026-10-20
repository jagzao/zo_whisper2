"""DV2-01..03, DV2-06..10, DV2-30 — mode resolution, config validation and
the Evidence Plane (TEST-MATRIX-ZMI-DOCS-V2-001)."""
from __future__ import annotations

import json

import pytest

from tests.fixtures.documentation_v2 import (
    load_fixture,
    materialize_frames_dir,
)
from transcript_pipeline.documentation.classifier import (
    ModeResolution,
    resolve_documentation_mode,
)
from transcript_pipeline.documentation.evidence import (
    FIDELITY_UNTIMED_FULL_TRANSCRIPT,
    build_evidence_timeline,
)
from transcript_pipeline.documentation.evidence_writer import write_evidence_outputs
from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2
from transcript_pipeline.projects import validate_project

# ── DV2-01 mode explicit ──────────────────────────────────────────────────

def test_dv2_01_explicit_mode_wins_over_filename_hint(tmp_path):
    """Explicit KT_SESSION wins over a `_tutorial` filename hint."""
    project = {
        "documentation": {"mode": "KT_SESSION"},
        "second_brain": {"enabled": True, "scope": "GLOBAL", "domain": "d",
                          "default_artifact_type": "TUTORIAL"},
    }
    resolution = resolve_documentation_mode(project, filename="acme_tutorial_session.mp4")
    assert resolution.mode == "KT_SESSION"
    assert resolution.source == "explicit_config"

    # End-to-end: the pipeline resolves the explicit mode too.
    frames_dir = materialize_frames_dir("reference_meeting", tmp_path)
    result = generate_documentation_v2(
        frames_dir, "acme_tutorial_session.mp4", project_config=project, evidence_only=True
    )
    assert result["mode"]["mode"] == "KT_SESSION"
    assert result["mode"]["source"] == "explicit_config"


# ── DV2-02 artifact mapping ───────────────────────────────────────────────

def test_dv2_02_artifact_type_kt_maps_to_kt_session_when_auto():
    project = {
        "documentation": {"mode": "AUTO"},
        "second_brain": {"enabled": True, "scope": "PROJECT", "project_id": "acme",
                          "domain": "second-brain/acme", "default_artifact_type": "KT"},
    }
    resolution = resolve_documentation_mode(project)
    assert resolution.mode == "KT_SESSION"
    assert resolution.source == "artifact_mapping"
    assert "KT" in resolution.reason


# ── DV2-03 safe fallback ──────────────────────────────────────────────────

def test_dv2_03_no_config_no_provider_falls_back_to_reference_with_typed_reason():
    resolution = resolve_documentation_mode(None)
    assert resolution == ModeResolution(mode="REFERENCE", source="fallback", reason="no_authority_resolved")
    assert isinstance(resolution.to_dict(), dict)

    # Also with a config that has no documentation block and no second_brain.
    resolution = resolve_documentation_mode({"name": "Acme"})
    assert resolution.mode == "REFERENCE"
    assert resolution.source == "fallback"


def test_dv2_03_config_documentation_block_validation():
    assert validate_project({"name": "x", "documentation": {"mode": "KT_SESSION"}}) == []
    assert validate_project({"name": "x", "documentation": {"synthesis_enabled": False}}) == []
    assert validate_project({"name": "x", "documentation": {"max_screenshots": 5}}) == []
    assert validate_project({"name": "x"}) == []

    errors = validate_project({"name": "x", "documentation": {"mode": "NOT_A_MODE"}})
    assert any("documentation.mode" in e for e in errors)
    errors = validate_project({"name": "x", "documentation": {"max_screenshots": 0}})
    assert any("max_screenshots" in e for e in errors)
    errors = validate_project({"name": "x", "documentation": {"max_screenshots_per_section": -1}})
    assert any("max_screenshots_per_section" in e for e in errors)
    errors = validate_project({"name": "x", "documentation": {"synthesis_enabled": "yes"}})
    assert any("synthesis_enabled" in e for e in errors)
    errors = validate_project({"name": "x", "documentation": []})
    assert any("documentation" in e for e in errors)


# ── DV2-06 evidence ids stable ────────────────────────────────────────────

def test_dv2_06_same_persisted_evidence_yields_same_evidence_ids(tmp_path):
    mapping = load_fixture("kt_session")
    first = build_evidence_timeline(mapping, source_media="acme_kt_session.mp4")
    second = build_evidence_timeline(mapping, source_media="acme_kt_session.mp4")
    assert [i.evidence_id for i in first.items] == [i.evidence_id for i in second.items]
    assert first.source_hash == second.source_hash
    # Deterministic chronological E-### ordinals.
    assert first.items[0].evidence_id == "E-001"
    assert first.items[-1].evidence_id == f"E-{len(first.items):03d}"


# ── DV2-07 segment recovery ───────────────────────────────────────────────

def test_dv2_07_timestamped_saved_segments_preferred():
    mapping = load_fixture("kt_session")
    timeline = build_evidence_timeline(mapping)
    timestamped = [
        item for item in timeline.items
        if item.evidence_source in ("transcript", "transcript_ocr")
        and item.timestamp_start != item.timestamp_end
    ]
    assert timestamped, "persisted segment start/end must be recovered as real ranges"
    # The segment window around 100s must be 97..107, not the frame PTS.
    first = timestamped[0]
    assert first.timestamp_start == pytest.approx(97.0)
    assert first.timestamp_end == pytest.approx(107.0)


# ── DV2-08 mapped segment fallback ────────────────────────────────────────

def test_dv2_08_missing_saved_segment_file_recovers_unique_mapped_segments():
    mapping = {
        "video_info": {"name": "m.mp4", "duration": 100.0},
        "transcription_summary": {"language": "en"},
        "frames": [
            {"frame_file": "frame_0000.png", "timestamp": 10.0, "timestamp_formatted": "00:00:10"},
            {"frame_file": "frame_0001.png", "timestamp": 12.0, "timestamp_formatted": "00:00:12"},
            {"frame_file": "frame_0002.png", "timestamp": 40.0, "timestamp_formatted": "00:00:40"},
        ],
        # No transcription_segments persisted: only full_text per frame; the
        # same segment text mapped to TWO frames must dedupe to one item.
        "transcription_mapping": {
            "frame_0000.png": {"full_text": "shared segment text"},
            "frame_0001.png": {"full_text": "shared segment text"},
            "frame_0002.png": {"full_text": "other segment text"},
        },
    }
    timeline = build_evidence_timeline(mapping)
    texts = [item.transcript_excerpt for item in timeline.items if item.transcript_excerpt]
    assert texts.count("shared segment text") == 1
    assert texts.count("other segment text") == 1
    assert timeline.item_count == 2


# ── DV2-09 full transcript fallback ───────────────────────────────────────

def test_dv2_09_full_transcript_only_yields_lower_fidelity_no_fake_timestamps():
    mapping = {
        "video_info": {"name": "m.mp4", "duration": 500.0},
        "transcription_summary": {"language": "en", "full_transcription": " ".join(f"word{i}" for i in range(300))},
        "frames": [{"frame_file": "frame_0000.png", "timestamp": 250.0, "timestamp_formatted": "00:04:10"}],
        "transcription_mapping": {"frame_0000.png": {"full_text": ""}},
    }
    timeline = build_evidence_timeline(mapping)
    assert timeline.fidelity == FIDELITY_UNTIMED_FULL_TRANSCRIPT
    facts = timeline.facts()
    assert len(facts) > 1, "long transcript must split into bounded untimed facts"
    assert all(item.untimed is True for item in facts)
    assert "".join(item.transcript_excerpt for item in facts) == " ".join(
        f"word{i}" for i in range(300)
    )
    assert all(len(item.transcript_excerpt) <= 1200 for item in facts)
    item = facts[0]
    # Honest full-span bounds, no fabricated per-segment timestamps.
    assert item.timestamp_start == 0.0
    assert item.timestamp_end == pytest.approx(500.0)
    assert item.evidence_source == "transcript"
    # The empty frame stays a queued placeholder, never a fake fact.
    assert len(timeline.review_queue) == 1
    assert timeline.review_queue[0].evidence_source == "none"


# ── DV2-10 low-confidence queue ───────────────────────────────────────────

def test_dv2_10_none_source_items_enter_review_queue_not_synthesis_facts(tmp_path):
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    timeline = build_evidence_timeline(mapping)
    assert timeline.review_queue, "low-confidence tail must be queued"
    assert all(item.evidence_source == "none" for item in timeline.review_queue)
    facts_ids = {item.evidence_id for item in timeline.facts()}
    queue_ids = {item.evidence_id for item in timeline.review_queue}
    assert facts_ids.isdisjoint(queue_ids)

    # The review queue is persisted and isolated (AC-07).
    write_evidence_outputs(frames_dir, timeline)
    queue = json.loads((frames_dir / "evidence" / "review-queue.json").read_text(encoding="utf-8"))
    assert queue["reviewRequiredCount"] == len(timeline.review_queue)
    assert all(item["evidenceSource"] == "none" for item in queue["items"])


# ── DV2-30 evidence timeline ──────────────────────────────────────────────

def test_dv2_30_evidence_timeline_preserves_raw_chronological_evidence(tmp_path):
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    result = generate_documentation_v2(frames_dir, "acme_kt_session.mp4", evidence_only=True)
    assert result["status"] == "EVIDENCE_READY"

    timeline_md = (frames_dir / "evidence" / "EVIDENCE_TIMELINE.md").read_text(encoding="utf-8")
    items = [json.loads(line) for line in (frames_dir / "evidence" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(items) == result["evidence"]["item_count"]
    # Chronological preservation: raw items keep source order and excerpts.
    timestamps = [item["timestampStart"] for item in items]
    assert timestamps == sorted(timestamps)
    for item in items:
        assert f"## {item['evidenceId']} @ " in timeline_md
        if item["transcriptExcerpt"]:
            assert item["transcriptExcerpt"][:40] in timeline_md
    # No giant evidence PDF by default (SPEC §10).
    assert not (frames_dir / "evidence" / "EVIDENCE_TIMELINE.pdf").exists()
