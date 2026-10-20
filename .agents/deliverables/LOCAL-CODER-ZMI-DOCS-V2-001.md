# LOCAL-CODER-ZMI-DOCS-V2-001

## Status
FROZEN_FOR_IMPLEMENTATION

## Role
Implementation worker only.

All architecture/product/test design is frozen in:
- AUDIT-ZMI-DOCS-V2-001-current-documentation-quality.md
- EPIC-ZMI-DOCS-V2-001-evidence-to-knowledge.md
- SPEC-ZMI-DOCS-V2-001-contracts.md
- US-ZMI-DOCS-V2-001-semantic-documentation.md
- PLAN-ZMI-DOCS-V2-001-implementation.md
- TEST-MATRIX-ZMI-DOCS-V2-001.md
- docs/adr/0007-evidence-is-not-documentation.md

## Worker constraints
- do not redesign;
- do not change enums/contracts without REVIEW_REQUIRED;
- do not use real client data;
- do not process real P&G/confidential videos;
- do not merge;
- do not deploy;
- do not run heavy validation;
- do not call strong planning models;
- no recursive autonomous loops;
- max 2 mechanical fix attempts for same error signature.

## Model routing
Use the already selected cheap coder.
Preferred:
1. Z.ai Coding Plan GLM
2. OpenCode DeepSeek
3. Ollama Server DeepSeek
4. OpenRouter DeepSeek

Fallback only on provider/auth/quota/invocation failure.
A failing test is not a model-routing reason.

## Required implementation order
Execute PLAN WP-01 through WP-20 in order unless a later independent WP can safely continue after a typed blocker.

## Allowed validation
- targeted/unit tests from TEST-MATRIX;
- existing directly affected regressions;
- Ruff;
- compileall;
- targeted Pyright if configured.

No full/heavy gates.

## Completion
Commit and push branch:
`feat/zmi-documentation-synthesis-v2`

Final output only:
```text
BRANCH=feat/zmi-documentation-synthesis-v2
HEAD=<remote sha>
STATUS=<READY_FOR_CHATGPT_REVIEW|REVIEW_REQUIRED|BLOCKED_EXTERNAL>
TARGETED=<PASS|FAIL>
RUFF=<PASS|FAIL|NOT_CONFIGURED>
TYPECHECK=<PASS|FAIL|NOT_CONFIGURED>
HEAVY_VALIDATION=NOT_RUN_PENDING_CHATGPT_REVIEW
REAL_MEDIA=NOT_PROCESSED
FAILED=<none|ids>
BLOCKERS=<none|typed ids>
```
