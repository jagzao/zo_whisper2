"""Unit tests: W6 normalized crop application primitives.

Covers the pure pixel-box mapping, the deterministic Pillow crop (synthetic
images only), and the frame-directory crop that preserves every source frame.
No FFmpeg, no real media — a synthetic RGBA/RGB image is built with Pillow.
"""

from __future__ import annotations

import pytest

from transcript_pipeline.live_capture.crop import apply_crop_to_frames, crop_frame, to_pixel_box
from transcript_pipeline.live_capture.models import CropRegion


def _region(x=0.0, y=0.0, width=1.0, height=1.0) -> CropRegion:
    return CropRegion(x, y, width, height)


# ── CropRegion helpers ─────────────────────────────────────────────

def test_is_full_frame_true_for_unit_square():
    assert _region(0.0, 0.0, 1.0, 1.0).is_full_frame is True


def test_is_full_frame_false_for_partial_region():
    assert _region(0.0, 0.0, 0.5, 0.5).is_full_frame is False
    assert _region(0.1, 0.0, 0.9, 1.0).is_full_frame is False


# ── pixel-box mapping ──────────────────────────────────────────────

def test_to_pixel_box_centered_region_is_deterministic():
    assert to_pixel_box(_region(0.25, 0.25, 0.5, 0.5), 100, 100) == (25, 25, 75, 75)


def test_to_pixel_box_full_frame_fills_entire_image():
    assert to_pixel_box(_region(0.0, 0.0, 1.0, 1.0), 100, 100) == (0, 0, 100, 100)


def test_to_pixel_box_clamps_inside_bounds():
    # width/height exactly fill to the right/bottom edge; never exceeds.
    assert to_pixel_box(_region(0.0, 0.0, 1.0, 1.0), 3, 3) == (0, 0, 3, 3)


def test_to_pixel_box_minimum_one_pixel():
    # A tiny region still yields at least a 1x1 box.
    box = to_pixel_box(_region(0.0, 0.0, 0.001, 0.001), 1000, 1000)
    left, top, right, bottom = box
    assert right > left and bottom > top


def test_to_pixel_box_rejects_nonpositive_dimensions():
    with pytest.raises(ValueError):
        to_pixel_box(_region(), 0, 100)
    with pytest.raises(ValueError):
        to_pixel_box(_region(), 100, -1)


# ── deterministic image crop ───────────────────────────────────────

def _left_red_right_blue_image(path, size=10):
    from PIL import Image

    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = (255, 0, 0) if x < size // 2 else (0, 0, 255)
    img.save(path)
    return path


def _all_pixels(img):
    return {color for _count, color in img.getcolors()}


def test_crop_frame_deterministically_crops_left_half(tmp_path):
    from PIL import Image

    src = tmp_path / "frame_0001.png"
    dst = tmp_path / "cropped.png"
    _left_red_right_blue_image(src, size=10)

    meta = crop_frame(src, dst, _region(0.0, 0.0, 0.5, 1.0))

    assert src.exists()  # source preserved
    with Image.open(dst) as cropped:
        assert cropped.size == (5, 10)
        assert _all_pixels(cropped) == {(255, 0, 0)}
    assert meta["source"] == "frame_0001.png"
    assert meta["source_size"] == [10, 10]
    assert meta["output_size"] == [5, 10]
    assert meta["pixel_box"] == {"left": 0, "top": 0, "right": 5, "bottom": 10}
    assert meta["crop"] == {"x": 0.0, "y": 0.0, "width": 0.5, "height": 1.0}


def test_crop_frame_full_frame_is_noop_error(tmp_path):
    src = tmp_path / "frame_0001.png"
    _left_red_right_blue_image(src)
    with pytest.raises(ValueError):
        crop_frame(src, tmp_path / "out.png", _region(0.0, 0.0, 1.0, 1.0))


# ── frame-directory crop preserves sources ─────────────────────────

def _make_frames_dir(tmp_path, count=3, size=10):
    from PIL import Image

    frames_dir = tmp_path / "Frames"
    frames_dir.mkdir(parents=True)
    for i in range(count):
        path = frames_dir / f"frame_{i:04d}.png"
        img = Image.new("RGB", (size, size), (i * 40, 0, 0))
        img.save(path)
    return frames_dir


def test_apply_crop_to_frames_crops_and_preserves_originals(tmp_path):
    frames_dir = _make_frames_dir(tmp_path, count=2, size=10)
    result = apply_crop_to_frames(frames_dir, _region(0.0, 0.0, 0.5, 1.0))

    assert result["applied"] is True
    assert result["frames_cropped"] == 2
    assert result["source_preserved"] is True
    originals_dir = frames_dir / "originals"
    assert originals_dir.is_dir()
    assert len(list(originals_dir.glob("frame_*.png"))) == 2
    # Cropped frames are half width (5 px), originals are full (10 px).
    from PIL import Image

    with Image.open(frames_dir / "frame_0000.png") as cropped:
        assert cropped.size == (5, 10)
    with Image.open(originals_dir / "frame_0000.png") as original:
        assert original.size == (10, 10)


def test_apply_crop_to_frames_none_is_noop(tmp_path):
    frames_dir = _make_frames_dir(tmp_path, count=2)
    before = sorted(p.name for p in frames_dir.glob("frame_*.png"))
    result = apply_crop_to_frames(frames_dir, None)
    assert result["applied"] is False
    assert sorted(p.name for p in frames_dir.glob("frame_*.png")) == before
    assert not (frames_dir / "originals").exists()


def test_apply_crop_to_frames_full_frame_is_noop(tmp_path):
    frames_dir = _make_frames_dir(tmp_path, count=2)
    result = apply_crop_to_frames(frames_dir, _region(0.0, 0.0, 1.0, 1.0))
    assert result["applied"] is False
    assert result["reason"] == "no-op"
    assert not (frames_dir / "originals").exists()


def test_apply_crop_to_frames_empty_dir_is_noop(tmp_path):
    frames_dir = tmp_path / "EmptyFrames"
    frames_dir.mkdir()
    result = apply_crop_to_frames(frames_dir, _region(0.0, 0.0, 0.5, 0.5))
    assert result["applied"] is False
    assert result["reason"] == "no_frames"
