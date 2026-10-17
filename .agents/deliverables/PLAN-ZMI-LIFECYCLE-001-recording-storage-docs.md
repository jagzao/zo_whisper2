# PLAN-ZMI-LIFECYCLE-001 — Recording, optimized storage and documentation

## Status
`FROZEN_FOR_IMPLEMENTATION`

## Source

- `AUDIT-ZMI-LIFECYCLE-001-recording-storage-docs.md`
- `EPIC-ZMI-LIFECYCLE-001-recording-to-knowledge.md`
- `FEATURE-ZMI-LIFECYCLE-001-safe-media-and-docs.md`
- `US-ZMI-LIFECYCLE-001-recording-storage-docs.md`
- `TEST-MATRIX-ZMI-LIFECYCLE-001.md`
- Canonical runtime history: `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md` (W40 evidence, W41-W45 scope)

## Execution rules

- No worktree; continue on the approved current branch. Preserve the owner’s plan edits and never reset/stash/clean them. Commit only the coherent implementation artifacts/code after review of the diff.
- OpenCode Go is PRIMARY_CODER; DeepSeek is fallback only when the configured provider is unavailable/auth/quota/invocation failure, via runtime aliases. Codex/ChatGPT performs heavy analysis/review; do not call premium models from the coding loop.
- Synthetic/isolated data for tests. Never test destructive cleanup against user originals.
- Local coder runs implementation gates only. Commit/push, stop at `READY_FOR_CHATGPT_REVIEW`. After ChatGPT `/review` and RAM gate, run heavy gates. Then authorized production deploy is allowed with backup/rollback and no schema/data destructive migration.

## WP-01 — Reconcile baseline and lifecycle state

- Verify current HEAD/remote, clean/dirty owner changes, W40 code/tests, active services/jobs and actual compression/capture/docs entry points.
- Preserve existing working tree; no worktree. If owner edits overlap, only stage explicit files and include no unrelated user changes.
- Write checkpoint and list exact source-state transitions and existing persistence schema before editing.
- Evidence: baseline SHA, status, active-job inventory, relevant service/config root evidence.

## WP-02 — Compression integrity/provenance

- Introduce the smallest compatible provenance/state model and migration/default handling.
- Stage output, probe both source and candidate with available ffprobe/library, compare streams/duration, require size reduction, atomically publish, persist provenance, re-open/verify published hash and registration, then unlink only the linked source.
- Preserve original for all errors and make interrupted retries idempotent.
- Evidence: AC-01/02 tests including FFmpeg failures, invalid streams, duration mismatch, output too large, collision, publish/index failure, and retry.

## WP-03 — Surface compression retention result

- Expose original/optimized size, bytes saved, cleanup status and deterministic reason through existing API/UI surfaces.
- Keep UI controls state-based and use current SafePathResolver/auth checks. A cleanup retry is allowed only for a provenance-matched source.
- Evidence: AC-03 API/UI tests; no generic deletion action added.

## WP-04 — Capture cleanup and duration invariants

- Keep ordered assembly/completeness checks and verified duration persistence.
- Exercise >=3 ACKed fragments through assembly, then processing success and temporary cleanup; exercise failure/cancel/restart/hash mismatch/partial mapping retaining all recoverable inputs.
- Retain final file, manifest/provenance and docs; hide internal chunks from media/delete UI.
- Evidence: AC-04/05 tests, ffprobe output and fixture artifact.

## WP-05 — Docs and mobile UI regression

- Verify Regenerate Documentation button placement and mobile visibility, progress/result states and version selection.
- Tests prove no transcription, FFmpeg, OCR or vision calls; Reprocess Video remains separate.
- Regress pointer crop across portrait/landscape, touch, mouse, pointer capture/cancel and object-fit geometry; Clear Crop remains adjacent.
- Test delete visibility/reason matrix and duration formatting from persisted metadata.
- Evidence: AC-05/06/07 Playwright + focused tests.

## WP-06 — Desktop/LAN parity and synthetic end-to-end

- Verify Docker bind, host/LAN environment, DB path, media root, jobs/worker configuration and revision marker; remove configuration divergence at its root, not by copying data.
- Synthetic flow: capture >=3 fragments -> assembly -> validated duration -> processing -> docs -> regeneration/version -> cleanup state; also source -> optimize -> verify -> cleanup.
- Confirm desktop/LAN API sets and state match, and responsive UI controls work on both origins.
- Evidence: AC-08/09 Host E2E, parity JSON and ffprobe artifact.

## WP-07 — Implementation closure and ChatGPT review

- Run targeted gates, quality/lint/typecheck and code/diff review.
- Commit/push implementation; update checkpoint and DELIVERY evidence; stop at `READY_FOR_CHATGPT_REVIEW`.
- Do not run heavy gates or deploy until ChatGPT review is approved.

## WP-08 — Heavy release gates

- Verify `scripts/ram_gate.py`; if <=6 GiB, report `HEAVY_VALIDATION_DEFERRED_LOW_RAM`, keep implementation pushed, and defer heavy validation/deploy.
- Otherwise run full pytest, security, smoke, authoritative E2E, Docker gates, configured Sonar/Jenkins/CI in protocol order. Do not treat NOT_CONFIGURED as PASS.
- Any heavy failure returns to ChatGPT review with compact deterministic evidence; do not self-approve a scope change.

## WP-09 — Authorized production deployment and UAT readiness

- Confirm final approved SHA equals origin and all required gates pass; capture production config/service identities and backup/rollback steps.
- Deploy/restart only the current Whisper desktop and LAN services, from the same reviewed SHA and shared data root. No account/environment substitution, schema reset, data copy, or deletion/migration of user media.
- Verify health, served HEAD markers, localhost/LAN normalized video/project/job/docs/worker parity, mobile crop/docs/duration/delete behavior, and synthetic multiframe playback. Confirm rollback command and previous image/SHA.
- Record deployment and checks in DELIVERY. Stop at `READY_FOR_HUMAN_ACCEPTANCE`; owner performs final real-phone UAT before `DONE`.

## Rollback

Keep the last known-good production image/SHA and configuration. If health, parity, or integrity checks fail, restore the previous image/config without touching shared data. Do not run cleanup or backfill against real originals during rollback.
