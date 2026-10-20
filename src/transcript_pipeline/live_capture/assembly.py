"""Server-side fragment assembly for W6 processing chunks.

Ordered, already-ACKed fragments are concatenated/remuxed into ONE playable
media file. The default strategy uses FFmpeg's concat demuxer with stream copy
only when ffmpeg is present and stable; otherwise it falls back to
concatenating *validated* container segments (same extension, each carrying a
matching container signature). If neither path can produce validated media the
caller gets `AssemblyError` and must keep the source fragments and retry later
— a chunk is never silently claimed finalized.

This module never deletes source fragments: it only reads them.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from transcript_pipeline.live_capture.errors import AssemblyError

# Matroska/WebM share the EBML header; MP4-family containers carry an `ftyp`
# box near the start. Anything else is accepted only by the signature-less
# fallback rule below.
_EBML_MAGIC = b"\x1a\x45\xdf\xa3"
_MP4_FAMILY = frozenset({".mp4", ".mov", ".m4a", ".3gp"})
_EBML_FAMILY = frozenset({".webm", ".mkv"})
_OUTPUT_FORMATS = {
    ".webm": "webm", ".mkv": "matroska", ".mp4": "mp4", ".mov": "mov",
    ".m4a": "ipod", ".mp3": "mp3", ".wav": "wav", ".ogg": "ogg",
    ".opus": "opus", ".flac": "flac",
}

_FFMPEG_TIMEOUT_SEC = 600


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def _looks_like_container(path: Path, extension: str) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
    except OSError:
        return False
    if not head:
        return False
    ext = extension.lower()
    if ext in _EBML_FAMILY:
        return head.startswith(_EBML_MAGIC)
    if ext in _MP4_FAMILY:
        return b"ftyp" in head
    # Unknown/opaque extension: accept a non-empty file; the segment-level
    # validation cannot be stricter without a container-specific parser.
    return True


def _validate_segments(paths: list[Path], extension: str) -> None:
    if not paths:
        raise AssemblyError("no fragments to assemble")
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise AssemblyError(f"fragment media missing or empty: {path.name}")
        if not _looks_like_container(path, extension):
            raise AssemblyError(f"fragment is not a valid {extension} container: {path.name}")


def _empty_temp(dest: Path) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    os.close(fd)
    return Path(name)


def _concatenate_bytes(paths: list[Path], dest: Path) -> None:
    """Documented fallback: append validated container segments in order.

    Only reached when FFmpeg is absent or its concat/remux failed, and only
    after `_validate_segments` proved every segment is a non-empty container.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _empty_temp(dest)
    try:
        with open(tmp, "wb") as out:
            for path in paths:
                with open(path, "rb") as fh:
                    shutil.copyfileobj(fh, out)
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _assemble_with_ffmpeg(paths: list[Path], dest: Path, durations_ms: list[int] | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_path = dest.parent / f".{dest.name}.concat.txt"
    lines = []
    for index, path in enumerate(paths):
        lines.append(f"file '{path.resolve().as_posix()}'\n")
        if durations_ms is not None:
            lines.append(f"duration {durations_ms[index] / 1000:.6f}\n")
    list_path.write_text("".join(lines), encoding="utf-8")
    tmp_out = _empty_temp(dest)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                "-f", _OUTPUT_FORMATS.get(dest.suffix.lower(), dest.suffix.lstrip(".")),
                str(tmp_out),
            ],
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT_SEC,
        )
        if result.returncode != 0 or not tmp_out.is_file() or tmp_out.stat().st_size == 0:
            raise AssemblyError(f"ffmpeg concat failed: {result.stderr.strip()[:500]}")
        tmp_out.replace(dest)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AssemblyError(f"ffmpeg concat could not run: {exc}") from exc
    finally:
        list_path.unlink(missing_ok=True)
        tmp_out.unlink(missing_ok=True)


def probe_media_duration(path: Path) -> float | None:
    """Return a finite duration from actual container/stream metadata."""
    if not ffprobe_available():
        return None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(result.stdout or "{}")
        values = [(data.get("format") or {}).get("duration")]
        values.extend(stream.get("duration") for stream in data.get("streams", []))
        for value in values:
            if value is None or not isinstance(value, (int, float, str)):
                continue
            duration = float(value)
            if result.returncode == 0 and math.isfinite(duration) and duration > 0:
                return duration
    except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.SubprocessError):
        return None
    return None


