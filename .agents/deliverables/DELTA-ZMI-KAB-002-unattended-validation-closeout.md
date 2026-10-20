# DELTA-ZMI-KAB-002 — Unattended validation closure

STATUS: FROZEN_FOR_IMPLEMENTATION
OWNER/HEAVY-MODEL ANALYSIS: COMPLETE
WORKER: IMPLEMENTATION ONLY — ECONOMICAL Z.AI GLM CODER
SOURCE BRANCH: `feat/kab-local-ingest-v1`
SOURCE HEAD AT FREEZE: `6b9adf1f0f869b0715cab4d2cf0d1164c545b96a`

## Mission / reality check

The K'ab local receiver/worker/features were implemented and pushed; the previous worker reported PASS for TLS, authentication, resumable chunks, checksums, READY handoff, media pairing, incremental processing, transcript consolidation, manual and AI package.

Zo Media Intelligence **base Docker service** is reported running at `http://127.0.0.1:5000` and must remain running and localhost-only.

The last general validation report:
- full pytest: `562 passed, 6 failed, 1 error`;
- K'ab targeted: `117 passed`;
- K'ab offline synthetic E2E: PASS;
- integrated `scripts/e2e.py`: FAIL;
- Ruff/Pyright: NOT_RUN (unavailable in the previous execution environment);
- security 5/6, `dependency_audit` unavailable offline;
- earlier owner report mentions missing `markitdown`, `pytesseract`, a Jenkinsfile check, and an E2E fixture/port issue.

These are *reported symptoms*, not confirmed root causes: the actual failing test names and trace must be read from targeted artifacts before any narrow mechanical change. Do not invent a root cause.

The job is to complete every feasible deterministic validation task unattended without weakening security or changing frozen product behavior. It is NOT authorized to guarantee green if a required external dependency is unavailable.

## Decisions frozen by heavy-model analysis

### D1. Runtime / Git isolation

- Leave running `zmi` production container and its `/data` and `/cache` volumes untouched.
- Do not run `docker compose down`, prune images/volumes, delete real media, or kill the existing `127.0.0.1:5000` service.
- Work ONLY in `C:\Dev\Zo\whisper-kab-ingest` on `feat/kab-local-ingest-v1`.
- Use `git fetch origin`, verify local branch/upstream and clean status. Preserve unrelated owner work. Never reset, stash, force-push, merge, delete other worktrees, or switch the main `C:\Dev\Zo\whisper` worktree.
- If the worktree is not clean, do not overwrite unrelated changes; commit only strictly relevant changes where safe.
- The `KAB_INGEST_ENABLED=false` default is unchanged: do NOT turn on a LAN listener or generate production TLS secrets unattended.

### D2. Dependency/environment repair before rerunning full tests

The previous full suite used a Python environment missing required extras. Fix the test environment — not the tests.

1. Detect a supported Python installation; prefer 3.12 for wheel compatibility.
2. Create/reuse a **dedicated isolated development venv** for this K'ab worktree outside tracked paths (e.g. `.venv-kab` if gitignored).
3. Install the repository's declared dev extras into that venv with the existing dependency metadata: `python -m pip install -e ".[dev]"`. This includes `vision` (`pytesseract`), `documents` (`markitdown==0.0.2`), `pdf` (`reportlab`), plus pytest, playwright, ruff, pyright and pip-audit.
4. If outbound package downloads are unavailable, use existing wheel cache or the repo's Docker test image with pinned dependencies; **do not downgrade test expectations or commit arbitrary binary packages**. Do not change public dependency declarations just to force an installation.
5. Verify imports of `markitdown`, `pytesseract`, `reportlab`, `pytest`, `ruff`, `pyright`, `pip_audit` in the exact interpreter used for tests. If still unavailable, record `ENV_DEPENDENCY_UNAVAILABLE` with package names.
6. Verify FFmpeg/ffprobe and Chromium availability for E2E; use deterministic Playwright browser install if allowed. Do not claim browser checks PASS without executing them.

Only after this environment bootstrap, rerun failing tests and full validation ONCE on the consistent environment. Avoid repeated full-suite loops.

### D3. Existing pytest failures

- Collect exact test IDs + compact failure signatures from current pytest output to a local file under `artifacts/kab-closeout/`.
- Re-run only each affected test or module for confirmation (no more than 2 attempts per mechanical fix).
- If a failure is caused by missing optional test dependencies now present, no source change is needed.
- If an infrastructure/fixture check looks for `Jenkinsfile`, validate against the worktree repo root; `Jenkinsfile` already exists on the source branch. Correct a wrong working directory/path in test harness if that is exactly the cause; do not add a fake Jenkinsfile or alter expectations.
- If a test is directly broken by a simple typo/import/lint/new K'ab integration mismatch with clear existing expected behavior, a narrow mechanical code correction is allowed with a targeted regression check.
- If a failure requires deciding expected product behavior, changing the security boundary, rearchitecting, or weakening an assertion, record the exact test as `REVIEW_REQUIRED` and continue all independent work. No LLM analysis to invent behavior.

### D4. Integrated host E2E

- The dashboard at `127.0.0.1:5000` is the **production runtime**. Never bind the host E2E to that port, reuse production `DATA_ROOT`, or terminate that container.
- Host E2E uses `127.0.0.1:5500` with `ZMI_DATA_ROOT` and `ZMI_TEST_DATA_ROOT` both pointing to an **isolated generated synthetic data root**, never the repo's real `Videos/`, `audio/`, or production `zmi-data`.
- For direct isolated host E2E: seed `projects.json` from `projects.json.example`; run `docs/assets/generate_mock_data.py`; then `scripts/e2e.py` with the same venv; clean only the synthetic data on exit.
- Test fixtures must satisfy the existing UI E2E contract including a synthetic transcription exceeding 100 characters, project matches and tutorial evidence. Do not relax test assertions because a fixture is incomplete.
- Fix only an observed fixture-path/config/execution error mechanically; preserve dashboard Host/Origin security.
- If port 5500 is occupied, choose another unused loopback-only port through environment variables. Never change production binding.

