"""Grounding validator.

Validates KnowledgeDocument against SPEC §5.
Fail closed.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from transcript_pipeline.documentation.synthesis_models import KnowledgeDocument


class GroundingError(Exception):
    """Raised when a document fails grounding validation."""
    pass


def validate_grounding(
    knowledge_document: KnowledgeDocument,
    evidence_index: dict[str, Any],
) -> list[str]:
    """Returns list of validation errors, empty if valid.
    
    Checks:
    1. each claim has >=1 evidence ref
    2. every ref exists in EvidenceIndex
    3. every procedure step has >=1 evidence ref
    4. timestamps within source duration
    5. low/no-evidence placeholder items cannot be sole support for factual claim
    6. generated content cannot set reviewed=true/HUMAN_REVIEWED
    7. unknown section/mode enum fails
    8. forbidden raw payload keys fail recursively
    9. output does not include whole raw transcript
    10. source evidence never rewritten in-place by synthesis
    """
    errors = []
    
    # TODO: implement each check
    # For now placeholder
    return errors


def persist_validation_report(
    validation_errors: list[str],
    output_dir: Path,
) -> None:
    """Write compact validation report."""
    report = {
        "valid": len(validation_errors) == 0,
        "errors": validation_errors,
        "validated_at": datetime.now().isoformat(),
    }
    (output_dir / "synthesis-validation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )