"""Provider-agnostic LLM interface.

`provider_type` is never inferred from the model name — a `LLM_BASE_URL`
pointing at `localhost`/`127.0.0.1` (e.g. Ollama, LM Studio) is classified
`local`; anything else is `remote`, unless `LLM_PROVIDER_TYPE` overrides it
explicitly (see `Settings.from_env`). `PrivacyGuard` uses this to decide
whether a call is even allowed to leave the machine.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Protocol


class LLMProviderType(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


class LLMProvider(Protocol):
    provider_type: LLMProviderType

    def generate_summary(
        self, text: str, system_prompt: str | None = None, max_tokens: int = 2000
    ) -> str: ...

    def describe_frame(self, image_path: str | Path, context_text: str = "") -> str: ...
