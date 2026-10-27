"""W9: finalized Live Capture media wired into the EXISTING SimpleScan /
Documentation V2 flow.

Covers the bridge module (`live_capture.integration`) and its processor
hooks: capture media is recognized (no duplicate pipeline), AUDIO_MISSING
chunks are documented visually without ever loading Whisper, the session
CropRegion reaches keyframe extraction, a late session transcript enriches
docs as ONE untimed block (never fabricated per-frame timing, never
overwriting a timed Whisper transcript), and a processed frames dir
regenerates through the existing Docs V2 regeneration entry point.

Synthetic fixtures only — no real media, no ffmpeg, no tesseract, no
network. Sessions are built on disk through the real CaptureService so the
manifest layout under test is exactly what production writes.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tests.fixtures.documentation_v2 import materialize_frames_dir
from transcript_pipeline.documentation.evidence import (
    FIDELITY_UNTIMED_FULL_TRANSCRIPT,
    build_evidence_timeline,
)
from transcript_pipeline.live_capture import models
from transcript_pipeline.live_capture.errors import SessionNotFoundError
from transcript_pipeline.live_capture.integration import (
    CaptureContext,
    apply_capture_context,
    context_from_session,
    load_session_capture_context,
    regenerate_capture_documentation,
    resolve_capture_context,
)
from transcript_pipeline.live_capture.service import CaptureService
from transcript_pipeline.transcription import processor as processor_module

A = models.AudioAvailability


# ── helpers ─────────────────────────────────────────────────────────


def _service(tmp_path) -> CaptureService:
    return CaptureService(videos_root=tmp_path / "Videos")


def _finalized_chunk(service: CaptureService, *, audio=A.MISSING, crop=None, title="W9") -> models.Session:
    session = service.create_session(title, crop=crop, audio_availability=audio)
    service.start_chunk(session.session_id, audio_availability=audio)
    service.finalize_chunk(
        session.session_id, 0, b"\x00\x01\x02", media_extension=".webm", audio_availability=audio
    )
    return session


class _Tracker:
    def __init__(self, events):
        self.events = events

    def is_file_processed(self, path):
        return False

    def mark_as_processed(self, path, status):
        self.events.append(("tracker", status))


class _RecordingExtractor:
    """Fake KeyframeExtractor: records kwargs, reports success, touches no media."""

    def __init__(self, frames_dir: Path):
        self.frames_dir = frames_dir
        self.calls = []

    def extract_keyframes(self, video_path, method="iframe", max_frames=None, quality=2, crop=None):
        self.calls.append({"method": method, "crop": crop})
        return {
            "success": True,
            "frames_dir": str(self.frames_dir),
            "frame_count": 1,
            "video_duration": 60.0,
            "method": method,
            "processing_time": 0.0,
        }


def _synthetic_frames_dir(tmp_path: Path) -> Path:
    frames_dir = tmp_path / "synthetic_frames"
    frames_dir.mkdir()
    mapping = {
        "video_info": {"name": "chunk-000000.webm"},
        "frames": [{"frame_file": "frame_0000.png", "timestamp": 1.0}],
    }
    (frames_dir / "frame_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    Image.new("RGB", (8, 8), (10, 20, 30)).save(frames_dir / "frame_0000.png")
    return frames_dir


def _read_evidence_items(frames_dir: Path) -> list[dict]:
    lines = (frames_dir / "evidence" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


# ── (a) resolve_capture_context ─────────────────────────────────────


def test_resolve_capture_context_for_real_chunk(tmp_path):
    service = _service(tmp_path)
    region = models.CropRegion(0.0, 0.0, 0.5, 1.0)
    session = _finalized_chunk(service, crop=region)
    service.associate_transcript(session.session_id, "late transcript", language="es")

    chunk_path = tmp_path / "Videos" / "live_capture" / session.session_id / "chunks" / "chunk-000000.webm"
    assert chunk_path == service.store.chunk_media_path(session.session_id, 0, ".webm")
    assert chunk_path.is_file()

    context = resolve_capture_context(chunk_path, videos_root=tmp_path / "Videos")

    assert isinstance(context, CaptureContext)
    assert context.session_id == session.session_id
    assert context.chunk_index == 0
    assert context.crop == region
    assert context.transcript is not None
    assert context.transcript.text == "late transcript"
    assert context.transcript.alignment == "loose"
    assert context.audio_missing is True
    assert context.has_loose_transcript is True
    assert context == context_from_session(service.get_session(session.session_id), chunk_index=0)


def test_resolve_returns_none_for_legacy_path(tmp_path):
    legacy = tmp_path / "Videos" / "project" / "demo.mp4"
    assert resolve_capture_context(legacy, videos_root=tmp_path / "Videos") is None


def test_resolve_returns_none_for_capture_shape_without_manifest(tmp_path):
    chunks_dir = tmp_path / "Videos" / "live_capture" / "sess-absent" / "chunks"
    chunks_dir.mkdir(parents=True)
    chunk = chunks_dir / "chunk-000000.webm"
    chunk.write_bytes(b"\x00\x00")
    assert resolve_capture_context(chunk, videos_root=tmp_path / "Videos") is None


def test_load_session_capture_context_propagates_typed_errors(tmp_path):
    with pytest.raises(SessionNotFoundError):
        load_session_capture_context("sess-doesnotexist", videos_root=tmp_path / "Videos")


# ── (b) apply_capture_context ───────────────────────────────────────


def _context_with_transcript(tmp_path, *, text="transcripcion tardia", language="es"):
    service = _service(tmp_path)
    session = _finalized_chunk(service, crop=models.CropRegion(0.1, 0.0, 0.5, 1.0))
    service.associate_transcript(session.session_id, text, language=language)
    context = load_session_capture_context(session.session_id, videos_root=tmp_path / "Videos")
    assert context.has_loose_transcript
    return session, context


def test_apply_capture_context_injects_one_loose_transcript(tmp_path):
    session, context = _context_with_transcript(tmp_path)
    mapping = {
        "video_info": {"name": "chunk-000000.webm"},
        "frames": [{"frame_file": "frame_0000.png", "timestamp": 1.0}],
    }

    status = apply_capture_context(mapping, context)

    assert status["sessionId"] == session.session_id
    assert status["audioMissing"] is True
    assert status["transcriptApplied"] is True
    assert status["alignment"] == "loose"

    summary = mapping["transcription_summary"]
    assert summary["full_transcription"] == "transcripcion tardia"
    assert summary["language"] == "es"
    assert summary["alignment"] == models.TRANSCRIPT_ALIGNMENT_LOOSE
    assert summary["source"] == "live_capture_session"

    assert mapping["video_info"]["capture"]["sessionId"] == session.session_id
    # One untimed block only: no per-frame mapping created, no timing keys added.
    assert "transcription_mapping" not in mapping
    for forbidden in ("start", "end", "segments", "timestamp", "timestamps"):
        assert forbidden not in summary


@pytest.mark.parametrize(
    "existing",
    [
        {"transcription_summary": {"full_transcription": "whisper timed text"}, "transcription_mapping": {}},
        {"transcription_summary": {}, "transcription_mapping": {"frame_0000.png": {"full_text": "whisper"}}},
        {
            "transcription_summary": {"full_transcription": "   "},
            "transcription_mapping": {"frame_0000.png": {"full_text": "whisper timed"}},
        },
    ],
)
def test_apply_capture_context_never_overwrites_timed_transcript(tmp_path, existing):
    session, context = _context_with_transcript(tmp_path, text="late", language="es")
    mapping = {"video_info": {}, "frames": [], **existing}

    status = apply_capture_context(mapping, context)

    assert status["transcriptApplied"] is False
    assert status["alignment"] is None
    summary = mapping["transcription_summary"]
    assert str(summary.get("full_transcription", "") or "").strip() != "late"
    assert summary.get("source") != "live_capture_session"
    for entry in (mapping.get("transcription_mapping") or {}).values():
        assert entry["full_text"] != "late"


def test_apply_capture_context_without_transcript_records_provenance_only(tmp_path):
    service = _service(tmp_path)
    session = _finalized_chunk(service, crop=models.CropRegion(0.0, 0.0, 0.5, 1.0), audio=A.AVAILABLE)
    context = load_session_capture_context(session.session_id, videos_root=tmp_path / "Videos")
    assert context.audio_missing is False

    mapping = {"video_info": {}, "frames": []}
    status = apply_capture_context(mapping, context)

    assert status["transcriptApplied"] is False
    assert "full_transcription" not in mapping["transcription_summary"]
    assert mapping["transcription_summary"]["language"] == "unknown"


def test_provenance_records_session_crop_and_availability(tmp_path):
    session, context = _context_with_transcript(tmp_path)
    provenance = context.provenance()

    assert provenance["source"] == "live_capture"
    assert provenance["sessionId"] == session.session_id
    assert provenance["chunkIndex"] is None  # session-level context
    assert provenance["crop"] == {"x": 0.1, "y": 0.0, "width": 0.5, "height": 1.0}
    assert provenance["audioAvailability"] == "MISSING"
    assert provenance["transcriptAlignment"] == "loose"
    assert json.dumps(provenance)  # JSON-safe


# ── (c) no-audio processor path (AC2/AC3) ───────────────────────────


def _bare_processor(tmp_path) -> processor_module.SimpleScanProcessor:
    instance = processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)
    instance.videos_base = tmp_path / "Videos"
    instance.audio_base = tmp_path / "audio"
    instance.transcriptions_base = tmp_path / "transcriptions"
    instance.transcriptions_base.mkdir(exist_ok=True)
    instance._language_detector = SimpleNamespace(detect=lambda *args, **kwargs: None)
    instance._projects_config = []
    return instance


def test_audio_missing_chunk_transcribes_without_whisper_and_forwards_crop(tmp_path):
    service = _service(tmp_path)
    region = models.CropRegion(0.25, 0.25, 0.5, 0.5)
    session = _finalized_chunk(service, crop=region, audio=A.MISSING)
    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")

    frames_dir = _synthetic_frames_dir(tmp_path)
    recorded = {}

    def fake_ensure_keyframes(video_path, crop=None):
        recorded["crop"] = crop
        return {"frames_dir": str(frames_dir), "frame_count": 1, "video_duration": 42.0, "method": "stub"}

    instance = _bare_processor(tmp_path)
    instance._ensure_keyframes = fake_ensure_keyframes
    model_calls = []

    def _ensure_model_must_not_run():
        model_calls.append(1)
        raise AssertionError("Whisper must never load for an AUDIO_MISSING capture chunk")

    instance._ensure_model = _ensure_model_must_not_run

    result = instance.transcribe_file(chunk_path)

    assert result["text"] == ""
    assert result["segments"] == []
    assert result["language"] is None
    assert result["capture"].session_id == session.session_id
    assert result["capture"].audio_missing is True
    assert result["frame_info"]["frames_dir"] == str(frames_dir)
    assert recorded["crop"] == region
    assert model_calls == []


def test_ensure_keyframes_forwards_crop_to_extractor(tmp_path):
    service = _service(tmp_path)
    region = models.CropRegion(0.25, 0.25, 0.5, 0.5)
    session = _finalized_chunk(service, crop=region, audio=A.MISSING)
    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")

    frames_dir = _synthetic_frames_dir(tmp_path)
    extractor = _RecordingExtractor(frames_dir)
    instance = processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)
    instance.keyframe_extractor = extractor
    instance.require_keyframes_for_videos = False
    instance.stats = {"frames_extracted": 0}

    frame_info = instance._ensure_keyframes(chunk_path, crop=region)

    assert frame_info is not None
    assert frame_info["frames_dir"] == str(frames_dir)
    assert extractor.calls, "extractor must have been invoked"
    assert all(call["crop"] is region for call in extractor.calls)


# ── (d) video-to-docs integration through process_file (AC1) ────────


def test_process_file_wires_capture_chunk_into_existing_docs_flow(tmp_path, monkeypatch):
    service = _service(tmp_path)
    region = models.CropRegion(0.1, 0.1, 0.8, 0.8)
    session = _finalized_chunk(service, crop=region, audio=A.MISSING)
    service.associate_transcript(session.session_id, "late session transcript", language="es")
    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")

    context = resolve_capture_context(chunk_path, videos_root=tmp_path / "Videos")
    assert context is not None and context.audio_missing

    frames_dir = materialize_frames_dir("reference_meeting", tmp_path / "frames-root")

    engine_module = importlib.import_module("transcript_pipeline.documentation.engine")
    pipeline_v2 = importlib.import_module("transcript_pipeline.documentation.pipeline_v2")
    synthesis = importlib.import_module("transcript_pipeline.documentation.synthesis")
    monkeypatch.setattr(processor_module, "generate_documentation", engine_module.generate_documentation)
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    monkeypatch.setattr(processor_module, "is_tutorial_video", lambda path: False)
    # AC5: the real engine runs, but no tesseract / vision LLM / synthesis network.
    monkeypatch.setattr(engine_module, "_ocr_text", lambda frame_path: "")
    monkeypatch.setattr(engine_module, "_vision_description", lambda frame_path, project_config: None)
    monkeypatch.setattr(pipeline_v2, "default_synthesis_service", lambda: synthesis.SynthesisService(None, None))
    monkeypatch.setattr(
        processor_module,
        "_ai_service",
        SimpleNamespace(describe_frames_for_tutorial=lambda *args, **kwargs: {}),
    )

    events = []
    instance = _bare_processor(tmp_path)
    instance.tracker = _Tracker(events)
    instance.stats = {"already_processed": 0, "tutorials_processed": 0, "errors": 0, "processed": 0}
    instance.transcribe_file = lambda path: {
        "text": "",
        "segments": [],
        "language": "unknown",
        "duration": 0.0,
        "processing_time": 0.0,
        "project": None,
        "frame_info": {"frames_dir": str(frames_dir)},
        "capture": context,
    }

    assert instance.process_file(chunk_path) is True
    assert events == [("tracker", "completed")]

    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    assert mapping["video_info"]["capture"]["sessionId"] == session.session_id
    assert mapping["transcription_summary"]["session_transcript"]["text"] == "late session transcript"
    assert mapping["transcription_summary"]["session_transcript"]["alignment"] == "loose"

    evidence_dir = frames_dir / "evidence"
    assert (evidence_dir / "evidence.jsonl").is_file()
    assert (evidence_dir / "EVIDENCE_TIMELINE.md").is_file()
    assert (evidence_dir / "review-queue.json").is_file()
    assert (frames_dir / "manual" / "steps.json").is_file()
    diagnostic = json.loads((frames_dir / "manual" / "diagnostic-report.json").read_text(encoding="utf-8"))
    assert diagnostic["status"] == "SOURCE_INCOMPLETE"
    assert not (frames_dir / "manual" / "MANUAL.md").exists()
    assert not (frames_dir / "ai-package").exists()

    items = _read_evidence_items(frames_dir)
    transcript_items = [item for item in items if item["transcriptExcerpt"]]
    assert len(transcript_items) == 1
    assert transcript_items[0]["untimed"] is True
    assert transcript_items[0]["transcriptExcerpt"] == "late session transcript"
    assert transcript_items[0]["sourceProvenance"] == "session_transcript.loose"


# ── (e) late-transcript regeneration (AC4) ──────────────────────────


def test_regenerate_capture_documentation_uses_late_transcript_once_and_is_idempotent(tmp_path):
    service = _service(tmp_path)
    session = _finalized_chunk(service, audio=A.MISSING, title="late transcript")
    late_text = "transcripcion completa suministrada tarde"
    service.associate_transcript(session.session_id, late_text, language="es")

    frames_dir = materialize_frames_dir("reference_meeting", tmp_path / "frames-root")
    # This case exercises the late, loose capture transcript. The fixture
    # also writes a sibling timestamped transcript, which would take priority.
    (frames_dir.parent / "acme_reference_overview_segments.json").unlink()
    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    mapping.pop("transcription_mapping", None)
    mapping["transcription_summary"] = {"language": "en"}
    (frames_dir / "frame_mapping.json").write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result = regenerate_capture_documentation(
        frames_dir, session.session_id, videos_root=tmp_path / "Videos", evidence_only=True
    )

    assert result["status"] == "SOURCE_INCOMPLETE"
    assert result["capture"]["transcriptApplied"] is True
    assert result["capture"]["sessionId"] == session.session_id
    assert result["evidence"]["fidelity"] == FIDELITY_UNTIMED_FULL_TRANSCRIPT

    items = _read_evidence_items(frames_dir)
    untimed = [item for item in items if item["untimed"]]
    assert len(untimed) == 1
    assert untimed[0]["transcriptExcerpt"] == late_text
    assert untimed[0]["timestampStart"] == 0.0
    assert untimed[0]["timestampEnd"] == 600.0  # honest full span, no fabricated per-second timing
    assert [item for item in items if item["transcriptExcerpt"]] == untimed

    mapping_after = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    assert "transcription_mapping" not in mapping_after  # the loose transcript never becomes per-frame entries
    summary = mapping_after["transcription_summary"]
    for forbidden in ("start", "end", "segments", "timestamp", "timestamps"):
        assert forbidden not in summary

    timeline = build_evidence_timeline(
        mapping_after, source_media="acme_reference_overview.mp4", frames_dir=frames_dir
    )
    assert timeline.fidelity == FIDELITY_UNTIMED_FULL_TRANSCRIPT
    assert sum(1 for item in timeline.items if item.untimed) == 1

    result_again = regenerate_capture_documentation(
        frames_dir, session.session_id, videos_root=tmp_path / "Videos", evidence_only=True
    )
    assert result_again["capture"]["transcriptApplied"] is False
    items_again = _read_evidence_items(frames_dir)
    assert len(items_again) == len(items)
    assert len([item for item in items_again if item["untimed"]]) == 1


def test_accepted_processing_cancel_stops_before_documentation(tmp_path):
    service = _service(tmp_path)
    session = _finalized_chunk(service, audio=A.MISSING, title="cancel during processing")
    service.mark_processing(session.session_id, 0)
    chunk_path = service.store.chunk_media_path(session.session_id, 0, ".webm")
    context = resolve_capture_context(chunk_path, videos_root=tmp_path / "Videos")
    events = []
    instance = _bare_processor(tmp_path)
    instance.tracker = _Tracker(events)
    instance.stats = {"already_processed": 0, "tutorials_processed": 0, "errors": 0, "processed": 0}

    def request_cancel_during_transcription(_path):
        service.cancel_processing(session.session_id, 0)
        return {
            "text": "",
            "segments": [],
            "language": "unknown",
            "duration": 1.0,
            "processing_time": 0.0,
            "project": None,
            "frame_info": {"frames_dir": str(tmp_path / "not-generated")},
            "capture": context,
        }

    instance.transcribe_file = request_cancel_during_transcription
    instance._integrate_transcription_with_frames = lambda *args: pytest.fail("cancelled work advanced to docs")

    assert instance.process_file(chunk_path) is False
    assert events == []
    assert service.get_session(session.session_id).get_chunk(0).state is models.ChunkState.CANCELLED
