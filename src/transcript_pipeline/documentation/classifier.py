"""DocumentationMode resolver (SPEC §2/§8, EPIC "Mode authority").

Authority order (frozen):
1. explicit project `documentation.mode` (anything except AUTO);
2. explicit `second_brain.default_artifact_type` mapping;
3. allowed synthesis classifier when mode=AUTO;
4. safe fallback REFERENCE.

Filename suffixes (e.g. `_tutorial`) are hints only and never participate in
resolution — they must never override explicit project configuration.

For AUTO the classifier receives compact TEXTUAL evidence only (no
screenshots) unless explicitly allowed, and MUST return structured JSON.
Any classifier failure, unavailability or invalid output falls back to
REFERENCE with a typed reason — never an exception, never a guess.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from transcript_pipeline.documentation.evidence import EvidenceTimeline
from transcript_pipeline.documentation.modes import (
    DOCUMENTATION_MODES,
    MODE_FOR_ARTIFACT_TYPE,
    normalize_documentation_config,
)

logger = logging.getLogger(__name__)

CLASSIFIER_FALLBACK_REASON = "no_authority_resolved"
CLASSIFIER_UNAVAILABLE_REASON = "classifier_unavailable"
CLASSIFIER_INVALID_REASON = "classifier_invalid_output"


class ModeClassifier(Protocol):
    def classify(self, textual_evidence: str) -> str: ...


@dataclass(frozen=True)
class ModeResolution:
    mode: str
    source: str  # explicit_config | artifact_mapping | classifier | fallback
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"mode": self.mode, "source": self.source, "reason": self.reason}


def resolve_documentation_mode(
    project_config: dict | None,
    timeline: EvidenceTimeline | None = None,
    *,
    classifier: ModeClassifier | None = None,
    filename: str | None = None,
) -> ModeResolution:
    """Resolves the DocumentationMode for one recording.

    `filename` is accepted for call-site ergonomics and deliberately ignored:
    filename suffixes are hints that MUST NOT override explicit project
    configuration (EPIC), so they take no part in resolution at all.
    """
    del filename  # explicit no-op: never authoritative

    documentation = (project_config or {}).get("documentation")
    cfg = normalize_documentation_config(documentation if isinstance(documentation, dict) else None)
    explicit_mode = cfg["mode"] if documentation else None

    # 1. explicit documentation.mode (a non-AUTO explicit value wins).
    if isinstance(explicit_mode, str) and explicit_mode in DOCUMENTATION_MODES and explicit_mode != "AUTO":
        return ModeResolution(mode=explicit_mode, source="explicit_config", reason="documentation.mode")

    # 2. explicit second_brain.default_artifact_type mapping.
    second_brain = (project_config or {}).get("second_brain")
    if isinstance(second_brain, dict):
        artifact_type = second_brain.get("default_artifact_type")
        if isinstance(artifact_type, str) and artifact_type in MODE_FOR_ARTIFACT_TYPE:
            return ModeResolution(
                mode=MODE_FOR_ARTIFACT_TYPE[artifact_type],
                source="artifact_mapping",
                reason=f"second_brain.default_artifact_type={artifact_type}",
            )

    # 3. allowed classifier for AUTO (compact textual evidence only).
    if explicit_mode == "AUTO" and cfg["synthesis_enabled"] and classifier is not None and timeline is not None:
        try:
            textual = compact_textual_evidence(timeline)
            raw = classifier.classify(textual)
            mode = _parse_classifier_json(raw)
        except Exception as e:  # noqa: BLE001 - classifier failure must fall back, never raise
            logger.info("[DOCS-V2] mode classifier failed (%s) — REFERENCE fallback", type(e).__name__)
            return ModeResolution(mode="REFERENCE", source="fallback", reason=CLASSIFIER_UNAVAILABLE_REASON)
        if mode is None:
            return ModeResolution(mode="REFERENCE", source="fallback", reason=CLASSIFIER_INVALID_REASON)
        return ModeResolution(mode=mode, source="classifier", reason="auto_classified")

    # 4. safe fallback.
    return ModeResolution(mode="REFERENCE", source="fallback", reason=CLASSIFIER_FALLBACK_REASON)


def _parse_classifier_json(raw: str) -> str | None:
    """Structured output only: `{"mode": "KT_SESSION"}` (fenced JSON allowed).
    Free-form text is rejected."""
    text = str(raw).strip()
    if text.startswith("```"):
        text = text.strip("` \n")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    mode = data.get("mode")
    if isinstance(mode, str) and mode in DOCUMENTATION_MODES and mode != "AUTO":
        return mode
    return None


def compact_textual_evidence(timeline: EvidenceTimeline, *, max_chars: int = 6000) -> str:
    """Compact textual view of the evidence facts for classification.
    Chronological, deduped excerpts, bounded. No screenshots are attached."""
    parts: list[str] = []
    total = 0
    for item in timeline.facts():
        excerpt = item.transcript_excerpt or item.ocr_excerpt or ""
        if not excerpt:
            continue
        line = f"[{item.evidence_id}] {excerpt}"
        if total + len(line) > max_chars:
            break
        parts.append(line)
        total += len(line)
    return "\n".join(parts)


_CLASSIFIER_SYSTEM_PROMPT = (
    "You classify recorded sessions into a documentation mode. "
    "You receive compact chronological textual evidence excerpts with evidence ids. "
    'Return ONLY a JSON object like {"mode": "KT_SESSION"} where mode is one of: '
    "TUTORIAL, KT_SESSION, PROCESS_WALKTHROUGH, MEETING, ARCHITECTURE, INCIDENT, REFERENCE. "
    "No Markdown, no code fences, no extra fields."
)


class LLMModeClassifier:
    """Classifier for mode=AUTO using the SAME provider and privacy boundary
    as synthesis. Structured output only; any failure surfaces as an
    exception to the resolver, which falls back to REFERENCE with a typed
    reason (never a crash, never a guess)."""

    def __init__(self, provider: Any, guard: Any, project_config: dict | None) -> None:
        self._provider = provider
        self._guard = guard
        self._project_config = project_config

    def classify(self, textual_evidence: str) -> str:
        # Same privacy boundary as every other outbound call: checked before
        # the request (remote + confidential => blocked => typed fallback).
        self._guard.check(self._provider, self._project_config)
        return self._provider.generate_summary(
            textual_evidence,
            system_prompt=_CLASSIFIER_SYSTEM_PROMPT,
            max_tokens=32,
            temperature=0,
        )
