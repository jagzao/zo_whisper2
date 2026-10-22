import json

from transcript_pipeline.documentation import batch_regenerate_v2 as batch


def test_corpus_inventory_reports_missing_artifacts_and_excludes_capture_chunks(tmp_path, monkeypatch):
    videos = tmp_path / "Videos"
    audio = tmp_path / "audio"
    transcriptions = tmp_path / "CarpetaTranscripciones"
    ready = videos / "general" / "ready.mp4"
    transcript_only = videos / "general" / "transcript_only.mp4"
    empty_mapping = videos / "general" / "empty_mapping.mp4"
    needs_transcript = videos / "general" / "needs_transcript.mp4"
    final_capture = videos / "live_capture" / "session" / "final" / "recording.webm"
    internal_chunk = videos / "live_capture" / "session" / "chunks" / "0001.webm"
    for media in (ready, transcript_only, empty_mapping, needs_transcript, final_capture, internal_chunk):
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"media")

    ready_frames = transcriptions / "general" / "ready_Frames" / "ready"
    ready_frames.mkdir(parents=True)
    (ready_frames / "frame_0001.png").write_bytes(b"frame")
    (ready_frames / "frame_mapping.json").write_text(
        json.dumps({"frames": [{"frame_file": "frame_0001.png"}]}), encoding="utf-8"
    )
    empty_frames = transcriptions / "general" / "empty_mapping_Frames" / "empty_mapping"
    empty_frames.mkdir(parents=True)
    (empty_frames / "frame_mapping.json").write_text(json.dumps({"frames": []}), encoding="utf-8")
    needs_transcript_frames = transcriptions / "general" / "needs_transcript_Frames" / "needs_transcript"
    needs_transcript_frames.mkdir(parents=True)
    (needs_transcript_frames / "frame_0001.png").write_bytes(b"frame")
    (needs_transcript_frames / "frame_mapping.json").write_text(
        json.dumps({"frames": [{"frame_file": "frame_0001.png"}]}), encoding="utf-8"
    )
    transcript = transcriptions / "general" / "transcript_only.txt"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("saved transcript", encoding="utf-8")
    (transcriptions / "general" / "ready.txt").write_text("captured transcript", encoding="utf-8")

    monkeypatch.setattr(batch, "VIDEOS_DIR", videos)
    monkeypatch.setattr(batch, "AUDIO_DIR", audio)
    monkeypatch.setattr(batch, "TRANSCRIPTIONS_DIR", transcriptions)

    items = batch._discover([])
    states = {item["name"]: item["state"] for item in items}

    assert states == {
        "ready.mp4": "READY",
        "transcript_only.mp4": "NEEDS_KEYFRAMES_ONLY",
        "empty_mapping.mp4": "NEEDS_TRANSCRIPT_AND_KEYFRAMES",
        "needs_transcript.mp4": "NEEDS_TRANSCRIPT",
        "recording.webm": "NEEDS_TRANSCRIPT_AND_KEYFRAMES",
    }
