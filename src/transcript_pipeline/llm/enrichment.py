"""Single entry point for every outbound AI call in the pipeline.

Before this module, each handler called `PrivacyGuard.check()`,
`redact_secrets()`, and the provider separately — easy to get the
combination wrong (see the `project_config=None` bug this replaced) or to
skip a check entirely (the frame-vision call site that never checked
`FRAME_DESCRIPTIONS`/`ALLOW_FRAME_UPLOAD` at all). `AIEnrichmentService` is
the one place that combination is assembled, so every caller gets the same
policy for free instead of having to remember it.

Frame/image policy (`_check_frame_policy`), most restrictive first:
- `FRAME_DESCRIPTIONS=false` blocks ANY visual analysis, local or remote —
  this is a "do we do this at all" switch, not a network-boundary one.
  Applies to video frames, screenshots, and document-embedded images alike.
- `PrivacyGuard.check()` blocks a remote call when `ALLOW_EXTERNAL_LLM` is
  off, or when the project is `data_classification: confidential`.
- `ALLOW_IMAGE_UPLOAD=false` additionally blocks a remote call even when
  the above two would otherwise allow it — text generation and image
  upload are separate permissions for a remote provider. (Deprecated
  alias: `ALLOW_FRAME_UPLOAD`, still read if `ALLOW_IMAGE_UPLOAD` is unset.)
Local providers never leave the machine, so only the first check applies
to them.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from transcript_pipeline.llm.guard import ExternalLLMBlockedError, PrivacyGuard
from transcript_pipeline.llm.openai_compatible import OpenAICompatibleProvider
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.llm.redaction import redact_secrets
from transcript_pipeline.settings import Settings


class AIEnrichmentService:
    def __init__(self, provider: OpenAICompatibleProvider, guard: PrivacyGuard, settings: Settings):
        self._provider = provider
        self._guard = guard
        self._settings = settings

    def _is_remote(self) -> bool:
        return self._provider.provider_type is LLMProviderType.REMOTE

    def summarize(
        self, text: str, project_config: dict[str, Any] | None = None, system_prompt: str | None = None
    ) -> str:
        self._guard.check(self._provider, project_config)
        # A local provider never leaves the machine — nothing to redact
        # against, and redacting anyway would just hide real content from
        # a model that's already fully on-device.
        safe_text = redact_secrets(text) if self._is_remote() else text
        return self._provider.generate_summary(safe_text, system_prompt=system_prompt)

    def describe_frame_with_prompt(
        self,
        image_path: str | Path,
        prompt: str,
        project_config: dict[str, Any] | None = None,
        *,
        max_tokens: int = 500,
        temperature: float = 0.2,
    ) -> str:
        self._check_frame_policy(project_config)
        safe_prompt = redact_secrets(prompt) if self._is_remote() else prompt
        return self._provider.describe_frame_with_prompt(
            image_path, safe_prompt, max_tokens=max_tokens, temperature=temperature
        )

    def describe_frames_for_tutorial(
        self, frames_dir: str | Path, mapping: dict, project_config: dict[str, Any] | None = None
    ) -> dict:
        self._check_frame_policy(project_config)
        # describe_frames_for_tutorial() also has its own internal
        # FRAME_DESCRIPTIONS short-circuit — kept as defense in depth, not
        # removed, so any other direct caller of the provider stays safe.
        safe_mapping = mapping
        if self._is_remote():
            safe_mapping = copy.deepcopy(mapping)
            for frame_info in safe_mapping.values():
                if isinstance(frame_info, dict) and "full_text" in frame_info:
                    frame_info["full_text"] = redact_secrets(frame_info["full_text"])
        return self._provider.describe_frames_for_tutorial(frames_dir, safe_mapping)

    def allow_document_llm(self, project_config: dict[str, Any] | None = None) -> bool:
        """For callers (MarkItDown document scanning) that need a bool to
        decide whether to construct an LLM-backed client at all, rather
        than a call they can wrap in try/except themselves.

        Uses the same frame/image policy as the video-frame path — a
        document's embedded images going to a vision model is the same
        outbound-image risk as a video frame or screenshot, so it shares
        one gate (`FRAME_DESCRIPTIONS` → `PrivacyGuard` →
        `ALLOW_IMAGE_UPLOAD` if remote) instead of only checking the guard."""
        try:
            self._check_frame_policy(project_config)
            return True
        except ExternalLLMBlockedError:
            return False

    def _check_frame_policy(self, project_config: dict[str, Any] | None) -> None:
        if not self._settings.frame_descriptions:
            raise ExternalLLMBlockedError("FRAME_DESCRIPTIONS is disabled — refusing visual analysis.")
        self._guard.check(self._provider, project_config)
        if self._provider.provider_type is LLMProviderType.REMOTE and not self._settings.allow_image_upload:
            raise ExternalLLMBlockedError(
                "ALLOW_IMAGE_UPLOAD is disabled — refusing to send image bytes to a remote provider."
            )
