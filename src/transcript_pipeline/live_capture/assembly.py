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


def _assemble_with_ffmpeg(paths: list[Path], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_path = dest.parent / f".{dest.name}.concat.txt"
    list_path.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in paths), encoding="utf-8"
    )
    tmp_out = _empty_temp(dest)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
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


def _validate_output(dest: Path, extension: str) -> None:
    if not dest.is_file() or dest.stat().st_size == 0:
        raise AssemblyError("assembled media is empty")
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
    elif not _looks_like_container(dest, extension):
        raise AssemblyError("assembled media failed container validation")


def assemble_media(paths: list[Path], dest: Path) -> None:
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

    if ffmpeg_available():
        try:
            _assemble_with_ffmpeg(paths, dest)
        except AssemblyError:
            _concatenate_bytes(paths, dest)
    else:
        _concatenate_bytes(paths, dest)

    _validate_output(dest, extension)
