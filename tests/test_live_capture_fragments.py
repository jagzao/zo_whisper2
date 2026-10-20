"""W5 unit/store tests: durable, idempotent upload fragments.

Covers the server half of short-fragment upload: bounded streaming into
atomic temp/fragment storage, hash+size ACK, idempotent replay of the same
ID with identical bytes, conflict on the same ID with different bytes,
ordering and durable-on-disk media. Synthetic bytes only; no real media.
"""

from __future__ import annotations

import hashlib
import io
import threading

import pytest

from transcript_pipeline.live_capture.errors import (
    FragmentConflictError,
    FragmentTooLargeError,
    ManifestCorruptError,
    SessionNotFoundError,
    ValidationError,
)
from transcript_pipeline.live_capture.models import FRAGMENT_STATE_ACKED, Fragment, fragment_id, validate_fragment_id
from transcript_pipeline.live_capture.service import CaptureService


@pytest.fixture
def service(tmp_path):
    return CaptureService(videos_root=tmp_path / "Videos")


def _fragment_media(tmp_path, session_id, fragment_id_value, extension=".webm"):
    return tmp_path / "Videos" / "live_capture" / session_id / "fragments" / f"{fragment_id_value}{extension}"


def _fragment_manifest(tmp_path, session_id):
    return tmp_path / "Videos" / "live_capture" / session_id / "fragments.json"


# ── model + identity validation ────────────────────────────────────

def test_fragment_id_helper_is_zero_padded_and_path_safe():
    assert fragment_id(1) == "fragment-000001"
    assert fragment_id(123456) == "fragment-123456"
    assert validate_fragment_id("fragment-000001") == "fragment-000001"


@pytest.mark.parametrize("bad", ["", " ", "../evil", "a/b", "frag ment", "x" * 65])
def test_fragment_id_rejects_unsafe_values(bad):
    with pytest.raises(ValidationError):
        validate_fragment_id(bad)


def test_fragment_model_rejects_non_acked_state_and_negative_sequence():
    with pytest.raises(ValidationError):
        Fragment(
            fragment_id="fragment-000001",
            sequence=1,
            created_at="2026-10-15T09:00:00+00:00",
            media_extension=".webm",
            media_size_bytes=3,
            media_sha256="abc",
            state="RECORDING",
        )
    with pytest.raises(ValidationError):
        Fragment(
            fragment_id="fragment-000001",
            sequence=-1,
            created_at="2026-10-15T09:00:00+00:00",
            media_extension=".webm",
            media_size_bytes=3,
            media_sha256="abc",
        )


# ── first upload / ACK / durable file ──────────────────────────────

def test_upload_fragment_acks_and_persists_durable_media(service, tmp_path):
    session = service.create_session("fragmentos")
    data = b"fragment-bytes" * 100
    fragment = service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(data))

    assert fragment.state == FRAGMENT_STATE_ACKED
    assert fragment.sequence == 1
    assert fragment.media_size_bytes == len(data)
    assert fragment.media_sha256 == hashlib.sha256(data).hexdigest()
    # Durable media file exists with the exact bytes and no temp leftovers.
    media = _fragment_media(tmp_path, session.session_id, "fragment-000001")
    assert media.read_bytes() == data
    assert not list(media.parent.glob("*.tmp"))
    # Manifest persisted by ID.
    listed = service.list_fragments(session.session_id)
    assert [f.fragment_id for f in listed] == ["fragment-000001"]


def test_upload_fragment_unknown_session_is_not_found(service):
    with pytest.raises(SessionNotFoundError):
        service.upload_fragment("sess-missing", "fragment-000001", 1, io.BytesIO(b"x"))


def test_upload_fragment_rejects_empty_body_without_persisting(service, tmp_path):
    session = service.create_session("vacio")
    with pytest.raises(ValidationError):
        service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(b""))
    assert service.list_fragments(session.session_id) == []
    assert not _fragment_manifest(tmp_path, session.session_id).exists()


def test_upload_fragment_enforces_max_bytes_and_leaves_no_temp(service, tmp_path):
    session = service.create_session("limite")
    with pytest.raises(FragmentTooLargeError):
        service.upload_fragment(
            session.session_id, "fragment-000001", 1, io.BytesIO(b"y" * 1000), max_bytes=100
        )
    assert service.list_fragments(session.session_id) == []
    fragments_dir = _fragment_media(tmp_path, session.session_id, "fragment-000001").parent
    assert not list(fragments_dir.glob("*.tmp"))


