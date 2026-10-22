import json
import subprocess

from transcript_pipeline.media.keyframe_extractor import KeyframeExtractor


def test_video_duration_uses_ffprobe_metadata_without_decoding(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"format": {"duration": "123.5"}, "streams": []}))

    monkeypatch.setattr("transcript_pipeline.media.keyframe_extractor.subprocess.run", run)
    extractor = KeyframeExtractor(output_base_dir=str(tmp_path / "frames"))

    assert extractor._get_video_duration(tmp_path / "video.mp4") == 123.5
    command, kwargs = calls[0]
    assert command[0] == "ffprobe"
    assert "-show_entries" in command
    assert "-f" not in command
    assert kwargs["timeout"] == 15


def test_video_duration_falls_back_to_stream_metadata(tmp_path, monkeypatch):
    def run(command, **kwargs):
        payload = {"streams": [{"duration": "10.0"}, {"duration": "12.5"}]}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload))

    monkeypatch.setattr("transcript_pipeline.media.keyframe_extractor.subprocess.run", run)
    extractor = KeyframeExtractor(output_base_dir=str(tmp_path / "frames"))

    assert extractor._get_video_duration(tmp_path / "video.mp4") == 12.5
