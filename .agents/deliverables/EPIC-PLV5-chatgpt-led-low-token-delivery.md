# EPIC-PLV5 — ChatGPT-led, Low-Token Spec-Driven Delivery

## Status
FROZEN

## Why V5

Project-lead V4 still assumes:
- a STRONG_PLANNER inside the local autonomous loop;
- model-tier escalation during implementation;
- repair loops driven by local LLMs;
- full release gates before owner audit.

That no longer matches the owner's development architecture.

V5 makes ChatGPT/owner the only high-reasoning layer and turns the local agent into a bounded implementation worker.

## Canonical lifecycle

```
OWNER + CHATGPT HIGH-THINKING
  -> /analysis
  -> freeze EPIC/FEATURE/US/ADR/PLAN/TEST-MATRIX/assets in Git
  -> one implementation prompt
  -> CHEAP LOCAL CODER
       code
       compile/typecheck
       lint
       targeted unit tests
       bounded mechanical fixes only
       commit + push
       compact SUMMARY
  -> CHATGPT /review
       diff + summary + focused artifacts
       decide READY_FOR_HEAVY_VALIDATION or DELTA_REQUIRED
  -> deterministic RAM gate
       available RAM > 6 GiB ?
          yes -> heavy deterministic validation now
          no  -> HEAVY_VALIDATION_DEFERRED_LOW_RAM / nighttime
  -> heavy deterministic validation
       full regression/integration
       E2E/Playwright
       Docker
       security/dependency audit
       Jenkins/Sonar when configured
       no LLM waiting/polling
  -> compact SUMMARY
  -> CHATGPT /review
  -> owner acceptance
```

## Absolute responsibility boundary

### Owner + ChatGPT
Own:
- product analysis;
- architecture;
- UX;
- security design;
- scope;
- User Stories;
- Acceptance Criteria;
- implementation plan down to files/interfaces/algorithms when needed;
- assets/icons/fonts/CSS/UI behavior;
- migration strategy;
- deterministic test design;
- failure diagnosis after implementation/heavy validation;
- any delta/re-plan.

### Local coder
Own:
- implementation of frozen plan;
- compile/typecheck;
- lint;
- targeted unit tests;
- small deterministic fixtures;
- mechanical corrections directly implied by diagnostics;
- commit/push;
- compact evidence.

The local coder does NOT own:
- architecture;
- product decisions;
- re-planning;
- acceptance changes;
- test weakening;
- autonomous behavior changes;
- heavy failure diagnosis.

## Model policy

One local coding model is selected from the approved cheap fallback chain:

1. Z.ai Coding Plan — owner-approved GLM coder; currently known working: `zai-coding-plan/glm-5.2`. Prefer an explicitly configured cheaper GLM variant when the owner has approved it.
2. OpenCode provider — DeepSeek coding model.
3. Ollama server — DeepSeek coding model.
4. OpenRouter — DeepSeek coding model.

Never auto-escalate to:
- OpenAI/Codex/GPT;
- Claude;
- Kimi;
- any premium planner/reviewer.

Provider/model fallback is allowed only for provider unavailability, quota exhaustion, authentication failure, or model invocation failure — not because a test is red.

## Token rules

- no strong planner inside local runtime;
- no nested LLM subagents by default;
- no autonomous recursive repair loop;
- at most 2 bounded mechanical repair attempts for one identical failure signature;
- deterministic tools do not consume LLM;
- no LLM waits for pytest/Playwright/Docker/Jenkins/Sonar;
- raw logs are not fed to an LLM by default;
- compact JSON/MD evidence first.

## Validation split

### Implementation gates — local coder may run
- compile/build of changed surface;
- Ruff/formatter/lint;
- Pyright/typecheck;
- targeted unit tests for changed surface;
- small deterministic integration test only when explicitly listed in frozen PLAN and low-cost.

### Heavy gates — NOT run before ChatGPT /review
- full repository regression suite when materially expensive;
- Playwright full E2E;
- browser trace-heavy flows;
- Docker build/full E2E;
- real tiny-ASR/model download;
- SonarQube;
- Jenkins full pipeline;
- soak/load;
- dependency/security scans that require large downloads or long external work.

Heavy validation is owner/ChatGPT-authorized after /review.

## RAM policy for heavy validation

Before heavy gates, deterministically measure available physical RAM.

Threshold:
```
available_ram_gib > 6.0
```

If true:
`HEAVY_VALIDATION_ALLOWED`

If false:
`HEAVY_VALIDATION_DEFERRED_LOW_RAM`

Low RAM is not a product failure and must not cause an LLM loop.
Nighttime execution may retry the deterministic RAM gate and run heavy tests when capacity is available.

## Power-loss / resume policy

Every implementation run maintains a gitignored checkpoint with:
- repo;
- branch;
- starting SHA;
- current SHA;
- active frozen contract;
- completed implementation work packages;
- targeted gates run/results;
- last commit/push;
- remaining mechanical work;
- terminal state.

After reboot:
```
LOAD_CHECKPOINT
 -> VERIFY_REPO_AND_REMOTE
 -> VERIFY_NO_UNCOMMITTED_OWNER_WORK_IS_OVERWRITTEN
 -> RESUME_FROM_FIRST_INCOMPLETE_MECHANICAL_STEP
```

Never re-run /analysis locally merely because power/session was lost.

## Terminal states

Local implementation:
- `READY_FOR_CHATGPT_REVIEW`
- `REVIEW_REQUIRED`
- `BLOCKED_EXTERNAL:<reason>`
- `SPEC_CONFLICT`

Post-review heavy validation:
- `HEAVY_VALIDATION_PASS`
- `HEAVY_VALIDATION_FAIL`
- `HEAVY_VALIDATION_DEFERRED_LOW_RAM`
- `BLOCKED_EXTERNAL:<reason>`

No local terminal state implies owner acceptance.
