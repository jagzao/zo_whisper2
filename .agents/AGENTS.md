# .agents Architecture Guide

This directory defines the provider-agnostic AI orchestration layer for Zo Media Intelligence.

## Core principle

Product/architecture/UX decisions are made outside the autonomous coding loop by the owner working with ChatGPT/Claude. Those decisions are persisted in Git as frozen EPIC / FEATURE / US / ADR artifacts. Autonomous agents execute that contract; they do not redefine it.

The target owner interaction budget for a normal feature is exactly two touchpoints:

1. INITIAL_SPEC — owner + assistant define/freeze the work and send one start instruction.
2. FINAL_ACCEPTANCE — after implementation, deterministic validation, PR/CI, and external audit, the owner performs the final product check.

Any extra owner interruption must be exceptional and documented.

## Directory layout

```
.agents/
├── AGENTS.md
├── protocols/
│   ├── project-lead.md
│   ├── delivery-loop.md
│   ├── model-routing.md
│   └── deterministic-gates.md
├── deliverables/
│   ├── TEMPLATE.md
│   ├── EPIC-*.md
│   ├── FEATURE-*.md
│   ├── US-*.md
│   ├── PLAN-*.md
│   └── DELIVERY-*.md
├── templates/
├── skills/
├── agents/
├── session/      # local runtime checkpoint; gitignored
└── memory/       # local runtime memory; gitignored
```

## Source of truth

```
EPIC -> FEATURE -> US/ADR -> PLAN -> CODE -> DELIVERY
```

- EPIC / FEATURE / US / ADR are owner-approved product truth.
- PLAN is an implementation artifact produced from the frozen spec.
- PLAN may not silently change the frozen spec.
- If implementation reveals a genuine contradiction in frozen requirements, stop with `SPEC_CONFLICT`.
- Runtime state never belongs in tracked files.

## Deployed source and UI parity

- Before rebuilding or restarting a deployed service, identify the Compose build
  context and the exact checkout that supplies the running image. Parallel
  checkouts do not share edits; compare and port every in-scope change explicitly.
- Validate the artifact served by the running service after deployment. For UI
  changes, include phone and desktop viewport checks; confirm the mobile layout,
  touch controls, and absence of page-level horizontal overflow.
- Do not treat a successful image build or a localhost response as proof that the
  deployed UI contains the intended responsive changes.

## Project-lead V5

Project-lead is the local implementation worker for a frozen owner + ChatGPT spec, not a product owner and not an analyst.

Its normal lifecycle is:

```
FROZEN_SPEC (owner + ChatGPT)
  -> FROZEN_PLAN (in Git; no local STRONG_PLAN stage)
  -> IMPLEMENT (single selected cheap coder)
  -> IMPLEMENTATION_GATES (targeted UT, lint, typecheck)
  -> BOUNDED_REPAIR (max 2 per identical signature)
  -> COMMIT + PUSH
  -> READY_FOR_CHATGPT_REVIEW
  -> [ChatGPT /review]
  -> HEAVY_VALIDATION (RAM-gated, deterministic, LLM-free)
  -> OWNER_ACCEPTANCE
```

See:
- `.agents/protocols/project-lead.md`
- `.agents/protocols/model-routing.md`
- `.agents/protocols/deterministic-gates.md`
- `.agents/protocols/delivery-loop.md`
- `.agents/protocols/provider-aliases.md`

## Model policy

Exactly one cheap coder, selected deterministically by `scripts/model_router.py`:

1. Z.ai Coding Plan GLM owner-approved coder (default);
2. OpenCode DeepSeek;
3. Ollama server DeepSeek;
4. OpenRouter DeepSeek.

Never: OpenAI/Codex/GPT, Claude, Kimi, premium planner/reviewer models, nested LLM subagents by default. A red test never justifies escalation. There is no local STRONG_PLANNER.

Do not commit provider credentials or private endpoints.

## Deterministic-first validation

LLMs implement. Software proves correctness.

Implementation (light) gates the coder may run: targeted pytest, Ruff, typecheck, quality.py, security.py, smoke.py.

Heavy gates run only after ChatGPT `/review` and the RAM gate (`scripts/ram_gate.py`, available RAM > 6.0 GiB): full regression, Playwright E2E, Docker, SonarQube, Jenkins, soak — orchestrated LLM-free by `scripts/heavy_validation_runner.py`.

- pytest
- Ruff
- Pyright
- security.py / pip-audit / Gitleaks
- FFmpeg/ffprobe checks
- Playwright
- SonarQube
- Jenkins
- GitHub Actions for public PR checks

An LLM may create the first Playwright scenario for a feature. Re-running the scenario must consume zero LLM tokens.

Do not add Electron to a web project merely for validation. Validation adapter:
- web -> Playwright Chromium
- electron -> Playwright Electron
- mobile -> native/Appium-equivalent driver

## Owner interruption policy

Project-lead MUST NOT ask the owner what to do next when the next action can be derived from the frozen spec, plan, repository state, deterministic gate result, or CI result.

Allowed human-blocking states only:
- `BLOCKED_EXTERNAL`
- `DESTRUCTIVE_APPROVAL_REQUIRED`
- `SECURITY_OR_PRIVACY_DECISION`
- `SPEC_CONFLICT`
- `PRODUCT_DECISION_REQUIRED`

Coding difficulty, failing tests, one exhausted model pool, timeouts, long-running tests, or a session/context limit are not owner blockers.

## Resume contract

After every meaningful work package, `scripts/delivery_checkpoint.py` atomically
persists a local checkpoint under gitignored `.agents/session/` containing:
- active US and frozen plan/contract
- completed/pending work packages
- last verified SHA
- last green gates
- current deterministic failures
- running processes/artifacts
- exact next action

On a new session or after a power loss:

```
LOAD_CHECKPOINT -> VERIFY_REPO_STATE -> RESUME_FIRST_INCOMPLETE_MECHANICAL_STEP
```

Never re-run local analysis or re-plan merely because a session restarted. Never
ask the owner to reconstruct context already recoverable from Git/checkpoint.

## How the owner starts execution

After the owner and ChatGPT have frozen the spec in Git, the start prompt should stay short:

`Project-lead: ejecuta <US-ID> completa siguiendo Project-lead V5. Termina solo en READY_FOR_CHATGPT_REVIEW o un blocker permitido.`

The detailed scope belongs in Git, not in repeated mega-prompts.
