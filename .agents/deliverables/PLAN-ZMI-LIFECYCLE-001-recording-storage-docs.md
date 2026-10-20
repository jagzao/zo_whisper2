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

- No worktree. Preserve all existing working-tree edits; never reset, stash, or clean. Commit coherent checkpoints and push them.
- Model order: Z.AI/GLM; if auth/provider unavailable, OpenCode Go/DeepSeek Flash; then local DeepSeek/Ollama; then any available current coding model. DeepSeek Pro only for a difficult blocker after cheaper attempts. GLM auth failure is `MODEL_DEGRADED=YES`, never a project blocker.
- Synthetic/isolated data for tests. Never test destructive cleanup against user originals.
- New/changed business logic must have relevant unit tests and those tests must pass. Build/import/start and migration/data-safety checks are mandatory. Integration, Playwright, E2E, Docker, security scans, and resource-heavy gates are advisory; run when practical and record `PASS`, `FAIL_ADVISORY`, `ENV_BLOCKED`, `NOT_CONFIGURED`, or `NOT_RUN` with evidence. RAM controls execution strategy, never publication eligibility.
- Commit and push code, canonical SDD, and the single active Kanban. Deploy only the final pushed HEAD, preserve rollback, shared data, and any active job.

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

## WP-07 - Implementation closure and objective source checks

- Run focused regression, quality/lint/typecheck, inspect the code diff, and require `git diff --check`.
- Commit/push implementation and record exact evidence in DELIVERY. A manual review approval is not a release prerequisite; failed objective checks block the next stage.

## WP-08 — Optional confidence checks

- After implementation and unit tests are complete, attempt integration, media regression, Playwright, Host E2E, Docker E2E, and security checks when practical. Serialize resource-heavy checks when useful.
- Record every attempted/unavailable check as `PASS`, `FAIL_ADVISORY`, `ENV_BLOCKED`, `NOT_CONFIGURED`, or `NOT_RUN`. Advisory failure creates a defect/UAT item and does not block deployment unless it proves a hard blocker: incomplete requested feature, relevant unit failure, app build/start failure, or known data loss/corruption.
- Jenkins, Sonar, and soak are `NOT_REQUIRED`; do not configure them for this release.

## WP-09 — Authorized production deployment and UAT readiness

- Confirm the final pushed SHA equals origin; capture production config/service identities, pre-deploy shared-data snapshot, and backup/rollback steps. Advisory gates are not prerequisites.
- Preserve the active processing job. Restart only if inactive or if web can be isolated from the worker without loss; otherwise wait for job completion while continuing independent work.
- Deploy/restart only the current Whisper desktop and LAN services, from the same reviewed SHA and shared data root. No account/environment substitution, schema reset, data copy, or deletion/migration of user media.
- Verify health, served HEAD markers, localhost/LAN normalized video/project/job/docs/worker parity, Videos, New Recording, Video Editor, Overview modal, and `/setup`. Confirm rollback command and previous image/SHA.
- Record deployment and checks in DELIVERY. Stop at `READY_FOR_HUMAN_ACCEPTANCE`; owner performs final real-phone UAT before `DONE`.

## Delivery Kanban — black video completion, 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Temporal detection, preview, review, trim | 🟨 TESTING | Media/API unit tests pass; isolated browser verified ranges, total removed duration, cancel/confirm, derivative output, original preservation. | Canonical full regression after stable RAM >6 GiB | Codex |
| Separate spatial border crop | 🟨 TESTING | Letterbox/pillarbox unit cases and browser crop workflow pass. | Canonical full regression after stable RAM >6 GiB | Codex |
| Black-preview capture auto-stop | 🟨 TESTING | Browser verified safe Off default, countdown warning, visible-content cancellation, stop behavior and mobile layout. | Canonical full regression after stable RAM >6 GiB | Codex |
| Playwright / Host E2E | 🟩 COMPLETE | Full host smoke plus all black-video scenarios pass; report and screenshot are in `artifacts/gates/e2e-host-data/`. | Retain evidence | Codex |
| Full regression and release gates | 🟨 TESTING | Latest full run found one floating-point timeout assertion; tolerance fixed. Security, smoke and Docker build/E2E passed. | Rerun canonical runner after stable RAM >6 GiB | Codex |
| Sonar / Jenkins / soak | 🟥 BLOCKED | Runner reports `NOT_CONFIGURED`. | Keep explicitly ENV_BLOCKED | Codex |
| Desktop/LAN deploy and served UI | TODO | Not restarted; live services still serve the previous build; shared data unchanged. | After required gates pass, deploy final HEAD and verify served SHA, shared-data parity and black-trim controls | Codex |

