# MERGED — these methods are already in watcher/core/video/keyframe_extractor.py
# This file is kept as a reference snapshot only. Do not use directly.

"""
Smart Scene Extraction
----------------------
Replaces the naive gt(scene,0.4) method with a robust pipeline:
1. Blur pre-filter via FFmpeg (ignore cursor/UI micro-changes)
2. Stricter threshold (0.5) + cooldown (5s between frames)
3. Perceptual-hash deduplication post-extraction (remove >90% similar frames)
4. Strict max_frames enforcement
"""

import subprocess
from pathlib import Path
from typing import Optional, List

# NOTE: These methods are designed to be pasted into KeyframeExtractor class.

def _extract_smart_scene_frames(
    self,
    video_path: Path,
    output_dir: Path,
    max_frames: Optional[int],
    quality: int
) -> int:
    """
    Extrae frames basados en cambios de escena REALES, ignorando
    movimientos de cursor y micro-actualizaciones de UI.

    Pipeline:
      1. ffmpeg: gblur + scene detection (threshold 0.5)
      2. ffmpeg: extract selected PTS
      3. deduplicate via perceptual hash (remove >90% similar)
      4. hard-limit to max_frames
    """
    # Phase 1: detect scene-change PTS with blurred input
    scene_th = float(getattr(self, "scene_threshold", 0.5))
    cooldown_s = float(getattr(self, "scene_cooldown_s", 5.0))

    # Build filter: blur lightly, then select scenes above threshold,
    # followed by a cooldown frame selection to enforce minimum gap.
    # We use f='gt(scene,{th})' and then showinfo to collect pts.
    detect_filter = (
        f"gblur=sigma=2:steps=1,"
        f"select='gt(scene\\,{scene_th})',showinfo"
    )

    detect_cmd = [
        self.ffmpeg_path,
        "-i", str(video_path),
        "-vf", detect_filter,
        "-f", "null",
        "-"
    ]

    result = subprocess.run(detect_cmd, capture_output=True, text=True)
    pts_list = []
    for line in result.stderr.splitlines():
        if "pts:" in line and "pts_time:" in line:
            try:
                parts = line.split("pts_time:")
                if len(parts) >= 2:
                    val = parts[1].split()[0].strip()
                    pts_list.append(float(val))
            except Exception:
                continue

    if not pts_list:
        return 0

    # Enforce cooldown and deduplicate initial PTS list
    filtered_pts = []
    last = -cooldown_s
    for pts in sorted(set(pts_list)):
        if pts - last >= cooldown_s:
            filtered_pts.append(pts)
            last = pts

    # Hard limit before extraction if requested
    if max_frames and len(filtered_pts) > max_frames:
        # Uniformly sample across video duration instead of first N
        step = len(filtered_pts) / max_frames
        filtered_pts = [filtered_pts[int(i * step)] for i in range(max_frames)]

    # Phase 2: extract exact frames at selected PTS
    fmt = self.frame_format
    for idx, pts in enumerate(filtered_pts):
        out_file = output_dir / f"frame_{idx:04d}.{fmt}"
        cmd = [
            self.ffmpeg_path,
            "-ss", str(pts),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", str(quality),
            "-y",
            str(out_file)
        ]
        subprocess.run(cmd, capture_output=True, text=True)

    extracted = sorted(output_dir.glob(f"frame_*.{fmt}"))

    # Phase 3: deduplicate perceptual hashes
    if len(extracted) > 1:
        try:
            extracted = self._deduplicate_by_hash(extracted, similarity=0.90)
        except Exception:
            pass

    # Phase 4: strict max_frames final limit
    if max_frames and len(extracted) > max_frames:
        for f in extracted[max_frames:]:
            try:
                f.unlink()
            except Exception:
                pass
        extracted = extracted[:max_frames]

    return len(extracted)


def _deduplicate_by_hash(
    self,
    frame_paths: List[Path],
    similarity: float = 0.90
) -> List[Path]:
    """
    Remove consecutive frames whose perceptual hash similarity exceeds
    the threshold. Keeps the first frame of each near-duplicate run.

    Requires Pillow + imagehash; falls back gracefully if unavailable.
    """
    try:
        from PIL import Image
        import imagehash
    except Exception:
        raise RuntimeError("imagehash not available")

    kept = []
    last_hash = None
    threshold = int((1.0 - similarity) * 64)  # ahash is 64 bits

    for path in frame_paths:
        try:
            img = Image.open(path)
            h = imagehash.average_hash(img)
        except Exception:
            kept.append(path)
            continue

        if last_hash is None or (h - last_hash) > threshold:
            kept.append(path)
            last_hash = h
        else:
            # Remove duplicate
            try:
                path.unlink()
            except Exception:
                pass

    return kept