### D5. Docker CI gates (never touch production Compose project)

Use existing `scripts/docker_gate.py` with its isolated `zmi-test-*` Compose projects. These gates may clean up **only their own test-scoped** resources.

Run sequentially:
```
docker-config
docker-build
docker-smoke
docker-persistence
docker-asr-smoke
docker-e2e
```

Do not rerun image build unnecessarily if it is already cached; do not fabricate PASS when offline model download fails. Preserve downloaded tiny Whisper model cache in the test scope as allowed.

### D6. Security / pip-audit

- `scripts/security.py` performs six checks; five passed and `dependency_audit` could not run offline in prior execution.
- Install `pip-audit` in the dedicated venv if available, then invoke the actual security gate.
- The tool's vulnerability DB/network may be unavailable. Such an outcome is `BLOCKED_EXTERNAL:ADVISORY_NETWORK`, not PASS.
- Do not suppress/skip `pip-audit`, change code to return 0 when it could not audit, or disable secret scanning.
- A real discovered CVE is a real FAIL requiring heavy-model review if resolution would modify version pins or behavior.

### D7. Quality gates

Run Ruff + Pyright with the exact isolated venv and existing `scripts/quality.py`.

- Fix only explicit formatting/import/unused-variable errors introduced by current K'ab edits; no broad formatting churn.
- Do not alter Pyright config/suppress errors to hide failures.
- If dependencies/tooling cannot be installed, record the exact blocker `ENV_TOOL_UNAVAILABLE` not PASS.

### D8. Jenkins

- Jenkins is already upgraded and serving localhost, but API trigger returns HTTP 403 without owner-approved credentials.
- Perform at most one authenticated-availability probe using **only an already-authorized, normally supplied credential**; otherwise record `BLOCKED_EXTERNAL:JENKINS_AUTH`.
- Never try filesystem/script-console credential extraction, token generation bypass, disable CSRF/authentication, or prompt the owner overnight.
- Jenkins trigger availability MUST NOT block local deterministic gates.
- The security/functional state remains incomplete until the required remote validation is executed; do not claim Jenkins PASS.

### D9. Unattended workflow / bounded mechanical corrections

Allowed local actions:
- install pinned/declaration-consistent dependencies and browser;
- create isolated test data;
- fix deterministic runner paths;
- fix obvious mechanical errors in code introduced by this branch (e.g. import, typo, incorrect relative fixture path);
- run bounded targeted checks;
- commit and push only the permitted repair changes.

Forbidden:
- product analysis, new designs, changing behavior, choosing alternative transport/storage;
- expensive or planning-model escalation; spawning subagents;
- changing tests to obtain PASS;
- modifying security boundaries, exposing K'ab/dashboard to LAN, or uploading private media;
- merging or deploying Android client;
- indefinite fix-test cycles;
- network calls from the K'ab *offline* test suite (loopback only).

Cap mechanical retries to **two per distinct failure signature**. If still failing, record `REVIEW_REQUIRED`, continue independent checks, and complete the report. A no-op/check-only task consumes zero LLM tokens once started.

### D10. Completion/evidence (must happen even on failure)

Keep one immutable evidence folder `artifacts/kab-closeout/<run-id>/` containing:
- `SUMMARY.json`;
- `SUMMARY.md`;
- `pytest.json` or test-id list/counts;
- `quality.json`;
- `security.json`;
- `host-e2e.json`;
- `docker-gates.json`;
- `blockers.json`;
- bounded logs/trace excerpts separately.

Reports must derive from real command exit codes. Never replace FAIL or SKIPPED with PASS.

Final status:
- `READY_FOR_OWNER_REVIEW` only if all locally runnable required gates are genuinely green;
- `REVIEW_REQUIRED` if any real test/code gate fails;
- `BLOCKED_EXTERNAL` if only required external checks remain unavailable.

Commit and push work to `origin/feat/kab-local-ingest-v1`. No merge. Keep production Docker service running. Once all independent tasks/evidence are exhausted, **EXIT WITHOUT ASKING THE OWNER**.

Output only:
```
BRANCH=feat/kab-local-ingest-v1
HEAD=<actual SHA>
BASE_RUNTIME=<PASS|FAIL>
KAB_TARGETED=<pass/fail counts>
FULL_PYTEST=<pass/fail/error counts>
QUALITY=<PASS|FAIL|BLOCKED_EXTERNAL>
SECURITY=<PASS|FAIL|BLOCKED_EXTERNAL>
HOST_E2E=<PASS|FAIL|BLOCKED_EXTERNAL>
DOCKER_GATES=<PASS|FAIL|BLOCKED_EXTERNAL>
JENKINS=<TRIGGERED|BLOCKED_EXTERNAL:JENKINS_AUTH>
STATUS=<READY_FOR_OWNER_REVIEW|REVIEW_REQUIRED|BLOCKED_EXTERNAL>
SUMMARY=<absolute path>
BLOCKERS=<short IDs only>
```

This execution explicitly DOES NOT implement `KAB_ANDROID_SENDER_SPEC`. That is a separate future, unapproved Android code change. A full green closeout here only means the local receiver/worker implementation is ready for review.
