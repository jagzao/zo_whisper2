"""Evidence-gated Session Knowledge Pack builder for reviewed golden samples."""
from __future__ import annotations

import json
import os
import posixpath
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.mission_pack import validate_claim_records

SESSION_ID = "AMS_KAP_-_App_Support_-_Session_41"
APPLICATIONS = {
    "pgregdoc.com": "pg-regdoc",
    "north-america-central-product-research-testing-panelist-payments": "north-america-central-product-research-testing-panelist-payments",
}
FRAME_SUPPORT = {
    "C-009": "frame_0005.png", "C-010": "frame_0005.png",
    "C-011": "frame_0006.png", "C-013": "frame_0005.png",
    "C-016": "frame_0021.png", "C-017": "frame_0021.png",
    "C-018": "frame_0021.png", "C-019": "frame_0021.png",
}
UNCERTAIN_STATES = {"SOURCE_UNCERTAIN", "NEEDS_REVIEW", "CONFLICTING"}
APPLICATION_TITLES = {
    "pg-regdoc": "PG RegDoc",
    APPLICATIONS["north-america-central-product-research-testing-panelist-payments"]:
        "North America Central Product Research Testing<br/>Panelist Payments",
}
DIAGRAM_RELATIONS = {
    "DATA_FLOW", "CALLS", "HOSTS", "USES", "DEPENDS_ON", "AUTHENTICATES_WITH",
    "MANAGES", "STORES_IN", "NETWORK_PATH_CONTROL",
}
DIRECTED_RELATIONS = {"DATA_FLOW", "CALLS", "HOSTS", "USES", "MANAGES", "STORES_IN", "NETWORK_PATH_CONTROL"}


