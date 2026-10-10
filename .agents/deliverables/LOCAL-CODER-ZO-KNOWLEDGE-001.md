# LOCAL-CODER-ZO-KNOWLEDGE-001 — Zo Media producer implementation

## Status
FROZEN_FOR_IMPLEMENTATION

## Runtime identity
- Runner: OpenCode directly, never Codex.
- Agent: `implementation-worker`.
- Model: `zai-coding-plan/glm-5.2`.
- Subagents: forbidden.
- Web research: forbidden.
- Planning/analysis skills: forbidden.

## Source of truth

Read, do not redesign:
1. `.agents/deliverables/AUDIT-ZO-KNOWLEDGE-001-knowledge-to-action.md`
2. `.agents/deliverables/EPIC-ZO-KNOWLEDGE-001-project-aware-knowledge-to-action.md`
3. `.agents/deliverables/SPEC-ZO-KNOWLEDGE-001-cross-repo-contracts.md`
4. `.agents/deliverables/US-ZO-KNOWLEDGE-001-master.md`
5. `.agents/deliverables/PLAN-ZO-KNOWLEDGE-001-cross-repo-implementation.md`
6. `.agents/deliverables/TEST-MATRIX-ZO-KNOWLEDGE-001.md`

## This run implements ONLY Zo Media work

Implement:
- WP-01 — Zo project knowledge configuration
- WP-02 — Knowledge Package v2 domain model
- WP-03 — Durable knowledge outbox
- WP-04 — Documentation completion -> knowledge outbox
- WP-05 — K'ab explicit project identity

Do NOT implement Zavi or zavi-kab consumer work in this run.
That avoids external-directory access and prevents one cheap coder from having to infer cross-repo decisions.

## Required behavior

### WP-01
- add PROJECT/GLOBAL knowledge scope;
- add REFERENCE/GUIDED/EXECUTABLE actionability;
- add artifact type enum;
- validate optional second_brain config;
- legacy config unchanged;
- publishing absent/disabled by default;
- PROJECT requires project_id/domain;
- GLOBAL confidential rejected;
- add examples/tests.

### WP-02
Create `src/transcript_pipeline/knowledge/` with typed models, deterministic identity/policy/package builder.
Add backward-compatible:
- `knowledge-package.json`;
- `procedure.json` for procedural content.

Preserve existing manual/AI package outputs.

### WP-03
Create durable `DATA_ROOT/knowledge-outbox/{pending,publishing,published,failed}` + ledger.
Use atomic writes/moves, packageId idempotency, bounded retry/backoff.
No Supabase service-role credential in this repo.

### WP-04
After successful documentation:
- resolve exact project routing/config;
- disabled -> no-op;
- enabled -> build package and enqueue;
- publisher outage must not fail documentation generation;
- raw transcript/media must not be published.

Reuse the SAME package builder for K'ab consolidated sessions.

### WP-05
Extend K'ab session contract with optional explicit `projectKey`, backwards compatible.
Persist atomically.
Do not guess project from phone filename.
If project cannot be deterministically resolved, processing still completes but Second Brain publishing is disabled for that session.

If a project catalog endpoint is needed by the frozen plan, expose safe authenticated fields only.

## Tests required in this run

Implement/run Zo/K'ab side tests from:
- ZK-01..ZK-20 in TEST-MATRIX;
- existing project validation regressions;
- existing documentation tests;
- existing K'ab targeted tests affected by projectKey/package publishing;
- targeted security tests for traversal/secret/raw-transcript exclusion.

Do not attempt ZV/RT/PR/KV cross-repo tests yet.

## Git

Work only on:
`feat/zmi-knowledge-to-action-v1`

Before edits:
- verify branch;
- verify upstream;
- inspect git status;
- do not reset/stash/delete unrelated work.

On completion:
1. targeted tests;
2. one relevant broader pytest pass if environment supports it;
3. Ruff/Pyright for changed source;
4. commit;
5. push branch;
6. STOP.

No merge.

## Terminal statuses

`ZO_PRODUCER_READY_FOR_REVIEW`
or
`REVIEW_REQUIRED`
or
`BLOCKED_EXTERNAL:<reason>`

## Final response only

```
BRANCH=feat/zmi-knowledge-to-action-v1
HEAD=<sha>
STATUS=<ZO_PRODUCER_READY_FOR_REVIEW|REVIEW_REQUIRED|BLOCKED_EXTERNAL:...>
TARGETED=<result>
PYTEST=<result>
RUFF=<result>
PYRIGHT=<result>
FAILED_TESTS=<none|ids>
CHANGED_FILES=<count>
BLOCKERS=<none|ids>
```
