# LOCAL-CODER-ZMI-LIFECYCLE-001

## Status
`FROZEN_FOR_IMPLEMENTATION`

## Role

Implementation worker only. Follow the frozen US, plan, test matrix and repository protocols. Do not re-analyze product scope or change contracts.

## Source of truth

- `.agents/deliverables/AUDIT-ZMI-LIFECYCLE-001-recording-storage-docs.md`
- `.agents/deliverables/EPIC-ZMI-LIFECYCLE-001-recording-to-knowledge.md`
- `.agents/deliverables/FEATURE-ZMI-LIFECYCLE-001-safe-media-and-docs.md`
- `.agents/deliverables/US-ZMI-LIFECYCLE-001-recording-storage-docs.md`
- `.agents/deliverables/PLAN-ZMI-LIFECYCLE-001-recording-storage-docs.md`
- `.agents/deliverables/TEST-MATRIX-ZMI-LIFECYCLE-001.md`
- `.agents/protocols/project-lead.md`, `model-routing.md`, `deterministic-gates.md`, `delivery-loop.md`
- Canonical W40/W41-W45 history in `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md`

## Model and workspace

- Use configured `PRIMARY_CODER` (OpenCode Go); DeepSeek configured fallback only for provider invocation/auth/quota/unavailability, through `scripts/model_router.py`.
- Codex/ChatGPT owns analysis, review and heavy-gate interpretation. Never invoke premium models or nested agents from the coder loop.
- Stay on the approved current branch. No worktree. Preserve all pre-existing owner edits; never reset/stash/clean. Stage explicit implementation files only.
- Do not commit secrets, runtime state, real media, transcripts or client evidence.

## Required order

Execute PLAN WP-01 through WP-07. One bounded work package at a time. After each, update `.agents/session/` using repository checkpoint tooling. Local implementation gates only: targeted tests, configured lint/quality/typecheck, and synthetic FFmpeg/ffprobe validation. Maximum two repair attempts per identical failure signature.

Stop after commit/push at `READY_FOR_CHATGPT_REVIEW`. Do not run heavy gates or deploy before ChatGPT review. After review, follow WP-08 RAM/heavy gate order. Production deployment is explicitly authorized only under WP-09 after all gates pass, from final pushed SHA, to current desktop+LAN Whisper services, with backup/rollback and non-destructive data handling. Never deploy on a failing/deferred gate.

## Start prompt

```text
Project-lead: ejecuta US-ZMI-LIFECYCLE-001 completa siguiendo Project-lead V5 y PLAN-ZMI-LIFECYCLE-001. Usa PRIMARY_CODER económico (OpenCode Go; DeepSeek configurado solo como fallback), conserva este workspace sin worktree y todos los cambios preexistentes. Completa WP-01–WP-07 y termina en READY_FOR_CHATGPT_REVIEW. No ejecutes gates pesados ni despliegues antes de /review. Tras review aprobada, continúa WP-08–WP-09; despliega a producción únicamente si todos los gates y backup/rollback pasan. Usa datos sintéticos para pruebas; no borres medios reales. Persiste checkpoint y evidencia tras cada paquete.
```

## Stop conditions

- Frozen contract contradiction -> `SPEC_CONFLICT` with exact evidence.
- Premise contradicted by deterministic evidence or identical failure after two repair attempts -> `REVIEW_REQUIRED` with compact signature/artifact.
- Genuine external credential/account/infrastructure blocker -> `BLOCKED_EXTERNAL:<reason>`.
- Do not ask the owner to choose next steps that the US/plan/gates determine.

## Required final handoff

```text
BRANCH=
HEAD=
REMOTE_HEAD=
STATUS=<READY_FOR_CHATGPT_REVIEW|REVIEW_REQUIRED|BLOCKED_EXTERNAL>
TARGETED=
QUALITY=
TYPECHECK=
MEDIA_INTEGRITY=
HEAVY_VALIDATION=<NOT_RUN_PENDING_REVIEW|PASS|FAIL|DEFERRED_LOW_RAM>
PRODUCTION_DEPLOY=<NOT_RUN_PENDING_REVIEW|PASS|FAIL>
DESKTOP_LAN_PARITY=
MOBILE_PLAYWRIGHT=
REAL_MEDIA_MODIFIED=NO
WORKTREE_STATUS=
BLOCKERS=<none|typed ids>
```
