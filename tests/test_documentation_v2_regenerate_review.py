"""DV2-40..43 — regeneration without any upstream work — plus the WP-15 CLI
and WP-16 human-review surface (TEST-MATRIX-ZMI-DOCS-V2-001)."""
from __future__ import annotations

import json

import pytest

from tests.fixtures.documentation_v2 import materialize_frames_dir
from tests.fixtures.documentation_v2.mock_synthesis import (
    MockAllowAllGuard,
    MockKTSynthesisProvider,
)
from transcript_pipeline.documentation import engine
from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2
from transcript_pipeline.documentation.regenerate_v2 import (
    UpstreamWorkAttemptedError,
    main as regenerate_main,
    regenerate_documentation_v2,
)
from transcript_pipeline.documentation.review import (
    edit_claim,
    edit_section,
    load_knowledge_document,
    mark_claim_reviewed,
    rerender_from_document,
)
from transcript_pipeline.documentation.synthesis import SynthesisService

KT_CONFIG = {"name": "Acme", "documentation": {"mode": "KT_SESSION"}}


def _deny(*args, **kwargs):
    raise AssertionError("upstream work must not run during V2 regeneration")


@pytest.fixture
def processed_kt(tmp_path):
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    result = generate_documentation_v2(
        frames_dir, "acme_kt_session.mp4",
        project_config=KT_CONFIG,
        synthesis_service=SynthesisService(MockKTSynthesisProvider(), MockAllowAllGuard(), model_name="mock"),
    )
    assert result["semantic"]["ready"] is True
    return frames_dir, result


# ── DV2-40 regeneration no whisper ────────────────────────────────────────

def test_dv2_40_regeneration_never_invokes_transcription(tmp_path, monkeypatch, processed_kt):
    frames_dir, _ = processed_kt
    from transcript_pipeline.transcription import processor as transcription_processor

    monkeypatch.setattr(
        transcription_processor.SimpleScanProcessor, "transcribe_file", _deny, raising=True
    )
    result = regenerate_documentation_v2(
        frames_dir, project_config=KT_CONFIG,
        synthesis_service=SynthesisService(MockKTSynthesisProvider(), MockAllowAllGuard(), model_name="mock"),
    )
    assert result["status"] in ("MANUAL_READY", "PUBLISH_ENQUEUED")
    assert result["semantic"]["ready"] is True


# ── DV2-41 regeneration no ffmpeg ─────────────────────────────────────────

def test_dv2_41_regeneration_never_invokes_keyframe_extraction(tmp_path, monkeypatch, processed_kt):
    frames_dir, _ = processed_kt
    from transcript_pipeline.media import keyframe_extractor

    monkeypatch.setattr(keyframe_extractor.KeyframeExtractor, "extract_keyframes", _deny, raising=True)
    result = regenerate_documentation_v2(frames_dir, project_config=KT_CONFIG, evidence_only=True)
    assert result["status"] == "EVIDENCE_READY"
    assert (frames_dir / "evidence" / "evidence.jsonl").exists()


# ── DV2-42 regeneration no OCR ────────────────────────────────────────────

def test_dv2_42_regeneration_never_invokes_ocr(tmp_path, monkeypatch, processed_kt):
    frames_dir, _ = processed_kt
    monkeypatch.setattr(engine, "_ocr_text", _deny, raising=True)
    result = regenerate_documentation_v2(frames_dir, project_config=KT_CONFIG, evidence_only=True)
    assert result["status"] == "EVIDENCE_READY"


# ── DV2-43 regeneration no vision ─────────────────────────────────────────

def test_dv2_43_regeneration_never_invokes_vision(tmp_path, monkeypatch, processed_kt):
    frames_dir, _ = processed_kt
    monkeypatch.setattr(engine, "_vision_description", _deny, raising=True)
    from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider

    monkeypatch.setattr(OpenAICompatibleProvider, "describe_frame", _deny, raising=True)
    monkeypatch.setattr(OpenAICompatibleProvider, "describe_frame_with_prompt", _deny, raising=True)
    result = regenerate_documentation_v2(frames_dir, project_config=KT_CONFIG, evidence_only=True)
    assert result["status"] == "EVIDENCE_READY"


