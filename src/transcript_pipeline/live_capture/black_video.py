"""Detect temporal black frames and persistent black borders without touching source media."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tempfile
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from transcript_pipeline.media.utils import run_ffprobe

_BLACK_INTERVAL_RE = re.compile(r"black_start:([0-9.]+).*?black_end:([0-9.]+)")
_CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


def _probe(path: Path) -> dict[str, Any]:
    result = run_ffprobe([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,codec_name,duration",
        "-of", "json", str(path),
    ])
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    duration = float(payload.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("Video duration could not be verified")
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise ValueError("Media has no video stream")
    return {"duration": duration, "streams": streams}


def _validate_output(source: Path, output: Path, expected_duration: float, progress: Callable[[str, int], None] | None = None) -> dict[str, Any]:
    source_info = _probe(source)
    output_info = _probe(output)
    source_types = [stream["codec_type"] for stream in source_info["streams"]]
    output_types = [stream["codec_type"] for stream in output_info["streams"]]
    if output_types.count("video") != 1 or ("audio" in source_types and "audio" not in output_types):
        raise RuntimeError("Trimmed output streams failed validation")
    if any(not stream.get("codec_name") for stream in output_info["streams"]):
        raise RuntimeError("Trimmed output contains an invalid stream")
    tolerance = max(1.0, expected_duration * 0.01)
    if abs(output_info["duration"] - expected_duration) > tolerance:
        raise RuntimeError("Trimmed output duration failed validation")
    if progress:
        progress("VALIDATING", 75)
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=7200,
        check=False,
    )
    if decoded.returncode or decoded.stderr.strip():
        raise RuntimeError("Trimmed output is not fully playable")
    return output_info


def _render_copy(
    source: Path,
    filters: str,
    output_suffix: str,
    expected_duration: float,
    *,
    filtered_audio: bool = False,
    progress: Callable[[str, int], None] | None = None,
) -> Path:
    output = source.with_name(f"{source.stem}_{output_suffix}.mp4")
    if output.exists():
        raise FileExistsError(f"{output_suffix} copy already exists")
    with tempfile.NamedTemporaryFile(prefix=f".{output.stem}.", suffix=".mp4", dir=source.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
    probe = _probe(source)
    has_audio = any(stream.get("codec_type") == "audio" for stream in probe["streams"])
    command = ["ffmpeg", "-hide_banner", "-y", "-i", str(source), "-filter_complex", filters, "-map", "[vout]"]
    if has_audio:
        command += ["-map", "[aout]"] if filtered_audio else ["-map", "0:a:0?", "-af", "asetpts=PTS-STARTPTS"]
    command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    if has_audio:
        command += ["-c:a", "aac"]
    command += ["-movflags", "+faststart", str(temporary)]
    try:
        if progress:
            progress("PROCESSING", 10)
        result = subprocess.run(command, capture_output=True, text=True, timeout=7200, check=False)
        if result.returncode or not temporary.exists() or temporary.stat().st_size == 0:
            raise RuntimeError(result.stderr[-1500:] or "FFmpeg did not produce an output video")
        if progress:
            progress("VALIDATING", 60)
        _validate_output(source, temporary, expected_duration, progress)
        temporary.replace(output)
        return output
    finally:
        temporary.unlink(missing_ok=True)


def detect_black_intervals(
    path: Path,
    *,
    darkness_threshold: float = 0.05,
    minimum_duration_seconds: float = 2.0,
) -> dict[str, Any]:
    if not math.isfinite(darkness_threshold) or not 0.01 <= darkness_threshold <= 0.30:
        raise ValueError("Darkness threshold must be between 0.01 and 0.30")
    if not math.isfinite(minimum_duration_seconds) or not 0.5 <= minimum_duration_seconds <= 3600:
        raise ValueError("Minimum duration must be between 0.5 and 3600 seconds")
    duration = _probe(path)["duration"]
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an",
            "-vf", f"scale=160:-2,tpad=stop_mode=add:stop_duration=1:color=white,blackdetect=d={minimum_duration_seconds}:pix_th={darkness_threshold}:pic_th=0.98",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=7200,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:] or "FFmpeg black-frame scan failed")
    intervals = []
    for match in _BLACK_INTERVAL_RE.finditer(result.stderr):
        start, end = map(float, match.groups())
        end = min(end, duration)
        if end - start >= minimum_duration_seconds:
            intervals.append({"start": round(start, 2), "end": round(end, 2)})
    confidence = "high" if darkness_threshold <= 0.08 else "low"
    return {
        "intervals": intervals,
        "duration": duration,
        "removed_seconds": round(sum(item["end"] - item["start"] for item in intervals), 2),
        "confidence": confidence,
        "status": "READY" if intervals and confidence == "high" else "NEEDS_REVIEW" if intervals else "NO_BLACK_SECTIONS",
    }


def trim_black_intervals(path: Path, intervals: list[dict[str, float]]) -> Path:
    duration = _probe(path)["duration"]
    cuts = []
    for item in intervals:
        start, end = float(item["start"]), float(item["end"])
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("Black interval values must be finite")
        cuts.append((max(0.0, start), min(duration, end)))
    cuts.sort()
    if not cuts or any(end <= start for start, end in cuts):
        raise ValueError("No valid black intervals to remove")

    merged: list[list[float]] = []
    for start, end in cuts:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    kept: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in merged:
        if start > cursor:
            kept.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        kept.append((cursor, duration))
    if not kept:
        raise ValueError("Black intervals cover the entire video")

    filters = []
    concat_inputs = []
    has_audio = any(stream.get("codec_type") == "audio" for stream in _probe(path)["streams"])
    for index, (start, end) in enumerate(kept):
        filters.append(f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}]")
        concat_inputs.append(f"[v{index}]")
        if has_audio:
            filters.append(f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{index}]")
            concat_inputs.append(f"[a{index}]")
    labels = "".join(concat_inputs)
    concat = f"{labels}concat=n={len(kept)}:v=1:a={1 if has_audio else 0}[vout]"
    if has_audio:
        concat = f"{labels}concat=n={len(kept)}:v=1:a=1[vout][aout]"
    filters.append(concat)
    expected = duration - sum(end - start for start, end in merged)
    return _render_copy(path, ";".join(filters), "trimmed", expected, filtered_audio=has_audio)


def detect_black_borders(path: Path, *, darkness_threshold: float = 0.05) -> dict[str, Any]:
    if not math.isfinite(darkness_threshold) or not 0.01 <= darkness_threshold <= 0.30:
        raise ValueError("Darkness threshold must be between 0.01 and 0.30")
    info = _probe(path)
    video = next(stream for stream in info["streams"] if stream.get("codec_type") == "video")
    width, height = int(video["width"]), int(video["height"])
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf",
            f"fps=1,cropdetect=limit={max(0.08, darkness_threshold)}:round=2:reset=0", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=7200,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:] or "FFmpeg border scan failed")
    crops = []
    for match in _CROP_RE.finditer(result.stderr):
        crop_width, crop_height, x, y = map(int, match.groups())
        if crop_width >= width * 0.2 and crop_height >= height * 0.2:
            crops.append((crop_width, crop_height, x, y))
    if not crops:
        return {"crop": None, "confidence": "low", "status": "NEEDS_REVIEW"}
    (crop_width, crop_height, x, y), count = Counter(crops).most_common(1)[0]
    borders = {"width": crop_width, "height": crop_height, "x": x, "y": y}
    has_borders = crop_width < width or crop_height < height
    confidence = "high" if count >= 2 and has_borders else "low"
    return {
        "crop": borders if has_borders else None,
        "frame": {"width": width, "height": height},
        "confidence": confidence,
        "status": "READY" if has_borders and confidence == "high" else "NEEDS_REVIEW" if has_borders else "NO_BLACK_BORDERS",
    }


def crop_black_borders(path: Path, crop: dict[str, int]) -> Path:
    info = _probe(path)
    duration = info["duration"]
    video = next(stream for stream in info["streams"] if stream.get("codec_type") == "video")
    width, height = int(video["width"]), int(video["height"])
    crop_width, crop_height = int(crop["width"]), int(crop["height"])
    x, y = int(crop["x"]), int(crop["y"])
    if min(crop_width, crop_height) < 2 or x < 0 or y < 0 or x + crop_width > width or y + crop_height > height:
        raise ValueError("Invalid border crop")
    return _render_copy(path, f"[0:v:0]crop={crop_width}:{crop_height}:{x}:{y}[vout]", "cropped", duration)


def validate_video_edit_spec(
    path: Path,
    cuts: list[dict[str, float]],
    *,
    trim_start: float = 0.0,
    trim_end: float | None = None,
    crop: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Validate reviewed coordinates against the source before queuing work."""
    info = _probe(path)
    duration = info["duration"]
    start = float(trim_start)
    end = duration if trim_end is None else float(trim_end)
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end > duration or end <= start:
        raise ValueError("Trim boundaries must be within the source duration")
    normalized = []
    for cut in cuts:
        if not isinstance(cut, dict):
            raise ValueError("Each cut must be an object")
        cut_start, cut_end = float(cut["start"]), float(cut["end"])
        if not math.isfinite(cut_start) or not math.isfinite(cut_end) or cut_start < 0 or cut_end > duration or cut_end <= cut_start:
            raise ValueError("Cut ranges must be within the source duration")
        normalized.append((cut_start, cut_end))
    streams = info["streams"]
    video = next(stream for stream in streams if stream.get("codec_type") == "video")
    if crop:
        width, height = int(video["width"]), int(video["height"])
        values = [crop.get(key) for key in ("x", "y", "width", "height")]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("Crop coordinates must be integer source pixels")
        x, y, crop_width, crop_height = (cast(int, value) for value in values)
        if min(crop_width, crop_height) < 2 or x < 0 or y < 0 or x + crop_width > width or y + crop_height > height or any(value % 2 for value in (x, y, crop_width, crop_height)):
            raise ValueError("Crop must be in bounds and use even pixel values")
    if start == 0 and end == duration and not normalized and not crop:
        raise ValueError("No video edits were selected")
    return {"duration": duration, "start": start, "end": end, "cuts": normalized}


