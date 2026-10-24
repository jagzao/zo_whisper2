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


def test_p_and_g_batch_stays_pending_until_explicit_release_gate(tmp_path, monkeypatch):
    videos = tmp_path / "Videos"
    transcriptions = tmp_path / "CarpetaTranscripciones"
    video = videos / "py_pg" / "pg_ready.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"media")
    frames = transcriptions / "py_pg" / "pg_ready_Frames" / "pg_ready"
    frames.mkdir(parents=True)
    (frames / "frame_0001.png").write_bytes(b"frame")
    (frames / "frame_mapping.json").write_text(
        json.dumps({"frames": [{"frame_file": "frame_0001.png"}]}), encoding="utf-8"
    )
    (transcriptions / "py_pg" / "pg_ready.txt").write_text("saved transcript", encoding="utf-8")
    project = {"name": "P&G", "match": {"folder_contains": ["py_pg"], "prefix": ["pg_"]}}
    monkeypatch.setattr(batch, "VIDEOS_DIR", videos)
    monkeypatch.setattr(batch, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(batch, "TRANSCRIPTIONS_DIR", transcriptions)
    monkeypatch.setattr(batch, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(batch, "load_projects", lambda _path: [project])
    monkeypatch.setenv("PG_DOCUMENTS_V2_ENABLED", "false")
    monkeypatch.setattr(batch, "regenerate_versioned", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must remain frozen")))

    result = batch.run_batch(manifest_path=tmp_path / "inventory.json")

    item = result["items"][0]
    assert item["state"] == "DOCUMENT_SYNTHESIS_PENDING_V2"
    assert item["evidence_state"] == "READY"
    assert item["documentation_status"] == "DOCUMENT_SYNTHESIS_PENDING_V2"
