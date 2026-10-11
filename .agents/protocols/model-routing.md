# Model Routing V5

## Goal

The local runtime uses exactly one cheap coding model, selected deterministically. There are no model tiers, no planners, and no escalation ladders inside the local runtime.

Owner + ChatGPT are the only analysis/architecture level. The local agent is an implementation worker.

## Frozen fallback chain

`scripts/model_router.py` implements this exact priority:

1. Z.ai Coding Plan — owner-approved GLM coder (e.g. `glm-5.2`).
2. OpenCode provider — DeepSeek coding model.
3. Ollama server — DeepSeek coding model.
4. OpenRouter — DeepSeek coding model.

A provider is tried only when the previous one failed for availability, authentication, quota, or invocation reasons.

## Hard prohibitions

Never select or invoke:

- OpenAI / Codex / GPT;
- Claude / Anthropic;
- Kimi / Moonshot;
- any premium planner or reviewer model;
- any nested LLM subagent by default.

A red test, a difficult bug, or a long task NEVER justifies changing model tier or provider beyond the frozen chain order. Routing is a pure function of provider availability — never of task complexity or test results.

## Routing rules

- selection is deterministic and machine-readable (`model_router.py` emits JSON);
- if only forbidden providers are available, fail closed: no selection, `FAIL_CLOSED` status;
- no network beyond the provider/model availability command already required by the runtime;
- no LLM decides routing.

## Token rules

- no strong planner inside the local runtime;
- no nested LLM subagents by default;
- no autonomous recursive repair loop;
- at most 2 bounded mechanical repair attempts for one identical failure signature;
- deterministic tools (pytest, Ruff, Pyright, Playwright, Docker, Jenkins, Sonar) consume zero LLM tokens;
- no LLM waits for or polls a deterministic process;
- raw logs are not fed to an LLM by default; compact JSON/MD evidence first.

## Context budget

The coder receives:

- frozen AC(s) relevant to the package;
- the PLAN work package;
- minimal relevant file/context set;
- compact deterministic failure report when repairing;
- explicit acceptance evidence required.

The coder does not receive complete historical chat logs or multi-thousand-line CI logs.

## Validation token policy

Validation tools do not require an LLM:

- pytest
- Ruff
- Pyright
- security.py / pip-audit / Gitleaks
- FFmpeg/ffprobe
- Playwright
- SonarQube
- Jenkins
- GitHub Actions

An LLM interprets a concise failure only when a repair is actually needed.
