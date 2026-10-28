"""Deterministic, evidence-bound KAV procedure and runbook contracts."""
from __future__ import annotations

import hashlib
import re
from typing import Any

ACTIONABILITY = {"REFERENCE", "GUIDED", "EXECUTABLE_WITH_CONFIRMATION", "EXECUTABLE"}
MATERIAL_ACTIONS = {
    "SUBMIT", "DELETE", "DISABLE", "DECOMMISSION", "CHANGE_PRODUCTION",
    "GRANT_ACCESS", "REVOKE_ACCESS", "MODIFY_RETENTION",
}
_ACTION = re.compile(
    r"\b(click|select|open|navigate|enter|type|choose|update|change|review|verify|check|"
    r"create|add|remove|assign|grant|revoke|submit|save|disable|delete|decommission|attach|"
    r"fill|complete|request|raise|use|point)\b",
    re.I,
)
_ORDER = re.compile(r"\b(first|then|next|after that|finally|step\s+\d+)\b", re.I)
_START_ORDER = re.compile(r"\b(first|step\s+1|to begin|start by|starting with)\b", re.I)
_WORKFLOW_END = re.compile(r"\b(finally|workflow complete|that(?:'s| is) it|done with (?:this|the) workflow)\b", re.I)
_PARAMETERS = {
    r"\b(password|passcode|credential|secret|token|api key)\b": "credential",
    r"\bacs\s+url\b": "acs_url", r"\burl\b": "url",
    r"\bentity\s+id\b": "entity_id", r"\b(identifier|id)\b": "identifier",
    r"\brole(?:\s+name)?\b": "role", r"\bgroup(?:\s+name)?\b": "group",
    r"\bentitlement(?:\s+id)?\b": "entitlement",
    r"\b(environment|production environment)\b": "environment",
    r"\b(owner|contact|application owner)\b": "owner_or_contact",
    r"\bbusiness justification\b": "business_justification",
    r"\b(ticket|request)(?:\s+id|\s+number)?\b": "ticket_or_request_id",
    r"\bretention(?:\s+period|\s+setting)?\b": "retention_setting",
    r"\b(configuration|connection) value\b": "configuration_value",
}
_SECRET = re.compile(r"\b(password|passcode|secret|token|api key|credential)\b\s*(?:is|:|=)?\s*([^\s,;]+)?", re.I)


def _id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def embedding_chunk_id(chunk: dict[str, Any]) -> str:
    normalized = " ".join(str(chunk.get("content", "")).split())
    raw = "|".join((str(chunk.get("knowledge_id", "")), str(chunk.get("version", "")),
                    str(chunk.get("canonical_topic", "")), normalized))
    return "chunk-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _action_name(text: str) -> str:
    lowered = text.casefold()
    if re.search(r"\b(change|update|modify)\b.{0,40}\bproduction\b", lowered):
        return "CHANGE_PRODUCTION"
    if re.search(r"\b(change|update|modify)\b.{0,40}\bretention\b", lowered):
        return "MODIFY_RETENTION"
    verb = _ACTION.search(text)
    if not verb:
        return "OBSERVE"
    return {
        "click": "NAVIGATE", "open": "NAVIGATE", "navigate": "NAVIGATE",
        "select": "SELECT", "choose": "SELECT", "enter": "ENTER_VALUE",
        "type": "ENTER_VALUE", "update": "UPDATE", "change": "UPDATE",
        "review": "REVIEW", "verify": "VERIFY", "create": "CREATE",
        "check": "REVIEW", "attach": "ATTACH", "fill": "ENTER_VALUE",
        "complete": "COMPLETE", "request": "PREPARE_REQUEST", "raise": "PREPARE_REQUEST",
        "use": "NAVIGATE", "point": "REVIEW",
        "add": "ADD", "remove": "REMOVE", "assign": "ASSIGN",
        "grant": "GRANT_ACCESS", "revoke": "REVOKE_ACCESS", "submit": "SUBMIT",
        "save": "SAVE", "disable": "DISABLE", "delete": "DELETE",
        "decommission": "DECOMMISSION",
    }[verb.group(1).casefold()]