def apply_video_edits(
    path: Path,
    cuts: list[dict[str, float]],
    *,
    trim_start: float = 0.0,
    trim_end: float | None = None,
    crop: dict[str, int] | None = None,
    progress: Callable[[str, int], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Create one validated derivative from reviewed temporal and spatial edits."""
    info = _probe(path)
    duration = info["duration"]
    end_limit = duration if trim_end is None else float(trim_end)
    start_limit = float(trim_start)
    if not math.isfinite(start_limit) or not math.isfinite(end_limit):
        raise ValueError("Trim boundaries must be finite")
    if start_limit < 0 or end_limit > duration or end_limit <= start_limit:
        raise ValueError("Trim boundaries are outside the video duration")
    if start_limit == 0 and end_limit == duration and not cuts and not crop:
        raise ValueError("No video edits were selected")

    normalized: list[tuple[float, float]] = []
    for item in cuts:
        start, end = float(item["start"]), float(item["end"])
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("Cut values must be finite")
        start, end = max(start_limit, start), min(end_limit, end)
        if end > start:
            normalized.append((start, end))
    normalized.sort()
    merged: list[list[float]] = []
    for start, end in normalized:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if start_limit == 0 and end_limit == duration and not merged and not crop:
        raise ValueError("No effective video edits were selected")

    kept: list[tuple[float, float]] = []
    cursor = start_limit
    for start, end in merged:
        if start > cursor:
            kept.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < end_limit:
        kept.append((cursor, end_limit))
    if not kept:
        raise ValueError("Edits remove the entire video")

    video = next(stream for stream in info["streams"] if stream.get("codec_type") == "video")
    crop_values = None
    if crop:
        width, height = int(video["width"]), int(video["height"])
        crop_width, crop_height = int(crop["width"]), int(crop["height"])
        x, y = int(crop["x"]), int(crop["y"])
        if (
            min(crop_width, crop_height) < 2
            or x < 0 or y < 0
            or x + crop_width > width or y + crop_height > height
            or any(value % 2 for value in (crop_width, crop_height, x, y))
        ):
            raise ValueError("Crop must be in bounds and use even pixel values")
        crop_values = {"width": crop_width, "height": crop_height, "x": x, "y": y}

    has_audio = any(stream.get("codec_type") == "audio" for stream in info["streams"])
    filters = []
    concat_inputs = []
    for index, (start, end) in enumerate(kept):
        video_filter = f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS"
        if crop_values:
            video_filter += (
                f",crop={crop_values['width']}:{crop_values['height']}:{crop_values['x']}:{crop_values['y']}"
            )
        filters.append(f"{video_filter}[v{index}]")
        concat_inputs.append(f"[v{index}]")
        if has_audio:
            filters.append(
                f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{index}]"
            )
            concat_inputs.append(f"[a{index}]")
    concat = "".join(concat_inputs) + f"concat=n={len(kept)}:v=1:a={1 if has_audio else 0}"
    if has_audio:
        concat += "[vout][aout]"
    else:
        concat += "[vout]"
    filters.append(concat)

    removed = sum(end - start for start, end in merged)
    expected_duration = end_limit - start_limit - removed
    output = _render_copy(path, ";".join(filters), "edited", expected_duration, filtered_audio=has_audio, progress=progress)
    provenance_path = output.with_suffix(".provenance.json")
    temp_provenance: Path | None = None
    try:
        provenance = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": path.name,
            "source_sha256": _sha256(path),
            "output": output.name,
            "output_sha256": _sha256(output),
            "source_duration_seconds": duration,
            "output_duration_seconds": round(expected_duration, 3),
            "trim_start_seconds": start_limit,
            "trim_end_seconds": end_limit,
            "cuts": [{"start": start, "end": end} for start, end in merged],
            "crop": crop_values,
            "validated": True,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=f".{provenance_path.name}.",
            suffix=".tmp", dir=path.parent, delete=False,
        ) as tmp:
            json.dump(provenance, tmp, indent=2)
            tmp.write("\n")
            temp_provenance = Path(tmp.name)
        temp_provenance.replace(provenance_path)
    except Exception:
        output.unlink(missing_ok=True)
        if temp_provenance is not None:
            temp_provenance.unlink(missing_ok=True)
        raise
    return output, provenance


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
