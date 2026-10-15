"""W5 unit tests: streamed chunk finalization, bounded blocks, order/overlap.

Covers the server-side half of bounded chunking — media is accepted as a
readable stream (never whole bytes), written to an atomic temp file in
bounded blocks, and hashed/sized incrementally. Synthetic bytes only.
"""

from __future__ import annotations

import hashlib
import io
import threading

import pytest

from transcript_pipeline.live_capture.errors import ChunkTooLargeError, UploadCancelledError, ValidationError
from transcript_pipeline.live_capture.models import ChunkState
from transcript_pipeline.live_capture.service import CaptureService


@pytest.fixture
def service(tmp_path):
    return CaptureService(videos_root=tmp_path / "Videos")


def _media_path(tmp_path, session_id, index, extension=".webm"):
    from transcript_pipeline.live_capture.models import chunk_id

    return tmp_path / "Videos" / "live_capture" / session_id / "chunks" / f"{chunk_id(index)}{extension}"


# ── streaming finalization ─────────────────────────────────────────

def test_stream_finalize_writes_and_hashes_incrementally(service, tmp_path):
    session = service.create_session("stream")
    service.start_chunk(session.session_id)
    data = b"x" * 100_000
    chunk = service.finalize_chunk_stream(session.session_id, 0, io.BytesIO(data), media_extension=".webm")

    assert chunk.state is ChunkState.FINALIZED
    assert chunk.media_size_bytes == len(data)
    assert chunk.media_sha256 == hashlib.sha256(data).hexdigest()
    assert _media_path(tmp_path, session.session_id, 0).read_bytes() == data
    assert not list(_media_path(tmp_path, session.session_id, 0).parent.glob("*.tmp"))


def test_stream_finalize_reads_in_bounded_blocks(service, tmp_path, monkeypatch):
    monkeypatch.setattr("transcript_pipeline.live_capture.service.STREAM_BLOCK_SIZE", 7)
    session = service.create_session("bounded")
    service.start_chunk(session.session_id)
    data = b"abcdefghij" * 20  # 200 bytes -> many bounded reads

    reads: list[int] = []

    class CountingIO(io.BytesIO):
        def read(self, n=-1):
            reads.append(n)
            return super().read(n)

    chunk = service.finalize_chunk_stream(session.session_id, 0, CountingIO(data), media_extension=".webm")
    assert chunk.media_size_bytes == len(data)
    assert chunk.media_sha256 == hashlib.sha256(data).hexdigest()
    # Every read is bounded by the block size and there was more than one read.
    assert reads and all(n == 7 for n in reads)


def test_stream_finalize_rejects_empty_source(service):
    session = service.create_session("empty")
    service.start_chunk(session.session_id)
    with pytest.raises(ValidationError):
        service.finalize_chunk_stream(session.session_id, 0, io.BytesIO(b""), media_extension=".webm")
    assert service.get_session(session.session_id).chunks[0].state is ChunkState.RECORDING


def test_stream_finalize_enforces_max_bytes_and_leaves_no_temp(service, tmp_path):
    session = service.create_session("limit")
    service.start_chunk(session.session_id)
    with pytest.raises(ChunkTooLargeError):
        service.finalize_chunk_stream(
            session.session_id, 0, io.BytesIO(b"y" * 1000), media_extension=".webm", max_bytes=100
        )
    # The chunk stays RECORDING and no media/temp file is left behind.
    assert service.get_session(session.session_id).chunks[0].state is ChunkState.RECORDING
    chunks_dir = _media_path(tmp_path, session.session_id, 0).parent
    assert not list(chunks_dir.glob("*.tmp"))
    assert not _media_path(tmp_path, session.session_id, 0).exists()


# ── order / overlap ────────────────────────────────────────────────

def test_finalize_n_while_n1_recording_preserves_order(service, tmp_path):
    """Chunk 0 finalizes while chunk 1 is still RECORDING; order is preserved."""
    session = service.create_session("solapado")
    service.start_chunk(session.session_id)  # chunk 0
    service.start_chunk(session.session_id)  # chunk 1 (still recording)

    f0 = service.finalize_chunk_stream(session.session_id, 0, io.BytesIO(b"c0"), media_extension=".webm")

    state = service.get_session(session.session_id)
    assert f0.index == 0
    assert state.get_chunk(0).state is ChunkState.FINALIZED
    assert state.get_chunk(1).state is ChunkState.RECORDING

    f1 = service.finalize_chunk_stream(session.session_id, 1, io.BytesIO(b"c1"), media_extension=".webm")
    assert f1.index == 1

    finalized = service.finalized_chunks(session.session_id)
    assert [c.index for c in finalized] == [0, 1]
    assert _media_path(tmp_path, session.session_id, 0).read_bytes() == b"c0"
    assert _media_path(tmp_path, session.session_id, 1).read_bytes() == b"c1"


def test_rotation_keeps_chunk_identity_and_order(service):
    session = service.create_session("rotacion")
    for i in range(3):
        service.start_chunk(session.session_id)
        service.finalize_chunk_stream(session.session_id, i, io.BytesIO(f"chunk-{i}".encode()), media_extension=".webm")

    chunks = service.get_session(session.session_id).chunks
    assert [c.index for c in chunks] == [0, 1, 2]
    assert [c.chunk_id for c in chunks] == ["chunk-000000", "chunk-000001", "chunk-000002"]
    assert all(c.state is ChunkState.FINALIZED for c in chunks)
    assert [c.media_size_bytes for c in chunks] == [7, 7, 7]


def test_cancel_upload_removes_partial_and_retry_is_allowed(service, tmp_path):
    session = service.create_session("cancel-upload")
    service.start_chunk(session.session_id)
    cancelled = service.cancel_upload(session.session_id, 0)
    assert cancelled.state is ChunkState.UPLOAD_CANCELLED
    assert service.cancel_upload(session.session_id, 0).state is ChunkState.UPLOAD_CANCELLED
    retried = service.retry_cancelled_upload(session.session_id, 0)
    assert retried.state is ChunkState.RECORDING
    path = _media_path(tmp_path, session.session_id, 0)
    service.finalize_chunk(session.session_id, 0, b"retry")
    assert path.read_bytes() == b"retry"


def test_cancel_during_stream_aborts_atomic_write(service, tmp_path):
    session = service.create_session("cancel-inflight")
    service.start_chunk(session.session_id)
    entered = threading.Event()
    release = threading.Event()
    errors = []

    class BlockingStream:
        calls = 0

        def read(self, size):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                release.wait(timeout=5)
                return b"partial"
            return b""

    def upload():
        try:
            service.finalize_chunk_stream(session.session_id, 0, BlockingStream())
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=upload)
    worker.start()
    assert entered.wait(timeout=5)
    canceler = threading.Thread(target=lambda: service.cancel_upload(session.session_id, 0))
    canceler.start()
    assert service._upload_events[(session.session_id, 0)].wait(timeout=5)
    release.set()
    worker.join(timeout=5)
    canceler.join(timeout=5)
    assert not worker.is_alive() and not canceler.is_alive()
    assert errors and isinstance(errors[0], UploadCancelledError)
    assert service.get_session(session.session_id).chunks[0].state is ChunkState.UPLOAD_CANCELLED
    chunk_dir = _media_path(tmp_path, session.session_id, 0).parent
    assert not list(chunk_dir.glob("*.tmp"))
    assert not _media_path(tmp_path, session.session_id, 0).exists()
