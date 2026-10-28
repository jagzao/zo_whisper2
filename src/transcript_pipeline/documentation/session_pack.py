"""Generic evidence-grounded Session and Application Knowledge Pack pipeline."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
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
    "MANAGES", "STORES_IN", "NETWORK_PATH_CONTROL",
}
DIRECTED_RELATIONS = {"DATA_FLOW", "CALLS", "HOSTS", "USES", "MANAGES", "STORES_IN", "NETWORK_PATH_CONTROL"}
UNCERTAIN_STATES = {"SOURCE_UNCERTAIN", "NEEDS_REVIEW", "CONFLICTING"}
APPLICATION_STATES = {"MATCH_CONFIRMED", "MATCH_PROBABLE", "NEW_APPLICATION", "AMBIGUOUS"}


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
    return {"application_id": _slug(str(candidate["name"])), "status": "NEW_APPLICATION"}


def classify_ambiguity(text: str) -> list[str]:
    markers = ("maybe", "possibly", "i think", "not sure", "unclear", "could be", "might be")
    lowered = text.casefold()
    found = [marker for marker in markers if re.search(rf"\b{re.escape(marker)}\b", lowered)]
    if re.search(r"\b(?:sorry|correction|i mean|rather)\b", lowered):
        found.append("speaker_correction")
    if text.rstrip().endswith(("...", "—")):
        found.append("unfinished_statement")
    return found


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
    factual = re.compile(r"\b(is|are|has|have|uses|depends|runs|contains|supports|provides|allows|requires|stores|connects|means|could)\b", re.I)
    claims = []
    for segment in bundle.transcript_segments:
        text = re.sub(r"\s+", " ", str(segment.get("text", "")).strip())
        if len(text.split()) < 5 or not factual.search(text):
            continue
        uncertain = bool(classify_ambiguity(text))
        matches = {app_id for alias, app_id in aliases.items() if alias and alias in _normalize_name(text)}
        app_id = next(iter(matches)) if len(matches) == 1 else "SESSION_GENERAL"
        claim_id = _stable_id("claim", bundle.media_id, segment["segment_id"], text)
        claims.append({
            "claim_id": claim_id, "application_id": app_id, "claim": text,
            "source_type": "TRANSCRIPT", "source_id": bundle.media_id,
            "timestamp": segment["start"], "frame_id": None,
            "confidence": float(segment.get("confidence", 0.75 if not uncertain else 0.4)),
            "verification_state": "SOURCE_UNCERTAIN" if uncertain else "SOURCE_CONFIRMED",
            "first_seen": {"session_id": bundle.media_id, "timestamp": segment["start"]},
            "last_confirmed": None,
            "supporting_sources": [{"source_id": bundle.media_id, "source_type": "TRANSCRIPT",
                                     "timestamp": segment["start"], "segments": [segment]}],
            "conflicts": [], "ambiguities": classify_ambiguity(text),
        })
    return claims


def extract_diagram_graphs(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagrams = []
    for frame in frames:
        nodes = frame.get("nodes") or []
        edges = frame.get("edges") or []
        if not nodes or not edges:
            continue
        provenance = frame.get("provenance") or {"frame_id": frame.get("frame_id"), "timestamp": frame.get("timestamp"),
                                                   "image_path": frame.get("source_image")}
        if frame.get("ocr_status") == "LOW_CONFIDENCE" and not frame.get("review_state"):
            continue
        clean_edges = [edge for edge in edges if edge.get("relation_type") in DIAGRAM_RELATIONS
                       and edge.get("provenance", provenance).get("frame_id") == provenance.get("frame_id")]
        if clean_edges:
            diagrams.append({"diagram_id": _stable_id("diagram", provenance.get("frame_id")),
                              "nodes": nodes, "edges": clean_edges, "source_frames": [provenance]})
    return diagrams


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


def _markdown(pack: dict[str, Any]) -> str:
    lines = [f"# {pack['title']}", "", f"**State:** {pack['quality_state']}", "",
             "## Executive Brief", "", pack.get("executive_brief", "Evidence-derived recording notes."), ""]
    for application in pack.get("applications", []):
        lines.extend([f"## {application['name']}", ""])
        for section in application.get("sections", []):
            lines.extend([f"### {section['title']}", ""])
            lines.extend(f"- {claim['claim']} [{claim['claim_id']}]" for claim in section.get("claims", []))
            if not section.get("claims"):
                lines.append("NOT EVIDENCED")
            lines.append("")
    if pack.get("ambiguities"):
        lines.extend(["## Ambiguities / Needs Review", ""])
        lines.extend(f"- {item['claim']} — {item['source_id']} @ {item['timestamp']}" for item in pack["ambiguities"])
    if pack.get("diagrams"):
        lines.extend(["## Derived Diagrams", ""])
        lines.extend(f"- {item['diagram_id']} from {', '.join(frame['frame_id'] for frame in item['source_frames'])}" for item in pack["diagrams"])
    lines.extend(["", "## Evidence Timeline", ""])
    lines.extend(f"- {item['start']} {item.get('source_type')} {item['id']}" for item in pack["evidence_events"])
    return "\n".join(lines) + "\n"


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
            story.append(Paragraph(escape(line), styles["BodyText"]))
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
    procedures = extract_procedures(
        evidence.transcript_segments, media_id=evidence.media_id, application_id=procedure_app_id
    )
    valid_evidence_ids = {str(item.get("segment_id")) for item in evidence.transcript_segments}
    valid_evidence_ids.update(str(item.get("frame_id")) for item in evidence.frames)
    valid_evidence_ids.update(str(item.get("id")) for item in evidence.evidence_events)
    procedure_gate, procedure_errors = procedure_grounding(procedures, valid_evidence_ids)
    runbooks = build_runbooks(procedures, source_session=evidence.media_id)
    runbook_gate, runbook_errors = validate_runbooks(runbooks, valid_evidence_ids)
    frames_by_id = {frame["frame_id"]: frame for frame in evidence.frames}
    for frame in evidence.frames:
        if frame.get("ocr_status") == "LOW_CONFIDENCE":
            continue
        text = str(frame.get("ocr_text", "")).strip()
        if len(text.split()) < 3:
            continue
        frame_claim = {
            "claim_id": _stable_id("claim", evidence.media_id, frame["frame_id"], text),
            "application_id": frame.get("application_id", "SESSION_GENERAL"), "claim": text,
            "source_type": "VIDEO_FRAME", "source_id": evidence.media_id,
            "timestamp": frame["timestamp"], "frame_id": frame["frame_id"],
            "confidence": float(frame.get("ocr_confidence") or frame.get("confidence") or 0),
            "verification_state": "VISUAL_CONFIRMED", "first_seen": {"session_id": evidence.media_id, "timestamp": frame["timestamp"]},
            "last_confirmed": None, "supporting_sources": [{"source_id": evidence.media_id,
            "source_type": "VIDEO_FRAME", "timestamp": frame["timestamp"], "frame_id": frame["frame_id"],
            "ocr_text": text}], "conflicts": [],
        }
        claims.append(frame_claim)
    apps = []
    app_ids = {item.get("application_id") for item in applications if item.get("application_id")}
    for app_id in sorted(app_ids):
        app = next(item for item in applications if item.get("application_id") == app_id)
        app_claims = [item for item in claims if item.get("application_id") == app_id]
        publishable_claims = [item for item in app_claims if item.get("verification_state") not in UNCERTAIN_STATES]
        apps.append({"application_id": app_id, "name": app.get("name", app_id),
                     "sections": [{"title": "Evidence-derived knowledge", "claims": publishable_claims,
                                   "claim_ids": [item["claim_id"] for item in publishable_claims]}]})
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
    diagrams = extract_diagram_graphs(evidence.frames)
    event_ids = {str(item["id"]) for item in evidence.evidence_events}
    diagram_errors = validate_diagram_provenance(diagrams, {item["claim_id"] for item in claims}, frame_ids, event_ids)
    relation_errors = validate_diagram_relations(diagrams)
    semantic_topics = {
        str(frame["semantic_topic"]) for frame in evidence.frames
        if frame.get("semantic_topic") and frame.get("visual_type") not in {"BLACK_OR_EMPTY", "MEETING_GALLERY"}
    }
    selected_topics = {
        str(frame["semantic_topic"]) for frame in evidence.frames
        if frame.get("semantic_topic") and frame.get("selected", True) and _semantic_topic_sources(frame)
    }
    visual_gate = "PASS" if semantic_topics and semantic_topics <= selected_topics else "FAIL"
    transcript_state = evidence.speech_coverage.get("transcript_state", "NEEDS_REVIEW")
    speech_gate = evidence.speech_coverage.get("speech_quality_gate", "FAIL")
    material_claims = [item for item in claims if item.get("verification_state") not in UNCERTAIN_STATES]
    low_ratio = sum(float(item.get("confidence") or 0) < .5 for item in material_claims) / max(1, len(material_claims))
    gates = evaluate_session_pack_gates(
        transcript_state=transcript_state, speech_gate=speech_gate, visual_gate=visual_gate,
        claim_errors=claim_errors, diagram_errors=diagram_errors, application_ids=app_ids,
        low_confidence_ratio=low_ratio, procedures=procedures, application_errors=application_errors,
        source_map_errors=[], timeline_errors=validate_timeline_chronology(evidence.evidence_events),
        relation_errors=relation_errors, valid_evidence_ids=valid_evidence_ids,
    )
    ambiguous_apps = [item for item in applications if item.get("status") == "AMBIGUOUS"]
    gates["APPLICATION_RESOLUTION"] = "PASS" if app_ids - {"SESSION_GENERAL"} and not ambiguous_apps else "FAIL"
    gates["PROCEDURE_GROUNDING"] = procedure_gate
    gates["KAV_RUNBOOK_VALIDATION"] = runbook_gate
    gates["QUALITY_GATE"] = "PASS" if all(
        value in {"PASS", "NOT_APPLICABLE"} for key, value in gates.items() if key != "QUALITY_GATE"
    ) else "FAIL"
    gates["SECOND_BRAIN_READY"] = second_brain_ready(
        quality_gate=gates["QUALITY_GATE"], claim_provenance=gates["CLAIM_LEDGER"],
        application_resolution=gates["APPLICATION_RESOLUTION"], has_application=bool(app_ids - {"SESSION_GENERAL"}),
        conflicts_promoted=any(item.get("verification_state") == "CONFLICTING" for item in claims),
        package_policy="NOT_EVALUATED", raw_transcript_published=False, raw_media_published=False,
        procedure_gate=procedure_gate, runbook_gate=runbook_gate,
    )
    embedding_is_ready, embedding_chunks = embedding_ready([])
    gates["EMBEDDING_READY"] = "YES" if embedding_is_ready else "NO"
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
        "executive_brief": "Evidence-derived session knowledge; source support is recorded for each claim.",
        "applications": apps, "application_candidates": applications, "claims": claims,
        "ambiguities": [item for item in claims if item.get("verification_state") in UNCERTAIN_STATES]
        + [{"claim": f"Application identity unresolved for {item.get('name') or 'this session'}.",
            "source_id": evidence.media_id, "timestamp": None, "application_id": None,
            "verification_state": "NEEDS_REVIEW"} for item in applications if item.get("status") == "AMBIGUOUS"]
        + ([{"claim": "No named application candidate could be grounded from this recording.",
             "source_id": evidence.media_id, "timestamp": None, "application_id": None,
             "verification_state": "NEEDS_REVIEW"}] if not applications else []),
        "diagrams": diagrams, "visual_topics": evidence.visual_topics,
        "evidence_events": evidence.evidence_events, "transcript_quality": evidence.speech_coverage,
        "procedures": procedures,
        "procedure_errors": procedure_errors, "kav_runbook_errors": runbook_errors,
        "embedding_inputs": embedding_chunks,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    kav_path = output_dir / "KAV_EXECUTION_RUNBOOKS.json"
    kav_path.write_text(json.dumps({"schema_version": 1, "runbooks": runbooks},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    if quality_state != "READY":
        diagnostic_path = output_dir / f"{basename}-diagnostic.json"
        diagnostic_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"status": quality_state, "gates": gates, "diagnostic": diagnostic_path,
                "kav_runbooks": kav_path, "pack": pack}
    markdown = _markdown(pack)
    paths = {"json": output_dir / f"{basename}.json", "md": output_dir / f"{basename}.md",
             "pdf": output_dir / f"{basename}.pdf", "kav_runbooks": kav_path}
    paths["json"].write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["md"].write_text(markdown, encoding="utf-8")
    _write_pdf(markdown, paths["pdf"], title)
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
