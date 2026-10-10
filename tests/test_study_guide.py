"""Unit coverage for the per-video study guide (documentation/study_guide.py).

The LLM is mocked at the AIEnrichmentService boundary (module-level
`_llm_service`), matching how the engine tests mock `_vision_description`:
no network, no provider construction. Exercises the rendered section
contract, the privacy-guard block path, the two-phase chunking strategy for
long transcripts, and the never-raises guarantee.
"""
from __future__ import annotations

import json

import pytest

from transcript_pipeline.documentation import study_guide
from transcript_pipeline.llm.guard import ExternalLLMBlockedError

SYNTHESIS_JSON = {
    "overview": "The video walks through building a monthly P&G report in Excel, "
    "from raw data import to a printable summary.",
    "key_topics": [
        {
            "topic": "Pivot tables",
            "details": "Creating and refreshing pivot tables over the sales dump.",
            "timestamps": ["00:00:01"],
        },
        {"topic": "Printing setup", "details": "", "timestamps": []},
    ],
    "glossary": [
        {"term": "Pivot table", "definition": "A summary table that aggregates raw rows by dimensions."},
    ],
    "walkthrough": [
        {"point": "Insert a pivot table from the Insert ribbon", "timestamp": "00:00:06"},
        {"point": "Set print area from Page Layout", "timestamp": "not-a-number"},
    ],
    "questions": [
        {"question": "Which ribbon tab opens the PivotTable wizard?", "answer": "Insert"},
    ]
    * 10,
}

REQUIRED_SECTIONS = (
    "## Overview",
    "## Key Topics",
    "## Glossary",
    "## Screens, Excel & Tools Walkthrough",
    "## Practice Questions",
)


class FakeService:
    """Stands in for AIEnrichmentService; records every generate_text call."""

    def __init__(self, responder):
        self.calls: list[dict] = []
        self._responder = responder

    def generate_text(self, text, system_prompt, project_config=None, *, max_tokens=4000, temperature=0.2):
        self.calls.append(
            {"text": text, "system": system_prompt, "max_tokens": max_tokens, "temperature": temperature}
        )
        return self._responder(system_prompt, text)


@pytest.fixture
def guide_tree(tmp_path):
    """Pipeline-shaped tree: transcriptions root → <stem>_Frames/<stem>/manual
    plus the transcript .txt two levels above the frames dir."""
    frames_dir = tmp_path / "pg_report_Frames" / "pg_report"
    manual_dir = frames_dir / "manual"
    manual_dir.mkdir(parents=True)
    steps = {
        "source": {"video_name": "pg_report.mp4", "duration": 10.0, "language": "en"},
        "steps": [
            {
                "id": "step-0001", "order": 1, "title": "Open the report",
                "instruction": "Open the monthly report workbook.", "timestamp": 1.5,
                "ocr_text": None, "confidence": "high",
            },
            {
                "id": "step-0002", "order": 2, "title": "Insert pivot",
                "instruction": "Insert > PivotTable.", "timestamp": 6.0,
                "ocr_text": "Insert PivotTable", "confidence": "high",
            },
        ],
    }
    (manual_dir / "steps.json").write_text(json.dumps(steps), encoding="utf-8")
    (tmp_path / "pg_report.txt").write_text(
        "short transcript about excel reports and pivot tables", encoding="utf-8"
    )
    return tmp_path, frames_dir, manual_dir


def test_generate_study_guide_writes_guide_with_all_sections(guide_tree, monkeypatch):
    base, frames_dir, manual_dir = guide_tree
    fake = FakeService(lambda system, text: json.dumps(SYNTHESIS_JSON))
    monkeypatch.setattr(study_guide, "_llm_service", fake)

    result = study_guide.generate_study_guide(manual_dir, frames_dir, "pg_report.mp4")

    assert result["status"] == "ok"
    assert result["path"] == str(manual_dir / "STUDY_GUIDE.md")
    guide = (manual_dir / "STUDY_GUIDE.md").read_text(encoding="utf-8")
    assert guide.startswith("# Study Guide — pg_report.mp4")
    for section in REQUIRED_SECTIONS:
        assert section in guide
    assert "AI-generated" in guide
    assert "Verify every claim against the video" in guide
    assert "Pivot tables" in guide
    assert "**Pivot table**" in guide
    assert "`00:00:06` — Insert a pivot table" in guide
    assert "PivotTable wizard" in guide
    # Short transcript → single phase, raw transcript sent to the synthesis call.
    assert len(fake.calls) == 1
    assert fake.calls[0]["system"] == study_guide._SYNTHESIS_SYSTEM_PROMPT
    assert "short transcript about excel reports" in fake.calls[0]["text"]
    assert fake.calls[0]["temperature"] == 0.2
    # Master index refreshed at the transcriptions root (frames_dir.parent.parent).
    assert (base / "INDEX.md").exists()


