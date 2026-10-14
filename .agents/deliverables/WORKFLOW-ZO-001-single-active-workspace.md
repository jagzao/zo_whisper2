# WORKFLOW-ZO-001 — Single active workspace / finish-first delivery

## Status
OWNER_RULE / AUTHORITATIVE

## Rule
For each repository/project, use ONE normal active worktree/workspace.

Do NOT create isolated/parallel worktrees as a routine delivery strategy.

The delivery sequence is:

1. identify the currently active branch/task;
2. recover any local work after interruption;
3. finish that work completely;
4. targeted/light CI;
5. ChatGPT review;
6. heavy deterministic validation when authorized;
7. real acceptance when required;
8. merge/close/archive the completed branch according to owner instruction;
9. switch the SAME normal workspace to the next already-analyzed branch;
10. continue from its frozen spec.

## Safety on a dirty workspace
A dirty workspace is not a reason to create another worktree.

Instead:
- inspect status/diff;
- identify whether changes belong to the active task;
- preserve them;
- commit coherent active-task changes early;
- push checkpoints frequently.

If unrelated owner changes coexist and cannot safely be separated mechanically:
- STOP with REVIEW_REQUIRED and report exact files;
- do not stash/reset/clean/discard automatically.

Never:
- git reset --hard owner work;
- git clean -fd owner work;
- auto-stash unrelated work;
- spawn additional worktrees to avoid understanding current state.

## Concurrency
Analysis/specification for the NEXT feature may be frozen in Git while current work is still being finished.

Implementation of the next feature MUST NOT begin until the current feature reaches its owner-approved completion gate.

This preserves project continuity and avoids branch/worktree proliferation.

## CI/CD resilience
Power-loss resilience comes from:
- small vertical slices;
- targeted fast CI;
- frequent coherent commits;
- immediate push;
- atomic checkpoints;
not from parallel worktrees.

## Current Zo Media Intelligence sequence
1. Finish Documentation Synthesis V2 on `feat/zmi-documentation-synthesis-v2`.
2. Final ChatGPT review.
3. Heavy deterministic validation.
4. One real non-sensitive Documentation V2 quality benchmark.
5. Owner acceptance / merge decision.
6. Only then switch the same normal workspace to `feat/zmi-live-capture-v1`.
7. Implement Live Capture from the already-frozen EPIC/SPEC/PLAN/TEST-MATRIX.

Live Capture analysis may remain parked remotely until step 6.