def test_interrupted_upload_leaves_nothing_and_retry_succeeds(service, tmp_path):
    session = service.create_session("interrumpido")
    fragments_dir = _fragment_media(tmp_path, session.session_id, "fragment-000001").parent

    class InterruptedIO:
        def __init__(self, first: bytes):
            self._first = first
            self._sent = False

        def read(self, n=-1):
            if not self._sent:
                self._sent = True
                return self._first
            raise ConnectionError("client disconnected mid-fragment")

    with pytest.raises(ConnectionError):
        service.upload_fragment(session.session_id, "fragment-000001", 1, InterruptedIO(b"partial-"))

    # The aborted POST leaves nothing durable: no manifest, no media, no temp.
    assert service.list_fragments(session.session_id) == []
    assert not _fragment_manifest(tmp_path, session.session_id).exists()
    assert not list(fragments_dir.glob("*.tmp"))

    # Retrying the same identity with the complete bytes ACKs exactly once.
    data = b"complete-fragment-bytes"
    fragment = service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(data))
    assert fragment.state == FRAGMENT_STATE_ACKED
    assert [f.fragment_id for f in service.list_fragments(session.session_id)] == ["fragment-000001"]
    assert _fragment_media(tmp_path, session.session_id, "fragment-000001").read_bytes() == data


def test_upload_fragment_reads_in_bounded_blocks(service, monkeypatch):
    monkeypatch.setattr("transcript_pipeline.live_capture.service.STREAM_BLOCK_SIZE", 7)
    session = service.create_session("bloques")
    reads: list[int] = []

    class CountingIO(io.BytesIO):
        def read(self, n=-1):
            reads.append(n)
            return super().read(n)

    fragment = service.upload_fragment(
        session.session_id, "fragment-000001", 1, CountingIO(b"abcdefghij" * 20)
    )
    assert fragment.media_size_bytes == 200
    assert reads and all(n == 7 for n in reads)


# ── idempotent replay ──────────────────────────────────────────────

def test_duplicate_identical_fragment_returns_same_ack_without_duplicate(service, tmp_path):
    session = service.create_session("replay")
    data = b"identical-bytes"
    first = service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(data))
    second = service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(data))

    assert second == first
    assert service.list_fragments(session.session_id).count(second) == 1
    # Media still exists, exactly one copy.
    assert _fragment_media(tmp_path, session.session_id, "fragment-000001").read_bytes() == data
    assert not list(_fragment_media(tmp_path, session.session_id, "fragment-000001").parent.glob("*.tmp"))


def test_duplicate_fragment_with_different_bytes_is_conflict(service, tmp_path):
    session = service.create_session("conflicto")
    service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(b"original"))
    with pytest.raises(FragmentConflictError):
        service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(b"different!!"))
    # Original bytes are never overwritten.
    assert _fragment_media(tmp_path, session.session_id, "fragment-000001").read_bytes() == b"original"
    assert len(service.list_fragments(session.session_id)) == 1


def test_duplicate_identical_fragment_repairs_missing_media(service, tmp_path):
    session = service.create_session("reparar")
    data = b"repair-me"
    service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(data))
    media = _fragment_media(tmp_path, session.session_id, "fragment-000001")
    media.unlink()  # simulate a lost file with a surviving manifest entry
    repaired = service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(data))
    assert repaired.media_sha256 == hashlib.sha256(data).hexdigest()
    assert media.read_bytes() == data


# ── ordering ───────────────────────────────────────────────────────

def test_fragments_are_listed_in_sequence_order(service):
    session = service.create_session("orden")
    # Upload out of order; listing must sort by sequence.
    service.upload_fragment(session.session_id, "fragment-000003", 3, io.BytesIO(b"third"))
    service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(b"first"))
    service.upload_fragment(session.session_id, "fragment-000002", 2, io.BytesIO(b"second"))

    listed = service.list_fragments(session.session_id)
    assert [f.sequence for f in listed] == [1, 2, 3]
    assert [f.fragment_id for f in listed] == [
        "fragment-000001",
        "fragment-000002",
        "fragment-000003",
    ]


# ── per-session concurrency ────────────────────────────────────────

def test_concurrent_identical_replay_writes_single_copy(service, tmp_path):
    session = service.create_session("concurrente")
    data = b"concurrent-identical"
    barrier = threading.Barrier(4)
    results: list[Fragment] = []
    errors: list[Exception] = []

    def upload():
        try:
            barrier.wait(timeout=5)
            results.append(service.upload_fragment(session.session_id, "fragment-000001", 1, io.BytesIO(data)))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=upload) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    assert len(results) == 4
    assert all(f.media_sha256 == hashlib.sha256(data).hexdigest() for f in results)
    assert len(service.list_fragments(session.session_id)) == 1
    assert _fragment_media(tmp_path, session.session_id, "fragment-000001").read_bytes() == data


def test_corrupt_fragment_manifest_is_reported_not_trusted(service, tmp_path):
    session = service.create_session("corrupto")
    manifest = _fragment_manifest(tmp_path, session.session_id)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ManifestCorruptError):
        service.list_fragments(session.session_id)
