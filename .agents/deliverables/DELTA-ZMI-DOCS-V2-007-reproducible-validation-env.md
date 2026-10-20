# DELTA-ZMI-DOCS-V2-007 — Reproducible validation environment and lockfile audit

## Status
FROZEN_FOR_IMPLEMENTATION

## Review base
Current branch implementation:
`889e53c464f22ff96ba95b4f51f334f801d9785d`

Documentation V2 product logic remains accepted. This delta addresses only validation reproducibility.

Observed after DELTA-006:
- R1-R7 PASS.
- retry pytest stops at collection because `markitdown` is missing.
- `markitdown==0.0.2` is already pinned in `requirements.lock.txt`.
- pip-audit reports many vulnerabilities from the currently installed Python environment.
- therefore the current host environment is not a trustworthy representation of the project's locked validation environment.

## V1 — Dedicated validation venv

Create one project-local ignored validation environment:
`.venv-validation`

Do not create a worktree.

Add `.venv-validation/` to .gitignore if not already covered by a generic venv rule.

Add deterministic helper:
`scripts/validation_env.py`

Required commands:
- `python scripts/validation_env.py ensure`
- `python scripts/validation_env.py python`
- optional `python scripts/validation_env.py status`

Behavior:
1. determine current base Python major.minor;
2. compute fingerprint from:
   - requirements.lock.txt bytes;
   - Python major.minor;
3. if no env or fingerprint mismatch:
   - create with `python -m venv .venv-validation`;
   - install/upgrade pip only as required by the lock;
   - install exactly `-r requirements.lock.txt`;
   - write fingerprint stamp atomically;
4. if fingerprint matches, do not reinstall;
5. emit compact status only.

No global/system package installation.

No conda assumptions.

On Windows validation Python:
`.venv-validation/Scripts/python.exe`

On POSIX:
`.venv-validation/bin/python`

## V2 — Gate execution under validation Python

Heavy host gates must run under the validation interpreter.

Preferred implementation:
- heavy_validation_runner resolves/ensures validation env once before heavy host gates;
- invokes gate_runner using validation Python;
- because gate_runner's `sys.executable` is then validation Python, pytest/security/smoke/e2e and nested Python commands use the same locked environment.

Do not recursively create another venv when already running from validation Python.

Docker gates continue using Docker harness and do not require host dependency installation beyond Docker CLI.

## V3 — Project dependency audit, not ambient-environment audit

Change `scripts/security.py::check_dependency_audit` so the authoritative dependency audit is based on project lockfiles.

Blocking production audit:
`python -m pip_audit -r requirements.runtime.lock.txt`

Development/full-validation audit:
`python -m pip_audit -r requirements.lock.txt`

Rules:
- runtime lock vulnerabilities => BLOCKING security FAIL;
- full/dev lock vulnerabilities => BLOCKING for heavy validation because test/document tooling is shipped to contributors/CI, but report separately from runtime;
- ambient unrelated packages must not affect project security result;
- write/retain machine-readable audit evidence under `artifacts/gates/security/` if practical;
- do not silently ignore vulnerabilities.

If either project lockfile reports vulnerabilities:
- do NOT auto-upgrade packages broadly;
- return exact package/version/advisory/fixed-version metadata;
- STATUS=REVIEW_REQUIRED for owner/ChatGPT dependency remediation.

This makes the existing “39 vulnerabilities across 8 installed packages” result diagnostic only until reproduced against the lockfiles.

## V4 — MarkItDown collection contract

After validation env ensure:
- `import markitdown` must succeed;
- `import openpyxl` must succeed;
- `import pptx` must succeed;
- `import pytest` must succeed.

Add a small validation-env dependency smoke.

Do not skip `tests/test_markitdown_documents.py` because the dependency belongs to the locked dev environment.

## V5 — Playwright browser availability

The validation env contains the Python Playwright package, but browser binaries are external artifacts.

Before host E2E:
- test whether the required Chromium executable is available for the installed Playwright;
- if absent, run exactly once:
  `<validation-python> -m playwright install chromium`
- do not use `--with-deps` on Windows;
- do not reinstall when already available.

Persist a browser-ready stamp keyed to Playwright version if helpful.

## V6 — Fast validation before heavy

Run with validation Python:
- dependency smoke;
- targeted validation_env tests;
- targeted gate_runner/security tests;
- `tests/test_markitdown_documents.py`;
- smoke.

Then run lock audits.

Decision:
A. lock audits CLEAN => continue failed-gate retries.
B. runtime/dev lock vulnerability found => STOP and report exact advisories; do not run further heavy gates until dependency remediation is reviewed.

## V7 — Retry sequence after clean lock audit

Using validation Python:

1. gate_runner pytest
2. gate_runner security
3. gate_runner smoke
4. gate_runner e2e
5. gate_runner docker-e2e

If any fails:
- stop after the current failed gate;
- report compact evidence;
- no automatic code repair loop.

If all pass:
- RAM gate with actual physical RAM;
- one final heavy_validation_runner run under validation Python.

## No product work
Do not modify Documentation V2 product behavior.
Do not resume Live Capture.
Do not process real media.
Do not rewrite history.
Do not merge/deploy.

## Acceptance
- validation environment derived from requirements.lock.txt;
- no global pip mutation;
- MarkItDown tests collect/run;
- security audit tied to project locks;
- ambient Python vulnerabilities cannot create false project failures;
- true lockfile vulnerabilities are reported and remain blocking;
- failed-gate retry and final heavy use same validation interpreter.
