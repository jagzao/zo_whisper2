from transcript_pipeline.live_capture.integration import apply_capture_context
from transcript_pipeline.live_capture.pipeline import resolve_capture_context
from transcript_pipeline.live_capture.playlist import PlaylistService
from transcript_pipeline.live_capture.service import CaptureService


def test_confirmed_logical_video_metadata_enters_existing_chunk_pipeline(tmp_path):
    capture = CaptureService(tmp_path / "Videos")
    session = capture.create_session("Continuous", capture_mode="playlist")
    playlist = PlaylistService(capture)
    capture.start_chunk(session.session_id)
    capture.finalize_chunk(session.session_id, 0, b"synthetic chunk")
    title = "AMS KAP\nCompliance\nSession 7\n2026-08-05 12:29 UTC"
    playlist.observe(session.session_id, title, 0.98, 1000, 1)
    result = playlist.observe(session.session_id, title, 0.98, 5000, 1)
    assert result["logicalVideos"]
    media_path = capture.store.chunk_media_path(session.session_id, 0, ".webm")

    context = resolve_capture_context(media_path, videos_root=tmp_path / "Videos")

    assert context is not None
    assert context.logical_videos, (media_path, playlist._file(session.session_id).read_text())
    assert context.logical_videos[0]["id"] == result["logicalVideos"][0]["id"]
    assert context.logical_videos[0]["title"] == "AMS KAP Compliance Session 7"
    assert context.provenance()["logicalVideos"] == list(context.logical_videos)
    mapping = {}
    apply_capture_context(mapping, context)
    assert mapping["video_info"]["capture"]["logicalVideos"] == list(context.logical_videos)
