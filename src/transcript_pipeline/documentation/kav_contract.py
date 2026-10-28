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
    r"\b(click|select|open|navigate|enter|type|choose|update|change|review|verify|"
    r"create|add|remove|assign|grant|revoke|submit|save|disable|delete|decommission)\b",
    re.I,
)
_ORDER = re.compile(r"\b(first|then|next|after that|finally|step\s+\d+)\b", re.I)
_SENSITIVE = re.compile(
    r"\b(password|credential|secret|token|api key|acs url|entity id|group name|"
    r"entitlement id|role name|retention period|business justification|ticket id|request id)\b",
    re.I,
)


def _id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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
        "add": "ADD", "remove": "REMOVE", "assign": "ASSIGN",
        "grant": "GRANT_ACCESS", "revoke": "REVOKE_ACCESS", "submit": "SUBMIT",
        "save": "SAVE", "disable": "DISABLE", "delete": "DELETE",
        "decommission": "DECOMMISSION",
    }[verb.group(1).casefold()]


def extract_procedures(segments: list[dict[str, Any]], *, media_id: str,
                       application_id: str | None = None) -> list[dict[str, Any]]:
    """Accept only two or more evidence-linked actions with explicit ordering cues."""
    candidate: list[dict[str, Any]] = []
    saw_order = False
    for segment in sorted(segments, key=lambda item: float(item.get("start", 0))):
        text = re.sub(r"\s+", " ", str(segment.get("text", "")).strip())
        ordered = bool(_ORDER.search(text))
        saw_order = saw_order or ordered
        if _SENSITIVE.search(text):
            return []
        if not text or not _ACTION.search(text):
            continue
        if not ordered:
            return []
        candidate.append({
            "order": len(candidate) + 1,
            "instruction": text,
            "semantic_action": _action_name(text),
            "semantic_target": None,
            "required_values": [],
            "evidence_refs": [str(segment.get("segment_id", ""))] if segment.get("segment_id") else [],
            "source_timestamp": segment.get("start"),
            "frame_id": segment.get("frame_id"),
            "confidence": min(0.8, float(segment.get("confidence", 0.65))),
        })
    if len(candidate) < 2 or not saw_order or any(not step["evidence_refs"] for step in candidate):
        return []
    procedure_id = f"proc-{_id(media_id, *(step['evidence_refs'][0] for step in candidate))}"
    return [{
        "procedure_id": procedure_id,
        "title": "Demonstrated operational workflow",
        "purpose": "Follow the ordered actions evidenced in the source recording.",
        "application_id": application_id,
        "actionability": "GUIDED",
        "trigger": "The operator has confirmed the task and current approved workflow.",
        "required_inputs": ["Confirm all required values from an approved current source."],
        "preconditions": ["Validate the current approved UI and policy before proceeding."],
        "steps": candidate,
        "expected_outcomes": [],
        "evidence_refs": list(dict.fromkeys(ref for step in candidate for ref in step["evidence_refs"])),
        "confidence": min(step["confidence"] for step in candidate),
        "verification_state": "SYNTHESIZED_UNREVIEWED",
    }]


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
                   evidence_index: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
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
        identifier = str(procedure.get("procedure_id") or procedure.get("procedureId")
                         or procedure.get("id") or f"runbook-{_id(source_session, procedure.get('title'))}")
        runbooks.append({
            "id": f"kav-{_id(identifier)}", "version": 1,
            "application_id": procedure.get("application_id", procedure.get("applicationId")),
            "title": str(procedure.get("title", "Evidence-grounded workflow")),
            "status": "CANDIDATE", "actionability": actionability,
            "trigger": procedure.get("trigger", "Confirm the task and approved current workflow."),
            "required_inputs": list(procedure.get("required_inputs", procedure.get("requiredInputs", []))),
            "preconditions": list(procedure.get("preconditions", procedure.get("prerequisites", []))),
            "steps": steps, "evidence_to_capture": all_refs,
            "approval_required_before": sorted(approvals),
            "stop_conditions": [
                "A required value, approval, identifier, credential, URL, or policy is missing.",
                "The current approved UI or policy materially conflicts with this historical instruction.",
            ],
            "prohibitions": [
                "Never infer credentials, URLs, identifiers, groups, entitlements, roles, retention, owners, justification, approval, environment, or ticket IDs.",
                "Do not submit or make material changes without explicit approval.",
            ],
            "escalation": {"condition": "Missing or conflicting required information", "target": "Juan", "instruction": "Stop and request an approved value or human review."},
            "source_sessions": [source_session], "source_claims": [], "source_evidence": all_refs,
            "verification_state": procedure.get("verification_state", "SYNTHESIZED_UNREVIEWED"),
            "confidence": float(procedure.get("confidence", 0.0)),
        })
    return runbooks


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
    missing = sorted({str(value) for step in runbook.get("steps", [])
                      for value in step.get("required_values", [])
                      if value not in supplied_values or supplied_values.get(value) in (None, "")})
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


def embedding_ready(chunks: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    safe = []
    for chunk in chunks:
        try:
            confidence = float(chunk.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        prohibited = ("conflicting", "unreviewed_conflict", "contains_secret", "raw_transcript",
                      "raw_transcript_text", "raw_ocr", "raw_ocr_dump", "diagnostic",
                      "raw_execution_state", "kav_execution_state", "execution_state")
        if (chunk.get("curated") is not True or chunk.get("verification_status") not in {"HUMAN_REVIEWED", "CONFIRMED"}
                or any(chunk.get(key) for key in prohibited) or confidence < 0.8):
            continue
        content = str(chunk.get("content", ""))
        if _SENSITIVE.search(content):
            continue
        required = ("knowledge_id", "version", "project_id", "canonical_topic", "source_knowledge_ids",
                    "verification_status", "confidence", "provenance_pointers")
        if any(key not in chunk for key in required):
            continue
        safe.append({**chunk, "content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()})
    return bool(safe), safe