## Rollback

Keep the last known-good production image/SHA and configuration. If health, parity, or integrity checks fail, restore the previous image/config without touching shared data. Do not run cleanup or backfill against real originals during rollback.


## Delivery Kanban - release recovery (2026-10-18)

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Stop and safe delete from Videos table | 🟨 TESTING | Cooperative capture stop and confirmed session delete; 51 dashboard/capture tests pass; committed and pushed as `5b5d4a3` | Mobile browser UAT after deploy | Codex |
| Crop geometry and mobile touch | 🟨 TESTING | Isolated Playwright PASS for fill/contain/cover, portrait/landscape, touch capture, Clear Crop, roundtrip | Mobile capture and served UAT after deployment | Codex |
| Job `f50a16874aeb40e38db4ba6e13382f89` | 🟩 COMPLETE | Persisted status COMPLETED, attempt 4 | Preserve job history | Codex |
| Job `f4afbebcadc245efae26bcd57ed679bd` | 🟦 IN PROGRESS | Queue ACTIVE attempt 4; owner PID 1604 absent, heartbeat stale since 16:13 local. Host master PIDs 24988/48584 scan 716 files; Session 41 keyframe probe timed out, fallback `scene` produced no frame. `.venv-validation` has broken namespace `av` (`audio` missing), causing transcription errors. Worker stale-recovery tests pass 3/3. Preserve processes; do not restart or recover concurrently. | Let current pipeline exit; then repair runtime dependency, recover stale job through existing worker, and verify no duplicate execution | Worker |
| LAN/PyPI TLS trust | 🟨 TESTING | LAN HTTPS and pip index use verified TLS; repaired corrupt certifi. Combined upstream certifi + trusted local root is configured as user `REQUESTS_CA_BUNDLE`; default `requests` call to PyPI returns 200. Docker runtime now points `REQUESTS_CA_BUNDLE` to the system CA store populated by the BuildKit secret. Compose config passes and 56 Docker gate tests pass; full Docker build pending RAM | Ensure restarted host inherits CA bundle; run Docker build gate after RAM exceeds 6 GiB | Codex |
| Shared desktop/LAN data | 🟨 TESTING | Bind maps `C:\Dev\Zo\whisper` to `/data`; projects API payload SHA256 matches: `0cde94cf8daa94db57c167c73e31d613d78e3c042102964d5a934a376527f455`; LAN lists 55; localhost `/api/files` timed out | Compare files/docs after safe restart | Codex |
| Shared worker status parity | 🟨 TESTING | `/api/status` now reads `running`, mode, start time, and active/cancel-requested count from shared queue; 35 LAN/worker tests pass | Deploy and compare both origins | Codex |
| RAM and heavy release gates | 🟥 BLOCKED | Latest `scripts/ram_gate.py` reports 1.88 GiB available (threshold 6.0); master PID 48584 uses ~1.7 GiB and Jenkins/SonarQube are active | Preserve active processing and CI; recheck after they finish | Codex |
| Regression, mobile capture, Host E2E, heavy, Docker E2E | 🟨 TESTING | 51 focused dashboard/capture/date/delete tests pass in 4.61s; 56 Docker gate tests pass after runtime CA update; prior crop Playwright and assembly regressions pass; current Host E2E/mobile served UAT/heavy gates remain pending | Run remaining gates after safe worker completion and RAM threshold | Codex |
| Desktop/LAN rebuild and UAT | PENDING | HEAD/origin `00e18db03429ce91e5ea41d26e80de60a2924791`; both health endpoints return ONLINE, but localhost pipeline state reports `running=false`/transcription error while shared queue still counts one active job; do not restart while compressor child runs | Reconcile job after compressor exits, run gates, then deploy same HEAD to both services | Codex |
| Repeated AMS KAP playlist rows | 🟩 COMPLETE | Three distinct synthetic Playwright sessions; 1, 1, and 3 ACKed fragments; same fixture title; not optimized media | Preserve records; delete only through new stop/confirm UI after served | Codex |

