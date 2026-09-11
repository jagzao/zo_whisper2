"""Coverage for the human-readable MANUAL.pdf writer (US-002 A).

The PDF is built from the SAME `DocumentationSource` + `list[ProceduralStep]`
objects that feed `write_manual` — never re-extracted from the video, never
re-transcribed, never re-run through OCR/vision. reportlab (the `pdf` extra)
does the layout; pypdf (dev extra) is used only to read the output back for
assertions. Frame fixtures are REAL tiny PNGs (PIL) because reportlab rejects
the fake byte strings used elsewhere in the suite.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pypdf import PdfReader

from transcript_pipeline.documentation import engine
from transcript_pipeline.documentation.engine import (
    generate_documentation,
    regenerate_from_steps,
    remove_step,
    update_step,
    write_manual,
)
from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep
from transcript_pipeline.documentation.pdf_writer import write_manual_pdf

MAPPING = {
    "video_info": {"name": "demo.mp4", "duration": 10.0, "extraction_method": "smart_scene"},
    "transcription_summary": {"language": "en"},
    "frames": [
        {"frame_file": "frame_0000.png", "timestamp": 1.5, "timestamp_formatted": "00:00:01.500"},
        {"frame_file": "frame_0001.png", "timestamp": 6.0, "timestamp_formatted": "00:00:06.000"},
    ],
    "transcription_mapping": {
        "frame_0000.png": {"full_text": "Click the New Project button to get started."},
        "frame_0001.png": {"full_text": ""},
    },
}


def _make_png(path, color: str = "white") -> None:
    from PIL import Image

    Image.new("RGB", (320, 180), color=color).save(path)


def _source() -> DocumentationSource:
    return DocumentationSource(
        video_name="demo.mp4", duration=10.0, language="en",
        extraction_method="smart_scene", generated_at="2026-01-01T00:00:00+00:00",
    )


def _steps() -> list[ProceduralStep]:
    return [
        ProceduralStep(
            id="step-0001", order=1, title="Create a new project",
            instruction="Click the New Project button to get started.",
            timestamp=1.5, frame_ref="frame_0000.png",
            transcript_ref="Click the New Project button to get started.",
            confidence="high", evidence_source="transcript", reviewed=True,
            visual_description="A dialog with a New Project button is visible.",
        ),
        ProceduralStep(
            id="step-0002", order=2, title="Step at 00:00:06",
            instruction="(no transcript or on-screen text captured near this moment — review evidence before trusting this step)",
            timestamp=6.0, frame_ref="frame_0001.png", transcript_ref="",
            confidence="low", evidence_source="none",
        ),
    ]


def _pdf_text(path) -> str:
    reader = PdfReader(str(path))
    return re.sub(r"\s+", " ", " ".join((page.extract_text() or "") for page in reader.pages))


def _pdf_image_count(path) -> int:
    reader = PdfReader(str(path))
    return sum(len(page.images) for page in reader.pages)


@pytest.fixture
def frames_dir(tmp_path) -> Path:
    frames = tmp_path / "frames"
    frames.mkdir()
    _make_png(frames / "frame_0000.png", color="lightblue")
    _make_png(frames / "frame_0001.png", color="lightyellow")
    return frames


# ── Direct writer ────────────────────────────────────────────────────────

def test_write_manual_pdf_creates_nonempty_pdf(frames_dir, tmp_path):
    manual_dir = tmp_path / "manual"
    pdf_path = write_manual_pdf(manual_dir, _source(), _steps(), frames_dir)

    assert pdf_path == manual_dir / "MANUAL.pdf"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert len(PdfReader(str(pdf_path)).pages) >= 1


def test_pdf_contains_essential_textual_content(frames_dir, tmp_path):
    pdf_path = write_manual_pdf(tmp_path / "manual", _source(), _steps(), frames_dir)
    text = _pdf_text(pdf_path)

    assert "demo.mp4" in text  # title / video name
    assert "Duration" in text and "00:00:10" in text  # metadata
    assert "Language" in text and "en" in text
    assert "Extraction method" in text and "smart_scene" in text
    assert "Generated at" in text and "2026-01-01T00:00:00+00:00" in text
    assert "1. Create a new project" in text  # numbered step + title
    assert "00:00:01" in text  # step timestamp
    assert "Click the New Project button to get started." in text  # instruction
    assert "confidence: high" in text
    assert "evidence source: transcript" in text
    assert "REVIEWED" in text  # reviewed badge
    assert "AI interpretation (unverified)" in text  # visual description callout
    assert "LOW CONFIDENCE" in text  # low-confidence warning
    assert "2. Step at 00:00:06" in text


def test_pdf_embeds_screenshots(frames_dir, tmp_path):
    pdf_path = write_manual_pdf(tmp_path / "manual", _source(), _steps(), frames_dir)
    assert _pdf_image_count(pdf_path) >= 2


def test_step_without_frame_image_is_skipped_gracefully(tmp_path):
    step = ProceduralStep(
        id="step-0001", order=1, title="No screenshot step",
        instruction="This step has no frame image at all.",
        timestamp=2.0, frame_ref=None, transcript_ref="",
        confidence="medium", evidence_source="ocr",
    )
    pdf_path = write_manual_pdf(tmp_path / "manual", _source(), [step], tmp_path / "missing-frames")
    assert pdf_path.exists()
    assert "No screenshot step" in _pdf_text(pdf_path)
    assert _pdf_image_count(pdf_path) == 0


def test_unicode_text_does_not_crash(frames_dir, tmp_path):
    step = ProceduralStep(
        id="step-0001", order=1, title="Ünïcode tïtle",
        instruction="Café naïve — 日本語 ☕ configurá el sistema.",
        timestamp=1.5, frame_ref="frame_0000.png", transcript_ref="",
        confidence="high", evidence_source="transcript",
    )
    pdf_path = write_manual_pdf(tmp_path / "manual", _source(), [step], frames_dir)
    assert pdf_path.exists()
    assert "Café" in _pdf_text(pdf_path)


def test_deterministic_structure(frames_dir, tmp_path):
    first = write_manual_pdf(tmp_path / "a", _source(), _steps(), frames_dir)
    second = write_manual_pdf(tmp_path / "b", _source(), _steps(), frames_dir)
    assert _pdf_text(first) == _pdf_text(second)
    assert len(PdfReader(str(first)).pages) == len(PdfReader(str(second)).pages)


# ── Engine integration ───────────────────────────────────────────────────

@pytest.fixture
def generated(tmp_path):
    frames = tmp_path / "demo_Frames" / "demo"
    frames.mkdir(parents=True)
    (frames / "frame_mapping.json").write_text(json.dumps(MAPPING), encoding="utf-8")
    _make_png(frames / "frame_0000.png", color="lightblue")
    _make_png(frames / "frame_0001.png", color="lightyellow")
    generate_documentation(frames, "demo.mp4")
    return frames, frames / "manual", frames / "ai-package"


def test_generate_documentation_writes_pdf(generated):
    frames_dir, manual_dir, _ = generated
    pdf_path = manual_dir / "MANUAL.pdf"
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert "Click the New Project button" in _pdf_text(pdf_path)


def test_regenerate_from_steps_keeps_pdf_in_sync(generated):
    frames_dir, manual_dir, ai_dir = generated
    steps_payload = json.loads((manual_dir / "steps.json").read_text(encoding="utf-8"))
    steps_payload["steps"][1]["instruction"] = "Edited by a human reviewer"
    (manual_dir / "steps.json").write_text(json.dumps(steps_payload), encoding="utf-8")

    regenerate_from_steps(manual_dir, ai_dir, frames_dir, "demo.mp4")

    text = _pdf_text(manual_dir / "MANUAL.pdf")
    assert "Edited by a human reviewer" in text
    assert "(no transcript or on-screen text captured near this moment" not in text


def test_update_step_keeps_pdf_in_sync(generated):
    frames_dir, manual_dir, ai_dir = generated
    update_step(
        manual_dir, ai_dir, frames_dir, "step-0002",
        instruction="Confirmed manually: this opens the settings dialog.",
    )
    text = _pdf_text(manual_dir / "MANUAL.pdf")
    assert "Confirmed manually: this opens the settings dialog." in text
    assert "REVIEWED" in text


def test_remove_step_keeps_pdf_in_sync(generated):
    frames_dir, manual_dir, ai_dir = generated
    remove_step(manual_dir, ai_dir, frames_dir, "step-0001")
    text = _pdf_text(manual_dir / "MANUAL.pdf")
    assert "Click the New Project button" not in text
    assert "Step at 00:00:06" in text


def test_regeneration_does_not_retranscribe_or_rerun_ocr_vision(generated, monkeypatch):
    """Definition-of-Done: regenerate/edit/remove must rebuild MANUAL.pdf from
    steps.json alone — no frame_mapping re-derivation, no OCR, no vision."""
    frames_dir, manual_dir, ai_dir = generated

    def _forbidden(*args, **kwargs):
        raise AssertionError("regeneration must not re-derive steps or re-run OCR/vision")

    monkeypatch.setattr(engine, "build_steps", _forbidden)
    monkeypatch.setattr(engine, "_ocr_text", _forbidden)
    monkeypatch.setattr(engine, "_vision_description", _forbidden)

    result = regenerate_from_steps(manual_dir, ai_dir, frames_dir, "demo.mp4")
    assert result["step_count"] == 2
    assert (manual_dir / "MANUAL.pdf").exists()

    update_step(manual_dir, ai_dir, frames_dir, "step-0001", reviewed=True)
    remove_step(manual_dir, ai_dir, frames_dir, "step-0002")
    assert (manual_dir / "MANUAL.pdf").exists()


def test_pdf_skipped_gracefully_when_reportlab_unavailable(generated, monkeypatch, tmp_path):
    """Core installs without the `pdf` extra must still get MANUAL.md — the
    PDF is skipped with a warning, never an error. The metadata must record
    the absence so the API can surface it instead of pretending the human
    bundle is complete."""
    frames_dir, _, _ = generated
    fresh_manual_dir = tmp_path / "fresh-manual"
    monkeypatch.setattr(engine, "_PDF_AVAILABLE", False)

    write_manual(fresh_manual_dir, _source(), _steps(), frames_dir)

    assert (fresh_manual_dir / "MANUAL.md").exists()
    assert not (fresh_manual_dir / "MANUAL.pdf").exists()
    metadata = json.loads((fresh_manual_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["manual_pdf"] == "missing"


def test_write_manual_records_pdf_generation_failure_in_metadata(generated, monkeypatch, tmp_path):
    """reportlab present but the PDF write raises: MANUAL.md still works
    (graceful degradation), but metadata.json must record the failure so the
    API/DOCS tab can report it visibly."""
    frames_dir, _, _ = generated
    fresh_manual_dir = tmp_path / "fresh-manual"

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated reportlab failure")

    monkeypatch.setattr(engine, "write_manual_pdf", _boom)

    write_manual(fresh_manual_dir, _source(), _steps(), frames_dir)

    assert (fresh_manual_dir / "MANUAL.md").exists()
    assert not (fresh_manual_dir / "MANUAL.pdf").exists()
    metadata = json.loads((fresh_manual_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["manual_pdf"] == "failed"


def test_write_manual_records_pdf_ok_when_generated(generated, tmp_path):
    """Happy path: a successful PDF write is recorded as "ok" in metadata."""
    frames_dir, _, _ = generated
    fresh_manual_dir = tmp_path / "fresh-manual"

    write_manual(fresh_manual_dir, _source(), _steps(), frames_dir)

    assert (fresh_manual_dir / "MANUAL.pdf").exists()
    metadata = json.loads((fresh_manual_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["manual_pdf"] == "ok"