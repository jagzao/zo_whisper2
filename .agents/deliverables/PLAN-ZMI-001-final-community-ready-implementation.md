# PLAN-ZMI-001 — Final Community-Ready Implementation

## Source

- AUDIT-ZMI-001
- EPIC-ZMI-001
- US-ZMI-001

This plan is implementation detail only; it cannot redefine the frozen US.

## Work packages

### WP-01 — Clean V4 delivery engine
- Port reviewed V4 protocols from the experimental branch without unsafe history.
- Compact gate runner + tests.
- Provider aliases.
- Project-level OpenCode interruption enforcement.
- Crash-resume evidence/rules.

Evidence: tooling/config tests + gate-runner tests.

### WP-02 — Product persistence integrity
- Atomic Edit File transaction.
- Atomic Project rename/delete + override migration.
- Safe media-delete override cleanup.
- Failure injection / rollback tests.

Evidence: `tests/test_project_override.py`.

### WP-03 — Recovery acceptance
- Real dashboard child-process start/stop/start integration smoke.
- Ensure processes terminate and fresh run-state is reported.

Evidence: `tests/integration/test_dashboard_process_restart.py`.

### WP-04 — Deterministic CI toolchain
- Jenkinsfile.
- SonarQube properties.
- Public GitHub PR CI.
- Gitleaks workflow.
- Fresh-install acceptance script.
- Compact artifacts.

Evidence: config tests + remote PR checks + local/Jenkins evidence where available.

### WP-05 — Community surface
- Code of Conduct.
- Bug/feature issue forms.
- PR template.
- README/SECURITY/CONTRIBUTING/LOCAL-OPS truth alignment.
- Post-acceptance community-launch checklist.

### WP-06 — Closure
- full pytest;
- quality;
- security;
- smoke;
- E2E;
- fresh-install;
- private denylist current tree/history on maintainer machine;
- review PR diff;
- fill DELIVERY;
- stop at READY_FOR_OWNER_AUDIT.

## Rollback

All work is isolated on `feat/zmi-final-completion`. No repository rename/tag/release or main merge occurs before owner acceptance.
