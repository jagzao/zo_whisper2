# DELTA-ZMI-DOCS-V2-008 — TLS-safe locked dependency audit

## Status
FROZEN_FOR_IMPLEMENTATION

## Review base
Current branch:
`285944e8d13870bf8de2b254a11d7ca56625582b`

DELTA-007 succeeded in creating a reproducible validation environment and all required imports pass.

Remaining blocker:
- runtime/dev lock audits cannot complete because pip-audit HTTPS certificate verification to the vulnerability/index service fails.
- vulnerability status is therefore UNKNOWN.

This is a validation transport problem, not evidence of a Documentation V2 product failure.

## Security principle
Do NOT disable TLS verification.

Forbidden:
- `--trusted-host`
- `verify=False`
- disabling certificate verification globally
- replacing HTTPS with HTTP
- permanently mutating owner/global certificate settings

Prefer the operating-system trust store.

## T1 — Diagnose trust without mutating global config

Using:
`.venv-validation\Scripts\python.exe`

Run a deterministic TLS probe that:
1. imports `truststore`;
2. calls `truststore.inject_into_ssl()`;
3. performs a bounded HTTPS request to the PyPI JSON endpoint;
4. reports status without logging certificate/private proxy secrets.

Also record only whether these env vars are SET/UNSET, never their values:
- PIP_CERT
- REQUESTS_CA_BUNDLE
- CURL_CA_BUNDLE
- SSL_CERT_FILE
- HTTPS_PROXY

If the system-trust probe fails:
- return `TLS_SYSTEM_TRUST_UNAVAILABLE`;
- do not disable verification;
- stop before vulnerability acceptance.

## T2 — Audit fully pinned locks without dependency resolution

Both project lockfiles are fully pinned.

Add a small authoritative wrapper:
`scripts/pip_audit_locked.py`

Behavior:
1. inject system trust with `truststore.inject_into_ssl()`;
2. invoke pip-audit's normal module CLI in-process/through its public CLI entry path;
3. force:
   - `--no-deps`
   - `--disable-pip`
   - `--progress-spinner off`
   - `--format json`
   - `-r <lockfile>`
4. no package installation/resolution;
5. preserve pip-audit exit semantics;
6. UTF-8 deterministic output.

Do not use private pip-audit internals when the module CLI entrypoint can be used.

Rationale:
the lock already contains exact transitive pins, so the audit should not resolve dependencies from an index merely to learn versions we already froze.

## T3 — Vulnerability service policy

Primary service:
`pypi`

If and only if the primary audit fails due a transport/service failure rather than a vulnerability result, allow ONE deterministic fallback:
`--vulnerability-service osv`

Record:
- service_used
- transport_fallback=true/false

A successful OSV audit is acceptable because pip-audit officially supports OSV as a vulnerability service.

If both services fail:
- vulnerability status remains UNKNOWN;
- security gate FAIL;
- no bypass.

Do not retry in a loop.

## T4 — Security harness integration

`scripts/security.py` must call `scripts/pip_audit_locked.py` for:
- requirements.runtime.lock.txt
- requirements.lock.txt

Persist machine evidence:
- artifacts/gates/security/runtime-audit.json
- artifacts/gates/security/dev-audit.json

For each audit distinguish:
- CLEAN
- VULNERABLE
- TRANSPORT_ERROR
- INVALID_REPORT

Only CLEAN passes.

VULNERABLE reports exact:
- package
- pinned version
- advisory id
- fix versions

TRANSPORT_ERROR never means zero vulnerabilities.

## T5 — Tests

Add deterministic tests:
1. system-trust injection occurs before audit CLI;
2. no `--trusted-host` or TLS-disable path exists;
3. wrapper passes `--no-deps --disable-pip`;
4. PyPI clean => CLEAN;
5. PyPI vulnerability => VULNERABLE, no fallback;
6. PyPI transport fail + OSV clean => CLEAN + fallback recorded;
7. PyPI transport fail + OSV fail => TRANSPORT_ERROR;
8. malformed JSON => INVALID_REPORT;
9. security harness preserves vulnerability metadata;
10. no secret/proxy/certificate values printed.

## T6 — Retry policy

After targeted tests are green:
1. run runtime lock audit;
2. run dev lock audit.

If either is VULNERABLE:
- STOP;
- report advisories/fixed versions;
- do not auto-upgrade.

If either is TRANSPORT_ERROR/INVALID_REPORT:
- STOP;
- report compact transport evidence;
- do not bypass TLS.

Only if both are CLEAN:
- ensure Playwright Chromium;
- retry pytest;
- security;
- smoke;
- e2e;
- docker-e2e.

Stop on first failed gate and return evidence.

If all pass:
- RAM gate;
- one final heavy validation run.

## No product feature work
Do not modify Documentation V2 behavior.
Do not resume Live Capture.
Do not process real media.
Do not merge/deploy.
