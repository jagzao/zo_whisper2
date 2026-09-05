"""Unit coverage for the video-to-documentation engine (US-001 §4.6/§4.7/§4.8).

Pure dict/JSON-driven — no FFmpeg, no real video. Exercises the confidence
rules, manifest/steps schema, visual-evidence layering (OCR + vision LLM,
privacy-gated), the "regenerate without retranscribing" contract, and the
human review edit/remove surface directly against `frame_mapping.json`-shaped
input.
"""
from __future__ import annotations

import json

import pytest

from transcript_pipeline.documentation import engine
from transcript_pipeline.documentation.engine import (
    build_steps,
    generate_documentation,
    load_steps,
    regenerate_from_steps,
    remove_step,
    update_step,
    write_ai_package,
    write_manual,
)
from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep

MAPPING_WITH_TRANSCRIPT = {
    "video_info": {"name": "demo.mp4", "duration": 10.0, "extraction_method": "smart_scene"},
    "transcription_summary": {"language": "en"},
    "frames": [
        {"frame_file": "frame_0000.png", "timestamp": 1.5, "timestamp_formatted": "00:00:01.500"},
        {"frame_file": "frame_0001.png", "timestamp": 6.0, "timestamp_formatted": "00:00:06.000"},
    ],
    "transcription_mapping": {
        "frame_0000.png": {"full_text": "Click the New Project button to get started."},
        "frame_0001.png": {"full_text": ""},
    },
}


def test_build_steps_grounds_instruction_in_transcript_and_orders_by_timestamp():
    steps = build_steps(MAPPING_WITH_TRANSCRIPT)

    assert [s.order for s in steps] == [1, 2]
    assert steps[0].instruction == "Click the New Project button to get started."
    assert steps[0].confidence == "high"
    assert steps[0].evidence_source == "transcript"
    assert steps[0].transcript_ref == steps[0].instruction


def test_build_steps_flags_frame_without_transcript_as_low_confidence():
    steps = build_steps(MAPPING_WITH_TRANSCRIPT)

    empty_step = steps[1]
    assert empty_step.confidence == "low"
    assert empty_step.evidence_source == "none"
    # Must never fabricate a plausible-sounding instruction for missing evidence.
    assert "New Project" not in empty_step.instruction
    assert empty_step.transcript_ref == ""


def test_build_steps_never_hallucinates_beyond_transcript_text():
    """Every non-empty instruction must be exactly the evidence text, not a
    paraphrase/summary that could introduce unsupported claims."""
    steps = build_steps(MAPPING_WITH_TRANSCRIPT)
    for step in steps:
        if step.transcript_ref:
            assert step.instruction == step.transcript_ref


# ── Visual evidence layering (§4.5/§4.7) ─────────────────────────────────

def test_ocr_evidence_grounds_instruction_when_transcript_empty(tmp_path, monkeypatch):
    """A frame with no transcript but real on-screen text (OCR) must ground
    `instruction` in that text — labeled, medium confidence — and must NOT
    fall through to a vision-LLM call (avoids redundant vision calls, §4.5)."""
    from PIL import Image, ImageDraw

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    img = Image.new("RGB", (300, 60), color="white")
    ImageDraw.Draw(img).text((5, 5), "Click Deploy Now", fill="black")
    img.save(frames_dir / "frame_0001.png")

    vision_called = []
    monkeypatch.setattr(engine, "_vision_description", lambda *a, **k: vision_called.append(1) or "should not happen")

    steps = build_steps(MAPPING_WITH_TRANSCRIPT, frames_dir=frames_dir)

    step = steps[1]
    assert step.evidence_source == "ocr"
    assert step.confidence == "medium"
    assert "Deploy" in step.instruction
    assert step.ocr_text and "Deploy" in step.ocr_text
    assert step.visual_description is None
    assert not vision_called, "vision LLM must not be called when OCR already grounded the step"


