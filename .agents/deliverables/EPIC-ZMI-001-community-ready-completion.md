# EPIC-ZMI-001 — Community-Ready Completion

## Goal

Finish **Zo Media Intelligence** as a trustworthy first open-source/community project that can be shared publicly, cloned by another developer, validated deterministically, and used locally with minimal maintainer intervention.

Source audit: `.agents/deliverables/AUDIT-ZMI-001-current-state.md`.

## Definition of complete

```
clean repository
+ product integrity
+ deterministic delivery/tooling
+ truthful public CI/docs
+ contributor surface
+ fresh-install proof
+ final owner acceptance
= READY_FOR_COMMUNITY_LAUNCH
```

## Features

1. **FEATURE-ZMI-001 — Autonomous deterministic delivery**
   Project-lead V4, model routing, gate runner, Jenkins, SonarQube and runtime owner-interruption enforcement.

2. **FEATURE-ZMI-002 — Product integrity and recovery**
   Atomic Edit File / Project CRUD state transitions plus real process restart smoke.

3. **FEATURE-ZMI-003 — Community and public CI readiness**
   Lightweight PR CI, security scan, community templates, truthful docs and release checklist.

4. **FEATURE-ZMI-004 — Fresh-install acceptance**
   Reproducible clean install and synthetic end-to-end smoke instructions/evidence.

## Execution constraints

- Work from a clean branch based on `main`; do not merge PR #23 history.
- Never commit private identifiers, owner runtime state, real media or real transcripts.
- `.agents/session/`, `.agents/memory/`, `artifacts/` remain gitignored.
- No Electron dependency for this web product.
- No product-scope expansion unrelated to the audit.
- No automatic repository rename/tag/release before final owner acceptance.

## Release gates

- targeted regression tests;
- full pytest suite;
- Ruff + Pyright;
- security + dependency audit + Gitleaks;
- smoke;
- Playwright E2E;
- clean-install smoke;
- SonarQube when configured;
- Jenkins pipeline definition validation / local run when Jenkins exists;
- GitHub PR checks after push.

## Terminal state

`READY_FOR_OWNER_AUDIT` -> assistant audit -> `READY_FOR_HUMAN_ACCEPTANCE` -> owner local test -> `READY_FOR_COMMUNITY_LAUNCH`.
