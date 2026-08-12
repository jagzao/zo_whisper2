"""Privacy boundary for outbound LLM calls.

Nothing gets sent to a remote provider just because an API key happens to
be configured. `PrivacyGuard.check()` must be called before any request
that leaves the machine — it raises `ExternalLLMBlockedError` if
`ALLOW_EXTERNAL_LLM` is off, or if the matched project is marked
`data_classification: confidential`. Local providers (Ollama, LM Studio —
see `LLMProviderType.LOCAL`) are never blocked by this guard.
"""

from __future__ import annotations

from typing import Any

from transcript_pipeline.llm.provider import LLMProvider, LLMProviderType
from transcript_pipeline.settings import Settings


class ExternalLLMBlockedError(RuntimeError):
    """A remote LLM call was refused by the privacy guard."""


class PrivacyGuard:
    def __init__(self, settings: Settings):
        self._settings = settings

    def check(self, provider: LLMProvider, project_config: dict[str, Any] | None = None) -> None:
        if provider.provider_type is not LLMProviderType.REMOTE:
            return
        if not self._settings.allow_external_llm:
            raise ExternalLLMBlockedError(
                "ALLOW_EXTERNAL_LLM is disabled — refusing to send content to a remote LLM provider."
            )
        classification = (project_config or {}).get("data_classification", "internal")
        if classification == "confidential":
            raise ExternalLLMBlockedError(
                "Project is marked data_classification=confidential — refusing remote LLM call."
            )