def test_vision_description_is_never_used_as_instruction_and_never_raises_confidence(tmp_path, monkeypatch):
    """When neither transcript nor OCR ground a step, a vision-LLM
    description may be attached as `visual_description` — but only as a
    clearly-separate, unverified interpretation. It must never become the
    grounded `instruction` and must never push confidence above "low"."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_0001.png").write_bytes(b"not-a-real-image-ocr-will-fail-or-find-nothing")

    monkeypatch.setattr(engine, "_ocr_text", lambda *a, **k: "")  # simulate no readable text
    monkeypatch.setattr(engine, "_vision_description", lambda *a, **k: "The user opens a settings panel.")

    steps = build_steps(MAPPING_WITH_TRANSCRIPT, frames_dir=frames_dir)

    step = steps[1]
    assert step.visual_description == "The user opens a settings panel."
    assert step.confidence == "low"
    assert step.evidence_source == "none"
    assert "settings panel" not in step.instruction, "vision interpretation must never be merged into instruction"


def test_visual_evidence_skipped_entirely_when_transcript_already_grounds_step(tmp_path, monkeypatch):
    """§4.5: avoid redundant OCR/vision work on frames that already have
    strong grounding."""
    mapping_transcript_only = {
        "video_info": MAPPING_WITH_TRANSCRIPT["video_info"],
        "transcription_summary": MAPPING_WITH_TRANSCRIPT["transcription_summary"],
        "frames": [MAPPING_WITH_TRANSCRIPT["frames"][0]],
        "transcription_mapping": {"frame_0000.png": {"full_text": "Click the New Project button to get started."}},
    }
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_0000.png").write_bytes(b"irrelevant")

    calls = []
    monkeypatch.setattr(engine, "_gather_visual_evidence", lambda *a, **k: calls.append(1) or ("", None))

    build_steps(mapping_transcript_only, frames_dir=frames_dir)

    assert not calls, "visual evidence must not be gathered for a frame with transcript grounding"


def test_no_frames_dir_skips_visual_evidence_entirely():
    """Backward-compat / pure-unit-test path: omitting frames_dir must not
    attempt any OCR/vision work (no crash, no I/O)."""
    steps = build_steps(MAPPING_WITH_TRANSCRIPT)
    assert steps[1].ocr_text is None
    assert steps[1].visual_description is None


# ── Generation / regeneration / metadata persistence ─────────────────────

def test_generate_documentation_writes_manual_and_ai_package(tmp_path):
    frames_dir = tmp_path / "demo_Frames" / "demo"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_mapping.json").write_text(json.dumps(MAPPING_WITH_TRANSCRIPT), encoding="utf-8")
    (frames_dir / "frame_0000.png").write_bytes(b"fake-png-bytes-0")
    (frames_dir / "frame_0001.png").write_bytes(b"fake-png-bytes-1")

    summary = generate_documentation(frames_dir, "demo.mp4")

    assert summary["step_count"] == 2
    assert summary["low_confidence_count"] == 1

    manual_dir = frames_dir / "manual"
    manual_text = (manual_dir / "MANUAL.md").read_text(encoding="utf-8")
    assert "Click the New Project button" in manual_text
    assert "confidence: **low**" in manual_text
    assert (manual_dir / "assets" / "step-0001.png").exists()
    assert (manual_dir / "steps.json").exists()

    ai_dir = frames_dir / "ai-package"
    manifest = json.loads((ai_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert len(manifest["procedures"]) == 2
    assert manifest["artifacts"]  # at least one frame asset registered

    chunks = [json.loads(line) for line in (ai_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(chunks) == 2
    assert chunks[0]["metadata"]["confidence"] == "high"


def test_generate_documentation_raises_clearly_when_mapping_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate_documentation(tmp_path, "missing.mp4")


def test_steps_json_persists_source_metadata(tmp_path):
    """Regression: steps.json must include the source block (duration,
    language, extraction_method) — without it, regenerate_from_steps has
    nothing to read and silently resets everything to 0.0/"unknown"."""
    frames_dir = tmp_path / "demo_Frames" / "demo"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_mapping.json").write_text(json.dumps(MAPPING_WITH_TRANSCRIPT), encoding="utf-8")
    (frames_dir / "frame_0000.png").write_bytes(b"fake")
    (frames_dir / "frame_0001.png").write_bytes(b"fake")

    generate_documentation(frames_dir, "demo.mp4")

    payload = json.loads((frames_dir / "manual" / "steps.json").read_text(encoding="utf-8"))
    assert payload["source"]["duration"] == 10.0
    assert payload["source"]["language"] == "en"
    assert payload["source"]["extraction_method"] == "smart_scene"


def test_regenerate_from_steps_does_not_require_frame_mapping(tmp_path):
    """Definition-of-Done: 'regenerate documentation from approved structured
    content without retranscribing media' — this must work with only
    steps.json + the frame assets on disk, no frame_mapping.json needed."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_0000.png").write_bytes(b"fake-png")

    manual_dir = tmp_path / "manual"
    ai_dir = tmp_path / "ai-package"
    source = DocumentationSource(
        video_name="demo.mp4", duration=10.0, language="en",
        extraction_method="smart_scene", generated_at="2026-01-01T00:00:00+00:00",
    )
    original_step = ProceduralStep(
        id="step-0001", order=1, title="Original", instruction="Original instruction",
        timestamp=1.5, frame_ref="frame_0000.png", transcript_ref="Original instruction",
        confidence="high",
    )
    write_manual(manual_dir, source, [original_step], frames_dir)
    write_ai_package(ai_dir, source, [original_step], frames_dir)

    # Human edits steps.json directly (e.g. via a review UI) — no re-transcription.
    steps_payload = json.loads((manual_dir / "steps.json").read_text(encoding="utf-8"))
    steps_payload["steps"][0]["instruction"] = "Edited by a human reviewer"
    (manual_dir / "steps.json").write_text(json.dumps(steps_payload), encoding="utf-8")

    result = regenerate_from_steps(manual_dir, ai_dir, frames_dir, "demo.mp4")

    assert result["step_count"] == 1
    manual_text = (manual_dir / "MANUAL.md").read_text(encoding="utf-8")
    assert "Edited by a human reviewer" in manual_text
    assert "Original instruction" not in manual_text