def extract_procedures(segments: list[dict[str, Any]], *, media_id: str,
                       application_id: str | None = None) -> list[dict[str, Any]]:
    """Find multiple evidence-grounded ordered action clusters across a recording."""
    ordered_segments = sorted(segments, key=lambda item: float(item.get("start", 0)))
    procedures: list[dict[str, Any]] = []
    candidate: list[dict[str, Any]] = []
    cluster_application: str | None = None
    topic: set[str] = set()
    last_action_at: float | None = None

    def finish() -> None:
        nonlocal candidate, cluster_application, topic, last_action_at
        if len(candidate) >= 2 and all(step["evidence_refs"] for step in candidate):
            refs = list(dict.fromkeys(ref for step in candidate for ref in step["evidence_refs"]))
            procedure_id = f"proc-{_id(media_id, *refs)}"
            procedures.append({
                "procedure_id": procedure_id,
                "title": "Demonstrated operational workflow",
                "purpose": "Follow the ordered actions evidenced in the source recording.",
                "application_id": cluster_application or application_id,
                "actionability": "GUIDED",
                "trigger": "The operator has confirmed the task and current approved workflow.",
                "required_inputs": [],
                "preconditions": ["Validate the current approved UI and policy before proceeding."],
                "steps": candidate,
                "expected_outcomes": [],
                "evidence_refs": refs,
                "confidence": min(step["confidence"] for step in candidate),
                "verification_state": "SYNTHESIZED_UNREVIEWED",
            })
        candidate, cluster_application, topic, last_action_at = [], None, set(), None

    for segment in ordered_segments:
        text = re.sub(r"\s+", " ", str(segment.get("text", "")).strip())
        if not text:
            continue
        timestamp = float(segment.get("start", 0))
        starts_workflow = bool(_START_ORDER.search(text))
        if starts_workflow:
            finish()
        if not candidate and not starts_workflow:
            continue
        if candidate and last_action_at is not None and timestamp - last_action_at > 180:
            finish()
            continue
        if not _ACTION.search(text):
            continue
        tokens = _topic_tokens(text)
        segment_application = segment.get("application_id")
        topic_changed = bool(candidate and topic and tokens and not (tokens & topic))
        application_changed = bool(candidate and segment_application and cluster_application
                                   and segment_application != cluster_application)
        inactive = last_action_at is not None and timestamp - last_action_at > 180
        if candidate and (application_changed or inactive or (topic_changed and timestamp - (last_action_at or timestamp) > 30)):
            finish()
            if not starts_workflow:
                continue
        safe_text = _SECRET.sub(lambda match: match.group(1) + " [REDACTED]", text)
        refs = [str(segment.get("segment_id"))] if segment.get("segment_id") else []
        if not refs:
            continue
        values = _required_values(text)
        candidate.append({
            "order": len(candidate) + 1, "instruction": safe_text,
            "semantic_action": _action_name(text), "semantic_target": None,
            "required_values": values, "evidence_refs": refs,
            "source_timestamp": segment.get("start"), "frame_id": segment.get("frame_id"),
            "confidence": min(0.8, float(segment.get("confidence", 0.65))),
        })
        topic.update(tokens)
        last_action_at = timestamp
        if segment_application and not cluster_application:
            cluster_application = str(segment_application)
        if _WORKFLOW_END.search(text):
            finish()
    finish()
    return procedures


def _topic_tokens(text: str) -> set[str]:
    ignored = {"first", "then", "next", "finally", "open", "click", "select", "enter", "submit", "review", "the", "and", "with", "this", "that", "after", "once", "request", "form"}
    return {token for token in re.findall(r"[a-z]{4,}", text.casefold()) if token not in ignored}


def _required_values(text: str) -> list[dict[str, str]]:
    values = []
    for pattern, key in _PARAMETERS.items():
        if key == "url" and re.search(r"\bacs\s+url\b", text, re.I):
            continue
        if re.search(pattern, text, re.I):
            values.append({"key": key, "status": "REQUIRED_UNRESOLVED", "source": "APPROVED_CURRENT_SOURCE"})
    return values


