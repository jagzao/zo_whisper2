"""Shared fixtures for integration tests that need a real, tiny synthetic
video with known, hard scene cuts (real FFmpeg, no mocks)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

requires_ffmpeg = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not available")

# Two hard cuts, both known exactly: t=2.0s and t=4.0s.
CUT_1_S = 2.0
CUT_2_S = 4.0


def make_synthetic_cuts_video(path: Path) -> None:
    """6s, 64x64, 10fps video: 2s testsrc + 2s smptebars + 2s rgbtestsrc.

    Uses patterned/textured lavfi sources rather than flat solid colors: a
    flat-color frame is a degenerate case for perceptual-hash dedup (every
    pixel equals the mean, so average_hash collapses to the same bit pattern
    regardless of hue), which would make a dedup phase falsely merge two
    genuinely distinct scenes.
    """
    cmd = [
        "ffmpeg",
        "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=2",
        "-f", "lavfi", "-i", "smptebars=size=64x64:rate=10:duration=2",
        "-f", "lavfi", "-i", "rgbtestsrc=size=64x64:rate=10:duration=2",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]",
        "-pix_fmt", "yuv420p",
        "-y", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"fixture generation failed: {result.stderr}"


@pytest.fixture
def synthetic_cuts_video(tmp_path) -> Path:
    video_path = tmp_path / "cuts.mp4"
    make_synthetic_cuts_video(video_path)
    return video_path
