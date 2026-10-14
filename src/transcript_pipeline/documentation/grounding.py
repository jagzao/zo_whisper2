"""Fail-closed grounding validator (SPEC §5, PLAN WP-08).

A KnowledgeDocument is valid ONLY when:

1. each claim has >= 1 evidence ref;
2. every ref exists in the EvidenceIndex;
3. every procedure step has >= 1 evidence ref;
4. timestamps are within source duration;
5. low/no-evidence placeholder items cannot be the sole support for a
   factual claim;
6. generated content cannot set reviewed=true / HUMAN_REVIEWED;
7. unknown section/mode enum fails;
8. forbidden raw payload keys fail recursively;
9. the output does not include the whole raw transcript;
10. source evidence is never rewritten in-place by synthesis (the caller
    proves this by comparing the timeline identity around synthesis).

Invalid output NEVER reaches MANUAL/publisher (fail closed). A compact
validation report is persisted at manual/synthesis-validation.json.
No LLM verifier exists in this epic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.evidence import EvidenceTimeline
from transcript_pipeline.documentation.knowledge_models import KnowledgeDocument
from transcript_pipeline.documentation.modes import (
    DOCUMENTATION_MODES,
    SECTION_TYPES,
    VERIFICATION_STATUSES,
)
from transcript_pipeline.knowledge.policy import FORBIDDEN_PACKAGE_FIELDS

# A single output string field longer than this that also covers >=95% of the
# full raw transcript is treated as a whole-transcript dump (SPEC §5.9).
_WHOLE_TRANSCRIPT_OVERLAP = 0.95


@dataclass
class ValidationReport:
    valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    claim_count: int = 0
    section_count: int = 0
    procedure_count: int = 0
    evidence_ref_count: int = 0
    coerced_review_flags: int = 0
    source_evidence_mutated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "claimCount": self.claim_count,
            "sectionCount": self.section_count,
            "procedureCount": self.procedure_count,
            "evidenceRefCount": self.evidence_ref_count,
            "coercedReviewFlags": self.coerced_review_flags,
            "sourceEvidenceMutated": self.source_evidence_mutated,
        }


def validate_knowledge_document(
    document: KnowledgeDocument,
    timeline: EvidenceTimeline,
    *,
    full_transcript: str | None = None,
    source_evidence_mutated: bool = False,
) -> ValidationReport:
    report = ValidationReport(source_evidence_mutated=source_evidence_mutated)
    errors = report.errors
    index_ids = {str(ref.get("evidenceId")) for ref in document.evidence_index}
    timeline_by_id = timeline.by_id()
    duration = timeline.duration
    all_refs: set[str] = set()

    # 7. unknown mode/section enums fail.
    if document.documentation_mode not in DOCUMENTATION_MODES:
        errors.append(f"unknown documentation mode: {document.documentation_mode!r}")
    for section in document.sections:
        if section.section_type not in SECTION_TYPES:
            errors.append(f"{section.id}: unknown sectionType {section.section_type!r}")

    # 1. each claim has >= 1 evidence ref.
    for section in document.sections:
        for claim in section.claims:
            report.claim_count += 1
            if not claim.evidence_refs:
                errors.append(f"{claim.id}: claim without evidence refs")

    # 2. every ref exists in the evidence index AND the timeline.
    for ref in document.all_evidence_refs():
        all_refs.add(ref)
        if ref not in index_ids:
            errors.append(f"unknown evidence ref: {ref}")
        elif ref not in timeline_by_id:
            errors.append(f"evidence ref not in timeline: {ref}")

    # 3. every procedure step has >= 1 evidence ref.
    for procedure in document.procedures:
        report.procedure_count += 1
        if not procedure.steps:
            errors.append(f"{procedure.id}: procedure without steps")
        for step in procedure.steps:
            if not step.evidence_refs:
                errors.append(f"{procedure.id}: step {step.order} without evidence refs")

    # 4. timestamps within source duration.
    for ref in document.evidence_index:
        start = float(ref.get("timestampStart", 0.0))
        end = float(ref.get("timestampEnd", 0.0))
        if start < 0 or (duration > 0 and (start > duration + 0.001 or end > duration + 0.001)) or end < start:
            errors.append(f"{ref.get('evidenceId')}: timestamp outside source duration")

    # 5. placeholders cannot be the sole support for a factual claim.
    for section in document.sections:
        for claim in section.claims:
            placeholders = [r for r in claim.evidence_refs if r in timeline_by_id and timeline_by_id[r].is_placeholder()]
            non_placeholders = [r for r in claim.evidence_refs if r in timeline_by_id and not timeline_by_id[r].is_placeholder()]
            if claim.text and placeholders and not non_placeholders:
                errors.append(f"{claim.id}: only placeholder evidence supports a factual claim")

    # 6. generated content cannot set reviewed/HUMAN_REVIEWED.
    for section in document.sections:
        for claim in section.claims:
            if claim.verification_status == "HUMAN_REVIEWED":
                errors.append(f"{claim.id}: generated claim marked HUMAN_REVIEWED")
    for ref in document.evidence_index:
        if ref.get("reviewed") is True:
            # Only human-reviewed source evidence (steps.json reviewed flag)
            # may carry reviewed=true; synthesis must not have set it.
            item = timeline_by_id.get(str(ref.get("evidenceId")))
            if item is None or not item.reviewed:
                errors.append(f"{ref.get('evidenceId')}: synthesis set reviewed=true")

    # 8. forbidden raw payload keys fail recursively.
    _scan_forbidden(document.to_dict(), "document", errors)

    # 9. output does not include the whole raw transcript.
    if full_transcript:
        normalized = " ".join(full_transcript.split())
        if len(normalized) > 200:
            for text_field in _iter_string_fields(document.to_dict()):
                if normalized in text_field or (
                    len(text_field) > len(normalized) * _WHOLE_TRANSCRIPT_OVERLAP
                    and normalized[:200] in text_field
                    and _overlap_ratio(normalized, text_field) >= _WHOLE_TRANSCRIPT_OVERLAP
                ):
                    errors.append("whole raw transcript embedded in output")
                    break

    # 10. source evidence never rewritten in-place by synthesis.
    if source_evidence_mutated:
        errors.append("source evidence was mutated in-place by synthesis")

    report.section_count = len(document.sections)
    report.evidence_ref_count = len(all_refs)
    report.valid = not errors
    return report


def write_validation_report(manual_dir: Path, report: ValidationReport) -> Path:
    manual_dir.mkdir(parents=True, exist_ok=True)
    path = manual_dir / "synthesis-validation.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_PACKAGE_FIELDS:
                errors.append(f"forbidden raw payload field in {path}: {key}")
            _scan_forbidden(child, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]", errors)


def _iter_string_fields(value: Any):
    if isinstance(value, str):
        if value:
            yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _iter_string_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_string_fields(child)


def _overlap_ratio(normalized_transcript: str, candidate: str) -> float:
    candidate_normalized = " ".join(candidate.split())
    if not normalized_transcript:
        return 0.0
    words = normalized_transcript.split()
    if not words:
        return 0.0
    contained = sum(1 for word in words if word in candidate_normalized)
    return contained / len(words)


def known_verification_statuses() -> tuple[str, ...]:
    return VERIFICATION_STATUSES
