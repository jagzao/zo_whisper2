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
import hashlib
import shutil
import subprocess
from dataclasses import replace

import pytest

from transcript_pipeline.live_capture.assembly import assemble_media, probe_media_streams
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


def _make_live_audio_segment(path):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1",
         "-c:a", "libopus", "-b:a", "64k", "-f", "webm", "-live", "1", str(path)],
        capture_output=True, check=True, timeout=120,
    )
    return path


def _make_live_video_segment(path, duration=15):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"testsrc2=duration={duration}:size=64x64:rate=10", "-c:v", "libvpx", "-b:v", "200k",
         "-f", "webm", "-live", "1", str(path)],
        capture_output=True, check=True, timeout=120,
    )
    return path


def _make_live_av_segment(path, duration=1):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"testsrc2=duration={duration}:size=160x120:rate=15", "-f", "lavfi", "-i",
         f"sine=frequency=440:duration={duration}", "-c:v", "libvpx", "-b:v", "250k",
         "-c:a", "libopus", "-b:a", "48k", "-shortest", "-f", "webm", "-live", "1", str(path)],
        capture_output=True, check=True, timeout=60,
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
def test_final_assembled_crop_stream_retains_audio_and_actual_dimensions(tmp_path):
    service = CaptureService(videos_root=tmp_path / "Videos")
    session = service.create_session(
        "cropped camera with mic",
        capture_metadata={"audioRequested":True,"cropOutputWidth":160,"cropOutputHeight":120},
    )
    source = _make_live_av_segment(tmp_path / "crop-av.webm")
    service.upload_fragment(
        session.session_id, "fragment-000001", 1, io.BytesIO(source.read_bytes()),
        duration_ms=1000, recorded_offset_ms=0,
    )
    service.drain_processing_chunks(session.session_id)
    service.finalize_session(session.session_id)

    final = service.finalize_session_media(session.session_id)

    assert final["streams"]["videoStreams"] == 1
    assert final["streams"]["audioStreams"] == 1
    assert final["streams"]["width"] == 160
    assert final["streams"]["height"] == 120
    assert final["streams"]["videoCodec"] == "vp8"
    assert final["streams"]["audioCodec"] == "opus"
    assert service.get_session(session.session_id).capture_metadata["finalMediaProbe"]["audioStreams"] == 1


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


@requires_ffmpeg
def test_three_15_second_live_fragments_finalize_as_one_complete_video(tmp_path):
    service = CaptureService(videos_root=tmp_path / "Videos")
    session = service.create_session("45 second synthetic capture", chunk_duration_sec=600)
    for sequence in range(1, 4):
        source = _make_live_video_segment(tmp_path / f"live-{sequence}.webm")
        service.upload_fragment(
            session.session_id, f"fragment-{sequence:06d}", sequence,
            io.BytesIO(source.read_bytes()), duration_ms=15_000, recorded_offset_ms=(sequence - 1) * 15_000,
        )

    service.drain_processing_chunks(session.session_id)
    service.finalize_session(session.session_id, ended_at="2026-10-16T12:00:45+00:00")
    final = service.finalize_session_media(session.session_id)
    path = service.store.final_media_path(session.session_id, ".webm")
    probed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    duration = float(json.loads(probed.stdout)["format"]["duration"])

    assert len(service.list_fragments(session.session_id)) == 3
    assert final["fragmentIds"] == ["fragment-000001", "fragment-000002", "fragment-000003"]
    assert duration == pytest.approx(45, abs=2)
    assert final["durationSec"] == pytest.approx(duration, abs=0.2)
    assert service.finalize_session_media(session.session_id) == final

    bad_bytes = b"".join(
        service.store.fragment_media_path(session.session_id, fragment.fragment_id, fragment.media_extension).read_bytes()
        for fragment in service.list_fragments(session.session_id)
    )
    path.write_bytes(bad_bytes)
    stored = service.get_session(session.session_id)
    bad_manifest = {**final, "sha256": hashlib.sha256(bad_bytes).hexdigest(),
                    "sizeBytes": len(bad_bytes), "durationSec": None}
    service.store.save_session(replace(stored, final_media=bad_manifest))

    recovered = service.finalize_session_media(session.session_id)
    backup = service.store.final_recovery_backup_path(session.session_id, ".webm")
    recovered_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert float(json.loads(recovered_probe.stdout)["format"]["duration"]) == pytest.approx(45, abs=2)
    assert backup.read_bytes() == bad_bytes
    assert recovered["durationSec"] == pytest.approx(45, abs=2)


@requires_ffmpeg
def test_audio_capture_finalization_adds_duration_for_native_player(tmp_path):
    service = CaptureService(videos_root=tmp_path / "Videos")
    session = service.create_session("audio-only", capture_kind="audio", capture_source="microphone")
    fragment_path = _make_live_audio_segment(tmp_path / "live-audio.webm")
    service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(fragment_path.read_bytes()),
                            media_extension=".webm", duration_ms=1000, recorded_offset_ms=0)
    service.drain_processing_chunks(session.session_id)
    service.finalize_session(session.session_id)
    final = service.finalize_session_media(session.session_id)
    path = service.store.final_media_path(session.session_id, ".webm")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert 0 < duration < 3
    assert final["durationSec"] == pytest.approx(duration, abs=0.2)
    assert any(stream.get("codec_type") == "audio" for stream in _probe_streams(path))
