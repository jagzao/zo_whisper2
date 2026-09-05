# .agents Architecture Guide

This directory defines a **provider-agnostic AI layer** for the Whisper transcription project. It is designed to work with any LLM (OpenAI, DeepSeek, Claude, local Ollama, etc.) through a unified interface.

## Philosophy

- `.kilo/` is Kilo-specific IDE configuration (commands, TUI, shortcuts).
- `.agents/` is the **AI orchestration layer**: skills, prompts, agents, and MCP tools independent of any single IDE or model provider.
- By keeping `.agents/` generic, the same automation definitions can be consumed by Kilo, Claude Code, Cursor, Roo Code, or custom scripts.

## Directory Layout

```
.agents/
├── AGENTS.md                          # This file
├── skills/
│   └── transcription-pipeline/
│       └── SKILL.md                   # Domain skill for the transcription flow
├── agents/
│   └── (specialized agent definitions per task)
├── prompts/
│   └── (reusable system/user prompts)
├── templates/
│   └── (markdown templates for summaries, QA, etc.)
└── mcp/
    └── (Model Context Protocol server definitions)
```

## Conventions

1. **Skills** are self-contained task guides. Each `SKILL.md` explains context, file paths, critical commands, and decision trees for a domain (e.g., transcription pipeline, scene extraction).
2. **Agents** define personas (e.g., `transcription-reviewer`, `scene-extraction-optimizer`). They reference skills and prompts.
3. **Prompts** are plain text or Jinja2 templates without business logic.
4. **MCP** servers expose project-specific tools (e.g., query processed_files.json, trigger RUN_MAX_QUALITY.bat).

## Integration with Existing Pipeline

The local workflow (`RUN_MAX_QUALITY.bat` -> `master_processor.py` -> `simple_scan.py`) is the primary engine. `.agents/` does not replace it; it **augments** it with LLM-driven post-processing and quality gates.

See `CLAUDE.md` for the full architecture, file naming conventions, and output structure.

### Example Flow

1. Human drops video in `Videos/`.
2. `RUN_MAX_QUALITY.bat` runs Whisper + scene extraction.
3. `.agents/agents/transcription-analyst` reads the transcript and generates a structured Markdown summary using `.agents/templates/summary.md`.
4. The agent routes output to the correct project folder based on filename prefixes (`zo_`, `northwind_`, `jm_`).

### Language Detection

- Filename prefix `es_` or `en_` → explicit language
- `lang.txt` in a subfolder (contains just `es` or `en`) → folder-level default
- No prefix or file → Whisper auto-detects

## LLM Provider Abstraction

Keep provider-specific tokens and URLs in local `.env` files (never in skills). Skills reference generic environment variables:

```env
LLM_API_KEY=...
LLM_BASE_URL=https://api.openai.com/v1   # or Ollama: http://localhost:11434/v1
LLM_MODEL=gpt-4o-mini                    # or mistral, deepseek-chat, etc.
```

The file `watcher/core/integration/llm_client.py` (to be created) should expose a single `generate_summary(text, prompt_template) -> str` that calls any OpenAI-compatible `/v1/chat/completions` endpoint using these three variables.

**Notion is optional and disabled by default.** Do not require `NOTION_API_KEY` for core functionality.

## Analysis-to-Delivery Autonomous Execution Contract

When a substantial product/architecture/UX/technical analysis has just been completed and the owner asks to **generate the deliverable**, the deliverable MUST capture the complete agreed analysis as an executable User Story (US) or implementation package. Do not reduce it to a summary or a partial backlog item.

The generated US/deliverable MUST include, when applicable:

- complete functional scope and every decision agreed during the analysis;
- architecture, data-flow, UX/UI, integration, privacy, security and non-functional requirements;
- explicit acceptance criteria and definition of done;
- implementation tasks/subtasks detailed enough for `project-lead` to execute autonomously;
- Unit Tests (UT);
- integration tests where applicable;
- End-to-End (E2E) tests;
- smoke tests;
- regression tests for existing behavior affected by the change;
- security/privacy tests and negative/abuse cases where applicable;
- observability, diagnostics and error-path validation where applicable;
- documentation and release/readme changes required by the feature;
- a validation loop that continues until implementation and all applicable gates are green.

### Autonomous implementation loop

`project-lead` must treat the US as a completion contract, not as planning guidance.

1. Read the repository memory/rules/skills and the complete US before editing code.
2. Inspect the current implementation and establish the real baseline.
3. Implement the full scope end-to-end.
4. Run the applicable UT, integration, E2E, smoke, regression, security, quality and static-analysis gates.
5. If a gate fails, diagnose it, fix the root cause and rerun the relevant gates.
6. Repeat implementation → test → diagnose → fix → retest for as many iterations as necessary.
7. Do not stop because the task is large, takes a long time, or has already consumed many iterations. There is no artificial time-box for completion.
8. Do not declare completion with knowingly failing tests, TODO placeholders, mocked production behavior, skipped acceptance criteria or unverified assumptions unless an external hard blocker truly prevents completion.
9. If an external hard blocker exists, record exact evidence, what remains blocked, and what was completed independently of that blocker.
10. Finish with an auditable handoff: changed files, implemented acceptance criteria, tests/gates executed and results, security/privacy validation, known residual risks, and exact manual checks (if any) still worth performing.

The expected outcome is **completed implementation ready for owner/assistant audit and validation**, not a proposal for future work.

### How the owner should start execution

The repository contains the persistent implementation memory, so the assistant MUST NOT generate a new mega-prompt merely to start the agent. After creating the complete US/deliverable, give the owner one short execution instruction that references it, for example:

`Project-lead: toma la US <ruta-o-id> y ejecútala completa de inicio a fin siguiendo la memoria y reglas del repo. Termina solo cuando implementación y gates aplicables estén completos y verdes, y entrega el handoff de validación.`

Keep that start instruction short. The detailed scope belongs in the US and repository memory, not duplicated into a giant chat prompt.
