"""T33-T37: worker restart/reconcile/stale semantics, states, mux fail-closed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from transcript_pipeline.kab_ingest.store import segment_dir_name
from transcript_pipeline.kab_ingest.worker import MAX_PROCESSING_ATTEMPTS, KabIngestWorker
from tests.kab_ingest_utils import (
    FakeTranscriber,
    chunk_bytes,
    make_store,
    session_payload,
    sha256_hex,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _reader(data: bytes):
    iterator = iter([data])
    return lambda _n: next(iterator, b"")


def _ready_video_session(tmp_path, *, segments: int = 1, tracks=("video",), session_id: str = "sess-0001"):
    store = make_store(tmp_path)
    store.create_session(session_payload(session_id=session_id, requiredTracks=list(tracks)))
    for segment in range(segments):
        for track in tracks:
            body = chunk_bytes(f"{session_id}-{segment}-{track}", 256)
            store.put_chunk(session_id, segment, track, 0, read=_reader(body), expected_sha256=sha256_hex(body), expected_size=len(body))
            store.complete_segment(
                session_id, segment, track,
                total_chunks=1, size_bytes=len(body), sha256=sha256_hex(body),
                extension=".mp4" if track == "video" else ".m4a",
                duration_ms=1000, start_offset_ms=segment * 1000,
            )
    return store


def test_t33_processes_ready_and_never_twice(tmp_path):
    store = _ready_video_session(tmp_path)
    transcriber = FakeTranscriber()
    worker = KabIngestWorker(store, tmp_path, transcribe=transcriber, poll_seconds=0.01)
    assert worker.run_once() == 1
    assert transcriber.calls and transcriber.calls[0].name == "segment-000000.video.mp4"
    result_path = store.paths("sess-0001").result_file(0)
    assert result_path.exists()
    first_processed_at = result_path.read_text(encoding="utf-8")

    assert worker.run_once() == 0
    assert len(transcriber.calls) == 1
    assert result_path.read_text(encoding="utf-8") == first_processed_at
    state = store.read_worker_state("sess-0001")
    assert state["segments"]["0"]["state"] == "PROCESSED"

    store.paths("sess-0001").ready_marker(0).write_text("{}", encoding="utf-8")
    assert worker.run_once() == 0
    assert len(transcriber.calls) == 1


def test_t34_reconciles_missing_ready_marker(tmp_path):
    store = _ready_video_session(tmp_path)
    store.paths("sess-0001").ready_marker(0).unlink()
    worker = KabIngestWorker(store, tmp_path, transcribe=FakeTranscriber(), poll_seconds=0.01)
    worker.reconcile_session("sess-0001")
    assert store.paths("sess-0001").ready_marker(0).exists()
    assert worker.run_once() == 1
    assert store.paths("sess-0001").result_file(0).exists()


def test_t35_stale_processing_retries_once_then_fails_permanently(tmp_path):
    store = _ready_video_session(tmp_path)
    paths = store.paths("sess-0001")
    from transcript_pipeline.kab_ingest.atomic import atomic_write_json

    paths.ready_marker(0).rename(paths.processing_marker(0))
    marker_payload = {
        "schemaVersion": 1,
        "segmentIndex": 0,
        "attempts": 1,
        "tracks": {"video": {"file": "segment-000000.video.mp4", "extension": ".mp4", "sizeBytes": 256, "sha256": "x", "durationMs": 1000, "startOffsetMs": 0}},
    }
    atomic_write_json(paths.processing_marker(0), marker_payload)

    transcriber = FakeTranscriber()
    worker = KabIngestWorker(store, tmp_path, transcribe=transcriber, poll_seconds=0.01)
    worker.run_once()
    assert store.read_worker_state("sess-0001")["segments"]["0"]["state"] == "PROCESSED"
    assert not paths.processing_marker(0).exists()
    assert paths.result_file(0).exists()
    assert len(transcriber.calls) == 1

    _ready_video_session(tmp_path, session_id="sess-0002")
    paths2 = store.paths("sess-0002")
    paths2.ready_marker(0).rename(paths2.processing_marker(0))
    atomic_write_json(paths2.processing_marker(0), {**marker_payload, "attempts": MAX_PROCESSING_ATTEMPTS})
    worker.run_once()
    assert store.read_worker_state("sess-0002")["segments"]["0"]["state"] == "FAILED"
    assert paths2.failed_marker(0).exists()
    assert not paths2.processing_marker(0).exists()
    assert not paths2.result_file(0).exists()
    assert len(transcriber.calls) == 1


def test_t36_transcription_failure_marks_failed_visible_in_state(tmp_path):
    class BoomTranscriber:
        def __init__(self):
            self.calls = 0

        def __call__(self, media_path: Path) -> dict:
            self.calls += 1
            raise RuntimeError("whisper exploded")

    store = _ready_video_session(tmp_path)
    boom = BoomTranscriber()
    worker = KabIngestWorker(store, tmp_path, transcribe=boom, poll_seconds=0.01)
    worker.run_once()
    state = store.read_worker_state("sess-0001")
    assert state["segments"]["0"]["state"] == "FAILED"
    assert store.paths("sess-0001").failed_marker(0).exists()
    assert not store.paths("sess-0001").processing_marker(0).exists()

    summary = store.session_state("sess-0001")
    assert summary["failedSegmentIndexes"] == [0]
    assert summary["segments"][0]["errorCode"] == "processing_failed"

    assert worker.run_once() == 0
    assert boom.calls == 1


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not available")
def test_t37_mux_merges_video_and_external_audio(tmp_path):
    video = tmp_path / "in-video.mp4"
    audio = tmp_path / "in-audio.m4a"
    out = tmp_path / "out.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=duration=0.5:size=128x96:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True, timeout=120,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", "-c:a", "aac", str(audio)],
        check=True, capture_output=True, timeout=120,
    )
    from transcript_pipeline.kab_ingest.mux import mux_video_with_external_audio

    mux_video_with_external_audio(video, audio, out)
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    kinds = sorted(line.strip() for line in probe.stdout.splitlines() if line.strip())
    assert kinds == ["audio", "video"]


def test_t37_mux_fail_closed_on_missing_input(tmp_path):
    from transcript_pipeline.kab_ingest.mux import MuxError, mux_video_with_external_audio

    real = tmp_path / "real.mp4"
    real.write_bytes(b"not really a video")
    with pytest.raises(MuxError):
        mux_video_with_external_audio(tmp_path / "missing.mp4", real, tmp_path / "out.mp4")
    assert not (tmp_path / "out.mp4").exists()

    store = _ready_video_session(tmp_path, segments=1, tracks=("video", "audio"))
    paths = store.paths("sess-0001")
    from transcript_pipeline.kab_ingest.atomic import atomic_write_json

    atomic_write_json(
        paths.ready_marker(0),
        {
            "schemaVersion": 1,
            "segmentIndex": 0,
            "requiredTracks": ["video", "audio"],
            "tracks": {
                "video": {"file": "segment-000000.video.mp4", "extension": ".mp4"},
                "audio": {"file": "segment-999999.audio.m4a", "extension": ".m4a"},
            },
        },
    )
    worker = KabIngestWorker(store, tmp_path, transcribe=FakeTranscriber(), poll_seconds=0.01)
    worker.run_once()
    assert store.read_worker_state("sess-0001")["segments"]["0"]["state"] == "FAILED"
    assert not store.paths("sess-0001").result_file(0).exists()


def test_worker_requires_whisper_when_default_bridge_used(tmp_path):
    from transcript_pipeline.kab_ingest.worker import WhisperBridge

    bridge = WhisperBridge()
    assert bridge._processor is None
    assert segment_dir_name(7) == "segment-000007"
