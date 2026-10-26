from __future__ import annotations

import json

from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2


class _NeverSynthesize:
    def synthesize(self, *args, **kwargs):
        raise AssertionError("incomplete source must not reach synthesis")


def test_partial_transcript_writes_diagnostic_and_blocks_ready_manual(tmp_path):
    frames_dir = tmp_path / "source_Frames"
    frames_dir.mkdir()
    (frames_dir / "frame_mapping.json").write_text(json.dumps({
        "video_info": {"name": "source.mp4", "duration": 1000},
        "transcription_summary": {"full_transcription": "partial speech"},
        "frames": [],
        "transcription_mapping": {},
    }), encoding="utf-8")
    (tmp_path / "source_segments.json").write_text(json.dumps({
        "segments": [{"start": 10, "end": 600, "text": "partial speech"}],
    }), encoding="utf-8")

    result = generate_documentation_v2(
        frames_dir,
        "source.mp4",
        project_config={"documentation": {"mode": "KT_SESSION", "synthesis_enabled": True}},
        synthesis_service=_NeverSynthesize(),
    )

    assert result["status"] == "SOURCE_INCOMPLETE"
    assert result["transcript_quality"]["transcript_state"] == "PARTIAL"
    assert (frames_dir / "manual" / "diagnostic-report.json").exists()
    assert not (frames_dir / "manual" / "MANUAL.md").exists()
