# DELTA-ZMI-DOCS-V2-006 — Heavy harness remediation

## Status
FROZEN_FOR_IMPLEMENTATION

## Review base
Documentation V2 product code remains accepted at:
`659fafd10cdd2e9d2ecfb350ff41a468de726950`

Heavy validation evidence:
- RAM 7.05 GiB => ALLOWED
- pytest FAIL: transcript_pipeline import path
- security FAIL: current-tree/private denylist issue + pip-audit unavailable
- smoke FAIL: host validation polluted by local DASHBOARD_HOST=0.0.0.0
- e2e FAIL: folders_visible / host E2E instability
- docker-build PASS
- docker-e2e FAIL: legacy watcher compose tries to pull `whisper-base`
- runner output hit a Windows cp1252 UnicodeDecodeError
- sonar/jenkins/soak NOT_CONFIGURED

This delta repairs validation infrastructure and current-tree documentation hygiene.
Do not redesign Documentation V2.

## R1 — Deterministic Python import path

Heavy `pytest` must work from a clean checkout without requiring a manually activated editable install.

Implement one authoritative solution:
- preferred: gate runner validation env prepends `<repo>/src` to `PYTHONPATH`;
- preserve any existing PYTHONPATH after it;
- nested Python subprocesses inherit it.

Add regression proving `transcript_pipeline` is importable through the gate environment.

Do not hardcode developer machine paths.

## R2 — Deterministic host validation environment

Host-side heavy gates must not inherit runtime/container binding values from the owner's shell or `scan_config.env`.

For host gates `pytest/security/smoke/e2e`, build a validation environment that explicitly sets:
- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`
- `PYTHONPATH=<repo>/src[+existing]`
- `DASHBOARD_HOST=127.0.0.1`
- `ZMI_CONTAINER_MODE=false`
- `ALLOW_EXTERNAL_LLM=false`
- `ZMI_CONFIG_ENV=<nonexistent/isolated validation env path>`

Preserve private security inputs such as `SENSITIVE_IDENTIFIERS`.

Do not modify the owner's real runtime config.

## R3 — Windows UTF-8 subprocess safety

Every gate-runner subprocess capture must specify:
- `encoding="utf-8"`
- `errors="replace"`

No gate summary may crash because child output contains characters outside cp1252.

Add a regression with non-ASCII child output.

## R4 — Security gate semantics and current-tree hygiene

### R4a current tree
Documentation/spec files committed during Documentation V2 must not contain real client identifiers.

Replace any real-client examples newly introduced by this feature with synthetic placeholders such as:
- `CONFIDENTIAL_CLIENT`
- `project-confidential`
- `ExampleCorp`

Do not print private denylist values in logs.

Run current-tree denylist check and require PASS.

### R4b history audit
The repository already documents history cleanup as an owner-only/destructive decision in `docs/GIT_HISTORY_CLEANUP.md`.

Therefore the normal `security.py` heavy gate must NOT make known historical denylist debt a blocking failure unless explicitly requested.

Behavior:
- default: history audit is logged as SKIPPED/ADVISORY with a clear reason;
- `ZMI_ENFORCE_HISTORY_CLEAN=1`: run the full-history denylist check and make it blocking.

The current-tree denylist remains blocking always.

Do not rewrite Git history.
Do not force-push.
Do not delete branches.

### R4c pip-audit
`pip-audit` is already declared in the dev extra.
The current local heavy environment is stale/missing it.

For this remediation run:
- if `python -m pip_audit --version` fails because module is absent, install only the declared tool into the current Python environment:
  `python -m pip install "pip-audit>=2.7.0"`
- do not edit dependency pins unless the declared dependency is inconsistent.

Then security must execute dependency audit normally.

## R5 — Host E2E isolation and async wait

Host E2E must not depend on real workspace media or stale files.

When `ZMI_E2E_EXTERNAL_SERVER != 1`:
1. create/use an isolated test data root under `artifacts/gates/e2e-host-data` (or temp equivalent under artifacts);
2. clear only that test-owned path through scoped safe cleanup;
3. generate synthetic dashboard fixtures with `docs/assets/generate_mock_data.py` using `ZMI_DATA_ROOT` set to the test root;
4. start dashboard with the sanitized host validation environment;
5. run Playwright against that isolated dataset.

Update `folders_visible` to WAIT for exactly four folder cards within the bounded timeout instead of checking immediately after `#filesList` appears.

Do not use real/client media.

Add regression/contract tests for the isolated data root and bounded async wait.

## R6 — Docker heavy gates must use the current Docker product harness

The gate registry currently points `docker-e2e` at legacy:
`watcher/docker-compose.yml`
whose Dockerfile depends on a local `whisper-base` image.

This is not the current ZMI Docker product.

Use the existing authoritative:
`scripts/docker_gate.py`

Registry:
- docker-build => `python scripts/docker_gate.py docker-build`
- docker-e2e => `python scripts/docker_gate.py docker-e2e`

Do not invoke watcher/docker-compose.yml from the Project Lead heavy gate.

Add tests proving registry commands use docker_gate.py and never the legacy watcher compose.

## R7 — Heavy runner reporting

Preserve current rule:
- NOT_CONFIGURED != PASS.

Additionally include explicit:
- `required_core_gates`
- `configured_failures`
- `not_configured`

in `heavy-validation.json` if practical without redesign.

Core gates for this product:
- pytest
- security
- smoke
- e2e

Docker configured gates also must pass before deploy.
Sonar/Jenkins/soak may remain NOT_CONFIGURED.

## Fast remediation validation

Before re-running heavy, run ONLY:
- tests for gate_runner env/UTF-8/registry;
- security harness tests;
- E2E harness contract/unit tests;
- docker gate unit tests;
- smoke directly once under sanitized env;
- pytest import smoke;
- Ruff changed scripts/tests;
- compileall/typecheck.

Do not run real media.
Do not run Live Capture.
Do not create worktrees.

## Heavy retry strategy

After fast remediation is green:
1. run ONLY previously failed gates individually:
   - pytest
   - security
   - smoke
   - e2e
   - docker-e2e
2. if any fails, STOP and return compact evidence; do not run full heavy.
3. if all five pass, run `python scripts/heavy_validation_runner.py` ONCE for final authoritative summary.
4. do not run configured gates repeatedly in loops.

## No destructive history cleanup
A full git-filter-repo/history rewrite is explicitly outside this delta and requires owner approval.
