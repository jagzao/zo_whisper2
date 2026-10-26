"""DV2-21..23 — representative screenshot selection (TEST-MATRIX)."""
from __future__ import annotations

import json

from PIL import Image

from tests.fixtures.documentation_v2 import materialize_frames_dir
from tests.fixtures.documentation_v2.mock_synthesis import (
    MockAllowAllGuard,
    MockKTSynthesisProvider,
)
from transcript_pipeline.documentation import screenshots as screenshots_module
from transcript_pipeline.documentation.knowledge_models import KnowledgeDocument
from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2
from transcript_pipeline.documentation.screenshots import select_screenshots
from transcript_pipeline.documentation.synthesis import SynthesisService

KT_CONFIG = {"name": "Acme", "documentation": {"mode": "KT_SESSION"}}


def _kt_document(tmp_path):
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    result = generate_documentation_v2(
        frames_dir, "acme_kt_session.mp4",
        project_config=KT_CONFIG,
        synthesis_service=SynthesisService(MockKTSynthesisProvider(), MockAllowAllGuard(), model_name="m"),
    )
    document = KnowledgeDocument.from_json((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))
    return frames_dir, document, result


# ── DV2-21 screenshot duplicate ───────────────────────────────────────────

def test_dv2_21_near_identical_phash_frames_collapse(tmp_path):
    frames_dir, document, result = _kt_document(tmp_path)
    assert result["semantic"]["ready"] is True

    import json as _json

    timeline_payload = None
    from transcript_pipeline.documentation.evidence import build_evidence_timeline, load_persisted_steps

    mapping = _json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    steps = load_persisted_steps(frames_dir / "manual")
    timeline = build_evidence_timeline(mapping, steps=steps, source_media="acme_kt_session.mp4")
    del timeline_payload

    selection = select_screenshots(document, timeline, frames_dir, max_total=24, max_per_section=2)
    assert selection.picks
    # Perceptual dedup ran (imagehash when installed, Pillow aHash otherwise).
    assert selection.phash_mode in ("imagehash", "pillow")
    # No two selected frames share the same source path (near-identical
    # repeated screens collapsed).
    paths = [pick.source_path for pick in selection.picks]
    assert len(paths) == len(set(paths))

    # A manual repeated-dashboard neighborhood proves the collapse at the
    # aHash level: consecutive variant frames dedupe, distinct do not.
    # Textured images (not flat colors — degenerate for average hash).
    from PIL import ImageDraw

    def _textured(path, fill, label):
        img = Image.new("RGB", (320, 200), color=fill)
        draw = ImageDraw.Draw(img)
        draw.rectangle((8, 8, 311, 191), fill=tuple(min(255, c + 12) for c in fill),
                       outline=(20, 20, 20), width=2)
        draw.text((16, 16), label, fill=(240, 240, 240))
        img.save(path)

    near_a = frames_dir / "near_a.png"
    near_b = frames_dir / "near_b.png"
    far = frames_dir / "far.png"
    _textured(near_a, (60, 90, 130), "Queue View")
    _textured(near_b, (61, 91, 131), "Queue View")
    _textured(far, (8, 8, 8), "Compliance Sampling Report")
    ha, hb, hf = (
        screenshots_module._pillow_ahash(p) for p in (near_a, near_b, far)
    )
    assert screenshots_module._hamming(ha, hb) <= 6, "near-identical frames must collapse"
    assert screenshots_module._hamming(ha, hf) > 6, "distinct frames must not collapse"


# ── DV2-22 screenshot cap ─────────────────────────────────────────────────

def test_dv2_22_global_and_per_section_caps_enforced(tmp_path):
    frames_dir, document, _ = _kt_document(tmp_path)
    from transcript_pipeline.documentation.evidence import build_evidence_timeline, load_persisted_steps

    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    steps = load_persisted_steps(frames_dir / "manual")
    timeline = build_evidence_timeline(mapping, steps=steps, source_media="acme_kt_session.mp4")

    selection = select_screenshots(document, timeline, frames_dir, max_total=5, max_per_section=1)
    assert len(selection.picks) <= 5
    per_section: dict[str, int] = {}
    for pick in selection.picks:
        per_section[pick.section_id] = per_section.get(pick.section_id, 0) + 1
    assert all(count <= 1 for count in per_section.values())

    selection2 = select_screenshots(document, timeline, frames_dir, max_total=2, max_per_section=2)
    assert len(selection2.picks) <= 2

    # Defaults from SPEC §9.
    selection3 = select_screenshots(document, timeline, frames_dir)
    assert len(selection3.picks) <= 24
    per_section3: dict[str, int] = {}
    for pick in selection3.picks:
        per_section3[pick.section_id] = per_section3.get(pick.section_id, 0) + 1
    assert all(count <= 2 for count in per_section3.values())


# ── DV2-23 no imagehash fallback ──────────────────────────────────────────

def test_dv2_23_missing_hash_lib_still_deterministic_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(screenshots_module, "_IMAGEHASH_AVAILABLE", False)
    monkeypatch.setattr(screenshots_module, "_PIL_AVAILABLE", False)
    frames_dir, document, _ = _kt_document(tmp_path / "again")
    from transcript_pipeline.documentation.evidence import build_evidence_timeline, load_persisted_steps

    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    steps = load_persisted_steps(frames_dir / "manual")
    timeline = build_evidence_timeline(mapping, steps=steps, source_media="acme_kt_session.mp4")

    first = select_screenshots(document, timeline, frames_dir, max_total=6, max_per_section=1)
    second = select_screenshots(document, timeline, frames_dir, max_total=6, max_per_section=1)
    assert first.phash_mode == "path"
    assert [p.source_path for p in first.picks] == [p.source_path for p in second.picks], (
        "fallback selection must be deterministic"
    )
    assert len(first.picks) <= 6
    # Same-frame path dedup still applies.
    paths = [pick.source_path for pick in first.picks]
    assert len(paths) == len(set(paths))


# ── extra: source frames are never deleted ────────────────────────────────

def test_selection_never_deletes_source_frames(tmp_path):
    frames_dir, document, _ = _kt_document(tmp_path / "preserve")
    before = sorted(p.name for p in frames_dir.glob("frame_*.png"))
    from transcript_pipeline.documentation.evidence import build_evidence_timeline, load_persisted_steps

    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    steps = load_persisted_steps(frames_dir / "manual")
    timeline = build_evidence_timeline(mapping, steps=steps, source_media="acme_kt_session.mp4")
    select_screenshots(document, timeline, frames_dir)
    after = sorted(p.name for p in frames_dir.glob("frame_*.png"))
    assert before == after
