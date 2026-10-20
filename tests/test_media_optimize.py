"""Validated optimization + provenance tests (L01-L07).

Deterministic tests inject a fake prober/encoder so every state transition and
failure path is proven without real media. One ffmpeg-backed success test
exercises the real encode/publish/cleanup path with a synthetic lavfi clip.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from transcript_pipeline.media import optimize
from transcript_pipeline.media.optimize import (
    CLEANUP_PENDING,
    FAILED,
    OPTIMIZED_SOURCE_REMOVED,
    OPTIMIZED_SOURCE_RETAINED,
    Probe,
    ProvenanceStore,
    optimize_media,
    retry_source_cleanup,
    validate_candidate,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not available")


def _key(path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


class FakeMedia:
    """Prober whose per-path facts are configured; size always comes from disk."""

    def __init__(self, *, default_video=True, default_audio=False, default_duration: float | None = 10.0):
        self.facts: dict[str, dict] = {}
        self.default = {
            "ok": True,
            "video": default_video,
            "audio": default_audio,
            "duration": default_duration,
        }

    def set(self, path, **facts) -> None:
        self.facts[_key(path)] = {**self.default, **facts}

    def prober(self, path) -> Probe:
        p = Path(path)
        cfg = self.facts.get(_key(p), self.default)
        size = p.stat().st_size if p.is_file() else 0
        ok = cfg["ok"] and p.is_file()
        return Probe(
            path=p,
            ok=ok,
            has_video=cfg["video"],
            has_audio=cfg["audio"],
            duration=cfg["duration"] if ok else None,
            size_bytes=size,
        )


def _writer(payload: bytes, *, produce=True):
    def _compress(src, dst):
        if not produce:
            return False
        Path(dst).write_bytes(payload)
        return True

    return _compress


@pytest.fixture
def layout(tmp_path):
    src = tmp_path / "Video_compress" / "clip.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"S" * 4096)
    dest = tmp_path / "Videos" / "general"
    return tmp_path, src, dest


# ── L01 success ─────────────────────────────────────────────────────


def test_success_publishes_validated_output_and_removes_source(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)

    result = optimize_media(
        src, dest, base_path=base, prober=media.prober,
        compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json",
    )

    assert result.cleanup_state == OPTIMIZED_SOURCE_REMOVED
    assert not src.exists()
    assert result.output is not None and result.output.is_file()
    assert result.bytes_saved == 4096 - 1024
    records = json.loads((base / "prov.json").read_text(encoding="utf-8"))
    record = next(iter(records.values()))
    assert record["sourceRelative"] == "Video_compress/clip.mp4"
    assert record["cleanupState"] == OPTIMIZED_SOURCE_REMOVED
    assert record["outputSize"] == 1024


# ── L02 encoder/stream failures ─────────────────────────────────────


def test_encoder_failure_retains_source(layout):
    base, src, dest = layout
    media = FakeMedia()
    media.set(src)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"", produce=False), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert src.exists()
    assert not dest.exists() or not any(dest.iterdir())


def test_missing_output_retains_source(layout):
    base, src, dest = layout
    media = FakeMedia()

    def _no_write(src_, dst_):
        return True

    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_no_write, provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert src.exists()


def test_candidate_without_video_stream_retains_source(layout):
    base, src, dest = layout
    media = FakeMedia(default_video=False)
    media.set(src, video=True)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert src.exists()
    assert not (dest / "clip.mp4").exists()


# ── L03 duration / audio policy ─────────────────────────────────────


def test_duration_mismatch_beyond_tolerance_retains_source(layout):
    base, src, dest = layout
    media = FakeMedia(default_duration=30.0)
    media.set(src, duration=10.0)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert "duration" in (result.reason or "")
    assert src.exists()


def test_audio_dropped_retains_source(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=False)
    media.set(src, audio=True, duration=10.0)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert "audio" in (result.reason or "")
    assert src.exists()


def test_duration_unknown_on_output_retains_source(layout):
    base, src, dest = layout
    media = FakeMedia(default_duration=None)
    media.set(src, duration=10.0)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert src.exists()


# ── L04 size reduction ──────────────────────────────────────────────


def test_output_not_smaller_retains_source(layout):
    base, src, dest = layout
    media = FakeMedia()
    media.set(src)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 4096), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert "smaller" in (result.reason or "")
    assert src.exists()


def test_validate_candidate_requires_meaningful_reduction():
    source = Probe(Path("s"), True, True, None, 10.0, 1000)
    equal = Probe(Path("c"), True, True, None, 10.0, 1000)
    assert validate_candidate(source, equal) is not None
    smaller = Probe(Path("c"), True, True, None, 10.0, 980)
    assert validate_candidate(source, smaller) is None


# ── L05 collision / publish / persistence failures ──────────────────


def test_collision_publishes_unique_name(layout):
    base, src, dest = layout
    dest.mkdir(parents=True)
    existing = dest / "clip.mp4"
    existing.write_bytes(b"E" * 500)
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    media.set(existing, video=True, audio=True, duration=10.0)

    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == OPTIMIZED_SOURCE_REMOVED
    assert existing.read_bytes() == b"E" * 500
    output = result.output
    assert output is not None and output != existing and output.is_file()
    assert not src.exists()


def test_atomic_publish_failure_retains_source(layout, monkeypatch):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    real_replace = os.replace

    def guarded_replace(a, b):
        if ".optimized" in str(a):
            raise OSError("publish boom")
        return real_replace(a, b)

    monkeypatch.setattr(optimize.os, "replace", guarded_replace)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert src.exists()


def test_provenance_persistence_failure_retains_source(layout, monkeypatch):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)

    def boom(self, record):
        raise OSError("disk full")

    monkeypatch.setattr(ProvenanceStore, "upsert", boom)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == FAILED
    assert src.exists()


# ── L06 retry safety / no overwrite ─────────────────────────────────


def test_retry_after_publish_reuses_output_without_overwrite(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")

    first = optimize_media(src, dest, base_path=base, prober=media.prober,
                           compressor=_writer(b"O" * 1024), provenance=store, remove_source=False)
    assert first.cleanup_state == OPTIMIZED_SOURCE_RETAINED
    assert src.exists()
    outputs = list(dest.glob("*.mp4"))
    assert len(outputs) == 1

    second = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance=store, remove_source=True)
    assert second.cleanup_state == OPTIMIZED_SOURCE_REMOVED
    assert second.output == first.output
    assert not src.exists()
    assert list(dest.glob("*.mp4")) == outputs


def test_invalid_hash_matching_output_is_not_reused(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")

    first = optimize_media(src, dest, base_path=base, prober=media.prober,
                           compressor=_writer(b"O" * 1024), provenance=store, remove_source=False)
    assert first.cleanup_state == OPTIMIZED_SOURCE_RETAINED
    existing = first.output
    assert existing is not None and existing.is_file()
    existing_sha = optimize.sha256_file(existing)

    # Bytes (and therefore hash) are unchanged, but the file no longer validates.
    media.set(existing, video=False, audio=True, duration=10.0)

    second = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance=store, remove_source=True)

    assert optimize.sha256_file(existing) == existing_sha
    assert existing.exists()
    assert second.output is not None and second.output != existing
    assert second.output.is_file()
    assert second.cleanup_state == OPTIMIZED_SOURCE_REMOVED
    assert not src.exists()


def test_invalid_hash_matching_output_does_not_qualify_to_remove_source(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")

    first = optimize_media(src, dest, base_path=base, prober=media.prober,
                           compressor=_writer(b"O" * 1024), provenance=store, remove_source=False)
    existing = first.output
    assert existing is not None and existing.is_file()
    existing_sha = optimize.sha256_file(existing)

    media.set(existing, video=False, audio=True, duration=10.0)

    # The re-encoded candidate is also rejected, so the source must survive: the
    # invalid but hash-matching existing output never qualifies for removal.
    second = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 4096), provenance=store, remove_source=True)

    assert optimize.sha256_file(existing) == existing_sha
    assert existing.exists()
    assert second.cleanup_state == FAILED
    assert src.exists()


# ── L07 cleanup failure + retry ─────────────────────────────────────


def test_removal_failure_sets_cleanup_pending(layout, monkeypatch):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    real_unlink = Path.unlink

    def guarded_unlink(self, *args, **kwargs):
        if Path(self) == src:
            raise OSError("locked by another process")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", guarded_unlink)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")
    assert result.cleanup_state == CLEANUP_PENDING
    assert src.exists()
    records = json.loads((base / "prov.json").read_text(encoding="utf-8"))
    assert next(iter(records.values()))["cleanupState"] == CLEANUP_PENDING


def test_retry_cleanup_completes_after_pending(layout, monkeypatch):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")
    real_unlink = Path.unlink

    def guarded_unlink(self, *args, **kwargs):
        if Path(self) == src:
            raise OSError("locked by another process")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", guarded_unlink)
    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance=store)
    assert result.cleanup_state == CLEANUP_PENDING
    assert next(iter(store.load().values()))["cleanupState"] == CLEANUP_PENDING
    monkeypatch.undo()

    output_relative = next(iter(store.load()))
    state = retry_source_cleanup(output_relative, base_path=base, provenance=store, prober=media.prober)
    assert state == OPTIMIZED_SOURCE_REMOVED
    assert not src.exists()
    output = result.output
    assert output is not None and output.is_file()


def test_retry_cleanup_refuses_when_source_changed(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")
    optimize_media(src, dest, base_path=base, prober=media.prober,
                   compressor=_writer(b"O" * 1024), provenance=store, remove_source=False)
    output_relative = next(iter(store.load()))
    records = store.load()
    records[output_relative]["cleanupState"] = CLEANUP_PENDING
    store.save(records)

    src.write_bytes(b"S" * 42)
    state = retry_source_cleanup(output_relative, base_path=base, provenance=store)
    assert state == CLEANUP_PENDING
    assert src.exists()


def test_retry_cleanup_proceeds_only_when_pending(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")

    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance=store, remove_source=False)
    assert result.cleanup_state == OPTIMIZED_SOURCE_RETAINED
    output_relative = next(iter(store.load()))

    # A retained record is never re-processed, even though the output hash still
    # matches and the output is a valid optimization.
    state = retry_source_cleanup(output_relative, base_path=base, provenance=store, prober=media.prober)

    assert state == OPTIMIZED_SOURCE_RETAINED
    assert src.exists()
    assert store.load()[output_relative]["cleanupState"] == OPTIMIZED_SOURCE_RETAINED


def test_retry_cleanup_does_not_delete_when_state_not_pending(layout):
    base, src, dest = layout
    dest.mkdir(parents=True)
    output = dest / "clip.mp4"
    output.write_bytes(b"O" * 1024)
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    media.set(output, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")

    for terminal_state in (OPTIMIZED_SOURCE_REMOVED, OPTIMIZED_SOURCE_RETAINED):
        _write_record(
            store, "Videos/general/clip.mp4",
            cleanupState=terminal_state,
            sourceRelative="Video_compress/clip.mp4",
            outputRelative="Videos/general/clip.mp4",
            sourceSha256=optimize.sha256_file(src),
            outputSha256=optimize.sha256_file(output),
        )

        state = retry_source_cleanup(
            "Videos/general/clip.mp4", base_path=base, provenance=store, prober=media.prober,
        )

        assert state == terminal_state
        assert src.exists()
        assert store.load()["Videos/general/clip.mp4"]["cleanupState"] == terminal_state


def test_retry_cleanup_rereads_source_before_unlink(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    store = ProvenanceStore(base / "prov.json")
    optimize_media(src, dest, base_path=base, prober=media.prober,
                   compressor=_writer(b"O" * 1024), provenance=store, remove_source=False)
    output_relative = next(iter(store.load()))
    records = store.load()
    records[output_relative]["cleanupState"] = CLEANUP_PENDING
    store.save(records)

    real_prober = media.prober

    def mutating_prober(path):
        probe = real_prober(path)
        if Path(path) == src:
            with src.open("ab") as handle:
                handle.write(b"LATE")
        return probe

    # The source only changes during the pre-unlink probe, i.e. after the first
    # hash check. The pre-unlink re-read must still notice and keep the source.
    state = retry_source_cleanup(
        output_relative, base_path=base, provenance=store, prober=mutating_prober,
    )

    assert state == CLEANUP_PENDING
    assert src.exists()
    assert src.read_bytes().endswith(b"LATE")
    assert store.load()[output_relative]["cleanupState"] == CLEANUP_PENDING


# ── L08 source integrity before unlink ──────────────────────────────


def test_source_mutation_during_encode_retains_modified_bytes(layout):
    base, src, dest = layout
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    original = src.read_bytes()

    def mutating_compress(src_, dst_):
        Path(dst_).write_bytes(b"O" * 1024)
        with Path(src_).open("ab") as handle:
            handle.write(b"MUTATED")
        return True

    result = optimize_media(
        src, dest, base_path=base, prober=media.prober,
        compressor=mutating_compress, provenance_path=base / "prov.json",
    )

    assert result.cleanup_state == CLEANUP_PENDING
    assert result.reason is not None and "changed" in result.reason
    assert src.exists()
    assert src.read_bytes() == original + b"MUTATED"
    assert result.output is not None and result.output.is_file()


# ── L09 cleanup containment / traversal rejection ───────────────────


def _write_record(store: ProvenanceStore, key: str, **fields) -> None:
    store.save({key: {"cleanupState": CLEANUP_PENDING, **fields}})


def test_retry_cleanup_rejects_source_traversal_and_preserves_sentinel(layout):
    base, _src, dest = layout
    dest.mkdir(parents=True)
    output = dest / "clip.mp4"
    output.write_bytes(b"O" * 1024)
    sentinel = base.parent / "sentinel_traversal.txt"
    sentinel.write_bytes(b"KEEP")
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "Videos/general/clip.mp4",
        sourceRelative="../sentinel_traversal.txt",
        outputRelative="Videos/general/clip.mp4",
        sourceSha256=optimize.sha256_file(sentinel),
        outputSha256=optimize.sha256_file(output),
    )

    state = retry_source_cleanup("Videos/general/clip.mp4", base_path=base, provenance=store)

    assert state == FAILED
    assert sentinel.exists() and sentinel.read_bytes() == b"KEEP"


def test_retry_cleanup_rejects_absolute_source_and_preserves_sentinel(layout):
    base, _src, dest = layout
    dest.mkdir(parents=True)
    output = dest / "clip.mp4"
    output.write_bytes(b"O" * 1024)
    sentinel = base.parent / "sentinel_absolute.txt"
    sentinel.write_bytes(b"KEEP")
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "Videos/general/clip.mp4",
        sourceRelative=str(sentinel),
        outputRelative="Videos/general/clip.mp4",
        sourceSha256=optimize.sha256_file(sentinel),
        outputSha256=optimize.sha256_file(output),
    )

    state = retry_source_cleanup("Videos/general/clip.mp4", base_path=base, provenance=store)

    assert state == FAILED
    assert sentinel.exists() and sentinel.read_bytes() == b"KEEP"


def test_retry_cleanup_rejects_symlink_escape_and_preserves_sentinel(layout):
    base, _src, dest = layout
    dest.mkdir(parents=True)
    output = dest / "clip.mp4"
    output.write_bytes(b"O" * 1024)
    sentinel = base.parent / "sentinel_symlink.txt"
    sentinel.write_bytes(b"KEEP")
    link = base / "escape_link.mp4"
    try:
        link.symlink_to(sentinel)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "Videos/general/clip.mp4",
        sourceRelative="escape_link.mp4",
        outputRelative="Videos/general/clip.mp4",
        sourceSha256=optimize.sha256_file(sentinel),
        outputSha256=optimize.sha256_file(output),
    )

    state = retry_source_cleanup("Videos/general/clip.mp4", base_path=base, provenance=store)

    assert state == FAILED
    assert sentinel.exists() and sentinel.read_bytes() == b"KEEP"
    assert link.exists()


def test_retry_cleanup_unlinks_internal_symlink_not_target(layout):
    base, _src, dest = layout
    dest.mkdir(parents=True)
    output = dest / "clip.mp4"
    output.write_bytes(b"O" * 1024)
    target = base / "Video_compress" / "target.mp4"
    target.write_bytes(b"T" * 4096)
    link = base / "Video_compress" / "link.mp4"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")
    media = FakeMedia(default_duration=10.0)
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "Videos/general/clip.mp4",
        sourceRelative="Video_compress/link.mp4",
        outputRelative="Videos/general/clip.mp4",
        sourceSha256=optimize.sha256_file(link),
        outputSha256=optimize.sha256_file(output),
    )

    state = retry_source_cleanup(
        "Videos/general/clip.mp4", base_path=base, provenance=store, prober=media.prober,
    )

    assert state == OPTIMIZED_SOURCE_REMOVED
    assert not link.is_symlink()
    assert target.exists() and target.read_bytes() == b"T" * 4096


def test_retry_cleanup_rejects_output_traversal_and_preserves_sentinel(layout):
    base, _src, _dest = layout
    outside = base.parent / "outside_output.mp4"
    outside.write_bytes(b"OUTSIDE")
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "k",
        sourceRelative="Video_compress/clip.mp4",
        outputRelative="../outside_output.mp4",
        sourceSha256="x",
        outputSha256=optimize.sha256_file(outside),
    )

    state = retry_source_cleanup("k", base_path=base, provenance=store)

    assert state == FAILED
    assert outside.exists() and outside.read_bytes() == b"OUTSIDE"


def test_retry_cleanup_rejects_in_root_source_outside_video_compress(layout):
    base, _src, dest = layout
    dest.mkdir(parents=True)
    output = dest / "clip.mp4"
    output.write_bytes(b"O" * 1024)
    stray = base / "notes.txt"
    stray.write_bytes(b"KEEP")
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "Videos/general/clip.mp4",
        sourceRelative="notes.txt",
        outputRelative="Videos/general/clip.mp4",
        sourceSha256=optimize.sha256_file(stray),
        outputSha256=optimize.sha256_file(output),
    )

    state = retry_source_cleanup("Videos/general/clip.mp4", base_path=base, provenance=store)

    assert state == FAILED
    assert stray.exists() and stray.read_bytes() == b"KEEP"


def test_retry_cleanup_rejects_in_root_output_outside_videos(layout):
    base, src, _dest = layout
    other = base / "other"
    other.mkdir()
    stray_output = other / "out.mp4"
    stray_output.write_bytes(b"O" * 1024)
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "other/out.mp4",
        sourceRelative="Video_compress/clip.mp4",
        outputRelative="other/out.mp4",
        sourceSha256=optimize.sha256_file(src),
        outputSha256=optimize.sha256_file(stray_output),
    )

    state = retry_source_cleanup("other/out.mp4", base_path=base, provenance=store)

    assert state == FAILED
    assert src.exists() and src.read_bytes() == b"S" * 4096
    assert stray_output.exists() and stray_output.read_bytes() == b"O" * 1024


def test_retry_cleanup_keeps_pending_when_output_invalid(layout):
    base, src, dest = layout
    dest.mkdir(parents=True)
    output = dest / "clip.mp4"
    output.write_bytes(b"O" * 1024)
    media = FakeMedia(default_video=False)
    store = ProvenanceStore(base / "prov.json")
    _write_record(
        store, "Videos/general/clip.mp4",
        sourceRelative="Video_compress/clip.mp4",
        outputRelative="Videos/general/clip.mp4",
        sourceSha256=optimize.sha256_file(src),
        outputSha256=optimize.sha256_file(output),
    )

    state = retry_source_cleanup(
        "Videos/general/clip.mp4", base_path=base, provenance=store, prober=media.prober,
    )

    assert state == CLEANUP_PENDING
    assert src.exists()
    record = store.load()["Videos/general/clip.mp4"]
    assert record["cleanupState"] == CLEANUP_PENDING
    assert "valid" in (record.get("reason") or "")


def test_result_from_record_rejects_outside_root_output(layout):
    base, src, _dest = layout
    probe = Probe(path=src, ok=True, has_video=True, has_audio=None, duration=10.0, size_bytes=4096)

    traversal = {"outputRelative": "../escape.mp4", "cleanupState": OPTIMIZED_SOURCE_REMOVED}
    assert optimize._result_from_record(src, traversal, base, probe).output is None

    absolute = {
        "outputRelative": str(base.parent / "escape.mp4"),
        "cleanupState": OPTIMIZED_SOURCE_REMOVED,
    }
    assert optimize._result_from_record(src, absolute, base, probe).output is None

    inside = {"outputRelative": "Videos/general/clip.mp4", "cleanupState": OPTIMIZED_SOURCE_REMOVED}
    resolved = optimize._result_from_record(src, inside, base, probe).output
    assert resolved is not None and resolved.name == "clip.mp4"


# ── L10 fail-closed containment for source/destination ──────────────


def _forbidden_prober(path):
    raise AssertionError("prober must not run for a rejected path")


def _forbidden_compressor(src, dst):
    raise AssertionError("compressor must not run for a rejected path")


def test_external_source_rejected_before_probe(layout):
    base, _src, dest = layout
    outside = base.parent / "external_source.mp4"
    outside.write_bytes(b"S" * 4096)

    result = optimize_media(
        outside, dest, base_path=base,
        prober=_forbidden_prober, compressor=_forbidden_compressor,
        provenance_path=base / "prov.json",
    )

    assert result.cleanup_state == FAILED
    assert "source" in (result.reason or "").lower()
    assert outside.exists() and outside.read_bytes() == b"S" * 4096
    assert not (base / "prov.json").exists()


def test_external_destination_rejected_before_encode(layout):
    base, src, _dest = layout
    outside_dir = base.parent / "external_dest"

    result = optimize_media(
        src, outside_dir, base_path=base,
        prober=_forbidden_prober, compressor=_forbidden_compressor,
        provenance_path=base / "prov.json",
    )

    assert result.cleanup_state == FAILED
    assert "destination" in (result.reason or "").lower()
    assert src.exists() and src.read_bytes() == b"S" * 4096
    assert not outside_dir.exists()


def test_source_symlink_escape_rejected_and_preserved(layout):
    base, _src, dest = layout
    sentinel = base.parent / "sentinel_source_escape.mp4"
    sentinel.write_bytes(b"KEEP")
    link = base / "Video_compress" / "escape.mp4"
    try:
        link.symlink_to(sentinel)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")

    result = optimize_media(
        link, dest, base_path=base,
        prober=_forbidden_prober, compressor=_forbidden_compressor,
        provenance_path=base / "prov.json",
    )

    assert result.cleanup_state == FAILED
    assert sentinel.exists() and sentinel.read_bytes() == b"KEEP"
    assert link.exists()


def test_destination_symlink_escape_rejected_and_preserved(layout):
    base, src, _dest = layout
    outside_dir = base.parent / "external_dest_dir"
    outside_dir.mkdir()
    videos = base / "Videos"
    videos.mkdir(parents=True, exist_ok=True)
    link = videos / "escape"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")

    result = optimize_media(
        src, link, base_path=base,
        prober=_forbidden_prober, compressor=_forbidden_compressor,
        provenance_path=base / "prov.json",
    )

    assert result.cleanup_state == FAILED
    assert src.exists() and src.read_bytes() == b"S" * 4096
    assert not any(outside_dir.iterdir())
    assert link.exists()


# ── L11 fail-closed source metadata ─────────────────────────────────


def test_source_without_duration_fails_closed_before_encode(layout):
    base, src, dest = layout
    media = FakeMedia()
    media.set(src, duration=None)
    result = optimize_media(
        src, dest, base_path=base, prober=media.prober,
        compressor=_forbidden_compressor, provenance_path=base / "prov.json",
    )
    assert result.cleanup_state == FAILED
    assert "duration" in (result.reason or "")
    assert src.exists()


@pytest.mark.parametrize("bad_duration", [0.0, -1.0, float("inf"), float("nan")])
def test_source_with_nonpositive_or_nonfinite_duration_fails_closed(layout, bad_duration):
    base, src, dest = layout
    media = FakeMedia()
    media.set(src, duration=bad_duration)
    result = optimize_media(
        src, dest, base_path=base, prober=media.prober,
        compressor=_forbidden_compressor, provenance_path=base / "prov.json",
    )
    assert result.cleanup_state == FAILED
    assert "duration" in (result.reason or "")
    assert src.exists()


def test_source_with_zero_size_fails_closed_before_encode(tmp_path):
    base = tmp_path
    src = base / "Video_compress" / "empty.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"")
    media = FakeMedia()
    media.set(src, duration=10.0)
    result = optimize_media(
        src, base / "Videos" / "general", base_path=base, prober=media.prober,
        compressor=_forbidden_compressor, provenance_path=base / "prov.json",
    )
    assert result.cleanup_state == FAILED
    assert "empty" in (result.reason or "")
    assert src.exists()


# ── L12 suffix conversion publishes MP4 without overwriting ─────────


def test_webm_source_publishes_mp4_without_overwriting_existing(tmp_path):
    base = tmp_path
    src = base / "Video_compress" / "clip.webm"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"S" * 4096)
    dest = base / "Videos" / "general"
    dest.mkdir(parents=True)
    existing = dest / "clip.mp4"
    existing.write_bytes(b"E" * 500)
    media = FakeMedia(default_audio=True)
    media.set(src, video=True, audio=True, duration=10.0)
    media.set(existing, video=True, audio=True, duration=10.0)

    result = optimize_media(src, dest, base_path=base, prober=media.prober,
                            compressor=_writer(b"O" * 1024), provenance_path=base / "prov.json")

    assert result.cleanup_state == OPTIMIZED_SOURCE_REMOVED
    assert existing.read_bytes() == b"E" * 500
    assert result.output is not None
    assert result.output.suffix == ".mp4" and result.output != existing
    assert not src.exists()
    records = json.loads((base / "prov.json").read_text(encoding="utf-8"))
    record = next(iter(records.values()))
    assert record["sourceRelative"] == "Video_compress/clip.webm"
    assert record["outputRelative"].endswith(".mp4")


# ── real ffmpeg path ────────────────────────────────────────────────

@requires_ffmpeg
def test_real_ffmpeg_success_removes_source(tmp_path):
    base = tmp_path
    src_dir = base / "Video_compress"
    src_dir.mkdir(parents=True)
    src = src_dir / "sample.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc2=duration=3:size=128x128:rate=15", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
        capture_output=True, check=True, timeout=120,
    )
    dest = base / "Videos" / "general"

    result = optimize_media(src, dest, base_path=base, provenance_path=base / "prov.json")

    assert result.succeeded, result.reason
    assert not src.exists()
    assert result.output is not None and result.output.is_file()
    output_size = result.output_size
    assert output_size is not None and output_size < result.source_size


@requires_ffmpeg
def test_real_ffmpeg_webm_source_publishes_playable_mp4(tmp_path):
    base = tmp_path
    src_dir = base / "Video_compress"
    src_dir.mkdir(parents=True)
    src = src_dir / "sample.webm"
    # The video bitrate is deliberately high so the H.265/AAC output is
    # genuinely smaller; an already-efficient source would (correctly) be kept.
    # The Opus track proves non-MP4 source audio survives the conversion.
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=duration=3:size=320x240:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libvpx-vp9", "-b:v", "4000k", "-pix_fmt", "yuv420p",
         "-c:a", "libopus", "-b:a", "128k", str(src)],
        capture_output=True, check=True, timeout=300,
    )
    source_probe = optimize.default_prober(src)
    assert source_probe.duration is not None and source_probe.duration > 0
    assert source_probe.has_audio is True

    dest = base / "Videos" / "general"

    result = optimize_media(src, dest, base_path=base, provenance_path=base / "prov.json")

    assert result.succeeded, result.reason
    assert result.output is not None and result.output.is_file()
    assert result.output.suffix == ".mp4"

    published = optimize.default_prober(result.output)
    assert published.ok and published.has_video
    assert published.has_audio is True
    assert published.duration is not None
    assert abs(published.duration - source_probe.duration) <= optimize.duration_tolerance(source_probe.duration)
    assert published.size_bytes > 0
    output_size = result.output_size
    assert output_size is not None and output_size < result.source_size

    # A full decode of both streams must succeed before the source is trusted as
    # safely removed.
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(result.output), "-f", "null", "-"],
        capture_output=True, text=True, timeout=300,
    )
    assert decoded.returncode == 0, decoded.stderr

    assert not src.exists()

    record = next(iter(json.loads((base / "prov.json").read_text(encoding="utf-8")).values()))
    assert record["sourceRelative"].endswith(".webm")
    assert record["outputRelative"].endswith(".mp4")
    assert record["cleanupState"] == OPTIMIZED_SOURCE_REMOVED
