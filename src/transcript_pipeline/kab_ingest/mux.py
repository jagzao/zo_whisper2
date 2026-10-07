"""FFmpeg muxing of a video segment with its external audio track.

Hard rules (V1 spec):
- FFmpeg is invoked as an argv array via subprocess — never a shell string;
- input 0 is the video file, input 1 is the external audio file; the video
  stream is always stream-copied from input 0 and the audio always comes
  from input 1 (re-encoded to AAC only because a raw concat/container mix
  can't be guaranteed — the mic stream is never silently substituted);
- any FFmpeg failure raises and the worker marks the segment FAILED —
  there is no fallback to un-muxed or wrong-audio output.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

FFMPEG_TIMEOUT_SECONDS = 600


class MuxError(RuntimeError):
    """FFmpeg failed; the segment must be treated as failed (fail closed)."""


def mux_video_with_external_audio(video: Path, audio: Path, out: Path) -> Path:
    """Muxes video (stream copy) with external audio (AAC) into `out`."""
    if not video.is_file():
        raise MuxError(f"video input missing: {video.name}")
    if not audio.is_file():
        raise MuxError(f"audio input missing: {audio.name}")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(out),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        out.unlink(missing_ok=True)
        raise MuxError("ffmpeg timed out during segment mux") from exc
    except FileNotFoundError as exc:
        raise MuxError("ffmpeg binary not available") from exc
    if result.returncode != 0:
        out.unlink(missing_ok=True)
        raise MuxError(f"ffmpeg failed with exit code {result.returncode}")
    if not out.is_file():
        raise MuxError("ffmpeg reported success but produced no output")
    return out
