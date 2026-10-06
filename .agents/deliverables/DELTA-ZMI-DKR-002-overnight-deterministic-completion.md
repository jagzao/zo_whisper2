# DELTA-ZMI-DKR-002 — Overnight deterministic completion

## Status
FROZEN_FOR_IMPLEMENTATION

## Why this delta exists

The product implementation is already pushed at commit `17ed80d4167416fc8d2aa54dae97ee2b03fc3747`.

Jenkins was upgraded successfully to 2.580.1 and responds on `127.0.0.1:8080`, but its Remote API requires authenticated access and currently returns HTTP 403. Jenkins authentication is an external owner credential concern. It MUST NOT cause the implementation worker to stop all independent work, weaken Jenkins security, inspect secrets, or consume a stronger reasoning model.

The overnight objective is therefore to finish every executable implementation/validation task without owner interaction, produce the same compact deterministic evidence locally, and leave only the authenticated Jenkins trigger as `BLOCKED_EXTERNAL:JENKINS_AUTH` when no credential is already available through an approved mechanism.

## Non-negotiable division of labor

### Heavy model / owner
Already completed:
- product analysis;
- gap/bug/tech-debt audit;
- architecture;
- Docker trust boundary;
- user story;
- implementation plan;
- acceptance criteria;
- test matrix;
- this blocker-resolution delta.

### Local worker
Implementation only.

The local worker MUST NOT:
- perform product analysis;
- redesign architecture;
- re-plan the feature;
- reinterpret acceptance criteria;
- use a strong/planning model;
- escalate model tier automatically;
- ask routine questions;
- wait for Jenkins;
- inspect full logs unless a deterministic command needs a bounded tail for evidence;
- disable Jenkins auth/CSRF;
- read/reset/create Jenkins credentials by bypassing normal owner authentication.

For coding/edit operations use only the paid economical Z.ai GLM coding route. Preferred model: `zai-coding-plan/glm-5.3-flash`. If that exact configured model is unavailable, use another already-authorized Z.ai GLM Coding Plan model; never escalate to GPT/Claude/Kimi/strong planner.

Shell, Git, Docker, pytest, Ruff, Pyright, Playwright, FFmpeg, Tesseract, Jenkins probes and summary generation are deterministic tools and require no LLM.

## Exact implementation tasks

### A. Jenkins infra consistency

Repository: `C:\Dev\OrquestadorZao`.

The running Compose image has already been changed from Jenkins 2.516.2 LTS JDK21 to 2.580.1 LTS JDK21 and the existing `ci_jenkins_home` volume survived the upgrade.

Make the persisted infra source internally consistent:
1. Change only the Jenkins base image references that still pin `2.516.2-lts-jdk21` to `2.580.1-lts-jdk21`, including `infra/ci/jenkins/Dockerfile` if that is the active derived image source.
2. Do not change plugins, auth, ports, volumes, CSRF, users or credentials.
3. Run deterministic config/build sanity appropriate to that repo.
4. If the OrquestadorZao worktree contains unrelated owner changes, do not overwrite/stash/reset them. Commit only the exact Jenkins image-pin files if selective commit is safe; otherwise leave the exact diff recorded as evidence and continue ZMI work.

### B. Add a Jenkins-independent deterministic delivery wrapper

Repository: `C:\Dev\Zo\whisper`, branch `feat/zmi-docker-runtime`.

Create `scripts/run_delivery.py`.

Purpose:
- execute the same product gates already specified by the Jenkinsfile;
- no LLM;
- continue to subsequent independent gates after a failure;
- write compact per-gate evidence using existing runners;
- invoke `scripts/summarize_gates.py` at the end;
- exit 0 only when the required local gate summary is PASS;
- never trigger Jenkins itself;
- never modify expected behavior.

Environment:
- `BUILD_NUMBER=overnight-local` by default when not supplied;
- `BUILD_ID` derived from BUILD_NUMBER;
- `ALLOW_EXTERNAL_LLM=false`;
- host E2E isolated under `artifacts/gates/build-<build>/host-e2e-data`;
- host E2E port 5500 unless explicitly overridden.

