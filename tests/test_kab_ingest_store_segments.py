"""T24-T28: segment assembly, exact chunk order, ready markers, cross-track rules."""

from __future__ import annotations

from transcript_pipeline.kab_ingest.errors import KabIngestConflict, KabIngestValidationError
from tests.kab_ingest_utils import (
    chunk_bytes,
    make_store,
    session_payload,
    sha256_hex,
)


def _reader(data: bytes):
    iterator = iter([data])
    return lambda _n: next(iterator, b"")


def _upload(store, segment: int, track: str, chunk: int, body: bytes):
    return store.put_chunk(
        "sess-0001", segment, track, chunk,
        read=_reader(body), expected_sha256=sha256_hex(body), expected_size=len(body),
    )


def test_t24_video_only_segment_completes_and_marks_ready(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video"]))
    a = chunk_bytes("t24-a", 512)
    b = chunk_bytes("t24-b", 256)
    _upload(store, 0, "video", 0, a)
    _upload(store, 0, "video", 1, b)
    summary = store.complete_segment(
        "sess-0001", 0, "video",
        total_chunks=2, size_bytes=len(a) + len(b), sha256=sha256_hex(a + b),
        extension=".mp4", duration_ms=2000, start_offset_ms=0,
    )
    assert summary["ready"] is True
    assert summary["missingTracks"] == []
    assembled = store.paths("sess-0001").segments / "segment-000000.video.mp4"
    assert assembled.read_bytes() == a + b
    assert store.paths("sess-0001").ready_marker(0).exists()
    meta = store.paths("sess-0001").segment_track_meta(0, "video").read_text(encoding="utf-8")
    assert '"sha256"' in meta


def test_t25_assembly_follows_chunk_index_not_upload_order(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video"]))
    first_half = chunk_bytes("t25-0", 400)
    second_half = chunk_bytes("t25-1", 400)
    _upload(store, 0, "video", 1, second_half)
    _upload(store, 0, "video", 0, first_half)
    store.complete_segment(
        "sess-0001", 0, "video",
        total_chunks=2, size_bytes=800, sha256=sha256_hex(first_half + second_half),
        extension=".webm", duration_ms=1000, start_offset_ms=5000,
    )
    assembled = store.paths("sess-0001").segments / "segment-000000.video.webm"
    assert assembled.read_bytes() == first_half + second_half


def test_t26_missing_chunk_blocks_completion(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video"]))
    a = chunk_bytes("t26-a", 512)
    _upload(store, 0, "video", 0, a)
    try:
        store.complete_segment(
            "sess-0001", 0, "video",
            total_chunks=2, size_bytes=len(a) * 2, sha256=sha256_hex(a + a),
            extension=".mp4", duration_ms=1000, start_offset_ms=0,
        )
        raise AssertionError("expected KabIngestValidationError")
    except KabIngestValidationError as exc:
        assert "missing" in exc.message
    assert not store.paths("sess-0001").ready_marker(0).exists()


def test_t27_declared_size_mismatch_blocks_completion(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video"]))
    a = chunk_bytes("t27-a", 512)
    _upload(store, 0, "video", 0, a)
    try:
        store.complete_segment(
            "sess-0001", 0, "video",
            total_chunks=1, size_bytes=len(a) + 1, sha256=sha256_hex(a),
            extension=".mp4", duration_ms=1000, start_offset_ms=0,
        )
        raise AssertionError("expected KabIngestValidationError")
    except KabIngestValidationError as exc:
        assert "size" in exc.message.lower()
    assert not (store.paths("sess-0001").segments / "segment-000000.video.mp4").exists()


def test_t28_ready_marker_only_after_all_required_tracks(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video", "audio"]))
    video = chunk_bytes("t28-v", 300)
    audio = chunk_bytes("t28-a", 300)

    _upload(store, 0, "video", 0, video)
    summary_video = store.complete_segment(
        "sess-0001", 0, "video",
        total_chunks=1, size_bytes=len(video), sha256=sha256_hex(video),
        extension=".mp4", duration_ms=1500, start_offset_ms=1000,
    )
    assert summary_video["ready"] is False
    assert summary_video["missingTracks"] == ["audio"]
    assert not store.paths("sess-0001").ready_marker(0).exists()

    offset_conflict = False
    try:
        store.complete_segment(
            "sess-0001", 0, "audio",
            total_chunks=1, size_bytes=len(audio), sha256=sha256_hex(audio),
            extension=".m4a", duration_ms=1500, start_offset_ms=9999,
        )
        raise AssertionError("expected offset conflict")
    except KabIngestConflict:
        offset_conflict = True
    assert offset_conflict

    _upload(store, 0, "audio", 0, audio)
    summary_audio = store.complete_segment(
        "sess-0001", 0, "audio",
        total_chunks=1, size_bytes=len(audio), sha256=sha256_hex(audio),
        extension=".m4a", duration_ms=1500, start_offset_ms=1000,
    )
    assert summary_audio["ready"] is True
    assert store.paths("sess-0001").ready_marker(0).exists()
    marker = store.paths("sess-0001").ready_marker(0).read_text(encoding="utf-8")
    assert "segment-000000.video.mp4" in marker
    assert "segment-000000.audio.m4a" in marker


def test_t28_segment_complete_idempotent_and_conflicting(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video"]))
    a = chunk_bytes("t28b", 256)
    _upload(store, 0, "video", 0, a)
    payload = dict(
        total_chunks=1, size_bytes=len(a), sha256=sha256_hex(a),
        extension=".mp4", duration_ms=1000, start_offset_ms=0,
    )
    first = store.complete_segment("sess-0001", 0, "video", **payload)
    second = store.complete_segment("sess-0001", 0, "video", **payload)
    assert first["ready"] is True and second["ready"] is True
    conflicting = dict(payload, size_bytes=len(a) + 5)
    try:
        store.complete_segment("sess-0001", 0, "video", **conflicting)
        raise AssertionError("expected conflict")
    except KabIngestConflict as exc:
        assert "different metadata" in exc.message
