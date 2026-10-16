"""W6 unit tests: server processing-chunk aggregation from ACKed fragments.

Covers ordered aggregation on the recorded timeline, the ~duration boundary
using short fake duration metadata, the force-finalized partial tail, durable
fragment->chunk mapping, retry-after-assembly-failure (without re-upload) and
the guarantee that source fragments are never deleted. Synthetic media only —
a deterministic fake assembler stands in for FFmpeg; real FFmpeg synthetic
media is covered separately in `test_live_capture_assembly.py`.
"""

from __future__ import annotations

import io
import json

import pytest

from transcript_pipeline.live_capture.errors import AssemblyError, ValidationError
from transcript_pipeline.live_capture.models import ChunkState, PROCESSING_STATE_FINALIZED, PROCESSING_STATE_RETRYABLE
from transcript_pipeline.live_capture.service import CaptureService


def _fake_assembler(paths, dest):
    """Deterministic stand-in for FFmpeg: ordered byte concatenation."""
    from pathlib import Path

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"".join(Path(p).read_bytes() for p in paths))


@pytest.fixture
def service(tmp_path):
    return CaptureService(videos_root=tmp_path / "Videos", assembler=_fake_assembler)


def _session_dir(tmp_path, session_id):
    return tmp_path / "Videos" / "live_capture" / session_id


def _upload(service, session_id, seq, *, duration_ms=None, offset_ms=None, data=None):
    fragment_id = f"fragment-{seq:06d}"
    payload = data if data is not None else f"seg-{seq}".encode()
    return service.upload_fragment(
        session_id,
        fragment_id,
        seq,
        io.BytesIO(payload),
        duration_ms=duration_ms,
        recorded_offset_ms=offset_ms,
        recorded_at="2026-10-15T09:00:00+00:00",
    )


# ── recorded timeline metadata ─────────────────────────────────────

def test_fragment_records_and_persists_recorded_timeline(service):
    session = service.create_session("timeline")
    fragment = _upload(service, session.session_id, 1, duration_ms=1500, offset_ms=0)
    assert fragment.duration_ms == 1500
    assert fragment.recorded_offset_ms == 0
    assert fragment.recorded_at == "2026-10-15T09:00:00+00:00"

    reloaded = service.list_fragments(session.session_id)
    assert reloaded[0].duration_ms == 1500
    assert reloaded[0].recorded_offset_ms == 0


def test_project_id_inherits_to_fragments_processing_mapping_and_chunk(service):
    session = service.create_session("project-owned", chunk_duration_sec=1, project_id="Zo Interviews")
    fragment = _upload(service, session.session_id, 1, duration_ms=1000, offset_ms=0)
    mapping = service.list_processing_chunks(session.session_id)[0]
    chunk = service.get_session(session.session_id).chunks[0]
    assert session.project_id == "Zo Interviews"
    assert fragment.project_id == "Zo Interviews"
    assert mapping.project_id == "Zo Interviews"
    assert chunk.project_id == "Zo Interviews"


def test_fragment_rejects_negative_duration(service):
    session = service.create_session("bad-duration")
    with pytest.raises(ValidationError):
        _upload(service, session.session_id, 1, duration_ms=-1)


# ── boundary on recorded timeline ──────────────────────────────────

def test_no_processing_chunk_before_duration_threshold(service):
    session = service.create_session("below", chunk_duration_sec=3)
    _upload(service, session.session_id, 1, duration_ms=1000, offset_ms=0)
    _upload(service, session.session_id, 2, duration_ms=1000, offset_ms=1000)

    assert len(service.get_session(session.session_id).chunks) == 0
    assert service.list_processing_chunks(session.session_id) == []


def test_full_chunk_finalizes_at_duration_threshold(service):
    session = service.create_session("threshold", chunk_duration_sec=3)
    for seq in range(1, 4):
        _upload(service, session.session_id, seq, duration_ms=1000, offset_ms=(seq - 1) * 1000)

    finalized = service.finalized_chunks(session.session_id)
    assert [c.index for c in finalized] == [0]
    assert finalized[0].state is ChunkState.FINALIZED
    assert finalized[0].recorded_at == "2026-10-15T09:00:00+00:00"
    # The assembled media is the ordered concatenation of the three fragments.
    media = service.store.session_dir(session.session_id) / "chunks" / "chunk-000000.webm"
    assert media.read_bytes() == b"seg-1seg-2seg-3"

    mapping = service.list_processing_chunks(session.session_id)
    assert len(mapping) == 1
    assert mapping[0].state == PROCESSING_STATE_FINALIZED
    assert list(mapping[0].fragment_ids) == ["fragment-000001", "fragment-000002", "fragment-000003"]
    assert mapping[0].duration_ms == 3000
    assert mapping[0].recorded_at == finalized[0].recorded_at


