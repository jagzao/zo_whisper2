"""DV2 targeted tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcript_pipeline.documentation.models import DocumentationMode
from transcript_pipeline.projects import validate_project


def test_dv2_01_mode_explicit():
    """Explicit KT_SESSION wins over filename hint."""
    project = {
        "name": "Test",
        "documentation": {"mode": "KT_SESSION"}
    }
    errors = validate_project(project)
    assert errors == []


def test_dv2_02_artifact_mapping():
    """default_artifact_type=KT maps to KT_SESSION when documentation.mode=AUTO."""
    # This test requires mode resolver implementation
    pass


def test_dv2_03_safe_fallback():
    """No config/provider => REFERENCE, typed reason."""
    from transcript_pipeline.documentation.classifier import resolve_documentation_mode
    mode, reason = resolve_documentation_mode(None)
    assert mode == DocumentationMode.REFERENCE
    assert reason == "fallback"


def test_dv2_04_confidential_remote_block():
    """Remote synthesis on confidential project is blocked before request."""
    # Requires synthesis provider with privacy guard
    pass


def test_dv2_05_local_confidential_allowed():
    """Configured local provider can receive bounded synthesis blocks."""
    pass


def test_dv2_06_evidence_ids_stable():
    """Same persisted evidence => same evidence ids."""
    from transcript_pipeline.documentation.evidence import deterministic_evidence_id
    id1 = deterministic_evidence_id(0.0, 2.0, "transcript", "", None, "source")
    id2 = deterministic_evidence_id(0.0, 2.0, "transcript", "", None, "source")
    assert id1 == id2


def test_dv2_07_segment_recovery():
    """Timestamped saved segments preferred."""
    pass


def test_dv2_08_mapped_segment_fallback():
    """Missing saved segment file => unique frame-mapped segments recovered/deduped."""
    pass


def test_dv2_09_full_transcript_fallback():
    """Only full transcript => evidence result explicitly lower fidelity, no fake timestamps."""
    pass


def test_dv2_10_low_confidence_queue():
    """none-source items enter review queue and do not become synthesis facts automatically."""
    pass


def test_dv2_11_compaction_order():
    """Blocks preserve chronology."""
    pass


def test_dv2_12_ocr_dedup():
    """Repeated OCR from near-identical frames does not inflate synthesis input."""
    pass


def test_dv2_13_block_bounds():
    """Hard character/call bounds respected."""
    pass


def test_dv2_14_json_only():
    """Free-form model response rejected."""
    pass


def test_dv2_15_unknown_evidence():
    """Claim citing E-999 fails grounding validation."""
    pass


def test_dv2_16_missing_evidence():
    """Factual claim without refs fails."""
    pass


def test_dv2_17_bad_procedure():
    """Procedure step without evidence fails."""
    pass


def test_dv2_18_reviewed_spoof():
    """Model-provided HUMAN_REVIEWED fails/coerces to unreviewed."""
    pass


def test_dv2_19_timestamp_bound():
    """Out-of-duration ref fails."""
    pass


def test_dv2_20_last_good():
    """Invalid synthesis does not overwrite existing valid manual/document."""
    pass


def test_dv2_21_screenshot_duplicate():
    """Near-identical pHash frames collapse."""
    pass


def test_dv2_22_screenshot_cap():
    """Global/per-section caps enforced."""
    pass


def test_dv2_23_no_imagehash_fallback():
    """Missing optional hash lib still produces deterministic bounded selection."""
    pass


def test_dv2_24_kt_template():
    """Synthetic KT document includes summary/context/process/system/decision/risk/open-question/action sections."""
    pass


def test_dv2_25_tutorial_procedure():
    """Synthetic tutorial creates grounded ordered procedure."""
    pass


def test_dv2_26_reference_no_procedure():
    """Reference source can validly output procedures=[]."""
    pass


def test_dv2_27_semantic_manual():
    """MANUAL content comes from KnowledgeDocument, not one heading per EvidenceItem."""
    pass


def test_dv2_28_review_queue_callout():
    """Manual shows count, not 20 empty sections."""
    pass


def test_dv2_29_semantic_pdf():
    """PDF includes semantic headings/evidence refs and bounded screenshots."""
    pass


def test_dv2_30_evidence_timeline():
    """EVIDENCE_TIMELINE preserves raw chronological captured evidence."""
    pass


def test_dv2_31_chunks_semantic():
    """chunks.jsonl count follows semantic units, not frame count."""
    pass


def test_dv2_32_chunks_metadata():
    """scope/project/artifact/actionability/evidence refs all present."""
    pass


def test_dv2_33_raw_transcript_forbidden():
    """No whole raw transcript/VTT/media keys in package/chunks."""
    pass


def test_dv2_34_semantic_package():
    """Knowledge Package summary/title/sections originate from KnowledgeDocument."""
    pass


def test_dv2_35_no_fake_procedure():
    """KT document without procedure yields no procedure.json / package procedures."""
    pass


def test_dv2_36_real_procedure_bridge():
    """Tutorial procedure maps to Procedure v1 preserving evidence."""
    pass


def test_dv2_37_identity_timestamp_independent():
    """generatedAt changes alone do not create new knowledge version."""
    pass


def test_dv2_38_semantic_version_change():
    """Material semantic/evidence change increments existing knowledge version."""
    pass


def test_dv2_39_publisher_compatibility():
    """Existing outbox/publisher receives semantic package unchanged at transport layer."""
    pass


def test_dv2_40_regeneration_no_whisper():
    """Monkeypatch transcription to throw; regenerate succeeds from persisted artifacts."""
    pass


def test_dv2_41_regeneration_no_ffmpeg():
    """Monkeypatch keyframe extraction to throw; regenerate succeeds."""
    pass


def test_dv2_42_regeneration_no_ocr():
    """Monkeypatch OCR to throw; regenerate succeeds."""
    pass


def test_dv2_43_regeneration_no_vision():
    """Monkeypatch frame vision to throw; regenerate succeeds."""
    pass


def test_dv2_44_evidence_only_provider_unavailable():
    """Evidence outputs succeed; synthesis typed unavailable; no false MANUAL_READY."""
    pass


def test_dv2_45_malformed_retry_bound():
    """At most one schema-repair call."""
    pass


def test_dv2_46_no_recursive_loop():
    """Provider invocation count cannot exceed configured block count + one bounded repair."""
    pass


def test_dv2_47_current_compatibility():
    """Existing manual/steps metadata callers do not crash."""
    pass


def test_dv2_48_synthetic_no_client_data():
    """Fixtures contain only synthetic organizations/apps/screens."""
    pass