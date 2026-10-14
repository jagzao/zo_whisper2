"""DV2-24..29/31..33/35/47 — semantic manual, PDF, AI package output and
compatibility (TEST-MATRIX-ZMI-DOCS-V2-001)."""
from __future__ import annotations

import json

from tests.fixtures.documentation_v2 import materialize_frames_dir
from tests.fixtures.documentation_v2.mock_synthesis import (
    MockAllowAllGuard,
    MockKTSynthesisProvider,
    MockReferenceSynthesisProvider,
    MockTutorialSynthesisProvider,
)
from transcript_pipeline.documentation.engine import generate_documentation
from transcript_pipeline.documentation.pipeline_v2 import generate_documentation_v2
from transcript_pipeline.documentation.synthesis import SynthesisService

KT_CONFIG = {"name": "Acme", "documentation": {"mode": "KT_SESSION"}}
TUTORIAL_CONFIG = {"name": "Acme", "documentation": {"mode": "TUTORIAL"}}
REFERENCE_CONFIG = {"name": "Acme", "documentation": {"mode": "REFERENCE"}}


def _service(provider):
    return SynthesisService(provider, MockAllowAllGuard(), model_name="mock-model")


def _generate(fixture, tmp_path, config, provider):
    frames_dir = materialize_frames_dir(fixture, tmp_path)
    result = generate_documentation_v2(
        frames_dir, json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))["video_info"]["name"],
        project_config=config, synthesis_service=_service(provider),
    )
    assert result["semantic"]["ready"] is True
    return frames_dir, result


# ── DV2-24 KT template ────────────────────────────────────────────────────

