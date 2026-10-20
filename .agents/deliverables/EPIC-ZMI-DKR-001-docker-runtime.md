# EPIC-ZMI-DKR-001 — Docker Runtime

## Goal

Run Zo Media Intelligence reproducibly in a secure, CPU-first Docker container without changing its local-first single-user product model.

Source audit: `.agents/deliverables/AUDIT-ZMI-DKR-001-docker-readiness.md`.

## Definition of complete

```
portable runtime paths
+ production Docker image
+ secure Compose contract
+ persistent media/state/model cache
+ deterministic container tests
+ compact Jenkins evidence
= READY_FOR_DOCKER_OWNER_AUDIT
```

## Features

1. **FEATURE-ZMI-DKR-001 — Portable runtime filesystem**
   Separate immutable code from mutable data/log/config/cache while preserving non-Docker compatibility.

2. **FEATURE-ZMI-DKR-002 — Secure CPU container runtime**
   Dockerfile, Compose, initialization, localhost-only publishing, system media/OCR dependencies, healthcheck and non-root runtime.

3. **FEATURE-ZMI-DKR-003 — Container behavioral validation**
   Deterministic build, smoke, persistence, restart, real tiny-model ASR and Playwright/E2E validation.

4. **FEATURE-ZMI-DKR-004 — Low-token delivery evidence**
   Complete Jenkins matrix, per-gate compact JSON, aggregate summary and one final notification.

## Constraints

- Base from `feat/zmi-final-completion`; do not merge abandoned experimental Docker stacks.
- `watcher/` and `deepseek/` stay excluded from production image/build context.
- No GPU image in this epic.
- No remote/internet-facing dashboard mode.
- No model weights embedded in image.
- No secrets embedded in image, Compose, Dockerfile or committed env files.
- Existing host execution must keep working when Docker env vars are absent.
- Local coder implements frozen scope only; it does not redesign requirements.

## Terminal state

`READY_FOR_OWNER_AUDIT`.
