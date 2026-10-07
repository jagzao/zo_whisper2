"""T42-T45: session completion consolidation — evidence preserved, deterministic,
no LLM, idempotent regeneration, availability booleans."""

from __future__ import annotations

import json
from pathlib import Path

from transcript_pipeline.documentation.engine import generate_documentation
from transcript_pipeline.kab_ingest import consolidate
from tests.kab_ingest_utils import (
    _make_frames,
    make_store,
    session_payload,
)


def _processed_session(tmp_path, *, with_docs: bool):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video"]))
    for segment_index in (0, 1):
        result = {
            "schemaVersion": 1,
            "sessionId": "sess-0001",
            "segmentIndex": segment_index,
            "startOffsetMs": segment_index * 10_000,
            "durationMs": 2000,
            "media": {"kind": "video", "file": f"segment-{segment_index:06d}.mp4"},
            "transcription": {
                "text": f"texto segmento {segment_index}",
                "language": "es",
                "durationSec": 2.0,
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": f"inicio {segment_index}"},
                    {"start": 1.0, "end": 2.0, "text": f"fin {segment_index}"},
                ],
            },
            "docsGenerated": with_docs,
            "docsManualDir": None,
            "framesDir": None,
        }
        if with_docs:
            frames_dir = _make_frames(tmp_path / "Frames", segment_index, f"segment-{segment_index:06d}.mp4")
            manual_dir = store.paths("sess-0001").completed / f"segment-{segment_index:06d}" / "manual"
            generate_documentation(
                frames_dir,
                f"segmento {segment_index}",
                manual_dir=manual_dir,
                ai_package_dir=store.paths("sess-0001").completed / f"segment-{segment_index:06d}" / "ai-package",
                project_config=None,
            )
            result["docsManualDir"] = manual_dir.resolve().relative_to(tmp_path.resolve()).as_posix()
            result["framesDir"] = frames_dir.resolve().relative_to(tmp_path.resolve()).as_posix()
        from transcript_pipeline.kab_ingest.atomic import atomic_write_json

        atomic_write_json(store.paths("sess-0001").result_file(segment_index), result)
        store.update_segment_state("sess-0001", segment_index, state="PROCESSED", attempts=1)
    from transcript_pipeline.kab_ingest import transcripts

    transcripts.regenerate(store, tmp_path, "sess-0001")
    return store


def test_t42_consolidation_preserves_evidence_and_applies_offsets(tmp_path):
    store = _processed_session(tmp_path, with_docs=True)
    completion = consolidate.consolidate_session(
        store, tmp_path, "sess-0001", ended_at="2026-10-06T12:00:00+00:00", reason="cliente cerro sesion"
    )
    steps = json.loads((tmp_path / "kab-inbox" / "sess-0001" / "completed" / "manual" / "steps.json").read_text(encoding="utf-8"))["steps"]
    assert [s["id"] for s in steps] == [f"step-{i:04d}" for i in range(1, len(steps) + 1)]
    second_segment_steps = [s for s in steps if s["timestamp"] >= 10.0]
    assert second_segment_steps, "offset shift failed: no steps at 10s+"
    for step in steps:
        assert step["evidence_source"] in ("transcript", "ocr", "transcript_ocr", "none")
        assert step["confidence"] in ("high", "medium", "low")
        assert "transcript_ref" in step
        assert step["instruction"]
    assert completion["status"] == "COMPLETED"
    assert completion["processedSegmentCount"] == 2


def test_t43_outputs_and_safe_relative_paths(tmp_path):
    store = _processed_session(tmp_path, with_docs=True)
    completion = consolidate.consolidate_session(store, tmp_path, "sess-0001", ended_at="2026-10-06T12:00:00+00:00", reason=None)
    completed = tmp_path / "kab-inbox" / "sess-0001" / "completed"
    for name in ("MANUAL.md", "MANUAL.pdf", "steps.json", "metadata.json"):
        assert (completed / "manual" / name).is_file(), name
    assert (completed / "manual" / "assets").is_dir()
    for name in ("manifest.json", "steps.json", "chunks.jsonl", "knowledge.md"):
        assert (completed / "ai-package" / name).is_file(), name
    assert (completed / "ai-package" / "assets").is_dir()

    text = json.dumps(completion)
    assert str(tmp_path) not in text
    for value in completion["outputs"].values():
        assert not Path(value).is_absolute()
        assert ".." not in value
        assert Path(value).drive == ""
    assert completion["availability"]["transcript"] is True
    assert completion["availability"]["manual"] is True
    assert completion["availability"]["aiPackage"] is True
    assert completion["outputs"]["manual"] == "completed/manual"
    assert completion["outputs"]["aiPackage"] == "completed/ai-package"


def test_t44_no_llm_and_no_external_output_in_consolidation(tmp_path, monkeypatch):
    from transcript_pipeline.llm.guard import ExternalLLMBlockedError

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("consolidation must never call the LLM service")

    import transcript_pipeline.documentation.engine as engine

    monkeypatch.setattr(engine, "_ai_service", type("Blocked", (), {"describe_frame_with_prompt": staticmethod(_forbidden)})())
    monkeypatch.setattr(engine, "_VISION_AVAILABLE", True)
    monkeypatch.setattr(engine, "_OCR_AVAILABLE", False)

    store = _processed_session(tmp_path, with_docs=True)
    completion = consolidate.consolidate_session(store, tmp_path, "sess-0001", ended_at="2026-10-06T12:00:00+00:00", reason=None)
    steps = json.loads((tmp_path / "kab-inbox" / "sess-0001" / "completed" / "manual" / "steps.json").read_text(encoding="utf-8"))["steps"]
    assert all(step["visual_description"] is None for step in steps)
    assert completion["availability"]["manual"] is True


def test_t45_consolidation_is_deterministic_and_idempotent(tmp_path):
    store = _processed_session(tmp_path, with_docs=True)
    first = consolidate.consolidate_session(store, tmp_path, "sess-0001", ended_at="2026-10-06T12:00:00+00:00", reason=None)
    completed = tmp_path / "kab-inbox" / "sess-0001" / "completed"
    manual_before = (completed / "manual" / "MANUAL.md").read_bytes()
    chunks_before = (completed / "ai-package" / "chunks.jsonl").read_bytes()
    steps_before = (completed / "manual" / "steps.json").read_bytes()
    completion_before = (completed / "session.complete.json").read_bytes()

    second = consolidate.consolidate_session(store, tmp_path, "sess-0001", ended_at="2026-10-06T12:00:00+00:00", reason=None)
    assert second == first
    assert (completed / "manual" / "MANUAL.md").read_bytes() == manual_before
    assert (completed / "ai-package" / "chunks.jsonl").read_bytes() == chunks_before
    assert (completed / "manual" / "steps.json").read_bytes() == steps_before
    assert (completed / "session.complete.json").read_bytes() == completion_before