def test_dv2_24_kt_document_renders_semantic_template_sections(tmp_path):
    frames_dir, result = _generate("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    document = json.loads((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))
    section_types = [s["sectionType"] for s in document["sections"]]
    for expected in (
        "EXECUTIVE_SUMMARY", "CONTEXT_SCOPE", "PROCESS", "SYSTEM",
        "ROLE_RESPONSIBILITY", "DECISION", "RISK", "OPEN_QUESTION", "ACTION_ITEM",
    ):
        assert expected in section_types, f"KT template section {expected} missing"
    assert document["documentationMode"] == "KT_SESSION"
    # No forced procedure for KT content.
    assert document["procedures"] == []
    # Concise: tens of semantic sections, not one per evidence item.
    assert 1 <= len(document["sections"]) < result["evidence"]["item_count"]


# ── DV2-25 tutorial procedure ─────────────────────────────────────────────

def test_dv2_25_tutorial_creates_grounded_ordered_procedure(tmp_path):
    frames_dir, _ = _generate("tutorial", tmp_path, TUTORIAL_CONFIG, MockTutorialSynthesisProvider())
    document = json.loads((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))
    assert len(document["procedures"]) == 1
    procedure = document["procedures"][0]
    orders = [step["order"] for step in procedure["steps"]]
    assert orders == sorted(orders)
    evidence_ids = {item["evidenceId"] for item in document["evidenceIndex"]}
    for step in procedure["steps"]:
        assert step["evidenceRefs"], "every step must be grounded"
        assert set(step["evidenceRefs"]) <= evidence_ids


# ── DV2-26 reference no procedure ─────────────────────────────────────────

def test_dv2_26_reference_source_validly_outputs_zero_procedures(tmp_path):
    frames_dir, _ = _generate("reference_meeting", tmp_path, REFERENCE_CONFIG, MockReferenceSynthesisProvider())
    document = json.loads((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))
    assert document["procedures"] == []
    report = json.loads((frames_dir / "manual" / "synthesis-validation.json").read_text(encoding="utf-8"))
    assert report["valid"] is True


# ── DV2-27 semantic manual ────────────────────────────────────────────────

def test_dv2_27_manual_content_comes_from_knowledge_document(tmp_path):
    frames_dir, _ = _generate("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    document = json.loads((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))
    manual = (frames_dir / "manual" / "MANUAL.md").read_text(encoding="utf-8")

    # Manual mirrors the semantic document, not one heading per EvidenceItem.
    for section in document["sections"]:
        assert section["title"] in manual
        for claim in section["claims"]:
            assert claim["text"] in manual
    assert manual.count("## ") <= len(document["sections"]) + len(document["procedures"]) + 4
    assert "Knowledge transfer for Acme Corp" in manual


# ── DV2-28 review queue callout ───────────────────────────────────────────

def test_dv2_28_review_queue_callout_is_count_not_empty_sections(tmp_path):
    frames_dir, result = _generate("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    manual = (frames_dir / "manual" / "MANUAL.md").read_text(encoding="utf-8")
    queue_count = result["evidence"]["review_required_count"]
    assert queue_count >= 3, "fixture guarantees a low-confidence tail"
    assert f"Review queue: {queue_count}" in manual
    # The placeholders are NOT expanded into empty manual sections.
    assert "No captured evidence near this moment — queued for human review.\n\n##" not in manual
    metadata = json.loads((frames_dir / "manual" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["review_required_count"] == queue_count
    assert metadata["schema_version"] == 2
    assert metadata["documentation_mode"] == "KT_SESSION"
    assert metadata["synthesis_status"] == "MANUAL_READY"
    assert metadata["evidence_item_count"] == result["evidence"]["item_count"]
    assert metadata["semantic_section_count"] == result["semantic"]["section_count"]


# ── DV2-29 semantic PDF ───────────────────────────────────────────────────

def test_dv2_29_pdf_renders_semantic_headings_evidence_refs_bounded_images(tmp_path):
    try:
        import reportlab  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("reportlab not installed")
    frames_dir, _ = _generate("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    document = json.loads((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))

    pdf_path = frames_dir / "manual" / "MANUAL.pdf"
    assert pdf_path.exists()
    metadata = json.loads((frames_dir / "manual" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["manual_pdf"] == "ok"

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for section in document["sections"][:4]:
        assert section["title"] in text, "semantic headings must render"
    assert "[E-0" in text, "evidence-reference style must render"
    images = sum(len(page.images) for page in reader.pages)
    assert images <= 24, "bounded screenshots only"
    # Representative screenshots exist but far fewer than evidence frames.
    assert images >= 1


# ── DV2-31 chunks semantic ────────────────────────────────────────────────

def test_dv2_31_chunks_follow_semantic_units_not_frame_count(tmp_path):
    frames_dir, result = _generate("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    document = json.loads((frames_dir / "manual" / "knowledge-document.json").read_text(encoding="utf-8"))
    chunks = [json.loads(line) for line in (frames_dir / "ai-package" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]

    semantic_units = len(document["sections"]) + len(document["procedures"])
    assert len(chunks) <= semantic_units + len(document["sections"])  # split parts allowed
    assert len(chunks) < result["evidence"]["item_count"], (
        "one chunk per captured frame is exactly what V2 must not do"
    )
    for chunk in chunks:
        assert chunk["id"].startswith(("section-", "procedure-"))
        for line in chunk["text"].splitlines():
            if line.startswith("["):
                continue


# ── DV2-32 chunks metadata ────────────────────────────────────────────────

def test_dv2_32_chunks_metadata_complete(tmp_path):
    project = dict(KT_CONFIG, second_brain={
        "enabled": True, "scope": "PROJECT", "project_id": "acme",
        "domain": "second-brain/acme", "default_artifact_type": "KT",
        "default_actionability": "REFERENCE",
    })
    frames_dir, _ = _generate("kt_session", tmp_path, project, MockKTSynthesisProvider())
    chunks = [json.loads(line) for line in (frames_dir / "ai-package" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert chunks
    for chunk in chunks:
        meta = chunk["metadata"]
        assert meta["documentId"]
        assert meta["sectionId"]
        assert meta["sectionType"]
        assert meta["scope"] == "PROJECT"
        assert meta["projectId"] == "acme"
        assert meta["artifactType"]
        assert meta["actionability"]
        assert isinstance(meta["evidenceRefs"], list) and meta["evidenceRefs"]
        assert meta["evidenceConfidence"] in ("high", "medium", "low")
        assert meta["reviewStatus"]
        assert meta["sourceMedia"]
        assert meta["timestampRange"] is None or len(meta["timestampRange"]) == 2


# ── DV2-33 raw transcript forbidden ───────────────────────────────────────

def test_dv2_33_no_whole_raw_transcript_keys_in_package_or_chunks(tmp_path):
    frames_dir, _ = _generate("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    mapping = json.loads((frames_dir / "frame_mapping.json").read_text(encoding="utf-8"))
    full_transcript = mapping["transcription_summary"]["full_transcription"]

    forbidden_keys = ("rawTranscript", "transcript", "vtt", "rawVtt", "mediaBytes", "mediaPath", "media")

    def _assert_no_forbidden_keys(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key not in forbidden_keys, f"forbidden key {key} in {path}"
                _assert_no_forbidden_keys(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                _assert_no_forbidden_keys(child, f"{path}[{index}]")

    for payload_file in ("chunks.jsonl", "evidence.jsonl"):
        for line in (frames_dir / "ai-package" / payload_file).read_text(encoding="utf-8").splitlines():
            _assert_no_forbidden_keys(json.loads(line), payload_file)
    _assert_no_forbidden_keys(
        json.loads((frames_dir / "ai-package" / "manifest.json").read_text(encoding="utf-8")), "manifest.json"
    )

    for payload_file in ("chunks.jsonl", "evidence.jsonl", "manifest.json", "knowledge.md"):
        content = (frames_dir / "ai-package" / payload_file).read_text(encoding="utf-8")
        assert full_transcript[:200] not in content, (
            f"whole raw transcript must not appear in {payload_file}"
        )
    # Bounded excerpts only.
    for line in (frames_dir / "ai-package" / "evidence.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        for field in ("transcriptExcerpt", "ocrExcerpt"):
            value = item.get(field)
            assert value is None or len(value) <= 1200


# ── DV2-35 no fake procedure ──────────────────────────────────────────────

def test_dv2_35_kt_without_procedure_yields_no_procedure_json(tmp_path):
    frames_dir, _ = _generate("kt_session", tmp_path, KT_CONFIG, MockKTSynthesisProvider())
    assert not (frames_dir / "ai-package" / "procedure.json").exists()
    manifest = json.loads((frames_dir / "ai-package" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["procedures"] == []


# ── DV2-47 current compatibility ──────────────────────────────────────────

def test_dv2_47_existing_manual_steps_metadata_callers_do_not_crash(tmp_path):
    """No provider: the legacy compatibility bundles must keep working for
    the existing dashboard/test surface."""
    frames_dir = materialize_frames_dir("kt_session", tmp_path)
    result = generate_documentation(frames_dir, "acme_kt_session.mp4")

    # Historical summary keys preserved.
    assert result["manual_dir"] == str(frames_dir / "manual")
    assert result["ai_package_dir"] == str(frames_dir / "ai-package")
    assert result["step_count"] > 0
    assert result["low_confidence_count"] > 0
    assert "knowledge" in result

    from transcript_pipeline.documentation.engine import load_steps

    source, steps = load_steps(frames_dir / "manual")
    assert len(steps) == result["step_count"]
    assert source.duration == 4500.0
    metadata = json.loads((frames_dir / "manual" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["step_count"] == result["step_count"]
    assert metadata["video_name"] == "acme_kt_session.mp4"
    manifest = json.loads((frames_dir / "ai-package" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    chunks = (frames_dir / "ai-package" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(chunks) == result["step_count"]
    # V2 metadata additions present and honest: a typed non-ready synthesis
    # status (unavailable or privacy-blocked depending on env defaults),
    # never a false MANUAL_READY.
    assert metadata["synthesis_status"] in ("SYNTHESIS_NOT_AVAILABLE", "SYNTHESIS_BLOCKED_PRIVACY")
    assert result["status"] in ("SYNTHESIS_NOT_AVAILABLE", "SYNTHESIS_BLOCKED_PRIVACY", "EVIDENCE_READY")
    assert metadata["evidence_item_count"] >= 1
