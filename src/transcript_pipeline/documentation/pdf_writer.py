"""Human-readable MANUAL.pdf writer (US-002 A).

Builds a structured PDF from the SAME `DocumentationSource` +
`list[ProceduralStep]` objects that feed `engine.write_manual` — it never
re-extracts or re-interprets the video, never re-runs OCR/vision, and never
converts Markdown to plain text: every section (title, metadata, numbered
steps, timestamps, screenshots, instruction, confidence, evidence source,
reviewed badge, low-confidence warning, AI-interpretation callout) is laid
out directly from the typed domain model.

reportlab is an optional dependency (the `pdf` extra): pure Python,
cross-platform, no native Windows deps. When it is missing,
`engine.write_manual` skips the PDF and keeps writing MANUAL.md.
"""
from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from transcript_pipeline.documentation.models import DocumentationSource, ProceduralStep

logger = logging.getLogger(__name__)

_PAGE_SIZE = A4
_MARGIN = 18 * mm
_MAX_IMAGE_WIDTH = 150 * mm
_MAX_IMAGE_HEIGHT = 90 * mm


def _register_fonts() -> tuple[str, str, str, str]:
    """Returns (body, bold, italic, bold_italic) font names.

    reportlab's built-in Helvetica only covers Latin-1; the Bitstream Vera
    TTFs bundled inside reportlab extend that (Latin/Greek/Cyrillic) with no
    system-font dependency, so they are preferred when present, with
    Helvetica as the always-available fallback.
    """
    try:
        import reportlab

        fonts_dir = Path(reportlab.__file__).parent / "fonts"
        for name, filename in (
            ("ManualBody", "Vera.ttf"),
            ("ManualBold", "VeraBd.ttf"),
            ("ManualItalic", "VeraIt.ttf"),
            ("ManualBoldItalic", "VeraBI.ttf"),
        ):
            path = fonts_dir / filename
            if not path.exists():
                raise FileNotFoundError(path)
            pdfmetrics.registerFont(TTFont(name, str(path)))
        return "ManualBody", "ManualBold", "ManualItalic", "ManualBoldItalic"
    except Exception as e:
        logger.warning("[DOCS] Unicode TTF unavailable (%s); falling back to Helvetica", e)
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"


_BODY, _BOLD, _ITALIC, _BOLD_ITALIC = _register_fonts()


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "ManualTitle", fontName=_BOLD, fontSize=20, leading=24,
            spaceAfter=6 * mm, textColor=colors.HexColor("#111827"),
        ),
        "heading": ParagraphStyle(
            "ManualHeading", fontName=_BOLD, fontSize=13, leading=16,
            spaceBefore=6 * mm, spaceAfter=2 * mm, textColor=colors.HexColor("#111827"),
        ),
        "meta": ParagraphStyle(
            "ManualMeta", fontName=_BODY, fontSize=9, leading=12,
            textColor=colors.HexColor("#4b5563"),
        ),
        "body": ParagraphStyle(
            "ManualBody", fontName=_BODY, fontSize=10, leading=14,
            spaceBefore=2 * mm, textColor=colors.HexColor("#1f2933"),
        ),
        "small": ParagraphStyle(
            "ManualSmall", fontName=_BODY, fontSize=8.5, leading=11,
            textColor=colors.HexColor("#6b7280"),
        ),
        "cell": ParagraphStyle("ManualCell", fontName=_BODY, fontSize=9.5, leading=12),
        "cell_bold": ParagraphStyle("ManualCellBold", fontName=_BOLD, fontSize=9.5, leading=12),
    }


