"""Deterministic cheap model router (PLV5).

Selects the single local coding model from the owner-approved cheap fallback
chain. Routing is a pure function of provider availability — never of task
complexity, test results, or any LLM judgement.

Priority (frozen):
1. Z.ai Coding Plan GLM owner-approved coder
2. OpenCode DeepSeek
3. Ollama server DeepSeek
4. OpenRouter DeepSeek

Forbidden anywhere in the chain: OpenAI/Codex/GPT, Claude, Kimi, premium
planner/reviewer models.

Run:
    python scripts/model_router.py --providers providers.json
    python scripts/model_router.py --provider zai-coding-plan:glm-5.2 --provider ollama:deepseek-v3.1

Input providers JSON: list of {"provider": str, "model": str, "available": bool}.
Output: single JSON object on stdout. Exit codes: 0 selected, 4 fail-closed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Frozen fallback chain: (chain slot, provider-name matcher patterns).
# Matching is by PROVIDER name only — the chain order is provider-level, so a
# DeepSeek model served by Ollama must resolve to the ollama slot, not to the
# earlier opencode slot.
PROVIDER_CHAIN: list[tuple[str, list[str]]] = [
    ("zai_glm", ["zai", "z.ai", "zai-coding-plan", "coding-plan"]),
    ("opencode_deepseek", ["opencode"]),
    ("ollama_deepseek", ["ollama"]),
    ("openrouter_deepseek", ["openrouter"]),
]

FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    ("openai", r"\bopenai\b|codex|\bgpt[-_ ]|o[134](-mini)?\b"),
    ("claude", r"\bclaude\b|\banthropic\b"),
    ("kimi", r"\bkimi\b|\bmoonshot\b"),
]

FAIL_CLOSED_STATUS = "FAIL_CLOSED"
SELECTED_STATUS = "SELECTED"


def _matches_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(p in lowered for p in patterns)


def _is_forbidden(provider: str, model: str) -> str | None:
    combined = f"{provider} {model}"
    for label, pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, combined, flags=re.IGNORECASE):
            return label
    return None


def select_model(providers: list[dict]) -> dict:
    """Pure deterministic selection over declared provider availability.

    Accepts no test results, no complexity hints, no token budget. A red unit
    test can never influence routing because no such input exists (PLV5-R06).
    """
    available: list[dict] = [
        p for p in providers if isinstance(p, dict) and p.get("available", True)
    ]

    rejected: list[dict] = []
    for entry in available:
        provider = str(entry.get("provider", ""))
        model = str(entry.get("model", ""))
        reason = _is_forbidden(provider, model)
        if reason is not None:
            rejected.append(
                {
                    "provider": provider,
                    "model": model,
                    "reason": f"forbidden:{reason}",
                }
            )

    for chain_name, patterns in PROVIDER_CHAIN:
        for entry in available:
            provider = str(entry.get("provider", ""))
            model = str(entry.get("model", ""))
            if _is_forbidden(provider, model) is not None:
                continue
            if _matches_any(provider, patterns):
                return {
                    "status": SELECTED_STATUS,
                    "chain_slot": chain_name,
                    "provider": provider,
                    "model": model,
                    "reason": "first available provider in frozen cheap chain",
                    "rejected": rejected,
                }

    return {
        "status": FAIL_CLOSED_STATUS,
        "chain_slot": None,
        "provider": None,
        "model": None,
        "reason": "no permitted provider available; failing closed",
        "rejected": rejected,
    }


def _parse_providers(argv: list[str] | None) -> list[dict]:
    parser = argparse.ArgumentParser(description="PLV5 deterministic cheap model router")
    parser.add_argument("--providers", type=Path, help="JSON file with provider availability list")
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        help="inline provider spec provider:model (repeatable)",
    )
    args = parser.parse_args(argv)

    providers: list[dict] = []
    if args.providers:
        providers = json.loads(args.providers.read_text(encoding="utf-8"))
    for spec in args.provider:
        provider, _, model = spec.partition(":")
        providers.append(
            {"provider": provider.strip(), "model": model.strip() or provider.strip()}
        )
    if not providers:
        raise SystemExit("--providers or --provider is required")
    return providers


def main(argv: list[str] | None = None) -> int:
    providers = _parse_providers(argv)
    result = select_model(providers)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == SELECTED_STATUS else 4


if __name__ == "__main__":
    sys.exit(main())