def test_oversized_single_fragment_forms_its_own_chunk(service):
    session = service.create_session("oversize", chunk_duration_sec=3)
    _upload(service, session.session_id, 1, duration_ms=5000, offset_ms=0)
    finalized = service.finalized_chunks(session.session_id)
    assert [c.index for c in finalized] == [0]
    assert list(service.list_processing_chunks(session.session_id)[0].fragment_ids) == ["fragment-000001"]


# ── final partial tail on stop ─────────────────────────────────────

def test_drain_force_finalizes_partial_tail(service):
    session = service.create_session("tail", chunk_duration_sec=600)
    _upload(service, session.session_id, 1, duration_ms=1000, offset_ms=0)
    _upload(service, session.session_id, 2, duration_ms=1000, offset_ms=1000)

    # Below threshold while recording: nothing finalized automatically.
    assert service.finalized_chunks(session.session_id) == []

    chunk = service.drain_processing_chunks(session.session_id)
    assert chunk is not None and chunk.state is ChunkState.FINALIZED
    mapping = service.list_processing_chunks(session.session_id)
    assert len(mapping) == 1
    assert mapping[0].state == PROCESSING_STATE_FINALIZED
    assert mapping[0].duration_ms == 2000  # partial, below the 600s threshold
    assert list(mapping[0].fragment_ids) == ["fragment-000001", "fragment-000002"]


def test_drain_finalizes_complete_chunks_then_tail(service):
    session = service.create_session("complete-plus-tail", chunk_duration_sec=3)
    for seq in range(1, 6):
        _upload(service, session.session_id, seq, duration_ms=1000, offset_ms=(seq - 1) * 1000)

    # Fragments 1-3 already finalized the first complete chunk during upload.
    assert [c.index for c in service.finalized_chunks(session.session_id)] == [0]

    service.drain_processing_chunks(session.session_id)
    finalized = service.finalized_chunks(session.session_id)
    assert [c.index for c in finalized] == [0, 1]
    mapping = service.list_processing_chunks(session.session_id)
    assert [list(m.fragment_ids) for m in mapping] == [
        ["fragment-000001", "fragment-000002", "fragment-000003"],
        ["fragment-000004", "fragment-000005"],
    ]


def test_drain_without_fragments_is_a_noop(service):
    session = service.create_session("empty-tail")
    assert service.drain_processing_chunks(session.session_id) is None
    assert service.list_processing_chunks(session.session_id) == []
    assert service.get_session(session.session_id).chunks == ()


def test_missing_durations_do_not_auto_finalize_but_drain_tail(service):
    session = service.create_session("no-duration", chunk_duration_sec=600)
    _upload(service, session.session_id, 1)
    _upload(service, session.session_id, 2)
    assert service.get_session(session.session_id).chunks == ()

    service.drain_processing_chunks(session.session_id)
    assert [c.index for c in service.finalized_chunks(session.session_id)] == [0]


# ── retry / recovery without re-upload ─────────────────────────────