def probe_media_streams(path: Path) -> dict[str, object] | None:
    """Return actual audio/video stream metadata for capture validation."""
    if not ffprobe_available():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,channels,sample_rate",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if video is None and audio is None:
            return None
        raw_fps = (video or {}).get("avg_frame_rate") or (video or {}).get("r_frame_rate")
        try:
            numerator, denominator = str(raw_fps).split("/", 1)
            fps = float(numerator) / float(denominator)
        except (TypeError, ValueError, ZeroDivisionError):
            fps = None
        raw_duration = (data.get("format") or {}).get("duration")
        try:
            duration = float(raw_duration) if isinstance(raw_duration, (int, float, str)) else None
        except (TypeError, ValueError):
            duration = None
        return {
            "videoStreams": sum(item.get("codec_type") == "video" for item in streams),
            "audioStreams": sum(item.get("codec_type") == "audio" for item in streams),
            "width": (video or {}).get("width"),
            "height": (video or {}).get("height"),
            "fps": fps if fps and fps > 0 else None,
            "videoCodec": (video or {}).get("codec_name"),
            "audioCodec": (audio or {}).get("codec_name"),
            "audioChannels": (audio or {}).get("channels"),
            "audioSampleRate": (audio or {}).get("sample_rate"),
            "durationSec": duration,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.SubprocessError):
        return None


def _validate_output(dest: Path, extension: str, expected_duration_sec: float | None = None) -> float | None:
    if not dest.is_file() or dest.stat().st_size == 0:
        raise AssemblyError("assembled media is empty")
    duration = None
    if ffprobe_available():
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(dest)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AssemblyError(f"assembled media could not be probed: {exc}") from exc
        if result.returncode != 0:
            raise AssemblyError("assembled media failed ffprobe validation")
        streams = json.loads(result.stdout or "{}").get("streams", [])
        if not streams:
            raise AssemblyError("assembled media has no streams")
        duration = probe_media_duration(dest)
    if expected_duration_sec is not None:
        if duration is None:
            raise AssemblyError("assembled media duration could not be verified; source fragments were preserved")
        tolerance = max(2.0, expected_duration_sec * 0.05)
        if abs(duration - expected_duration_sec) > tolerance:
            raise AssemblyError(
                f"assembled media duration {duration:.3f}s does not match expected "
                f"{expected_duration_sec:.3f}s (tolerance {tolerance:.3f}s)"
            )
    elif not _looks_like_container(dest, extension):
        raise AssemblyError("assembled media failed container validation")


def assemble_media(paths: list[Path], dest: Path, durations_ms: list[int] | None = None) -> None:
    """Assembles ordered fragments into `dest` (atomic) or raises.

    FFmpeg concat/remux (stream copy) is tried first when ffmpeg is present.
    On any FFmpeg failure the validated byte-concatenation fallback is used.
    The output must always pass validation before the caller may finalize a
    processing chunk.
    """
    paths = [Path(p) for p in paths]
    dest = Path(dest)
    extension = dest.suffix
    _validate_segments(paths, extension)
    if durations_ms is not None and (len(durations_ms) != len(paths) or any(value <= 0 for value in durations_ms)):
        raise AssemblyError("fragment durations must be positive and match the assembly inputs")

    if ffmpeg_available():
        try:
            _assemble_with_ffmpeg(paths, dest, durations_ms)
        except AssemblyError:
            if durations_ms is not None:
                raise
            _concatenate_bytes(paths, dest)
    elif durations_ms is not None:
        raise AssemblyError("FFmpeg is required to preserve the acknowledged capture timeline")
    else:
        _concatenate_bytes(paths, dest)

    expected_duration = sum(durations_ms) / 1000 if durations_ms is not None else None
    _validate_output(dest, extension, expected_duration)


def ensure_seekable_audio(path: Path, normalized_path: Path) -> float:
    """Ensure an audio-only WebM has finite duration metadata for native players."""
    path = Path(path)
    normalized_path = Path(normalized_path)
    if path.suffix.lower() != ".webm" or not ffprobe_available():
        return 0.0

    def duration_of(candidate: Path) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(candidate)],
                capture_output=True, text=True, timeout=60,
            )
            value = json.loads(result.stdout or "{}").get("format", {}).get("duration")
            duration = float(value)
            return duration if result.returncode == 0 and math.isfinite(duration) and duration > 0 else 0.0
        except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.SubprocessError):
            return 0.0

    duration = duration_of(path)
    if duration:
        return duration
    if not ffmpeg_available():
        raise AssemblyError("audio recording has no finite duration and FFmpeg is unavailable")
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-map", "0:a:0", "-vn",
             "-c:a", "libopus", "-b:a", "128k", "-f", "webm", str(normalized_path)],
            capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        normalized_path.unlink(missing_ok=True)
        raise AssemblyError(f"audio output could not be normalized for playback: {exc}") from exc
    if result.returncode != 0 or not normalized_path.is_file():
        normalized_path.unlink(missing_ok=True)
        raise AssemblyError(f"audio output could not be normalized for playback: {result.stderr.strip()[:300]}")
    duration = duration_of(normalized_path)
    if not duration:
        normalized_path.unlink(missing_ok=True)
        raise AssemblyError("normalized audio has no playable duration")
    return duration
