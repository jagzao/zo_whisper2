# DELIVERY-ZMI-LIFECYCLE-001 — implementation checkpoint

## Status

`READY_FOR_HUMAN_ACCEPTANCE`

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

## Gate repair round — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Full regression / loopback TLS | 🟥 BLOCKED | Python 3.12 full pytest: 1225 passed, 1 failed, 6 errors from reset loopback TLS handshakes. Explicit host-interception handling added; focused rerun: 1 passed, 6 environment skips. | Rerun full pytest | Codex |
| Black video Host E2E | 🟨 TESTING | Smoke dashboard passed. Black-tools browser timed out waiting for `DOMContentLoaded` at 30 s before scenario checks; navigation now waits for commit then `#filesList` up to 60 s. | Rerun Host E2E and exercise all black-video UI paths | Codex |
| Security / smoke / Docker | 🟩 COMPLETE | Security PASS (116 passed, 3 skipped; dependency audit clean); smoke PASS; Docker build PASS (200.45 s); Docker E2E PASS (109.72 s). | Retain reports | Codex |
| Sonar / Jenkins / soak | 🟥 BLOCKED | Runner reports `NOT_CONFIGURED` for all three. | No local executable is configured | Codex |

RAM opened briefly at 6.33 GiB for the first heavy run, then fell during validation. The canonical runner completed its gates; the next regression and Host E2E run remains scheduled for a stable >6 GiB window. No deployment/restart occurred.

## Black video delivery run — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Temporal preview, review gate, and non-destructive trim | 🟩 COMPLETE | Full pytest: 1226 passed, 13 skipped; isolated and full Host Playwright passed ranges, removed duration, cancel/confirm, derivative output, and original preservation. | Preserve evidence | Codex |
| Separate black-border crop | 🟩 COMPLETE | Unit cases and Host Playwright passed separate letterbox/pillarbox crop confirmation and derivative creation. | Preserve evidence | Codex |
| Live capture auto-stop | 🟩 COMPLETE | Host Playwright passed Off default, warning/countdown, visible-content cancellation, stop, and mobile layout. Screenshot: `artifacts/gates/e2e-host-data/black-video-tools.png`. | Preserve evidence | Codex |
| Playwright and Host E2E | 🟩 COMPLETE | Full `scripts/e2e.py` PASS includes dashboard smoke and every black-video path. Report: `artifacts/gates/e2e-host-data/e2e_report.json`. | Preserve evidence | Codex |
| Full regression / release gates | 🟩 COMPLETE | Canonical runner PASS: pytest, security, smoke, Host E2E, Docker build and Docker E2E. Report: `artifacts/gates/heavy-validation.json`. | Preserve evidence | Codex |
| Sonar / Jenkins / soak | 🟥 BLOCKED | `NOT_CONFIGURED`; these tools are absent from the release environment and are not required core gates. | Keep explicitly ENV_BLOCKED | Codex |
| Desktop/LAN deployment and served UI parity | 🟩 COMPLETE | Rebuilt desktop and started LAN from this checkout; both return 200 and matching HEAD header/meta. Playwright confirms temporal/crop controls, safe defaults and mobile layout. Shared data hashes and desktop/LAN media identity parity match. Evidence: `artifacts/gates/deployment-post.json`, `artifacts/gates/served-black-video-ui.json`. | Preserve evidence | Codex |

Completion is based on passing tests, Host Playwright evidence, and served desktop/LAN verification. Final owner real-phone UAT remains the canonical acceptance step.


## Local HTTPS trust repair — 2026-10-19

- Leaf certificate on disk chains to `CN=Whisper LAN Local CA`; SAN includes localhost, 127.0.0.1, active LAN IP 192.168.50.20, and configured DNS/IP names. Server-auth EKU is present.
- Root CA is installed in Windows `CurrentUser\Root`. `certutil -user -verify` built the leaf-to-root chain; its only reported issue is unavailable revocation information for this private CA. .NET X509Chain builds successfully with revocation disabled for this no-CRL local CA.
- Windows `Invoke-WebRequest`, default Python requests trust bundle, and Playwright each returned the Whisper UI (HTTP 200) at `https://localhost:5001`, `https://127.0.0.1:5001`, and `https://192.168.50.20:5001`. All three served build metadata `31accd058ff9b47c261476a184d33029f5aa55ee`.
- Norton HTTPS inspection replaces the peer leaf; verified peer issuer is `Norton Web/Mail Shield Root` / `generated by Norton Antivirus for SSL/TLS scanning`. Python strict verification against only the Whisper CA fails on the intercepted connection. Norton Web Protection was not disabled. Delivery remains TESTING until only the three local origins are excluded from Safe Web scanning and strict peer-chain verification passes.
- Public root only is exported to `artifacts/gates/Whisper-LAN-Local-CA.cer` for Galaxy installation. No CA private key was exported. Phone installation and physical-device verification remain owner actions. Steps: `docs/ops/MOBILE_LAN_ACCESS.md`.
- Evidence artifacts: `artifacts/gates/Whisper-LAN-Local-CA.cer`, `artifacts/gates/Whisper-LAN-Local-CA.pem`, `artifacts/gates/https-cert-dashboard.*.log`.
