from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont

from transcript_pipeline.live_capture.playlist import ocr_title_image
from transcript_pipeline.live_capture.titles import MultiFrameTitleConfirmer, parse_title_text


def test_parse_title_family_category_session_and_displayed_time():
    item = parse_title_text("AMS KAP\nCompliance\nSession 12\n2026-08-05 12:29 UTC", 0.98)
    assert item.title == "AMS KAP Compliance Session 12"
    assert item.category == "Compliance"
    assert item.session_number == 12
    assert item.displayed_at == "2026-08-05 12:29 UTC"
    assert item.confidence == 0.98
    assert item.status == "CANDIDATE"


def test_parser_accepts_other_title_families_without_exact_title_hardcoding():
    item = parse_title_text("App Support onboarding / Session 3")
    assert item.session_number == 3
    assert item.category == "App Support"


def test_unknown_or_ambiguous_title_requires_review_without_inventing_fields():
    item = parse_title_text("A slide with incidental words", 0.9)
    assert item.title == "A slide with incidental words"
    assert item.session_number is None
    assert item.displayed_at is None
    assert item.status == "NEEDS_TITLE_REVIEW"
    assert item.confidence <= 0.6


def test_confirmation_requires_multiple_frames_and_marks_only_stable_change():
    confirm = MultiFrameTitleConfirmer(stable_samples=3)
    first = parse_title_text("AMS KAP Compliance Session 1")
    second = parse_title_text("AMS KAP Compliance Session 2")
    assert confirm.observe(first)["confirmed"] is False
    assert confirm.observe(first)["confirmed"] is False
    assert confirm.observe(first)["confirmed"] is True
    assert confirm.observe(second)["boundary"] is False
    assert confirm.observe(second)["boundary"] is False
    change = confirm.observe(second)
    assert change["confirmed"] is True
    assert change["boundary"] is True


def test_low_confidence_sample_never_confirms_or_splits():
    confirm = MultiFrameTitleConfirmer(stable_samples=2)
    title = parse_title_text("AMS KAP Compliance Session 1", 0.5)
    assert confirm.observe(title) == {
        "status": "NEEDS_TITLE_REVIEW", "confirmed": False, "boundary": False, "count": 0,
    }


def test_synthetic_title_card_runs_through_local_tesseract():
    import pytesseract

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract executable unavailable")
    image = Image.new("RGB", (1280, 720), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("arial.ttf", 64)
    for y, line in ((100, "AMS KAP"), (220, "Compliance"), (340, "Session 17"), (460, "2026-08-05 12:29 UTC")):
        draw.text((80, y), line, font=font, fill="black")
    encoded = BytesIO()
    image.save(encoded, format="JPEG")
    text, confidence = ocr_title_image(encoded.getvalue())
    result = parse_title_text(text, confidence)
    assert result.session_number == 17
    assert result.category == "Compliance"
    assert result.displayed_at == "2026-08-05 12:29 UTC"
    assert result.status == "CANDIDATE"
