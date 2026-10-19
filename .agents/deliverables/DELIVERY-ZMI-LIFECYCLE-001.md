# DELIVERY-ZMI-LIFECYCLE-001 — implementation checkpoint

## Status

`HEAVY_VALIDATION_DEFERRED_LOW_RAM`

## Implemented

- Large originals are encoded to staged MP4/H.265, probed for playable video/audio and duration, checked for meaningful size reduction, atomically published, hash-verified and registered before source cleanup.
- Failed validation preserves the original. Provenance records source/output hashes, sizes, durations, saved bytes and cleanup state. Authenticated retry is limited to pending records whose paths/hashes still validate.
- Dashboard exposes optimized/original sizes, savings, cleanup state/reason and pending retry. It refreshes after a processing run finishes.
- Existing Live Capture finalization, duration, pointer crop, shared desktop/LAN data root, video duration column, deterministic delete reasons, documentation regeneration/version history and processing-gated temporary cleanup were confirmed in W40 evidence in `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md`.
- JM P0 audit/recovery: session `sess-4ee4a8f39d86`, expected timeline 71.295 s, 5/5 ACKed fragments present and mapped. The prior final was 14.944 s because FFmpeg received a `.tmp` output without an explicit container format, failed, and fallback byte-concatenation preserved reset timestamps. Reassembled and validated 71.25 s; old final backed up and all five source fragments retained.

## Validation evidence

- Focused pytest across media optimization, dashboard API, capture cleanup/assembly/chunks, shared root, revision parity, ffprobe retry, pipeline/dashboard and security endpoints: **168 passed, 4 skipped**. Four skips require Windows symlink privilege.
- Ruff on changed Python surfaces and `git diff --check`: **PASS**.
- Real FFmpeg synthetic MP4 and WebM/Opus inputs: optimized output probe and complete decode passed in focused tests.
- RAM gate: **2.11 GiB available / 6.0 GiB required**, so full pytest, security, smoke, authoritative E2E and Docker release gates are deferred by PLV5. Both workers report one active job, so restarting either service now could interrupt processing.
- No production service was restarted and no real source or recording was modified in this checkpoint.
- Implementation was committed and pushed as `dc9e942d4cb26e3dfe20233693a8b44baea6b2ad`; local and `origin/feat/zmi-documentation-synthesis-v2` match, with a clean worktree.
- Read-only live probe: `http://localhost:5000` and `https://192.168.50.20:5001` are ONLINE and both serve `32b83feea8831c491b92f046b2c44a250ff0733c`. Both return the same 45 video IDs and seven projects; both workers report RUNNING, zero pending, one active, concurrency one. Desktop Docker bind mounts the repository at `/data`; the previous `.67` LAN address is stale. The shared-data requirement is currently met, and the existing W40 mobile features are served, but the new optimized-media lifecycle is not yet served.

## Remaining before human acceptance

- Run the ordered heavy gates once available RAM is above 6 GiB.
- Complete W45 isolated synthetic end-to-end and served desktop/LAN parity verification from the final committed SHA.
- After the active processing job drains and all required gates pass, restart both services; confirm shared data, mobile crop/docs, duration, playback and deterministic delete reasons.
- Owner performs the final real-phone UAT.

## Black video feature checkpoint — 2026-10-18

- Temporal detection supports configurable darkness threshold and minimum duration (2 s default), multiple intervals, review preview with removed-time total, and H.264/AAC derivative output. Output is fully decoded/probed before publication; originals are never overwritten.
- Automatic temporal trim and spatial border crop are explicit opt-ins. Low-confidence automatic requests return `NEEDS_REVIEW`. Spatial border detection/crop is a separate operation.
- Live capture black-preview stop is opt-in (Off by default), configurable at 30/60/120 seconds, warns for 10 seconds, and cancels when visible content returns.
- Targeted test command: `watcher/venv/Scripts/python.exe -m pytest tests/test_black_video.py tests/test_dashboard_black_video_api.py -q` — **12 passed**. Synthetic tests cover all-black, brief dark transition, multiple/start/end intervals, naturally dark content, letterbox/pillarbox, audio continuity, duration, API review behavior and source preservation.
- Ruff on changed implementation/test/E2E files: **PASS**. `compileall -q src scripts`: **PASS**. `git diff --check`: **PASS**.
- Repository-wide Ruff gate is currently **FAIL on existing findings** outside this feature (47 findings in `scripts`/`tests`). `scripts/quality.py` syntax/import checks pass; its repository-wide Ruff and existing Pyright checks fail on unrelated files (`processor.py`, `versioning.py`, `kab_ingest`, etc.).
- Playwright/Host E2E remain **DEFERRED** under the canonical execution plan: current available RAM is below the 6 GiB heavy-gate threshold and ChatGPT `/review` has not occurred. The isolated fixture scenario is added to `scripts/e2e.py`; no live/user media is used.
- Feature remains `TESTING`; do not claim COMPLETE until reviewed heavy gates and visual UI evidence pass.

## Black video completion run — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Temporal detection and non-destructive trim | 🟨 TESTING | Targeted pytest — 12 passed; changed-file Ruff, compileall and `git diff --check` pass. Tests cover fully black, short transition, multiple/start/end intervals, naturally dark footage, audio, duration, source hash and API review gate. | Playwright UI review/confirmation | Codex |
| Separate spatial border detection/crop | 🟨 TESTING | Same run passed synthetic letterbox/pillarbox, crop output, source hash and duration checks; temporal scan stays separate. | Playwright UI evidence | Codex |
| Live capture auto-stop | 🟨 TESTING | Inspected implementation: explicit Off default, 30/60/120 s setting, 10 s countdown warning, content-return cancellation. Browser test not run. | Playwright countdown/stop/cancel verification | Codex |
| Playwright and Host E2E | 🟥 BLOCKED | `scripts/ram_gate.py`: 4.33 GiB available of >6.0 GiB required. Per canonical plan, both gates deferred. | Re-run RAM gate; run isolated black-video Host E2E and save screenshot/report | Codex |
| Original preservation | 🟩 COMPLETE | API integration test verifies original path and SHA-256 unchanged after temporal trim; media unit tests verify source unchanged after crop. | Keep invariant | Codex |

This run did not mark the feature complete. Head was `2b73649`; Playwright and Host E2E remain pending under the canonical RAM gate.
