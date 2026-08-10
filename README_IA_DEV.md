# README_IA_DEV.md

> How this project is built with AI: conventions, harnesses, and expertise markers for collaborators and future agents.

## TL;DR

This repo is a **local-first audio/video transcription pipeline** (faster-whisper CPU int8 + Flask dashboard) that is developed, tested, and documented alongside LLM assistants. The goal is not just to automate code, but to program **faster and with fewer mistakes** by giving every AI assistant the same canonical context, reusable skills, and automated feedback loops.

Key signals of an AI-native workflow:

- `CLAUDE.md` + `AGENTS.md` give every agent the same canonical context (architecture, paths, constraints).
- `.agents/` contains a provider-agnostic orchestration layer: skills, agents, prompts, templates, and MCP tools.
- `scripts/quality.py`, `scripts/security.py`, `scripts/ut.py`, `scripts/e2e.py`, and `scripts/run_harness.py` form an automated quality gate that can run locally and in CI.
- All screenshots in `docs/screenshots/` are generated from 100% synthetic data.
- No real secrets, client names, or local paths are committed.

## Why this makes us program faster with AI

Without shared context, every AI assistant starts from zero: it has to guess the folder layout, the Python version, how tests run, and what *not* to touch. That wastes tokens, iterations, and your time. This repo fixes that by treating context as code:

1. **Onboarding in seconds.** A new agent reads `CLAUDE.md`, `AGENTS.md`, and `.agents/AGENTS.md` and immediately knows the architecture, constraints, and entry points.
2. **Consistent decisions.** Every agent uses the same conventions (snake_case modules, `PLACEHOLDER_*` secrets, `ponytail:` shortcuts), so reviews focus on logic, not style.
3. **Parallel work.** Skills and agents let us delegate whole domains (summarization, scene extraction, routing) without rewriting instructions each time.
4. **Fast feedback.** Harnesses run in under a minute and catch syntax errors, secret leaks, broken imports, and UI regressions before a human review.
5. **Safe automation.** Security and quality gates mean we can let agents edit, test, and propose pull requests with less manual supervision.

## AI-assisted development conventions

### 1. Context files are the source of truth

| File | Audience | Purpose |
|---|---|---|
| `CLAUDE.md` | Claude Code / any agent | Architecture, daily workflow, config, file naming, output structure |
| `AGENTS.md` | Generic agents / LLM tools | Repo entry point, environment, conventions, anti-patterns |
| `.agents/AGENTS.md` | Provider-agnostic AI layer | Skills, agents, prompts, MCP conventions |
| `.agents/skills/transcription-pipeline/SKILL.md` | Task-specific agents | Domain commands, env vars, routing rules, smart scene extraction |
| `.agents/agents/transcription-analyst.md` | Persona-driven agents | Role, goal, instructions, constraints, tools |
| `.agents/templates/summary.md` | Output templates | Reusable Markdown formats for summaries |

These files are **not** a separate doc layer — they are executable context: every agent reads them before touching code.

### 2. Prompt-driven code changes

- Agents receive natural-language tasks ("add dashboard pagination", "harden search highlight", "create E2E harness").
- They are expected to follow the ladder of laziness: reuse existing code → stdlib → native → installed deps → minimal new code.
- Deliberate shortcuts are marked with a `ponytail:` comment naming the shortcut and the upgrade path.

This pattern lets us move from idea to tested code in minutes. For example, adding search highlighting in the dashboard required only one prompt: the agent read the existing template, fixed a data-attribute bug, and the E2E harness confirmed it with a real transcription.

Example:

```python
# ponytail: local-only paths; not pushed (env file gitignored).
RAG_BASE_PATH = os.getenv("RAG_BASE_PATH", "C:/Dev/LocalProject/Rag/_transcripciones")
```

### 3. Composition roots stay thin

`master_processor.py`, `simple_scan.py`, `compress_and_move.py`, and `dashboard.py` at the repo root contain **no business logic**. They import the package under `src/transcript_pipeline/` and run it. This lets AI refactor the internals without touching the daily `.bat` entry point, reducing the blast radius of every change.

