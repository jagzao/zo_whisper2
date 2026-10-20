from transcript_pipeline.live_capture.playlist import PlaylistService
from transcript_pipeline.live_capture.service import CaptureService


def _playlist(tmp_path):
    capture = CaptureService(tmp_path / "Videos")
    session = capture.create_session("Continuous", capture_mode="playlist")
    return capture, session.session_id, PlaylistService(capture)


def _sample(service, session, text, offset, sequence, confidence=0.98):
    return service.observe(session, text, confidence, offset, sequence)


def test_title_boundaries_need_two_frames_and_map_inside_same_physical_chunk(tmp_path):
    capture, session_id, service = _playlist(tmp_path)
    one = "AMS KAP\nCompliance\nSession 1\n2026-08-05 12:29 UTC"
    two = "AMS KAP\nCompliance\nSession 2\n2026-08-05 12:44 UTC"
    assert _sample(service, session_id, one, 1000, 1)["logicalVideos"] == []
    assert len(_sample(service, session_id, one, 5000, 1)["logicalVideos"]) == 1
    assert len(_sample(service, session_id, two, 12000, 2)["logicalVideos"]) == 1
    result = _sample(service, session_id, two, 14000, 2)
    first, second = result["logicalVideos"]
    assert first["endOffsetMs"] == 12000
    assert second["startOffsetMs"] == 12000
    assert first["sessionNumber"] == 1 and second["sessionNumber"] == 2
    assert first["processingChunkIds"] == ["chunk-000000"]
    assert second["processingChunkIds"] == ["chunk-000000"]
    assert first["fragmentIds"] == ["fragment-000001", "fragment-000002"]
    assert second["fragmentIds"] == ["fragment-000002"]
    recovered = PlaylistService(capture).list(session_id)
    assert recovered["logicalVideos"] == result["logicalVideos"]


def test_low_confidence_title_stays_review_candidate_and_does_not_split(tmp_path):
    _, session_id, service = _playlist(tmp_path)
    title = "AMS KAP Compliance Session 1"
    _sample(service, session_id, title, 0, 1)
    confirmed = _sample(service, session_id, title, 5000, 1)
    pending = _sample(service, session_id, "uncertain slide words", 9000, 1, 0.45)
    assert pending["reviewCandidates"] == []
    result = _sample(service, session_id, "uncertain slide words", 10000, 1, 0.45)
    assert len(result["logicalVideos"]) == len(confirmed["logicalVideos"]) == 1
    candidate = result["reviewCandidates"][0]
    assert candidate["status"] == "NEEDS_TITLE_REVIEW"
    explicit = service.confirm_candidate(session_id, candidate["id"])
    assert len(explicit["logicalVideos"]) == 2
    assert explicit["logicalVideos"][1]["manuallyReviewed"] is True


def test_review_rename_date_split_and_merge_roundtrip(tmp_path):
    _, session_id, service = _playlist(tmp_path)
    title = "AMS KAP Compliance Session 1"
    service.observe(session_id, title, 0.98, 0, 1)
    row = service.observe(session_id, title, 0.98, 10000, 1)["logicalVideos"][0]
    service.observe(session_id, title, 0.98, 20000, 2)
    split = service.review(session_id, row["id"], "split", {"offsetMs": 15000, "fragmentSequence": 2})
    assert len(split["logicalVideos"]) == 2
    service.review(session_id, split["logicalVideos"][1]["id"], "rename", {"title": "Corrected"})
    dated = service.review(session_id, split["logicalVideos"][1]["id"], "recorded-date", {"recordedAt": "2026-08-05"})
    assert dated["logicalVideos"][1]["title"] == "Corrected"
    assert dated["logicalVideos"][1]["recordedAt"] == "2026-08-05"
    merged = service.review(session_id, split["logicalVideos"][0]["id"], "merge", {})
    assert len(merged["logicalVideos"]) == 1
