"""End-to-end coverage for the video-to-documentation engine using a real
synthetic video (US-001 §4.6, §14 DoD: "Human manual generation works from
synthetic video fixture" / "AI-ready package generation works from the same
source").

Chains together the two pieces already unit-tested in isolation: real FFmpeg
keyframe extraction with real PTS (`test_keyframe_timestamp_provenance.py`),
and the transcript-alignment + documentation engine (`test_documentation_engine.py`).
No LLM/network involved — transcript segments are a synthetic stand-in for a
faster-whisper result, so this test has no external dependency beyond FFmpeg.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.integration.conftest import CUT_1_S, CUT_2_S, requires_ffmpeg
from transcript_pipeline.documentation.engine import generate_documentation
from transcript_pipeline.media.keyframe_extractor import KeyframeExtractor

# Stand-in for a faster-whisper segments list: dicts with start/end/text,
# one utterance placed right at each known scene cut.
FAKE_SEGMENTS = [
    {"start": CUT_1_S - 0.5, "end": CUT_1_S + 1.0, "text": "Now click File then New Project."},
    {"start": CUT_2_S - 0.5, "end": CUT_2_S + 1.0, "text": "Type the project name and press Enter."},
]


def _integrate_transcription(frames_dir, segments) -> None:
    """Minimal stand-in for processor._integrate_transcription_with_frames —
    same alignment rule (±2s window), so the fixture stays independent of
    faster-whisper while proving the real contract frame_mapping.json must
    satisfy for the documentation engine to ground its steps correctly."""
    mapping_path = frames_dir / "frame_mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))

    transcription_mapping = {}
    for frame in mapping["frames"]:
        ts = frame["timestamp"]
        nearby = [s["text"] for s in segments if abs(ts - s["start"]) <= 2 or abs(ts - s["end"]) <= 2 or s["start"] <= ts <= s["end"]]
        transcription_mapping[frame["frame_file"]] = {"timestamp": ts, "full_text": " ".join(nearby)}

    mapping["transcription_mapping"] = transcription_mapping
    mapping["transcription_summary"] = {"language": "en"}
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")


@requires_ffmpeg
def test_full_video_to_documentation_pipeline(tmp_path, monkeypatch, synthetic_cuts_video):
    monkeypatch.setenv("SMART_SCENE_COOLDOWN", "1.0")
    monkeypatch.setenv("SMART_SCENE_BLUR", "1")

    extractor = KeyframeExtractor(output_base_dir=str(tmp_path / "Frames"))
    monkeypatch.setattr(extractor, "_get_output_paths", lambda vp: (tmp_path / "Frames", vp.stem))

    result = extractor.extract_keyframes(synthetic_cuts_video, method="smart_scene", max_frames=10)
    assert result["success"], result["error"]

    frames_dir = Path(result["frames_dir"])
    _integrate_transcription(frames_dir, FAKE_SEGMENTS)

    summary = generate_documentation(frames_dir, "cuts.mp4")

    assert summary["step_count"] == result["frame_count"]
    assert summary["low_confidence_count"] == 0, "every real cut has an aligned transcript segment"

    manual_text = (frames_dir / "manual" / "MANUAL.md").read_text(encoding="utf-8")
    assert "click File then New Project" in manual_text
    assert "Type the project name" in manual_text

    ai_dir = frames_dir / "ai-package"
    manifest = json.loads((ai_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["procedures"]) == result["frame_count"]
    assert all(p["confidence"] == "high" for p in manifest["procedures"])

    chunks = [json.loads(line) for line in (ai_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    # Grounding check: every chunk's text must contain evidence pulled straight
    # from the synthetic transcript, never something outside it.
    known_phrases = ["click File then New Project", "Type the project name"]
    for chunk in chunks:
        assert any(phrase in chunk["text"] for phrase in known_phrases)
