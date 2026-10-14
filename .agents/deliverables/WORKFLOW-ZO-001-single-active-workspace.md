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

If unrelated owner changes coexist and prevent a safe branch switch, use ONE temporary preservation branch in the SAME workspace:

1. inspect all modified/untracked files;
2. verify no secrets/private runtime data will be committed;
3. create a clearly named temporary branch, e.g. `wip/zo-whisper-preserve-YYYYMMDD-HHMM`;
4. commit the unrelated local changes there with a WIP/preservation message;
5. push that branch immediately;
6. return the same workspace to the active feature branch;
7. finish the active feature;
8. reconcile/delete the preservation branch later with owner review.

This is a preservation mechanism, not a parallel implementation stream.

Do not create another worktree to park changes.

Never:
- git reset --hard owner work;
- git clean -fd owner work;
- auto-stash unrelated work;
- discard untracked owner files;
- spawn additional worktrees to avoid understanding current state.

If a temporary preservation branch would include secrets, credentials, private media, raw client data, or unsafe generated artifacts:
- do not commit them;
- stop with REVIEW_REQUIRED and report the exact blocker.

## Result semantics
If work is blocked before implementation/tests run, report:
- NOT_RUN / BLOCKED_PRECONDITION
instead of falsely reporting implementation FAIL.

A feature/test is FAIL only after the relevant implementation/test actually ran and failed.

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
7. Review the already-pushed Live Capture Slice A/B checkpoints.
8. Resume from Slice C.
9. Continue from the frozen EPIC/SPEC/PLAN/TEST-MATRIX.

Live Capture implementation stays parked remotely until step 6.
