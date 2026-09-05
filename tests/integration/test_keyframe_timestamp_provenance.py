"""Regression coverage for the keyframe timestamp release blocker (US-001 §4.3).

Anchor bug (pre-fix): `_create_frame_mapping` estimated a uniform timestamp
(`duration / frame_count`) for the `scene` and `smart_scene` extraction methods,
discarding the real PTS FFmpeg had already detected during scene-change
detection. Any documentation/evidence built on top of `frame_mapping.json`
would then cite the wrong moment in the source video.

These tests build a tiny synthetic video with two hard, known color cuts
(black -> white at t=2.0s, white -> red at t=4.0s) using FFmpeg's `lavfi`
source + `concat` filter, run the real extractor (real FFmpeg, no mocks),
and assert the persisted `frame_mapping.json` timestamps land close to the
true cut points rather than at the uniform-estimate values a regression
would produce (0.0s / 3.0s for two frames over a 6s clip).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from transcript_pipeline.media.keyframe_extractor import KeyframeExtractor

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

CUT_1_S = 2.0
CUT_2_S = 4.0
TOLERANCE_S = 0.35


def _make_synthetic_cuts_video(path: Path) -> None:
    """6s, 64x64, 10fps video: 2s of testsrc + 2s of smptebars + 2s of rgbtestsrc,
    hard cuts at t=2.0s and t=4.0s.

    Uses textured/patterned lavfi sources (not flat solid colors): a flat
    color frame is a degenerate case for perceptual-hash dedup (every pixel
    equals the mean, so average_hash collapses to the same bit pattern
    regardless of hue), which would make the dedup phase falsely merge two
    genuinely distinct scenes. Patterned sources keep the dedup phase honest.
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


def _closest_distance(timestamp: float, targets: list[float]) -> float:
    return min(abs(timestamp - t) for t in targets)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not available")
@pytest.mark.parametrize("method,env", [
    ("scene", {}),
    ("smart_scene", {"SMART_SCENE_COOLDOWN": "1.0", "SMART_SCENE_BLUR": "1"}),
])
def test_frame_mapping_uses_real_pts_not_uniform_estimate(tmp_path, monkeypatch, method, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    video_path = tmp_path / "cuts.mp4"
    _make_synthetic_cuts_video(video_path)

    extractor = KeyframeExtractor(output_base_dir=str(tmp_path / "Frames"))
    monkeypatch.setattr(
        extractor, "_get_output_paths",
        lambda vp: (tmp_path / "Frames", vp.stem)
    )

    result = extractor.extract_keyframes(video_path, method=method, max_frames=10)

    assert result["success"], result["error"]
    assert result["frame_count"] >= 1

    mapping_path = Path(result["frames_dir"]) / "frame_mapping.json"
    assert mapping_path.exists()
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))

    frames = mapping["frames"]
    assert len(frames) == result["frame_count"]

    known_cuts = [CUT_1_S, CUT_2_S]
    for frame in frames:
        ts = frame["timestamp"]
        # Every retained frame must land near a real detected cut (±tolerance),
        # not at a fabricated uniform-interval position.
        assert _closest_distance(ts, known_cuts) <= TOLERANCE_S, (
            f"timestamp {ts} for {frame['frame_file']} is not close to a real "
            f"scene cut {known_cuts} — looks like a uniform-estimate regression"
        )

    # At least one frame must be attributed to each real cut — proves both
    # detected PTS values survived into the mapping, not just an average.
    timestamps = [f["timestamp"] for f in frames]
    assert any(abs(ts - CUT_1_S) <= TOLERANCE_S for ts in timestamps)
    assert any(abs(ts - CUT_2_S) <= TOLERANCE_S for ts in timestamps)
