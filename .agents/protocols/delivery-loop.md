# Delivery Loop V5

## Lifecycle

```
OWNER_ANALYSIS (owner + ChatGPT, outside local runtime)
  -> FROZEN_SPEC (EPIC/FEATURE/US/ADR in Git)
  -> FROZEN_PLAN (in Git; no local STRONG_PLAN stage)
  -> MECHANICAL_WORK_PACKAGES
  -> IMPLEMENTATION (single selected cheap coder)
  -> IMPLEMENTATION_GATES (targeted UT, lint, typecheck)
  -> BOUNDED_REPAIR (max 2 per identical signature)
  -> COMMIT + PUSH
  -> READY_FOR_CHATGPT_REVIEW
  -> [ChatGPT /review]
  -> HEAVY_VALIDATION (RAM-gated, deterministic, LLM-free)
  -> OWNER_ACCEPTANCE
```

## 1. Owner analysis / frozen spec

Product, architecture and UX analysis is performed by the owner with ChatGPT outside the autonomous coding loop and persisted in Git as EPIC/FEATURE/US/ADR.

Project-lead starts from that frozen contract. It may not silently add product scope, and it may not re-plan.

## 2. Frozen plan

The implementation PLAN is part of the frozen contract in Git. If a genuine contradiction appears, stop with `SPEC_CONFLICT`. If a technical premise is invalidated by evidence, stop with `REVIEW_REQUIRED` and hand compact evidence to ChatGPT.

## 3. Implementation

One cheap coder selected by `scripts/model_router.py` from the frozen fallback chain. No planner, no tier escalation, no subagents.

Prefer one context-rich implementation pass per coherent work package over many micro-dispatches that reread the same repository context.

## 4. Implementation gates (before review)

Run only:

- compile/typecheck of the changed surface;
- Ruff/lint;
- targeted unit tests of the changed surface;
- explicitly frozen lightweight deterministic tests.

These gates run via `scripts/gate_runner.py` light-category gates and never consume LLM tokens.

## 5. Bounded repair

```
CAPTURE -> COMPACT -> CLASSIFY -> REGRESSION TEST -> ONE REPAIR ATTEMPT -> RETEST
```

- identical mechanical failure signature: at most 2 repair attempts, then `REVIEW_REQUIRED`;
- never weaken a test to make it pass;
- never mark a defect fixed without deterministic evidence;
- product/behavior ambiguity -> `REVIEW_REQUIRED`, do not invent.

## 6. Heavy gates (after ChatGPT /review)

Never run before `/review`. When authorized, `scripts/heavy_validation_runner.py`:

1. runs `scripts/ram_gate.py` first;
2. available RAM > 6.0 GiB -> run heavy gates;
3. available RAM <= 6.0 GiB -> `HEAVY_VALIDATION_DEFERRED_LOW_RAM`, defer to nighttime;
4. runs gates sequentially with no LLM, continuing after one failure;
5. never modifies product code;
6. a heavy failure goes to ChatGPT for diagnosis, never to a local repair loop.

## 7. Checkpoint / power-loss resume

`scripts/delivery_checkpoint.py` atomically maintains `.agents/session/delivery-checkpoint.json`.

```
LOAD_CHECKPOINT -> VERIFY_REPO_AND_REMOTE -> RESUME_FIRST_INCOMPLETE_MECHANICAL_STEP
```

A session/power loss never triggers local re-analysis or re-planning.

## 8. Evidence and summary

Each implementation run ends with `scripts/implementation_summary.py` writing a compact `SUMMARY.json`/`SUMMARY.md` (contract id, branch, SHAs, changed files, selected model, gate results, blockers, terminal state). Raw logs are never embedded.

## 9. Handoff

Normal autonomous terminal state is `READY_FOR_CHATGPT_REVIEW`.

Do not require owner conversation between the initial instruction and that state unless a permitted blocker from `project-lead.md` occurs.

No merge. No deploy. No heavy validation without ChatGPT authorization.
