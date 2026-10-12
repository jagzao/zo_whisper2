# OVERNIGHT-ZO-KNOWLEDGE-001 — Unattended cross-repo implementation

## Status
FROZEN_FOR_EXECUTION

## Purpose

Execute the complete currently-approved implementation scope of EPIC-ZO-KNOWLEDGE-001 overnight without Codex, without owner interaction, and without delegating product analysis to the coding model.

## Runtime

Each repository is executed as an independent **OpenCode CLI non-interactive run**.

Required model:
`zai-coding-plan/glm-5.2`

Required execution properties:
- OpenCode starts directly from PowerShell; never from Codex.
- main model = GLM-5.2;
- small model = GLM-5.2;
- only provider allowed = `zai-coding-plan`;
- subagent depth = 0;
- custom `implementation-worker` primary agent;
- external plugins disabled with `--pure`;
- normal permission prompts auto-approved with `--auto`;
- task/subagent, web research and routine question tools are denied by the project agent contract;
- no premium planner/reviewer model;
- no external product analysis.

## Sequence

### RUN-01 — Zo Media producer
Repo: `jagzao/zo_whisper2`
Branch: `feat/zmi-knowledge-to-action-v1`
Contract:
`.agents/deliverables/LOCAL-CODER-ZO-KNOWLEDGE-001.md`

Covers:
- WP-01..05
- producer WP-16..19

### RUN-02 — Zavi Second Brain
Repo: `jagzao/zavi`
Branch: `feat/knowledge-scope-publishing-v1`
Contract:
`.agents/delivery/LOCAL-CODER-ZO-KNOWLEDGE-002.md`

Frozen cross-repo contract copies:
- `.agents/delivery/SPEC-ZO-KNOWLEDGE-001-cross-repo-contracts.md`
- `.agents/delivery/TEST-MATRIX-ZO-KNOWLEDGE-001.md`

Covers:
- WP-06..12
- consumer WP-16..19

### RUN-03 — KAV execution
Repo: `jagzao/zavi-kab`
Branch: `feat/knowledge-bound-skills-v1`
Contract:
`.agents/memory/tasks/LOCAL-CODER-ZO-KNOWLEDGE-003.md`

Frozen cross-repo contract copies:
- `.agents/memory/tasks/SPEC-ZO-KNOWLEDGE-001-cross-repo-contracts.md`
- `.agents/memory/tasks/TEST-MATRIX-ZO-KNOWLEDGE-001.md`

Covers:
- WP-13..15
- KAV WP-16..19

## Dependency/failure policy

The three implementations are independently useful and their contracts are frozen.

Therefore:
- RUN-02 continues even if RUN-01 finishes REVIEW_REQUIRED.
- RUN-03 continues even if RUN-01 or RUN-02 finishes REVIEW_REQUIRED.
- one failed test does not cancel independent work;
- a local worktree conflict is isolated by a dedicated git worktree when possible;
- an external blocker is recorded, not asked about overnight.

The coding model may perform at most two bounded mechanical repairs for one identical failure signature.

It may NOT:
- change product behavior;
- change security boundary;
- weaken acceptance criteria;
- apply Supabase migration to production;
- execute real Azure writes;
- merge;
- deploy;
- use another LLM/provider;
- ask owner questions.

## Final cross-repo deterministic closeout

After all OpenCode processes finish, the master PowerShell launcher performs zero-LLM checks:
- each branch has a commit SHA;
- each expected local SUMMARY.json exists if the worker reached evidence generation;
- frozen fixture JSON files parse;
- P&G fixture remains PROJECT/p-g;
- Azure fixture remains GLOBAL;
- no confidential GLOBAL fixture is treated as a valid publishable package;
- KAV knowledge-bound fixture presence is recorded.

It writes:
`<run-root>/MASTER-SUMMARY.json`
and
`<run-root>/MASTER-SUMMARY.md`.

No LLM analyzes failures overnight.

## Terminal state

If all three repository summaries report their READY_FOR_REVIEW state:
`READY_FOR_OWNER_REVIEW`

Otherwise:
`REVIEW_REQUIRED`

This state means "bring compact evidence to owner + heavy reasoning model"; it never triggers another expensive model automatically.
