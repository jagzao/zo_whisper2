from types import SimpleNamespace

from transcript_pipeline.file_tracker import FileTracker


def _make_file(tmp_path, name="clip.mp3", content=b"fake audio bytes"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_new_file_is_not_processed(tmp_path):
    tracker = FileTracker(db_path=tmp_path / "db.json")
    audio = _make_file(tmp_path)
    assert tracker.is_file_processed(audio) is False


def test_mark_as_processed_then_detected(tmp_path):
    tracker = FileTracker(db_path=tmp_path / "db.json")
    audio = _make_file(tmp_path)
    tracker.mark_as_processed(audio, "completed")
    assert tracker.is_file_processed(audio) is True


def test_hash_changes_when_content_changes(tmp_path):
    tracker = FileTracker(db_path=tmp_path / "db.json")
    audio = _make_file(tmp_path, content=b"version 1")
    hash_a = tracker.get_file_hash(audio)

    audio.write_bytes(b"version 2 - different content")
    hash_b = tracker.get_file_hash(audio)

    assert hash_a != hash_b


def test_database_persists_across_instances(tmp_path):
    db_path = tmp_path / "db.json"
    audio = _make_file(tmp_path)

    tracker_a = FileTracker(db_path=db_path)
    tracker_a.mark_as_processed(audio, "completed")

    tracker_b = FileTracker(db_path=db_path)
    assert tracker_b.is_file_processed(audio) is True


def test_get_statistics_counts_hash_entries(tmp_path):
    tracker = FileTracker(db_path=tmp_path / "db.json")
    audio = _make_file(tmp_path)
    tracker.mark_as_processed(audio, "completed")

    stats = tracker.get_statistics()
    assert stats["total_files"] == 1
    assert stats["status_breakdown"] == {"completed": 1}


def test_defaults_to_settings_hash_mode(tmp_path, monkeypatch):
    # Settings is a frozen dataclass — patch the module-level SETTINGS name
    # file_tracker.py imports, not an attribute on the (immutable) instance.
    fake_settings = SimpleNamespace(file_tracker_hash_mode="full")
    monkeypatch.setattr("transcript_pipeline.file_tracker.SETTINGS", fake_settings)
    tracker = FileTracker(db_path=tmp_path / "db.json")
    assert tracker.hash_mode == "full"


def test_explicit_hash_mode_overrides_settings(tmp_path):
    tracker = FileTracker(db_path=tmp_path / "db.json", hash_mode="full")
    assert tracker.hash_mode == "full"


def test_full_hash_mode_reads_entire_file(tmp_path):
    tracker = FileTracker(db_path=tmp_path / "db.json", hash_mode="full")
    audio = _make_file(tmp_path, content=b"x" * 100_000)
    hash_a = tracker.get_file_hash(audio)

    # Change a byte far past the "fast" mode's first-8KB window — full mode
    # must still detect it; fast mode (by design) would not.
    with open(audio, "r+b") as f:
        f.seek(50_000)
        f.write(b"Y")
    hash_b = tracker.get_file_hash(audio)

    assert hash_a != hash_b


def test_fast_hash_mode_ignores_changes_past_first_8kb(tmp_path):
    tracker = FileTracker(db_path=tmp_path / "db.json", hash_mode="fast")
    audio = _make_file(tmp_path, content=b"x" * 100_000)
    stat = audio.stat()
    hash_a = tracker.get_file_hash(audio)

    with open(audio, "r+b") as f:
        f.seek(50_000)
        f.write(b"Y")
    # Preserve mtime to isolate the "content changed past 8KB, fast mode
    # can't see it" behavior from "mtime changed, fast mode would catch it".
    import os

    os.utime(audio, (stat.st_atime, stat.st_mtime))
    hash_b = tracker.get_file_hash(audio)

    assert hash_a == hash_b


def test_fast_and_full_modes_produce_different_hashes_for_same_file(tmp_path):
    audio = _make_file(tmp_path, content=b"identical content")
    fast_tracker = FileTracker(db_path=tmp_path / "db.json", hash_mode="fast")
    full_tracker = FileTracker(db_path=tmp_path / "db2.json", hash_mode="full")

    assert fast_tracker.get_file_hash(audio) != full_tracker.get_file_hash(audio)
