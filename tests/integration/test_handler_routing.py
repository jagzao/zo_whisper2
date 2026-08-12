"""Regression coverage for the MasterProcessor <-> handler routing contract.

Anchor bug (pre-fix): `handler.process(...)` returned a bare `bool` that
`run_transcription_and_routing` discarded, so a failing handler still got
`tracker.mark_as_processed(audio_path, "completed_routed")`. These tests
build a bare `MasterProcessor` (bypassing `__init__`'s real filesystem/model
setup) wired to fakes, so they run without faster-whisper or real project
folders.
"""

from pathlib import Path

import pytest

from transcript_pipeline.handlers.base import HandlerResult
from transcript_pipeline.pipeline import master as master_module


class _FakeTracker:
    def __init__(self):
        self.marked: dict[str, str] = {}

    def is_file_processed(self, path: Path) -> bool:
        return False

    def mark_as_processed(self, path: Path, status: str) -> None:
        self.marked[str(path)] = status


class _FakeProcessor:
    def __init__(self, audio_files: list[Path]):
        self._audio_files = audio_files
        self.tracker = _FakeTracker()

    def find_audio_files(self) -> list[Path]:
        return self._audio_files

    def transcribe_file(self, path: Path) -> dict:
        return {"text": "fake transcript", "frame_info": None}

    def save_transcription(self, path: Path, result: dict) -> None:
        pass

    def _integrate_transcription_with_frames(self, result: dict, frame_info) -> None:
        pass


class _FakeHandler:
    def __init__(self, result: HandlerResult):
        self._result = result

    def process(self, transcription_data, original_file_path, project_config=None) -> HandlerResult:
        return self._result


@pytest.fixture
def bare_processor(tmp_path):
    """A MasterProcessor with __init__'s heavy setup skipped."""
    instance = master_module.MasterProcessor.__new__(master_module.MasterProcessor)
    instance.base_path = tmp_path
    instance.projects = [{"name": "TestProj", "match": {"prefix": ["tp_"]}}]
    instance._handlers = {}
    instance._organize_map = []
    instance.icecream_music = None
    instance.icecream_videos = None
    return instance


def _run_with_fake_processor(monkeypatch, bare_processor, audio_files):
    fake = _FakeProcessor(audio_files)
    monkeypatch.setattr(master_module, "SimpleScanProcessor", lambda: fake)
    success = bare_processor.run_transcription_and_routing()
    return fake.tracker.marked, success


def test_handler_success_marks_completed_routed(monkeypatch, bare_processor, tmp_path):
    audio = tmp_path / "tp_meeting.mp3"
    bare_processor._handlers["TestProj"] = _FakeHandler(HandlerResult.completed())
    marked, success = _run_with_fake_processor(monkeypatch, bare_processor, [audio])
    assert marked[str(audio)] == "completed_routed"
    assert success is True


def test_handler_permanent_failure_marks_failed_routed_not_completed(monkeypatch, bare_processor, tmp_path):
    audio = tmp_path / "tp_meeting.mp3"
    bare_processor._handlers["TestProj"] = _FakeHandler(HandlerResult.failed("bad data"))
    marked, success = _run_with_fake_processor(monkeypatch, bare_processor, [audio])
    # This is the anchor regression: a failed handler must never be marked
    # "completed_routed" (that was the pre-fix bug in master.py:133-145).
    assert marked[str(audio)] == "failed_routed"
    assert marked[str(audio)] != "completed_routed"
    assert success is False


def test_handler_retryable_failure_leaves_file_unmarked(monkeypatch, bare_processor, tmp_path):
    audio = tmp_path / "tp_meeting.mp3"
    bare_processor._handlers["TestProj"] = _FakeHandler(
        HandlerResult.failed("LLM endpoint timed out", retryable=True)
    )
    marked, success = _run_with_fake_processor(monkeypatch, bare_processor, [audio])
    # Deliberately not marked at all, so the next RUN_MAX_QUALITY.bat retries it.
    assert str(audio) not in marked
    assert success is False


def test_handler_exception_does_not_crash_the_batch(monkeypatch, bare_processor, tmp_path):
    class _RaisingHandler:
        def process(self, *args, **kwargs):
            raise RuntimeError("boom")

    audio = tmp_path / "tp_meeting.mp3"
    bare_processor._handlers["TestProj"] = _RaisingHandler()
    marked, success = _run_with_fake_processor(monkeypatch, bare_processor, [audio])
    # The outer try/except in run_transcription_and_routing catches it; the
    # file is left unmarked (not silently "completed") and the batch reports failure.
    assert str(audio) not in marked
    assert success is False


def test_no_matching_project_marks_completed(monkeypatch, bare_processor, tmp_path):
    audio = tmp_path / "unmatched_file.mp3"
    marked, success = _run_with_fake_processor(monkeypatch, bare_processor, [audio])
    assert marked[str(audio)] == "completed"
    assert success is True


def test_matched_project_without_handler_marks_completed(monkeypatch, bare_processor, tmp_path):
    # matches "TestProj" via prefix, but no handler registered for it
    audio = tmp_path / "tp_no_handler.mp3"
    marked, success = _run_with_fake_processor(monkeypatch, bare_processor, [audio])
    assert marked[str(audio)] == "completed"
    assert success is True
