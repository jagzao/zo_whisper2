"""Semantic MANUAL.pdf writer (SPEC §11/§18, PLAN WP-11).

Renders the KnowledgeDocument + representative screenshots to A4 PDF:
executive summary styling, section styling, evidence-reference style and a
review-needed callout. Does NOT render every EvidenceItem (that is the
evidence plane's job). Keeps the v1 writer's guarantees: bundled fonts with
fallback, metadata table, footer, graceful no-reportlab.
"""
from __future__ import annotations

import logging
import shutil
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

from transcript_pipeline.documentation.evidence import EvidenceTimeline
from transcript_pipeline.documentation.evidence_writer import format_timestamp
from transcript_pipeline.documentation.knowledge_models import KnowledgeDocument, executive_summary_evidence_refs
from transcript_pipeline.documentation.models import DocumentationSource
from transcript_pipeline.documentation.screenshots import ScreenshotSelection

logger = logging.getLogger(__name__)

_PAGE_SIZE = A4
_MARGIN = 18 * mm
_MAX_IMAGE_WIDTH = 150 * mm
_MAX_IMAGE_HEIGHT = 90 * mm


def _register_fonts() -> tuple[str, str, str, str]:
    try:
        import reportlab

        fonts_dir = Path(reportlab.__file__).parent / "fonts"
        for name, filename in (
            ("SemanticBody", "Vera.ttf"),
            ("SemanticBold", "VeraBd.ttf"),
            ("SemanticItalic", "VeraIt.ttf"),
            ("SemanticBoldItalic", "VeraBI.ttf"),
        ):
            path = fonts_dir / filename
            if not path.exists():
                raise FileNotFoundError(path)
            pdfmetrics.registerFont(TTFont(name, str(path)))
        return "SemanticBody", "SemanticBold", "SemanticItalic", "SemanticBoldItalic"
    except Exception as e:  # noqa: BLE001
        logger.warning("[DOCS-V2] Unicode TTF unavailable (%s); Helvetica fallback", e)
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"


_BODY, _BOLD, _ITALIC, _BOLD_ITALIC = _register_fonts()


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "SemanticTitle", fontName=_BOLD, fontSize=20, leading=24,
            spaceAfter=6 * mm, textColor=colors.HexColor("#111827"),
        ),
        "heading": ParagraphStyle(
            "SemanticHeading", fontName=_BOLD, fontSize=13, leading=16,
            spaceBefore=6 * mm, spaceAfter=2 * mm, textColor=colors.HexColor("#111827"),
        ),
        "meta": ParagraphStyle(
            "SemanticMeta", fontName=_BODY, fontSize=9, leading=12,
            textColor=colors.HexColor("#4b5563"),
        ),
        "body": ParagraphStyle(
            "SemanticBody", fontName=_BODY, fontSize=10, leading=14,
            spaceBefore=2 * mm, textColor=colors.HexColor("#1f2933"),
        ),
        "claim": ParagraphStyle(
            "SemanticClaim", fontName=_BODY, fontSize=10, leading=14,
            leftIndent=6 * mm, bulletIndent=2 * mm, spaceBefore=1 * mm,
            textColor=colors.HexColor("#1f2933"),
        ),
        "evidence_ref": ParagraphStyle(
            "SemanticEvidence", fontName=_ITALIC, fontSize=8.5, leading=11,
            textColor=colors.HexColor("#2563eb"),
        ),
        "small": ParagraphStyle(
            "SemanticSmall", fontName=_BODY, fontSize=8.5, leading=11,
            textColor=colors.HexColor("#6b7280"),
        ),
        "cell": ParagraphStyle("SemanticCell", fontName=_BODY, fontSize=9.5, leading=12),
        "cell_bold": ParagraphStyle("SemanticCellBold", fontName=_BOLD, fontSize=9.5, leading=12),
    }


def _callout(text: str, styles: dict[str, ParagraphStyle], *, background: str, border: str) -> Table:
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


def _review_callout(timeline: EvidenceTimeline, styles: dict[str, ParagraphStyle]) -> Table:
    return _callout(
        f"<b>REVIEW NEEDED</b> — {timeline.review_required_count} captured moment(s) lack "
        "transcript/on-screen-text evidence. They are isolated in evidence/review-queue.json "
        "and do not support any factual claim in this manual.",
        styles, background="#fef3c7", border="#f59e0b",
    )


