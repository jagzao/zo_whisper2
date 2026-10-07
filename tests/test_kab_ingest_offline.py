"""T46: loopback-only / offline independence of the full local flow."""

from __future__ import annotations

import pytest

from transcript_pipeline.kab_ingest.worker import KabIngestWorker
from tests.kab_ingest_utils import (
    FakeTranscriber,
    LoopbackOnlyGuard,
    chunk_bytes,
    make_store,
    session_payload,
    sha256_hex,
)


def _reader(data: bytes):
    iterator = iter([data])
    return lambda _n: next(iterator, b"")


def test_t46_full_local_flow_never_leaves_loopback(tmp_path, monkeypatch):
    guard = LoopbackOnlyGuard().install(monkeypatch)

    store = make_store(tmp_path)
    store.create_session(session_payload(session_id="sess-offline", requiredTracks=["video"]))
    body = chunk_bytes("t46", 512)
    store.put_chunk(
        "sess-offline", 0, "video", 0,
        read=_reader(body), expected_sha256=sha256_hex(body), expected_size=len(body),
    )
    store.complete_segment(
        "sess-offline", 0, "video",
        total_chunks=1, size_bytes=len(body), sha256=sha256_hex(body),
        extension=".mp4", duration_ms=1000, start_offset_ms=0,
    )

    worker = KabIngestWorker(store, tmp_path, transcribe=FakeTranscriber(), poll_seconds=0.01)
    assert worker.run_once() == 1

    from transcript_pipeline.kab_ingest import transcripts

    transcripts.regenerate(store, tmp_path, "sess-offline")

    from transcript_pipeline.kab_ingest import consolidate

    consolidate.consolidate_session(
        store, tmp_path, "sess-offline", ended_at="2026-10-06T12:00:00+00:00", reason=None
    )

    assert store.read_worker_state("sess-offline")["segments"]["0"]["state"] == "PROCESSED"
    assert guard.violations == []


def test_no_ingest_module_references_external_endpoints():
    import re
    from pathlib import Path

    package_dir = Path(__file__).resolve().parents[1] / "src" / "transcript_pipeline" / "kab_ingest"
    url_pattern = re.compile(r"https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    hits = []
    for py_file in package_dir.glob("*.py"):
        for number, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if url_pattern.search(line):
                hits.append(f"{py_file.name}:{number}")
    assert hits == []
