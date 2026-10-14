"""Grounded synthesis service (SPEC §7, PLAN WP-07).

One domain-level API:

    SynthesisService(provider, guard).synthesize(evidence_timeline, mode, project_config)
        -> SynthesisResult

Behavior (frozen):
- JSON structured prompt only; free-form Markdown is never authoritative;
- privacy: the existing PrivacyGuard blocks remote providers for
  confidential projects BEFORE any request leaves the machine (DV2-04);
  local providers are allowed under the existing local policy (DV2-05);
- deterministic temperature 0;
- bounded calls: one provider call per synthesis block (compactor-capped),
  plus AT MOST one schema-repair retry per failed response, same
  provider/model — no recursive repair loop (DV2-45/46);
- compact model metadata, no secrets in the document;
- provider/model output is coerced: generated claims can never carry
  HUMAN_REVIEWED or reviewed=true (DV2-18);
- the prompt explicitly requires evidence ids on every claim/step.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from transcript_pipeline.documentation.compaction import (
    DEFAULT_HARD_BLOCK_CHARS,
    DEFAULT_MAX_BLOCKS,
    DEFAULT_TARGET_BLOCK_CHARS,
    build_synthesis_blocks,
)
from transcript_pipeline.documentation.evidence import EvidenceTimeline
from transcript_pipeline.documentation.knowledge_models import (
    GlossaryEntry,
    KnowledgeClaim,
    KnowledgeDocument,
    KnowledgeSection,
    SynthesisMetadata,
    SynthesizedProcedure,
    SynthesizedStep,
    coerce_generated_claim,
)
from transcript_pipeline.documentation.modes import MODE_SECTION_TEMPLATES, section_sort_key

logger = logging.getLogger(__name__)

STATUS_OK = "SYNTHESIS_READY"
STATUS_UNAVAILABLE = "SYNTHESIS_NOT_AVAILABLE"
STATUS_BLOCKED_PRIVACY = "SYNTHESIS_BLOCKED_PRIVACY"
STATUS_INVALID = "SYNTHESIS_INVALID"

_MAX_OUTPUT_TOKENS = 4000

_SYSTEM_PROMPT_TEMPLATE = """You are a technical documentation synthesizer for mode {mode}.
You receive ONE chronological evidence block of a recorded session (transcript excerpts and deduplicated on-screen OCR text, each prefixed with its evidence id like [E-001]).

Return ONLY a JSON object (no Markdown, no code fences) with this exact shape:
{{
  "sections": [
    {{
      "sectionType": "<one of: {section_types}>",
      "title": "short semantic title",
      "summary": "1-3 sentence synthesis",
      "claims": [
        {{"text": "factual claim grounded in this block", "evidenceIds": ["E-001"], "tags": ["optional"]}}
      ]
    }}
  ],
  "procedures": [
    {{
      "title": "procedure title",
      "purpose": "why/when to perform it",
      "prerequisites": ["..."],
      "steps": [{{"instruction": "one ordered action", "evidenceIds": ["E-002"]}}],
      "expectedOutcomes": ["..."]
    }}
  ],
  "glossary": [{{"term": "...", "definition": "...", "evidenceIds": ["E-003"]}}]
}}

