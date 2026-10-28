"""Quality primitives for evidence-backed application mission packs."""

from __future__ import annotations

import re
from typing import Any

CLAIM_STATES = {
    "VISUAL_CONFIRMED",
    "MULTI_SOURCE_CONFIRMED",
    "SOURCE_CONFIRMED",
    "SOURCE_UNCERTAIN",
    "EXTERNAL_VERIFIED",
    "CONFLICTING",
    "NEEDS_REVIEW",
}
QUALITY_STATES = {"PASS", "PARTIAL", "FAIL", "NOT_EVALUATED"}
QUALITY_GATES = (
    "SOURCE_COVERAGE",
    "CLAIM_GROUNDING",
    "AMBIGUITY_HANDLING",
    "APP_SEGMENTATION",
    "SUPPORT_SCOPE",
    "DATA_FLOW",
    "ARCHITECTURE",
    "ACCESS_AUTH",
    "OWNERSHIP",
    "OPERATIONS",
    "RISKS",
    "OPEN_QUESTIONS",
    "FOLLOW_UPS",
    "EVIDENCE_TIMELINE",
    "SOURCE_MAPPING",
)
TRANSCRIPT_STATES = {"VALID", "PARTIAL", "MISSING", "FAILED", "NEEDS_REVIEW"}
NON_SPEECH_VAD_CLASSES = {
    "NOISE", "MUSIC", "REMOTE_AUDIO_ARTIFACT", "SILENCE_BOUNDARY", "FALSE_POSITIVE_VAD",
}
CLAIM_FIELDS = {
    "claim_id",
    "application_id",
    "claim",
    "source_type",
    "source_id",
    "timestamp",
    "frame_id",
    "confidence",
    "verification_state",
    "first_seen",
    "last_confirmed",
    "supporting_sources",
    "conflicts",
}


def measure_source_coverage(
    video_duration: float,
    transcript_segments: list[dict[str, Any]],
    visual_timestamps: list[float],
    *,
    major_gap_seconds: float = 300,
) -> dict[str, Any]:
    """Measure transcript reach and sampled-frame span without calling samples continuous coverage."""
    duration = max(0.0, float(video_duration))
    starts = [float(s["start"]) for s in transcript_segments if s.get("start") is not None]
    ends = [float(s["end"]) for s in transcript_segments if s.get("end") is not None]
    first = min(starts, default=None)
    last = max(ends, default=None)
    visual = sorted(float(t) for t in visual_timestamps)
    gaps: list[dict[str, Any]] = [
        {"start": float(a["end"]), "end": float(b["start"]), "seconds": float(b["start"]) - float(a["end"])}
        for a, b in zip(transcript_segments, transcript_segments[1:])
        if a.get("end") is not None and b.get("start") is not None
        and float(b["start"]) - float(a["end"]) > 30
    ]
    leading = first if first is not None else duration
    trailing = max(0.0, duration - last) if last is not None else duration
    transcript_reach = min(100.0, 100.0 * last / duration) if duration and last is not None else 0.0
    transcript_span = max(0.0, last - first) if first is not None and last is not None else 0.0
    visual_span = max(0.0, visual[-1] - visual[0]) if len(visual) > 1 else 0.0
    gaps.append({"start": last or 0.0, "end": duration, "seconds": trailing, "kind": "trailing"})
    if leading:
        gaps.append({"start": 0.0, "end": leading, "seconds": leading, "kind": "leading"})
    status = "SOURCE_INCOMPLETE" if trailing >= major_gap_seconds or transcript_reach < 85 else "READY"
    return {
        "video_duration_seconds": duration,
        "transcript_first_timestamp_seconds": first,
        "transcript_last_timestamp_seconds": last,
        "transcript_last_timestamp_coverage_percent": round(transcript_reach, 2),
        "transcript_span_coverage_percent": round(100.0 * transcript_span / duration, 2) if duration else 0.0,
        "leading_gap_seconds": round(leading, 3),
        "trailing_gap_seconds": round(trailing, 3),
        "visual_frame_count": len(visual),
        "visual_first_timestamp_seconds": visual[0] if visual else None,
        "visual_last_timestamp_seconds": visual[-1] if visual else None,
        "visual_sampled_span_percent": round(100.0 * visual_span / duration, 2) if duration else 0.0,
        "visual_sampling_is_continuous": False,
        "unexplained_gaps": gaps,
        "status": status,
    }