## Delivery Kanban — black video tools (2026-10-18)

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Temporal black detection and non-destructive trim | 🟨 TESTING | 12 targeted FFmpeg/API tests pass; scan returns intervals and total removed; validated derivative preserves source | Feature E2E after RAM gate | Codex |
| Spatial black border detection and crop | 🟨 TESTING | Separate letterbox/pillarbox detection and crop API; synthetic source hash and duration preserved | Capture UI evidence in isolated Host E2E | Codex |
| Live capture black preview auto-stop | 🟨 TESTING | Explicit Off/30/60/120 s selection, 10 s warning, reset when content returns; dashboard UI added | Verify countdown and cancellation in Playwright/Host E2E | Codex |
| Black tools implementation gates | 🟨 TESTING | 12 focused pytest passed; changed-file Ruff, compileall and `git diff --check` pass | Playwright/Host E2E after RAM gate | Codex |

## Black video completion run — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Temporal detection and non-destructive trim | 🟨 TESTING | `watcher/venv/Scripts/python.exe -m pytest tests/test_black_video.py tests/test_dashboard_black_video_api.py -q`: 12 passed, including fully black, short transition, multiple/start/end intervals, naturally dark footage, audio, duration, and source hash preservation | Run Playwright review/confirmation and Host E2E when RAM exceeds 6 GiB | Codex |
| Separate letterbox/pillarbox detection and crop | 🟨 TESTING | Same 12 tests include synthetic letterbox and pillarbox, crop output and temporal independence | Capture Playwright UI evidence when RAM exceeds 6 GiB | Codex |
| Live capture black preview auto-stop | 🟨 TESTING | Code has Off default, 30/60/120 s, 10 s warning and reset when content returns; no browser evidence in this run | Verify countdown, stop and cancellation in Playwright/Host E2E when RAM exceeds 6 GiB | Codex |
| Black video UI and Host E2E | 🟥 BLOCKED | `scripts/ram_gate.py`: 4.33 GiB available; canonical threshold is >6.0 GiB. Host E2E/Playwright were not run | Recheck RAM; run isolated black-video UI subset after gate opens | Codex |

## Gate repair round — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Full regression and loopback TLS | 🟥 BLOCKED | Full pytest on locked Python 3.12: 1225 passed, 1 failed, 6 errored. Six TLS setup failures and the TLS handshake test reset at loopback. Added explicit interception detection; focused rerun: 1 passed, 6 skipped as host TLS interception. | Rerun full pytest under canonical heavy runner | Codex |
| Black video Host E2E | 🟨 TESTING | Smoke UI passed; black tools script timed out waiting for `DOMContentLoaded` on its second browser. Changed to commit navigation plus bounded `#filesList` readiness wait. | Rerun full Host E2E when RAM is stable above 6 GiB | Codex |
| Security, smoke, Docker build/E2E | 🟩 COMPLETE | Heavy runner: security PASS, smoke PASS, Docker build PASS (200.45 s), Docker E2E PASS (109.72 s). | Keep artifacts for release record | Codex |
| Sonar, Jenkins, soak | 🟥 BLOCKED | Authoritative commands report `NOT_CONFIGURED`; not counted as PASS. | Configure only if part of the release environment | Codex |

## Delivery Kanban — black video release verification, 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Temporal detection, review and non-destructive trim | 🟩 COMPLETE | Full pytest: 1226 passed, 13 skipped; Host Playwright passed preview, review, cancel/confirm, output and source preservation. | Preserve evidence | Codex |
| Separate black-border crop | 🟩 COMPLETE | Letterbox/pillarbox unit coverage and Host Playwright crop flow pass. | Preserve evidence | Codex |
| Live capture auto-stop | 🟩 COMPLETE | Host Playwright passed Off default, warning/countdown, content-return cancel, stop and mobile layout. | Preserve evidence | Codex |
| Playwright / Host E2E | 🟩 COMPLETE | Full Host E2E and dashboard smoke pass; report and screenshots in `artifacts/gates/e2e-host-data/`. | Preserve evidence | Codex |
| Security, smoke, Docker build/E2E | 🟩 COMPLETE | Canonical heavy runner reports all core gates PASS; `artifacts/gates/heavy-validation.json`. | Preserve evidence | Codex |
| Sonar / Jenkins / soak | 🟥 BLOCKED | `NOT_CONFIGURED`; unavailable in this environment, separate from required core gates. | Keep marked ENV_BLOCKED | Codex |
| Desktop/LAN rebuild and served UI | 🟩 COMPLETE | Both origins return 200 and match current build header/meta; live Playwright verified black-trim controls and mobile layout. Pre/post shared-data hashes and desktop/LAN media identity parity match. | Preserve evidence | Codex |


