# AUDIT-ZMI-LIFECYCLE-001 — Capture, storage and documentation lifecycle

## Objective

Complete the user-facing workflow from live capture through durable assembly, optimized-media retention, temporary cleanup, and documentation regeneration; then validate and publish the reviewed result to the running production system for UAT.

## Baseline evidence

- W40 records the JM capture integrity incident as recovered: session `sess-4ee4a8f39d86`, five ACKed/present fragments, 71.295 s expected, old final 14.944 s, reconstructed final 71.25 s with all five fragments in order. Original fragments were retained. A synthetic three-fragment 45 s assembly regression passed.
- W40 records Pointer Event crop, mobile Playwright, duration column, state-specific delete action, desktop/LAN data parity, served revision parity, and Host E2E as passing at that checkpoint.
- Current compressor `src/transcript_pipeline/media/compressor.py` publishes an FFmpeg output then removes the source using a weak success test (process success/output existence); it does not sufficiently prove output playability, stream presence, duration preservation, or space savings before source deletion.
- Live Capture cleanup is separately guarded: temporary pieces are removed only after a final exists and matches the manifest, mappings are finalized, and all chunks are processed. Preserve this safety invariant.
- GC candidates are advisory; general age-based deletion is not authorized.
- Documentation V2 already separates regeneration from reprocessing, regenerates from saved evidence, and stores versions. Preserve it and close regression/UI coverage.

## Gaps to close

1. Compression must validate and durably publish the optimized file before deleting its exact source, with auditable provenance and retry-safe cleanup status.
2. Compression and capture cleanup outcomes need clear user-visible status. Users must be able to distinguish optimized media retained, raw source removed, or cleanup pending.
3. Live capture temporary fragments need explicit success/failure/retry regression coverage; never expose internal chunks as user media.
4. Documentation regeneration must remain a one-click, versioned action on desktop/mobile, distinct from reprocessing.
5. Final acceptance must exercise localhost and LAN as two views of one backend and publish only a reviewed, gated HEAD to the current production services.

## Constraints

- Keep ChatGPT/Codex on analysis, integrity threat review, acceptance evidence and release decision; use OpenCode Go as primary economical coder, with the configured DeepSeek alias fallback through `scripts/model_router.py`.
- No secrets/private model IDs in Git. No real customer media in fixtures or committed artifacts.
- Synthetic tests and isolated roots only. Do not test cleanup against unlinked, ambiguous, or unverified production originals.
- Do not run heavy gates before ChatGPT review and `scripts/ram_gate.py`; RAM must be >6 GiB.
- Production publication is authorized by the owner for this scope, after review and release gates. Do not publish if integrity, security, shared-data, or rollback checks fail.

## Decision

Freeze this scope in `US-ZMI-LIFECYCLE-001`, implement using `PLAN-ZMI-LIFECYCLE-001`, and use the bounded coder prompt in `LOCAL-CODER-ZMI-LIFECYCLE-001`. The existing W40 acceptance remains evidence, not a reason to reimplement completed work.
