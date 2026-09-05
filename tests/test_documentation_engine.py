"""Unit coverage for the video-to-documentation engine (US-001 §4.6/§4.7).

Pure dict/JSON-driven — no FFmpeg, no real video, no LLM. Exercises the
confidence rules, manifest/steps schema, and the "regenerate without
retranscribing" contract directly against `frame_mapping.json`-shaped input.
"""
from __future__ import annotations

import json

import pytest

from transcript_pipeline.documentation.engine import (
    build_steps,
    generate_documentation,
    regenerate_from_steps,
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
    assert steps[0].transcript_ref == steps[0].instruction


def test_build_steps_flags_frame_without_transcript_as_low_confidence():
    steps = build_steps(MAPPING_WITH_TRANSCRIPT)

    empty_step = steps[1]
    assert empty_step.confidence == "low"
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
    steps_payload["source"] = {"duration": 10.0, "language": "en", "extraction_method": "smart_scene"}
    (manual_dir / "steps.json").write_text(json.dumps(steps_payload), encoding="utf-8")

    result = regenerate_from_steps(manual_dir, ai_dir, frames_dir, "demo.mp4")

    assert result["step_count"] == 1
    manual_text = (manual_dir / "MANUAL.md").read_text(encoding="utf-8")
    assert "Edited by a human reviewer" in manual_text
    assert "Original instruction" not in manual_text
