# US-PLV4-001 — Deterministic Delivery Toolchain

## Status
`SPEC`

## Parent
EPIC: `.agents/deliverables/EPIC-PLV4-autonomous-delivery.md`

## Frozen scope

Implement the repository tooling required by Project-lead V4 so repeated validation is automated, deterministic, compact, resumable, and low-token.

This US does not change Zo Media Intelligence product behavior.

### Model routing

Project-lead uses the aliases defined by `model-routing.md`:

- `STRONG_PLANNER` — configurable strong planner; planning only.
- `PRIMARY_CODER` — OpenCode Go.
- `FREE_WORKER` — Ollama local.
- `SECONDARY_CODER` — Ollama Pro / Ollama Cloud.

If the repository has a safe tracked OpenCode/provider configuration surface, add provider aliases there without credentials. If provider configuration is necessarily user-local, document the exact local mapping instead of committing secrets/endpoints.

### Compact deterministic gate runner

Add a repository gate runner that can execute named gates and emit a normalized machine-readable report under:

`artifacts/gates/latest.json`

Minimum fields:
- status
- gate
- check
- error_signature
- affected_files when known
- artifact/log path when available
- duration_seconds
- command/runner identity

It must call existing authoritative scripts/tests rather than reimplement their logic.

Required named gates:
- unit/targeted pytest
- quality
- security
- smoke
- e2e/Playwright

Raw logs may be persisted as artifacts, but the default project-lead repair context is the compact report.

### Jenkins

Add a cross-platform `Jenkinsfile` suitable for local/long-running execution.

Pipeline intent:
`targeted -> quality -> security -> Playwright -> SonarQube -> full E2E -> optional soak/nightly -> artifacts`

Requirements:
- Windows and Linux command handling where practical.
- No embedded credentials.
- Sonar stage is explicit and fail-closed when configured as required; local developer mode may clearly mark it NOT_CONFIGURED rather than pretending PASS.
- archive deterministic gate artifacts.
- cleanup test processes/workspaces.

### SonarQube

Add `sonar-project.properties` for this Python repository.

At minimum configure:
- source/test roots
- Python version
- exclusions for generated/runtime/vendor/experimental directories as appropriate
- coverage/test report paths only when the repo actually generates them

Do not fabricate coverage.

Document local configuration through environment/credential store, never committed tokens.

### UI validation adapter

Document/implement the validation selection:
- Zo Media Intelligence web UI -> Playwright Chromium.
- Electron projects -> Playwright Electron.
- Do not add Electron as a runtime dependency to this repository.

Existing Playwright scenarios remain the authoritative repeated UI regression tests.

### No-LLM repeat proof

Provide a deterministic test/demonstration showing that once a gate or Playwright scenario exists, repeated execution does not call any LLM/provider code path.

## Acceptance criteria

1. [ ] AC-1 — named deterministic gate runner emits valid compact JSON for PASS and FAIL — verified by automated tests.
2. [ ] AC-2 — existing quality/security/smoke/e2e behavior remains authoritative and is invoked, not duplicated — verified by code review + tests.
3. [ ] AC-3 — Jenkinsfile supports the V4 stage ordering and archives compact artifacts without committed credentials.
4. [ ] AC-4 — SonarQube project configuration exists and has no fake PASS/coverage claims.
5. [ ] AC-5 — Zo Media Intelligence remains Playwright Chromium; no Electron runtime dependency added.
6. [ ] AC-6 — rerunning deterministic validation performs zero LLM calls — verified by regression test or an instrumented fake-provider assertion.
7. [ ] AC-7 — runtime gate artifacts/checkpoints are gitignored; frozen specs/PLAN/DELIVERY remain tracked.
8. [ ] AC-8 — current repository release gates remain green after implementation.

## Required final gates

- targeted new tests
- `pytest tests/ -q`
- `python scripts/quality.py`
- `python scripts/security.py`
- `python scripts/smoke.py`
- `python scripts/e2e.py`
- Jenkins pipeline validation to the extent available locally
- SonarQube quality gate when configured; otherwise explicit NOT_CONFIGURED evidence, never silent PASS

## Owner interventions

Expected: 2
Actual: 1

1. INITIAL_SPEC — frozen by owner + assistant
2. FINAL_ACCEPTANCE — pending

Unexpected interventions: 0

## Non-goals

- no product feature changes
- no Electron packaging for Zo Media Intelligence
- no cloud provider credential setup in Git
- no replacement of existing security/quality logic with LLM review
- no automatic merge/release as part of this US

## Terminal state

`READY_FOR_OWNER_AUDIT`
