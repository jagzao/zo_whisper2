# RESUME-PLV5-POWER-LOSS-20261010 — Reconcile Project Lead, then resume Knowledge-to-Action

## Status
FROZEN_FOR_EXECUTION

## Context

A power outage interrupted the previous unattended Knowledge-to-Action attempt.

Git review after reboot proves:
- no Knowledge-to-Action implementation commit was produced by the interrupted GLM run;
- the three Knowledge-to-Action branches still contain frozen contracts/tooling only;
- the local `feat/project-lead-v4-autonomous-delivery` worktree may contain uncommitted V4/toolchain changes and MUST be preserved;
- remote Project Lead V4 is architecturally outdated relative to the owner's current low-token workflow.

Therefore this resume run has TWO ordered phases.

# PHASE 1 — Project Lead V5 first

Repository:
`jagzao/zo_whisper2`

Current local dirty branch expected:
`feat/project-lead-v4-autonomous-delivery`

Remote frozen V5 authority:
- `.agents/deliverables/EPIC-PLV5-chatgpt-led-low-token-delivery.md`
- `.agents/deliverables/US-PLV5-low-token-workflow.md`
- `.agents/deliverables/PLAN-PLV5-low-token-workflow.md`
- `.agents/deliverables/TEST-MATRIX-PLV5-low-token-workflow.md`

The worker MUST read these files from `origin/feat/project-lead-v4-autonomous-delivery` if the local dirty branch cannot fast-forward.

## Required sequence

1. `git fetch origin`.
2. Treat the original dirty worktree as READ-ONLY owner state. Do NOT pull/switch/reset/stash/clean/commit/rebase it.
3. Read frozen V5 artifacts directly from origin with `git show origin/feat/project-lead-v4-autonomous-delivery:<path>`.
4. Create an isolated Project Lead reconciliation worktree from latest `origin/feat/project-lead-v4-autonomous-delivery` (detached or temporary local branch).
5. Inspect the dirty owner worktree only to recover existing Project Lead/tooling candidate changes.
6. Copy/apply ONLY the allowlisted Project Lead/tooling files from the dirty owner worktree into the isolated integration worktree.
7. Reconcile those files mechanically to the exact frozen V5 plan in the isolated worktree.
8. Implement any remaining V5 tooling/protocol changes there.
9. Run ONLY V5 lightweight targeted validation:
   - targeted workflow/router/RAM/checkpoint tests;
   - Ruff on changed tooling;
   - Pyright/typecheck on changed tooling when configured.
8. Do NOT run full repository E2E, Docker, Jenkins, Sonar, soak or full heavy regression in Phase 1.
10. Selectively stage only the allowlisted Project Lead/tooling paths defined by PLAN-PLV5 in the ISOLATED worktree.
11. Commit the Project Lead V5 implementation there.
12. Fetch origin again.
13. If remote advanced concurrently, rebase the CLEAN isolated integration commit(s) there; never rebase the dirty owner worktree.
14. Push HEAD to `feat/project-lead-v4-autonomous-delivery`.
15. Verify remote SHA contains the Project Lead V5 implementation.
16. Write compact implementation summary.
17. Only then enter PHASE 2.

The original dirty owner worktree MUST remain byte-for-byte untouched by Phase 1 except for read-only inspection.

# PHASE 2 — Resume Knowledge-to-Action implementation

## Frozen cross-repo architecture

The complete approved architecture is already in Git on:

`jagzao/zo_whisper2:feat/zmi-knowledge-to-action-v1`

Primary frozen artifacts:
- `.agents/deliverables/AUDIT-ZO-KNOWLEDGE-001-knowledge-to-action.md`
- `.agents/deliverables/EPIC-ZO-KNOWLEDGE-001-project-aware-knowledge-to-action.md`
- `.agents/deliverables/SPEC-ZO-KNOWLEDGE-001-cross-repo-contracts.md`
- `.agents/deliverables/US-ZO-KNOWLEDGE-001-master.md`
- `.agents/deliverables/PLAN-ZO-KNOWLEDGE-001-cross-repo-implementation.md`
- `.agents/deliverables/TEST-MATRIX-ZO-KNOWLEDGE-001.md`

Important frozen product decisions include:
- KnowledgeScope = PROJECT | GLOBAL;
- P&G-derived tutorials default PROJECT / `p-g`;
- GLOBAL promotion is explicit, never automatic;
- confidential + GLOBAL is invalid;
- raw P&G transcripts/VTT/media are not published to Second Brain;
- KnowledgeActionability = REFERENCE | GUIDED | EXECUTABLE;
- knowledge is not executable authority;
- procedure -> candidate -> capability binding -> VALIDATED skill -> policy/approval -> execution -> receipt;
- Zo Media uses durable outbox/publisher boundary; no Supabase service-role key in Zo;
- Zavi retrieval = GLOBAL + exact active PROJECT only;
- KAV execution enforces project scope, validation status, capabilities, approval, pre/postconditions;
- Azure Data Factory proof is deterministic fake capability only, no real Azure mutation in this implementation.

