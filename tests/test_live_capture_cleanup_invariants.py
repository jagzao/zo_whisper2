"""Live Capture temporary-media cleanup invariants (L10-L12 / AC-04).

Synthetic media and a deterministic fake assembler: proves the final recording
and manifest survive, and that source fragments/chunks are retained unless the
final is verified and every processing chunk completed.
"""

from __future__ import annotations

import io

import pytest

from transcript_pipeline.live_capture.service import CaptureService


def _fake_assembler(paths, dest):
    from pathlib import Path

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"".join(Path(p).read_bytes() for p in paths))


@pytest.fixture
def service(tmp_path):
    return CaptureService(videos_root=tmp_path / "Videos", assembler=_fake_assembler)


def _upload(service, session_id, seq, *, duration_ms, offset_ms):
    service.upload_fragment(
        session_id, f"fragment-{seq:06d}", seq, io.BytesIO(f"seg-{seq}".encode()),
        duration_ms=duration_ms, recorded_offset_ms=offset_ms,
        recorded_at="2026-10-15T09:00:00+00:00",
    )


def _four_fragments(service, *, chunk_duration_sec=2):
    session = service.create_session("cleanup-invariants", chunk_duration_sec=chunk_duration_sec)
    for seq in range(1, 5):
        _upload(service, session.session_id, seq, duration_ms=1000, offset_ms=(seq - 1) * 1000)
    service.drain_processing_chunks(session.session_id)
    service.finalize_session(session.session_id)
    return session


def _fragment_files(service, session_id):
    return [
        service.store.fragment_media_path(session_id, f"fragment-{seq:06d}", ".webm")
        for seq in range(1, 5)
    ]


def test_hash_mismatch_retains_fragments_and_blocks_cleanup(service):
    session = _four_fragments(service)
    final = service.finalize_session_media(session.session_id)
    final_path = service.store.final_media_path(session.session_id, final["extension"])

    final_path.write_bytes(b"corrupted-final-bytes")

    for chunk in service.get_session(session.session_id).chunks:
        service.mark_processing(session.session_id, chunk.index)
        service.complete_processing(session.session_id, chunk.index, transcript_available=True)

    assert service.cleanup_temporary_media_if_safe(session.session_id) is False
    assert all(path.is_file() for path in _fragment_files(service, session.session_id))
    assert final_path.is_file()


def test_cancelled_processing_retains_fragments(service):
    session = _four_fragments(service)
    service.finalize_session_media(session.session_id)

    first_chunk = service.get_session(session.session_id).chunks[0]
    service.mark_processing(session.session_id, first_chunk.index)
    service.cancel_processing(session.session_id, first_chunk.index)

    assert service.cleanup_temporary_media_if_safe(session.session_id) is False
    assert all(path.is_file() for path in _fragment_files(service, session.session_id))


def test_successful_processing_removes_only_session_temporaries(service):
    session = _four_fragments(service)
    final = service.finalize_session_media(session.session_id)
    final_path = service.store.final_media_path(session.session_id, final["extension"])

    for chunk in service.get_session(session.session_id).chunks:
        service.mark_processing(session.session_id, chunk.index)
        service.complete_processing(session.session_id, chunk.index, transcript_available=True)

    assert all(not path.exists() for path in _fragment_files(service, session.session_id))
    # Final media, manifest and provenance remain playable/inspectable.
    assert final_path.is_file()
    assert service.store.load_session(session.session_id).final_media == final
    assert len(service.list_fragments(session.session_id)) == 4
