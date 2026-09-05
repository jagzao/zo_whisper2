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
from pathlib import Path

import pytest

from tests.integration.conftest import CUT_1_S, CUT_2_S, requires_ffmpeg
from transcript_pipeline.media.keyframe_extractor import KeyframeExtractor

TOLERANCE_S = 0.35


def _closest_distance(timestamp: float, targets: list[float]) -> float:
    return min(abs(timestamp - t) for t in targets)


@requires_ffmpeg
@pytest.mark.parametrize("method,env", [
    ("scene", {}),
    ("smart_scene", {"SMART_SCENE_COOLDOWN": "1.0", "SMART_SCENE_BLUR": "1"}),
])
def test_frame_mapping_uses_real_pts_not_uniform_estimate(tmp_path, monkeypatch, synthetic_cuts_video, method, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    video_path = synthetic_cuts_video

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
