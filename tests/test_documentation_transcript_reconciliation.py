from transcript_pipeline.documentation.transcript_reconciliation import (
    classify_sidecar_copies,
    match_transcript_source,
    merge_recovery_intervals,
    normalize_media_basename,
    transcript_content_hash,
)


def test_recovery_micro_gaps_merge_with_source_interval_ids():
    windows = merge_recovery_intervals([
        {"interval_id": "a", "start": 12.1, "end": 12.5, "vad_region_id": "r1"},
        {"interval_id": "b", "start": 12.7, "end": 13.0, "vad_region_id": "r1"},
        {"interval_id": "c", "start": 13.1, "end": 13.4, "vad_region_id": "r1"},
    ])
    assert len(windows) == 1
    assert windows[0]["source_interval_ids"] == ["a", "b", "c"]
    assert windows[0]["start"] == 10.1
    assert windows[0]["end"] == 15.4


def test_recovery_windows_do_not_merge_across_vad_regions():
    intervals = [
        {"interval_id": "a", "start": 2, "end": 3, "vad_region_id": "r1"},
        {"interval_id": "b", "start": 3.2, "end": 4, "vad_region_id": "r2"},
    ]
    assert len(merge_recovery_intervals(intervals)) == 2


def test_normalizes_pg_prefix_suffix_and_separator_variants():
    assert normalize_media_basename("pg_AMS_KAP_-_Compliance_-_Session_2_optimized.mp4") == normalize_media_basename(
        "pg_AMS KAP – Compliance – Session 2.mp4"
    )
    assert normalize_media_basename("pg_session_2_final.mp4") == normalize_media_basename("Session 2.mp4")


def test_source_identity_requires_corrobating_metadata_or_exact_source_name():
    result = match_transcript_source(
        "pg_AMS KAP – Compliance – Session 7.mp4",
        "/data/Videos/py_pg/pg_AMS KAP – Compliance – Session 7.mp4",
        database_name="pg_AMS KAP – Compliance – Session 7.mp4",
        video_size=123,
        database_size=123,
    )
    assert result == {"status": "MATCHED", "method": "PROCESSING_DB_PROVENANCE", "confidence": "HIGH"}
    assert match_transcript_source("session 7.mp4", "session 7 old.mp4")["status"] == "AMBIGUOUS"


def test_missing_transcript_is_distinct_from_provenanced_alias():
    assert match_transcript_source("source.mp4", None)["status"] == "MISSING"
    alias = match_transcript_source(
        "pg_source.mp4", "C:/uploads/optimized/source.mp4",
        database_name="pg_source.mp4", video_size=42, database_size=42,
    )
    assert alias == {"status": "MATCHED", "method": "PROCESSING_DB_PROVENANCE", "confidence": "HIGH"}


def test_duplicate_transcripts_deduplicate_by_segment_content_and_keep_divergence():
    same = transcript_content_hash([{"start": 0, "end": 1, "text": "hello"}])
    different = transcript_content_hash([{"start": 0, "end": 1, "text": "goodbye"}])
    assert classify_sidecar_copies([{"content_hash": same}, {"content_hash": same}]) == [
        "CANONICAL", "DUPLICATE_IDENTICAL"
    ]
    assert classify_sidecar_copies([{"content_hash": same}, {"content_hash": different}]) == [
        "CANONICAL", "DUPLICATE_DIVERGENT"
    ]
