# DELTA-ZMI-DOCS-V2-002 — Fast CI/CD recovery lane

## Status
FROZEN_FOR_IMPLEMENTATION

## Why
The previous all-or-nothing implementation attempt was interrupted by a power outage before any implementation commit reached the remote branch.

Documentation V2 needs a CI/CD path that produces useful feedback and durable remote checkpoints quickly.

## Principle
**Fast lane on every coherent slice; heavy lane only after review.**

This delta supplements PLAN-ZMI-DOCS-V2-001. It does not alter product contracts.

## CI lanes

### FAST / implementation lane
Expected duration: minutes.

Allowed:
- focused DV2 tests for changed slice;
- directly affected regressions;
- Ruff changed Python surface;
- compileall/typecheck changed surface;
- schema/fixture validation;
- implementation summary.

Forbidden:
- full pytest;
- security full suite;
- smoke full suite;
- E2E/Playwright;
- Docker;
- Sonar;
- Jenkins recursive invocation;
- soak;
- real LLM;
- real media.

### HEAVY / post-review lane
Only after ChatGPT /review authorization and RAM > 6.0 GiB.

Order:
- full pytest
- security
- smoke
- E2E exactly once
- Docker build
- Docker E2E
- Sonar if configured
- Jenkins integration if useful
- optional soak

No LLM supervises heavy validation.

## Slice-specific fast test manifests
Implementation may create deterministic test manifests/scripts, but must not duplicate test logic.

Suggested mapping:

A:
- project config/mode tests
- evidence ids/resolver
- compaction
DV2-01..13 relevant subset

B:
- synthesis parsing/privacy
- grounding validator
- retry bound
DV2-14..20, 44..46

C:
- screenshot selection
- semantic manual/PDF
DV2-21..30

D:
- semantic chunks
- Knowledge Package bridge/idempotency/publisher compatibility
DV2-31..39

E:
- no-upstream regeneration
- compatibility
- synthetic-data guard
DV2-40..48

## Push discipline
After each green slice:
- commit coherent slice;
- push;
- verify remote SHA.

Do not keep hours of finished code only in a working tree.

## CI implementation requirement
Add a lightweight deterministic command for the branch, for example:

```
python scripts/docs_v2_fast_ci.py --slice A
python scripts/docs_v2_fast_ci.py --slice B
...
python scripts/docs_v2_fast_ci.py --all-light
```

The exact filename may vary, but it must:
- call existing pytest/Ruff/typecheck commands, not reimplement them;
- emit compact JSON summary under artifacts/gates/;
- fail fast on configuration errors;
- never call an LLM;
- never start heavy gates;
- run the chosen independent checks in parallel where safe;
- cap worker count to avoid RAM pressure;
- preserve raw logs as artifacts but return compact terminal output.

## Jenkins/self-hosted direction
Do not make GitHub Actions branch pushes a required feedback loop.

Prefer local/self-hosted Jenkins/Lenovo for heavy or scheduled validation to avoid unnecessary hosted-CI cost.

For this branch:
- fast CI may run locally immediately after each slice;
- after infrastructure is available, Jenkins can call the same deterministic fast command;
- one source of truth for commands, no duplicated pipeline logic.

## No unnecessary wait
Do not run a long test merely because a prior plan listed it later.
Use the smallest deterministic test that proves the current slice.

Do not wait for a coder/LLM during deterministic test execution.

## Acceptance
- outage after any slice loses at most the current slice;
- remote contains progress after every completed slice;
- fast failures return compact error signature;
- same signature gets max two mechanical fixes;
- all-light pass is required before READY_FOR_CHATGPT_REVIEW;
- heavy gates remain deferred.