def assess_transcript_quality(
    video_duration: float,
    transcript_segments: list[dict[str, Any]],
    *,
    major_gap_seconds: float = 300,
    valid_coverage_percent: float = 95,
    trailing_gap_classification: str | None = None,
    vad_speech_segments: list[dict[str, Any]] | None = None,
    supplemental_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Measure timestamp reach and gaps; sparse or malformed transcripts fail closed."""
    duration = float(video_duration or 0)
    if duration <= 0:
        return {"transcript_state": "NEEDS_REVIEW", "reason": "video_duration_unavailable"}
    if not transcript_segments and not supplemental_segments:
        return {
            "video_duration": duration, "transcript_start": None,
            "transcript_last_timestamp": None, "transcript_span": 0.0,
            "transcript_coverage_percent": 0.0, "speech_gaps": [],
            "final_gap": duration, "transcript_state": "MISSING",
        }

    normalized: list[tuple[float, float]] = []
    all_transcript_segments = [*transcript_segments, *(supplemental_segments or [])]
    for segment in all_transcript_segments:
        try:
            start, end = float(segment["start"]), float(segment["end"])
        except (KeyError, TypeError, ValueError):
            return {"video_duration": duration, "transcript_state": "FAILED", "reason": "invalid_segment_timestamps"}
        if start < 0 or end < start or end > duration + 30:
            return {"video_duration": duration, "transcript_state": "FAILED", "reason": "out_of_range_segment"}
        normalized.append((start, end))
    normalized.sort()
    first, last = normalized[0][0], max(end for _, end in normalized)
    gaps: list[dict[str, Any]] = [
        {"start": previous_end, "end": start, "seconds": round(start - previous_end, 3)}
        for (_, previous_end), (start, _) in zip(normalized, normalized[1:])
        if start - previous_end > 30
    ]
    final_gap = max(0.0, duration - last)
    if final_gap > 30:
        gaps.append({"start": last, "end": duration, "seconds": round(final_gap, 3), "kind": "final"})
    span = max(0.0, last - first)
    coverage = min(100.0, 100.0 * last / duration)
    vad_total = 0.0
    vad_covered = 0.0
    vad_untranscribed: list[dict[str, float]] = []
    if vad_speech_segments is not None:
        transcript_intervals = sorted(normalized)
        for speech in vad_speech_segments:
            speech_start, speech_end = float(speech["start"]), float(speech["end"])
            if speech_end <= speech_start:
                continue
            vad_total += speech_end - speech_start
            intervals = sorted(
                (max(speech_start, seg_start), min(speech_end, seg_end))
                for seg_start, seg_end in transcript_intervals
                if seg_end > speech_start and seg_start < speech_end
            )
            merged: list[list[float]] = []
            for overlap_start, overlap_end in intervals:
                if overlap_end <= overlap_start:
                    continue
                if merged and overlap_start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], overlap_end)
                else:
                    merged.append([overlap_start, overlap_end])
            covered = sum(end - start for start, end in merged)
            vad_covered += covered
            cursor = speech_start
            for overlap_start, overlap_end in merged:
                if overlap_start - cursor > 3:
                    vad_untranscribed.append({"start": round(cursor, 3), "end": round(overlap_start, 3), "seconds": round(overlap_start - cursor, 3)})
                cursor = max(cursor, overlap_end)
            if speech_end - cursor > 3:
                vad_untranscribed.append({"start": round(cursor, 3), "end": round(speech_end, 3), "seconds": round(speech_end - cursor, 3)})
    speech_coverage = 100.0 * vad_covered / vad_total if vad_total else None
    speech_coverage_valid = (
        vad_speech_segments is not None
        and speech_coverage is not None
        and speech_coverage >= valid_coverage_percent
        and all(gap["seconds"] <= major_gap_seconds for gap in vad_untranscribed)
    )
    leading_gap = first
    if leading_gap > 30:
        gaps.insert(0, {"start": 0.0, "end": first, "seconds": round(leading_gap, 3), "kind": "leading"})
    internal_gaps = [gap for gap in gaps if gap.get("kind") not in {"leading", "final"}]
    tail_explained = trailing_gap_classification == "NON_SPEECH_TRAILING_MEDIA" and speech_coverage_valid
    state = "VALID" if (
        (coverage >= valid_coverage_percent or tail_explained)
        and leading_gap <= major_gap_seconds
        and all(gap["seconds"] <= major_gap_seconds for gap in internal_gaps)
    ) else "PARTIAL"
    return {
        "video_duration": round(duration, 3), "transcript_start": round(first, 3),
        "leading_gap": round(leading_gap, 3),
        "transcript_last_timestamp": round(last, 3), "transcript_span": round(span, 3),
        "transcript_coverage_percent": round(coverage, 2), "speech_gaps": gaps,
        "media_coverage_percent": round(coverage, 2),
        "speech_coverage_percent": round(speech_coverage, 2) if speech_coverage is not None else None,
        "vad_speech_seconds": round(vad_total, 3),
        "transcribed_speech_seconds": round(vad_covered, 3),
        "uncovered_speech_seconds": round(max(0.0, vad_total - vad_covered), 3),
        "final_gap": round(final_gap, 3), "transcript_state": state,
        "trailing_gap_classification": trailing_gap_classification or "NEEDS_REVIEW",
        "vad_speech_coverage_percent": round(speech_coverage, 2) if speech_coverage is not None else None,
        "vad_untranscribed_speech_gaps": vad_untranscribed,
    }


def reconcile_speech_interval_coverage(
    vad_speech_seconds: float,
    transcribed_speech_seconds: float,
    interval_classifications: list[dict[str, Any]],
    *,
    valid_coverage_percent: float = 95.0,
) -> dict[str, Any]:
    """Separate non-speech VAD positives from actual missing or unintelligible speech."""
    total = max(0.0, float(vad_speech_seconds))
    transcribed = min(total, max(0.0, float(transcribed_speech_seconds)))
    excluded = sum(max(0.0, float(item.get("seconds", 0))) for item in interval_classifications
                   if item.get("classification") in NON_SPEECH_VAD_CLASSES)
    meaningful = sum(max(0.0, float(item.get("seconds", 0))) for item in interval_classifications
                     if item.get("classification") in {"ACTUAL_MISSING_SPEECH", "UNINTELLIGIBLE"})
    unresolved = sum(max(0.0, float(item.get("seconds", 0))) for item in interval_classifications
                     if item.get("classification") not in NON_SPEECH_VAD_CLASSES | {
                         "ACTUAL_MISSING_SPEECH", "UNINTELLIGIBLE", "COVERED"
                     })
    denominator = max(0.0, total - min(total, excluded))
    effective = min(100.0, 100.0 * transcribed / denominator) if denominator else 100.0
    return {
        "vad_speech_seconds": round(total, 3),
        "transcribed_speech_seconds": round(transcribed, 3),
        "uncovered_speech_seconds": round(max(0.0, total - transcribed), 3),
        "excluded_non_speech_vad_seconds": round(min(total, excluded), 3),
        "meaningful_uncovered_speech_seconds": round(meaningful, 3),
        "unclassified_seconds": round(unresolved, 3),
        "raw_speech_coverage_percent": round(100.0 * transcribed / total, 2) if total else 0.0,
        "effective_speech_coverage_percent": round(effective, 2),
        "state": "VALID" if effective >= valid_coverage_percent and unresolved == 0 else "NEEDS_REVIEW",
    }


def classify_trailing_gap(
    tail_start: float,
    video_duration: float,
    speech_segments: list[dict[str, Any]],
    visual_samples: list[dict[str, Any]],
    *,
    vad_completed: bool,
    minimum_visual_samples: int = 3,
    visual_coverage_threshold: float = 0.8,
) -> dict[str, Any]:
    """Classify an apparent transcript tail only when VAD and sampled visuals agree."""
    duration = max(0.0, float(video_duration))
    start = max(0.0, float(tail_start))
    tail_speech = [
        segment for segment in speech_segments
        if float(segment.get("end", 0)) > start and float(segment.get("start", duration)) < duration
    ]
    samples = [sample for sample in visual_samples if start <= float(sample.get("timestamp", -1)) <= duration]
    non_speech_visuals = sum(
        sample.get("visual_type") in {"MEETING_GALLERY", "BLACK_OR_EMPTY"} for sample in samples
    )
    visual_fraction = non_speech_visuals / len(samples) if samples else 0.0
    if tail_speech:
        classification = "UNTRANSCRIBED_SPEECH_GAP"
    elif (
        vad_completed
        and len(samples) >= minimum_visual_samples
        and samples[0].get("timestamp", duration) <= start + 60
        and samples[-1].get("timestamp", -1) >= duration - 60
        and visual_fraction >= visual_coverage_threshold
    ):
        classification = "NON_SPEECH_TRAILING_MEDIA"
    else:
        classification = "NEEDS_REVIEW"
    return {
        "classification": classification,
        "tail_start": round(start, 3),
        "video_duration": round(duration, 3),
        "vad_completed": bool(vad_completed),
        "vad_speech_segment_count": len(tail_speech),
        "visual_sample_count": len(samples),
        "non_speech_visual_fraction": round(visual_fraction, 3),
    }


def validate_claim_records(claims: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, claim in enumerate(claims):
        missing = sorted(CLAIM_FIELDS - claim.keys())
        if missing:
            errors.append(f"claim[{index}] missing: {', '.join(missing)}")
        state = claim.get("verification_state")
        if state not in CLAIM_STATES:
            errors.append(f"claim[{index}] invalid verification_state: {state}")
        has_provenance = bool(claim.get("source_id") or claim.get("frame_id") or claim.get("supporting_sources"))
        if not has_provenance:
            errors.append(f"claim[{index}] missing provenance")
        if state in {"SOURCE_CONFIRMED", "VISUAL_CONFIRMED", "MULTI_SOURCE_CONFIRMED"} and not has_provenance:
            errors.append(f"claim[{index}] confirmed without provenance")
        if state == "EXTERNAL_VERIFIED" and not claim.get("external_sources"):
            errors.append(f"claim[{index}] EXTERNAL_VERIFIED without external_sources")
    return errors


def assess_content_quality(items: list[dict[str, Any]], *, max_low_confidence_ratio: float = 0.1) -> dict[str, Any]:
    """Reject timestamp filler and documents dominated by unsupported low-confidence content."""
    total = len(items)
    low_confidence = sum(
        str(item.get("confidence", "")).lower() in {"low", "very_low"}
        or item.get("evidence_source") in {None, "none"}
        for item in items
    )
    filler = sum(bool(re.match(r"^\s*step\s+at\s+\d{1,2}:\d{2}(?::\d{2})?\s*$", str(item.get("title") or item.get("instruction") or ""), re.I)) for item in items)
    ratio = low_confidence / total if total else 0.0
    passed = ratio <= max_low_confidence_ratio and filler == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "item_count": total,
        "low_confidence_count": low_confidence,
        "low_confidence_content_ratio": round(ratio, 4),
        "timestamp_filler_count": filler,
        "max_low_confidence_ratio": max_low_confidence_ratio,
    }


def evaluate_quality_gates(
    evaluations: dict[str, dict[str, Any]], coverage: dict[str, Any]
) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}
    for gate in QUALITY_GATES:
        value = evaluations.get(gate)
        if not isinstance(value, dict) or value.get("status") not in QUALITY_STATES - {"NOT_EVALUATED"}:
            results[gate] = {"status": "NOT_EVALUATED", "evidence": "No gate result supplied."}
        else:
            results[gate] = {"status": value["status"], "evidence": str(value.get("evidence", ""))}
    if coverage.get("status") == "SOURCE_INCOMPLETE":
        results["SOURCE_COVERAGE"] = {
            "status": "FAIL",
            "evidence": f"Transcript ends at {coverage.get('transcript_last_timestamp_seconds')}s; "
            f"trailing gap is {coverage.get('trailing_gap_seconds')}s.",
        }
    all_pass = all(item["status"] == "PASS" for item in results.values())
    return {
        "status": "PASS" if all_pass else "FAIL",
        "fully_grounded": all_pass,
        "gates": results,
    }


def merge_application_facts(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deduplicate repeated fact text while preserving session provenance and conflicts."""
    merged = [dict(item) for item in existing]
    by_key = {_fact_key(item): item for item in merged}
    for source in incoming:
        item = dict(source)
        key = _fact_key(item)
        application_id = item.get("application_id")
        fact_key = re.sub(r"\s+", " ", str(item.get("fact_key") or "").strip().lower())
        prior = next((
            current for current in merged
            if application_id and current.get("application_id") == application_id
            and fact_key and re.sub(r"\s+", " ", str(current.get("fact_key") or "").strip().lower()) == fact_key
            and _normalized_fact(current) != _normalized_fact(item)
        ), None)
        if prior is not None:
            item["status"] = "CONFLICTING"
            prior["status"] = "CONFLICTING"
            prior.setdefault("conflicts", []).append(item.get("fact") or item.get("claim"))
            item.setdefault("conflicts", []).append(prior.get("fact") or prior.get("claim"))
        current = by_key.get(key)
        if current is None:
            item["supporting_sessions"] = list(dict.fromkeys(item.get("supporting_sessions", [])))
            item["supporting_frames"] = list(dict.fromkeys(item.get("supporting_frames", [])))
            item["conflicts"] = list(item.get("conflicts", []))
            merged.append(item)
            by_key[key] = item
            continue
        current["supporting_sessions"] = list(dict.fromkeys(
            [*current.get("supporting_sessions", []), *item.get("supporting_sessions", [])]
        ))
        current["supporting_frames"] = list(dict.fromkeys(
            [*current.get("supporting_frames", []), *item.get("supporting_frames", [])]
        ))
        current["supporting_claims"] = list(dict.fromkeys(
            [*current.get("supporting_claims", []), *item.get("supporting_claims", [])]
        ))
        if item.get("last_confirmed"):
            current["last_confirmed"] = item["last_confirmed"]
        for ref in item.get("evidence_refs", []):
            if ref not in current.setdefault("evidence_refs", []):
                current["evidence_refs"].append(ref)
        for other in item.get("conflicts", []):
            if other not in current.setdefault("conflicts", []):
                current["conflicts"].append(other)
        if item.get("verification_state") == "CONFLICTING":
            current["verification_state"] = "CONFLICTING"
            current["status"] = "CONFLICTING"
        if current.get("status") not in {"CONFLICTING", "SUPERSEDED"}:
            current["status"] = "CONFIRMED" if len(current["supporting_sessions"]) > 1 else current.get("status", "NEEDS_REVIEW")
        if current.get("confidence") != item.get("confidence"):
            current["confidence"] = "LOW"
    return merged


def consolidate_application_claims(
    claim_sets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Consolidate grounded claims by exact app and explicit fact key; never fuzzy-merge apps."""
    facts: list[dict[str, Any]] = []
    for item in claim_sets:
        claim = item.get("claim")
        app_id = item.get("application_id")
        source_id = item.get("source_id")
        session_id = item.get("session_id") or item.get("first_seen", {}).get("session_id")
        if (not isinstance(claim, str) or not claim.strip()
                or not isinstance(app_id, str) or not app_id.strip()
                or not isinstance(source_id, str) or not source_id.strip()
                or not isinstance(session_id, str) or not session_id.strip()):
            continue
        if app_id == "SESSION_GENERAL":
            continue
        key = str(item.get("fact_key") or re.sub(r"\W+", " ", claim.lower())).strip().lower()
        if not key:
            continue
        stamp = item.get("timestamp")
        fact = {
            "application_id": app_id,
            "fact_key": key,
            "canonical_fact": claim,
            "fact": claim,
            "supporting_sessions": [session_id],
            "supporting_claims": [item.get("claim_id")] if item.get("claim_id") else [],
            "supporting_frames": [item["frame_id"]] if item.get("frame_id") else [],
            "evidence_refs": [{"session_id": session_id, "source_id": source_id,
                               "timestamp": stamp, "frame_id": item.get("frame_id")}],
            "first_seen": item.get("first_seen") or {"session_id": session_id, "timestamp": stamp},
            "last_confirmed": item.get("last_confirmed") or {"session_id": session_id, "timestamp": stamp},
            "confidence": item.get("confidence", 0),
            "status": "NEEDS_REVIEW" if item.get("verification_state") in {"SOURCE_UNCERTAIN", "NEEDS_REVIEW", "CONFLICTING"} else "CONFIRMED",
            "verification_state": item.get("verification_state", "NEEDS_REVIEW"),
            "conflicts": list(item.get("conflicts", [])),
            "merge_relation": item.get("merge_relation"),
        }
        facts = merge_application_facts(facts, [fact])
    for fact in facts:
        fact["canonical_fact"] = fact["fact"]
        if fact.get("status") not in {"CONFLICTING", "SUPERSEDED"} and len(fact.get("supporting_sessions", [])) > 1:
            fact["status"] = "CONFIRMED"
    return facts


def _fact_key(item: dict[str, Any]) -> str:
    application = str(item.get("application_id") or "SESSION_GENERAL").strip().lower()
    return f"{application}:{_normalized_fact(item)}"


def _normalized_fact(item: dict[str, Any]) -> str:
    key = str(item.get("fact") or item.get("claim") or item.get("fact_key") or "")
    return re.sub(r"\s+", " ", key.strip().lower())