## Quality & security harnesses as AI guardrails

AI writes code fast, but it can also introduce subtle bugs, leaked secrets, or broken imports. The harnesses act as guardrails that run automatically before any commit or pull request. They are designed to be fast enough that an agent can iterate many times in a single session.

All harnesses live under `scripts/` and produce JSON reports at the repo root.

| Harness | Script | What it checks | Report |
|---|---|---|---|
| Quality | `scripts/quality.py` | Python syntax (`py_compile`), import sanity for core modules, optional `ruff` lint | `quality_report.json` |
| Security | `scripts/security.py` | Committed secrets, `.env` ignored, path-traversal guards, optional `pip-audit` | `security_report.json` |
| Unit tests | `scripts/ut.py` | `pytest tests/` (projects, language, file_tracker) | `ut_report.json` |
| E2E | `scripts/e2e.py` | Starts dashboard, runs `tests/e2e/smoke_dashboard.py` (Playwright) | `e2e_report.json` |
| Combined | `scripts/run_harness.py` | Runs all four stages sequentially | `harness_report.json` |

Run everything locally:

```bash
python scripts/run_harness.py
```

Run a single gate:

```bash
python scripts/quality.py
python scripts/security.py
python scripts/ut.py
python scripts/e2e.py
```

### CI integration

The GitHub Actions workflow `.github/workflows/dashboard-ci.yml` uses the same harness pattern: quality → security → unit tests → E2E. Each job uploads its report. Because the E2E job depends on the previous three, CI fails fast on cheap checks and only runs the expensive Playwright test when everything else is green.

This means an AI can propose changes, and the repository itself verifies syntax, secrets, tests, and UI behavior without human intervention.

## Security discipline for AI-generated code

1. **Secrets stay in local `.env` files only.** `.env`, `*.env`, `watcher/.env`, and `deepseek/.env` are `.gitignore`d.
2. **Examples, not values.** Committed files end in `.env.example` and contain `PLACEHOLDER_*` or `your_*_here` values.
3. **Pre-push scan.** `scripts/security.py` checks tracked files for OpenAI/Notion/AWS keys, private keys, and hardcoded passwords before any push.
4. **Path traversal guard.** `dashboard/app.py` resolves requested paths and verifies they are inside `PROJECT_ROOT` before serving media or frames.
5. **No real client data in screenshots.** `docs/screenshots/` uses mock projects (Fabrikam, Contoso, Northwind) and synthetic transcripts.

## Skills & agent architecture

The `.agents/` directory is a generic AI orchestration layer, independent of any IDE or model provider.

```
.agents/
├── AGENTS.md                       # AI orchestration guide
├── agents/
│   └── transcription-analyst.md    # Persona for summarization/routing
├── skills/
│   └── transcription-pipeline/     # Domain skill
│       ├── SKILL.md
│       └── keyframe_extractor_smart_scene.py
├── prompts/                        # Reusable prompts
├── templates/                      # Output templates (summary.md)
└── mcp/                            # Model Context Protocol servers
```

Skills define the **what**, agents define the **who**, and prompts/templates define the **format**. This structure makes the same automation consumable by Claude Code, Cursor, Roo Code, or custom scripts.

## Caveman / ponytail development modes

This project experiments with two agent communication modes:

- **Caveman**: ultra-compressed, minimal-token communication. Drop articles, filler, and hedging; keep exact technical terms and code.
- **Ponytail**: lazy senior developer mode. Build the minimum that works; reuse before writing; delete over add; mark shortcuts with `ponytail:` comments.

Both modes are documented in `CLAUDE.md` and reflected in agent output style.

## How to onboard an AI assistant

1. Point it to `CLAUDE.md` and `AGENTS.md` first.
2. For domain tasks, load `.agents/skills/transcription-pipeline/SKILL.md`.
3. For summarization/routing tasks, load `.agents/agents/transcription-analyst.md`.
4. Run `python scripts/run_harness.py` before asking it to commit or push.
5. Never let it commit `.env`, `projects.json`, `processed_files.json`, or local screenshots.

## License

[MIT](LICENSE)
