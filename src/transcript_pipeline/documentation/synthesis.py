"""Synthesis provider service.

Reuses existing provider/privacy infrastructure.
One bounded call per block, JSON structured output, one schema repair retry.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from dataclasses import asdict
from typing import Any

from transcript_pipeline.documentation.classifier import resolve_documentation_mode
from transcript_pipeline.documentation.compaction import SynthesisBlock, compact_evidence_timeline
from transcript_pipeline.documentation.synthesis_models import KnowledgeDocument, SynthesisMetadata
from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
from transcript_pipeline.settings import SETTINGS

logger = logging.getLogger(__name__)


class SynthesisResult:
    def __init__(
        self,
        knowledge_document: KnowledgeDocument | None = None,
        status: str = "pending",
        error: str | None = None,
        metadata: dict | None = None,
    ):
        self.knowledge_document = knowledge_document
        self.status = status
        self.error = error
        self.metadata = metadata


def synthesize(
    evidence_timeline: dict,
    mode: str,
    project_config: dict | None,
) -> SynthesisResult:
    """Main synthesis API.
    
    Returns SynthesisResult with KnowledgeDocument if synthesis succeeded.
    """
    # Check if synthesis enabled
    if project_config and "documentation" in project_config:
        doc_config = project_config["documentation"]
        if isinstance(doc_config, dict) and doc_config.get("synthesis_enabled", True) is False:
            return SynthesisResult(
                status="synthesis_disabled",
                error="synthesis_enabled is false",
            )
    
    # Compact evidence into blocks
    blocks = compact_evidence_timeline(evidence_timeline)
    if not blocks:
        return SynthesisResult(
            status="invalid_input",
            error="No evidence blocks",
        )
    
    # Prepare provider
    try:
        provider = OpenAICompatibleProvider(SETTINGS)
        guard = PrivacyGuard(SETTINGS)
        guard.check(provider, project_config)
    except ExternalLLMBlockedError as e:
        return SynthesisResult(
            status="blocked_privacy",
            error=str(e),
        )
    except Exception as e:
        return SynthesisResult(
            status="provider_error",
            error=str(e),
        )
    
    # Build prompt with structured JSON schema request
    prompt = _build_synthesis_prompt(blocks, mode, project_config)
    
    # One bounded call + one schema repair retry max
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            response = provider.complete(
                prompt,
                temperature=0,
                max_tokens=8000,
                json_mode=True,
            )
            # Parse JSON response
            parsed = json.loads(response)
            # Validate against schema (placeholder)
            knowledge_doc = KnowledgeDocument(
                schemaVersion=2,
                documentationMode=mode,
                synthesis=SynthesisMetadata(
                    providerType=provider.provider_type.value,
                    model=provider.model,
                    generatedAt=datetime.now(),
                    status="success",
                    inputHash="TODO",
                ),
            )
            return SynthesisResult(
                knowledge_document=knowledge_doc,
                status="success",
            )
        except json.JSONDecodeError as e:
            if attempt == 0:
                logger.warning("[SYNTHESIS] Malformed JSON, retrying once")
                continue
            else:
                return SynthesisResult(
                    status="invalid_json",
                    error=str(e),
                )
        except Exception as e:
            return SynthesisResult(
                status="synthesis_failed",
                error=str(e),
            )
    
    return SynthesisResult(
        status="max_attempts_exceeded",
        error="Failed after retry",
    )


def _build_synthesis_prompt(blocks: list[SynthesisBlock], mode: str, project_config: dict | None) -> str:
    """Construct structured prompt for synthesis provider."""
    # TODO: implement proper prompt per SPEC
    return json.dumps({
        "task": "synthesize_documentation",
        "mode": mode,
        "blocks": [asdict(b) for b in blocks],
    }, indent=2)