def _summary_box(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    return _callout(
        f"<b>EXECUTIVE SUMMARY</b> — {escape(text)}", styles,
        background="#eef2ff", border="#6366f1",
    )


def _metadata_table(document: KnowledgeDocument, source: DocumentationSource, styles) -> Table:
    rows = [
        [Paragraph("Document", styles["cell_bold"]), Paragraph(escape(document.title), styles["cell"])],
        [Paragraph("Mode", styles["cell_bold"]), Paragraph(escape(document.documentation_mode), styles["cell"])],
        [Paragraph("Duration", styles["cell_bold"]), Paragraph(escape(format_timestamp(source.duration)), styles["cell"])],
        [Paragraph("Language", styles["cell_bold"]), Paragraph(escape(source.language), styles["cell"])],
        [Paragraph("Generated at", styles["cell_bold"]), Paragraph(escape(source.generated_at), styles["cell"])],
    ]
    table = Table(rows, colWidths=[45 * mm, None])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


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
    except Exception as e:  # noqa: BLE001
        logger.debug("[DOCS-V2] skipping unreadable frame %s: %s", path.name, e)
        return None
    scale = min(_MAX_IMAGE_WIDTH / width, _MAX_IMAGE_HEIGHT / height, 1.0)
    try:
        return Image(str(path), width=width * scale, height=height * scale)
    except Exception as e:  # noqa: BLE001
        logger.debug("[DOCS-V2] skipping frame %s: %s", path.name, e)
        return None


def _evidence_refs_line(refs, timeline: EvidenceTimeline) -> str:
    by_id = timeline.by_id()
    parts = []
    for ref in refs:
        item = by_id.get(ref)
        ts = format_timestamp(item.timestamp_start) if item else "?"
        parts.append(f"[{escape(ref)} @ {ts}]")
    return " ".join(parts)


def _footer_callback(title: str):
    def _draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(_BODY, 8)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(_MARGIN, 10 * mm, title[:80])
        canvas.drawRightString(_PAGE_SIZE[0] - _MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return _draw


def write_semantic_manual_pdf(
    manual_dir: Path,
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    selection: ScreenshotSelection,
    source: DocumentationSource,
) -> Path:
    manual_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = manual_dir / f"{Path(source.video_name).stem}.pdf"
    styles = _styles()

    story: list = [Paragraph(escape(document.title), styles["title"])]
    story.append(_metadata_table(document, source, styles))
    story.append(Spacer(1, 4 * mm))

    if timeline.review_required_count:
        story.append(_review_callout(timeline, styles))
        story.append(Spacer(1, 4 * mm))

    if document.executive_summary:
        story.append(_summary_box(document.executive_summary, styles))
        summary_refs = _evidence_refs_line(executive_summary_evidence_refs(document), timeline)
        if summary_refs:
            story.append(Paragraph(summary_refs, styles["evidence_ref"]))
        story.append(Spacer(1, 4 * mm))

    picks_by_section: dict[str, list[Path]] = {}
    for pick in selection.picks:
        picks_by_section.setdefault(pick.section_id, []).append(manual_dir / "assets" / f"{pick.evidence_id}{pick.source_path.suffix}")

    for section in document.sections:
        if section.section_type == "EXECUTIVE_SUMMARY" and not section.claims and not section.summary:
            continue
        heading = escape(section.title or section.section_type.replace("_", " ").title())
        head_block: list = [Paragraph(heading, styles["heading"])]
        if section.summary:
            head_block.append(Paragraph(escape(section.summary), styles["body"]))
            refs = _evidence_refs_line(section.summary_evidence_refs, timeline)
            if refs:
                head_block.append(Paragraph(refs, styles["evidence_ref"]))
        story.append(KeepTogether(head_block))
        for claim in section.claims:
            refs = _evidence_refs_line(claim.evidence_refs, timeline)
            story.append(Paragraph(
                f"• {escape(claim.text)} <font name='{_ITALIC}' size='8.5' color='#2563eb'>{refs}</font>",
                styles["claim"],
            ))
        if section.claims:
            story.append(Spacer(1, 2 * mm))
        for path in picks_by_section.get(section.id, []):
            image = _make_image(path)
            if image is not None:
                story.append(image)
                story.append(Spacer(1, 2 * mm))

    for procedure in document.procedures:
        procedure_header = [
            Paragraph(f"Procedure: {escape(procedure.title)}", styles["heading"]),
            Paragraph(escape(procedure.purpose), styles["body"]) if procedure.purpose else Spacer(1, 1),
        ]
        if procedure.metadata_evidence_refs:
            procedure_header.append(Paragraph(
                _evidence_refs_line(procedure.metadata_evidence_refs, timeline), styles["evidence_ref"]
            ))
        if procedure.prerequisites:
            procedure_header.append(Paragraph(
                "Prerequisites: " + escape("; ".join(procedure.prerequisites)), styles["body"]
            ))
        story.append(KeepTogether(procedure_header))
        for step in procedure.steps:
            refs = _evidence_refs_line(step.evidence_refs, timeline)
            story.append(Paragraph(
                f"{step.order}. {escape(step.instruction)} "
                f"<font name='{_ITALIC}' size='8.5' color='#2563eb'>{refs}</font>",
                styles["claim"],
            ))
        story.append(Spacer(1, 3 * mm))
        if procedure.expected_outcomes:
            story.append(Paragraph(
                "Expected outcomes: " + escape("; ".join(procedure.expected_outcomes)), styles["body"]
            ))
        for path in picks_by_section.get(procedure.id, []):
            image = _make_image(path)
            if image is not None:
                story.append(image)
                story.append(Spacer(1, 2 * mm))

    if document.glossary:
        story.append(Paragraph("Glossary", styles["heading"]))
        for entry in document.glossary:
            story.append(Paragraph(f"• <b>{escape(entry.term)}</b> — {escape(entry.definition)}", styles["claim"]))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=16 * mm,
        title=f"Manual — {document.title}",
        author="Zo Media Intelligence",
    )
    footer = _footer_callback(document.title)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    shutil.copyfile(pdf_path, manual_dir / "MANUAL.pdf")
    return pdf_path
