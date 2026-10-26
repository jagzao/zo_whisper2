from __future__ import annotations

from PIL import Image, ImageDraw

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
    paths = [_image(tmp_path / f"{name}.png") for name in ("ui1", "ui2", "ui3", "gallery", "black")]
    Image.new("RGB", (80, 50), (0, 0, 0)).save(paths[4])
    texts = {
        "ui1.png": "Queue Settings",
        "ui2.png": "Queue Settings",
        "ui3.png": "Queue Settings API URL",
        "gallery.png": "Participants",
    }
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
    assert records[2]["selected"] is True
    assert records[2]["selection_reason"] in {"OCR_CHANGE", "TOPIC_BOUNDARY"}
    assert records[2]["unique_information"]
    assert records[2]["ocr_text_signature"]
    assert records[2]["perceptual_signature"]
    assert records[2]["topic"].startswith("CONFIGURATION:")
    assert records[3]["visual_type"] == "MEETING_GALLERY"
    assert records[3]["selected"] is False
    assert records[4]["visual_type"] == "BLACK_OR_EMPTY"
    assert records[4]["ocr_status"] == "NOT_REQUIRED"
    assert result["visual_coverage_gate"] == "PASS"


def test_visual_classifier_avoids_architecture_claim_from_generic_words_and_suppresses_speaker_tile(tmp_path):
    assert visual_evidence._classify("Application Services Database", 0.9, False)[0] != "ARCHITECTURE_DIAGRAM"
    path = Image.new("RGB", (400, 320), (15, 15, 15))
    ImageDraw.Draw(path).ellipse((182, 122, 218, 158), fill=(245, 245, 245))
    image_path = tmp_path / "speaker.png"
    path.save(image_path)

    assert visual_evidence._has_centered_speaker_tile(image_path, "Speaker") is True
    assert visual_evidence._classify("Speaker", 0.9, False, speaker_tile=True)[0] == "MEETING_GALLERY"


def test_explicit_diagram_edges_keep_frame_provenance_and_render_deterministically(tmp_path, monkeypatch):
    path = _image(tmp_path / "diagram.png")
    monkeypatch.setattr(
        visual_evidence,
        "_ocr_attempts",
        lambda _: ([ ("Web App -> API Gateway", "--psm 6", 0.9) ], 0, False),
    )

    result = visual_evidence.analyze_frames(
        [{"frame_file": path.name, "timestamp": 12.5}], tmp_path, source_video="S41.mp4"
    )

    record = result["frames"][0]
    assert record["visual_type"] == "FLOW_DIAGRAM"
    assert record["edges"][0]["source"] == "Web App"
    assert record["edges"][0]["target"] == "API Gateway"
    assert record["edges"][0]["provenance"]["frame_id"] == path.name
    diagram = result["derived_diagrams"][0]
    assert diagram["source_video"] == "S41.mp4"
    assert diagram["timestamps"] == [12.5]
    assert diagram["source_frames"][0]["frame_id"] == path.name
    assert diagram["mermaid"].startswith("flowchart LR")


def test_participant_name_grid_is_suppressed_but_shared_application_screen_is_retained():
    gallery = "Alex Smith\nJordan Lee\nTaylor Brown\nMorgan Jones\nRiley Wilson\nCasey Davis"
    shared_screen = f"{gallery}\nPGRegDoc.com\nApplication Overview\nAzure database and support group"

    assert visual_evidence._classify(gallery, 0.9, False)[0] == "MEETING_GALLERY"
    assert visual_evidence._classify(shared_screen, 0.9, False)[0] != "MEETING_GALLERY"


def test_visual_topics_use_nearby_evidence_instead_of_one_generic_ui_bucket():
    assert visual_evidence._topic_for(
        "APPLICATION_UI", "SESSION_GENERAL", "records the daily production matrix"
    ) == "WORKFLOW:SESSION_GENERAL"
    assert visual_evidence._topic_for(
        "APPLICATION_UI", "SESSION_GENERAL", "AMS support is responsible for access tickets"
    ) == "ACCESS:SESSION_GENERAL"
    assert visual_evidence._topic_for(
        "APPLICATION_UI", "SESSION_GENERAL", "SQL database query and table"
    ) == "DATABASE:SESSION_GENERAL"


def test_semantic_topic_audit_does_not_change_existing_v2_visual_gate():
    report = {
        "frames": [
            {"frame_id": "f1", "timestamp": 1, "source_image": "f1.png", "ocr_status": "LOW_CONFIDENCE",
             "ocr_text": "", "visual_type": "APPLICATION_UI", "topic": "APPLICATION_UI:SESSION_GENERAL",
             "semantic_topic": "WORKFLOW:SESSION_GENERAL", "selected": True},
        ]
    }
    result = visual_evidence.apply_semantic_review(report, [])

    assert result["visual_coverage_gate"] == "PASS"
    assert result["semantic_topic_coverage_gate"] == "FAIL"
    assert result["semantic_topics_uncovered"] == ["WORKFLOW:SESSION_GENERAL"]


def test_reviewed_visual_topics_cover_distinct_content_with_frame_provenance():
    report = {"frames": [
        {"frame_id": "overview.png", "timestamp": 10, "source_image": "overview.png",
         "ocr_status": "SUCCESS", "ocr_text": "Overview", "visual_type": "OTHER"},
        {"frame_id": "flow.png", "timestamp": 20, "source_image": "flow.png",
         "ocr_status": "SUCCESS", "ocr_text": "Flow", "visual_type": "OTHER"},
    ]}
    reviews = [
        {"frame_id": "overview.png", "timestamp": 10, "visual_type": "PRESENTATION_SLIDE",
         "application": "PG_REGDOC", "topic": "OVERVIEW", "selected": True,
         "selection_reason": "SCENE_CHANGE", "components": ["PGRegDoc.com"], "confidence": .9},
        {"frame_id": "flow.png", "timestamp": 20, "visual_type": "FLOW_DIAGRAM",
         "application": "PG_REGDOC", "topic": "DATA_FLOW", "selected": True,
         "selection_reason": "ARCHITECTURE", "relationships": ["browser to application"], "confidence": .9,
         "supporting_evidence_ids": ["E-008"]},
    ]

    result = visual_evidence.apply_semantic_review(report, reviews)

    assert result["visual_coverage_gate"] == "PASS"
    assert result["visual_topics_discovered"] == ["DATA_FLOW", "OVERVIEW"]
    assert result["selected_count"] == 2
    assert result["frames"][1]["assertions"][0]["provenance"]["frame_id"] == "flow.png"
    assert result["frames"][1]["assertions"][0]["provenance"]["supporting_evidence_ids"] == ["E-008"]


def test_reviewed_visual_topic_rejects_frame_timestamp_mismatch():
    report = {"frames": [{"frame_id": "f.png", "timestamp": 10, "ocr_status": "SUCCESS"}]}
    review = [{"frame_id": "f.png", "timestamp": 11, "visual_type": "OTHER", "application": "APP"}]
    try:
        visual_evidence.apply_semantic_review(report, review)
    except ValueError as error:
        assert "timestamp" in str(error)
    else:
        raise AssertionError("mismatched provenance timestamp was accepted")
