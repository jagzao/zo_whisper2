# Delivery Loop V4

## Lifecycle

```
OWNER_ANALYSIS
 -> FROZEN_SPEC
 -> STRONG_PLAN
 -> IMPLEMENTATION_WORK_PACKAGES
 -> TARGETED_DETERMINISTIC_VALIDATION
 -> REPAIR_LOOP
 -> RELEASE_GATES
 -> PR/CI
 -> OWNER_AUDIT
 -> HUMAN_ACCEPTANCE
```

## 1. Owner analysis / frozen spec

Product, architecture and UX analysis is performed by the owner with ChatGPT/Claude outside the autonomous coding loop and persisted in Git as EPIC/FEATURE/US/ADR.

Project-lead starts from that frozen contract. It may not silently add product scope.

## 2. Plan

Before production implementation, STRONG_PLANNER creates `PLAN-<US>.md`.

The plan groups implementation into coherent work packages. ACs are acceptance gates, not a forced one-call-per-AC dispatch mechanism.

## 3. Implementation

Use model routing from `model-routing.md`.

Prefer one context-rich coding call for a coherent work package over many micro-calls that reread the same repository context.

FREE_WORKER handles mechanical work.
PRIMARY_CODER handles normal production implementation.
SECONDARY_CODER handles difficult/repeated implementation failures.

## 4. Targeted deterministic validation

Run the smallest authoritative deterministic gate for the changed surface first.

Examples:
- pure module -> targeted pytest
- typing/lint -> Ruff/Pyright
- filesystem/security -> security tests + security.py
- dashboard API -> pytest/integration
- dashboard UI -> Playwright
- media -> FFmpeg/ffprobe fixture check
- code-quality threshold -> SonarQube when configured

Repeated validation must not consume LLM tokens.

## 5. Repair loop

For every failure:

```
CAPTURE -> COMPACT -> CLASSIFY -> REGRESSION TEST -> ROUTE FIX -> RETEST
```

Store the compact failure signature, not only raw stdout.

Do not mark a defect fixed without deterministic evidence.

## 6. Release closure

At feature/US closure run all applicable release gates, not necessarily after every small edit.

Default Zo Media Intelligence closure:
- pytest
- quality.py
- security.py
- smoke.py
- Playwright E2E
- SonarQube quality gate when available/configured
- Jenkins local/long-running workflow when configured
- GitHub Actions/public PR checks when enabled

## 7. Browser validation

Zo Media Intelligence is a web app. Use Playwright Chromium.

Do not add Electron merely for testing.

Generic adapter:
- web -> Playwright Chromium
- electron product -> Playwright Electron
- mobile product -> native/Appium-equivalent automation

An LLM may author the initial scenario. All future reruns are deterministic.

## 8. Definition of Done

A US is DONE only when:
- every required AC has deterministic evidence;
- required code quality/security/browser gates are green;
- no known P0/P1 defect remains inside scope;
- PLAN work packages are complete;
- DELIVERY is filled with real evidence;
- PR/CI state matches the frozen workflow contract;
- runtime checkpoint can be discarded safely;
- owner intervention count is recorded.

## 9. Handoff

Normal autonomous terminal state is `READY_FOR_OWNER_AUDIT`.

Do not require owner conversation between initial spec and final audit unless a permitted blocker from `project-lead.md` occurs.