def test_assembly_failure_keeps_fragments_and_is_retryable(tmp_path):
    def failing_assembler(paths, dest):
        raise AssemblyError("synthetic assembly failure")

    failing = CaptureService(videos_root=tmp_path / "Videos", assembler=failing_assembler)
    session = failing.create_session("retry", chunk_duration_sec=3)
    for seq in range(1, 4):
        _upload(failing, session.session_id, seq, duration_ms=1000, offset_ms=(seq - 1) * 1000)

    # No chunk is claimed finalized; the map entry is retryable.
    assert failing.get_session(session.session_id).chunks == ()
    mapping = failing.list_processing_chunks(session.session_id)
    assert len(mapping) == 1
    assert mapping[0].state == PROCESSING_STATE_RETRYABLE
    assert mapping[0].last_error

    # Source fragments survive and are untouched.
    fragments = failing.list_fragments(session.session_id)
    assert [f.fragment_id for f in fragments] == ["fragment-000001", "fragment-000002", "fragment-000003"]
    for f in fragments:
        path = failing.store.fragment_media_path(session.session_id, f.fragment_id, f.media_extension)
        assert path.is_file() and path.stat().st_size > 0

    # A restarted service with a working assembler finalizes WITHOUT re-upload.
    restarted = CaptureService(videos_root=tmp_path / "Videos", assembler=_fake_assembler)
    chunk = restarted.finalize_processing_chunk(session.session_id)
    assert chunk is not None and chunk.state is ChunkState.FINALIZED
    assert [c.index for c in restarted.finalized_chunks(session.session_id)] == [0]
    assert restarted.list_processing_chunks(session.session_id)[0].state == PROCESSING_STATE_FINALIZED


def test_pending_entry_resumes_after_restart(tmp_path):
    """A reserved-but-unfinished (crash-after-reserve) entry is retried."""
    from transcript_pipeline.live_capture.models import (
        PROCESSING_STATE_PENDING,
        ProcessingChunkMapping,
    )

    root = tmp_path / "Videos"
    service = CaptureService(videos_root=root, assembler=_fake_assembler)
    session = service.create_session("restart-pending", chunk_duration_sec=600)
    _upload(service, session.session_id, 1, duration_ms=1000, offset_ms=0)
    _upload(service, session.session_id, 2, duration_ms=1000, offset_ms=1000)
    assert service.list_processing_chunks(session.session_id) == []

    # Simulate a crash after the range was reserved but before assembly ran.
    service.store.save_processing_map(
        session.session_id,
        [
            ProcessingChunkMapping(
                chunk_index=0,
                fragment_ids=("fragment-000001", "fragment-000002"),
                start_offset_ms=0,
                duration_ms=2000,
                state=PROCESSING_STATE_PENDING,
                created_at="2026-10-15T09:00:00+00:00",
            )
        ],
    )

    restarted = CaptureService(videos_root=root, assembler=_fake_assembler)
    chunk = restarted.finalize_processing_chunk(session.session_id)
    assert chunk is not None and chunk.state is ChunkState.FINALIZED
    assert restarted.list_processing_chunks(session.session_id)[0].state == PROCESSING_STATE_FINALIZED


# ── mapping durability / idempotency ───────────────────────────────

def test_mapping_is_durable_and_reloads(service, tmp_path):
    session = service.create_session("durable", chunk_duration_sec=3)
    for seq in range(1, 4):
        _upload(service, session.session_id, seq, duration_ms=1000, offset_ms=(seq - 1) * 1000)

    path = _session_dir(tmp_path, session.session_id) / "processing_chunks.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schemaVersion"] == 1
    assert raw["processingChunks"][0]["state"] == PROCESSING_STATE_FINALIZED

    reloaded = service.list_processing_chunks(session.session_id)
    assert reloaded[0].chunk_index == 0
    assert reloaded[0].chunk_extension == ".webm"


def test_drain_is_idempotent(service, tmp_path):
    session = service.create_session("idem", chunk_duration_sec=600)
    _upload(service, session.session_id, 1, duration_ms=1000, offset_ms=0)
    first = service.drain_processing_chunks(session.session_id)
    media = _session_dir(tmp_path, session.session_id) / "chunks" / "chunk-000000.webm"
    first_bytes = media.read_bytes()

    second = service.drain_processing_chunks(session.session_id)
    assert second is None
    assert len(service.get_session(session.session_id).chunks) == 1
    assert media.read_bytes() == first_bytes
    assert len(service.list_processing_chunks(session.session_id)) == 1
    assert first.index == 0


def test_original_fragments_are_never_deleted(service, tmp_path):
    session = service.create_session("keep-sources", chunk_duration_sec=3)
    for seq in range(1, 4):
        _upload(service, session.session_id, seq, duration_ms=1000, offset_ms=(seq - 1) * 1000)
    service.drain_processing_chunks(session.session_id)

    fragments = service.list_fragments(session.session_id)
    assert len(fragments) == 3
    for f in fragments:
        path = _session_dir(tmp_path, session.session_id) / "fragments" / f"{f.fragment_id}{f.media_extension}"
        assert path.is_file()
