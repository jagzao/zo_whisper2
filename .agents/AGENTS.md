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
4. The agent routes output to the correct project folder based on filename prefixes (`zo_`, `valeris_`, `jm_`).

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