def test_regeneration_no_upstream_guard_hard_fails_on_upstream_call(tmp_path, monkeypatch, processed_kt):
    """The built-in no-upstream-work guard turns any upstream attempt into a
    typed error instead of silently doing heavy work."""
    frames_dir, _ = processed_kt
    monkeypatch.setattr(engine, "_ocr_text", _deny, raising=True)
    with pytest.raises(UpstreamWorkAttemptedError):
        # The guard patches already-imported engine module attrs to deniers.
        from transcript_pipeline.documentation.regenerate_v2 import default_upstream_guard, install_upstream_guard, undo_guard

        undos = install_upstream_guard(default_upstream_guard())
        try:
            engine._ocr_text(frames_dir / "frame_0000.png")
        finally:
            undo_guard(undos)


def test_regeneration_cli_entrypoint(tmp_path, capsys, processed_kt):
    frames_dir, _ = processed_kt
    exit_code = regenerate_main([str(frames_dir), "--evidence-only"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "status=EVIDENCE_READY" in out

    exit_code = regenerate_main([str(tmp_path / "missing"), "--evidence-only"])
    assert exit_code == 2


def test_regeneration_dry_rebuilds_evidence_without_synthesis(tmp_path, processed_kt):
    frames_dir, _ = processed_kt
    result = regenerate_documentation_v2(frames_dir, evidence_only=True)
    assert result["status"] == "EVIDENCE_READY"
    assert result["synthesis"]["invocation_count"] == 0


# ── WP-16 human review compatibility ─────────────────────────────────────

def test_legacy_evidence_step_functions_still_work(processed_kt):
    frames_dir, _ = processed_kt
    from transcript_pipeline.documentation.engine import remove_step, update_step

    updated = update_step(
        frames_dir / "manual", frames_dir / "ai-package", frames_dir, "step-0001",
        instruction="Confirmed by reviewer.",
    )
    assert updated["reviewed"] is True
    result = remove_step(frames_dir / "manual", frames_dir / "ai-package", frames_dir, "step-0002")
    assert result["step_count"] >= 1


def test_semantic_claim_edit_and_explicit_human_review(processed_kt):
    frames_dir, _ = processed_kt
    manual_dir = frames_dir / "manual"
    document = load_knowledge_document(manual_dir)
    claim = document.sections[0].claims[0]

    edited = edit_claim(manual_dir, claim.id, text="EDITED claim text kept grounded.")
    assert any(
        c.text == "EDITED claim text kept grounded."
        for section in edited.sections for c in section.claims
    )
    # Editing alone never grants review status.
    assert all(
        c.verification_status == "SYNTHESIZED_UNREVIEWED"
        for section in edited.sections for c in section.claims
    )

    reviewed = mark_claim_reviewed(manual_dir, claim.id)
    target = [c for section in reviewed.sections for c in section.claims if c.id == claim.id][0]
    assert target.verification_status == "HUMAN_REVIEWED"

    with pytest.raises(KeyError):
        edit_claim(manual_dir, "claim-999", text="x")


def test_semantic_section_edit_and_rerender_without_synthesis(processed_kt):
    frames_dir, _ = processed_kt
    manual_dir = frames_dir / "manual"
    document = load_knowledge_document(manual_dir)
    section = document.sections[0]

    edited = edit_section(manual_dir, section.id, title="EDITED title", summary="EDITED summary.")
    assert edited.sections[0].title == "EDITED title"

    rerender = rerender_from_document(
        manual_dir, frames_dir / "ai-package", frames_dir,
        edited, _timeline_of(frames_dir, edited.source),
        project_config=KT_CONFIG,
    )
    assert rerender["manual"]["semantic_section_count"] == len(edited.sections)
    manual_text = (manual_dir / "MANUAL.md").read_text(encoding="utf-8")
    assert "EDITED title" in manual_text
    with pytest.raises(KeyError):
        edit_section(manual_dir, "section-99", title="x")


def _timeline_of(frames_dir, source_media):
    from transcript_pipeline.documentation.evidence import build_evidence_timeline, load_persisted_steps

    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    return build_evidence_timeline(mapping, steps=load_persisted_steps(frames_dir / "manual"),
                                   source_media=source_media)
