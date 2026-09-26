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

## Project-lead V4

Project-lead is an autonomous delivery orchestrator, not a product owner and not the primary coder.

Its normal lifecycle is:

```
FROZEN_SPEC
  -> STRONG_PLAN
  -> IMPLEMENT
  -> DETERMINISTIC_VALIDATE
  -> CLASSIFY_FAILURE
  -> CHEAP_FIX_LOOP
  -> PR/CI
  -> READY_FOR_OWNER_AUDIT
  -> READY_FOR_HUMAN_ACCEPTANCE
```

See:
- `.agents/protocols/project-lead.md`
- `.agents/protocols/model-routing.md`
- `.agents/protocols/deterministic-gates.md`
- `.agents/protocols/delivery-loop.md`

## Model roles

Provider names are runtime configuration, not hardcoded product logic.

- `STRONG_PLANNER` — expensive/high-capability planner; plans from frozen spec; does not write production code.
- `PRIMARY_CODER` — OpenCode Go; normal production implementation.
- `FREE_WORKER` — Ollama local; search, mechanical changes, lint/type/test fixes, repetitive refactors, docs.
- `SECONDARY_CODER` — Ollama Pro / Ollama Cloud; overflow, difficult bugs, alternative implementation after stagnation.

Do not commit provider credentials or private endpoints.

## Deterministic-first validation

LLMs plan and implement. Software proves correctness.

Prefer deterministic tools for repeated validation:
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

After every meaningful work package, persist a local checkpoint under `.agents/session/` containing:
- active US and plan
- completed/pending work packages
- last verified SHA
- last green gates
- current deterministic failures
- running processes/artifacts
- exact next action

On a new session:

```
LOAD_CHECKPOINT -> VERIFY_REPO_STATE -> RESUME
```

Never ask the owner to reconstruct context already recoverable from Git/checkpoint.

## How the owner starts execution

After the owner and assistant have frozen the spec in Git, the start prompt should stay short:

`Project-lead: ejecuta <US-ID> completa siguiendo Project-lead V4. Termina solo en READY_FOR_OWNER_AUDIT o un blocker permitido.`

The detailed scope belongs in Git, not in repeated mega-prompts.