Rules (violations make the output invalid):
- Every claim and every procedure step MUST cite at least one evidenceId from this block's evidence ids: {block_evidence_ids}.
- Only produce "procedures" when this block contains explicit ORDERED operational actions. Otherwise use an empty list.
- Preferred section types for mode {mode}: {preferred_sections}.
- Do NOT invent facts, timestamps, names, or section types.
- Do NOT include any "reviewed", "humanReviewed", or verification status fields: generated content is never human reviewed.
- Output must fit within {max_claims} claims and {max_procedures} procedures total.
"""

_REPAIR_PROMPT = (
    "Your previous response was rejected because it was not valid JSON matching the schema "
    "(error: {error}). Return ONLY the corrected JSON object. No Markdown, no commentary, "
    "no code fences, no fields outside the schema."
)


@dataclass
class SynthesisResult:
    status: str
    document: KnowledgeDocument | None = None
    errors: list[str] = field(default_factory=list)
    invocation_count: int = 0
    provider_type: str = "unknown"
    model: str = "unknown"
    coerced_review_flags: int = 0

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK and self.document is not None


class SynthesisService:
    """Provider-bound synthesis service. `provider` is any OpenAI-compatible
    object exposing `generate_summary(text, system_prompt=..., max_tokens=...,
    temperature=...)` and `provider_type`; `guard` is the shared PrivacyGuard.
    Either may be None (=> typed SYNTHESIS_NOT_AVAILABLE)."""

    def __init__(self, provider: Any | None, guard: Any | None, *, model_name: str | None = None) -> None:
        self._provider = provider
        self._guard = guard
        self._model_name = model_name

    def synthesize(
        self,
        evidence_timeline: EvidenceTimeline,
        mode: str,
        project_config: dict | None,
    ) -> SynthesisResult:
        if self._provider is None or self._guard is None:
            return SynthesisResult(status=STATUS_UNAVAILABLE, errors=["no synthesis provider configured"])

        # Privacy boundary BEFORE any request (DV2-04): remote provider on a
        # confidential project is blocked exactly like every other outbound
        # LLM call; local providers pass (DV2-05).
        try:
            self._guard.check(self._provider, project_config)
        except Exception as e:  # noqa: BLE001 - guard raises ExternalLLMBlockedError
            return SynthesisResult(
                status=STATUS_BLOCKED_PRIVACY,
                errors=[f"privacy:{type(e).__name__}"],
                provider_type=_provider_type_name(self._provider),
            )

        compaction = build_synthesis_blocks(
            evidence_timeline,
            target_chars=DEFAULT_TARGET_BLOCK_CHARS,
            hard_chars=DEFAULT_HARD_BLOCK_CHARS,
            max_blocks=DEFAULT_MAX_BLOCKS,
        ).build()
        if not compaction.blocks:
            return SynthesisResult(
                status=STATUS_UNAVAILABLE,
                errors=["no evidence facts to synthesize"],
                provider_type=_provider_type_name(self._provider),
            )

        invocations = 0
        errors: list[str] = []
        coerced = 0
        fragments: list[dict[str, Any]] = []

        for block in compaction.blocks:
            system_prompt = self._system_prompt(mode, block.evidence_ids)
            user_payload = json.dumps(
                {
                    "mode": mode,
                    "block": block.to_prompt_dict(),
                    "evidenceCatalog": [
                        {
                            "evidenceId": item.evidence_id,
                            "timestampRange": [item.timestamp_start, item.timestamp_end],
                            "excerpt": (item.transcript_excerpt or item.ocr_excerpt or "")[:600],
                        }
                        for item in evidence_timeline.facts()
                        if item.evidence_id in set(block.evidence_ids)
                    ],
                },
                ensure_ascii=False,
            )

            raw, block_errors, used, coerced_count = self._request_block(system_prompt, user_payload)
            invocations += used
            coerced += coerced_count
            if block_errors:
                errors.extend(block_errors)
                continue
            try:
                fragments.append(json.loads(raw))
            except ValueError as e:
                errors.append(f"block-{block.index}:unparseable:{type(e).__name__}")

        if not fragments:
            return SynthesisResult(
                status=STATUS_INVALID,
                errors=errors or ["no valid synthesis fragments"],
                invocation_count=invocations,
                provider_type=_provider_type_name(self._provider),
                coerced_review_flags=coerced,
            )

        document = self._merge_fragments(fragments, evidence_timeline, mode, invocations)
        return SynthesisResult(
            status=STATUS_OK,
            document=document.document,
            errors=errors,
            invocation_count=invocations,
            provider_type=_provider_type_name(self._provider),
            model=self._model_name or _provider_model_name(self._provider),
            coerced_review_flags=coerced + document.coerced_claims,
        )

    # ── internals ────────────────────────────────────────────────────────

    def _system_prompt(self, mode: str, block_evidence_ids: tuple[str, ...]) -> str:
        preferred = ", ".join(MODE_SECTION_TEMPLATES.get(mode, MODE_SECTION_TEMPLATES["AUTO"]))
        from transcript_pipeline.documentation.modes import SECTION_TYPES

        return _SYSTEM_PROMPT_TEMPLATE.format(
            mode=mode,
            section_types=", ".join(SECTION_TYPES),
            block_evidence_ids=", ".join(block_evidence_ids),
            preferred_sections=preferred,
            max_claims=12,
            max_procedures=2,
        )

    def _request_block(
        self, system_prompt: str, user_payload: str
    ) -> tuple[str, list[str], int, int]:
        """One bounded request + at most ONE schema-repair retry (DV2-45/46).
        Returns (raw_json, errors, invocation_count, coerced_review_flags)."""
        provider = self._provider
        if provider is None:
            return "", ["provider_unavailable"], 0, 0
        try:
            raw = provider.generate_summary(
                user_payload, system_prompt=system_prompt,
                max_tokens=_MAX_OUTPUT_TOKENS, temperature=0,
            )
        except Exception as e:  # noqa: BLE001 - transport failure => typed unavailable signal
            return "", [f"provider:{type(e).__name__}"], 1, 0

        valid, error, coerced = _validate_fragment_shape(raw)
        if valid:
            return raw, [], 1, coerced

        # Exactly one bounded repair retry, same provider/model.
        repair_prompt = _REPAIR_PROMPT.format(error=error)
        try:
            raw = provider.generate_summary(
                repair_prompt, system_prompt=system_prompt,
                max_tokens=_MAX_OUTPUT_TOKENS, temperature=0,
            )
        except Exception as e:  # noqa: BLE001
            return "", [f"provider:{type(e).__name__}", "repair_failed"], 2, coerced
        valid, error, coerced2 = _validate_fragment_shape(raw)
        if valid:
            return raw, [], 2, coerced + coerced2
        return "", [f"malformed_after_repair:{error}"], 2, coerced + coerced2

    def _merge_fragments(
        self,
        fragments: list[dict[str, Any]],
        timeline: EvidenceTimeline,
        mode: str,
        invocations: int,
    ) -> _MergedDocument:
        sections: list[KnowledgeSection] = []
        procedures: list[SynthesizedProcedure] = []
        glossary: list[GlossaryEntry] = []
        claim_no = 0
        section_no = 0
        procedure_no = 0
        coerced_claims = 0

        for fragment in fragments:
            for raw_section in fragment.get("sections", []) or []:
                claim_no, claims, section_coerced = _parse_claims(raw_section.get("claims", []), claim_no)
                coerced_claims += section_coerced
                section_no += 1
                sections.append(KnowledgeSection(
                    id=f"section-{section_no:02d}",
                    section_type=str(raw_section.get("sectionType", "REFERENCE")).strip().upper(),
                    title=str(raw_section.get("title", "")).strip() or f"Section {section_no}",
                    summary=str(raw_section.get("summary", "")).strip(),
                    claims=claims,
                    evidence_refs=tuple(
                        ref for claim in claims for ref in claim.evidence_refs
                    ),
                    order=section_no,
                ))
            for raw_procedure in fragment.get("procedures", []) or []:
                procedure_no += 1
                steps = []
                for i, raw_step in enumerate(raw_procedure.get("steps", []) or [], start=1):
                    steps.append(SynthesizedStep(
                        order=int(raw_step.get("order", i) or i),
                        instruction=str(raw_step.get("instruction", "")).strip(),
                        evidence_refs=tuple(str(r) for r in raw_step.get("evidenceIds", [])),
                        semantic_action=raw_step.get("semanticAction"),
                        semantic_target=raw_step.get("semanticTarget"),
                    ))
                procedures.append(SynthesizedProcedure(
                    id=f"procedure-{procedure_no:03d}",
                    title=str(raw_procedure.get("title", "")).strip() or f"Procedure {procedure_no}",
                    purpose=str(raw_procedure.get("purpose", "")).strip(),
                    prerequisites=tuple(str(p) for p in raw_procedure.get("prerequisites", [])),
                    steps=tuple(steps),
                    expected_outcomes=tuple(str(o) for o in raw_procedure.get("expectedOutcomes", [])),
                    evidence_refs=tuple(step_evidence for step in steps for step_evidence in step.evidence_refs),
                ))
            for raw_entry in fragment.get("glossary", []) or []:
                glossary.append(GlossaryEntry(
                    term=str(raw_entry.get("term", "")).strip(),
                    definition=str(raw_entry.get("definition", "")).strip(),
                    evidence_refs=tuple(str(r) for r in raw_entry.get("evidenceIds", [])),
                ))

        # Deterministic mode-template ordering (stable sort keeps arrival
        # order within the same section type).
        sections.sort(key=lambda s: (section_sort_key(mode, s.section_type), s.order))
        for new_order, section in enumerate(sections, start=1):
            sections[new_order - 1] = replace(section, order=new_order)

        evidence_index = [item.to_ref() for item in timeline.items]
        document = KnowledgeDocument(
            document_id=f"kd-{mode.lower()}-{timeline.source_hash[7:19]}",
            source=timeline.source_media,
            documentation_mode=mode,
            title=timeline.source_media or "Untitled session",
            executive_summary=_executive_summary(sections),
            sections=sections,
            procedures=procedures,
            glossary=glossary,
            evidence_index=evidence_index,
            synthesis=SynthesisMetadata(
                provider_type=_provider_type_name(self._provider),
                model=self._model_name or _provider_model_name(self._provider),
                generated_at=datetime.now(timezone.utc).isoformat(),
                status="SYNTHESIZED_UNREVIEWED",
                input_hash=timeline.source_hash,
                invocation_count=invocations,
            ),
        )
        return _MergedDocument(document=document, coerced_claims=coerced_claims)


@dataclass
class _MergedDocument:
    document: KnowledgeDocument
    coerced_claims: int = 0


def _parse_claims(raw_claims: list[Any], start_no: int) -> tuple[int, tuple[KnowledgeClaim, ...], int]:
    claims: list[KnowledgeClaim] = []
    no = start_no
    coerced = 0
    for raw in raw_claims:
        no += 1
        claim = KnowledgeClaim(
            id=f"claim-{no:03d}",
            text=str(raw.get("text", "")).strip(),
            evidence_refs=tuple(str(r) for r in raw.get("evidenceIds", [])),
            evidence_confidence=str(raw.get("evidenceConfidence", "low")),
            verification_status=str(raw.get("verificationStatus", "SYNTHESIZED_UNREVIEWED")),
            tags=tuple(str(t) for t in raw.get("tags", [])),
        )
        coerced_claim = coerce_generated_claim(claim)
        if coerced_claim.verification_status != claim.verification_status:
            coerced += 1
        claims.append(coerced_claim)
    return no, tuple(claims), coerced


def _executive_summary(sections: list[KnowledgeSection]) -> str:
    for section in sections:
        if section.section_type == "EXECUTIVE_SUMMARY" and (section.summary or section.claims):
            if section.summary:
                return section.summary
            return " ".join(claim.text for claim in section.claims)
    return ""


def _validate_fragment_shape(raw: str) -> tuple[bool, str, int]:
    """Structural pre-check of one provider response: must be a JSON object
    (no free-form prose). Counts coerced review flags. Returns
    (valid, error, coerced_review_flags)."""
    coerced = 0
    text = str(raw).strip()
    if not text.startswith("{"):
        return False, "not a JSON object (free-form response rejected)", coerced
    try:
        data = json.loads(text)
    except ValueError as e:
        return False, f"invalid JSON: {type(e).__name__}", coerced
    if not isinstance(data, dict):
        return False, "JSON root is not an object", coerced

    def _scan(value: Any) -> None:
        nonlocal coerced
        if isinstance(value, dict):
            for key in list(value.keys()):
                if key.lower() in ("reviewed", "humanreviewed", "verificationstatus"):
                    coerced += 1
            for child in value.values():
                _scan(child)
        elif isinstance(value, list):
            for child in value:
                _scan(child)

    _scan(data)
    return True, "", coerced


def _provider_type_name(provider: Any) -> str:
    provider_type = getattr(provider, "provider_type", None)
    return str(getattr(provider_type, "value", provider_type) or "unknown")


def _provider_model_name(provider: Any) -> str:
    for attr in ("model", "llm_model", "_model"):
        value = getattr(provider, attr, None)
        if isinstance(value, str) and value:
            return value
    settings = getattr(provider, "_settings", None)
    value = getattr(settings, "llm_model", None)
    return str(value) if isinstance(value, str) and value else "unknown"


def default_synthesis_service() -> SynthesisService:
    """Builds the production service from the shared settings/provider
    infrastructure when available; otherwise returns an unavailable service
    (typed SYNTHESIS_NOT_AVAILABLE, never an exception)."""
    try:
        from transcript_pipeline.llm.guard import PrivacyGuard
        from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
        from transcript_pipeline.settings import SETTINGS

        provider = OpenAICompatibleProvider(SETTINGS)
        return SynthesisService(provider, PrivacyGuard(SETTINGS), model_name=SETTINGS.llm_model)
    except Exception as e:  # noqa: BLE001 - optional LLM stack must never break documentation
        logger.info("[DOCS-V2] synthesis provider unavailable: %s", type(e).__name__)
        return SynthesisService(None, None)
