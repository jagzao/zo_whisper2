"""Quality primitives for evidence-backed application mission packs."""

from __future__ import annotations

import re
from typing import Any

CLAIM_STATES = {
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
CLAIM_FIELDS = {
    "claim",
    "application",
    "source_timestamp",
    "source_type",
    "confidence",
    "verification_state",
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
    gaps = [
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


def validate_claim_records(claims: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, claim in enumerate(claims):
        missing = sorted(CLAIM_FIELDS - claim.keys())
        if missing:
            errors.append(f"claim[{index}] missing: {', '.join(missing)}")
        state = claim.get("verification_state")
        if state not in CLAIM_STATES:
            errors.append(f"claim[{index}] invalid verification_state: {state}")
        if state == "SOURCE_CONFIRMED" and not claim.get("evidence_refs"):
            errors.append(f"claim[{index}] SOURCE_CONFIRMED without evidence_refs")
        if state == "EXTERNAL_VERIFIED" and not claim.get("external_sources"):
            errors.append(f"claim[{index}] EXTERNAL_VERIFIED without external_sources")
    return errors


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
        current = by_key.get(key)
        if current is None:
            item["supporting_sessions"] = list(dict.fromkeys(item.get("supporting_sessions", [])))
            item["conflicts"] = list(item.get("conflicts", []))
            merged.append(item)
            by_key[key] = item
            continue
        current["supporting_sessions"] = list(dict.fromkeys(
            [*current.get("supporting_sessions", []), *item.get("supporting_sessions", [])]
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
        if current.get("confidence") != item.get("confidence"):
            current["confidence"] = "LOW"
    return merged


def _fact_key(item: dict[str, Any]) -> str:
    key = str(item.get("fact") or item.get("claim") or item.get("fact_key") or "")
    return re.sub(r"\s+", " ", key.strip().lower())
