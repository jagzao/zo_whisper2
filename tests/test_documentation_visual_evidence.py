from __future__ import annotations

from PIL import Image

from transcript_pipeline.documentation import visual_evidence


def _image(path, color=(245, 245, 245)):
    Image.new("RGB", (80, 50), color).save(path)
    return path


def test_ocr_outcomes_distinguish_success_no_text_failure_and_not_required(tmp_path, monkeypatch):
    path = _image(tmp_path / "screen.png")
    monkeypatch.setattr(visual_evidence, "_ocr_attempts", lambda _: ([ ("Queue", "--psm 6", 0.8) ], 0, False))
    assert visual_evidence.analyze_frame({"frame_file": path.name}, tmp_path)["ocr_status"] == "SUCCESS"

    monkeypatch.setattr(visual_evidence, "_ocr_attempts", lambda _: ([], 2, False))
    assert visual_evidence.analyze_frame({"frame_file": path.name}, tmp_path)["ocr_status"] == "NO_TEXT"
    monkeypatch.setattr(visual_evidence, "_ocr_attempts", lambda _: ([], 2, True))
    assert visual_evidence.analyze_frame({"frame_file": path.name}, tmp_path)["ocr_status"] == "FAILED"
    monkeypatch.setattr(visual_evidence, "_is_black", lambda _: True)
    assert visual_evidence.analyze_frame({"frame_file": path.name}, tmp_path)["ocr_status"] == "NOT_REQUIRED"


def test_ocr_retries_preprocessed_image_once_and_records_retry_count(tmp_path, monkeypatch):
    path = _image(tmp_path / "screen.png")
    calls = []

    def read_text(image, config):
        calls.append(config)
        return "" if len(calls) == 1 else "Queue Settings"

    monkeypatch.setattr(visual_evidence.pytesseract, "image_to_string", read_text)
    monkeypatch.setattr(visual_evidence.pytesseract, "image_to_data", lambda *args, **kwargs: {"conf": ["80"]})
    result = visual_evidence.analyze_frame({"frame_file": path.name, "timestamp": 20}, tmp_path)

    assert result["ocr_status"] == "SUCCESS"
    assert result["retry_count"] == 1
    assert result["engine"] == "tesseract"
    assert result["provenance"] == {"frame_id": "screen.png", "timestamp": 20.0, "image_path": str(path)}


def test_visual_type_and_keyframe_selection_keep_provenance_and_suppress_gallery_black_duplicates(tmp_path, monkeypatch):
    paths = [_image(tmp_path / f"{name}.png") for name in ("ui1", "ui2", "gallery", "black")]
    Image.new("RGB", (80, 50), (0, 0, 0)).save(paths[3])
    texts = {"ui1.png": "Queue Settings", "ui2.png": "Queue Settings", "gallery.png": "Participants"}
    monkeypatch.setattr(
        visual_evidence,
        "_ocr_attempts",
        lambda path: ([(texts[path.name], "--psm 6", 0.9)], 0, False) if path.name in texts else ([], 2, False),
    )

    result = visual_evidence.analyze_frames(
        [{"frame_file": path.name, "timestamp": index * 10} for index, path in enumerate(paths)], tmp_path
    )

    records = result["frames"]
    assert records[0]["selected"] is True
    assert records[0]["selection_reason"] in visual_evidence.SELECTION_REASONS
    assert records[0]["visual_type"] == "CONFIGURATION"
    assert records[0]["provenance"]["frame_id"] == "ui1.png"
    assert records[1]["selected"] is False
    assert records[2]["visual_type"] == "MEETING_GALLERY"
    assert records[2]["selected"] is False
    assert records[3]["visual_type"] == "BLACK_OR_EMPTY"
    assert records[3]["ocr_status"] == "NOT_REQUIRED"
