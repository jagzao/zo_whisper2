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
- Non-interactive unattended execution is supported and preferred for overnight runs.

## Source of truth

Read, do not redesign:
1. `.agents/deliverables/AUDIT-ZO-KNOWLEDGE-001-knowledge-to-action.md`
2. `.agents/deliverables/EPIC-ZO-KNOWLEDGE-001-project-aware-knowledge-to-action.md`
3. `.agents/deliverables/SPEC-ZO-KNOWLEDGE-001-cross-repo-contracts.md`
4. `.agents/deliverables/US-ZO-KNOWLEDGE-001-master.md`
5. `.agents/deliverables/PLAN-ZO-KNOWLEDGE-001-cross-repo-implementation.md`
6. `.agents/deliverables/TEST-MATRIX-ZO-KNOWLEDGE-001.md`

These artifacts are authoritative. Do not infer a different product design.

## This run implements Zo Media work

Implement:
- WP-01 — Zo project knowledge configuration
- WP-02 — Knowledge Package v2 domain model
- WP-03 — Durable knowledge outbox
- WP-04 — Documentation completion -> knowledge outbox
- WP-05 — K'ab explicit project identity
- WP-16 — producer-side frozen contract fixtures
- WP-17 — Zo publisher observability
- WP-18 — Zo documentation
- WP-19 — Zo-side deterministic acceptance/evidence

Do NOT implement Zavi or zavi-kab consumer internals in this run.

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

### WP-16 — producer contract fixtures
Create deterministic fixtures under:
`contracts/knowledge-to-action/v1/`

Required semantic fixtures:
- `p-g-project-package.json`
- `azure-global-package.json`
- `confidential-global-invalid-package.json`

They must conform exactly to SPEC-ZO-KNOWLEDGE-001 and be stable/deterministic. They are test/spec fixtures only: no real P&G data, names, URLs, transcripts, credentials or client secrets.

### WP-17 — observability
Expose compact local publisher state without secrets:
- pending count;
- published count;
- failed count;
- last package id;
- last typed result/error code.

Never log full confidential transcript, bearer tokens, service-role keys or cloud credentials.

### WP-18 — documentation
Document:
- project second_brain config;
- PROJECT vs GLOBAL;
- KnowledgeScope vs Zavi LearningScope distinction;
- package v2;
- outbox/retry behavior;
- raw transcript/media exclusion;
- K'ab projectKey behavior.

### WP-19 — Zo deterministic acceptance
Produce compact local evidence for all Zo-side required checks. No LLM evaluates long logs.

## Tests required in this run

Implement/run:
- ZK-01..ZK-20 in TEST-MATRIX;
- existing project validation regressions;
- existing documentation tests;
- existing K'ab targeted tests affected by projectKey/package publishing;
- targeted security tests for traversal/secret/raw-transcript exclusion;
- fixture schema/determinism tests;
- outbox restart/idempotency tests;
- observability redaction tests.

Do not attempt ZV/RT/PR/KV consumer tests in this repository.

## Unattended failure policy

Do not ask the owner routine questions.
Do not stop because one independent deterministic gate fails.

For a directly-caused mechanical compile/type/import/lint/test failure:
- at most 2 bounded repair attempts per identical failure signature.

For product/architecture/expected-behavior ambiguity:
- do NOT invent a decision;
- record REVIEW_REQUIRED;
- preserve evidence;
- continue all independent work.

For unavailable credentials/external service:
- record BLOCKED_EXTERNAL:<typed reason>;
- continue all independent local work.

No infinite loops.

## Git

Work only on:
`feat/zmi-knowledge-to-action-v1`

Before edits:
- verify branch/upstream/status;
- do not reset/stash/delete unrelated work.

On completion:
1. targeted tests;
2. one relevant broader pytest pass if environment supports it;
3. Ruff/Pyright for changed source;
4. security checks;
5. compact evidence;
6. commit;
7. push branch;
8. STOP.

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
SECURITY=<result>
FIXTURES=<result>
OBSERVABILITY=<result>
FAILED_TESTS=<none|ids>
CHANGED_FILES=<count>
BLOCKERS=<none|ids>
```
