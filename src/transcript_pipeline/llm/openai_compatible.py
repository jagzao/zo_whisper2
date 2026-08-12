"""OpenAI-compatible chat-completions client.

Works against any `/v1/chat/completions` endpoint: OpenAI, Ollama,
DeepSeek API, LM Studio, llama.cpp server. Reads all configuration from
`Settings` (see `transcript_pipeline.settings`) instead of calling
`os.getenv` directly, so callers can inject a differently-configured
instance in tests without touching environment variables.

This replaces `watcher/core/integration/llm_client.py` — the previous
shared-kernel module lived outside the installable package and required
`bootstrap.ensure_watcher_importable()` to reach it via `sys.path`.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import certifi
import requests

from transcript_pipeline.config import PROJECT_ROOT
from transcript_pipeline.llm.provider import LLMProviderType
from transcript_pipeline.settings import SETTINGS, Settings

logger = logging.getLogger(__name__)

_DEFAULT_SUMMARY_PROMPT = (
    "Eres un asistente ejecutivo. Resume la transcripción de forma concisa: "
    "TL;DR en 3-5 bullets, temas principales, y tareas/decisiones pendientes. "
    "Responde en el mismo idioma que la transcripción."
)


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings = SETTINGS):
        self._settings = settings
        self.provider_type = LLMProviderType(settings.llm_provider_type)

    def generate_summary(
        self, text: str, system_prompt: str | None = None, max_tokens: int = 2000
    ) -> str:
        return self._make_request(
            {
                "model": self._settings.llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt or _DEFAULT_SUMMARY_PROMPT},
                    {"role": "user", "content": text},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            }
        )

    def generate_from_template(self, text: str, template_path: str | Path | None = None) -> str:
        """Generates a summary using the prompt section of a markdown template file."""
        if template_path is None:
            template_path = PROJECT_ROOT / ".agents" / "templates" / "summary.md"

        system_prompt = None
        try:
            template_content = Path(template_path).read_text(encoding="utf-8")
            if "## Prompt for the Agent" in template_content:
                system_prompt = template_content.split("## Prompt for the Agent")[-1].strip().strip("`\n")
        except Exception as e:
            logger.warning("Could not load prompt template %s: %s", template_path, e)

        return self.generate_summary(text, system_prompt=system_prompt)

    def describe_frame(self, image_path: str | Path, context_text: str = "") -> str:
        """Sends a single frame image to the vision model, returns a 1-2 sentence description."""
        prompt = (
            "Describe en 1-2 oraciones qué se ve en esta pantalla. "
            "Enfócate en código, UI, contenido relevante o cambio de escena. "
            + (f"Contexto de la transcripción: {context_text[:300]}" if context_text else "")
        )
        return self.describe_frame_with_prompt(image_path, prompt, max_tokens=150, temperature=0.2)

    def describe_frame_with_prompt(
        self, image_path: str | Path, prompt: str, *, max_tokens: int = 500, temperature: float = 0.2
    ) -> str:
        """Sends a single frame image to the vision model with a caller-supplied prompt.

        Used directly by callers that need a structured (e.g. JSON) response
        with a domain-specific prompt — `describe_frame` is a thin wrapper
        around this with the default screen-description prompt.
        """
        image_bytes = Path(image_path).read_bytes()
        suffix = Path(image_path).suffix.lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix, "png")
        b64 = base64.b64encode(image_bytes).decode()

        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}},
        ]
        return self._make_request(
            {
                "model": self._settings.llm_model,
                "messages": [{"role": "user", "content": user_content}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )

    def describe_frames_for_tutorial(
        self,
        frames_dir: str | Path,
        transcription_mapping: dict,
        max_frames: int | None = None,
    ) -> dict:
        """Describes up to `max_frames` images in `frames_dir`. Returns {filename: description}.

        Only runs if `FRAME_DESCRIPTIONS=true` — callers must still run this
        through `PrivacyGuard` themselves if the provider is remote.
        """
        if not self._settings.frame_descriptions:
            return {}

        limit = max_frames or self._settings.frame_description_max
        frames_dir = Path(frames_dir)
        frame_files = sorted(
            f for f in frames_dir.glob("frame_*") if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )[:limit]

        descriptions: dict[str, str] = {}
        for frame_path in frame_files:
            context = ""
            if frame_path.name in transcription_mapping:
                context = transcription_mapping[frame_path.name].get("full_text", "")
            try:
                descriptions[frame_path.name] = self.describe_frame(frame_path, context)
                logger.info("Described frame: %s", frame_path.name)
            except Exception as e:
                logger.warning("Could not describe frame %s: %s", frame_path.name, e)

        return descriptions

    def _make_request(self, payload: dict) -> str:
        base_url = self._settings.llm_base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self._settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self._settings.llm_api_key}"
        r = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
            verify=certifi.where(),
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
