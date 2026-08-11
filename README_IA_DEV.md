# README_IA_DEV.md

> How this project is built with AI: conventions, harnesses, and expertise markers for collaborators and future agents.

## TL;DR

This repo is a **local-first audio/video transcription pipeline** (faster-whisper CPU int8 + Flask dashboard) that is developed, tested, and documented alongside LLM assistants. The goal is not just to automate code, but to program **faster and with fewer mistakes** by giving every AI assistant the same context, reusable conventions, and automated feedback loops.

Key signals of an AI-native workflow, all of which are in this repo:

- `scripts/quality.py`, `scripts/security.py`, `scripts/ut.py`, `scripts/e2e.py`, and `scripts/run_harness.py` form an automated quality gate that runs locally and in CI.
- `.github/workflows/dashboard-ci.yml` runs the same gate on every push/PR: quality → security → unit tests → E2E.
- All screenshots in `docs/screenshots/` are generated from 100% synthetic data (`docs/assets/generate_mock_data.py`).
- No real secrets, client names, or local paths are committed — `scripts/security.py` checks for this before every push.

Local development also uses project-specific context files and an agent/skill orchestration layer to brief AI assistants consistently — those aren't published here since they reference local paths and internal conventions, but the harnesses and CI below are the actual guardrails, and they're fully public and runnable by anyone who clones this repo.

## Why this makes us program faster with AI

Without shared context, every AI assistant starts from zero: it has to guess the folder layout, the Python version, how tests run, and what *not* to touch. That wastes tokens, iterations, and time. This repo treats verification as code instead of relying on manual review:

1. **Consistent decisions.** Every change follows the same conventions (snake_case modules, `PLACEHOLDER_*` secrets in `.env.example` files, thin composition roots) so review focuses on logic, not style.
2. **Fast feedback.** Harnesses run in under a minute and catch syntax errors, secret leaks, broken imports, and UI regressions before a human review.
3. **Safe automation.** Security and quality gates mean changes — AI-authored or not — can be verified objectively before they're merged.

## AI-assisted development conventions

### 1. Prompt-driven code changes

- Changes are described in plain language ("add dashboard pagination", "harden search highlight", "create an E2E harness") and implemented by reusing existing code before adding new code.
- Deliberate shortcuts are marked with a `ponytail:` comment naming the shortcut and the upgrade path, e.g.:

```python
# ponytail: local-only paths; not pushed (env file gitignored).
RAG_BASE_PATH = os.getenv("RAG_BASE_PATH", "C:/Dev/LocalProject/Rag/_transcripciones")
```

### 2. Composition roots stay thin

`master_processor.py`, `simple_scan.py`, `compress_and_move.py`, and `dashboard.py` at the repo root contain **no business logic**. They import the package under `src/transcript_pipeline/` and run it. This lets the internals be refactored — by a human or an AI assistant — without touching the daily `.bat` entry point, reducing the blast radius of every change.

## Quality & security harnesses as AI guardrails

AI writes code fast, but it can also introduce subtle bugs, leaked secrets, or broken imports. The harnesses act as guardrails that run automatically before any commit or pull request. They're fast enough to run after every meaningful change.

All harnesses live under `scripts/` and produce JSON reports at the repo root.

| Harness | Script | What it checks | Report |
|---|---|---|---|
| Quality | `scripts/quality.py` | Python syntax (`py_compile`), import sanity for core modules, optional `ruff` lint | `quality_report.json` |
| Security | `scripts/security.py` | Committed secrets, `.env` ignored, path-traversal guards, optional `pip-audit` | `security_report.json` |
| Unit tests | `scripts/ut.py` | `pytest tests/` (projects, language, file_tracker) | `ut_report.json` |
| E2E | `scripts/e2e.py` | Generates synthetic data, starts the dashboard, runs `tests/e2e/smoke_dashboard.py` (Playwright) | `e2e_report.json` |
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

The GitHub Actions workflow `.github/workflows/dashboard-ci.yml` uses the same harness pattern: quality → security → unit tests → E2E. Each job uploads its report as an artifact. Because the E2E job depends on the previous three, CI fails fast on cheap checks and only runs the expensive Playwright test when everything else is green.

## Security discipline for AI-generated code

1. **Secrets stay in local `.env` files only.** `.env`, `*.env`, `watcher/.env`, and `deepseek/.env` are `.gitignore`d.
2. **Examples, not values.** Committed files end in `.env.example` and contain `PLACEHOLDER_*` or `your_*_here` values.
3. **Pre-push scan.** `scripts/security.py` checks tracked files for OpenAI/Notion/AWS keys, private keys, and hardcoded passwords before any push.
4. **Path traversal guard.** `dashboard/app.py` resolves requested paths and verifies they are inside `PROJECT_ROOT` before serving media or frames.
5. **No real client data in screenshots.** `docs/screenshots/` uses mock projects (Northwind, Contoso, Fabrikam) and synthetic transcripts, generated fresh by `docs/assets/generate_mock_data.py` rather than sanitized from real recordings.

## Caveman / ponytail development modes

This project experiments with two agent communication modes:

- **Caveman**: ultra-compressed, minimal-token communication. Drop articles, filler, and hedging; keep exact technical terms and code.
- **Ponytail**: lazy senior developer mode. Build the minimum that works; reuse before writing; delete over add; mark shortcuts with `ponytail:` comments.

## Example: a typical AI-assisted feature flow

1. **Describe the feature** in plain language: *"Add pagination, filters, and sort to the dashboard file table."*
2. **Implement:** reuse the existing `dashboard.html` and `app.py`, add client-side filtering/sorting/pagination.
3. **Verify locally:** run `python scripts/quality.py` (syntax) and `python scripts/e2e.py` (UI behavior).
4. **Fix regressions:** the harness catches a broken search highlight; fix it, and the E2E test passes.
5. **Commit via the harness:** final check with `python scripts/security.py` to ensure no secrets, then push.

This loop takes minutes, not hours, and produces tested code with a traceable report.

## License

[MIT](LICENSE)