def procedure_grounding(procedures: list[dict[str, Any]], valid_evidence_ids: set[str]) -> tuple[str, list[str]]:
    if not procedures:
        return "NOT_APPLICABLE", []
    errors: list[str] = []
    for procedure in procedures:
        refs = set(procedure.get("evidence_refs", []))
        steps = procedure.get("steps", [])
        if not procedure.get("procedure_id") or not refs or not refs <= valid_evidence_ids or not steps:
            errors.append(str(procedure.get("procedure_id") or "procedure") + ": invalid procedure provenance")
        for step in steps:
            step_refs = set(step.get("evidence_refs", []))
            if (not step.get("instruction") or not step_refs or not step_refs <= valid_evidence_ids
                    or not step.get("semantic_action") or int(step.get("order", 0)) < 1):
                errors.append(f"{procedure.get('procedure_id')}: invalid step provenance")
    return ("FAIL", errors) if errors else ("PASS", [])


def build_runbooks(procedures: list[dict[str, Any]], *, source_session: str,
                   evidence_index: list[dict[str, Any]] | None = None,
                   claims: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    evidence_by_id = {str(item.get("evidence_id") or item.get("evidenceId")): item
                      for item in (evidence_index or [])}
    runbooks = []
    for procedure in procedures:
        requested_actionability = procedure.get("actionability", "GUIDED")
        actionability = (requested_actionability if procedure.get("actionability_explicit") is True
                         else "GUIDED")
        if actionability == "EXECUTABLE" and not (
                procedure.get("policy_allows_execution") is True and procedure.get("safe_reversible") is True):
            actionability = "GUIDED"
        if actionability not in ACTIONABILITY:
            actionability = "GUIDED"
        steps = []
        approvals = set()
        for step in procedure.get("steps", []):
            action = str(step.get("semantic_action") or step.get("semanticAction") or "OBSERVE").upper()
            if action in MATERIAL_ACTIONS:
                approvals.add(action)
            refs = step.get("evidence_refs", step.get("evidenceRefs", []))
            source = (next((evidence_by_id.get(str(ref)) for ref in refs
                            if evidence_by_id.get(str(ref))), {}) or {})
            steps.append({
                "order": int(step.get("order", 0)), "action": action,
                "instruction": str(step.get("instruction", "")),
                "semantic_action": action,
                "semantic_target": step.get("semantic_target", step.get("semanticTarget")),
                "required_values": list(step.get("required_values", [])),
                "evidence_refs": list(refs),
                "expected_ui_state": "Validate against the current approved UI; historical screens may differ.",
                "failure_state": "STOP and request human review; do not guess or continue.",
                "source_timestamp": step.get("source_timestamp", step.get("timestamp",
                                                                          source.get("timestamp_start", source.get("timestampStart")))),
                "frame_id": step.get("frame_id", source.get("frame_id", source.get("frameRef"))),
                "historical_instruction": True,
                "current_live_validation_required": True,
            })
        all_refs = list(dict.fromkeys(ref for step in steps for ref in step["evidence_refs"]))
        claim_ids = [str(claim.get("claim_id")) for claim in (claims or [])
                     if claim.get("claim_id") and set(all_refs) & _claim_evidence_refs(claim)]
        capture = []
        if any(step["action"] in MATERIAL_ACTIONS for step in steps):
            capture = ["PRE_CHANGE_STATE", "POST_CHANGE_STATE", "CONFIRMATION_MESSAGE"]
        identifier = str(procedure.get("procedure_id") or procedure.get("procedureId")
                         or procedure.get("id") or f"runbook-{_id(source_session, procedure.get('title'))}")
        runbooks.append({
            "id": f"kav-{_id(identifier)}", "version": 1,
            "application_id": procedure.get("application_id", procedure.get("applicationId")),
            "title": str(procedure.get("title", "Evidence-grounded workflow")),
            "status": "CANDIDATE", "actionability": actionability,
            "execution_ready": False,
            "trigger": procedure.get("trigger", "Confirm the task and approved current workflow."),
            "required_inputs": list(procedure.get("required_inputs", procedure.get("requiredInputs", []))),
            "preconditions": list(procedure.get("preconditions", procedure.get("prerequisites", []))),
            "steps": steps, "evidence_to_capture": capture,
            "approval_required_before": sorted(approvals),
            "stop_conditions": [
                "A required value, approval, identifier, credential, URL, or policy is missing.",
                "The current approved UI or policy materially conflicts with this historical instruction.",
            ],
            "prohibitions": [
                "Never infer credentials, URLs, identifiers, groups, entitlements, roles, retention, owners, justification, approval, environment, or ticket IDs.",
                "Do not submit or make material changes without explicit approval.",
            ],
            "escalation": {"condition": "Missing or conflicting required information", "target": "AUTHORIZED_REVIEWER", "instruction": "Stop and request an approved value or human review."},
            "source_sessions": [source_session], "source_claims": claim_ids, "source_evidence": all_refs,
            "verification_state": procedure.get("verification_state", "SYNTHESIZED_UNREVIEWED"),
            "confidence": float(procedure.get("confidence", 0.0)),
        })
    return runbooks


def _claim_evidence_refs(claim: dict[str, Any]) -> set[str]:
    refs = {str(value) for value in claim.get("evidence_refs", [])}
    for source in claim.get("supporting_sources", []):
        for key in ("source_id", "segment_id", "frame_id", "source_evidence_id"):
            if source.get(key):
                refs.add(str(source[key]))
        refs.update(str(segment.get("segment_id")) for segment in source.get("segments", [])
                    if segment.get("segment_id"))
    return refs


def validate_runbooks(runbooks: list[dict[str, Any]], valid_evidence_ids: set[str]) -> tuple[str, list[str]]:
    if not runbooks:
        return "NOT_APPLICABLE", []
    errors = []
    for runbook in runbooks:
        escalation = runbook.get("escalation") or {}
        if runbook.get("actionability") not in ACTIONABILITY or not runbook.get("steps"):
            errors.append(f"{runbook.get('id')}: missing actionability or steps")
        if runbook.get("status") != "CANDIDATE":
            errors.append(f"{runbook.get('id')}: runbook must remain a candidate")
        if (not runbook.get("trigger") or not isinstance(runbook.get("required_inputs"), list)
                or not runbook.get("stop_conditions") or not runbook.get("prohibitions")
                or not escalation.get("target")
                or not escalation.get("instruction")):
            errors.append(f"{runbook.get('id')}: required safety contract is incomplete")
        if not set(runbook.get("source_evidence", [])) <= valid_evidence_ids:
            errors.append(f"{runbook.get('id')}: source evidence is invalid")
        for step in runbook.get("steps", []):
            refs = set(step.get("evidence_refs", []))
            if not refs or not refs <= valid_evidence_ids:
                errors.append(f"{runbook.get('id')}: step evidence is invalid")
            if step.get("action") in MATERIAL_ACTIONS and step["action"] not in runbook.get("approval_required_before", []):
                errors.append(f"{runbook.get('id')}: material action lacks approval boundary")
            if not step.get("historical_instruction") or not step.get("current_live_validation_required"):
                errors.append(f"{runbook.get('id')}: historical/current validation metadata missing")
    return ("FAIL", errors) if errors else ("PASS", [])


def evaluate_runbook_preflight(runbook: dict[str, Any], *, supplied_values: dict[str, Any],
                               current_live_matches: bool | None,
                               approved_actions: set[str] | None = None) -> dict[str, Any]:
    """Fail closed on missing inputs, unvalidated historical UI, conflicts, or approvals."""
    required = list(runbook.get("required_inputs", [])) + [
        value for step in runbook.get("steps", []) for value in step.get("required_values", [])]
    missing = sorted({str(value.get("key") or value.get("name")) if isinstance(value, dict) else str(value)
                      for value in required
                      if (str(value.get("key") or value.get("name")) if isinstance(value, dict) else str(value)) not in supplied_values
                      or supplied_values.get(str(value.get("key") or value.get("name")) if isinstance(value, dict) else str(value)) in (None, "")})
    if missing:
        return {"status": "STOP", "reason": "MISSING_REQUIRED_VALUES", "missing_values": missing}
    if current_live_matches is None:
        return {"status": "STOP", "reason": "CURRENT_LIVE_VALIDATION_REQUIRED"}
    if current_live_matches is False:
        return {"status": "STOP", "reason": "HISTORICAL_INSTRUCTION_CONFLICT_REVIEW"}
    approved = approved_actions or set()
    required = set(runbook.get("approval_required_before", []))
    pending = sorted(required - approved)
    if pending:
        return {"status": "STOP", "reason": "APPROVAL_REQUIRED", "actions": pending}
    if runbook.get("actionability") in {"REFERENCE", "GUIDED"}:
        return {"status": "STOP", "reason": "HUMAN_MUST_PERFORM_ACTION"}
    return {"status": "READY", "reason": "PREFLIGHT_PASSED"}


def second_brain_ready(*, quality_gate: str, claim_provenance: str, application_resolution: str,
                       has_application: bool, conflicts_promoted: bool, package_policy: str,
                       raw_transcript_published: bool, raw_media_published: bool,
                       procedure_gate: str, runbook_gate: str) -> str:
    checks = [quality_gate == "PASS", claim_provenance == "PASS",
              (application_resolution == "PASS" if has_application else True),
              not conflicts_promoted, package_policy == "PASS",
              not raw_transcript_published, not raw_media_published,
              (procedure_gate == "PASS" and runbook_gate == "PASS"
               if procedure_gate != "NOT_APPLICABLE" else runbook_gate == "NOT_APPLICABLE")]
    return "PASS" if all(checks) else "FAIL"


def embedding_ready(chunks: list[dict[str, Any]], *, second_brain_ready_state: str = "FAIL",
                    intended_chunk_ids: set[str] | None = None,
                    accepted_exclusions: dict[str, str] | None = None) -> dict[str, Any]:
    eligible, rejected = [], []
    for chunk in chunks:
        try:
            confidence = float(chunk.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        prohibited = ("conflicting", "unreviewed_conflict", "contains_secret", "raw_transcript",
                      "raw_transcript_text", "raw_ocr", "raw_ocr_dump", "diagnostic",
                      "raw_execution_state", "kav_execution_state", "execution_state")
        reasons = []
        content = str(chunk.get("content", ""))
        if not content.strip():
            reasons.append("EMPTY_CONTENT")
        if chunk.get("curated") is not True:
            reasons.append("NOT_CURATED")
        if chunk.get("verification_status") != "HUMAN_REVIEWED":
            reasons.append("NOT_HUMAN_REVIEWED")
        if any(chunk.get(key) for key in prohibited):
            reasons.append("PROHIBITED_CONTENT")
        if confidence < 0.8:
            reasons.append("LOW_CONFIDENCE")
        if _SECRET.search(content):
            reasons.append("SECRET_CONTENT")
        normalized = " ".join(content.split())
        expected_hash = "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if chunk.get("content_hash") != expected_hash:
            reasons.append("INVALID_CONTENT_HASH")
        chunk_id = embedding_chunk_id(chunk)
        if chunk.get("chunk_id") != chunk_id:
            reasons.append("INVALID_CHUNK_ID")
        if second_brain_ready_state != "PASS":
            reasons.append("SECOND_BRAIN_NOT_READY")
        required = ("chunk_id", "knowledge_id", "version", "project_id", "canonical_topic", "source_knowledge_ids",
                    "verification_status", "confidence", "provenance_pointers", "content_hash")
        if any(not chunk.get(key) for key in required):
            reasons.append("MISSING_IDENTITY_OR_PROVENANCE")
        if chunk.get("conflicting") or chunk.get("unreviewed_conflict"):
            reasons.append("CONFLICT")
        if reasons:
            rejected.append({"chunk_id": chunk_id, "chunk": chunk,
                             "rejection_reasons": sorted(set(reasons))})
        else:
            eligible.append({**chunk, "chunk_id": chunk_id, "content": normalized, "content_hash": expected_hash})
    ids = intended_chunk_ids if intended_chunk_ids is not None else {embedding_chunk_id(c) for c in chunks}
    rejected_ids = {str(item["chunk_id"]) for item in rejected}
    explicitly_excluded = accepted_exclusions or {}
    accounted = {str(item.get("chunk_id")) for item in eligible} | {
        key for key, reason in explicitly_excluded.items() if isinstance(reason, str) and reason.strip()
    }
    document_ready = (second_brain_ready_state == "PASS" and bool(ids) and ids <= accounted
                      and not (rejected_ids - set(explicitly_excluded)))
    return {"CHUNK_EMBEDDING_ELIGIBLE": bool(eligible), "DOCUMENT_EMBEDDING_READY": document_ready,
            "eligible_chunks": eligible, "rejected_chunks": rejected}
