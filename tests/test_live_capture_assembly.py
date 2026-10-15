"""W6 FFmpeg-backed assembly test with synthetic media.

These tests only run when ffmpeg/ffprobe are available (repository-provided
binaries, no private media). They generate tiny patterned lavfi clips, upload
them as fragments, and prove the default assembler produces a playable
processing chunk via the real FFmpeg concat path. The deterministic
boundary/mapping/retry tests live in `test_live_capture_processing_chunks.py`
with a fake assembler, so they never depend on FFmpeg.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess

import pytest

from transcript_pipeline.live_capture.assembly import assemble_media
from transcript_pipeline.live_capture.errors import AssemblyError
from transcript_pipeline.live_capture.service import CaptureService

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not available")


def _make_segment(path, duration=1):
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc2=duration={duration}:size=64x64:rate=10",
            "-c:v", "libvpx", "-b:v", "200k", str(path),
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    return path


def _probe_streams(path) -> list[dict]:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout).get("streams", [])


def test_assemble_media_rejects_non_container(tmp_path):
    bad = tmp_path / "notmedia.webm"
    bad.write_bytes(b"this-is-not-a-container")
    with pytest.raises(AssemblyError):
        assemble_media([bad], tmp_path / "out.webm")


@requires_ffmpeg
def test_default_assembler_concats_real_webm_segments(tmp_path):
    first = _make_segment(tmp_path / "a.webm")
    second = _make_segment(tmp_path / "b.webm")
    dest = tmp_path / "joined.webm"

    assemble_media([first, second], dest)

    assert dest.is_file() and dest.stat().st_size > 0
    assert any(s.get("codec_type") == "video" for s in _probe_streams(dest))


@requires_ffmpeg
def test_service_aggregates_real_segments_into_processing_chunk(tmp_path):
    service = CaptureService(videos_root=tmp_path / "Videos")
    session = service.create_session("real-media", chunk_duration_sec=3)
    segment_sizes = []
    for seq in range(1, 4):
        segment = _make_segment(tmp_path / f"seg{seq}.webm")
        data = segment.read_bytes()
        segment_sizes.append(len(data))
        service.upload_fragment(
            session.session_id,
            f"fragment-{seq:06d}",
            seq,
            io.BytesIO(data),
            duration_ms=1000,
            recorded_offset_ms=(seq - 1) * 1000,
        )

    finalized = service.finalized_chunks(session.session_id)
    assert [c.index for c in finalized] == [0]
    chunk_media = service.store.session_dir(session.session_id) / "chunks" / "chunk-000000.webm"
    assert chunk_media.is_file()
    assert chunk_media.stat().st_size > max(segment_sizes)
    assert any(s.get("codec_type") == "video" for s in _probe_streams(chunk_media))

    mapping = service.list_processing_chunks(session.session_id)
    assert len(mapping) == 1 and mapping[0].state == "FINALIZED"
    # Source fragments are retained after a successful assembly.
    assert len(service.list_fragments(session.session_id)) == 3
