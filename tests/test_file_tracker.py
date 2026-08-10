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