## Local HTTPS trust repair — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Leaf SAN and local CA chain | 🟨 TESTING | Leaf includes `DNS:localhost`, `IP:127.0.0.1`, `IP:192.168.50.20` (active LAN IP), serverAuth EKU, and issuer `Whisper LAN Local CA`; Windows CurrentUser Root contains that CA. Windows X509Chain builds to that root; local CA has no revocation endpoint. | Retest direct on-wire chain after Norton local-origin exclusion | Codex |
| HTTPS localhost, loopback, and LAN | 🟨 TESTING | Windows browser, `Invoke-WebRequest`, Python requests default CA bundle, and Chromium return HTTP 200/UI at all three URLs. Served build meta is `31accd058ff9b47c261476a184d33029f5aa55ee`. | Repeat strict Whisper-CA verification after Norton exclusion | Codex |
| Norton HTTPS scanning | 🟥 BLOCKED | Peer issuer is `Norton Web/Mail Shield Root` with OU `generated by Norton Antivirus for SSL/TLS scanning`; Norton reissues the connection. Explicit Whisper-CA verification therefore fails. Web Protection remains enabled. | Add only the three local HTTPS origins to Safe Web Exclusions; retest peer issuer and strict chain | Owner |
| Galaxy public CA export and instructions | 🟩 COMPLETE | Public root only exported as `artifacts/gates/Whisper-LAN-Local-CA.cer`; no private key copied. Galaxy One UI install steps documented in `docs/ops/MOBILE_LAN_ACCESS.md`. | Install public CA and verify on phone after Norton configuration | Owner |

Strict verification: `requests.get(..., verify=<Whisper CA PEM>)` fails for all three local origins while Norton substitutes its own leaf; normal Windows/Python trust validation and Playwright pass. No TLS validation bypass was used. Exact local origins and Norton instructions are in `docs/ops/MOBILE_LAN_ACCESS.md`.

## Delivery Kanban - video trim editor, 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| TIME editor: playback, timeline, reviewable cuts, manual trim, preview | 🟩 COMPLETE | Host Playwright verifies seek/play, detected interval adjustment/deselection, manual cut/trim, preview, reset and cancel. Screenshot: `artifacts/gates/e2e-host-data/video-trim-editor.png` | Preserve evidence | Codex |
| FRAME editor: border detection, crop rectangle, preview and reset | 🟩 COMPLETE | Isolated letterbox fixture verifies suggested crop, manual adjustment, crop preview/reset and apply | Preserve evidence | Codex |
| Apply: validated copy, source preservation and provenance | 🟩 COMPLETE | 16 focused pytest tests pass; API and Host E2E verify valid output, sidecar provenance and unchanged source hash | Preserve evidence | Codex |
| Playwright / Host E2E | 🟩 COMPLETE | `scripts/e2e.py` PASS; report `artifacts/gates/e2e-host-data/e2e_report.json`; includes mobile layout and capture auto-stop warning/cancel | Preserve evidence | Codex |
| Desktop and LAN deployment from final HEAD | 🟩 COMPLETE | Desktop image rebuilt and LAN host process restarted; strict requests + Playwright verify HTTP 200 and Edit video TIME/FRAME controls at desktop, LAN localhost and LAN IP. Both serve `131abb068ee245e4da97bbd34434ab1cc92e1671`; 58-file count, state hashes, media tree, projects and desktop/LAN identity match pre-restart evidence. Artifacts: `artifacts/gates/served-video-trim-editor.json`, `artifacts/gates/deployment-post.json` | Preserve evidence | Codex |

