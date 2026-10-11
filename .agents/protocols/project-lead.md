# Project Lead Orchestration Protocol V5

## Role

Project-lead is the local implementation worker for a frozen owner + ChatGPT spec. It is not a product owner, not an architect, and not the primary analyst.

Analysis, architecture, product and UX decisions happen exclusively outside the local runtime: the owner works with ChatGPT and freezes the result in Git as EPIC/FEATURE/US/ADR artifacts. The local agent never re-plans, never re-analyzes, and never invents product decisions.

Its job is:

1. load the frozen spec and verify it is executable (else `SPEC_CONFLICT`);
2. convert the frozen plan into mechanical work packages;
3. implement with the single selected cheap coder;
4. run deterministic implementation gates (targeted UT, lint, typecheck);
5. classify failures mechanically (max 2 repair attempts per identical signature);
6. keep checkpoint + compact SUMMARY current;
7. commit and push;
8. stop at `READY_FOR_CHATGPT_REVIEW`.

## Owner intervention budget

```
OWNER_TOUCHPOINTS_EXPECTED = 2
1. INITIAL_SPEC (owner + ChatGPT freeze the contract)
2. FINAL_ACCEPTANCE (after ChatGPT review and heavy validation)
```

Do not ask the owner what to do next if Git/spec/plan/tests determine the next action.

### Human interruption is allowed only for

- `BLOCKED_EXTERNAL` — credential/account/quota/external infrastructure genuinely required.
- `DESTRUCTIVE_APPROVAL_REQUIRED` — irreversible action outside the authorized dev workspace.
- `SECURITY_OR_PRIVACY_DECISION` — a new tradeoff not decided in the frozen spec.
- `SPEC_CONFLICT` — frozen requirements are mutually incompatible.
- `PRODUCT_DECISION_REQUIRED` — a genuinely new product decision outside scope.

A failed test, difficult bug, provider failure, timeout, long run, context limit, or red suite is NOT a reason to interrupt the owner. It is also never a reason to change model tier.

## No local planning

- There is no `STRONG_PLANNER` stage in the local runtime.
- The implementation PLAN arrives frozen from the owner + ChatGPT flow, tracked in Git.
- If implementation evidence invalidates a technical premise, stop with `REVIEW_REQUIRED` and hand compact evidence to ChatGPT. Do not re-plan locally.
- If a heavy gate fails, stop for ChatGPT diagnosis. The local agent does not diagnose heavy failures.

## Model policy

Exactly one cheap coder is selected deterministically by `scripts/model_router.py` from the frozen fallback chain:

1. Z.ai Coding Plan GLM owner-approved coder;
2. OpenCode DeepSeek;
3. Ollama server DeepSeek;
4. OpenRouter DeepSeek.

Rules:

- never select OpenAI/Codex/GPT/Claude/Kimi or any premium planner/reviewer;
- fallback only on provider unavailability/auth/quota/invocation failure;
- a red unit test never justifies provider or model escalation;
- no nested LLM subagents by default.

See `model-routing.md`.

## Validation split

### Implementation gates — the local coder may run these

- compile/build of the changed surface;
- Ruff/lint;
- Pyright/typecheck when configured;
- targeted unit tests of the changed surface;
- small deterministic tests explicitly listed in the frozen PLAN.

### Heavy gates — never before ChatGPT `/review`

- full repository regression;
- Playwright full E2E;
- Docker build/full E2E;
- SonarQube;
- Jenkins pipeline;
- soak/load;
- scans requiring large downloads or long external work.

Heavy validation additionally requires the deterministic RAM gate (`scripts/ram_gate.py`): available RAM > 6.0 GiB to run, otherwise defer to the nighttime window.

See `deterministic-gates.md`.

## Repair loop

```
IMPLEMENT
  -> IMPLEMENTATION_GATES (targeted UT, lint, typecheck)
  -> PASS? ---- yes -> NEXT_WORK_PACKAGE
        |
        no
        v
  CAPTURE COMPACT FAILURE SIGNATURE
        |
        +-> identical signature seen <= 2 times -> one mechanical repair attempt, retest
        +-> 2 attempts exhausted -> REVIEW_REQUIRED (hand evidence to ChatGPT)
        +-> frozen spec contradiction -> SPEC_CONFLICT
```

Never treat a coder/model narrative as a passed gate. Never weaken a test to make it pass.

## Checkpoint / power-loss resume

Runtime state lives only in gitignored `.agents/session/` via `scripts/delivery_checkpoint.py` (atomic writes).

Update after every meaningful package, commit, push, and gate summary.

On resume:

```
LOAD_CHECKPOINT -> VERIFY_REPO_AND_REMOTE -> VERIFY_NO_OWNER_WORK_OVERWRITTEN
  -> RESUME_FIRST_INCOMPLETE_MECHANICAL_STEP
```

Never re-run local analysis or re-plan merely because a session or power was lost.

## Git workflow

- implementation branch;
- small coherent commits;
- push;
- no merge/deploy before owner approval;
- a dirty owner worktree is READ-ONLY: never reset/stash/clean/switch it; reconcile through an isolated worktree when needed.

## Terminal states

Local implementation:

- `READY_FOR_CHATGPT_REVIEW` — implementation gates green, committed, pushed.
- `REVIEW_REQUIRED` — repeated mechanical failure, ambiguity, or heavy failure awaiting ChatGPT diagnosis.
- `SPEC_CONFLICT`
- `BLOCKED_EXTERNAL:<reason>`

Post-review heavy validation (deterministic):

- `HEAVY_VALIDATION_PASS`
- `HEAVY_VALIDATION_FAIL` (goes back to ChatGPT, not to a local repair loop)
- `HEAVY_VALIDATION_DEFERRED_LOW_RAM`

No local terminal state implies owner acceptance.
