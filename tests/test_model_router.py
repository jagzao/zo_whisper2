"""PLV5 deterministic model router tests (TEST-MATRIX PLV5-R01..R06, T03)."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import model_router  # noqa: E402

FORBIDDEN_CANDIDATES = [
    {"provider": "openai", "model": "gpt-5", "available": True},
    {"provider": "openai", "model": "codex-max", "available": True},
    {"provider": "anthropic", "model": "claude-opus-5", "available": True},
    {"provider": "moonshot", "model": "kimi-k3", "available": True},
]


def test_r01_zai_available_selects_zai_glm():
    result = model_router.select_model(
        [
            {"provider": "zai-coding-plan", "model": "glm-5.2", "available": True},
            {"provider": "ollama", "model": "deepseek-v3.1", "available": True},
        ]
    )
    assert result["status"] == "SELECTED"
    assert result["chain_slot"] == "zai_glm"
    assert result["model"] == "glm-5.2"


def test_r02_zai_unavailable_selects_opencode_deepseek():
    result = model_router.select_model(
        [
            {"provider": "zai-coding-plan", "model": "glm-5.2", "available": False},
            {"provider": "opencode", "model": "deepseek-v3.1", "available": True},
        ]
    )
    assert result["status"] == "SELECTED"
    assert result["chain_slot"] == "opencode_deepseek"


def test_r03_first_two_unavailable_selects_ollama_deepseek():
    result = model_router.select_model(
        [
            {"provider": "zai-coding-plan", "model": "glm-5.2", "available": False},
            {"provider": "opencode", "model": "deepseek-v3.1", "available": False},
            {"provider": "ollama-server", "model": "deepseek-r1", "available": True},
        ]
    )
    assert result["status"] == "SELECTED"
    assert result["chain_slot"] == "ollama_deepseek"


def test_r04_first_three_unavailable_selects_openrouter_deepseek():
    result = model_router.select_model(
        [
            {"provider": "zai-coding-plan", "model": "glm-5.2", "available": False},
            {"provider": "opencode", "model": "deepseek-v3.1", "available": False},
            {"provider": "ollama-server", "model": "deepseek-r1", "available": False},
            {"provider": "openrouter", "model": "deepseek/deepseek-chat", "available": True},
        ]
    )
    assert result["status"] == "SELECTED"
    assert result["chain_slot"] == "openrouter_deepseek"


def test_r05_only_forbidden_available_fails_closed():
    result = model_router.select_model(FORBIDDEN_CANDIDATES)
    assert result["status"] == "FAIL_CLOSED"
    assert result["provider"] is None
    assert result["model"] is None


def test_r06_red_test_never_escalates_provider():
    providers = [{"provider": "zai-coding-plan", "model": "glm-5.2", "available": True}]
    first = model_router.select_model(providers)
    second = model_router.select_model(providers)
    assert first == second  # deterministic: no hidden escalation input exists
    signature = inspect.signature(model_router.select_model)
    for param in signature.parameters:
        assert "test" not in param.lower()
        assert "complex" not in param.lower()
        assert "fail" not in param.lower()


def test_t03_router_never_selects_forbidden_models():
    for candidate in FORBIDDEN_CANDIDATES:
        alone = model_router.select_model([candidate])
        assert alone["status"] == "FAIL_CLOSED"
        mixed = model_router.select_model([candidate, {"provider": "ollama", "model": "deepseek-v3.1"}])
        assert mixed["status"] == "SELECTED"
        assert mixed["provider"] == "ollama"
    for candidate in FORBIDDEN_CANDIDATES:
        rejection = next(
            (r for r in model_router.select_model(FORBIDDEN_CANDIDATES)["rejected"] if r["model"] == candidate["model"]),
            None,
        )
        assert rejection is not None
        assert rejection["reason"].startswith("forbidden:")


def test_t04_no_unbounded_retry_loop():
    source = Path(model_router.__file__).read_text(encoding="utf-8")
    assert "while True" not in source
    assert source.count("while ") == 0
