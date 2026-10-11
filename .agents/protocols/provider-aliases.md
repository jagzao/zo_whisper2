# Provider Alias Mapping

PLV5 uses a single cheap coder selected from a frozen fallback chain. Configure
the chain locally; do not commit credentials, private endpoints, or
machine-specific configuration.

| Chain slot | Default target | Notes |
|---|---|---|
| 1. `ZAI_GLM_CODER` | Z.ai Coding Plan GLM owner-approved coder (e.g. `glm-5.2`) | Preferred default. |
| 2. `OPENCODE_DEEPSEEK` | OpenCode provider DeepSeek | Fallback only. |
| 3. `OLLAMA_DEEPSEEK` | Local Ollama server DeepSeek | Fallback only. |
| 4. `OPENROUTER_DEEPSEEK` | OpenRouter DeepSeek | Fallback only. |

Fallback moves to the next slot only on provider unavailability,
authentication failure, quota exhaustion, or invocation failure — never
because a test is red or a task looks hard.

Forbidden in every slot: OpenAI/Codex/GPT, Claude/Anthropic, Kimi/Moonshot,
premium planner/reviewer models, and nested LLM subagents by default.

`scripts/model_router.py` performs the deterministic selection and emits
machine-readable JSON with the chosen slot and the rejection reasons.
