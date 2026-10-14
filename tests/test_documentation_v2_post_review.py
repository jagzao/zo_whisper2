from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from transcript_pipeline.documentation.compaction import build_synthesis_blocks
from transcript_pipeline.documentation.evidence import build_evidence_timeline
from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2
from transcript_pipeline.documentation.regenerate_v2 import (
    UpstreamWorkAttemptedError,
    default_upstream_guard,
    install_upstream_guard,
    main as regenerate_main,
    undo_guard,
)
from transcript_pipeline.documentation.synthesis import _validate_fragment_shape
from transcript_pipeline.documentation.synthesis import SynthesisService
from transcript_pipeline.documentation.evidence import EvidenceTimeline, EvidenceItem


def test_saved_segments_are_authoritative_over_sparse_frames(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (tmp_path / "long_recording_segments.json").write_text(json.dumps({
        "segments": [{"start": i * 60, "end": i * 60 + 4, "text": f"spoken {i}"} for i in range(12)]
    }), encoding="utf-8")
    mapping = {
        "video_info": {"name": "long_recording.mp4", "duration": 800},
        "frames": [{"frame_file": f"f{i}.png", "timestamp": i * 300} for i in range(3)],
        "transcription_mapping": {f"f{i}.png": {"full_text": f"mapped {i}"} for i in range(3)},
    }
    timeline = build_evidence_timeline(mapping, source_media="long_recording.mp4", frames_dir=frames)
    speech = [item.transcript_excerpt for item in timeline.items if item.transcript_excerpt]
    assert speech == [f"spoken {i}" for i in range(12)]


def test_saved_segment_absence_uses_mapping_fallback():
    timeline = build_evidence_timeline({
        "video_info": {"name": "fallback.mp4"},
        "frames": [{"frame_file": "f.png", "timestamp": 7}],
        "transcription_mapping": {"f.png": {"full_text": "mapped speech"}},
    })
    assert [item.transcript_excerpt for item in timeline.facts()] == ["mapped speech"]


def test_builtin_upstream_guard_intercepts_and_restores_targets():
    guard = default_upstream_guard()
    undos = install_upstream_guard(guard)
    try:
        for dotted in guard:
            parts = dotted.split(".")
            target = __import__(parts[0])
            for part in parts[1:]:
                target = getattr(target, part)
            with pytest.raises(UpstreamWorkAttemptedError):
                target()
    finally:
        undo_guard(undos)
    assert undos
    assert all(original is getattr(parent, attr) for parent, original, attr in undos)


@pytest.mark.parametrize("raw", [
    "{}", '{"foo":"bar"}', '{"sections":[null]}',
    '{"sections":[],"procedures":[],"glossary":[]}',
    '{"sections":[{"sectionType":"REFERENCE","claims":[{"text":"x","evidenceIds":[]}]}]}',
])
def test_strict_schema_rejects_empty_unknown_and_malformed(raw):
    assert _validate_fragment_shape(raw)[0] is False


def test_strict_schema_accepts_grounded_reference_claim():
    raw = json.dumps({"sections": [{"sectionType": "REFERENCE", "title": "Ref", "summary": "s", "claims": [
        {"text": "Grounded fact", "evidenceIds": ["E-001"]}
    ]}], "procedures": [], "glossary": []})
    assert _validate_fragment_shape(raw)[0] is True


def test_compaction_overflow_marks_coverage_incomplete_and_service_fails_closed():
    mapping = {
        "video_info": {"name": "overflow.mp4"},
        "frames": [{"frame_file": f"f{i}", "timestamp": float(i)} for i in range(5)],
        "transcription_mapping": {f"f{i}": {"full_text": f"speech {i} " + "x" * 60} for i in range(5)},
    }
    timeline = build_evidence_timeline(mapping)
    compacted = build_synthesis_blocks(timeline, target_chars=70, hard_chars=100, max_blocks=1).build()
    assert not compacted.coverage_complete
    assert compacted.omitted_evidence_ids


def test_compaction_coverage_failure_makes_no_provider_request():
    class Provider:
        provider_type = "local"
        calls = 0

        def generate_summary(self, *args, **kwargs):
            self.calls += 1
            return "{}"

    class Guard:
        def check(self, *args):
            return None

    timeline = EvidenceTimeline(items=[EvidenceItem(
        evidence_id="E-001", ordinal=1, timestamp_start=0, timestamp_end=1,
        confidence="high", reviewed=False, evidence_source="transcript",
        transcript_excerpt="x" * 30_000,
    )])
    provider = Provider()
    result = SynthesisService(provider, Guard()).synthesize(timeline, "REFERENCE", {})
    assert result.status == "SYNTHESIS_INVALID"
    assert result.errors == ["input_coverage_exceeded"]
    assert provider.calls == 0


def test_any_failed_block_invalidates_synthesis(monkeypatch):
    from transcript_pipeline.documentation import synthesis as module
    from transcript_pipeline.documentation.compaction import CompactionResult, SynthesisBlock

    timeline = EvidenceTimeline(items=[EvidenceItem(
        evidence_id=f"E-{i:03d}", ordinal=i, timestamp_start=i, timestamp_end=i,
        confidence="high", reviewed=False, evidence_source="transcript", transcript_excerpt=f"speech {i}",
    ) for i in range(1, 4)])
    blocks = [SynthesisBlock(i, i, i, (f"E-{i:03d}",), f"speech {i}", "", 10) for i in range(1, 4)]
    class Builder:
        def build(self):
            return CompactionResult(blocks=blocks)
    monkeypatch.setattr(module, "build_synthesis_blocks", lambda *a, **k: Builder())

    class Provider:
        provider_type = "local"
        calls = 0
        repair_block_two = False
        def generate_summary(self, text, **kwargs):
            self.calls += 1
            if not text.startswith("{") and self.repair_block_two:
                return "still malformed"
            payload = json.loads(text) if text.startswith("{") else {}
            idx = payload.get("block", {}).get("blockIndex")
            if idx == 2:
                self.repair_block_two = True
                return "malformed"
            self.repair_block_two = False
            evidence_id = f"E-{idx:03d}"
            return json.dumps({"sections": [{"sectionType": "REFERENCE", "claims": [
                {"text": f"fact {idx}", "evidenceIds": [evidence_id]}
            ]}], "procedures": [], "glossary": []})
    class Guard:
        def check(self, *args):
            return None
    result = SynthesisService(Provider(), Guard()).synthesize(timeline, "REFERENCE", {})
    assert result.status == "SYNTHESIS_INVALID"
    assert result.document is None
    assert any(error.startswith("block-2:") for error in result.errors)


def test_mode_override_rejected_even_evidence_only(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_mapping.json").write_text(json.dumps({"frames": [], "video_info": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid DocumentationMode"):
        generate_documentation_v2(frames, "x.mp4", evidence_only=True, mode_override="INVALID")
    result = generate_documentation_v2(frames, "x.mp4", evidence_only=True, mode_override="KT_SESSION")
    assert result["mode"]["mode"] == "KT_SESSION"
    assert regenerate_main([str(frames), "--mode", "INVALID", "--evidence-only"]) == 2


def test_documentation_v2_tests_have_no_vacuous_assertions():
    tests = Path(__file__).parent
    patterns = [re.compile(r"\bor\s+True\b"), re.compile(r"\bif\s+False\s+else\s+True\b"), re.compile(r"\bassert\s+True\b")]
    for path in tests.glob("test_documentation_v2*.py"):
        source = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not pattern.search(source), f"vacuous assertion in {path.name}: {pattern.pattern}"