## Delivery Kanban - video editor and mobile landscape UAT, 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Precise crop: 8 handles, drag, aspect lock, zoom/pan, source-pixel mapping | 🟨 TESTING | Focused Host Playwright passes every handle, drag, zoom/pan and original-pixel bounds | Deploy and verify served editor | Codex |
| HH:MM:SS inputs and draggable trim/cut timeline | 🟨 TESTING | Focused Host Playwright verifies >1h timecode and synchronized trim/cut handles | Deploy and verify served timeline | Codex |
| Apply lifecycle, idempotency, validated derivative and provenance | 🟨 TESTING | 82 focused unit/API tests pass; Host E2E verifies PROCESSING/VALIDATING/COMPLETED, one derivative, playable output and unchanged original | Deploy and verify Show result | Codex |
| Landscape orientation and rear-camera retention | 🟨 TESTING | Synthetic browser media verifies portrait-to-landscape-to-portrait with rear camera and crop alignment | Verify on physical phone | Owner |
| Quality selector and actual capture metadata | 🟨 TESTING | Host E2E verifies Auto 1080p request, 720p fallback, actual settings, codec/bitrate reporting | Verify displayed settings on physical phone | Owner |
| Landscape layout, timer and accessible controls | 🟨 TESTING | Host E2E verifies landscape preview, timer, Start/Stop and no page overflow | Verify on physical phone | Owner |
| Playwright and relevant Host E2E | 🟨 TESTING | `scripts/e2e.py` focused gate PASS; 82 unit/API tests PASS; full smoke gate previously reset before browser load | Rerun full Host E2E after RAM gate permits | Codex |
| Desktop/LAN deployment and served UI | TODO | Not restarted from this candidate HEAD; canonical RAM gate currently reports 5.38 GiB | After automated gates and RAM >6 GiB, build/restart; verify served SHA and shared-data parity | Codex |
| Physical-phone UAT | TODO | Exact checklist: `docs/ops/VIDEO_EDITOR_MOBILE_UAT.md`; synthetic Playwright is not phone evidence | Owner follows checklist after deployment | Owner |
| Full repository heavy gate | 🟥 BLOCKED | `scripts/ram_gate.py`: 5.38 GiB available, threshold strictly >6 GiB | Rerun when RAM gate allows | Codex |
| Mobile certificate onboarding | 🟨 TESTING | 65 tests pass (1 skipped); Host E2E Playwright verifies desktop QR, persistent dismiss, mobile layout and public-only CA download (`artifacts/gates/e2e-host-data/e2e_report.json`) | Deploy and verify served `/setup` | Agent |
| Android CA installation | TODO | Playwright confirms only public root download and Samsung steps; no physical install performed | Confirm install on Galaxy phone | Juan |
| Secure LAN access | TODO | HTTP allowlist/redirect tests pass; Compose LAN opt-in config passes; live restart/strict HTTPS not verified | Deploy after gate; verify certificate download and HTTPS on phone | Juan + Agent |
| Mobile onboarding deployment gate | 🟥 BLOCKED | RAM gate reports 4.76 GiB; canonical deploy gate requires automated gates and >6 GiB | Rerun gate, then rebuild/restart desktop and LAN services | Agent |


## Automated release acceptance policy — canonical, 2026-10-19

This section replaces every earlier gate rule in this plan, including the fixed `>6 GiB` RAM guard and requirements that integration, Playwright/E2E, Docker E2E, Jenkins, Sonar, soak, or phone UAT pass before publication. All dated Kanban tables above are historical evidence only.

Hard blockers — the only conditions that block release: incomplete requested implementation; relevant unit tests fail; app build/start fails; known data loss or corruption; an unsafe restart that would lose the active user job and cannot be isolated or recovered.

Advisory gates (integration, E2E, Playwright, Host E2E, Docker build/E2E, heavy gates, security, other optional checks) record exactly one of `PASS`, `FAIL_ADVISORY`, `ENV_BLOCKED`, `NOT_CONFIGURED`, `NOT_RUN`. Advisory results never block release, and `PASS` requires executed evidence from the current run. Jenkins, Sonar and soak are `NOT_REQUIRED`. RAM affects execution strategy only (ordering, serialization, deferral) — never release eligibility; never stop an active user job or unrelated services to manufacture headroom. Physical Galaxy phone UAT is `OWNER_PENDING` owner verification and does not hold release.

Model policy: GLM is the preferred executor; on auth/provider failure degrade to the cheapest available fallback. Provider routing is an execution detail, never a project blocker.

Mandatory engineering Definition of Done: scope complete per the US; no TODO/mock in requested production functionality; relevant unit tests pass; app builds/imports/starts; migrations valid; data safety (no user data loss; active job preserved); code + SDD + Kanban committed and pushed.

Deploy verification (required whenever deploying): deploy only the final pushed HEAD with rollback available; deploy only when the active job is inactive or safely isolatable/recoverable; verify desktop and LAN HTTPS serve that exact HEAD, health is ONLINE, and shared-data parity holds against a pre-deploy snapshot; then run the required lightweight post-deploy smoke: dashboard loads, Videos list renders, worker RUNNING with expected counts, `/setup` reachable, served revision equals deployed HEAD.

## Current finalization status

The single authoritative active Delivery Kanban, canonical release policy and resume order are in `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md`, section `FINAL SDD RELEASE RUN`. All Kanban tables and gate lists in this file are historical evidence, not live status.
