from __future__ import annotations

import json

from transcript_pipeline.documentation.evidence import build_evidence_timeline
from transcript_pipeline.transcription import processor as processor_module


class _Tracker:
    def __init__(self, events):
        self.events = events

    def is_file_processed(self, path):
        return False

    def mark_as_processed(self, path, status):
        self.events.append(("tracker", status))


def test_process_saves_segments_before_docs_and_docs_failure_is_nonfatal(tmp_path, monkeypatch):
    events = []
    frames_dir = tmp_path / "output" / "project" / "demo_Frames" / "demo"
    frames_dir.mkdir(parents=True)
    audio_path = tmp_path / "videos" / "project" / "demo.mp4"
    segments = [{"id": str(i), "start": i * 5, "end": i * 5 + 2, "text": f"speech {i}"} for i in range(10)]
    instance = processor_module.SimpleScanProcessor.__new__(processor_module.SimpleScanProcessor)
    instance.tracker = _Tracker(events)
    instance.stats = {"already_processed": 0, "tutorials_processed": 0, "errors": 0, "processed": 0}
    instance.transcribe_file = lambda path: {
        "text": " ".join(segment["text"] for segment in segments),
        "segments": segments,
        "frame_info": {"frames_dir": str(frames_dir)},
    }

    def integrate(result, frame_info):
        events.append("integrate")
        mapping = {
            "video_info": {"name": "demo.mp4", "duration": 60},
            "transcription_summary": {"full_transcription": result["text"]},
            "frames": [{"frame_file": "f.png", "timestamp": 5}],
            "transcription_mapping": {"f.png": {"full_text": "sparse frame text"}},
        }
        (frames_dir / "frame_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")

    def save(path, result):
        events.append("save")
        segment_path = frames_dir.parent.parent / "demo_segments.json"
        segment_path.write_text(json.dumps({"segments": result["segments"]}), encoding="utf-8")

    def fail_documentation(path, video_name, project_config=None):
        mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
        timeline = build_evidence_timeline(mapping, source_media=video_name, frames_dir=frames_dir)
        recovered = [item.transcript_excerpt for item in timeline.items if item.transcript_excerpt]
        assert recovered == [segment["text"] for segment in segments]
        events.append("docs")
        raise RuntimeError("synthetic documentation failure")

    instance._integrate_transcription_with_frames = integrate
    instance.save_transcription = save
    monkeypatch.setattr(processor_module, "TUTORIAL_FEATURES_AVAILABLE", True)
    monkeypatch.setattr(processor_module, "is_tutorial_video", lambda path: False)
    monkeypatch.setattr(processor_module, "generate_documentation", fail_documentation)

    assert instance.process_file(audio_path) is True
    assert events == ["integrate", "save", "docs", ("tracker", "completed")]
    saved_path = frames_dir.parent.parent / "demo_segments.json"
    assert json.loads(saved_path.read_text(encoding="utf-8"))["segments"] == segments
    assert instance.stats["processed"] == 1
    assert instance.stats["errors"] == 0