def test_blocked_by_guard_returns_blocked_without_file(guide_tree, monkeypatch):
    _, frames_dir, manual_dir = guide_tree

    def raise_blocked(system, text):
        raise ExternalLLMBlockedError("ALLOW_EXTERNAL_LLM is disabled")

    fake = FakeService(raise_blocked)
    monkeypatch.setattr(study_guide, "_llm_service", fake)

    result = study_guide.generate_study_guide(manual_dir, frames_dir, "pg_report.mp4")

    assert result["status"] == "blocked"
    assert "ALLOW_EXTERNAL_LLM" in result["error"]
    assert not (manual_dir / "STUDY_GUIDE.md").exists()


def test_long_transcript_is_chunked_before_synthesis(guide_tree, monkeypatch):
    base, frames_dir, manual_dir = guide_tree
    # 13k chars > 12k threshold → 2 chunks of ~10k with 200-char overlap.
    (base / "pg_report.txt").write_text("excel report word " * 723, encoding="utf-8")
    fake = FakeService(lambda system, text: json.dumps(SYNTHESIS_JSON))
    monkeypatch.setattr(study_guide, "_llm_service", fake)

    result = study_guide.generate_study_guide(manual_dir, frames_dir, "pg_report.mp4")

    assert result["status"] == "ok"
    assert result["chunks"] == 2
    chunk_calls = [c for c in fake.calls if c["system"] == study_guide._CHUNK_SYSTEM_PROMPT]
    synthesis_calls = [c for c in fake.calls if c["system"] == study_guide._SYNTHESIS_SYSTEM_PROMPT]
    assert len(chunk_calls) == 2
    assert len(synthesis_calls) == 1
    assert "Chunk 1/2" in chunk_calls[0]["text"]
    assert "Chunk 2/2" in chunk_calls[1]["text"]
    # The synthesis gets the chunk extractions, not the raw transcript again.
    assert "excel report word" not in synthesis_calls[0]["text"]
    assert (manual_dir / "STUDY_GUIDE.md").exists()


def test_chunk_splitting_produces_overlapping_covering_chunks():
    text = "x" * 25_000
    chunks = study_guide._chunk_transcript(text)
    assert all(len(c) <= study_guide._CHUNK_TARGET for c in chunks)
    # Coverage: the tail of one chunk reappears at the head of the next.
    for first, second in zip(chunks, chunks[1:]):
        assert second.startswith(first[len(first) - study_guide._CHUNK_OVERLAP :])
    # The last chunk reaches the end of the transcript.
    assert "".join(chunks).endswith("x" * 100)
    # Short transcript stays whole.
    assert study_guide._chunk_transcript("x" * 100) == ["x" * 100]


def test_llm_failure_is_non_fatal(guide_tree, monkeypatch):
    _, frames_dir, manual_dir = guide_tree

    def boom(system, text):
        raise RuntimeError("provider down")

    fake = FakeService(boom)
    monkeypatch.setattr(study_guide, "_llm_service", fake)

    result = study_guide.generate_study_guide(manual_dir, frames_dir, "pg_report.mp4")

    assert result["status"] == "failed"
    assert "provider down" in result["error"]
    assert not (manual_dir / "STUDY_GUIDE.md").exists()


def test_missing_transcript_and_steps_are_tolerated(tmp_path, monkeypatch):
    frames_dir = tmp_path / "orphan_Frames" / "orphan"
    manual_dir = frames_dir / "manual"
    manual_dir.mkdir(parents=True)
    fake = FakeService(lambda system, text: json.dumps(SYNTHESIS_JSON))
    monkeypatch.setattr(study_guide, "_llm_service", fake)

    result = study_guide.generate_study_guide(manual_dir, frames_dir, "orphan.mp4")

    assert result["status"] == "ok"
    assert "No transcript available" in fake.calls[0]["text"]
    assert (manual_dir / "STUDY_GUIDE.md").exists()


def test_unparseable_synthesis_json_reports_failure(guide_tree, monkeypatch):
    _, frames_dir, manual_dir = guide_tree
    fake = FakeService(lambda system, text: "sorry, I cannot answer in JSON")
    monkeypatch.setattr(study_guide, "_llm_service", fake)

    result = study_guide.generate_study_guide(manual_dir, frames_dir, "pg_report.mp4")

    assert result["status"] == "failed"
    assert not (manual_dir / "STUDY_GUIDE.md").exists()
