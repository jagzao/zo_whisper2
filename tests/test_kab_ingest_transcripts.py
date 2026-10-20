"""T38-T41: deterministic session transcripts with offsets, order, provenance."""

from __future__ import annotations

import json

from transcript_pipeline.kab_ingest import transcripts
from tests.kab_ingest_utils import make_store, session_payload


def _result(segment_index: int, start_offset_ms: int, segments: list[dict], language: str = "es") -> dict:
    return {
        "schemaVersion": 1,
        "sessionId": "sess-0001",
        "segmentIndex": segment_index,
        "startOffsetMs": start_offset_ms,
        "durationMs": 2000,
        "media": {"kind": "video", "file": f"segment-{segment_index:06d}.mp4"},
        "transcription": {"text": " ".join(s["text"] for s in segments), "language": language, "durationSec": 2.0, "segments": segments},
        "docsGenerated": False,
        "docsManualDir": None,
        "framesDir": None,
    }


def _write_result(store, result: dict) -> None:
    from transcript_pipeline.kab_ingest.atomic import atomic_write_json

    atomic_write_json(store.paths("sess-0001").result_file(result["segmentIndex"]), result)


def _session_with_store(tmp_path):
    store = make_store(tmp_path)
    store.create_session(session_payload(requiredTracks=["video"]))
    return store


def test_t38_offsets_shift_local_timestamps(tmp_path):
    store = _session_with_store(tmp_path)
    _write_result(store, _result(0, 0, [{"start": 0.0, "end": 1.0, "text": "uno"}, {"start": 1.0, "end": 2.0, "text": "dos"}]))
    _write_result(store, _result(1, 30_000, [{"start": 0.0, "end": 1.5, "text": "tres"}]))

    entries = transcripts.flatten_transcript_segments(_result(1, 30_000, [{"start": 0.25, "end": 1.5, "text": "tres"}]))
    assert entries[0]["localStart"] == 30.25
    assert entries[0]["localEnd"] == 31.5
    assert entries[0]["sourceSegmentIndex"] == 1

    out = transcripts.regenerate(store, tmp_path, "sess-0001")
    segments_doc = json.loads((out / transcripts.SEGMENTS_JSON).read_text(encoding="utf-8"))
    locals_sorted = [(s["sourceSegmentIndex"], s["localStart"]) for s in segments_doc["segments"]]
    assert locals_sorted == sorted(locals_sorted)
    assert locals_sorted[0] == (0, 0.0)
    assert locals_sorted[-1] == (1, 30.0)
    assert segments_doc["language"] == "es"


def test_t39_segments_json_provenance_and_transcript_order(tmp_path):
    store = _session_with_store(tmp_path)
    _write_result(store, _result(0, 500, [{"start": 0.0, "end": 1.0, "text": "primero"}]))
    _write_result(store, _result(1, 1500, [{"start": 0.0, "end": 1.0, "text": "segundo"}]))
    out = transcripts.regenerate(store, tmp_path, "sess-0001")

    doc = json.loads((out / transcripts.SEGMENTS_JSON).read_text(encoding="utf-8"))
    assert doc["sessionId"] == "sess-0001"
    for entry in doc["segments"]:
        assert set(("sourceSegmentIndex", "localStart", "localEnd", "text")) <= set(entry)
    assert doc["segments"][0]["sourceSegmentIndex"] == 0
    assert doc["segments"][0]["localStart"] == 0.5
    assert doc["segments"][1]["sourceSegmentIndex"] == 1
    assert doc["segments"][1]["localStart"] == 1.5

    txt = (out / transcripts.TRANSCRIPT_TXT).read_text(encoding="utf-8")
    assert txt.index("primero") < txt.index("segundo")
    assert "(segment 000000)" in txt


def test_t40_manifest_lists_processed_segments(tmp_path):
    store = _session_with_store(tmp_path)
    _write_result(store, _result(0, 0, [{"start": 0.0, "end": 1.0, "text": "a"}], language="en"))
    out = transcripts.regenerate(store, tmp_path, "sess-0001")
    manifest = json.loads((out / transcripts.MANIFEST_JSON).read_text(encoding="utf-8"))
    assert manifest["sessionId"] == "sess-0001"
    assert manifest["language"] == "en"
    assert manifest["segments"][0]["segmentIndex"] == 0
    assert manifest["segments"][0]["state"] == "PROCESSED"
    assert manifest["segments"][0]["docsGenerated"] is False


def test_t41_incremental_regeneration_is_atomic_and_cumulative(tmp_path):
    store = _session_with_store(tmp_path)
    _write_result(store, _result(0, 0, [{"start": 0.0, "end": 1.0, "text": "a"}]))
    out = transcripts.regenerate(store, tmp_path, "sess-0001")
    first = json.loads((out / transcripts.SEGMENTS_JSON).read_text(encoding="utf-8"))
    assert [s["sourceSegmentIndex"] for s in first["segments"]] == [0]

    _write_result(store, _result(1, 1000, [{"start": 0.0, "end": 1.0, "text": "b"}]))
    out = transcripts.regenerate(store, tmp_path, "sess-0001")
    second = json.loads((out / transcripts.SEGMENTS_JSON).read_text(encoding="utf-8"))
    assert [s["sourceSegmentIndex"] for s in second["segments"]] == [0, 1]
    assert not list(out.glob("*.tmp"))
