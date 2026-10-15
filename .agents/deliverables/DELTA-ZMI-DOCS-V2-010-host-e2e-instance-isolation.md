# DELTA-ZMI-DOCS-V2-010 — Host E2E instance isolation

## Status
FROZEN_FOR_IMPLEMENTATION

## Review base
Current branch head:
`1a9026808bcb3053455b69701822f1fd5be3f791`

Current heavy retry status:
- pytest PASS
- security PASS
- smoke PASS
- e2e FAIL
- docker-e2e NOT_RUN

Observed host E2E failure referenced a real workspace file (`gravity_ai_medical.mp4`) even though host E2E is supposed to use synthetic data under `artifacts/gates/e2e-host-data`.

This is a harness isolation defect, not a Documentation V2 product failure.

## E1 — Force host E2E mode

`gate_runner.validation_environment("e2e", ...)` must explicitly set:
`ZMI_E2E_EXTERNAL_SERVER=0`

Do not preserve an inherited value of 1 for the host e2e gate.

Docker E2E remains separate and explicitly sets `ZMI_E2E_EXTERNAL_SERVER=1` inside `scripts/docker_gate.py`.

Add regression:
- base env with `ZMI_E2E_EXTERNAL_SERVER=1`
- host gate env returns 0
- isolated ZMI_DATA_ROOT/ZMI_TEST_DATA_ROOT are present.

## E2 — Dedicated host E2E port

For non-external mode, `scripts/e2e.py` must not target the normal dashboard default port 5000.

At runtime:
1. choose an available loopback port dynamically (bind 127.0.0.1:0, read assigned port, close immediately);
2. set child env `DASHBOARD_HOST=127.0.0.1`;
3. set child env `DASHBOARD_PORT=<chosen>`;
4. set child/test env `ZMI_BASE_URL=http://127.0.0.1:<chosen>`;
5. use that URL for readiness and smoke test.

External-server mode continues to honor supplied `ZMI_BASE_URL`.

Do not kill or interfere with a real dashboard already running on port 5000.

## E3 — Prove spawned-server ownership

Host readiness must fail if the spawned dashboard process exits before readiness.

`_wait_for_server` (or equivalent) receives the child process and:
- checks `process.poll()` while waiting;
- if child exits, return a typed startup failure and include bounded child output;
- never treat an unrelated already-running dashboard as the successful child.

After readiness, verify child is still alive before launching Playwright.

## E4 — Synthetic-data preflight

Before Playwright host smoke begins, verify the isolated server does not expose known real-workspace data.

Implement a deterministic preflight against `/api/files` in host mode:
- fixture generation knows the expected mock media filenames;
- returned media filenames must be a subset of the expected synthetic fixture names plus only E2E-created disposable names;
- if an unexpected filename appears, fail immediately with check `host_e2e_data_isolation`;
- never print absolute local paths;
- do not continue browser mutations against an unexpected server.

Prefer exposing a small helper/constant from `docs/assets/generate_mock_data.py` or a generated fixture manifest rather than duplicating a long list in multiple modules.

## E5 — Browser close safety

The current TargetClosedError is likely downstream from hitting the wrong server, but make smoke cleanup robust:
- browser/page cleanup occurs in finally;
- a failed check should be recorded before cleanup;
- no unhandled TargetClosedError should erase the primary check/error signature.

Do not hide genuine Playwright failures.

## Tests
Add targeted deterministic tests:
1. host e2e overrides inherited EXTERNAL_SERVER=1 to 0;
2. host e2e chooses a non-5000 dynamic loopback port;
3. external mode still honors provided base URL;
4. exited child cannot satisfy readiness;
5. host synthetic preflight accepts expected fixture names;
6. host synthetic preflight rejects an unexpected filename without leaking absolute paths;
7. real port-5000 server is never contacted in host mode.

## Retry
After targeted tests/Ruff/compile:
1. run gate_runner e2e only.
2. If PASS, run docker-e2e.
3. If both PASS, run actual RAM gate and one final heavy_validation_runner run.
4. Stop on first failure. No automatic repair loop.

## No product work
Do not alter Documentation V2 semantics.
Do not resume Live Capture.
Do not process real media.
Do not merge/deploy.
