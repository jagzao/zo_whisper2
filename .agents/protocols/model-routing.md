# Model Routing V4

## Goal

Use expensive intelligence only where it materially improves outcome. Use deterministic software for repeated validation and low-cost models for mechanical work.

Provider/model names are runtime aliases so credentials and vendor choices can change without rewriting product specs.

## Cost policy

Default to the cheapest model that reliably completes the task. Escalate only when evidence shows the cheaper tier cannot complete it.

Routine coding ladder (first available wins):

1. OpenCode Go / DeepSeek Flash (`ECONOMICAL_CODER`).
2. Local coding model / Ollama / DeepSeek.
3. Another economical coding model.
4. GPT-6 Luna or larger models — genuinely difficult work only.

Correctness gates are unchanged by this policy. Cheaper models never lower acceptance criteria, test coverage, review requirements, or release gates.

## Roles

### STRONG_PLANNER

Purpose:
- consume frozen EPIC/FEATURE/US/ADR
- inspect relevant repository context
- create/update the implementation PLAN
- resolve difficult technical planning after evidence proves a premise wrong

Rules:
- does not write production code
- does not run normal fix loops
- is not invoked merely because a unit test fails
- plan is subordinate to frozen spec
- reserve GPT-6 Luna-class or larger models for genuinely difficult planning or debugging

Runtime provider: configurable. The owner may use Claude/GPT interactively for product analysis; autonomous access requires whatever authorized provider is actually connected at runtime.

### PRIMARY_CODER (ECONOMICAL_CODER)

Default: OpenCode Go with DeepSeek Flash-class economical model.

Purpose:
- normal production feature implementation
- non-mechanical refactors
- complex test creation tied to implementation
- first meaningful repair of a normal code defect

### FREE_WORKER

Default: local coding model / Ollama.

Purpose:
- repository search/exploration
- mechanical edits
- lint/type fixes with deterministic diagnostics
- repetitive refactors
- docs
- fixture maintenance
- simple regression-test repairs
- small code transformations with explicit expected output

Do not assign a high-risk architectural rewrite to FREE_WORKER merely because it is free.

### SECONDARY_CODER

Default: another economical coding model (Ollama Pro / Ollama Cloud or equivalent).

Purpose:
- overflow when PRIMARY_CODER is unavailable
- alternative implementation after repeated failure
- difficult bug after compact evidence + regression test exist
- second independent coding approach

### Premium escalation

Premium/large models (GPT-6 Luna or larger) are reserved for genuinely difficult work: complex architecture, hard cross-cutting refactors, or debugging where cheaper tiers stagnated with evidence. Return to the economical tier immediately after the hard step.

## Failure routing

```
ROUTINE IMPLEMENTATION
  -> ECONOMICAL_CODER (OpenCode Go / DeepSeek Flash -> local -> other economical)

MECHANICAL / EXACT DIAGNOSTIC
  -> FREE_WORKER

NORMAL PRODUCTION DEFECT
  -> PRIMARY_CODER

SAME ERROR SIGNATURE AFTER 2 MEANINGFUL ATTEMPTS
  -> SECONDARY_CODER

GENUINELY DIFFICULT WORK (evidence required)
  -> STRONG_PLANNER / large model

CODER TIERS FAIL BECAUSE TECHNICAL PREMISE IS WRONG
  -> STRONG_PLANNER bounded re-plan

FROZEN REQUIREMENTS CONTRADICT
  -> SPEC_CONFLICT
```

## Pool failure

If a pool is unavailable, project-lead automatically tries the next permitted pool appropriate for the task.

Do not interrupt the owner simply to choose a model.

## Context budget

Workers receive:
- frozen AC(s) relevant to the package
- PLAN work package
- minimal relevant file/context set
- compact deterministic failure report when fixing
- explicit acceptance evidence required

Workers should not receive complete historical chat logs or multi-thousand-line CI logs by default.

## Validation token policy

Validation tools do not require an LLM:
- pytest
- Ruff
- Pyright
- security.py
- pip-audit
- Gitleaks
- FFmpeg/ffprobe
- Playwright
- SonarQube
- Jenkins
- GitHub Actions

LLMs interpret a concise failure only when repair is needed.

## Cost telemetry

Record per task:
- active orchestration model
- role
- degraded flag
- fallback reason

Canonical keys: `ACTIVE_ORCHESTRATION_MODEL`, `MODEL_ROLE`, `MODEL_DEGRADED`, `MODEL_FALLBACK_REASON`.
