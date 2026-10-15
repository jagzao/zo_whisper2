"""W9 integration: finalized Live Capture chunks flow through the existing
SimpleScanProcessor -> KeyframeExtractor -> Documentation V2 pipeline.

Real FFmpeg on the synthetic cuts video (no Whisper, no network): the crop
from the session manifest reaches keyframe extraction, a late session
transcript is consumed as loose untimed evidence for Docs V2, and an
audio-bearing chunk keeps the normal keyframe -> transcript -> docs flow.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.integration.conftest import requires_ffmpeg
from tests.integration.test_documentation_engine_pipeline import (
    FAKE_SEGMENTS,
    _integrate_transcription,
)
from transcript_pipeline.documentation.engine import generate_documentation
from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.service import CaptureService
from transcript_pipeline.media.keyframe_extractor import KeyframeExtractor
from transcript_pipeline.transcription import processor as processor_module

A = models.AudioAvailability


def _setup_finalized_chunk(tmp_path, monkeypatch, synthetic_cuts_video, *, audio_availability, crop=None):
    """Finalizes the synthetic video as chunk-000000 of a capture session on
    disk and returns (processor, chunk_path) wired to a redirected extractor."""
    monkeypatch.setenv("SMART_SCENE_COOLDOWN", "1.0")
    monkeypatch.setenv("SMART_SCENE_BLUR", "1")

    service = CaptureService(videos_root=tmp_path / "Videos")
    session = service.create_session("W9 integration", crop=crop, audio_availability=audio_availability)
    service.start_chunk(session.session_id, audio_availability=audio_availability)
    service.finalize_chunk(
        session.session_id, 0, synthetic_cuts_video.read_bytes(), audio_availability=audio_availability
    )

    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")
    assert chunk_path.is_file()

    extractor = KeyframeExtractor(output_base_dir=str(tmp_path / "Frames"))
    monkeypatch.setattr(extractor, "_get_output_paths", lambda vp: (tmp_path / "Frames", vp.stem))

    processor = processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)
    processor.keyframe_extractor = extractor
    processor.require_keyframes_for_videos = True
    processor.stats = {"frames_extracted": 0}
    return processor, chunk_path


@requires_ffmpeg
def test_capture_crop_flows_into_keyframe_extraction(tmp_path, monkeypatch, synthetic_cuts_video):
    processor, chunk_path = _setup_finalized_chunk(
        tmp_path, monkeypatch, synthetic_cuts_video,
        audio_availability=A.MISSING, crop=models.CropRegion(0.0, 0.0, 0.5, 0.5),
    )

    ctx = processor._capture_context(chunk_path)
    assert ctx is not None
    assert ctx.crop is not None and ctx.crop.width == 0.5

    frame_info = processor._ensure_keyframes(chunk_path, crop=ctx.crop)
    assert frame_info

    frames_dir = Path(frame_info["frames_dir"])
    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    assert "crop" in mapping
    assert mapping["crop"]["applied"] is True

    originals_dir = frames_dir / "originals"
    assert originals_dir.is_dir()
    assert len(list(originals_dir.glob("frame_*.png"))) == frame_info["frame_count"]


@requires_ffmpeg
def test_late_session_transcript_is_loose_untimed_evidence(tmp_path, monkeypatch, synthetic_cuts_video):
    processor, chunk_path = _setup_finalized_chunk(
        tmp_path, monkeypatch, synthetic_cuts_video, audio_availability=A.MISSING
    )
    service = CaptureService(videos_root=tmp_path / "Videos")
    ctx = processor._capture_context(chunk_path)
    assert ctx is not None
    session_id = ctx.session_id
    service.associate_transcript(session_id, "late session text about the recording", language="es")
    ctx = processor._capture_context(chunk_path)
    assert ctx.transcript is not None and ctx.transcript.alignment == "loose"

    frame_info = processor._ensure_keyframes(chunk_path, crop=ctx.crop)
    assert frame_info
    frames_dir = Path(frame_info["frames_dir"])

    processor._integrate_capture_context(frame_info, ctx)

    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    session_entry = mapping["transcription_summary"]["session_transcript"]
    assert session_entry["alignment"] == "loose"
    assert session_entry["text"] == "late session text about the recording"

    summary = generate_documentation(frames_dir, "chunk-000000.webm")
    assert summary["step_count"] >= 1

    evidence_path = frames_dir / "evidence" / "evidence.jsonl"
    assert evidence_path.exists()
    items = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    loose = [i for i in items if i.get("sourceProvenance") == "session_transcript.loose"]
    assert loose
    assert all(i["untimed"] is True for i in loose)
    assert any("late session text" in (i.get("transcriptExcerpt") or "") for i in loose)

    # The loose transcript never becomes per-frame alignment: no frame carries
    # transcript text and no step is grounded on a fabricated transcript.
    assert not any(
        (entry.get("full_text") or "").strip()
        for entry in mapping.get("transcription_mapping", {}).values()
    )
    steps_payload = json.loads((frames_dir / "manual" / "steps.json").read_text(encoding="utf-8"))
    for step in steps_payload["steps"]:
        assert not (step.get("transcript_ref") or "").strip()
        assert step["evidence_source"] not in ("transcript", "transcript_ocr")


@requires_ffmpeg
def test_finalized_chunk_with_audio_flows_to_docs(tmp_path, monkeypatch, synthetic_cuts_video):
    processor, chunk_path = _setup_finalized_chunk(
        tmp_path, monkeypatch, synthetic_cuts_video, audio_availability=A.AVAILABLE
    )

    ctx = processor._capture_context(chunk_path)
    assert ctx is not None
    assert ctx.audio_availability is A.AVAILABLE

    frame_info = processor._ensure_keyframes(chunk_path, crop=ctx.crop)
    assert frame_info
    frames_dir = Path(frame_info["frames_dir"])

    _integrate_transcription(frames_dir, FAKE_SEGMENTS)

    summary = generate_documentation(frames_dir, "chunk-000000.webm")
    assert summary["step_count"] == frame_info["frame_count"]
    assert summary["low_confidence_count"] == 0

    manual_text = (frames_dir / "manual" / "MANUAL.md").read_text(encoding="utf-8")
    assert "click File then New Project" in manual_text
    assert "Type the project name" in manual_text