def test_source_metadata_survives_repeated_regeneration(tmp_path):
    """Regression: duration/language/extraction_method must not be lost or
    reset to defaults across multiple regenerate_from_steps calls in a row —
    the exact bug that motivated persisting `source` in steps.json."""
    frames_dir = tmp_path / "demo_Frames" / "demo"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_mapping.json").write_text(json.dumps(MAPPING_WITH_TRANSCRIPT), encoding="utf-8")
    (frames_dir / "frame_0000.png").write_bytes(b"fake")
    (frames_dir / "frame_0001.png").write_bytes(b"fake")
    manual_dir, ai_dir = frames_dir / "manual", frames_dir / "ai-package"

    generate_documentation(frames_dir, "demo.mp4")
    regenerate_from_steps(manual_dir, ai_dir, frames_dir, "demo.mp4")
    regenerate_from_steps(manual_dir, ai_dir, frames_dir, "demo.mp4")  # second regen — the bug only showed up here

    metadata = json.loads((manual_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["duration"] == 10.0
    assert metadata["language"] == "en"
    assert metadata["extraction_method"] == "smart_scene"


# ── Human review: edit / remove (§4.8) ───────────────────────────────────

@pytest.fixture
def generated_docs(tmp_path):
    frames_dir = tmp_path / "demo_Frames" / "demo"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_mapping.json").write_text(json.dumps(MAPPING_WITH_TRANSCRIPT), encoding="utf-8")
    (frames_dir / "frame_0000.png").write_bytes(b"fake")
    (frames_dir / "frame_0001.png").write_bytes(b"fake")
    generate_documentation(frames_dir, "demo.mp4")
    return frames_dir, frames_dir / "manual", frames_dir / "ai-package"


def test_update_step_edits_instruction_and_marks_reviewed(generated_docs):
    frames_dir, manual_dir, ai_dir = generated_docs

    updated = update_step(
        manual_dir, ai_dir, frames_dir, "step-0002",
        instruction="Confirmed manually: this opens the settings dialog.",
    )

    assert updated["instruction"] == "Confirmed manually: this opens the settings dialog."
    assert updated["reviewed"] is True

    manual_text = (manual_dir / "MANUAL.md").read_text(encoding="utf-8")
    assert "Confirmed manually" in manual_text
    ai_manifest = json.loads((ai_dir / "manifest.json").read_text(encoding="utf-8"))
    assert any(p["id"] == "step-0002" and p["reviewed"] for p in ai_manifest["procedures"])


def test_update_step_can_toggle_reviewed_without_editing_text(generated_docs):
    frames_dir, manual_dir, ai_dir = generated_docs
    updated = update_step(manual_dir, ai_dir, frames_dir, "step-0001", reviewed=True)
    assert updated["instruction"] == "Click the New Project button to get started."
    assert updated["reviewed"] is True


def test_update_step_unknown_id_raises(generated_docs):
    frames_dir, manual_dir, ai_dir = generated_docs
    with pytest.raises(KeyError):
        update_step(manual_dir, ai_dir, frames_dir, "step-9999", instruction="x")


def test_remove_step_deletes_and_renumbers(generated_docs):
    frames_dir, manual_dir, ai_dir = generated_docs

    result = remove_step(manual_dir, ai_dir, frames_dir, "step-0001")

    assert result["step_count"] == 1
    _, steps = load_steps(manual_dir)
    assert len(steps) == 1
    assert steps[0].id == "step-0002"
    assert steps[0].order == 1  # renumbered after the deletion

    manual_text = (manual_dir / "MANUAL.md").read_text(encoding="utf-8")
    assert "Click the New Project button" not in manual_text


def test_remove_step_unknown_id_raises(generated_docs):
    frames_dir, manual_dir, ai_dir = generated_docs
    with pytest.raises(KeyError):
        remove_step(manual_dir, ai_dir, frames_dir, "step-9999")
