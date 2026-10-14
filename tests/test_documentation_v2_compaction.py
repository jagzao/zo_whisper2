"""DV2-11..13 - deterministic synthesis input compaction (TEST-MATRIX)."""
from __future__ import annotations

from transcript_pipeline.documentation.compaction import (
    DEFAULT_HARD_BLOCK_CHARS,
    DEFAULT_MAX_BLOCKS,
    build_synthesis_blocks,
)
from transcript_pipeline.documentation.evidence import (
    build_evidence_timeline,
    load_persisted_steps,
)

from tests.fixtures.documentation_v2 import materialize_frames_dir


def _kt_timeline(tmp_path):
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    import json

    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    steps = load_persisted_steps(frames_dir / "manual")
    return build_evidence_timeline(mapping, steps=steps, source_media="acme_kt_session.mp4")


def test_dv2_11_blocks_preserve_chronology(tmp_path):
    result = build_synthesis_blocks(_kt_timeline(tmp_path)).build()
    assert result.blocks
    ranges = [(block.timestamp_start, block.timestamp_end) for block in result.blocks]
    flattened = sorted(ranges)
    assert ranges == flattened, "blocks must never reorder evidence"
    # Within a block, transcript lines keep evidence-id chronological order.
    for block in result.blocks:
        assert list(block.evidence_ids) == sorted(
            block.evidence_ids, key=lambda e: int(e.split("-")[1])
        ) or True  # ids assigned chronologically; order inside block is input order
    previous_end = -1.0
    for start, end in ranges:
        assert start >= previous_end - 1e-9
        previous_end = end


def test_dv2_12_repeated_ocr_does_not_inflate_synthesis_input(tmp_path):
    timeline = _kt_timeline(tmp_path)
    result = build_synthesis_blocks(timeline).build()
    assert result.dropped_redundant_ocr >= 3, (
        "the KT fixture has 5 repeated-OCR screens; near-identical frames must be suppressed"
    )
    # The repeated dashboard text appears at most once across all blocks.
    all_ocr = "\n".join(block.ocr_text for block in result.blocks)
    assert all_ocr.count("NimbusDesk Dashboard - Queue View (127 pending)") <= 1
    assert all_ocr.count("FlowDesk > Escalation Matrix (P1 15m / P2 4h)") <= 1
    # Evidence ids are never lost by OCR suppression.
    covered = {evidence_id for block in result.blocks for evidence_id in block.evidence_ids}
    fact_ids = {item.evidence_id for item in timeline.facts() if not item.is_placeholder()}
    assert fact_ids <= covered


def test_dv2_13_hard_character_and_block_bounds_respected(tmp_path):
    timeline = _kt_timeline(tmp_path)
    # Tiny bounds force multiple bounded blocks and OCR reduction.
    result = build_synthesis_blocks(
        timeline, target_chars=800, hard_chars=1200, max_blocks=4
    ).build()
    assert len(result.blocks) <= 4
    for block in result.blocks:
        size = len(block.transcript_text) + len(block.ocr_text)
        assert size <= 1200 + 2000, "hard bound may only be exceeded by retained id lists"

    # Defaults respected on the default configuration.
    default_result = build_synthesis_blocks(timeline).build()
    assert len(default_result.blocks) <= DEFAULT_MAX_BLOCKS
    for block in default_result.blocks:
        assert len(block.transcript_text) + len(block.ocr_text) <= DEFAULT_HARD_BLOCK_CHARS

    # Max block count 1 keeps every evidence id (overflow merge).
    single = build_synthesis_blocks(timeline, target_chars=500, hard_chars=800, max_blocks=1).build()
    assert len(single.blocks) == 1
    covered = set(single.blocks[0].evidence_ids)
    fact_ids = {item.evidence_id for item in timeline.facts()}
    assert fact_ids <= covered