## Branches and current reviewed heads before implementation

At post-outage review:
- Zo Media: `feat/zmi-knowledge-to-action-v1` @ `190a3aecfc02c3c486953cfb69395b9f8c972d68`
- Zavi: `feat/knowledge-scope-publishing-v1` @ `82d163f13cb7bfd868d5642418a80975caff9be7`
- KAV: `feat/knowledge-bound-skills-v1` @ `0da3df120f24de76dea0d09d85a5215534db171c`

These SHAs are reference points, not reset targets. Fetch and preserve any newer remote commit if present.

## Phase 2 execution order

### 2A — Zo Media
Contract:
`.agents/deliverables/LOCAL-CODER-ZO-KNOWLEDGE-001.md`

Implement all frozen Zo producer work:
- scoped project publishing;
- Knowledge Package v2;
- procedure output;
- durable outbox/publisher;
- K'ab explicit project identity;
- contract fixtures;
- observability/docs;
- targeted deterministic tests.

Under PLV5, run ONLY:
- compile/typecheck;
- Ruff/lint;
- targeted UT;
- explicitly frozen lightweight tests.

Do NOT run full E2E/Docker/Jenkins/Sonar/heavy validation before ChatGPT review.

Commit + push.
Write compact summary.

### 2B — Zavi
Contract:
`.agents/delivery/LOCAL-CODER-ZO-KNOWLEDGE-002.md`

Implement:
- scope types;
- additive migrations (DO NOT apply live);
- import API;
- GLOBAL + active PROJECT lexical/vector retrieval;
- normalized Second Brain scope;
- controlled promotion/version/supersede;
- procedure/skill candidate;
- fixtures/observability/docs;
- targeted unit/type/lint tests.

No heavy validation yet.
Commit + push.
Write compact summary.

### 2C — KAV
Contract:
`.agents/memory/tasks/LOCAL-CODER-ZO-KNOWLEDGE-003.md`

Implement:
- knowledge-bound skill model;
- execution guards;
- fake Azure Data Factory capability proof;
- fixtures/observability/docs;
- targeted unit/build/lint tests.

No real Azure write.
No Android deploy.
No heavy cross-repo E2E yet.
Commit + push.
Write compact summary.

# Model routing for all local coding

Use exactly the PLV5 cheap fallback chain:

1. Z.ai Coding Plan GLM owner-approved coder.
2. OpenCode DeepSeek.
3. Ollama-server DeepSeek.
4. OpenRouter DeepSeek.

Never auto-use:
- OpenAI/Codex/GPT;
- Claude;
- Kimi;
- premium planners/reviewers.

Fallback only for provider/model availability/auth/quota/invocation failure.
A red test does NOT justify changing model tier.

# No-loop / interruption policy

- no local architecture/product analysis;
- no re-planning;
- no subagent planner;
- no recursive autonomous repair;
- max 2 mechanical attempts per identical failure signature;
- no owner question for routine failures;
- continue independent work after a failure;
- preserve compact evidence;
- product/behavior ambiguity -> REVIEW_REQUIRED, do not invent;
- external blocker -> record and continue independent local work;
- deterministic process can wait for its own completion without an LLM polling it;
- no raw log ingestion by model by default.

# RAM / heavy validation rule

This resume run does NOT execute heavy validation.

After all implementation branches are committed/pushed:
`READY_FOR_CHATGPT_REVIEW`

ChatGPT then decides if heavy validation may start.

When authorized, heavy validation MUST first run the deterministic RAM gate:
- available RAM > 6.0 GiB -> run heavy validation;
- available RAM <= 6.0 GiB -> defer to nighttime.

# Required final output

```
PROJECT_LEAD_BRANCH=feat/project-lead-v4-autonomous-delivery
PROJECT_LEAD_HEAD=<remote sha>
PROJECT_LEAD_STATUS=<PASS|REVIEW_REQUIRED|BLOCKED_EXTERNAL>

ZO_BRANCH=feat/zmi-knowledge-to-action-v1
ZO_HEAD=<remote sha>
ZO_STATUS=<READY_FOR_CHATGPT_REVIEW|REVIEW_REQUIRED|BLOCKED_EXTERNAL>

ZAVI_BRANCH=feat/knowledge-scope-publishing-v1
ZAVI_HEAD=<remote sha>
ZAVI_STATUS=<READY_FOR_CHATGPT_REVIEW|REVIEW_REQUIRED|BLOCKED_EXTERNAL>

KAV_BRANCH=feat/knowledge-bound-skills-v1
KAV_HEAD=<remote sha>
KAV_STATUS=<READY_FOR_CHATGPT_REVIEW|REVIEW_REQUIRED|BLOCKED_EXTERNAL>

HEAVY_VALIDATION=NOT_RUN_PENDING_CHATGPT_REVIEW
FAILED_TARGETED=<none|ids>
BLOCKERS=<none|typed ids>
```

Then STOP. No merge. No deploy. No heavy validation.