Execution order:
1. targeted:
   `python scripts/gate_runner.py targeted tests/test_gate_runner.py tests/test_summarize_gates.py tests/test_mock_data_root.py tests/test_docker_gate.py tests/test_project_override.py tests/integration/test_dashboard_process_restart.py`
2. full pytest:
   `python scripts/gate_runner.py pytest`
3. quality:
   `python scripts/gate_runner.py quality`
4. security:
   `python scripts/gate_runner.py security`
5. Docker config:
   `python scripts/docker_gate.py docker-config`
6. Docker build:
   `python scripts/docker_gate.py docker-build`
7. Docker smoke:
   `python scripts/docker_gate.py docker-smoke`
8. Docker persistence:
   `python scripts/docker_gate.py docker-persistence`
9. Docker real tiny-ASR smoke:
   `python scripts/docker_gate.py docker-asr-smoke`
10. host Playwright E2E:
    - create isolated host E2E data root;
    - copy `projects.json.example` to its `projects.json`;
    - run `docs/assets/generate_mock_data.py`;
    - run `python scripts/gate_runner.py e2e`;
    - always run mock cleanup.
11. Docker Playwright E2E:
    `python scripts/docker_gate.py docker-e2e`
12. summary:
    `python scripts/summarize_gates.py --email-status NOT_CONFIGURED`.

A gate failure does not terminate the wrapper. Record it and continue every independent later gate. Only a prerequisite failure may cause a dependent gate to be recorded SKIPPED with an exact deterministic reason.

Do not implement Sonar locally when `SONAR_HOST_URL` is absent. Preserve `NOT_CONFIGURED`; do not fake PASS.

### C. Tests for the wrapper

Add focused deterministic tests proving:
- execution order is frozen;
- failure of one independent gate does not stop later gates;
- environment forces external LLM off;
- isolated E2E data root is used;
- summary always runs;
- wrapper exit status follows summary;
- no Jenkins/network/LLM call is made by the wrapper.

### D. Overnight execution

After B/C implementation:
1. run cheap targeted tests for only the wrapper changes;
2. commit + push ZMI implementation;
3. execute `python scripts/run_delivery.py`;
4. do not use an LLM while the deterministic suite is running;
5. do not poll with an LLM; the shell process itself waits;
6. preserve `artifacts/gates/build-overnight-local/SUMMARY.json` and `SUMMARY.md`;
7. push code changes only. Test artifacts remain under the existing artifact policy unless already intended for Git.

If all local required gates PASS:
- final local state: `LOCAL_VALIDATED`.

If any gate FAILS:
- do not analyze or modify product code;
- final state: `REVIEW_REQUIRED`;
- preserve compact summary and the specific failing gate artifact/log;
- continue other independent gates first.

### E. Jenkins authentication blocker handling

After local validation, perform exactly one unauthenticated health/API probe.

If Jenkins still returns 403 for the authenticated API surface and no approved Jenkins API credential is already available through normal environment/credential tooling:
- record `JENKINS_TRIGGER=BLOCKED_EXTERNAL:JENKINS_AUTH`;
- do not disable security;
- do not inspect Jenkins secrets;
- do not create users/tokens through filesystem/script-console bypass;
- do not ask the sleeping owner;
- do not treat this as a reason to skip local deterministic validation.

Jenkins scripted clients should later use owner-created username + API token with preemptive HTTP Basic auth. API-token requests are CSRF-exempt; CSRF protection remains enabled.

## Final output

The local worker ends with only:
- ZMI commit SHA;
- OrquestadorZao Jenkins image-pin commit SHA or exact uncommitted diff status;
- local SUMMARY path;
- overall local PASS/FAIL;
- failing gate names only;
- Jenkins trigger status.

No architectural explanation, no re-plan, no long log dump, no request for routine confirmation.