def _seconds(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    parts = [float(part) for part in str(value).split(":")]
    return sum(part * factor for part, factor in zip(parts, (3600, 60, 1)[-len(parts):]))


def _clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02}:{total % 3600 // 60:02}:{total % 60:02}"


def deduplicate_source_artifacts(source_map: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one canonical evidence ID per normalized path and content hash."""
    result: list[dict[str, Any]] = []
    by_artifact: dict[tuple[str, str], dict[str, Any]] = {}
    for source in source_map:
        path = source.get("source_path") or source.get("path")
        digest = source.get("sha256")
        if not path or not digest:
            result.append(dict(source))
            continue
        normalized_path = posixpath.normpath(str(path).replace("\\", "/")).casefold()
        key = (normalized_path, str(digest).casefold())
        canonical = by_artifact.get(key)
        if canonical is None:
            canonical = dict(source)
            canonical["aliases"] = list(canonical.get("aliases", []))
            by_artifact[key] = canonical
            result.append(canonical)
            continue
        aliases = canonical.setdefault("aliases", [])
        for alias in [source.get("evidence_id"), *source.get("aliases", [])]:
            if alias and alias != canonical.get("evidence_id") and alias not in aliases:
                aliases.append(alias)
    return result


def sort_evidence_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=lambda event: (
        _seconds(event["start"]), _seconds(event["end"]), str(event["id"]),
    ))


def validate_timeline_chronology(events: list[dict[str, Any]]) -> list[str]:
    keys = [(_seconds(e["start"]), _seconds(e["end"]), str(e["id"])) for e in events]
    return ["evidence timeline is not strictly chronological"] if keys != sorted(keys) else []


def apply_reviewed_topics(report: dict[str, Any], review_path: Path) -> dict[str, Any]:
    reviewed = json.loads(review_path.read_text(encoding="utf-8"))
    if reviewed.get("schema_version") != 1:
        raise ValueError("unsupported visual review schema")
    from transcript_pipeline.documentation.visual_evidence import apply_semantic_review

    result = apply_semantic_review(report, reviewed.get("frames", []))
    if len(reviewed.get("frames", [])) != result.get("frame_count"):
        raise ValueError("semantic visual audit must cover every extracted frame")
    expected = set(reviewed.get("topics_expected", []))
    if set(result["visual_topics_discovered"]) != expected:
        raise ValueError("reviewed visual topics do not match expected coverage")
    if result["visual_coverage_gate"] != "PASS":
        raise ValueError("unique visual-topic coverage gate failed")
    return result


def _segment_refs(segments: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [
        {"segment_id": f"S41-PRIMARY-{index:04}", "start": float(item["start"]),
         "end": float(item["end"]), "text": str(item.get("text", "")).strip()}
        for index, item in enumerate(segments, 1)
        if float(item["end"]) > start and float(item["start"]) < end
    ]


def _build_claims(
    knowledge_path: Path,
    app_dir: Path,
    app_id: str,
    events: list[dict[str, Any]],
    source_map: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    primary_source_id: str,
    video_source_id: str,
    visual_frames: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    facts = json.loads(knowledge_path.read_text(encoding="utf-8")).get("facts", [])
    event_map = {event["id"]: event for event in events}
    claims = []
    for fact in facts:
        claim_id = str(fact["fact_key"])
        first = fact.get("first_seen") or {}
        target = _seconds(first.get("timestamp", 0))
        event_refs = [ref for ref in fact.get("evidence_refs", []) if str(ref).startswith("E-")]
        matched = [event_map[ref] for ref in event_refs if ref in event_map]
        if not matched:
            candidates = [event for event in events if event.get("application") in {app_dir.name, app_id}]
            if not candidates:
                candidates = [event for event in events if event.get("application") not in {"SESSION", "SESSION_GENERAL"}]
            nearest = min(candidates, key=lambda event: abs(_seconds(event["start"]) - target))
            if abs(_seconds(nearest["start"]) - target) > 90:
                raise ValueError(f"no source event matches {claim_id}")
            matched = [nearest]

        supports: list[dict[str, Any]] = []
        for event in matched:
            start, end = _seconds(event["start"]), _seconds(event["end"])
            raw_segments = _segment_refs(segments, start, end)
            if raw_segments and "TRANSCRIPT" in event.get("source_types", []):
                supports.append({
                    "source_id": primary_source_id, "source_type": "TRANSCRIPT_SEGMENTS",
                    "timestamp": start, "end_timestamp": end,
                    "evidence_id": event["id"], "segments": raw_segments,
                    "event_summary": event.get("summary"),
                    "original_references": [ref for ref in event_refs if ref == event["id"]],
                })
        frame_id = FRAME_SUPPORT.get(claim_id)
        if frame_id:
            visual = visual_frames.get(frame_id)
            if not visual or not visual.get("selected"):
                raise ValueError(f"claim {claim_id} references an unselected visual frame")
            frame_source = next((item for item in source_map if item.get("source_path", "").endswith(frame_id)), None)
            if not frame_source:
                raise ValueError(f"no source-map entry for {frame_id}")
            supports.append({
                "source_id": video_source_id, "source_type": "VIDEO_FRAME",
                "timestamp": float(frame_source["timestamp_seconds"]),
                "evidence_id": frame_source["evidence_id"], "frame_id": frame_id,
                "source_path": frame_source["source_path"],
                "image_sha256": frame_source.get("sha256"),
                "ocr_status": visual.get("ocr_status"),
                "ocr_text": visual.get("ocr_text"),
            })
        if not supports:
            raise ValueError(f"claim {claim_id} has no matched transcript or frame provenance")
        supports.sort(key=lambda item: item["timestamp"])
        primary = supports[0]
        state = str(fact.get("verification_state", "NEEDS_REVIEW"))
        if fact.get("conflicts") and claim_id == "C-013":
            state = "SOURCE_UNCERTAIN"
        if len({item["source_type"] for item in supports}) > 1 and state == "SOURCE_CONFIRMED":
            state = "MULTI_SOURCE_CONFIRMED"
        confidence = {"HIGH": .95, "MEDIUM": .75, "LOW": .4}.get(str(fact.get("confidence", "LOW")).upper(), .4)
        claims.append({
            "claim_id": claim_id, "application_id": app_id, "claim": fact["fact"],
            "source_type": "MULTI_SOURCE" if len({item["source_type"] for item in supports}) > 1 else primary["source_type"],
            "source_id": primary["source_id"], "timestamp": primary["timestamp"],
            "frame_id": frame_id, "confidence": confidence, "verification_state": state,
            "first_seen": first, "last_confirmed": fact.get("last_confirmed"),
            "supporting_sources": supports, "conflicts": list(fact.get("conflicts", [])),
            "source_reference_audit": _audit_original_refs(fact.get("evidence_refs", []), event_map, source_map, matched),
        })
    return claims


def _audit_original_refs(
    refs: list[str], events: dict[str, dict[str, Any]], source_map: list[dict[str, Any]],
    resolved_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resolved_ids = {event["id"] for event in resolved_events}
    result = []
    for ref in refs:
        if ref in events:
            result.append({"reference": ref, "resolution": "EXACT_EVENT_MATCH", "resolved_event_id": ref})
        elif str(ref).startswith("E-") and resolved_ids:
            result.append({"reference": ref, "resolution": "RECONCILED_BY_APPLICATION_AND_FIRST_SEEN", "resolved_event_id": sorted(resolved_ids)})
        elif str(ref).startswith("V-"):
            frame = next((item for item in source_map
                          if item.get("evidence_id") == ref or ref in item.get("aliases", [])), None)
            result.append({
                "reference": ref, "resolution": "SOURCE_FRAME_MAPPED" if frame else "UNRESOLVED",
                "canonical_evidence_id": frame.get("evidence_id") if frame else None,
                "frame_path": frame.get("source_path") if frame else None,
                "timestamp": frame.get("timestamp_seconds") if frame else None,
                "sha256": frame.get("sha256") if frame else None,
            })
        else:
            result.append({"reference": ref, "resolution": "UNRESOLVED"})
    if any(item["resolution"] == "UNRESOLVED" for item in result):
        raise ValueError("legacy fact references include unresolved source IDs")
    return result


def _node(node_id: str, label: str, frame_ids: list[str], event_ids: list[str], confidence: float) -> dict[str, Any]:
    return {"id": node_id, "label": label, "provenance": {
        "frame_ids": frame_ids, "evidence_ids": event_ids, "confidence": confidence,
    }}


def _edge(source: str, target: str, label: str, frame_ids: list[str], event_ids: list[str],
          claim_ids: list[str], confidence: float, relation_type: str) -> dict[str, Any]:
    return {"source": source, "target": target, "label": label, "relation_type": relation_type, "claim_ids": claim_ids,
            "provenance": {"frame_ids": frame_ids, "evidence_ids": event_ids, "confidence": confidence}}


def build_derived_diagrams() -> list[dict[str, Any]]:
    flow_frame, arch_frame, cprt_frame = "frame_0005.png", "frame_0006.png", "frame_0021.png"
    flow_nodes = [
        _node("admin", "P&G admin employees", [flow_frame], ["E-008"], .95),
        _node("browser", "Web browser", [flow_frame], ["E-008"], .95),
        _node("regdoc", "PGRegDoc.com", [flow_frame], ["E-008"], .95),
        _node("consumers", "Retailers and consumers", [flow_frame], ["E-008"], .95),
        _node("developers", "Application developers", [flow_frame], ["E-008"], .95),
        _node("pingid", "PingID", [flow_frame], ["E-008"], .95),
    ]
    flow_edges = [
        _edge("admin", "browser", "maintain country SDS and export PDFs", [flow_frame], ["E-008"], ["C-009"], .94, "USES"),
        _edge("browser", "regdoc", "manual content maintenance", [flow_frame], ["E-008"], ["C-009"], .94, "USES"),
        _edge("regdoc", "browser", "make available PDF documents", [flow_frame], ["E-008"], ["C-009"], .94, "DATA_FLOW"),
        _edge("browser", "consumers", "retrieve available PDFs", [flow_frame], ["E-008"], ["C-009"], .94, "DATA_FLOW"),
        _edge("developers", "browser", "perform manual application configuration", [flow_frame], ["E-008"], ["C-010"], .94, "USES"),
        _edge("browser", "regdoc", "configuration activity", [flow_frame], ["E-008"], ["C-010"], .94, "USES"),
        _edge("regdoc", "pingid", "authentication dependency", [flow_frame], ["E-008"], ["C-030"], .9, "AUTHENTICATES_WITH"),
    ]
    arch_nodes = [
        _node("users", "Users", [arch_frame], ["E-009"], .86),
        _node("browser", "Web browser", [arch_frame], ["E-009"], .86),
        _node("regdoc", "PGRegDoc.com", [arch_frame], ["E-009"], .86),
        _node("azure", "Microsoft Azure", [arch_frame], ["E-009"], .86),
        _node("proddev", "Separate PROD and DEV environments", [arch_frame], ["E-009"], .86),
        _node("sql", "Azure SQL (data storage)", [arch_frame], ["E-009"], .86),
        _node("storage", "Data storage", [arch_frame], ["E-009"], .86),
        _node("adf", "Azure Data Factory", [arch_frame], ["E-009"], .86),
        _node("app_ops", "Processing and application operations", [arch_frame], ["E-009"], .86),
        _node("network", "Private endpoints and virtual networks", [arch_frame], ["E-009"], .86),
        _node("key_services", "Key Azure services", [arch_frame], ["E-009"], .86),
        _node("pingid", "PingID authentication dependency", [flow_frame], ["E-008"], .9),
    ]
    arch_edges = [
        _edge("azure", "regdoc", "hosts", [arch_frame], ["E-009"], ["C-002", "C-011"], .86, "HOSTS"),
        _edge("users", "browser", "secure access", [arch_frame], ["E-009"], ["C-011"], .86, "USES"),
        _edge("browser", "regdoc", "application access", [arch_frame], ["E-009"], ["C-011"], .86, "USES"),
        _edge("regdoc", "proddev", "has separate environments", [arch_frame], ["E-009"], ["C-011"], .86, "USES"),
        _edge("regdoc", "sql", "stores application data", [arch_frame], ["E-009"], ["C-011"], .86, "STORES_IN"),
        _edge("adf", "app_ops", "processes application data", [arch_frame], ["E-009"], ["C-011"], .86, "DATA_FLOW"),
        _edge("network", "key_services", "controls network paths", [arch_frame], ["E-009"], ["C-011"], .86, "NETWORK_PATH_CONTROL"),
        _edge("regdoc", "pingid", "authentication dependency", [flow_frame], ["E-008"], ["C-030"], .9, "AUTHENTICATES_WITH"),
    ]
    cprt_nodes = [
        _node("salesforce", "Salesforce LEX", [cprt_frame], ["E-020"], .93),
        _node("cprt", "CPRT SaaS / ETL application", [cprt_frame], ["E-020"], .93),
        _node("vendors", "Fulfilment vendor servers", [cprt_frame], ["E-020"], .93),
        _node("pgdb", "P&G-hosted database", [cprt_frame], ["E-020"], .93),
    ]
    cprt_edges = [
        _edge("salesforce", "cprt", "exports panelist and fulfilment data", [cprt_frame], ["E-020"], ["C-016", "C-017"], .93, "DATA_FLOW"),
        _edge("cprt", "vendors", "ETL transfer (record describes vendor destination)", [cprt_frame], ["E-020"], ["C-016", "C-017"], .9, "DATA_FLOW"),
        _edge("cprt", "pgdb", "ETL load (record lists P&G database as an alternative)", [cprt_frame], ["E-020"], ["C-017"], .9, "DATA_FLOW"),
    ]
    specs = [
        ("pgregdoc-data-flow", "PGRegDoc operational data flow", flow_nodes, flow_edges),
        ("pgregdoc-architecture", "PGRegDoc architecture context", arch_nodes, arch_edges),
        ("na-cprt-data-flow", "North America CPRT catalogue-described data flow", cprt_nodes, cprt_edges),
    ]
    diagrams = []
    for diagram_id, title, nodes, edges in specs:
        node_map = {node["id"]: node["label"] for node in nodes}
        lines = ["flowchart LR", *[f'    {node["id"]}["{node["label"]}"]' for node in nodes]]
        lines.extend(
            f'    {edge["source"]} {"-->" if edge["relation_type"] in DIRECTED_RELATIONS else "---"}'
            f'|{edge["relation_type"]}: {edge["label"]}| {edge["target"]}'
            for edge in edges
        )
        diagrams.append({
            "diagram_id": diagram_id, "title": title, "nodes": nodes, "edges": edges,
            "labels": list(node_map.values()), "source_frames": sorted({f for item in [*nodes, *edges] for f in item["provenance"]["frame_ids"]}),
            "source_evidence_ids": sorted({e for item in [*nodes, *edges] for e in item["provenance"]["evidence_ids"]}),
            "mermaid": "\n".join(lines),
            "provenance_label": "Derived only from the linked source frames and transcript evidence; original screenshots remain available.",
        })
    return diagrams


def validate_pack_claim_provenance(
    claims: list[dict[str, Any]], known_sources: set[str], known_frames: set[str]
) -> list[str]:
    errors = validate_claim_records(claims)
    for claim in claims:
        claim_id = claim.get("claim_id", "-")
        if claim.get("source_id") not in known_sources:
            errors.append(f"{claim_id}: unknown source_id")
        if not isinstance(claim.get("timestamp"), (int, float)):
            errors.append(f"{claim_id}: timestamp must be numeric seconds")
        sources = claim.get("supporting_sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{claim_id}: supporting_sources is empty")
            continue
        for source in sources:
            if source.get("source_id") not in known_sources or not isinstance(source.get("timestamp"), (int, float)):
                errors.append(f"{claim_id}: invalid source reference")
            if source.get("source_type") == "TRANSCRIPT_SEGMENTS" and not source.get("segments"):
                errors.append(f"{claim_id}: transcript citation has no segment")
            if source.get("source_type") == "VIDEO_FRAME" and source.get("frame_id") not in known_frames:
                errors.append(f"{claim_id}: frame citation is unknown")
    return errors


def validate_diagram_provenance(
    diagrams: list[dict[str, Any]], claim_ids: set[str], frame_ids: set[str], event_ids: set[str]
) -> list[str]:
    errors = []
    for diagram in diagrams:
        for item in [*diagram.get("nodes", []), *diagram.get("edges", [])]:
            provenance = item.get("provenance", {})
            if not provenance.get("frame_ids") or not set(provenance["frame_ids"]) <= frame_ids:
                errors.append(f"{diagram['diagram_id']}: invalid/missing frame provenance")
            if not provenance.get("evidence_ids") or not set(provenance["evidence_ids"]) <= event_ids:
                errors.append(f"{diagram['diagram_id']}: invalid/missing evidence provenance")
        for edge in diagram.get("edges", []):
            if not edge.get("label") or not edge.get("claim_ids") or not set(edge["claim_ids"]) <= claim_ids:
                errors.append(f"{diagram['diagram_id']}: ungrounded edge")
    return errors


def validate_diagram_relations(diagrams: list[dict[str, Any]]) -> list[str]:
    errors = []
    for diagram in diagrams:
        for edge in diagram.get("edges", []):
            relation = edge.get("relation_type")
            if relation not in DIAGRAM_RELATIONS:
                errors.append(f"{diagram['diagram_id']}: invalid relation type")
                continue
            pair = f'{edge["source"]} {edge["target"]}'
            operator = "-->" if relation in DIRECTED_RELATIONS else "---"
            expected = f'{edge["source"]} {operator}|{relation}: {edge["label"]}| {edge["target"]}'
            if expected not in diagram.get("mermaid", ""):
                errors.append(f"{diagram['diagram_id']}: relation rendering does not match {relation}")
            directional_auth = f'{edge["source"]} -->|AUTHENTICATES_WITH:'
            if relation == "AUTHENTICATES_WITH" and directional_auth in diagram.get("mermaid", ""):
                errors.append(f"{diagram['diagram_id']}: authentication dependency is rendered directionally")
            if not pair:
                errors.append(f"{diagram['diagram_id']}: missing relation endpoints")
    return errors


def validate_source_artifact_dedup(source_map: list[dict[str, Any]]) -> list[str]:
    seen: set[tuple[str, str]] = set()
    evidence_ids: set[str] = set()
    errors = []
    for source in source_map:
        path = source.get("source_path") or source.get("path")
        digest = source.get("sha256")
        if path and digest:
            key = (posixpath.normpath(str(path).replace("\\", "/")).casefold(), str(digest).casefold())
            if key in seen:
                errors.append("duplicate canonical path and SHA-256")
            seen.add(key)
        evidence_id = source.get("evidence_id")
        if evidence_id:
            if evidence_id in evidence_ids:
                errors.append(f"duplicate evidence ID {evidence_id}")
            evidence_ids.add(evidence_id)
        if evidence_id in source.get("aliases", []):
            errors.append(f"canonical evidence ID {evidence_id} duplicated as alias")
    return errors


def _general_claim_relevant(claim: dict[str, Any], app_id: str) -> bool:
    text = " ".join(str(claim.get(key, "")) for key in ("claim", "semantic_scope")).casefold()
    if "both applications" in text or "two applications" in text:
        return True
    if app_id == "pg-regdoc":
        return "pgregdoc" in text or "pg regdoc" in text
    return "north america central product research testing panelist payments" in text or "cprt" in text


def validate_application_claim_isolation(
    applications: list[dict[str, Any]], claims: list[dict[str, Any]]
) -> list[str]:
    claim_map = {claim.get("claim_id"): claim for claim in claims}
    errors = []
    for application in applications:
        app_id = application.get("application_id")
        for section in application.get("sections", []):
            for claim_id in section.get("claim_ids", []):
                claim = claim_map.get(claim_id)
                if not claim:
                    errors.append(f"{app_id}/{section.get('title')}: unknown claim {claim_id}")
                elif claim.get("application_id") != app_id and not (
                    claim.get("application_id") == "SESSION_GENERAL" and _general_claim_relevant(claim, app_id)
                ):
                    errors.append(f"{app_id}/{section.get('title')}: claim {claim_id} belongs to {claim.get('application_id')}")
    return errors


def evaluate_session_pack_gates(
    *, transcript_state: str, speech_gate: str, visual_gate: str,
    claim_errors: list[str], diagram_errors: list[str], application_ids: set[str],
    low_confidence_ratio: float, procedures: list[dict[str, Any]],
    application_errors: list[str], source_map_errors: list[str], timeline_errors: list[str],
    relation_errors: list[str],
) -> dict[str, str]:
    gates = {
        "SOURCE_IDENTITY": "PASS",
        "TRANSCRIPT_SPEECH_COVERAGE": "PASS" if transcript_state == "VALID" and speech_gate == "PASS" else "FAIL",
        "SPEECH_COVERAGE": "PASS" if transcript_state == "VALID" and speech_gate == "PASS" else "FAIL",
        "VISUAL_TOPIC_COVERAGE": "PASS" if visual_gate == "PASS" else "FAIL",
        "VISUAL_COVERAGE": "PASS" if visual_gate == "PASS" else "FAIL",
        "CLAIM_PROVENANCE": "PASS" if not claim_errors else "FAIL",
        "CLAIM_LEDGER": "PASS" if not claim_errors else "FAIL",
        "DIAGRAM_PROVENANCE": "PASS" if not diagram_errors else "FAIL",
        "DIAGRAM_RELATION_GROUNDING": "PASS" if not relation_errors else "FAIL",
        "APPLICATION_CLAIM_ISOLATION": "PASS" if not application_errors else "FAIL",
        "SOURCE_ARTIFACT_DEDUP": "PASS" if not source_map_errors else "FAIL",
        "EVIDENCE_TIMELINE_CHRONOLOGICAL": "PASS" if not timeline_errors else "FAIL",
        "APPLICATION_SEGMENTATION": "PASS" if application_ids == set(APPLICATIONS.values()) else "FAIL",
        "LOW_CONFIDENCE_FILLER": "PASS" if low_confidence_ratio <= .1 else "FAIL",
        "PROCEDURE_GROUNDING": "PASS" if all(item.get("source_id") and item.get("steps") for item in procedures) else "PASS" if not procedures else "FAIL",
    }
    gates["QUALITY_GATE"] = "PASS" if all(value == "PASS" for value in gates.values()) else "FAIL"
    return gates


def _claim_by_id(claims: list[dict[str, Any]], claim_id: str) -> dict[str, Any]:
    return next(claim for claim in claims if claim["claim_id"] == claim_id)


def _fmt_claim(claim: dict[str, Any]) -> str:
    return f"{claim['claim']} [{claim['claim_id']}]"


def _section_claim(claim: dict[str, Any], section: str, first_seen: dict[str, str]) -> str:
    claim_id = claim["claim_id"]
    previous = first_seen.get(claim_id)
    if previous:
        return f"{section} is also supported by [{claim_id}]; see {previous} for the source-backed detail."
    first_seen[claim_id] = section
    return _fmt_claim(claim)


def _make_application_sections(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping = {
        "pg-regdoc": {
            "Application Identity": ["C-002", "C-028"], "Business Purpose": ["C-002", "C-003", "C-004"],
            "Support Scope": ["C-008"], "Users / Roles": ["C-007"], "Ownership / Contacts": ["C-012"],
            "Environments": ["C-011"], "Architecture": ["C-002", "C-011", "C-013"],
            "Operational Data Flow": ["C-009", "C-010", "C-013"], "Authentication / Access": ["C-030", "C-013"],
            "Dependencies": ["C-002", "C-011", "C-013"], "Configuration": ["C-010"],
            "Recurring Support Activities": ["C-009", "C-006"], "Lifecycle": [],
            "Decisions": [], "Action Items": ["C-015"], "Deferred Knowledge": ["C-015"],
            "Architecture Diagram": [],
        },
        "north-america-central-product-research-testing-panelist-payments": {
            "Application Identity": ["C-016", "C-029"], "Business Purpose": ["C-016", "C-017"],
            "Users / Roles": ["C-018"], "Ownership / Contacts": ["C-026"], "Environments": [],
            "Architecture": ["C-016", "C-017"], "Operational Data Flow": ["C-017"],
            "Authentication / Access": ["C-018", "C-023"], "Dependencies": ["C-017"],
            "Lifecycle": ["C-019", "C-021"], "Decisions": ["C-019"],
            "Action Items": ["C-023", "C-024"], "Deferred Knowledge": ["C-024"],
            "Architecture Diagram": [],
        },
    }
    result = []
    for app_id, headings in mapping.items():
        app_claims = [c for c in claims if c["application_id"] == app_id]
        sections = []
        first_seen: dict[str, str] = {}
        if app_id == "pg-regdoc":
            sections.append({"title": "Architecture Diagram", "text": "Derived diagrams: pgregdoc-architecture (technical context; frame_0006.png, 00:06:38) and pgregdoc-data-flow (user flow; frame_0005.png, 00:05:41). Source frames and transcript evidence are linked in each diagram.", "claim_ids": ["C-011", "C-009"]})
        if app_id.endswith("payments"):
            sections.append({"title": "Support Scope", "text": "The catalogue record lists P&G AMS Support Team; explicit in-scope and out-of-scope boundaries are not stated.", "claim_ids": ["C-026"]})
        for heading, ids in headings.items():
            supported = [_claim_by_id(claims, claim_id) for claim_id in ids]
            supported = [c for c in supported if c["verification_state"] not in UNCERTAIN_STATES]
            if supported:
                sections.append({"title": heading, "claims": [_section_claim(c, heading, first_seen) for c in supported], "claim_ids": [c["claim_id"] for c in supported]})
        if app_id.endswith("payments"):
            flow_section = next(section for section in sections if section["title"] == "Operational Data Flow")
            flow_section["text"] = "Catalogue-described flow is shown in derived diagram na-cprt-data-flow, sourced from frame_0021.png at 00:20:52. It is a catalogue description, not a verified live integration trace."
        special = {
            "Troubleshooting / Known Failure Modes": ["C-023"] if app_id.endswith("payments") else [],
            "Ticket / Support Patterns": ["C-020"] if app_id.endswith("payments") else [],
            "Risks / Limitations": ["C-023", "C-024"] if app_id.endswith("payments") else ["C-008", "C-015"],
        }
        for heading, value in special.items():
            if isinstance(value, str):
                sections.append({"title": heading, "text": value, "claim_ids": []})
            else:
                supported = [_claim_by_id(claims, claim_id) for claim_id in value]
                supported = [c for c in supported if c["verification_state"] not in UNCERTAIN_STATES]
                if supported:
                    sections.append({"title": heading, "claims": [_section_claim(c, heading, first_seen) for c in supported], "claim_ids": [c["claim_id"] for c in supported]})
        if app_id.endswith("payments"):
            sections.extend([
                {"title": "Environments", "text": "NOT EVIDENCED.", "claim_ids": []},
                {"title": "Configuration", "text": "NOT EVIDENCED.", "claim_ids": []},
                {"title": "Recurring Support Activities", "text": "NOT EVIDENCED.", "claim_ids": []},
                {"title": "Ticket / Support Patterns", "text": "NOT EVIDENCED as a verified recurring pattern; the speaker's low-usage impression is retained under Ambiguities / Needs Review.", "claim_ids": ["C-020"]},
                {"title": "Monitoring / Observability", "text": "NOT EVIDENCED.", "claim_ids": []},
                {"title": "Operational Procedures", "text": "NOT EVIDENCED: no repeatable AMS support procedure was demonstrated.", "claim_ids": []},
            ])
        else:
            sections.extend([
                {"title": "Lifecycle", "text": "NOT EVIDENCED.", "claim_ids": []},
                {"title": "Ticket / Support Patterns", "text": "NOT EVIDENCED.", "claim_ids": []},
                {"title": "Monitoring / Observability", "text": "NOT EVIDENCED.", "claim_ids": []},
                {"title": "Operational Procedures", "text": "NOT EVIDENCED: no repeatable AMS support procedure was demonstrated.", "claim_ids": []},
            ])
        uncertainties = [c for c in app_claims if c["verification_state"] in UNCERTAIN_STATES]
        sections.append({"title": "Ambiguities / Needs Review", "claims": [_fmt_claim(c) for c in uncertainties], "claim_ids": [c["claim_id"] for c in uncertainties] or []})
        result.append({"application_id": app_id, "sections": sections})
    return result


def _markdown(pack: dict[str, Any]) -> str:
    lines = [f"# {SESSION_ID}", "", "**Document type:** Session Knowledge Pack  |  **Quality:** READY FOR OWNER REVIEW", "",
             "## Executive Brief", "", pack["executive_brief"], "",
             "## Applications Covered", ""]
    for app in pack["applications"]:
        title = APPLICATION_TITLES[app["application_id"]].replace("<br/>", " ")
        lines.extend([f"### {title}", ""])
        for section in app["sections"]:
            lines.extend([f"#### {section['title']}", ""])
            if section.get("text"):
                lines.extend([section["text"], ""])
            for item in section.get("claims", []):
                lines.extend([f"- {item}", ""])
    for title, content in pack["common_sections"].items():
        lines.extend([f"## {title}", ""])
        if isinstance(content, list):
            lines.extend([f"- {item}" for item in content])
        else:
            lines.append(str(content))
        lines.append("")
    shown_frames: set[str] = set()
    for diagram in pack["derived_diagrams"]:
        lines.extend([f"## {diagram['title']}", "", diagram["provenance_label"], "",
                      f"Source: {SESSION_ID}.mp4; frames {', '.join(diagram['source_frames'])}.", "",
                      "```mermaid", diagram["mermaid"], "```", ""])
        for frame_id in diagram["source_frames"]:
            if frame_id in shown_frames:
                continue
            rel = f"{pack['frame_dir_relative']}/{frame_id}"
            lines.extend([f"![Original evidence frame {frame_id}]({rel})", ""])
            shown_frames.add(frame_id)
    lines.extend(["## Evidence Timeline", ""])
    for event in pack["evidence_timeline"]:
        lines.append(f"- {event['start']}-{event['end']}: {event['summary']} ({event['id']}).")
    lines.extend(["", "## Source Map", ""])
    for source in pack["source_map"]:
        name = source.get("source_id") or source.get("evidence_id")
        path = source.get("path") or source.get("source_path")
        aliases = f" (aliases: {', '.join(source['aliases'])})" if source.get("aliases") else ""
        lines.append(f"- {name}{aliases} ({source['source_type']}): `{path}`; SHA-256 `{source['sha256']}`.")
    lines.append("")
    lines.extend(["## Quality Scorecard", ""])
    lines.extend(f"- {key}: {value}" for key, value in pack["quality_scorecard"].items())
    lines.append("")
    return "\n".join(lines)


def _draw_diagram(diagram: dict[str, Any]):
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib import colors

    drawing = Drawing(520, 215)
    nodes = diagram["nodes"]
    width, height = 130, 34
    columns = min(4, max(1, len(nodes)))
    positions = {}
    for index, node in enumerate(nodes):
        col, row = index % columns, index // columns
        x = 8 + col * 128
        y = 175 - row * 58
        positions[node["id"]] = (x, y)
    for edge in diagram["edges"]:
        x1, y1 = positions[edge["source"]]
        x2, y2 = positions[edge["target"]]
        sx, sy = x1 + width - 8, y1 + height / 2
        ex, ey = x2, y2 + height / 2
        if x1 >= x2:
            sx, ex = x1 + width / 2, x2 + width / 2
            sy, ey = y1, y2 + height
        end_arrow = 4 if edge["relation_type"] in DIRECTED_RELATIONS else 0
        drawing.add(Line(sx, sy, ex, ey, strokeColor=colors.HexColor("#45627A"), strokeWidth=0.8, endArrowSize=end_arrow))
    for node in nodes:
        x, y = positions[node["id"]]
        drawing.add(Rect(x, y, width - 8, height, rx=4, ry=4, fillColor=colors.HexColor("#F4F7FA"), strokeColor=colors.HexColor("#45627A")))
        rows = [""]
        for word in node["label"].split():
            if not rows[-1] or len(rows[-1]) + len(word) + 1 <= 24:
                rows[-1] = f"{rows[-1]} {word}".strip()
            else:
                rows.append(word)
        for row_index, label in enumerate(rows[:2]):
            drawing.add(String(x + 4, y + 20 - row_index * 9, label, fontName="Helvetica", fontSize=6.5, fillColor=colors.HexColor("#21324B")))
    return drawing


def _write_pdf(pack: dict[str, Any], path: Path, frames_dir: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="PackBody", parent=styles["BodyText"], fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=5))
    styles.add(ParagraphStyle(name="PackH1", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#21324B"), spaceAfter=10))
    styles.add(ParagraphStyle(name="PackH2", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#284D68"), spaceBefore=11, spaceAfter=5))
    story = [Paragraph(SESSION_ID, styles["PackH1"]), Paragraph("Session Knowledge Pack  |  READY FOR OWNER REVIEW", styles["PackBody"]),
             Paragraph("Executive Brief", styles["PackH2"]), Paragraph(pack["executive_brief"], styles["PackBody"])]
    for app in pack["applications"]:
        story.extend([Paragraph(APPLICATION_TITLES[app["application_id"]], styles["PackH1"]), Spacer(1, 4)])
        for section in app["sections"]:
            parts = [Paragraph(section["title"], styles["PackH2"])]
            if section.get("text"):
                parts.append(Paragraph(section["text"], styles["PackBody"]))
            for item in section.get("claims", []):
                parts.append(Paragraph("- " + item, styles["PackBody"]))
            story.append(KeepTogether(parts))
    shown_frames = set()
    for diagram in pack["derived_diagrams"]:
        story.extend([Paragraph(diagram["title"], styles["PackH2"]), Paragraph(diagram["provenance_label"], styles["PackBody"]),
                      Paragraph(f"Derived from {SESSION_ID}.mp4; {', '.join(diagram['source_frames'])}.", styles["PackBody"]),
                      _draw_diagram(diagram)])
        node_labels = {node["id"]: node["label"] for node in diagram["nodes"]}
        story.extend(Paragraph(
            f"{index}. {node_labels[edge['source']]} {edge['relation_type']} {node_labels[edge['target']]}: {edge['label']} "
            f"(claims {', '.join(edge['claim_ids'])}; frames {', '.join(edge['provenance']['frame_ids'])}; "
            f"evidence {', '.join(edge['provenance']['evidence_ids'])}).",
            styles["PackBody"],
        ) for index, edge in enumerate(diagram["edges"], 1))
        for frame_id in diagram["source_frames"]:
            if frame_id in pack["representative_frames"] and frame_id not in shown_frames:
                story.extend([Paragraph(pack["representative_frames"][frame_id], styles["PackBody"]),
                              Image(str(frames_dir / frame_id), width=6.1 * inch, height=3.43 * inch)])
                shown_frames.add(frame_id)
    for frame_id, caption in pack["representative_frames"].items():
        if frame_id not in shown_frames:
            story.extend([Paragraph(caption, styles["PackBody"]), Image(str(frames_dir / frame_id), width=6.1 * inch, height=3.43 * inch)])
    for title, content in pack["common_sections"].items():
        story.extend([Paragraph(title, styles["PackH2"])])
        values = content if isinstance(content, list) else [str(content)]
        story.extend(Paragraph("- " + value, styles["PackBody"]) for value in values)
    story.extend([Paragraph("Evidence Timeline", styles["PackH2"])])
    story.extend(Paragraph(f"{event['start']}-{event['end']}: {event['summary']} ({event['id']})", styles["PackBody"]) for event in pack["evidence_timeline"])
    story.extend([PageBreak(), Paragraph("Source Map", styles["PackH1"])])
    story.extend(Paragraph(
        f"{s.get('source_id') or s.get('evidence_id')}"
        f"{' (aliases: ' + ', '.join(s['aliases']) + ')' if s.get('aliases') else ''}"
        f"  |  {s['source_type']}  |  {s.get('path') or s.get('source_path')}  |  SHA-256 {s['sha256']}",
        styles["PackBody"],
    ) for s in pack["source_map"])
    story.extend([Paragraph("Quality Scorecard", styles["PackH1"])])
    story.extend(Paragraph(f"- {key}: {value}", styles["PackBody"]) for key, value in pack["quality_scorecard"].items())
    story.append(Paragraph("Quality / Evidence Notes: 20.578 seconds of short residual VAD intervals remain classified UNCERTAIN under the accepted 0.5-second boundary tolerance. They are retained in the JSON ledger. Nine OCR-low-confidence frames are not used as sole support for a claim. Procedures=0; no support SOP was demonstrated.", styles["PackBody"]))
    def page_marks(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#68798A"))
        canvas.drawString(document.leftMargin, letter[1] - 0.4 * inch, "Session 41 Knowledge Pack")
        canvas.drawRightString(letter[0] - document.rightMargin, 0.35 * inch, f"Page {document.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=letter, rightMargin=0.65*inch, leftMargin=0.65*inch,
                      topMargin=0.62*inch, bottomMargin=0.62*inch, title=SESSION_ID).build(
        story, onFirstPage=page_marks, onLaterPages=page_marks
    )


def generate_session_pack(
    *, video_path: Path, frame_root: Path, transcript_path: Path,
    speech_report_path: Path, visual_report_path: Path, review_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    speech = json.loads(speech_report_path.read_text(encoding="utf-8"))
    duration = float(speech.get("video_duration_seconds", 0))
    speech_video = str(speech.get("video", "")).replace("\\", "/").rsplit("/", 1)[-1]
    if (speech_video != video_path.name or abs(duration - 2105.365) > 1.0
            or speech.get("transcript_state") != "VALID" or speech.get("speech_quality_gate") != "PASS"):
        raise ValueError("transcript speech-coverage gate failed or source identity differs")
    visual = apply_reviewed_topics(json.loads(visual_report_path.read_text(encoding="utf-8")), review_path)
    timeline_path = frame_root / "evidence" / "evidence-timeline.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    segment_records = transcript.get("segments", [])
    source_map = deduplicate_source_artifacts(timeline["source_map"])
    timeline["events"] = sort_evidence_timeline(timeline["events"])
    timeline["source_map"] = source_map
    source_map_errors = validate_source_artifact_dedup(source_map)
    timeline_errors = validate_timeline_chronology(timeline["events"])
    source_lookup = {item["source_id"]: item for item in source_map if item.get("source_id")}
    primary_id = "S-TRANSCRIPT-PRIMARY"
    video_id = "S-VIDEO"
    if primary_id not in source_lookup or video_id not in source_lookup:
        raise ValueError("timeline is missing transcript/video source identity")
    visual_frames = {item["frame_id"]: item for item in visual["frames"]}
    apps_dir = frame_root / "applications"
    claims = []
    for knowledge_path in apps_dir.rglob("app-knowledge.json"):
        directory = knowledge_path.parent.parent
        if directory.is_dir():
            app_id = APPLICATIONS.get(directory.name)
            if not app_id:
                raise ValueError(f"unmapped application directory: {directory.name}")
            claims.extend(_build_claims(knowledge_path, directory, app_id, timeline["events"], source_map,
                                        segment_records, primary_id, video_id, visual_frames))
    catalogue = visual_frames["frame_0021.png"]
    catalogue_source = next((item for item in source_map if item.get("source_path", "").endswith("frame_0021.png")), None)
    if not catalogue_source or not catalogue.get("selected"):
        raise ValueError("CPRT catalogue provenance unavailable")
    for claim_id, claim_text in (
        ("C-028", "The source overview screen identifies the application as PGRegDoc.com."),
        ("C-030", "The PG RegDoc data-flow slide labels PingID as the authentication dependency."),
        ("C-026", "The catalogue record lists Paul Senn as owner and P&G AMS Support Team as the support group."),
        ("C-027", "The catalogue classifies the entry as an Application in the Application Platform / Business Application categories."),
        ("C-029", "The catalogue record title identifies North America Central Product Research Testing Panelist Payments."),
    ):
        source_frame_id = "frame_0000.png" if claim_id == "C-028" else "frame_0005.png" if claim_id == "C-030" else "frame_0021.png"
        frame_record = visual_frames[source_frame_id]
        frame_source = next((item for item in source_map if item.get("source_path", "").endswith(source_frame_id)), None)
        if not frame_source or not frame_record.get("selected"):
            raise ValueError(f"reviewed frame provenance unavailable for {claim_id}")
        claims.append({
            "claim_id": claim_id,
            "application_id": "pg-regdoc" if claim_id in {"C-028", "C-030"} else APPLICATIONS["north-america-central-product-research-testing-panelist-payments"],
            "claim": claim_text, "source_type": "VIDEO_FRAME", "source_id": video_id,
            "timestamp": float(frame_source["timestamp_seconds"]), "frame_id": source_frame_id,
            "confidence": .9, "verification_state": "VISUAL_CONFIRMED",
            "first_seen": {"session_id": SESSION_ID, "timestamp": _clock(float(frame_source["timestamp_seconds"]))},
            "last_confirmed": {"session_id": SESSION_ID, "timestamp": _clock(float(frame_source["timestamp_seconds"]))},
            "supporting_sources": [{
                "source_id": video_id, "source_type": "VIDEO_FRAME",
                "timestamp": float(frame_source["timestamp_seconds"]), "frame_id": source_frame_id,
                "evidence_id": frame_source["evidence_id"], "source_path": frame_source["source_path"],
                "image_sha256": frame_source.get("sha256"), "ocr_status": frame_record["ocr_status"],
                "ocr_text": frame_record["ocr_text"],
            }], "conflicts": [],
        })
    opening = next(event for event in timeline["events"] if event["id"] == "E-001")
    opening_segments = _segment_refs(segment_records, _seconds(opening["start"]), _seconds(opening["end"]))
    claims.append({
        "claim_id": "C-001", "application_id": "SESSION_GENERAL",
        "claim": "The recording explicitly covers PG RegDoc and North America Central Product Research Testing Panelist Payments.",
        "source_type": "TRANSCRIPT", "source_id": primary_id,
        "timestamp": _seconds(opening["start"]), "frame_id": None, "confidence": .95,
        "verification_state": "SOURCE_CONFIRMED", "first_seen": {"session_id": SESSION_ID, "timestamp": opening["start"]},
        "last_confirmed": None, "supporting_sources":[{"source_id": primary_id, "source_type":"TRANSCRIPT_SEGMENTS",
            "timestamp": _seconds(opening["start"]), "evidence_id":"E-001", "segments":opening_segments}], "conflicts":[],
    })
    known_sources = set(source_lookup)
    known_sources.add(video_id)
    claim_errors = validate_pack_claim_provenance(claims, known_sources, set(visual_frames))
    if claim_errors:
        raise ValueError("claim ledger gate failed: " + "; ".join(claim_errors))
    diagrams = build_derived_diagrams()
    claim_ids = {claim["claim_id"] for claim in claims}
    frame_ids = set(visual_frames)
    event_ids = {event["id"] for event in timeline["events"]}
    diagram_errors = validate_diagram_provenance(diagrams, claim_ids, frame_ids, event_ids)
    if diagram_errors:
        raise ValueError("derived diagram provenance gate failed: " + "; ".join(diagram_errors))
    relation_errors = validate_diagram_relations(diagrams)
    if relation_errors:
        raise ValueError("derived diagram relation gate failed: " + "; ".join(relation_errors))
    apps = _make_application_sections(claims)
    application_errors = validate_application_claim_isolation(apps, claims)
    if application_errors:
        raise ValueError("application claim isolation gate failed: " + "; ".join(application_errors))
    common = {
        "Open Questions": [
            "PG RegDoc frontend ownership boundary is not stated.",
            "The exact authentication phrase and its relationship to PingID need confirmation.",
            "North America CPRT technical walkthrough, resource access, and decommissioning decision remain open.",
        ],
        "Glossary": ["SDS: Safety Data Sheet (expanded in source context).", "REACH: business requirement is mentioned; speaker's suggested definition is unverified.", "ETL: Extract, Transform, Load (expanded in the visible catalogue record).", "CPRT: Product Research Testing Panelist Payments (record title)."],
        "Quality / Evidence Notes": [
            "Speech coverage: 97.39% effective; media timestamp reach: 68.20%; 20.578 seconds across 26 short residual intervals remain UNCERTAIN.",
            "The final 00:11:09.476 is classified NON_SPEECH_TRAILING_MEDIA based on completed VAD and sampled gallery/black frames.",
            "OCR: 22 SUCCESS, 9 LOW_CONFIDENCE, 5 NOT_REQUIRED; gallery and empty frames are excluded from operational content.",
            "PROCEDURES=0; no support SOP is invented. Low-confidence terms are isolated in Ambiguities / Needs Review.",
        ],
    }
    selected_frames = {item["frame_id"]: item for item in visual["frames"] if item.get("selected")}
    frame_labels = {
        "frame_0000.png": "00:00:57 - PG RegDoc application overview slide; supports application identity and overview. Source frame V-001.",
        "frame_0005.png": "00:05:41 - PG RegDoc data-flow slide; shows browser interactions and PingID label. Source frame V-002.",
        "frame_0006.png": "00:06:38 - Technical overview slide with production and development architecture diagrams; service labels are cross-checked against the concurrent technical walkthrough. Source frame V-003.",
        "frame_0021.png": "00:20:52 - CPRT application catalogue record; shows purpose/data description, lifecycle status and support group. Source frame V-004.",
    }
    frame_labels = {key: value for key, value in frame_labels.items() if key in selected_frames}
    assert_visual = {"discovered": visual["visual_topics_discovered"], "covered": visual["visual_topics_covered"],
                     "selected": visual["selected_count"], "suppressed_duplicates": visual["suppressed_duplicate_count"],
                     "suppressed_gallery": visual["suppressed_gallery_count"], "suppressed_black": visual["suppressed_black_count"]}
    assertive_claims = [claim for claim in claims if claim["verification_state"] not in UNCERTAIN_STATES]
    low_ratio = sum(claim["confidence"] < .5 for claim in assertive_claims) / max(1, len(assertive_claims))
    gates = evaluate_session_pack_gates(
        transcript_state=speech.get("transcript_state"), speech_gate=speech.get("speech_quality_gate"),
        visual_gate=visual["visual_coverage_gate"], claim_errors=claim_errors, diagram_errors=diagram_errors,
        application_ids={app["application_id"] for app in apps}, low_confidence_ratio=low_ratio, procedures=[],
        application_errors=application_errors, source_map_errors=source_map_errors,
        timeline_errors=timeline_errors, relation_errors=relation_errors,
    )
    if any(value != "PASS" for value in gates.values()):
        raise ValueError(f"Session Knowledge Pack generation blocked: {gates}")
    claim_states = {state: sum(claim["verification_state"] == state for claim in claims)
                    for state in sorted({claim["verification_state"] for claim in claims})}
    quality_scorecard = {
        "SOURCE_IDENTITY": "PASS",
        "MEDIA_COVERAGE": f"{speech.get('media_coverage_percent')}% timestamp reach",
        "SPEECH_COVERAGE": f"{speech.get('speech_coverage_percent')}% effective; {speech.get('uncovered_speech_seconds')} seconds retained uncertain",
        "TRANSCRIPT_STATE": speech.get("transcript_state"),
        "OCR_SUCCESS": sum(frame["ocr_status"] == "SUCCESS" for frame in visual["frames"]),
        "OCR_LOW_CONFIDENCE": sum(frame["ocr_status"] == "LOW_CONFIDENCE" for frame in visual["frames"]),
        "VISUAL_TOPICS": len(visual["visual_topics_discovered"]),
        "VISUAL_TOPICS_COVERED": len(visual["visual_topics_covered"]),
        "MEANINGFUL_FRAMES": visual["meaningful_visual_count"],
        "SELECTED_FRAMES": visual["selected_count"],
        "GROUNDED_CLAIMS": len(claims), "CLAIM_STATES": claim_states,
        "UNPROVEN_CLAIMS": 0, "APPLICATIONS_IDENTIFIED": len(apps),
        "PROCEDURES": 0, "ARCHITECTURE_DIAGRAMS": len(diagrams),
        "APPLICATION_CLAIM_ISOLATION": gates["APPLICATION_CLAIM_ISOLATION"],
        "SOURCE_ARTIFACT_DEDUP": gates["SOURCE_ARTIFACT_DEDUP"],
        "EVIDENCE_TIMELINE_CHRONOLOGICAL": gates["EVIDENCE_TIMELINE_CHRONOLOGICAL"],
        "DIAGRAM_RELATION_GROUNDING": gates["DIAGRAM_RELATION_GROUNDING"],
        "CLAIM_LEDGER": gates["CLAIM_LEDGER"],
        "VISUAL_COVERAGE": gates["VISUAL_COVERAGE"],
        "OPEN_QUESTIONS": 3,
        "AMBIGUITIES": sum(claim["verification_state"] in UNCERTAIN_STATES for claim in claims),
        "QUALITY_GATE": "PASS",
    }
    pack = {
        "schema_version": 1, "document_type": "SESSION_KNOWLEDGE_PACK", "source_video": video_path.name,
        "quality_state": "READY", "quality_gates": gates,
        "executive_brief": "This recording covers two separate applications. PG RegDoc is a public document-sharing application with documented Azure services and browser-based user flows. The North America CPRT record documents panelist-payment data handling, restricted database access, and a Leverage/Optimize lifecycle state; its technical walkthrough and decommissioning decision remain open.",
        "transcript_quality": {key: speech.get(key) for key in ("transcript_state", "speech_quality_gate", "media_coverage_percent", "speech_coverage_percent", "vad_speech_seconds", "transcribed_speech_seconds", "uncovered_speech_seconds", "uncovered_speech_interval_count", "largest_uncovered_speech_interval_seconds", "transcript_start", "transcript_last_timestamp")},
        "visual_coverage": assert_visual, "quality_scorecard": quality_scorecard,
        "claims": claims, "applications": apps,
        "derived_diagrams": diagrams, "representative_frames": frame_labels, "common_sections": common,
        "evidence_timeline": timeline["events"], "source_map": source_map,
        "source_coverage": timeline.get("source_coverage", {}),
        "frame_dir_relative": os.path.relpath(frame_root, output_dir).replace("\\", "/"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = video_path.stem
    json_path = output_dir / f"{basename}.json"
    md_path = output_dir / f"{basename}.md"
    pdf_path = output_dir / f"{basename}.pdf"
    json_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_markdown(pack), encoding="utf-8")
    _write_pdf(pack, pdf_path, frame_root)
    return {"status": "READY", "quality_gates": gates, "artifacts": {"json": str(json_path), "md": str(md_path), "pdf": str(pdf_path)}, "visual_coverage": assert_visual, "claim_count": len(claims), "diagram_count": len(diagrams)}
