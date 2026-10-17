# DELIVERY-ZMI-LIFECYCLE-001 — implementation checkpoint

## Status

`HEAVY_VALIDATION_DEFERRED_LOW_RAM`

## Implemented

- Large originals are encoded to staged MP4/H.265, probed for playable video/audio and duration, checked for meaningful size reduction, atomically published, hash-verified and registered before source cleanup.
- Failed validation preserves the original. Provenance records source/output hashes, sizes, durations, saved bytes and cleanup state. Authenticated retry is limited to pending records whose paths/hashes still validate.
- Dashboard exposes optimized/original sizes, savings, cleanup state/reason and pending retry. It refreshes after a processing run finishes.
- Existing Live Capture finalization, duration, pointer crop, shared desktop/LAN data root, video duration column, deterministic delete reasons, documentation regeneration/version history and processing-gated temporary cleanup were confirmed in W40 evidence in `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md`.

## Validation evidence

- Focused pytest across media optimization, dashboard API, capture cleanup/assembly/chunks, shared root, revision parity, ffprobe retry, pipeline/dashboard and security endpoints: **168 passed, 4 skipped**. Four skips require Windows symlink privilege.
- Ruff on changed Python surfaces and `git diff --check`: **PASS**.
- Real FFmpeg synthetic MP4 and WebM/Opus inputs: optimized output probe and complete decode passed in focused tests.
- RAM gate: **2.11 GiB available / 6.0 GiB required**, so full pytest, security, smoke, authoritative E2E, Docker release gates and live-service restart are deferred by PLV5.
- No production service was restarted and no real source or recording was modified in this checkpoint.

## Remaining before human acceptance

- Run the ordered heavy gates once available RAM is above 6 GiB.
- Complete W45 isolated synthetic end-to-end and served desktop/LAN parity verification from the final committed SHA.
- Restart both services only after all required gates pass; confirm shared data, mobile crop/docs, duration, playback and deterministic delete reasons.
- Owner performs the final real-phone UAT.