def _metadata_table(source: DocumentationSource, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [Paragraph("Video", styles["cell_bold"]), Paragraph(escape(source.video_name), styles["cell"])],
        [Paragraph("Duration", styles["cell_bold"]), Paragraph(escape(_format_duration(source.duration)), styles["cell"])],
        [Paragraph("Language", styles["cell_bold"]), Paragraph(escape(source.language), styles["cell"])],
        [Paragraph("Extraction method", styles["cell_bold"]), Paragraph(escape(source.extraction_method), styles["cell"])],
        [Paragraph("Generated at", styles["cell_bold"]), Paragraph(escape(source.generated_at), styles["cell"])],
    ]
    table = Table(rows, colWidths=[45 * mm, None])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _callout_box(text: str, styles: dict[str, ParagraphStyle], *, background: str, border: str) -> Table:
    table = Table([[Paragraph(text, styles["body"])]])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(border)),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _warning_box(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    return _callout_box(
        f"<b>LOW CONFIDENCE</b> — {escape(text)}", styles,
        background="#fef3c7", border="#f59e0b",
    )


def _ai_box(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    return _callout_box(
        f"<b>AI interpretation (unverified)</b> — {escape(text)}", styles,
        background="#e0f2fe", border="#38bdf8",
    )


def _reviewed_badge(styles: dict[str, ParagraphStyle]) -> Table:
    badge_style = ParagraphStyle(
        "ManualBadge", parent=styles["meta"], fontName=_BOLD,
        fontSize=8, textColor=colors.white,
    )
    table = Table([[Paragraph("REVIEWED", badge_style)]], colWidths=[28 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#16a34a")),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _frame_image(step: ProceduralStep, frames_dir: Path, manual_dir: Path) -> Image | None:
    candidates: list[Path] = []
    if step.frame_ref:
        candidates.append(frames_dir / Path(step.frame_ref).name)
    assets_dir = manual_dir / "assets"
    if assets_dir.is_dir():
        candidates.extend(sorted(assets_dir.glob(f"{step.id}.*")))
    for path in candidates:
        image = _make_image(path)
        if image is not None:
            return image
    return None


def _make_image(path: Path) -> Image | None:
    if not path.is_file():
        return None
    try:
        from PIL import Image as PILImage

        with PILImage.open(path) as im:
            im.load()
            width, height = im.size
        if width <= 0 or height <= 0:
            return None
    except Exception as e:
        logger.debug("[DOCS] skipping unreadable frame %s: %s", path.name, e)
        return None
    scale = min(_MAX_IMAGE_WIDTH / width, _MAX_IMAGE_HEIGHT / height, 1.0)
    try:
        return Image(str(path), width=width * scale, height=height * scale)
    except Exception as e:
        logger.debug("[DOCS] skipping frame %s: %s", path.name, e)
        return None


def _step_flowables(
    step: ProceduralStep, frames_dir: Path, manual_dir: Path, styles: dict[str, ParagraphStyle]
) -> list:
    flow: list = []
    heading = Paragraph(f"{step.order}. {escape(step.title)}", styles["heading"])
    meta = Paragraph(
        "  |  ".join([
            _format_ts(step.timestamp),
            f"confidence: <b>{step.confidence}</b>",
            f"evidence source: {step.evidence_source}",
        ]),
        styles["meta"],
    )
    head_block: list = [heading, meta]
    if step.reviewed:
        head_block.append(Spacer(1, 1 * mm))
        head_block.append(_reviewed_badge(styles))
    image = _frame_image(step, frames_dir, manual_dir)
    if image is not None:
        head_block.append(Spacer(1, 2 * mm))
        head_block.append(image)
    flow.append(KeepTogether(head_block))

    flow.append(Paragraph(escape(step.instruction).replace("\n", "<br/>"), styles["body"]))
    if step.confidence == "low":
        flow.append(Spacer(1, 2 * mm))
        flow.append(_warning_box(
            "No transcript or on-screen text was captured near this moment — "
            "verify this step before trusting it.",
            styles,
        ))
    if step.visual_description:
        flow.append(Spacer(1, 2 * mm))
        flow.append(_ai_box(step.visual_description, styles))
    flow.append(Spacer(1, 5 * mm))
    return flow


def _footer_callback(video_name: str):
    def _draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(_BODY, 8)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(_MARGIN, 10 * mm, video_name[:80])
        canvas.drawRightString(_PAGE_SIZE[0] - _MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return _draw


def write_manual_pdf(
    manual_dir: Path,
    source: DocumentationSource,
    steps: list[ProceduralStep],
    frames_dir: Path,
) -> Path:
    """Writes `manual_dir/MANUAL.pdf` from the same domain objects as
    `engine.write_manual` — no re-extraction, no OCR/vision. Returns the
    written PDF path."""
    manual_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = manual_dir / "MANUAL.pdf"
    styles = _styles()

    story: list = [Paragraph(escape(source.video_name), styles["title"])]
    story.append(_metadata_table(source, styles))
    story.append(Spacer(1, 4 * mm))

    low_count = sum(1 for s in steps if s.confidence == "low")
    if low_count:
        story.append(_warning_box(
            f"{low_count} of {len(steps)} step(s) have no transcript/on-screen-text "
            "evidence and are marked low confidence — review before treating them as accurate.",
            styles,
        ))
        story.append(Spacer(1, 4 * mm))

    for step in steps:
        story.extend(_step_flowables(step, frames_dir, manual_dir, styles))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=16 * mm,
        title=f"Manual — {source.video_name}",
        author="Zo Whisper Studio",
    )
    footer = _footer_callback(source.video_name)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return pdf_path


def _format_duration(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_ts(seconds: float) -> str:
    return _format_duration(seconds)