# US-XXX — <title>

## Status
`SPEC` | `IN_PROGRESS` | `READY_FOR_OWNER_AUDIT` | `DONE` | `BLOCKED_EXTERNAL` | `SPEC_CONFLICT`

## Parent
EPIC: <id/path>
FEATURE: <id/path>
ADR: <id/path(s) if applicable>

## Frozen scope
Describe the owner-approved functional/technical scope. Project-lead may not silently redefine it.

## Acceptance criteria
Each AC must be independently verifiable by a deterministic test/gate or an explicit final human acceptance step.

1. [ ] AC-1 — <criterion> — evidence: <pytest/playwright/security/sonar/etc.>
2. [ ] AC-2 — ...

## Non-goals
-

## Required deterministic gates
- [ ] targeted tests
- [ ] quality
- [ ] security
- [ ] smoke
- [ ] Playwright/E2E if UI
- [ ] SonarQube if configured/applicable
- [ ] Jenkins integration/soak if configured/applicable
- [ ] public PR CI if enabled

## Planning
PLAN artifact: `.agents/deliverables/PLAN-<US-ID>-<slug>.md`

## Evidence
Fill as work packages/ACs close. Evidence must be deterministic, not an executor claim.

- AC-1:
- AC-2:

## Owner interventions
Expected: 2
Actual: 1 at implementation start
Unexpected: 0

1. INITIAL_SPEC — owner-approved frozen spec
2. FINAL_ACCEPTANCE — pending

Any extra intervention must include blocker category + reason.

## Residual risks
-

## Final state
`READY_FOR_OWNER_AUDIT` only when implementation + required gates + DELIVERY evidence are complete.
