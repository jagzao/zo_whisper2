"""Deterministic normalized-crop application for generated frames (W6).

Turns a validated :class:`~transcript_pipeline.live_capture.models.CropRegion`
into a pixel box and crops a frame image losslessly-deterministically using
Pillow. The crop is always written to a *new* path — the original source
frame is never modified or discarded — and every transform records its
metadata so documentation/keyframe evidence can cite exactly what was
cropped.

These are primitives for the existing keyframe pipeline; they do not add a
separate processing pipeline. A ``None`` or full-frame crop is a no-op.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from transcript_pipeline.live_capture.models import CropRegion

# KeyframeExtractor writes frames with any of these formats.
FRAME_GLOBS = ("frame_*.png", "frame_*.jpg", "frame_*.jpeg", "frame_*.webp")
ORIGINALS_DIR = "originals"


def _round_half_up(value: float) -> int:
    """Rounds to the nearest integer, ties away from zero (deterministic)."""
    return math.floor(value + 0.5)


def to_pixel_box(crop: CropRegion, width: int, height: int) -> tuple[int, int, int, int]:
    """Converts a normalized crop to a ``(left, top, right, bottom)`` box in
    pixel space, clamped to the image bounds and at least 1px on each side.

    Pure math — no image library — so the coordinate mapping itself is
    trivially unit-testable and independent of Pillow's rounding.
    """
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    left = _round_half_up(crop.x * width)
    top = _round_half_up(crop.y * height)
    right = _round_half_up((crop.x + crop.width) * width)
    bottom = _round_half_up((crop.y + crop.height) * height)
    left = max(0, min(width, left))
    top = max(0, min(height, top))
    right = max(left + 1, min(width, right))
    bottom = max(top + 1, min(height, bottom))
    return left, top, right, bottom


def _frame_files(frames_dir: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in FRAME_GLOBS:
        files.extend(frames_dir.glob(pattern))
    return sorted({f for f in files if f.is_file()}, key=lambda p: p.name)


def crop_frame(src: Path, dst: Path, crop: CropRegion) -> dict[str, Any]:
    """Crops ``src`` into ``dst``, leaving ``src`` untouched.

    Returns transform metadata (source name, source/output pixel sizes, the
    normalized crop, and the resolved pixel box). Raises ``ValueError`` for a
    full-frame crop (callers should skip those as a no-op) and any Pillow
    failure propagates so the caller can fall back to the untouched source.
    """
    if crop.is_full_frame:
        raise ValueError("full-frame crop is a no-op; skip it instead")
    from PIL import Image

    with Image.open(src) as img:
        width, height = img.size
        box = to_pixel_box(crop, width, height)
        cropped = img.crop(box)
        dst.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(dst)
    return {
        "source": src.name,
        "source_size": [width, height],
        "crop": crop.to_manifest(),
        "pixel_box": {"left": box[0], "top": box[1], "right": box[2], "bottom": box[3]},
        "output_size": [box[2] - box[0], box[3] - box[1]],
    }


def apply_crop_to_frames(frames_dir: Path, crop: CropRegion) -> dict[str, Any]:
    """Crops every extracted frame in ``frames_dir`` in place, preserving each
    original under ``frames_dir/originals/``.

    Returns crop metadata suitable for ``frame_mapping.json``. A ``None`` or
    full-frame crop, an empty frames dir, or a missing Pillow all return a
    no-op status and never touch the source frames — an invalid/unsupported
    crop silently falls back to the full frame (per W6 recovery), it never
    discards evidence.
    """
    if crop is None or crop.is_full_frame:
        return {"applied": False, "reason": "no-op", "crop": crop.to_manifest() if crop else None}
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return {"applied": False, "reason": "pillow_unavailable", "crop": crop.to_manifest()}

    frames = _frame_files(frames_dir)
    if not frames:
        return {"applied": False, "reason": "no_frames", "crop": crop.to_manifest()}

    originals_dir = frames_dir / ORIGINALS_DIR
    originals_dir.mkdir(parents=True, exist_ok=True)

    transformed: list[dict[str, Any]] = []
    for frame in frames:
        original = originals_dir / frame.name
        try:
            frame.rename(original)
            meta = crop_frame(original, frame, crop)
            transformed.append(meta)
        except Exception:
            # Never leave a frame missing: restore the original on any failure
            # and skip this frame rather than discard its source.
            if original.exists() and not frame.exists():
                original.rename(frame)
            continue

    return {
        "applied": len(transformed) > 0,
        "reason": "ok" if transformed else "no_frames_cropped",
        "crop": crop.to_manifest(),
        "frames_cropped": len(transformed),
        "source_preserved": True,
        "originals_dir": ORIGINALS_DIR,
        "transforms": transformed,
    }
