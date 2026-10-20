"""Publish-policy validation for knowledge packages (SPEC §1/§2/§3).

The policy layer is deliberately separate from the model layer: the same
rules gate config validation (projects.py), package building, and the
producer-side contract fixtures, so a package can never be built that the
Zavi import boundary would have to reject for scope reasons.
"""
from __future__ import annotations

from transcript_pipeline.knowledge.models import (
    KNOWLEDGE_ACTIONABILITY_VALUES,
    KNOWLEDGE_ARTIFACT_TYPES,
    KNOWLEDGE_SCOPES,
)

CONFIDENTIAL = "confidential"

# Fields that must never appear in a package: whole raw transcript/VTT/media
# payloads are excluded from publication (SPEC §3 provenance, security
# negative tests).
FORBIDDEN_PACKAGE_FIELDS = frozenset(
    {
        "rawTranscript",
        "transcript",
        "vtt",
        "rawVtt",
        "mediaBytes",
        "mediaPath",
        "media",
    }
)


class PublishPolicyError(ValueError):
    """Raised when a package/config violates the frozen publish policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate_publish_context(
    *,
    scope: str,
    project_id: str | None,
    domain: str,
    data_classification: str,
) -> None:
    """Validates the scope/classification combination for publication.

    - scope must be a known enum value;
    - PROJECT requires project_id (fail closed);
    - GLOBAL requires an explicit domain;
    - confidential + GLOBAL is invalid;
    - scope is never inferred from classification (caller passes it).
    """
    if scope not in KNOWLEDGE_SCOPES:
        raise PublishPolicyError(f"unknown scope: {scope!r}")
    if scope == "PROJECT" and (not project_id or not str(project_id).strip()):
        raise PublishPolicyError("PROJECT scope requires projectId")
    if not domain or not str(domain).strip():
        raise PublishPolicyError("domain is required")
    if scope == "GLOBAL" and data_classification == CONFIDENTIAL:
        raise PublishPolicyError("confidential classification cannot be published with GLOBAL scope")


def validate_enums(*, artifact_type: str, actionability: str) -> None:
    if artifact_type not in KNOWLEDGE_ARTIFACT_TYPES:
        raise PublishPolicyError(f"unknown artifactType: {artifact_type!r}")
    if actionability not in KNOWLEDGE_ACTIONABILITY_VALUES:
        raise PublishPolicyError(f"unknown actionability: {actionability!r}")


def assert_no_forbidden_payload(package_payload: dict) -> None:
    """Fail-closed guard: a package carrying whole raw transcript/VTT/media
    fields anywhere (recursively, including inside nested evidence dicts and
    lists) must never reach the outbox.

    Bounded evidence such as `transcriptExcerpt` stays allowed: only the
    whole raw fields in FORBIDDEN_PACKAGE_FIELDS are rejected.
    """
    _scan_for_forbidden(package_payload, "package")


def _scan_for_forbidden(value: object, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_PACKAGE_FIELDS:
                raise PublishPolicyError(f"forbidden raw payload field in {path}: {key}")
            _scan_for_forbidden(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_for_forbidden(child, f"{path}[{index}]")
