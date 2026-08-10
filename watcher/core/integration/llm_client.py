"""
Provider-agnostic LLM client.

Reads LLM_BASE_URL, LLM_API_KEY, LLM_MODEL from environment and calls
any OpenAI-compatible /v1/chat/completions endpoint.

Compatible with: OpenAI, Ollama, DeepSeek API, LM Studio, llama.cpp server.
"""

import base64
import logging
import os
import requests
import certifi
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_summary(text: str, system_prompt: str = None, max_tokens: int = 2000) -> str:
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not system_prompt:
        system_prompt = (
            "Eres un asistente ejecutivo. Resume la transcripción de forma concisa: "
            "TL;DR en 3-5 bullets, temas principales, y tareas/decisiones pendientes. "
            "Responde en el mismo idioma que la transcripción."
        )
    return _make_request({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    })


def _make_request(payload: dict) -> str:
    """Shared HTTP call for all LLM functions."""
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key  = os.getenv("LLM_API_KEY", "")
    headers  = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    r = requests.post(
        f"{base_url}/chat/completions",
        json=payload, headers=headers,
        timeout=120, verify=certifi.where(),
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def describe_frame(image_path: str | Path, context_text: str = "") -> str:
    """
    Send a single frame image to the vision model and get a 1-2 sentence description.
    Requires a multimodal model (kimi-k2.6, gpt-4o, etc.).
    Controlled by env: FRAME_DESCRIPTIONS=true, FRAME_DESCRIPTION_MAX (default 20).
    """
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    image_bytes = Path(image_path).read_bytes()
    suffix = Path(image_path).suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix, "png")
    b64 = base64.b64encode(image_bytes).decode()

    user_content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/{mime};base64,{b64}"},
        },
        {
            "type": "text",
            "text": (
                "Describe en 1-2 oraciones qué se ve en esta pantalla. "
                "Enfócate en código, UI, contenido relevante o cambio de escena. "
                + (f"Contexto de la transcripción: {context_text[:300]}" if context_text else "")
            ),
        },
    ]

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": 150,
        "temperature": 0.2,
    }
    return _make_request(payload)


def describe_frames_for_tutorial(
    frames_dir: str | Path,
    transcription_mapping: dict,
    max_frames: int = None,
) -> dict:
    """
    Describe up to max_frames images in frames_dir using the vision model.
    Returns {frame_filename: description_str}.
    Only runs if FRAME_DESCRIPTIONS=true in environment.
    """
    if os.getenv("FRAME_DESCRIPTIONS", "false").lower() != "true":
        return {}

    limit = max_frames or int(os.getenv("FRAME_DESCRIPTION_MAX", "20"))
    frames_dir = Path(frames_dir)
    frame_files = sorted(
        f for f in frames_dir.glob("frame_*")
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )[:limit]

    descriptions = {}
    for frame_path in frame_files:
        context = ""
        if frame_path.name in transcription_mapping:
            context = transcription_mapping[frame_path.name].get("full_text", "")
        try:
            descriptions[frame_path.name] = describe_frame(frame_path, context)
            logger.info("Described frame: %s", frame_path.name)
        except Exception as e:
            logger.warning("Could not describe frame %s: %s", frame_path.name, e)

    return descriptions


def generate_from_template(text: str, template_path: str = None) -> str:
    """Generate summary using the prompt section of a markdown template file."""
    if template_path is None:
        template_path = str(
            Path(__file__).parents[3] / ".agents" / "templates" / "summary.md"
        )

    system_prompt = None
    try:
        template_content = Path(template_path).read_text(encoding="utf-8")
        if "## Prompt for the Agent" in template_content:
            system_prompt = template_content.split("## Prompt for the Agent")[-1].strip().strip("`\n")
    except Exception as e:
        logger.warning("Could not load prompt template %s: %s", template_path, e)

    return generate_summary(text, system_prompt=system_prompt)
