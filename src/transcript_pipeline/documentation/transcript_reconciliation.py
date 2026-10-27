"""Deterministic transcript identity and VAD recovery-window helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePath
from typing import Any


def normalize_media_basename(value: str) -> str:
    name = PurePath(str(value).replace("\\", "/")).name.casefold()
    name = re.sub(r"_segments\.json$", ".mp4", name)
    stem = name.removesuffix(".mp4")
    stem = re.sub(r"[ _.-](optimized|compressed|final)$", "", stem)
    normalized = re.sub(r"[^a-z0-9]+", "", stem)
    return normalized[2:] if normalized.startswith("pg") and len(normalized) > 2 else normalized


def transcript_content_hash(segments: list[dict[str, Any]]) -> str:
    payload = json.dumps(segments, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_sidecar_copies(sidecars: list[dict[str, Any]]) -> list[str]:
    """Return copy states in input order; divergent copies remain separate."""
    if not sidecars:
        return []
    hashes = [str(item.get("content_hash") or "") for item in sidecars]
    canonical = hashes[0]
    return [
        "CANONICAL" if index == 0 else ("DUPLICATE_IDENTICAL" if value == canonical else "DUPLICATE_DIVERGENT")
        for index, value in enumerate(hashes)
    ]


def merge_recovery_intervals(
    intervals: list[dict[str, Any]], *, max_gap_seconds: float = 5.0, padding_seconds: float = 2.0
) -> list[dict[str, Any]]:
    """Merge close VAD gaps only inside one speech region, retaining exact sources."""
    ordered = sorted(intervals, key=lambda item: (str(item.get("vad_region_id", "")), float(item["start"])))
    groups: list[list[dict[str, Any]]] = []
    for interval in ordered:
        region = interval.get("vad_region_id")
        if (
            groups
            and groups[-1][-1].get("vad_region_id") == region
            and float(interval["start"]) - float(groups[-1][-1]["end"]) <= max_gap_seconds
        ):
            groups[-1].append(interval)
        else:
            groups.append([interval])
    return [
        {
            "start": max(0.0, float(group[0]["start"]) - padding_seconds),
            "end": float(group[-1]["end"]) + padding_seconds,
            "vad_region_id": group[0].get("vad_region_id"),
            "source_interval_ids": [str(item["interval_id"]) for item in group],
        }
        for group in groups
    ]


def match_transcript_source(
    video_basename: str,
    source_audio: str | None,
    *,
    database_name: str | None = None,
    video_size: int | None = None,
    database_size: int | None = None,
) -> dict[str, str]:
    """Resolve only source-proven or corroborated identity; never fuzzy-match names."""
    audio_name = PurePath(str(source_audio or "").replace("\\", "/")).name
    if audio_name and normalize_media_basename(audio_name) == normalize_media_basename(video_basename):
        db_ok = (
            database_name is not None
            and normalize_media_basename(database_name) == normalize_media_basename(video_basename)
            and video_size is not None
            and database_size == video_size
        )
        return {"status": "MATCHED", "method": "PROCESSING_DB_PROVENANCE" if db_ok else "MEDIA_ID", "confidence": "HIGH"}
    exact = bool(audio_name) and audio_name.casefold() == video_basename.casefold()
    if exact:
        return {"status": "MATCHED", "method": "EXACT_BASENAME", "confidence": "MEDIUM"}
    return {"status": "AMBIGUOUS" if audio_name else "MISSING", "method": "MANUAL_REVIEW" if audio_name else "NONE", "confidence": "LOW" if audio_name else "NONE"}
