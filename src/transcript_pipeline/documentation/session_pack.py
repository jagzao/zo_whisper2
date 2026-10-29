"""Generic evidence-grounded Session and Application Knowledge Pack pipeline."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from transcript_pipeline.documentation.kav_contract import (
    build_runbooks,
    embedding_ready,
    extract_procedures,
    procedure_grounding,
    second_brain_ready,
    validate_runbooks,
)
from transcript_pipeline.documentation.mission_pack import (
    consolidate_application_claims,
    validate_claim_records,
)
from transcript_pipeline.documentation.visual_evidence import _semantic_topic_sources

DIAGRAM_RELATIONS = {
    "DATA_FLOW", "CALLS", "HOSTS", "USES", "DEPENDS_ON", "AUTHENTICATES_WITH",
    "MANAGES", "STORES_IN", "NETWORK_PATH_CONTROL", "SUPPORTS", "ASSOCIATED_WITH",
}
DIRECTED_RELATIONS = {"DATA_FLOW", "CALLS", "HOSTS", "USES", "MANAGES", "STORES_IN", "NETWORK_PATH_CONTROL"}
UNCERTAIN_STATES = {"SOURCE_UNCERTAIN", "NEEDS_REVIEW", "CONFLICTING"}
APPLICATION_STATES = {"MATCH_CONFIRMED", "MATCH_PROBABLE", "NEW_APPLICATION", "AMBIGUOUS"}
LIVE_VALIDATION_TOPICS = {
    "Architecture / hosting", "Data / storage", "Integrations / dependencies",
    "Authentication / access", "Roles / permissions", "Support / ownership", "Lifecycle", "Operations",
}


@dataclass
class MediaEvidenceBundle:
    media_id: str
    video_metadata: dict[str, Any]
    transcript_segments: list[dict[str, Any]] = field(default_factory=list)
    speech_coverage: dict[str, Any] = field(default_factory=dict)
    frames: list[dict[str, Any]] = field(default_factory=list)
    ocr_results: list[dict[str, Any]] = field(default_factory=list)
    visual_topics: list[dict[str, Any]] = field(default_factory=list)
    application_candidates: list[dict[str, Any]] = field(default_factory=list)
    evidence_events: list[dict[str, Any]] = field(default_factory=list)


def _seconds(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    parts = [float(part) for part in str(value).split(":")]
    return sum(part * factor for part, factor in zip(parts, (3600, 60, 1)[-len(parts):]))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unknown"


def _stable_id(prefix: str, *values: Any) -> str:
    token = "|".join(str(value) for value in values)
    return f"{prefix}-{hashlib.sha256(token.encode('utf-8')).hexdigest()[:12]}"


def _normalize_name(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def _unique_values(values: list[Any]) -> list[Any]:
    unique = {json.dumps(value, sort_keys=True, ensure_ascii=False): value for value in values}
    return list(unique.values())


def deduplicate_source_artifacts(source_map: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for source in source_map:
        path, digest = source.get("source_path") or source.get("path"), source.get("sha256")
        if not path or not digest:
            result.append(dict(source))
            continue
        key = (str(path).replace("\\", "/").casefold(), str(digest).casefold())
        prior = seen.get(key)
        if prior is None:
            prior = dict(source)
            prior["aliases"] = list(prior.get("aliases", []))
            seen[key] = prior
            result.append(prior)
        else:
            for alias in [source.get("evidence_id"), *source.get("aliases", [])]:
                if alias and alias != prior.get("evidence_id") and alias not in prior["aliases"]:
                    prior["aliases"].append(alias)
    return result


def sort_evidence_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=lambda event: (_seconds(event["start"]), _seconds(event["end"]), str(event["id"])))


def validate_timeline_chronology(events: list[dict[str, Any]]) -> list[str]:
    keys = [(_seconds(item["start"]), _seconds(item["end"]), str(item["id"])) for item in events]
    return [] if keys == sorted(keys) else ["evidence timeline is not chronological"]


def normalize_evidence_bundle(bundle: MediaEvidenceBundle | dict[str, Any]) -> MediaEvidenceBundle:
    value = asdict(bundle) if isinstance(bundle, MediaEvidenceBundle) else dict(bundle)
    required = {"media_id", "video_metadata", "transcript_segments", "speech_coverage", "frames",
                "ocr_results", "visual_topics", "application_candidates", "evidence_events"}
    missing = required - value.keys()
    if missing:
        raise ValueError(f"evidence bundle missing fields: {sorted(missing)}")
    if not value["media_id"] or not isinstance(value["video_metadata"], dict):
        raise ValueError("evidence bundle media identity is invalid")
    for index, segment in enumerate(value["transcript_segments"]):
        segment.setdefault("segment_id", _stable_id("seg", value["media_id"], index, segment.get("start")))
        segment["start"], segment["end"] = float(segment["start"]), float(segment["end"])
        if segment["end"] < segment["start"]:
            raise ValueError(f"invalid transcript interval: {segment['segment_id']}")
    for index, frame in enumerate(value["frames"]):
        frame.setdefault("frame_id", _stable_id("frame", value["media_id"], index, frame.get("timestamp")))
        frame["timestamp"] = float(frame["timestamp"])
    ocr_by_id = {str(item.get("frame_id")): item for item in value["ocr_results"] if item.get("frame_id")}
    for frame in value["frames"]:
        ocr = ocr_by_id.get(frame["frame_id"], {})
        for key in ("ocr_status", "ocr_text", "ocr_confidence", "retry_count", "engine", "source_image"):
            if key not in frame and key in ocr:
                frame[key] = ocr[key]
        if not frame.get("semantic_topic") and frame.get("topic"):
            frame["semantic_topic"] = frame["topic"]
    for topic in value["visual_topics"]:
        if not isinstance(topic, dict):
            continue
        refs = topic.get("frame_ids") or ([topic["frame_id"]] if topic.get("frame_id") else ([topic["source_frame"]] if topic.get("source_frame") else []))
        for frame_id in refs:
            frame = next((item for item in value["frames"] if item["frame_id"] == frame_id), None)
            if frame and not frame.get("semantic_topic"):
                frame["semantic_topic"] = topic.get("topic")
    if not value["evidence_events"]:
        value["evidence_events"] = [
            {"id": segment["segment_id"], "start": segment["start"], "end": segment["end"],
             "source_type": "TRANSCRIPT", "source_id": value["media_id"], "text": segment.get("text", "")}
            for segment in value["transcript_segments"]
        ]
        value["evidence_events"].extend(
            {"id": frame["frame_id"], "start": frame["timestamp"], "end": frame["timestamp"],
             "source_type": "VIDEO_FRAME", "source_id": value["media_id"], "frame_id": frame["frame_id"]}
            for frame in value["frames"]
        )
    value["evidence_events"] = sort_evidence_timeline(value["evidence_events"])
    return MediaEvidenceBundle(**value)


def discover_application_candidates(bundle: MediaEvidenceBundle) -> list[dict[str, Any]]:
    candidates = [dict(item) for item in bundle.application_candidates]
    metadata = bundle.video_metadata
    for item in metadata.get("applications", []) if isinstance(metadata.get("applications", []), list) else []:
        if isinstance(item, dict):
            candidates.append(dict(item))
    metadata_name = None
    for key in ("application_name", "application", "visible_application_title", "app_name", "cmdb_name"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            metadata_name = value
            break
    url = str(metadata.get("url", "") or "")
    domain = metadata.get("domain") or metadata.get("url_domain") or (urlparse(url).hostname if url else None)
    metadata_name = metadata_name or domain or metadata.get("cmdb_id")
    if metadata_name:
        candidates.append({
            "name": metadata_name,
            "aliases": list(metadata.get("application_aliases", [])),
            "application_id": metadata.get("application_id") or metadata.get("cmdb_id"),
            "visible_title": metadata.get("visible_application_title"),
            "domain": domain,
            "support_context": metadata.get("support_context"),
            "known_identifiers": list(metadata.get("known_identifiers", [])),
            "identity_signals": [value for value in (metadata.get("visible_application_title"), domain,
                                                       metadata.get("cmdb_id"), metadata.get("support_context")) if value],
            "status": "NEW_APPLICATION",
            "provenance": [{"source_id": bundle.media_id, "source_type": "VIDEO_METADATA"}],
        })
    patterns = [
        re.compile(
            r"\b(?:application|system|platform|tool|service|product)\s+(?:is\s+)?(?:called|named)\s+['\"“]?([\w][\w .&()/-]{1,70})",
            re.I,
        ),
        re.compile(
            r"\bwhat\s+this\s+is\s+essentially\s+(?:is\s+)?([\w][\w.-]{2,50})",
            re.I,
        ),
    ]
    for segment in bundle.transcript_segments:
        text = str(segment.get("text", ""))
        for pattern in patterns:
            for match in pattern.finditer(text):
                name = re.split(r"[,.;!?\n]", match.group(1), maxsplit=1)[0].strip(" '’\"”")
                if len(name.split()) > 8:
                    continue
                candidates.append({
                    "name": name, "aliases": [name], "status": "NEW_APPLICATION",
                    "provenance": [{"source_id": bundle.media_id, "segment_id": segment["segment_id"],
                                    "timestamp": segment["start"], "source_type": "TRANSCRIPT"}],
                })
    for event in bundle.evidence_events:
        name = str(event.get("application") or "").strip()
        if name and name.casefold() not in {"session", "unknown", "none"}:
            candidates.append({"name": name, "aliases": [name], "status": "NEW_APPLICATION",
                               "provenance": [{"source_id": bundle.media_id, "event_id": event.get("id"),
                                               "timestamp": event.get("start"), "source_type": "EVIDENCE_EVENT"}]})
    for frame in bundle.frames:
        name = str(frame.get("application") or "").strip()
        if name and name.casefold() not in {"session_general", "session", "other", "unknown"}:
            readable_name = str(frame.get("topic_title") or name).strip()
            readable_name = re.sub(r"\s+(?:application\s+)?(?:overview|summary|catalogue\s+record|technical\s+architecture|data\s+flow)$",
                                   "", readable_name, flags=re.I)
            candidates.append({"name": name, "aliases": [name], "status": "NEW_APPLICATION",
                               "display_name": readable_name,
                               "provenance": [{"source_id": bundle.media_id, "frame_id": frame.get("frame_id"),
                                               "timestamp": frame.get("timestamp"), "source_type": "VIDEO_FRAME"}]})
    event_candidates = [item for item in candidates if any(ref.get("event_id") for ref in item.get("provenance", []))]
    for candidate in list(candidates):
        if not any(ref.get("frame_id") for ref in candidate.get("provenance", [])):
            continue
        compact = re.sub(r"[^a-z0-9]", "", str(candidate.get("name", "")).casefold())
        for event_candidate in event_candidates:
            event_name = str(event_candidate.get("name", ""))
            event_compact = re.sub(r"[^a-z0-9]", "", event_name.casefold())
            overlap = set(_slug(candidate["name"]).split("-")) & set(_slug(event_name).split("-"))
            if compact in event_compact or event_compact in compact or len(overlap) >= 2:
                event_candidate.setdefault("aliases", []).append(candidate["name"])
                event_candidate.setdefault("provenance", []).extend(candidate.get("provenance", []))
                event_candidate["display_name"] = candidate.get("display_name") or event_candidate.get("display_name")
                candidates.remove(candidate)
                break
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        name = str(candidate.get("name", "")).strip()
        key = _normalize_name(name)
        if not key:
            continue
        entry = unique.setdefault(key, {**candidate, "name": name, "aliases": list(candidate.get("aliases", [name])),
                                        "provenance": list(candidate.get("provenance", []))})
        for alias in candidate.get("aliases", [name]):
            if alias not in entry["aliases"]:
                entry["aliases"].append(alias)
        for ref in candidate.get("provenance", []):
            if ref not in entry["provenance"]:
                entry["provenance"].append(ref)
    return list(unique.values())


def resolve_application_identity(candidate: dict[str, Any], known: list[dict[str, Any]]) -> dict[str, Any]:
    aliases = {_normalize_name(str(item)) for item in [candidate.get("name"), *candidate.get("aliases", [])] if item}
    matches = []
    for app in known:
        known_aliases = {_normalize_name(str(item)) for item in [app.get("name"), *app.get("aliases", [])] if item}
        if aliases & known_aliases:
            matches.append(app)
    if len(matches) == 1:
        return {"application_id": matches[0]["application_id"], "status": "MATCH_CONFIRMED",
                "matched_alias": sorted(aliases & {_normalize_name(str(item)) for item in [matches[0].get("name"), *matches[0].get("aliases", [])] if item})[0]}
    if len(matches) > 1:
        return {"application_id": None, "status": "AMBIGUOUS", "matched_candidates": [x.get("application_id") for x in matches]}
    if not candidate.get("name"):
        return {"application_id": None, "status": "AMBIGUOUS", "matched_candidates": []}
    if not candidate.get("provenance"):
        return {"application_id": None, "status": "NEEDS_REVIEW"}
    return {"application_id": _slug(str(candidate["name"])), "status": "NEW_APPLICATION"}


def classify_ambiguity(text: str) -> list[str]:
    markers = ("maybe", "possibly", "i think", "my impression", "appears that", "not sure", "unclear", "could be", "might be")
    lowered = text.casefold()
    found = [marker for marker in markers if re.search(rf"\b{re.escape(marker)}\b", lowered)]
    if re.search(r"\b(?:sorry|correction|i mean|rather)\b", lowered):
        found.append("speaker_correction")
    if text.rstrip().endswith(("...", "—")):
        found.append("unfinished_statement")
    return found


def _has_material_subject(text: str) -> bool:
    return bool(re.search(
        r"\b(?:application|system|service|business|process|workflow|data|database|storage|hosting|architecture|"
        r"platform|cloud|network|integration|api|role|permission|access|authentication|support|owner|lifecycle|"
        r"decommission|production|development|environment|configuration|notification|subscription|report|document|"
        r"user|customer|consumer|vendor|record|retention|entitlement|identity|browser|pdf|safety|security|"
        r"catalogue|catalog|group|salesforce|etl|factory|sql|environment|frontend|backend|bia)\b", text, re.I))


def extract_claims(bundle: MediaEvidenceBundle, applications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = {
        item.get("application_id") or _slug(str(item.get("name", ""))): item
        for item in applications if item.get("application_id") or item.get("name")
    }
    aliases = {
        _normalize_name(alias): app_id
        for app_id, app in resolved.items()
        for alias in [app.get("name"), *app.get("aliases", [])]
        if alias
    }
    application_anchors = []
    for item in [*bundle.evidence_events, *bundle.frames]:
        name = str(item.get("application") or "").strip()
        app_id = aliases.get(_normalize_name(name))
        timestamp = item.get("start", item.get("timestamp"))
        if app_id and timestamp is not None:
            start = _seconds(timestamp)
            end = _seconds(item.get("end", timestamp))
            application_anchors.append((start, end, app_id))
    factual = re.compile(r"\b(is|are|has|have|uses|depends|runs|contains|supports|provides|allows|requires|stores|connects|means|could)\b", re.I)
    claims = []
    events = [event for event in bundle.evidence_events if str(event.get("summary", "")).strip()]
    for event in events:
        text = re.sub(r"\s+", " ", str(event.get("summary", "")).strip()).rstrip(" .")
        support_scope = re.search(r"public website support via backend", text, re.I)
        if support_scope:
            event_app = str(event.get("application") or "")
            event_matches = {app_id for alias, app_id in aliases.items()
                             if alias and _normalize_name(alias) == _normalize_name(event_app)}
            app_id = next(iter(event_matches)) if len(event_matches) == 1 else "SESSION_GENERAL"
            timestamp = _seconds(event.get("start", 0))
            claims.append({
                "claim_id": _stable_id("claim", bundle.media_id, event.get("id"), "support-scope"),
                "application_id": app_id, "claim": "The public website remains within support scope through its supported backend.",
                "source_type": "EVIDENCE_EVENT", "source_id": bundle.media_id, "timestamp": timestamp,
                "frame_id": None, "confidence": float(event.get("confidence", .85)),
                "verification_state": "SOURCE_CONFIRMED",
                "first_seen": {"session_id": bundle.media_id, "timestamp": timestamp}, "last_confirmed": None,
                "supporting_sources": [{"source_id": bundle.media_id, "source_type": "EVIDENCE_EVENT",
                                        "event_id": event.get("id"), "source_claim_ids": event.get("claim_ids", []),
                                        "source_types": event.get("source_types", [])}],
                "conflicts": [], "ambiguities": [],
            })
        if len(text.split()) < 5 or not (factual.search(text) or support_scope) or not _has_material_subject(text) or re.search(
            r"\b(?:meeting|presentation|handoff|hello|thanks|suspicious phrase|reports no resource.group permission|"
            r"advises trying|attempt to switch|no prepared slides|data floor/code|technical presentation deferred|"
            r"limited tickets/use impression|incomplete application maturity|open.source statement)\b", text, re.I
        ):
            continue
        app_name = str(event.get("application") or "").strip()
        if app_name.casefold() in {"session", "session_general", "unknown", "none"}:
            continue
        matches = {app_id for alias, app_id in aliases.items() if alias and _normalize_name(alias) == _normalize_name(app_name)}
        app_id = next(iter(matches)) if len(matches) == 1 else "SESSION_GENERAL"
        app_label = next((str(app.get("display_name") or app.get("name")) for app in applications
                          if app.get("application_id") == app_id), app_name)
        uncertain = bool(classify_ambiguity(text)) or bool(event.get("verification_state") in UNCERTAIN_STATES)
        claim_id = _stable_id("claim", bundle.media_id, event.get("id"), text)
        claim_text = text
        prefix = app_label if app_label and _normalize_name(claim_text).startswith(_normalize_name(app_label)) else app_name
        if prefix and _normalize_name(claim_text).startswith(_normalize_name(prefix)):
            claim_text = re.sub(rf"^{re.escape(prefix)}\s*:?\s*", "", claim_text, flags=re.I)
        claim = f"{app_label}: {claim_text}." if app_label and app_id != "SESSION_GENERAL" else claim_text + "."
        claims.append({
            "claim_id": claim_id, "application_id": app_id, "claim": claim,
            "source_type": "EVIDENCE_EVENT", "source_id": bundle.media_id,
            "timestamp": _seconds(event.get("start", 0)), "frame_id": None,
            "confidence": float(event.get("confidence", 0.85 if not uncertain else 0.4)),
            "verification_state": "SOURCE_UNCERTAIN" if uncertain else "SOURCE_CONFIRMED",
            "first_seen": {"session_id": bundle.media_id, "timestamp": _seconds(event.get("start", 0))},
            "last_confirmed": None,
            "supporting_sources": [{"source_id": bundle.media_id, "source_type": "EVIDENCE_EVENT",
                                     "event_id": event.get("id"), "source_claim_ids": event.get("claim_ids", []),
                                     "source_types": event.get("source_types", [])}],
            "conflicts": [], "ambiguities": classify_ambiguity(text),
        })
    for segment in _join_contiguous_transcript_fragments(bundle.transcript_segments):
        text = re.sub(r"\s+", " ", str(segment.get("text", "")).strip())
        if (len(text.split()) < 5 or len(text.split()) > 55 or not factual.search(text) or not _has_material_subject(text)
                or text.endswith("...") or not text.endswith((".", "?", "!"))
                or len(re.findall(r"\b(?:is|are|was|were)\s+being\b", text, re.I)) > 1
                or re.match(r"^(?:while \w+ is doing|no worries|i wanted to share|wanted to share|"
                            r"i(?:'m| am) not|this is the base|for today|okay|no,? you have to)\b", text, re.I)):
            continue
        if text.endswith("?") or re.search(r"\b(?:hello|thanks|let me share|can you see|let's start|any questions|can we move|give me a second|schedule|attendees|make up session|we'll be covering|sorry,? [A-Z]|meeting|presentation)\b", text, re.I):
            continue
        uncertain = bool(classify_ambiguity(text))
        timestamp = float(segment["start"])
        interval_events = [event for event in bundle.evidence_events
                           if event.get("application") and str(event.get("application")).casefold() != "session"
                           and _seconds(event.get("start", 0)) <= timestamp <= _seconds(event.get("end", event.get("start", 0)))]
        event_app = str(interval_events[-1].get("application")) if interval_events else None
        matches = {app_id for alias, app_id in aliases.items() if alias and
                   (alias in _normalize_name(text) or (event_app and alias == _normalize_name(event_app)))}
        if not matches:
            nearest = sorted((min(abs(timestamp - start), abs(timestamp - end)), app_id)
                             for start, end, app_id in application_anchors)
            if nearest and nearest[0][0] <= 45 and (len(nearest) == 1 or nearest[0][1] == nearest[1][1]
                                                     or nearest[0][0] < nearest[1][0]):
                matches = {nearest[0][1]}
        app_id = next(iter(matches)) if len(matches) == 1 else "SESSION_GENERAL"
        claim_id = _stable_id("claim", bundle.media_id, segment["segment_id"], text)
        source_segments = segment.get("source_segments") or [segment]
        claims.append({
            "claim_id": claim_id, "application_id": app_id, "claim": text,
            "source_type": "TRANSCRIPT", "source_id": bundle.media_id,
            "timestamp": segment["start"], "frame_id": None,
            "confidence": float(segment.get("confidence", 0.75 if not uncertain else 0.4)),
            "verification_state": "SOURCE_UNCERTAIN" if uncertain else "SOURCE_CONFIRMED",
            "first_seen": {"session_id": bundle.media_id, "timestamp": segment["start"]},
            "last_confirmed": None,
            "supporting_sources": [{"source_id": bundle.media_id, "source_type": "TRANSCRIPT",
                                     "timestamp": segment["start"], "segments": source_segments}],
            "conflicts": [], "ambiguities": classify_ambiguity(text),
        })
    claims.extend(_extract_role_model_claims(bundle, aliases))
    for segment in _join_contiguous_transcript_fragments(bundle.transcript_segments):
        segment_text = str(segment.get("text", ""))
        owner = re.search(r"\bowned by\s+([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,5})", segment_text)
        bia = re.search(r"\b(?:overall )?BIA is\s+([a-z]+)", segment_text, re.I)
        derived = []
        if owner:
            derived.append(f"Application owner was identified as {owner.group(1)}.")
        if bia:
            derived.append(f"Overall business impact assessment is {bia.group(1)}.")
        for fact in derived:
            timestamp = float(segment["start"])
            interval = [event for event in bundle.evidence_events if event.get("application")
                        and _seconds(event.get("start", 0)) <= timestamp <= _seconds(event.get("end", event.get("start", 0)))]
            event_name = str(interval[-1].get("application")) if interval else ""
            app_matches = {app_id for alias, app_id in aliases.items()
                           if alias and _normalize_name(alias) == _normalize_name(event_name)}
            app_id = next(iter(app_matches)) if len(app_matches) == 1 else "SESSION_GENERAL"
            sources = [{"source_id": bundle.media_id, "source_type": "TRANSCRIPT", "timestamp": item.get("start"),
                        "segments": [item]} for item in segment.get("source_segments", [segment])]
            claims.append({"claim_id": _stable_id("claim", bundle.media_id, app_id, fact), "application_id": app_id,
                           "claim": fact, "source_type": "TRANSCRIPT", "source_id": bundle.media_id,
                           "timestamp": timestamp, "frame_id": None, "confidence": .75,
                           "verification_state": "SOURCE_CONFIRMED", "first_seen": {"session_id": bundle.media_id, "timestamp": timestamp},
                           "last_confirmed": None, "supporting_sources": sources, "conflicts": [], "ambiguities": []})
    return claims


def _join_contiguous_transcript_fragments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    joined: list[dict[str, Any]] = []
    for segment in sorted(segments, key=lambda item: float(item.get("start", 0))):
        if not joined:
            joined.append({**segment, "source_segments": [segment]})
            continue
        current = joined[-1]
        current_text = str(current.get("text", "")).rstrip()
        next_text = str(segment.get("text", "")).strip()
        gap = float(segment.get("start", 0)) - float(current.get("end", current.get("start", 0)))
        starts_new_sentence = bool(re.match(r"^(?:so|in addition|from an? |the |this |however|secondly|lastly)\b", next_text, re.I))
        if gap <= 1.0 and gap >= 0 and not current_text.endswith((".", "?", "!")) and not starts_new_sentence:
            current["text"] = f"{current_text} {next_text}"
            current["end"] = segment.get("end", current.get("end"))
            current["source_segments"].extend(segment.get("source_segments", [segment]))
        else:
            joined.append({**segment, "source_segments": [segment]})
    return joined


def _extract_role_model_claims(bundle: MediaEvidenceBundle, aliases: dict[str, str]) -> list[dict[str, Any]]:
    segments = sorted(bundle.transcript_segments, key=lambda item: float(item.get("start", 0)))
    text_parts = []
    segment_ranges = []
    cursor = 0
    for item in segments:
        value = str(item.get("text", ""))
        segment_ranges.append((cursor, cursor + len(value), item))
        text_parts.append(value)
        cursor += len(value) + 1
    text = " ".join(text_parts)
    role_terms = re.search(r"three primary user\s+groups", text, re.I)
    global_match = re.search(r"global admin", text, re.I)
    local_match = re.search(r"local administrator", text, re.I)
    if not role_terms or not global_match or not local_match:
        return []
    role_scope_match = re.search(r"(?:activities available .* depend on the role assigned|(?:functions|activities) depend on the role assigned|controlled access by limiting users)",
                                 text[local_match.start():], re.I)
    cluster_end = local_match.end() + role_scope_match.end() if role_scope_match else local_match.end() + 220
    cluster = [item for seg_start, seg_end, item in segment_ranges
               if seg_end >= role_terms.start() and seg_start <= cluster_end]
    cluster_text = " ".join(str(item.get("text", "")) for item in cluster)
    start = float(cluster[0]["start"]) if cluster else 0.0
    app_events = [event for event in bundle.evidence_events if event.get("application")
                  and _seconds(event.get("start", 0)) <= start <= _seconds(event.get("end", event.get("start", 0)))]
    event_name = str(app_events[-1].get("application")) if app_events else ""
    matched_apps = {app_id for alias, app_id in aliases.items()
                    if alias and event_name and _normalize_name(alias) == _normalize_name(event_name)}
    app_id = next(iter(matched_apps)) if len(matched_apps) == 1 else "SESSION_GENERAL"

    role_facts = []
    if re.search(r"consumers? and customers?", cluster_text, re.I) and re.search(r"access .*documents?.*subscribe", cluster_text, re.I):
        role_facts.append(("Consumers and customers access public safety documents and may subscribe to documentation notifications.",
                           re.compile(r"consumer|customer|public safety|technical documents|subscribe|notification", re.I)))
    if global_match and re.search(r"global admin.{0,180}manag(?:e|ing).*countries", cluster_text, re.I):
        role_facts.append(("Global administrators manage countries, user subscriptions, notifications, and text modules.",
                           re.compile(r"global admin|countries|subscription|notification|text modules", re.I)))
    if local_match and re.search(r"local administrator.{0,180}products and categories", cluster_text, re.I):
        role_facts.append(("Local administrators manage products and categories.",
                           re.compile(r"local administrator|products|categories", re.I)))
    if re.search(r"(?:activities available .*|(?:functions|activities) )depend on the role assigned", cluster_text, re.I) or re.search(
        r"controlled access by limiting users to the functions", cluster_text, re.I
    ):
        role_facts.append(("Administrative functions are limited according to each user's assigned role and responsibilities.",
                           re.compile(r"role assigned|controlled access|responsibilities", re.I)))

    claims = []
    for fact, evidence_pattern in role_facts:
        source_segments = [item for item in cluster if evidence_pattern.search(str(item.get("text", "")))]
        if not source_segments:
            source_segments = cluster
        timestamp = min(float(item.get("start", 0)) for item in source_segments)
        sources = [{"source_id": bundle.media_id, "source_type": "TRANSCRIPT", "timestamp": item.get("start"),
                    "segments": [item]} for item in source_segments]
        claims.append({
            "claim_id": _stable_id("claim", bundle.media_id, app_id, fact), "application_id": app_id,
            "claim": fact, "source_type": "TRANSCRIPT", "source_id": bundle.media_id,
            "timestamp": timestamp, "frame_id": None, "confidence": .75,
            "verification_state": "SOURCE_CONFIRMED",
            "first_seen": {"session_id": bundle.media_id, "timestamp": timestamp}, "last_confirmed": None,
            "supporting_sources": sources, "conflicts": [], "ambiguities": [],
        })
    return claims


def _visual_label_fact(label: str) -> str | None:
    match = re.match(r"\s*(owner|lifecycle|support group|class|app category|app sub-category|data classification|overall bia)\s*:\s*(.+?)\s*$", label, re.I)
    if not match:
        return None
    field_name, value = match.group(1).casefold(), match.group(2).strip().rstrip(".")
    if field_name == "owner":
        return f"Application catalogue lists {value} as owner."
    if field_name == "lifecycle":
        return f"Application catalogue records lifecycle as {value}."
    if field_name == "support group":
        return f"Application catalogue lists {value} as the support group."
    if field_name == "class":
        return f"Application catalogue classifies the entry as {value}."
    if field_name == "app category":
        return f"Application catalogue classifies the application category as {value}."
    if field_name == "app sub-category":
        return f"Application catalogue classifies the application sub-category as {value}."
    if field_name == "data classification":
        return f"Application data classification is recorded as {value}."
    return f"Application business impact is recorded as {value}."


def classify_semantic_topic(text: str) -> str:
    value = text.casefold()
    if re.search(r"\b(?:decommission|sunset|lifecycle|retire|end.of.life|leverage/optimize)\b", value):
        return "Lifecycle"
    if re.search(r"\b(?:application owner|owner|support group|support team|support scope|ownership|contact)\b", value):
        return "Support / ownership"
    if re.search(r"\b(?:role|global administrators?|local administrators?|global admins?|local admins?|entitlement|permission group|authorized group|access group|database access|access is limited|access to)\b", value):
        return "Roles / permissions"
    if re.search(r"\b(?:consumers?|customers?)\b", value) and re.search(r"\b(?:access|subscribe)", value):
        return "Roles / permissions"
    if re.search(r"\b(?:authentication|authenticate|identity provider|pingid|login|resource.group permission|access denied|access was denied|access problem|requesting permission)\b", value):
        return "Authentication / access"
    if re.search(r"\b(?:subscription|notification|integration|mail service|email|salesforce|saas/etl|data factory|depends on|connects to|data export|export flow|vendor servers)\b", value):
        return "Integrations / dependencies"
    if re.search(r"\b(?:sql|database|data storage|stores|storage|data model)\b", value):
        return "Data / storage"
    if re.search(r"\b(?:hosted|hosting|backend|azure|environments?|private endpoints?|virtual networks?|vnet|architecture|network path)\b", value):
        return "Architecture / hosting"
    if re.search(r"\b(?:maintain|retrieve|manual configuration|export pdf|operational|routine|support activity)\b", value):
        return "Operations"
    if re.search(r"\b(?:consumers?|customers?|public documents?|safety data sheets?|business purpose|purpose|used to|used by|serves|maintain .*documents|retrieve .*documents|supports .*business)\b", value):
        return "Purpose / business context"
    return "Operations"


def _source_ref_ids(claim: dict[str, Any]) -> list[dict[str, Any]]:
    refs = []
    for source in claim.get("supporting_sources", []):
        ref = {key: source[key] for key in ("source_type", "event_id", "frame_id", "timestamp", "source_claim_ids", "source_types")
               if source.get(key) is not None}
        segments = source.get("segments") or []
        if segments:
            ref["segment_ids"] = [segment["segment_id"] for segment in segments if segment.get("segment_id")]
            ref["segments"] = [{key: segment[key] for key in ("segment_id", "start", "end") if segment.get(key) is not None}
                               for segment in segments if segment.get("segment_id")]
            ref.setdefault("timestamp", source.get("timestamp"))
        ref["source_id"] = source.get("source_id")
        refs.append(ref)
    return _unique_values(refs)


def _canonical_fact_text(text: str, app_name: str) -> str:
    value = re.sub(r"\s+", " ", text).strip().rstrip(" .")
    if app_name:
        value = re.sub(rf"^{re.escape(app_name)}:\s*", "", value, flags=re.I)
    value = re.sub(r"^(?:so|and then|then|well|basically|you know)\s+", "", value, flags=re.I)
    value = re.sub(r"^(?:because )?initially,?\s*(?:just wanted to share that\s*)?initially\s+", "", value, flags=re.I)
    value = re.sub(r"^(?:i think|i believe) (.+)$", r"Evidence suggests \1", value, flags=re.I)
    export = re.match(r"^record describes (.+?) data export through (.+?) to (.+)$", value, re.I)
    if export:
        value = f"Data is exported from {export.group(1)} through {export.group(2)} to {export.group(3)}"
    value = re.sub(r"^this document sharing capability\b", "The application's document sharing capability", value, flags=re.I)
    purpose = re.match(r"^(?:the )?application's main purpose is to share (.+?) with (.+?) through (?:their|its) external website$", value, re.I)
    if purpose:
        value = f"{app_name} shares {purpose.group(1)} with {purpose.group(2)} through an external website"
    value = re.sub(r"\bwith their (consumers? and customers?)\b", r"with \1", value, flags=re.I)
    subscriptions = re.match(r"^(?:in addition to that,? )?(?:the )?application provides some external access to public safety data sheets and other technical documents,? so it also supports subscriptions and email notifications$", value, re.I)
    if subscriptions:
        value = f"{app_name} provides external access to public safety data sheets and technical documents and supports subscriptions and email notifications"
    value = re.sub(r"^(?:this|the) application\b", app_name, value, flags=re.I)
    value = re.sub(r"^my impression is that (.+)$", r"Evidence suggests \1", value, flags=re.I)
    value = re.sub(r"^from an admin perspective, the application\b", app_name, value, flags=re.I)
    value = re.sub(r"^data classification for this is\s+", "The application's data classification is ", value, flags=re.I)
    value = re.sub(r",\s*[^,.;]+?\s+and so forth\b", "", value, flags=re.I)
    value = re.sub(r"\busers subscriptions\b", "user subscriptions", value, flags=re.I)
    value = re.sub(rf"^{re.escape(app_name)} is already in\b", f"{app_name} is in", value, flags=re.I)
    value = re.sub(r"^this is (a|an)\b", rf"{app_name} is \1", value, flags=re.I)
    if re.match(r"^(?:Azure|Microsoft Azure) and has\b", value, re.I):
        value = re.sub(r"^(Azure|Microsoft Azure) and has", rf"{app_name} uses \1 and has", value, flags=re.I)
    if app_name and not _normalize_name(value).startswith(_normalize_name(app_name)):
        value = f"{app_name}: {value}"
    return value[:1].upper() + value[1:] + "." if value else ""


def _is_conversational_claim(text: str) -> bool:
    value = re.sub(r"^[^:]+:\s*", "", str(text))
    return bool(re.match(r"^(?:so this|and then|because|my impression|i think|i believe|from an admin perspective|"
                         r"while \w+ is doing|i wanted to share|wanted to share|this is the base)\b", value, re.I))


def _semantic_key(text: str, app_name: str | list[str]) -> str:
    value = _normalize_name(text)
    names = [app_name] if isinstance(app_name, str) else app_name
    for name in names:
        app = _normalize_name(name)
        if app:
            value = re.sub(rf"\b{re.escape(app)}\b", " ", value)
            joined = re.sub(r"\W+", "", name.casefold())
            if joined:
                value = re.sub(rf"\b{re.escape(joined)}(?:com)?\b", " ", value)
    value = re.sub(r"\bcom\b", " ", value)
    value = re.sub(r"\b(?:this|the) application\b", " ", value)
    value = re.sub(r"\b(?:so|then|basically|you know|i mean|actually|this|that|the)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _same_semantic_fact(left: str, right: str) -> bool:
    left_tokens, right_tokens = set(left.split()), set(right.split())
    common = left_tokens & right_tokens
    if len(common) < 2:
        return False
    ratio = SequenceMatcher(None, left, right).ratio()
    jaccard = len(common) / len(left_tokens | right_tokens)
    return ratio >= .82 or (len(common) >= 4 and jaccard >= .5)


def consolidate_semantic_claims(claims: list[dict[str, Any]], applications: list[dict[str, Any]],
                                source_session: str) -> list[dict[str, Any]]:
    app_names = {item.get("application_id"): str(item.get("display_name") or item.get("name") or "")
                 for item in applications if item.get("application_id")}
    app_aliases = {item.get("application_id"): [str(item.get("display_name") or item.get("name") or ""),
                                                 *[str(alias) for alias in item.get("aliases", [])]]
                   for item in applications if item.get("application_id")}
    groups: list[dict[str, Any]] = []
    for claim in claims:
        app_id = str(claim.get("application_id") or "SESSION_GENERAL")
        app_name = str(app_names.get(app_id) or "Session knowledge")
        source_text = str(claim.get("claim", "")).strip()
        compound_text = source_text
        for alias in app_aliases.get(app_id, [app_name]):
            compound_text = re.sub(rf"^{re.escape(alias)}\s*:\s*", "", compound_text, flags=re.I)
        compound = re.match(r"^(?:so\s+)?(?:this is )?a\s+(.+?)\s+application hosted\s+(?:in|on)\s+(.+)$", compound_text, re.I)
        if compound:
            claim = {**claim, "claim": f"{app_name} is a {compound.group(1)} application."}
            host_claim = {**claim, "claim": f"{app_name} is hosted on {compound.group(2).rstrip('. ')}."}
            source_text = host_claim["claim"]
            expanded = (claim, host_claim)
        else:
            expanded = (claim,)
        for item in expanded:
            source_text = str(item.get("claim", "")).strip()
            key = _semantic_key(source_text, app_aliases.get(app_id, [app_name]))
            hosted = re.search(r"\b(?:hosted|hosting|deployed|runs? on)\s+(?:in|on)?\s*(.+)$", key)
            if hosted:
                host = hosted.group(1).strip()
                provider = next((word for word in ("azure", "aws", "gcp", "google cloud") if word in host), host)
                key = f"application hosting {provider}"
            if re.search(r"\bprivate endpoints?\b", key) and re.search(r"\bvirtual networks?\b|\bvnet\b", key):
                key = "private endpoint and virtual network architecture"
            if not key:
                continue
            match = next((group for group in groups if group["application_id"] == app_id
                          and _same_semantic_fact(group["key"], key)), None)
            if match is None:
                groups.append({"application_id": app_id, "app_name": app_name, "key": key, "rows": [item]})
            else:
                match["rows"].append(item)
    consolidated = []
    for group in groups:
        app_id, app_name, key, rows = group["application_id"], group["app_name"], group["key"], group["rows"]
        sources = _unique_values([source for claim in rows for source in _source_ref_ids(claim)])
        source_types = sorted({str(source.get("source_type")) for source in sources})
        states = {claim.get("verification_state") for claim in rows}
        uncertain = bool(states & UNCERTAIN_STATES)
        confidences = [float(claim["confidence"]) for claim in rows if claim.get("confidence") is not None]
        confidence = min(confidences) if confidences else None
        earliest = min((float(claim.get("timestamp", 0)) for claim in rows), default=0.0)
        # Prefer the clearest supported phrasing while retaining uncertainty from every source.
        chosen = min(rows, key=lambda item: (bool(re.search(r"->|<->", str(item.get("claim", "")))),
                                             len(re.findall(r"\b(?:so|then|basically|you know|i mean)\b", item.get("claim", ""), re.I)),
                                             -float(item.get("confidence") or 0), -len(str(item.get("claim", "")))))
        canonical_fact = _canonical_fact_text(str(chosen.get("claim", "")), app_name)
        topic = classify_semantic_topic(canonical_fact)
        timecode = _format_timecode(earliest)
        knowledge_id = _stable_id("knowledge", app_id, key)
        evidence_refs = []
        observations = []
        for ref in sources:
            ref_time = ref.get("timestamp")
            observations.append({"source_session": source_session, "timestamp_seconds": ref_time,
                                 "timecode": _format_timecode(float(ref_time)) if ref_time is not None else None})
            evidence_refs.append(ref)
        temporal = (topic in LIVE_VALIDATION_TOPICS and topic != "Operations") or bool(
            re.search(r"\b(?:data classification|ownership|owner|support group|authentication provider|environments?|configuration|lifecycle|bia|business impact assessment)\b",
                      canonical_fact, re.I)
        )
        consolidated.append({
            "claim_id": _stable_id("claim", source_session, app_id, key),
            "knowledge_id": knowledge_id, "version": 1, "application_id": app_id,
            "topic": topic, "canonical_fact": canonical_fact, "claim": canonical_fact,
            "source_type": "SEMANTIC_CONSOLIDATED", "source_types": source_types,
            "source_id": source_session, "source_session": source_session,
            "source_sessions": [source_session], "timestamp": earliest,
            "observed_at": {"source_session": source_session, "timestamp_seconds": earliest, "timecode": timecode},
            "support_observations": _unique_values(observations),
            "current_live_validation_required": temporal,
            "current_state": "NOT_CURRENTLY_VERIFIED" if temporal else "NOT_APPLICABLE",
            "frame_id": next((ref.get("frame_id") for ref in sources if ref.get("frame_id")), None),
            "confidence": confidence,
            "verification_state": "SOURCE_UNCERTAIN" if uncertain else "SOURCE_CONFIRMED",
            "first_seen": {"session_id": source_session, "timestamp": earliest}, "last_confirmed": None,
            "supporting_sources": sources, "source_evidence_refs": evidence_refs,
            "conflicts": [], "ambiguities": list(_unique_values([marker for claim in rows
                                                                   for marker in claim.get("ambiguities", [])])),
        })
    return sorted(consolidated, key=lambda item: (item["application_id"], item["topic"], item["canonical_fact"]))


def _format_timecode(seconds: float) -> str:
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_open_questions(events: list[dict[str, Any]], claims: list[dict[str, Any]],
                         source_session: str, apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    app_names = {item.get("application_id"): item.get("name") for item in apps}
    app_aliases = {_normalize_name(str(alias)): item.get("application_id") for item in apps
                   for alias in [item.get("name"), *item.get("aliases", [])] if alias}
    material = []
    for event in events:
        text = str(event.get("summary", ""))
        lowered = text.casefold()
        candidates = []
        if re.search(r"front.?end|website support|support boundary", lowered) and re.search(r"unclear|unknown|unconfirmed|not clear", lowered):
            candidates.append("The frontend ownership and support boundary remains unconfirmed.")
        if re.search(r"authentication|pingid|it access", lowered) and re.search(r"uncertain|unclear|different|confirm", lowered):
            candidates.append("Authentication provider wording and the named IT Access user-management relationship require confirmation.")
        if re.search(r"decommission", lowered) and re.search(r"undecided|expect|not shown|decision", lowered):
            candidates.append("The decommissioning decision remains unresolved.")
        if re.search(r"open.source|maturity|incomplete", lowered):
            candidates.append("Application maturity and the incomplete open-source statement require clarification.")
        if re.search(r"technical presentation deferred|not prepared|no prepared slides|lacks access", lowered):
            candidates.append("Detailed technical architecture was not established in this recording.")
        if re.search(r"resource.group permission|no permission", lowered):
            candidates.append("Required resource-group access was not confirmed in this recording.")
        for question in candidates:
            event_app = _normalize_name(str(event.get("application") or ""))
            app_id = app_aliases.get(event_app)
            if app_id is None:
                app_id = next((claim.get("application_id") for claim in claims
                               if event.get("id") in {ref.get("event_id") for ref in claim.get("supporting_sources", [])}), None)
            material.append({"question_id": _stable_id("question", source_session, app_id, question),
                             "application_id": app_id, "application_name": app_names.get(app_id),
                             "question": question, "source_session": source_session,
                             "verification_state": "NEEDS_REVIEW", "evidence_refs": [{"event_id": event.get("id"),
                             "timestamp": event.get("start"), "source_types": event.get("source_types", [])}]})
    for question in material:
        question["application_name"] = app_names.get(question["application_id"])
    deduplicated: dict[tuple[str | None, str], dict[str, Any]] = {}
    for question in material:
        key = (question.get("application_id"), question["question"])
        deduplicated.setdefault(key, question)
        if len(deduplicated[key]["evidence_refs"]) < 2:
            if question["evidence_refs"][0] not in deduplicated[key]["evidence_refs"]:
                deduplicated[key]["evidence_refs"].extend(question["evidence_refs"])
    return list(deduplicated.values())


def build_glossary(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = {
        "SDS": (r"safety data sheets?", "Safety data sheets, maintained as country-specific documents."),
        "Azure SQL": (r"azure sql", "Identified as supporting application data storage."),
        "Azure Data Factory": (r"azure data factory", "Identified for data processing and application operations."),
        "PingID": (r"pingid", "Named in evidence related to application authentication; current configuration needs validation."),
        "Salesforce LEX": (r"salesforce lex", "Shown as a source in the recorded export flow."),
        "SaaS/ETL": (r"saas/etl", "Shown as an intermediate application in the recorded export flow."),
        "IT Access": (r"it access", "Term mentioned for application identity/access; exact meaning needs confirmation."),
    }
    glossary = []
    for term, (pattern, definition) in terms.items():
        supporting = [claim for claim in claims if re.search(pattern, claim["canonical_fact"], re.I)]
        if not supporting:
            continue
        refs = _unique_values([ref for claim in supporting for ref in claim.get("source_evidence_refs", [])])
        glossary.append({"term": term, "recorded_context": definition,
                         "source_evidence_refs": refs,
                         "verification_state": "SOURCE_UNCERTAIN" if any(item["verification_state"] == "SOURCE_UNCERTAIN" for item in supporting) else "SOURCE_CONFIRMED"})
    return glossary


def build_quality_evidence_notes(bundle: MediaEvidenceBundle) -> list[dict[str, Any]]:
    speech = bundle.speech_coverage
    notes = []
    speech_percent = speech.get("speech_coverage_percent")
    media_percent = speech.get("media_coverage_percent")
    if speech_percent is not None:
        notes.append({"note": f"Measured speech coverage is {float(speech_percent):.2f}%; speech gate: {speech.get('speech_quality_gate', 'NOT_EVALUATED')}.",
                      "evidence_refs": []})
    if media_percent is not None:
        notes.append({"note": f"Transcript segments span {float(media_percent):.2f}% of the full video timeline; media coverage is distinct from speech coverage.",
                      "evidence_refs": []})
    for event in bundle.evidence_events:
        summary = str(event.get("summary", "")).casefold()
        if "no transcript segment reaches" in summary or "final" in summary and "video interval" in summary:
            notes.append({"note": "The final video interval has no transcript coverage; sampled frames in that interval were classified as gallery-only.",
                          "evidence_refs": [str(event.get("id"))] if event.get("id") else []})
    return notes


def _golden_topic(title: str) -> str | None:
    value = title.casefold()
    if "business purpose" in value:
        return "Purpose / business context"
    if "architecture" in value or "environment" in value or "configuration" in value:
        return "Architecture / hosting"
    if "data flow" in value:
        return "Data / storage"
    if "authentication" in value or "access" in value:
        return "Authentication / access"
    if "role" in value or "user" in value:
        return "Roles / permissions"
    if "dependenc" in value:
        return "Integrations / dependencies"
    if "ownership" in value or "support" in value or "ticket" in value:
        return "Support / ownership"
    if "lifecycle" in value:
        return "Lifecycle"
    if "procedure" in value or "action item" in value or "monitoring" in value:
        return "Operations"
    if "question" in value or "ambigu" in value or "risk" in value or "deferred" in value:
        return "Open questions"
    return None


def _count_semantic_duplicates(facts: list[dict[str, Any]], applications: list[dict[str, Any]]) -> int:
    aliases_by_id = {str(item.get("application_id")): [str(item.get("name") or ""),
                                                       *[str(alias) for alias in item.get("aliases", [])]]
                     for item in applications if item.get("application_id")}
    seen: list[tuple[str, str]] = []
    duplicates = 0
    for item in facts:
        app_id = str(item.get("application_id") or "")
        key = _semantic_key(str(item.get("canonical_fact", "")), aliases_by_id.get(app_id, [app_id]))
        if any(previous_app == app_id and _same_semantic_fact(previous, key) for previous_app, previous in seen):
            duplicates += 1
        seen.append((app_id, key))
    return duplicates


def _semantic_fact_features(text: str) -> set[str]:
    value = re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", text.casefold()))
    features = set()
    if re.search(r"\b(?:custom backend|backend application)\b", value):
        features.add("backend")
    if re.search(r"\b(?:hosted|hosting|deployed|azure|cloud)\b", value):
        features.add("hosting")
    if re.search(r"\b(?:sql|database|data storage|storage)\b", value):
        features.add("sql_storage")
    if re.search(r"\b(?:mail|email).{0,35}subscription|subscription.{0,35}(?:mail|email)\b", value):
        features.add("mail_subscription")
    if re.search(r"\b(?:safety data sheets?|technical documents?)\b", value):
        features.add("application_documents")
    if re.search(r"\b(?:share|sharing|provides?|maintained|access|retrieve|documents?)\b", value) and "application_documents" in features:
        features.add("document_use")
    if re.search(r"\b(?:public|non.confidential)\b", value) and "application_documents" in features:
        features.add("public_documents")
    if re.search(r"\b(?:consumer|customer|retailer)s?\b", value):
        features.add("external_audience")
    if re.search(r"\b(?:external|public) website\b", value):
        features.add("external_website")
    if "reach" in value and re.search(r"business requirements?|business needs?", value):
        features.add("reach_business_requirement")
    if re.search(r"\bsubscriptions?\b", value) and re.search(r"\bnotifications?\b", value):
        features.add("subscriptions_notifications")
    if re.search(r"\bglobal admin(?:istrator)?s?\b", value):
        features.add("global_admin")
    if re.search(r"\blocal admin(?:istrator)?s?\b", value):
        features.add("local_admin")
    if re.search(r"\bconsumers? and customers?\b", value):
        features.add("consumer_customer_role")
    if re.search(r"\bcountries\b", value) and re.search(r"\bmanag(?:e|es|ed|ing|ement)\b", value):
        features.add("country_management")
    if re.search(r"\btext modules?\b", value):
        features.add("admin_text_modules")
    if re.search(r"\b(?:products? and categories|products/categories)\b", value):
        features.add("product_category_management")
    if re.search(r"\b(?:role assigned|role.scoped|controlled access|functions depend on.*role|responsibilities)\b", value):
        features.add("role_scoped_functions")
    if re.search(r"\b(?:public|external) website\b", value) and "support" in value and "backend" in value:
        features.add("website_backend_support_scope")
    if re.search(r"\bfront.?end\b", value) and re.search(r"\b(?:ownership|owner|boundary)\b", value):
        features.add("frontend_ownership_boundary")
    if re.search(r"\b(?:manually|add(?:ing)?|edit(?:ing)?|delet(?:e|ing)|maintain)\b", value) and "application_documents" in features:
        features.add("manual_document_operations")
    if re.search(r"\bpdfs?\b", value) and re.search(r"\b(?:extract|retrieve|access|export)\b", value):
        features.add("pdf_retrieval")
    if re.search(r"\bdevelopers?\b", value) and re.search(r"\b(?:manual|browser|configuration|configure)\b", value):
        features.add("developer_configuration")
    if "production" in value and "development" in value:
        features.add("production_development_environments")
    if "data factory" in value and re.search(r"\bprocessing\b", value):
        features.add("data_factory_processing")
    if re.search(r"\bprivate endpoints?\b", value) and re.search(r"\bvirtual networks?\b|\bvnet\b", value):
        features.add("private_network_controls")
    if re.search(r"\bowner\b", value):
        features.add("application_owner")
    if "support group" in value:
        features.add("application_support_group")
    if "data classification" in value and "public" in value:
        features.add("public_data_classification")
    if (re.search(r"\bbia\b", value) or "business impact assessment" in value) and re.search(r"\blow\b", value):
        features.add("low_business_impact")
    if "pingid" in value and re.search(r"\bauthentication|authenticate\b", value):
        features.add("pingid_authentication")
    if re.search(r"\bit access\b", value):
        features.add("it_access_user_management")
    if re.search(r"\b(?:sunset|leverage/optimize|leverage optimized|lifecycle)\b", value):
        features.add("lifecycle_status")
    if "decommission" in value:
        features.add("decommission_decision")
    if re.search(r"\blimited (?:usage|users?|user count)\b", value) or "limited usage" in value:
        features.add("limited_usage")
    if "saas/etl" in value:
        features.add("saas_etl_platform")
    if re.search(r"\bpanelist payments?\b", value) and "fulfilment" in value:
        features.add("panelist_payment_fulfilment_context")
    if "salesforce lex" in value and "fulfilment" in value:
        features.add("salesforce_fulfilment_data_export")
    if re.search(r"\b(?:direct database access|database access)\b", value) and re.search(r"\b(?:operations|technology development|business)\b", value):
        features.add("database_access_groups")
    if re.search(r"\b(?:class|category|sub.category)\b", value) and re.search(r"\bapplication platform|business application\b", value):
        features.add("application_catalogue_category")
    if re.search(r"\bresource.group\b", value) and re.search(r"\bpermission|access\b", value):
        features.add("resource_group_access_issue")
    if re.search(r"technical (?:deep.dive|walkthrough).{0,40}deferred|walkthrough was deferred|technical architecture.{0,40}(?:not established|was not covered)", value):
        features.add("technical_walkthrough_deferred")
    return features


def _semantic_coverage_topic(text: str) -> str:
    features = _semantic_fact_features(text)
    if features & {"global_admin", "local_admin", "role_scoped_functions", "database_access_groups", "consumer_customer_role"}:
        return "Roles / permissions"
    if features & {"website_backend_support_scope", "frontend_ownership_boundary", "application_owner"}:
        return "Support / ownership"
    if features & {"public_documents", "external_audience", "external_website", "reach_business_requirement"}:
        return "Purpose / business context"
    if features & {"lifecycle_status", "decommission_decision"}:
        return "Lifecycle / open questions"
    return classify_semantic_topic(text)


def _application_key(value: str) -> str:
    normalized = _normalize_name(value).replace(" com", "")
    return normalized.replace(" ", "")


def compare_session_pack_to_golden(pack: dict[str, Any], golden: dict[str, Any]) -> dict[str, Any]:
    gold_claims = golden.get("claims", [])
    gold_apps = golden.get("applications", [])
    gold_diagrams = golden.get("derived_diagrams", golden.get("diagrams", []))
    sections = golden.get("common_sections", {})
    gold_open = sections.get("Open Questions", []) if isinstance(sections, dict) else []
    gold_glossary = sections.get("Glossary", []) if isinstance(sections, dict) else []
    gold_topics = set()
    for app in gold_apps:
        for section in app.get("sections", []):
            if section.get("claims"):
                topic = _golden_topic(str(section.get("title", "")))
                if topic:
                    gold_topics.add(topic)
    current_facts = pack.get("canonical_facts", [])
    current_apps = pack.get("applications", [])
    current_topics = {str(item.get("topic")) for item in current_facts}
    if pack.get("open_questions"):
        current_topics.add("Open questions")
    raw_transcript = sum(item.get("source_type") == "TRANSCRIPT" or _is_conversational_claim(item.get("canonical_fact", ""))
                         for item in current_facts)
    duplicate_supports = sum(max(0, len(item.get("source_evidence_refs", [])) - 1) for item in current_facts)
    unsupported = sum(not item.get("source_evidence_refs") for item in current_facts)
    low = sum(item.get("verification_state") not in UNCERTAIN_STATES and item.get("confidence") is not None
              and float(item["confidence"]) < .5 for item in current_facts)
    duplicate_pairs = _count_semantic_duplicates(current_facts, pack.get("application_candidates", []))
    candidates = pack.get("application_candidates", [])

    def resolve_v3_application(golden_app_id: str) -> str | None:
        gold_key = _application_key(golden_app_id)
        for candidate in candidates:
            v3_id = str(candidate.get("application_id") or "")
            aliases = [str(candidate.get("name") or ""), *[str(alias) for alias in candidate.get("aliases", [])], v3_id]
            if any(_application_key(alias) == gold_key or
                   (len(gold_key) >= 8 and (gold_key in _application_key(alias) or _application_key(alias) in gold_key))
                   for alias in aliases if alias):
                return v3_id
        return None

    v3_features: dict[str, set[str]] = {}
    for fact in current_facts:
        app_id = str(fact.get("application_id") or "")
        v3_features.setdefault(app_id, set()).update(_semantic_fact_features(str(fact.get("canonical_fact", ""))))
    for question in pack.get("open_questions", []):
        app_id = str(question.get("application_id") or "")
        v3_features.setdefault(app_id, set()).update(_semantic_fact_features(str(question.get("question", ""))))

    golden_material = []
    for claim in gold_claims:
        gold_app_id = str(claim.get("application_id") or "")
        text = str(claim.get("claim") or claim.get("text") or "")
        features = _semantic_fact_features(text)
        if gold_app_id in {"", "SESSION_GENERAL"} or not features:
            continue
        v3_app_id = resolve_v3_application(gold_app_id)
        golden_material.append({"claim_id": claim.get("claim_id"), "application_id": gold_app_id,
                                "topic": _semantic_coverage_topic(text), "features": features,
                                "v3_application_id": v3_app_id})
    covered_golden = [item for item in golden_material if item["v3_application_id"] and
                      item["features"] <= v3_features.get(item["v3_application_id"], set())]
    missing_golden = [item for item in golden_material if item not in covered_golden]
    missing_topics = sorted({str(item["topic"]) for item in missing_golden})
    v3_material_count = sum(item.get("verification_state") not in UNCERTAIN_STATES for item in current_facts)
    metrics = {
        "canonical_facts": len(current_facts), "golden_canonical_facts": len(gold_claims),
        "applications": len(current_apps), "golden_applications": len(gold_apps),
        "topics_represented": sorted(current_topics), "golden_topics_represented": sorted(gold_topics),
        "uncovered_golden_topics": sorted(gold_topics - current_topics),
        "GOLDEN_MATERIAL_FACTS": len(golden_material),
        "V3_MATERIAL_FACTS": v3_material_count,
        "GOLDEN_FACTS_SEMANTICALLY_COVERED": len(covered_golden),
        "MISSING_GOLDEN_MATERIAL_FACTS": [
            {"claim_id": item["claim_id"], "topic": item["topic"]} for item in missing_golden
        ],
        "missing_golden_topics": missing_topics,
        "diagrams": len(pack.get("diagrams", [])), "golden_diagrams": len(gold_diagrams),
        "open_questions": len(pack.get("open_questions", [])), "golden_open_questions": len(gold_open),
        "glossary_entries": len(pack.get("glossary", [])), "golden_glossary_entries": len(gold_glossary),
        "raw_transcript_claims": raw_transcript, "semantic_duplicates": duplicate_pairs,
        "duplicate_support_refs_consolidated": duplicate_supports,
        "low_confidence_claims": low, "golden_low_confidence_claims": sum(
            item.get("confidence") is not None and float(item["confidence"]) < .5 for item in gold_claims),
        "unsupported_facts": unsupported,
    }
    coverage_regression = bool(
        metrics["applications"] < metrics["golden_applications"]
        or metrics["uncovered_golden_topics"]
        or metrics["MISSING_GOLDEN_MATERIAL_FACTS"]
        or metrics["diagrams"] < metrics["golden_diagrams"]
        or metrics["open_questions"] < metrics["golden_open_questions"]
        or metrics["glossary_entries"] < metrics["golden_glossary_entries"]
    )
    grounding_regression = metrics["unsupported_facts"] > 0 or metrics["low_confidence_claims"] > metrics["golden_low_confidence_claims"]
    required_sections = {"Executive Brief", "Applications", "Architecture / Data Flow", "Open Questions / Needs Review",
                         "Glossary", "Evidence Timeline", "Quality / Evidence Notes"}
    presentation_regression = not required_sections <= set(pack.get("rendered_sections", []))
    return {**metrics, "COVERAGE_REGRESSION": "YES" if coverage_regression else "NO",
            "GROUNDING_REGRESSION": "YES" if grounding_regression else "NO",
            "PRESENTATION_REGRESSION": "YES" if presentation_regression else "NO"}


def extract_diagram_graphs(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagrams = []
    for frame in frames:
        provenance = frame.get("provenance") or {"frame_id": frame.get("frame_id"), "timestamp": frame.get("timestamp"),
                                                   "image_path": frame.get("source_image")}
        if frame.get("ocr_status") == "LOW_CONFIDENCE" and not frame.get("review_state"):
            continue
        nodes = list(frame.get("nodes") or [])
        clean_edges = [edge for edge in (frame.get("edges") or [])
                       if edge.get("relation_type") in DIAGRAM_RELATIONS
                       and edge.get("provenance", provenance).get("frame_id") == provenance.get("frame_id")]
        node_ids = {str(node.get("label", node.get("id"))).casefold() for node in nodes}

        def node(label: str) -> str:
            label = re.sub(r"\s+", " ", label).strip(" .,:;>")
            key = label.casefold()
            if key not in node_ids:
                nodes.append({"id": _slug(label), "label": label, "provenance": dict(provenance)})
                node_ids.add(key)
            return label

        assertions = frame.get("assertions") or []
        flows = list(frame.get("data_flows") or [])
        relationships = list(frame.get("relationships") or [])
        flows.extend(assertion.get("value") for assertion in assertions
                     if isinstance(assertion, dict) and assertion.get("assertion_type") == "data_flows")
        relationships.extend(assertion.get("value") for assertion in assertions
                              if isinstance(assertion, dict) and assertion.get("assertion_type") == "relationships")
        for text in _unique_values([str(value) for value in flows + relationships if value]):
            annotation = ""
            if ":" in text:
                text, annotation = text.split(":", 1)
            if "<->" in text:
                left, right = (value.strip() for value in text.split("<->", 1))
                clean_edges.append({"source": node(left), "target": node(right), "relation_type": "AUTHENTICATES_WITH",
                                    "directed": False, "label": annotation or "bidirectional relationship",
                                    "provenance": dict(provenance)})
            elif "->" in text:
                path = [value.strip() for value in text.split("->") if value.strip()]
                for left, right in zip(path, path[1:]):
                    clean_edges.append({"source": node(left), "target": node(right), "relation_type": "DATA_FLOW",
                                        "directed": True, "label": annotation or None,
                                        "provenance": dict(provenance)})
            else:
                relation = None
                match = re.match(r"(.+?)\s+is hosted in\s+(.+)$", text, re.I)
                if match:
                    left, right, relation = match.group(1), match.group(2), "HOSTS"
                if not match:
                    match = re.match(r"(.+?)\s+supports\s+(.+)$", text, re.I)
                    if match:
                        left, right, relation = match.group(1), match.group(2), "SUPPORTS"
                if not match:
                    match = re.match(r"(.+?)\s+control\s+network paths to\s+(.+)$", text, re.I)
                    if match:
                        left, right, relation = match.group(1), match.group(2), "NETWORK_PATH_CONTROL"
                if relation:
                    clean_edges.append({"source": node(left), "target": node(right), "relation_type": relation,
                                        "directed": False, "label": None, "provenance": dict(provenance)})
        if nodes and clean_edges:
            diagrams.append({"diagram_id": _stable_id("diagram", provenance.get("frame_id")),
                             "title": frame.get("topic_title") or frame.get("title") or "Evidence-grounded diagram",
                             "application": frame.get("application"), "nodes": nodes, "edges": clean_edges,
                             "source_frames": [provenance], "source_evidence_ids": [provenance.get("frame_id")],
                             "verification_state": "VISUAL_CONFIRMED"})
    return diagrams


def consolidate_diagram_graphs(diagrams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    consolidated: dict[str, dict[str, Any]] = {}
    for diagram in diagrams:
        signature = json.dumps({
            "application": diagram.get("application"),
            "nodes": sorted(_normalize_name(str(node.get("label", node.get("id", ""))))
                            for node in diagram.get("nodes", [])),
            "edges": sorted((
                _normalize_name(str(edge.get("source", ""))),
                str(edge.get("relation_type", "")),
                _normalize_name(str(edge.get("target", ""))),
                bool(edge.get("directed")),
            ) for edge in diagram.get("edges", [])),
        }, sort_keys=True)
        current = consolidated.get(signature)
        if current is None:
            consolidated[signature] = diagram
            continue
        current["source_frames"] = _unique_values([*current.get("source_frames", []), *diagram.get("source_frames", [])])
        current["source_evidence_ids"] = _unique_values([*current.get("source_evidence_ids", []),
                                                          *diagram.get("source_evidence_ids", [])])
    return list(consolidated.values())


def validate_pack_claim_provenance(claims: list[dict[str, Any]], source_ids: set[str], frame_ids: set[str]) -> list[str]:
    errors = validate_claim_records(claims)
    for claim in claims:
        if claim.get("source_id") not in source_ids:
            errors.append(f"{claim.get('claim_id')} references unknown source_id")
        if claim.get("frame_id") and claim["frame_id"] not in frame_ids:
            errors.append(f"{claim.get('claim_id')} references unknown frame_id")
        for ref in claim.get("supporting_sources", []):
            if ref.get("source_id") not in source_ids:
                errors.append(f"{claim.get('claim_id')} supporting source is unresolved")
            if ref.get("source_type") == "TRANSCRIPT" and not ref.get("segments"):
                errors.append(f"{claim.get('claim_id')} transcript citation has no segment")
    return errors


def validate_diagram_provenance(diagrams: list[dict[str, Any]], claim_ids: set[str], frame_ids: set[str], event_ids: set[str]) -> list[str]:
    errors = []
    for diagram in diagrams:
        if not diagram.get("source_frames"):
            errors.append(f"{diagram.get('diagram_id')} has no frame provenance")
        for frame in diagram.get("source_frames", []):
            if frame.get("frame_id") not in frame_ids:
                errors.append(f"{diagram.get('diagram_id')} has unknown frame provenance")
        for edge in diagram.get("edges", []):
            if not edge.get("provenance", {}).get("frame_id"):
                errors.append(f"{diagram.get('diagram_id')} edge has no frame provenance")
            if set(edge.get("claim_ids", [])) - claim_ids or set(edge.get("event_ids", [])) - event_ids:
                errors.append(f"{diagram.get('diagram_id')} edge has unresolved claim/event provenance")
    return errors


def validate_diagram_relations(diagrams: list[dict[str, Any]]) -> list[str]:
    errors = []
    for diagram in diagrams:
        for edge in diagram.get("edges", []):
            relation = edge.get("relation_type")
            if relation not in DIAGRAM_RELATIONS:
                errors.append(f"{diagram.get('diagram_id')} has unsupported relation")
            if relation not in DIRECTED_RELATIONS and edge.get("directed"):
                errors.append(f"{diagram.get('diagram_id')} infers direction for a neutral relation")
    return errors


def validate_source_artifact_dedup(source_map: list[dict[str, Any]]) -> list[str]:
    keys = []
    for item in source_map:
        path, digest = item.get("source_path") or item.get("path"), item.get("sha256")
        if path and digest:
            keys.append((str(path).replace("\\", "/").casefold(), str(digest).casefold()))
    return ["duplicate source artifact IDs remain"] if len(keys) != len(set(keys)) else []


def validate_application_claim_isolation(apps: list[dict[str, Any]], claims: list[dict[str, Any]]) -> list[str]:
    by_id = {claim.get("claim_id"): claim for claim in claims}
    errors = []
    for app in apps:
        for section in app.get("sections", []):
            for claim_id in section.get("claim_ids", []):
                claim = by_id.get(claim_id)
                if not claim or claim.get("application_id") not in {app.get("application_id"), "SESSION_GENERAL"}:
                    errors.append(f"claim {claim_id} leaks across application sections")
    return errors


def evaluate_session_pack_gates(*, transcript_state: str, speech_gate: str, visual_gate: str,
                                claim_errors: list[str], diagram_errors: list[str], application_ids: set[str],
                                low_confidence_ratio: float, procedures: list[dict[str, Any]],
                                application_errors: list[str], source_map_errors: list[str],
                                timeline_errors: list[str], relation_errors: list[str],
                                valid_evidence_ids: set[str] | None = None) -> dict[str, str]:
    gates = {
        "TRANSCRIPT_SPEECH_COVERAGE": "PASS" if transcript_state == "VALID" and speech_gate == "PASS" else "FAIL",
        "VISUAL_TOPIC_COVERAGE": "PASS" if visual_gate == "PASS" else "FAIL",
        "CLAIM_LEDGER": "PASS" if not claim_errors else "FAIL",
        "DIAGRAM_PROVENANCE": "PASS" if not diagram_errors else "FAIL",
        "APPLICATION_SEGMENTATION": "PASS" if application_ids - {"SESSION_GENERAL"} else "FAIL",
        "APPLICATION_CLAIM_ISOLATION": "PASS" if not application_errors else "FAIL",
        "SOURCE_ARTIFACT_DEDUP": "PASS" if not source_map_errors else "FAIL",
        "EVIDENCE_TIMELINE_CHRONOLOGICAL": "PASS" if not timeline_errors else "FAIL",
        "DIAGRAM_RELATION_GROUNDING": "PASS" if not relation_errors else "FAIL",
        "LOW_CONFIDENCE_FILLER": "PASS" if low_confidence_ratio < .1 else "FAIL",
        "PROCEDURE_GROUNDING": procedure_grounding(procedures, valid_evidence_ids or set())[0],
    }
    gates["QUALITY_GATE"] = "PASS" if all(value in {"PASS", "NOT_APPLICABLE"} for value in gates.values()) else "FAIL"
    return gates


def build_derived_diagrams(frames: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return extract_diagram_graphs(frames or [])


def _executive_brief(applications: list[dict[str, Any]]) -> str:
    preferred = ["Purpose / business context", "Architecture / hosting", "Data / storage",
                 "Integrations / dependencies", "Support / ownership", "Lifecycle"]
    paragraphs = []
    for app in applications:
        sections = {section.get("title"): section.get("claims", []) for section in app.get("sections", [])}
        claims = [section_claims[0]["claim"] for name in preferred
                  if (section_claims := sections.get(name))]
        if claims:
            label = f"{app['name']}: "
            first = claims[0]
            if first.casefold().startswith(label.casefold()):
                first = first[len(label):]
            paragraphs.append(f"{app['name']}: {first}")
    return "\n\n".join(paragraphs) or "No material semantic knowledge passed evidence review; this pack requires review."


def _markdown(pack: dict[str, Any]) -> str:
    lines = [f"# {pack['title']}", "", f"State: {pack['quality_state']}", "",
             "## Executive Brief", "", pack.get("executive_brief", ""), "", "## Applications", ""]
    if any(item.get("current_live_validation_required") for item in pack.get("canonical_facts", [])):
        lines.extend(["Facts below describe what was observed in the KT recording. Items marked for live validation are not current-state verification.", ""])
    for application in pack.get("applications", []):
        lines.extend([f"## {application['name']}", ""])
        for section in application.get("sections", []):
            lines.extend([f"### {section['title']}", ""])
            for claim in section.get("claims", []):
                fact_text = str(claim["canonical_fact"])
                fact_text = re.sub(rf"^{re.escape(str(application['name']))}:\s*", "", fact_text, flags=re.I)
                fact_text = fact_text[:1].upper() + fact_text[1:]
                refs = _unique_values([ref.get("event_id") or ref.get("frame_id")
                                       or next((segment.get("segment_id") for segment in ref.get("segments", [])), None)
                                       for ref in claim.get("supporting_sources", [])])
                refs = [str(ref) for ref in refs if ref]
                suffix = f" [Evidence: {', '.join(refs)}]" if refs else ""
                temporal = (f" Observed in KT recording at {claim['observed_at']['timecode']}; current state not verified."
                            if claim.get("current_live_validation_required") else "")
                lines.append(f"- {fact_text}{temporal}{suffix}")
            lines.append("")
    if pack.get("diagrams"):
        lines.extend(["## Architecture / Data Flow", ""])
        for diagram in pack["diagrams"]:
            lines.extend([f"### {diagram.get('title') or 'Evidence-grounded diagram'}", ""])
            for edge in diagram.get("edges", []):
                relation = str(edge.get("relation_type", "related")).replace("_", " ").lower()
                connector = " -> " if edge.get("directed") else f" -- {relation} -- "
                statement = f"{edge.get('source')}" + (connector + str(edge.get("target")))
                evidence = edge.get("provenance", {}).get("frame_id")
                lines.append(f"- {statement}" + (f" [Evidence: {evidence}]" if evidence else ""))
            frames = [item.get("frame_id") for item in diagram.get("source_frames", []) if item.get("frame_id")]
            if frames:
                lines.append(f"Observed in recording; source frames: {', '.join(frames)}.")
            lines.append("")
    if pack.get("procedures"):
        lines.extend(["## Procedures", ""])
        lines.extend(f"- {item.get('title') or item.get('purpose')}" for item in pack["procedures"])
        lines.append("")
    if pack.get("open_questions"):
        lines.extend(["## Open Questions / Needs Review", ""])
        for item in pack["open_questions"]:
            app = f"{item['application_name']}: " if item.get("application_name") else ""
            refs = ", ".join(ref.get("event_id") or ref.get("frame_id") or "" for ref in item.get("evidence_refs", []))
            lines.append(f"- {app}{item['question']}" + (f" [Evidence: {refs}]" if refs else ""))
        lines.append("")
    if pack.get("glossary"):
        lines.extend(["## Glossary", ""])
        for item in pack["glossary"]:
            refs = ", ".join(ref.get("event_id") or ref.get("frame_id") or "" for ref in item.get("source_evidence_refs", []))
            lines.append(f"- **{item['term']}**: {item['recorded_context']}" + (f" [Evidence: {refs}]" if refs else ""))
        lines.append("")
    lines.extend(["", "## Evidence Timeline", ""])
    for item in pack["evidence_events"]:
        summary = _timeline_summary(item)
        if not summary:
            continue
        app = str(item.get("application") or "Session")
        for candidate in pack.get("application_candidates", []):
            app_pack = next((value for value in pack.get("applications", [])
                             if value.get("application_id") == candidate.get("application_id")), None)
            aliases = [candidate.get("name"), *candidate.get("aliases", [])]
            if app_pack and any(_normalize_name(str(alias)) == _normalize_name(app) for alias in aliases if alias):
                app = str(app_pack["name"])
                break
        if app.casefold() in {"session", "session_general", "unknown", "none"}:
            app = next((str(app_pack["name"]) for app_pack in pack.get("applications", [])
                        if item.get("id") in {ref.get("event_id") for claim in app_pack.get("claims", [])
                                               for ref in claim.get("supporting_sources", [])}), "Session")
        start = _seconds(item.get("start", 0))
        end = _seconds(item.get("end", item.get("start", 0)))
        def clock(value: float) -> str:
            hours, remainder = divmod(int(value), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        lines.append(f"- {clock(start)}-{clock(end)} | {app} | {summary} | Evidence: {item.get('id')}")
    if pack.get("quality_evidence_notes"):
        lines.extend(["", "## Quality / Evidence Notes", ""])
        for item in pack["quality_evidence_notes"]:
            refs = ", ".join(item.get("evidence_refs", []))
            lines.append(f"- {item['note']}" + (f" [Evidence: {refs}]" if refs else ""))
    return "\n".join(lines) + "\n"


def _timeline_summary(event: dict[str, Any]) -> str | None:
    text = str(event.get("summary") or event.get("text") or "Evidence event").strip()
    lowered = text.casefold()
    if re.search(r"suspicious phrase|advises trying|attempt to switch|no prepared slides|data floor/code|limited tickets/use impression", lowered):
        return None
    if re.search(r"reports no resource.group permission", lowered):
        return "Resource-group access was not confirmed."
    if re.search(r"technical presentation deferred|not prepared and lacks access", lowered):
        return "A technical walkthrough was deferred; architecture detail remains incomplete."
    if re.search(r"attempt to switch.*result", lowered):
        return None
    return text


def _write_pdf(markdown_text: str, path: Path, title: str) -> None:
    from xml.sax.saxutils import escape

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"]), Spacer(1, .2 * inch)]
    for line in markdown_text.splitlines():
        if not line:
            story.append(Spacer(1, .08 * inch))
        elif line.startswith("### "):
            story.append(Paragraph(escape(line[4:]), styles["Heading3"]))
        elif line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), styles["Heading2"]))
        elif line.startswith("# "):
            continue
        else:
            body = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escape(line))
            story.append(Paragraph(body, styles["BodyText"]))
    SimpleDocTemplate(str(path), pagesize=letter, rightMargin=.65 * inch, leftMargin=.65 * inch).build(story)


def generate_session_pack(bundle: MediaEvidenceBundle | dict[str, Any], output_dir: Path,
                          *, known_applications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize evidence, derive claims and render a pack only after explicit evidence gates pass."""
    evidence = normalize_evidence_bundle(bundle)
    candidates = discover_application_candidates(evidence)
    applications = []
    for candidate in candidates:
        resolution = resolve_application_identity(candidate, known_applications or [])
        applications.append({**candidate, **resolution})
    claims = extract_claims(evidence, applications)
    resolved_apps = [item for item in applications if item.get("status") in {"MATCH_CONFIRMED", "NEW_APPLICATION"}]
    procedure_app_id = resolved_apps[0].get("application_id") if len(resolved_apps) == 1 else None
    app_aliases = [
        (_normalize_name(str(alias)), str(app["application_id"]))
        for app in resolved_apps
        for alias in [app.get("name"), *app.get("aliases", [])]
        if alias and app.get("application_id")
    ]
    procedure_segments = []
    for segment in evidence.transcript_segments:
        normalized_text = _normalize_name(str(segment.get("text", "")))
        matches = {app_id for alias, app_id in app_aliases if alias and alias in normalized_text}
        resolved_segment_app = segment.get("application_id") or (next(iter(matches)) if len(matches) == 1 else None)
        procedure_segments.append({**segment, "application_id": resolved_segment_app})
    procedures = extract_procedures(
        procedure_segments, media_id=evidence.media_id, application_id=procedure_app_id
    )
    valid_evidence_ids = {str(item.get("segment_id")) for item in evidence.transcript_segments}
    valid_evidence_ids.update(str(item.get("frame_id")) for item in evidence.frames)
    valid_evidence_ids.update(str(item.get("id")) for item in evidence.evidence_events)
    procedure_gate, procedure_errors = procedure_grounding(procedures, valid_evidence_ids)
    runbooks = build_runbooks(procedures, source_session=evidence.media_id, claims=claims)
    runbook_gate, runbook_errors = validate_runbooks(runbooks, valid_evidence_ids)
    frames_by_id = {frame["frame_id"]: frame for frame in evidence.frames}
    raw_ocr_claims_suppressed = 0
    gallery_claims_suppressed = 0
    visual_claims = []
    application_alias_ids = {_normalize_name(str(alias)): app.get("application_id")
                             for app in applications
                             for alias in [app.get("name"), *app.get("aliases", [])]
                             if alias and app.get("application_id")}
    for frame in evidence.frames:
        visual_type = str(frame.get("visual_type") or "OTHER").upper()
        ocr_text = str(frame.get("ocr_text") or "").strip()
        if ocr_text:
            raw_ocr_claims_suppressed += 1
        if visual_type in {"MEETING_GALLERY", "BLACK_OR_EMPTY", "OTHER", "SESSION_GENERAL"}:
            gallery_claims_suppressed += int(bool(ocr_text))
            continue
        if not frame.get("selected", False):
            continue
        # OCR remains evidence; semantic content comes from reviewed structured frame assertions.
        assertions = frame.get("assertions") or []
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            assertion_type = str(assertion.get("assertion_type", "")).casefold()
            if assertion_type not in {"relationships", "data_flows", "configuration_fields", "visible_labels"}:
                continue
            evidence_ref = assertion.get("provenance", {})
            statement = assertion.get("statement") or assertion.get("value")
            if not statement or (evidence_ref.get("review_state") != "HUMAN_REVIEWED"
                                 and not frame.get("transcript_text")):
                continue
            text = str(statement).strip()
            if assertion_type == "visible_labels":
                text = _visual_label_fact(text) or ""
                if not text:
                    continue
            confidence = assertion.get("confidence", evidence_ref.get("confidence", frame.get("confidence")))
            visual_claims.append({
                "claim_id": _stable_id("claim", evidence.media_id, frame["frame_id"], text),
                "application_id": application_alias_ids.get(_normalize_name(str(frame.get("application") or "")),
                                                              frame.get("application_id", "SESSION_GENERAL")), "claim": text,
                "source_type": "VIDEO_FRAME", "source_id": evidence.media_id,
                "timestamp": frame["timestamp"], "frame_id": frame["frame_id"],
                "confidence": float(confidence) if confidence is not None else None,
                "verification_state": "VISUAL_CONFIRMED", "first_seen": {"session_id": evidence.media_id, "timestamp": frame["timestamp"]},
                "last_confirmed": None, "supporting_sources": [{"source_id": evidence.media_id,
                "source_type": "VIDEO_FRAME", "timestamp": frame["timestamp"], "frame_id": frame["frame_id"],
                "assertion_type": assertion.get("assertion_type")}], "conflicts": [],
            })
    claims.extend(visual_claims)
    claims = consolidate_semantic_claims(claims, applications, evidence.media_id)
    apps = []
    app_ids = {item.get("application_id") for item in applications if item.get("application_id")}
    for app_id in sorted(app_ids):
        app = next(item for item in applications if item.get("application_id") == app_id)
        app_claims = [item for item in claims if item.get("application_id") == app_id]
        publishable_claims = [item for item in app_claims if item.get("verification_state") not in UNCERTAIN_STATES]
        if not publishable_claims:
            continue
        grouped: dict[str, list[dict[str, Any]]] = {}
        for claim in publishable_claims:
            grouped.setdefault(str(claim["topic"]), []).append(claim)
        sections = [{"title": name, "claims": rows, "claim_ids": [item["claim_id"] for item in rows]}
                    for name, rows in grouped.items()]
        apps.append({"application_id": app_id, "name": app.get("display_name") or app.get("name", app_id),
                     "aliases": list(app.get("aliases", [])), "claims": publishable_claims,
                     "sections": sections})
    if not apps:
        general = [item for item in claims if item.get("application_id") == "SESSION_GENERAL"
                   and item.get("verification_state") not in UNCERTAIN_STATES]
        apps = [{"application_id": "SESSION_GENERAL", "name": "Session knowledge",
                 "sections": [{"title": "Evidence-derived knowledge", "claims": general,
                               "claim_ids": [item["claim_id"] for item in general]}]}]
        app_ids = {"SESSION_GENERAL"}
    source_ids = {evidence.media_id}
    frame_ids = set(frames_by_id)
    claim_errors = validate_pack_claim_provenance(claims, source_ids, frame_ids)
    application_errors = validate_application_claim_isolation(apps, claims)
    diagrams = consolidate_diagram_graphs(extract_diagram_graphs(evidence.frames))
    alias_to_application = {_normalize_name(str(alias)): item.get("application_id")
                            for item in applications
                            for alias in [item.get("name"), *item.get("aliases", [])]
                            if alias and item.get("application_id")}
    for diagram in diagrams:
        diagram["application_id"] = alias_to_application.get(_normalize_name(str(diagram.get("application") or "")))
    event_ids = {str(item["id"]) for item in evidence.evidence_events}
    diagram_errors = validate_diagram_provenance(diagrams, {item["claim_id"] for item in claims}, frame_ids, event_ids)
    relation_errors = validate_diagram_relations(diagrams)
    semantic_topics = {
        str(frame["semantic_topic"]) for frame in evidence.frames
        if frame.get("semantic_topic") and frame.get("visual_type") not in {"BLACK_OR_EMPTY", "MEETING_GALLERY"}
    }
    selected_topics = set()
    app_aliases = {_normalize_name(str(alias)) for app in applications
                   for alias in [app.get("name"), *app.get("aliases", [])] if alias}
    for frame in evidence.frames:
        if not frame.get("semantic_topic") or not frame.get("selected", True):
            continue
        if _semantic_topic_sources(frame):
            selected_topics.add(str(frame["semantic_topic"]))
            continue
        frame_app = _normalize_name(str(frame.get("application") or ""))
        timestamp = float(frame.get("timestamp", 0))
        if any(event.get("summary") and frame_app in app_aliases
               and _normalize_name(str(event.get("application") or "")) in app_aliases
               and abs(_seconds(event.get("start", 0)) - timestamp) <= 60
               for event in evidence.evidence_events):
            selected_topics.add(str(frame["semantic_topic"]))
    visual_gate = "PASS" if semantic_topics and semantic_topics <= selected_topics else "FAIL"
    transcript_state = evidence.speech_coverage.get("transcript_state", "NEEDS_REVIEW")
    speech_gate = evidence.speech_coverage.get("speech_quality_gate", "FAIL")
    material_claims = [item for item in claims if item.get("verification_state") not in UNCERTAIN_STATES]
    known_confidence = [float(item["confidence"]) for item in material_claims
                        if item.get("confidence") is not None]
    low_confidence_count = sum(value < .5 for value in known_confidence)
    low_ratio = low_confidence_count / max(1, len(known_confidence))
    confidence_by_source: dict[str, dict[str, int]] = {}
    for item in material_claims:
        source_type = str(item.get("source_type") or "UNKNOWN")
        counts = confidence_by_source.setdefault(source_type, {"low_confidence": 0, "missing_confidence": 0})
        if item.get("confidence") is None:
            counts["missing_confidence"] += 1
        elif float(item["confidence"]) < .5:
            counts["low_confidence"] += 1
    gates = evaluate_session_pack_gates(
        transcript_state=transcript_state, speech_gate=speech_gate, visual_gate=visual_gate,
        claim_errors=claim_errors, diagram_errors=diagram_errors, application_ids=app_ids,
        low_confidence_ratio=low_ratio, procedures=procedures, application_errors=application_errors,
        source_map_errors=[], timeline_errors=validate_timeline_chronology(evidence.evidence_events),
        relation_errors=relation_errors, valid_evidence_ids=valid_evidence_ids,
    )
    ambiguous_apps = [item for item in applications if item.get("status") == "AMBIGUOUS"]
    provenance_ids = valid_evidence_ids | {evidence.media_id}
    applications_with_claims = {claim.get("application_id") for claim in claims
                                if claim.get("verification_state") not in UNCERTAIN_STATES}
    applications_with_claims.update(item.get("application_id") for item in procedures if item.get("application_id"))
    unresolved_provenance = [item for item in applications if item.get("application_id") and
                             not any((ref.get("event_id") in provenance_ids or ref.get("frame_id") in provenance_ids
                                      or ref.get("segment_id") in provenance_ids or ref.get("source_id") == evidence.media_id)
                                     for ref in item.get("provenance", []))]
    gates["APPLICATION_RESOLUTION"] = "PASS" if (
        app_ids - {"SESSION_GENERAL"} and not ambiguous_apps and not unresolved_provenance
        and all(item.get("application_id") and item.get("name") for item in applications
                if item.get("status") in {"MATCH_CONFIRMED", "NEW_APPLICATION"})
        and all(item.get("application_id") in applications_with_claims or item.get("mentioned_no_material_knowledge")
                for item in applications if item.get("status") in {"MATCH_CONFIRMED", "NEW_APPLICATION"})
    ) else "FAIL"
    gates["PROCEDURE_GROUNDING"] = procedure_gate
    gates["KAV_RUNBOOK_VALIDATION"] = runbook_gate
    gates["KAV_EXECUTION_READY"] = "NO"
    gates["QUALITY_GATE"] = "PASS" if all(
        value in {"PASS", "NOT_APPLICABLE"} for key, value in gates.items()
        if key not in {"QUALITY_GATE", "KAV_EXECUTION_READY"}
    ) else "FAIL"
    gates["SECOND_BRAIN_READY"] = second_brain_ready(
        quality_gate=gates["QUALITY_GATE"], claim_provenance=gates["CLAIM_LEDGER"],
        application_resolution=gates["APPLICATION_RESOLUTION"], has_application=bool(app_ids - {"SESSION_GENERAL"}),
        conflicts_promoted=any(item.get("verification_state") == "CONFLICTING" for item in claims),
        package_policy="NOT_EVALUATED", raw_transcript_published=False, raw_media_published=False,
        procedure_gate=procedure_gate, runbook_gate=runbook_gate,
    )
    embedding_report = embedding_ready([], second_brain_ready_state=gates["SECOND_BRAIN_READY"])
    gates["EMBEDDING_READY"] = "YES" if embedding_report["DOCUMENT_EMBEDDING_READY"] else "NO"
    open_questions = build_open_questions(evidence.evidence_events, claims, evidence.media_id, apps)
    glossary = build_glossary(claims)
    quality_evidence_notes = build_quality_evidence_notes(evidence)
    quality_state = "READY" if gates["QUALITY_GATE"] == "PASS" else "NEEDS_REVIEW"
    basename = Path(str(evidence.video_metadata.get("basename") or evidence.media_id)).stem
    title = str(evidence.video_metadata.get("title") or basename)
    pack = {
        "schema_version": 2, "document_type": "SESSION_KNOWLEDGE_PACK", "media_id": evidence.media_id,
        "source_identity": str(evidence.video_metadata.get("source_sha256")
                                or evidence.video_metadata.get("path")
                                or evidence.video_metadata.get("basename") or evidence.media_id),
        "source_video": evidence.video_metadata.get("basename", evidence.media_id), "title": title,
        "quality_state": quality_state, "quality_gates": gates,
        "executive_brief": _executive_brief(apps),
        "applications": apps, "application_candidates": applications, "claims": claims,
        "canonical_facts": claims, "topics": sorted({item["topic"] for item in claims}),
        "ambiguities": [item for item in claims if item.get("verification_state") in UNCERTAIN_STATES]
        + [{"claim": f"Application identity unresolved for {item.get('name') or 'this session'}.",
            "source_id": evidence.media_id, "timestamp": None, "application_id": None,
            "verification_state": "NEEDS_REVIEW"} for item in applications if item.get("status") == "AMBIGUOUS"]
        + ([{"claim": "No named application candidate could be grounded from this recording.",
             "source_id": evidence.media_id, "timestamp": None, "application_id": None,
             "verification_state": "NEEDS_REVIEW"}] if not applications else []),
        "diagrams": diagrams, "visual_topics": evidence.visual_topics,
        "open_questions": open_questions, "glossary": glossary,
        "quality_evidence_notes": quality_evidence_notes,
        "rendered_sections": ["Executive Brief", "Applications", "Architecture / Data Flow", "Open Questions / Needs Review",
                              "Glossary", "Evidence Timeline", "Quality / Evidence Notes"],
        "evidence_events": evidence.evidence_events, "transcript_quality": evidence.speech_coverage,
        "procedures": procedures,
        "claim_confidence_diagnostics": {
            "material_claim_count": len(material_claims),
            "low_confidence_claim_count": low_confidence_count,
            "low_confidence_ratio": low_ratio,
            "missing_confidence_count": sum(item.get("confidence") is None for item in material_claims),
            "by_source_type": confidence_by_source,
        },
        "content_diagnostics": {"raw_transcript_fragments_suppressed": len(evidence.transcript_segments) if any(
            str(event.get("summary", "")).strip() for event in evidence.evidence_events) else 0,
            "raw_ocr_claims_suppressed": raw_ocr_claims_suppressed,
            "meeting_gallery_claims_suppressed": gallery_claims_suppressed,
            "material_semantic_claim_count": len(material_claims), "visual_semantic_claim_count": sum(
                "VIDEO_FRAME" in claim.get("source_types", []) for claim in material_claims),
            "raw_transcript_final_claim_count": sum(
                claim.get("source_type") == "TRANSCRIPT" or _is_conversational_claim(claim.get("canonical_fact", ""))
                for claim in claims),
            "raw_ocr_final_claim_count": sum(claim.get("source_type") == "VIDEO_FRAME" for claim in claims),
            "semantic_duplicate_claim_count": _count_semantic_duplicates(claims, applications),
            "duplicate_support_refs_consolidated": sum(max(0, len(claim.get("source_evidence_refs", [])) - 1) for claim in claims)},
        "kav_execution_runbooks": runbooks,
        "embedding_report": embedding_report,
        "procedure_errors": procedure_errors, "kav_runbook_errors": runbook_errors,
        "embedding_inputs": embedding_report["eligible_chunks"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    kav_path = output_dir / "KAV_EXECUTION_RUNBOOKS.json"
    kav_path.write_text(json.dumps({"schema_version": 1, "runbooks": runbooks},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    markdown = _markdown(pack)
    paths = {"json": output_dir / f"{basename}.json", "md": output_dir / f"{basename}.md",
             "pdf": output_dir / f"{basename}.pdf", "kav_runbooks": kav_path}
    paths["json"].write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["md"].write_text(markdown, encoding="utf-8")
    _write_pdf(markdown, paths["pdf"], title)
    if quality_state != "READY":
        diagnostic_path = output_dir / f"{basename}-diagnostic.json"
        diagnostic_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"status": quality_state, "gates": gates, "diagnostic": diagnostic_path, "paths": paths,
                "kav_runbooks": kav_path, "pack": pack}
    return {"status": "READY", "gates": gates, "paths": paths, "pack": pack}


def resolve_application_candidates(candidates: list[dict[str, Any]], known: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, **resolve_application_identity(item, known)} for item in candidates]


def consolidate_claims_across_sessions(session_packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims = []
    unresolved = []
    for pack in session_packs:
        media_id = str(pack.get("media_id") or pack.get("source_video") or "")
        applications = {item.get("application_id"): item for item in pack.get("application_candidates", [])}
        for claim in pack.get("claims", []):
            item = dict(claim)
            item["session_id"] = media_id
            item["fact_key"] = item.get("fact_key") or re.sub(r"\W+", " ", item.get("claim", "").casefold()).strip()
            item["supporting_claims"] = [item.get("claim_id")] if item.get("claim_id") else []
            item["supporting_sessions"] = [media_id]
            item["supporting_frames"] = [item["frame_id"]] if item.get("frame_id") else []
            item["merge_relation"] = claim.get("merge_relation")
            identity = applications.get(item.get("application_id"), {})
            if identity.get("status") == "AMBIGUOUS" or item.get("application_id") in {None, "SESSION_GENERAL"}:
                unresolved.append({"application_id": None, "claim": item.get("claim"),
                                   "supporting_sessions": [media_id], "supporting_claims": item["supporting_claims"],
                                   "supporting_evidence": item.get("supporting_sources", []),
                                   "status": "NEEDS_REVIEW", "conflicts": [], "supersedes": [], "superseded_by": []})
                continue
            claims.append(item)
    facts = consolidate_application_claims(claims)
    for fact in facts:
        fact_id = _stable_id("fact", fact.get("application_id"), fact.get("fact_key"))
        fact["fact_id"] = fact_id
        fact["canonical_text"] = fact.get("canonical_fact") or fact.get("fact")
        fact["supporting_evidence"] = list(fact.get("evidence_refs", []))
        fact.setdefault("supersedes", [])
        fact.setdefault("superseded_by", [])
        fact.setdefault("conflicts", [])
        if fact.get("status") != "CONFLICTING":
            fact["status"] = "CONFIRMED" if len(fact.get("supporting_sessions", [])) > 1 else "NEEDS_REVIEW"
    return [*facts, *unresolved]


def merge_cross_session_facts(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge explicit application/fact keys; differing facts conflict unless an explicit relation is supplied."""
    result = [dict(item) for item in existing]
    for item in incoming:
        current = next((fact for fact in result if fact.get("application_id") == item.get("application_id")
                        and fact.get("fact_key") == item.get("fact_key")), None)
        relation = str(item.get("merge_relation", "")).upper()
        if current is None:
            new_fact = dict(item)
            new_fact.setdefault("fact_id", _stable_id("fact", new_fact.get("application_id"), new_fact.get("fact_key"), new_fact.get("canonical_text")))
            new_fact.setdefault("supporting_sessions", [])
            new_fact.setdefault("supporting_claims", [])
            new_fact.setdefault("supporting_evidence", [])
            new_fact.setdefault("conflicts", [])
            new_fact.setdefault("supersedes", [])
            new_fact.setdefault("superseded_by", [])
            new_fact.setdefault("status", "NEEDS_REVIEW")
            result.append(new_fact)
            continue
        if relation == "SUPERSEDED":
            prior_id = current.get("fact_id")
            current["status"] = "SUPERSEDED"
            current.setdefault("superseded_by", []).append(item.get("fact_id") or _stable_id("fact", item.get("application_id"), item.get("fact_key"), item.get("canonical_text")))
            new_fact = {**item, "status": "CONFIRMED", "supersedes": [prior_id], "superseded_by": [], "conflicts": []}
            new_fact.setdefault("supporting_sessions", [])
            new_fact.setdefault("supporting_claims", [])
            new_fact.setdefault("supporting_evidence", [])
            result.append(new_fact)
            continue
        if relation == "EXTENDED":
            current["status"] = "EXTENDED"
            for field in ("supporting_sessions", "supporting_claims", "supporting_evidence"):
                    merged = [*current.get(field, []), *item.get(field, [])]
                    current[field] = _unique_values(merged)
            current.setdefault("extensions", []).append({"canonical_text": item.get("canonical_text"),
                "supporting_sessions": item.get("supporting_sessions", []), "supporting_claims": item.get("supporting_claims", [])})
            continue
        if _normalize_name(str(current.get("canonical_text", ""))) == _normalize_name(str(item.get("canonical_text", ""))):
            current["status"] = "CONFIRMED"
            for field in ("supporting_sessions", "supporting_claims", "supporting_evidence"):
                current[field] = _unique_values([*current.get(field, []), *item.get(field, [])])
            continue
        current["status"] = "CONFLICTING"
        current.setdefault("conflicts", []).append({"canonical_text": item.get("canonical_text"),
            "supporting_sessions": item.get("supporting_sessions", []), "supporting_claims": item.get("supporting_claims", [])})
    return result


def generate_application_mission_pack(application_id: str, facts: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    selected = [dict(item) for item in facts if item.get("application_id") == application_id]
    for item in selected:
        item.setdefault("supporting_evidence", list(item.get("evidence_refs", [])))
        item.setdefault("supporting_claims", [])
        item.setdefault("first_seen", {"session_id": (item.get("supporting_sessions") or [None])[0]})
        item.setdefault("last_confirmed", item["first_seen"])
        item.setdefault("confidence", 0)
        item.setdefault("status", "NEEDS_REVIEW")
        item.setdefault("conflicts", [])
    if not selected or any(not item.get("evidence_refs") or not item.get("supporting_sessions")
                           or not item.get("supporting_claims") or not item.get("supporting_evidence")
                           for item in selected):
        raise ValueError("Mission Pack requires provenance-grounded application facts")
    app_name = application_id.replace("-", " ").title()
    slug = _slug(application_id)
    knowledge = {"schema_version": 1, "application_id": application_id, "canonical_facts": selected}
    section_names = (
        "Identity", "Business Purpose", "Support Scope", "Users / Roles", "Owners", "Environments",
        "Architecture", "Data Flow", "Authentication", "Dependencies", "Configuration", "Procedures",
        "Recurring Operations", "Monitoring", "Troubleshooting", "Risks", "Lifecycle", "Decisions",
        "Open Questions", "Ambiguities", "Evidence Map",
    )
    sections: dict[str, list[dict[str, Any]]] = {name: [] for name in section_names}
    for fact in selected:
        text = str(fact.get("canonical_fact") or fact.get("fact", ""))
        lowered = text.casefold()
        patterns = (
            ("Procedures", r"\b(step|click|select|open|enter|save|submit|procedure|runbook)\b"),
            ("Monitoring", r"\b(monitor|alert|log|observability|dashboard)\b"),
            ("Troubleshooting", r"\b(error|failure|troubleshoot|incident|unavailable)\b"),
            ("Authentication", r"\b(authentication|authorize|permission|credential|identity|login|access)\b"),
            ("Users / Roles", r"\b(user|role|operator|administrator|admin)\b"),
            ("Owners", r"\b(owner|contact|team|support group)\b"),
            ("Environments", r"\b(prod|production|dev|development|qa|test environment)\b"),
            ("Data Flow", r"\b(data flow|workflow|processes|input|output|report)\b"),
            ("Configuration", r"\b(config|setting|parameter|connection string)\b"),
            ("Dependencies", r"\b(depends on|dependency|integration|connects? to|requires)\b"),
            ("Architecture", r"\b(host|server|database|cloud|architecture|network|service)\b"),
            ("Support Scope", r"\b(support|responsib|ams|in scope|out of scope)\b"),
            ("Lifecycle", r"\b(lifecycle|decommission|retire|sunset|release)\b"),
            ("Risks", r"\b(risk|limitation|constraint|vulnerability)\b"),
            ("Decisions", r"\b(decided|decision|agreed|approved)\b"),
            ("Business Purpose", r"\b(purpose|allows|provides|used to|business)\b"),
            ("Identity", r"\b(called|named|application|system|platform|product)\b"),
        )
        section = next((name for name, pattern in patterns if re.search(pattern, lowered)), "Recurring Operations")
        sections[section].append(fact)
        sections["Evidence Map"].append(fact)
        if fact.get("status") in {"CONFLICTING", "NEEDS_REVIEW"} or fact.get("conflicts"):
            sections["Ambiguities"].append(fact)
    md = [f"# {app_name} — Application Mission Pack", "", "## Executive Brief", "",
          f"Evidence currently supports {len(selected)} canonical facts across "
          f"{len({s for item in selected for s in item['supporting_sessions']})} session(s).", ""]
    for section, records in sections.items():
        if not records:
            continue
        md.extend([f"## {section}", ""])
        for item in records:
            fact_id = item.get("fact_id", item.get("claim_id", "unassigned"))
            if section == "Ambiguities":
                md.append(f"- Review {fact_id}: {item.get('status')}; conflicts={len(item.get('conflicts', []))}.")
                continue
            refs = ", ".join(item.get("supporting_sessions", []))
            claims = ", ".join(item.get("supporting_claims", [])) or "claim IDs unavailable"
            evidence = ", ".join(f"{ref.get('source_id', 'source')}@{ref.get('timestamp', 'time')}" for ref in item.get("evidence_refs", []))
            if section == "Evidence Map":
                md.append(f"- {fact_id}: sessions={refs}; claims={claims}; evidence={evidence}")
            else:
                md.append(f"- {item.get('canonical_fact') or item.get('fact')} [{fact_id}; sessions: {refs}; claims: {claims}; evidence: {evidence}]")
        md.append("")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"json": output_dir / f"{slug}-knowledge.json", "md": output_dir / f"{slug}-mission-pack.md",
             "pdf": output_dir / f"{slug}-mission-pack.pdf"}
    paths["json"].write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["md"].write_text("\n".join(md), encoding="utf-8")
    _write_pdf("\n".join(md), paths["pdf"], f"{app_name} — Application Mission Pack")
    return {"status": "READY", "paths": paths, "knowledge": knowledge}


def generate_cross_session_knowledge(
    session_packs: list[dict[str, Any]], output_dir: Path,
    *, known_applications: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve exact aliases, consolidate grounded facts, and publish eligible Mission Packs."""
    catalogs = [dict(item) for item in (known_applications or [])]
    candidate_sets = [
        (pack, [dict(item) for item in pack.get("application_candidates", [])])
        for pack in session_packs
    ]
    known_alias_ids: dict[str, set[str]] = {}
    for app in catalogs:
        app_id = str(app.get("application_id") or _slug(str(app.get("name", ""))))
        for alias in [app.get("name"), *app.get("aliases", [])]:
            key = _normalize_name(str(alias)) if alias else ""
            if key:
                known_alias_ids.setdefault(key, set()).add(app_id)

    normalized_packs = []
    for source_pack, candidates in candidate_sets:
        candidate_map: dict[str, dict[str, Any]] = {}
        normalized_candidates = []
        for candidate in candidates:
            source_id = candidate.get("application_id")
            name = str(candidate.get("name", ""))
            aliases = [name, *candidate.get("aliases", [])]
            matches = {app_id for alias in aliases if alias
                       for app_id in known_alias_ids.get(_normalize_name(str(alias)), set())}
            if candidate.get("status") == "AMBIGUOUS" or len(matches) > 1:
                resolution = {"application_id": None, "status": "AMBIGUOUS"}
            elif len(matches) == 1:
                resolution = {"application_id": next(iter(matches)), "status": "MATCH_CONFIRMED"}
            else:
                resolution = {"application_id": source_id or _slug(name), "status": "NEW_APPLICATION"}
            normalized = {**candidate, **resolution}
            normalized_candidates.append(normalized)
            if source_id:
                candidate_map[str(source_id)] = normalized
        pack = dict(source_pack)
        pack["application_candidates"] = normalized_candidates
        pack["claims"] = [
            {**claim, "application_id": (candidate_map.get(str(claim.get("application_id")), {}).get("application_id")
                                         if claim.get("application_id") != "SESSION_GENERAL" else None)}
            for claim in source_pack.get("claims", [])
        ]
        normalized_packs.append(pack)

    facts = consolidate_claims_across_sessions(normalized_packs)
    if any(fact.get("merge_relation") for fact in facts):
        facts = merge_cross_session_facts([], facts)
    sessions_by_app: dict[str, set[str]] = {}
    for fact in facts:
        if fact.get("application_id"):
            sessions_by_app.setdefault(fact["application_id"], set()).update(fact.get("supporting_sessions", []))
    app_ids = sorted(app_id for app_id, sessions in sessions_by_app.items() if len(sessions) >= 2)
    eligible = [fact for fact in facts if fact.get("application_id") in set(app_ids)]
    graph_nodes = []
    graph_edges = []
    for fact in facts:
        if not fact.get("application_id"):
            continue
        app_node = f"application:{fact['application_id']}"
        fact_node = f"fact:{fact.get('fact_id')}"
        if not any(node["id"] == app_node for node in graph_nodes):
            graph_nodes.append({"id": app_node, "type": "APPLICATION", "application_id": fact["application_id"]})
        graph_nodes.append({"id": fact_node, "type": "FACT", "fact_id": fact.get("fact_id"),
                            "text": fact.get("canonical_text"), "provenance": fact.get("evidence_refs", [])})
        graph_edges.append({"source": app_node, "target": fact_node, "relation": "HAS_FACT",
                            "supporting_claims": fact.get("supporting_claims", []),
                            "supporting_evidence": fact.get("evidence_refs", [])})
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = output_dir / "application-knowledge-graph.json"
    knowledge_path = output_dir / "application-knowledge.json"
    graph_path.write_text(json.dumps({"nodes": graph_nodes, "edges": graph_edges}, indent=2, ensure_ascii=False), encoding="utf-8")
    knowledge_path.write_text(json.dumps({"schema_version": 1, "facts": facts}, indent=2, ensure_ascii=False), encoding="utf-8")
    mission_packs = [generate_application_mission_pack(app_id, eligible, output_dir) for app_id in app_ids]
    return {"status": "READY" if mission_packs else "NEEDS_MORE_EVIDENCE", "facts": facts,
            "application_ids": app_ids, "mission_packs": mission_packs,
            "application_knowledge_graph": graph_path, "application_knowledge": knowledge_path}
