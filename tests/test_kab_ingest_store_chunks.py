"""T17-T23: chunk upload semantics — streaming, idempotency, conflicts, limits."""

from __future__ import annotations

import pytest

from transcript_pipeline.kab_ingest.errors import (
    KabIngestConflict,
    KabIngestPayloadTooLarge,
    KabIngestValidationError,
)
from transcript_pipeline.kab_ingest.store import SessionStore
from tests.kab_ingest_utils import (
    chunk_bytes,
    make_store,
    session_payload,
    sha256_hex,
)


def _reader(data: bytes):
    iterator = iter([data])
    return lambda _n: next(iterator, b"")


def test_t17_chunk_round_trip(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload())
    body = chunk_bytes("t17", 5000)
    result = store.put_chunk(
        "sess-0001", 0, "video", 0,
        read=_reader(body), expected_sha256=sha256_hex(body), expected_size=len(body),
    )
    assert result["idempotent"] is False
    final = store.paths("sess-0001").chunk_file(0, "video", 0)
    assert final.read_bytes() == body
    assert not list(final.parent.glob("*.tmp"))


def test_t18_same_hash_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload())
    body = chunk_bytes("t18", 2048)
    first = store.put_chunk("sess-0001", 3, "audio", 7, read=_reader(body), expected_sha256=sha256_hex(body), expected_size=len(body))
    second = store.put_chunk("sess-0001", 3, "audio", 7, read=_reader(body), expected_sha256=sha256_hex(body), expected_size=len(body))
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert store.paths("sess-0001").chunk_file(3, "audio", 7).stat().st_size == len(body)


def test_t19_wrong_sha_is_rejected_and_never_persisted(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload())
    body = chunk_bytes("t19", 1024)
    with pytest.raises(KabIngestValidationError):
        store.put_chunk("sess-0001", 0, "video", 0, read=_reader(body), expected_sha256=sha256_hex(b"other"), expected_size=len(body))
    chunk_dir = store.paths("sess-0001").segment_chunks_dir(0, "video")
    assert not chunk_dir.exists() or not any(chunk_dir.iterdir())


def test_t20_duplicate_index_different_content_conflicts(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload())
    first = chunk_bytes("t20-a", 512)
    second = chunk_bytes("t20-b", 512)
    store.put_chunk("sess-0001", 0, "video", 0, read=_reader(first), expected_sha256=sha256_hex(first), expected_size=len(first))
    with pytest.raises(KabIngestConflict):
        store.put_chunk("sess-0001", 0, "video", 0, read=_reader(second), expected_sha256=sha256_hex(second), expected_size=len(second))
    assert store.paths("sess-0001").chunk_file(0, "video", 0).read_bytes() == first


def test_t21_chunk_size_limits_enforced(tmp_path):
    store = make_store(tmp_path, max_chunk_bytes=1024, max_session_bytes=10 * 1024**3)
    store.create_session(session_payload())
    body = chunk_bytes("t21", 2048)
    with pytest.raises(KabIngestPayloadTooLarge):
        store.put_chunk("sess-0001", 0, "video", 0, read=_reader(body), expected_sha256=sha256_hex(body), expected_size=len(body))
    short = body[:512]
    with pytest.raises(KabIngestValidationError):
        store.put_chunk("sess-0001", 0, "video", 1, read=_reader(short), expected_sha256=sha256_hex(body), expected_size=1024)
    with pytest.raises(KabIngestPayloadTooLarge):
        store.put_chunk("sess-0001", 0, "video", 2, read=_reader(body), expected_sha256=sha256_hex(body), expected_size=10**6)
    zero = b""
    with pytest.raises(KabIngestValidationError):
        store.put_chunk("sess-0001", 0, "video", 3, read=_reader(zero), expected_sha256=sha256_hex(zero), expected_size=0)
    chunk_dir = store.paths("sess-0001").segment_chunks_dir(0, "video")
    assert not chunk_dir.exists() or not any(chunk_dir.glob("*.chunk")) or not any(chunk_dir.glob("*.tmp"))


def test_t21_body_size_mismatch_never_persists(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload())
    body = chunk_bytes("t21b", 1024)
    truncated = body[:512]
    with pytest.raises(KabIngestValidationError):
        store.put_chunk("sess-0001", 1, "audio", 0, read=_reader(truncated), expected_sha256=sha256_hex(body), expected_size=len(body))
    chunk_dir = store.paths("sess-0001").segment_chunks_dir(1, "audio")
    assert not any(chunk_dir.glob("*.chunk")) and not any(chunk_dir.glob("*.tmp"))


def test_t22_session_byte_cap_enforced(tmp_path):
    store = make_store(tmp_path, max_chunk_bytes=1024, max_session_bytes=2048)
    store.create_session(session_payload())
    first = chunk_bytes("t22-a", 1024)
    second = chunk_bytes("t22-b", 1024)
    third = chunk_bytes("t22-c", 1024)
    store.put_chunk("sess-0001", 0, "video", 0, read=_reader(first), expected_sha256=sha256_hex(first), expected_size=len(first))
    store.put_chunk("sess-0001", 0, "video", 1, read=_reader(second), expected_sha256=sha256_hex(second), expected_size=len(second))
    with pytest.raises(KabIngestPayloadTooLarge):
        store.put_chunk("sess-0001", 0, "video", 2, read=_reader(third), expected_sha256=sha256_hex(third), expected_size=len(third))


def test_t23_corrupt_segment_never_completes(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload())
    a = chunk_bytes("t23-a", 512)
    b = chunk_bytes("t23-b", 512)
    store.put_chunk("sess-0001", 0, "video", 0, read=_reader(a), expected_sha256=sha256_hex(a), expected_size=len(a))
    store.put_chunk("sess-0001", 0, "video", 1, read=_reader(b), expected_sha256=sha256_hex(b), expected_size=len(b))
    with pytest.raises(KabIngestValidationError):
        store.complete_segment(
            "sess-0001", 0, "video",
            total_chunks=2,
            size_bytes=len(a) + len(b),
            sha256=sha256_hex(b"tampered"),
            extension=".mp4",
            duration_ms=1000,
            start_offset_ms=0,
        )
    paths = store.paths("sess-0001")
    assert not (paths.segments / "segment-000000.video.mp4").exists()
    assert not paths.segment_track_meta(0, "video").exists()
    assert not paths.ready_marker(0).exists()
    assert not list(paths.segments.glob("*.tmp"))


def test_store_construction_requires_positive_limits(tmp_path):
    with pytest.raises(ValueError):
        SessionStore(tmp_path / "x", max_chunk_bytes=0, max_session_bytes=100)
    with pytest.raises(ValueError):
        SessionStore(tmp_path / "x", max_chunk_bytes=10, max_session_bytes=0)
