"""Black interval and border crop behavior against small synthetic FFmpeg clips."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from transcript_pipeline.live_capture.black_video import (
    crop_black_borders,
    detect_black_borders,
    detect_black_intervals,
    trim_black_intervals,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not available")


def _clip(path: Path, segments: list[tuple[str, float]], *, audio: bool = False) -> None:
    command = ["ffmpeg", "-hide_banner", "-y"]
    for color, duration in segments:
        command += ["-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=10:d={duration}"]
    concat_inputs = "".join(f"[{index}:v]" for index in range(len(segments)))
    total_duration = sum(duration for _, duration in segments)
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={total_duration}"]
    command += ["-filter_complex", f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[vout]", "-map", "[vout]"]
    if audio:
        command += ["-map", f"{len(segments)}:a:0", "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr[-2000:]


def _border_clip(path: Path, *, kind: str) -> None:
    if kind == "letterbox":
        vf = "drawbox=x=0:y=20:w=160:h=50:color=white:t=fill"
    else:
        vf = "drawbox=x=45:y=0:w=70:h=90:color=white:t=fill"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=4", "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]


def _duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@requires_ffmpeg
def test_fully_black_clip_is_one_temporal_interval(tmp_path):
    source = tmp_path / "full-black.mp4"
    _clip(source, [("black", 4)])
    result = detect_black_intervals(source)
    assert len(result["intervals"]) == 1
    assert result["intervals"][0]["start"] == pytest.approx(0, abs=0.2)
    assert result["intervals"][0]["end"] == pytest.approx(4, abs=0.3)
    assert result["status"] == "READY"


@requires_ffmpeg
def test_short_dark_transition_is_not_removed(tmp_path):
    source = tmp_path / "transition.mp4"
    _clip(source, [("white", 2), ("black", 1), ("white", 2)])
    assert detect_black_intervals(source)["intervals"] == []


@requires_ffmpeg
def test_multiple_intervals_and_start_end_black_are_detected(tmp_path):
    source = tmp_path / "multi.mp4"
    _clip(source, [("black", 2), ("blue", 2), ("black", 3), ("red", 2), ("black", 2)])
    intervals = detect_black_intervals(source)["intervals"]
    assert len(intervals) == 3
    assert intervals[0]["start"] == pytest.approx(0, abs=0.2)
    assert intervals[-1]["end"] == pytest.approx(11, abs=0.3)


@requires_ffmpeg
def test_naturally_dark_valid_footage_is_not_black_at_default_threshold(tmp_path):
    source = tmp_path / "dark-scene.mp4"
    _clip(source, [("0x202020", 4)])
    assert detect_black_intervals(source)["intervals"] == []


@requires_ffmpeg
@pytest.mark.parametrize("kind", ["letterbox", "pillarbox"])
def test_persistent_black_borders_detect_and_crop_independently(tmp_path, kind):
    source = tmp_path / f"{kind}.mp4"
    _border_clip(source, kind=kind)
    scan = detect_black_borders(source)
    assert scan["status"] == "READY"
    assert scan["crop"] is not None
    assert scan["crop"]["width"] < scan["frame"]["width"] or scan["crop"]["height"] < scan["frame"]["height"]
    assert detect_black_intervals(source)["intervals"] == []
    original_hash = _sha(source)
    output = crop_black_borders(source, scan["crop"])
    assert output.exists()
    assert _sha(source) == original_hash
    assert _duration(output) == pytest.approx(_duration(source), abs=0.3)


@requires_ffmpeg
def test_temporal_cut_preserves_audio_duration_and_original(tmp_path):
    source = tmp_path / "with-audio.mp4"
    _clip(source, [("blue", 2), ("black", 3), ("red", 2), ("black", 2), ("green", 2)], audio=True)
    scan = detect_black_intervals(source)
    original_hash = _sha(source)
    output = trim_black_intervals(source, scan["intervals"])
    assert output.exists()
    assert _sha(source) == original_hash
    assert _duration(output) == pytest.approx(_duration(source) - scan["removed_seconds"], abs=0.5)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(output)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    types = [stream["codec_type"] for stream in json.loads(probe.stdout)["streams"]]
    assert types.count("video") == 1
    assert "audio" in types


def test_low_confidence_sensitive_scan_requires_review(monkeypatch, tmp_path):
    source = tmp_path / "unused.mp4"

    def probe(_path):
        return {"duration": 10.0, "streams": [{"codec_type": "video"}]}

    def ffmpeg(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, "", "black_start:2 black_end:5 black_duration:3")

    monkeypatch.setattr("transcript_pipeline.live_capture.black_video._probe", probe)
    monkeypatch.setattr("transcript_pipeline.live_capture.black_video.subprocess.run", ffmpeg)
    result = detect_black_intervals(source, darkness_threshold=0.16)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["confidence"] == "low"


def test_detection_parameters_are_validated(tmp_path):
    with pytest.raises(ValueError):
        detect_black_intervals(tmp_path / "missing.mp4", darkness_threshold=0.5)
    with pytest.raises(ValueError):
        detect_black_intervals(tmp_path / "missing.mp4", minimum_duration_seconds=0.1)
