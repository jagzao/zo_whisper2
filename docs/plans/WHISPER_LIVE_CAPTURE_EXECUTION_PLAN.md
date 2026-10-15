# Whisper Live Capture and Playlist Execution Plan

Canonical execution plan for `feat/zmi-documentation-synthesis-v2`. Continue this plan in place. Work only in this repository; no worktree, merge, or deployment. Update and commit evidence at stable checkpoints.

## Goal

Deliver a user-facing mobile-safe Live Capture flow at `Videos -> New Recording`, with short acknowledged upload fragments, bounded offline retry, server processing chunks, and Continuous Playlist capture. Detect and confirm title changes from multiple frames, map logical videos to physical fragments and processing chunks, expose review controls, and reuse Whisper's existing documentation pipeline. Preserve Date sorting, cancellation, missing-audio/late-transcript, crop, and advisory GC behavior.

## Current verified state

- Baseline at plan update: branch `feat/zmi-documentation-synthesis-v2`, HEAD `e9e61be470dcccd80df069c04524fcf92cd12ae2`, clean worktree; remote matched HEAD.
- Existing domain/API and basic browser capture are under `src/transcript_pipeline/live_capture/`, `dashboard/app.py`, and `dashboard.html`; capture is currently reached from a header icon labelled Capture, not `Videos -> New Recording`.
- Existing modal has preview, title, a 600 second chunk setting, optional microphone, crop, start/stop, upload retry/cancel, missing-audio warning, late transcript, processing controls, and GC suggestions. Prior targeted browser reports cover those earlier flows.
- UI inspection found no Normal Recording / Continuous Playlist mode, Save local copy toggle, visible timer, fragment-level ACK/progress, IndexedDB pending buffer, current source-title/logical-video list, or playlist review actions (rename/date/split/merge/confirm). Existing browser capture buffers MediaRecorder data until long processing-chunk rotation, so it does not meet the short-fragment mobile-memory requirement.
- Existing session/chunk model, streamed finalization, cancellation, crop, audio, transcript, docs integration, GC candidates, and Date API/sort remain useful implementation foundations. They are not PASS for the new user-facing scope until the expected UI journey and Playwright evidence pass.
- Last full host E2E: PASS, 56 checks, no browser errors (`artifacts/gates/e2e-host-data/e2e_report.json`). Last targeted suite: 45 passed. Prior full pytest: 975 passed, 3 skipped. Docker compose config passed; heavy runner previously deferred at 5.62 GiB available vs required >6 GiB.
- Synthetic fixtures only. Never use private recordings in automated media tests.

## Non-goals

- No duplicate transcription/documentation stack, cloud upload dependency, guessed title presented as confirmed, fabricated transcript synchronization, automatic deletion, or mandatory full local phone recording.
- No automatic gallery write. Local full copy defaults OFF and requires explicit opt-in.
- No arbitrary sleeps, weakened assertions, merge, deployment, worktree, unrelated redesign, or private media in tests.

## Architecture decisions

- Dashboard entry is `Videos -> New Recording`; a shared capture page/modal exposes Normal Recording and Continuous Playlist. Require browser camera permission, request microphone only when selected, and provide responsive controls and visible state/timer.
- MediaRecorder emits independently identified fragments about 10-30 seconds long. Upload each incrementally; delete its temporary local copy only after durable server ACK. Store unacknowledged fragments in IndexedDB with configurable byte/count limit, visible warning, retry/backoff, and idempotency key. Save local copy is an explicit opt-in.
- Server separates `capture_session`, `upload_fragment`, `processing_chunk` (~10-15 minutes, configurable), and `logical_video`. Fragments are assembled or referenced server-side; the phone never needs a 15-minute blob. Persist fragment ACK/digest and mappings atomically. Repeated fragment IDs return prior ACK without duplicate bytes.
- Capture/session states include CAPTURING, UPLOADING, UPLOAD_PAUSED, RETRYING, UPLOADED, PROCESSING, CANCEL_REQUESTED, CANCELLED, FAILED, COMPLETED. Stop recording finalizes capture; cancel upload aborts one pending transfer; cancel processing requests worker cancellation. They remain distinct and idempotent.
- Playlist physical time/fragments/processing chunks are independent from logical-video title boundaries. Periodically sample synthetic or real runtime frames; OCR broadly extracts title/category/session/date/time. Confirm a title only after repeated compatible evidence and threshold confidence. Otherwise expose NEEDS_TITLE_REVIEW; never invent confidence.
- A confirmed title change closes/opens logical-video mappings at its observed time, including inside a processing chunk. Review supports rename, recorded date correction, split, merge, and confirmation.
- Confirmed logical videos enter the existing Whisper processor, Date listing, and Documentation V2 flow. `recorded_at` precedes `created_at`; backend sorting remains newest-first by default and supports ASC/DESC before filtering/pagination.
- Missing audio remains valid (`AUDIO_MISSING` / `TRANSCRIPT_REQUIRED`); transcripts may be attached later with loose session/logical-video association. GC stays advisory and destructive deletion requires explicit user action.

## Execution stages

Status values: `PENDING | IN_PROGRESS | PASS | BLOCKED`. A user-facing stage passes only after the expected UI journey and relevant Playwright evidence pass. `BLOCKED` is reserved for external/environment constraints after the documented fallback; recoverable code failures remain in progress.

### W0 - Repository baseline
- Status: PASS
- Objective: record branch, HEAD, tree, current code/UI, tests, artifacts and model tooling.
- Dependencies: none.
- Implementation tasks: inspect capture routes/modal/table, domain/pipeline, tests, gate reports and available approved coding executors.
- Relevant files/modules: `src/transcript_pipeline/live_capture/`, `dashboard/`, `tests/`, `artifacts/gates/`, `.agents/`, `scripts/model_router.py`.
- Acceptance criteria: verified baseline and missing UI/mobile/playlist capabilities recorded.
- Required tests: none; read-only inspection.
- Validation commands: `git status --short --branch`; `git rev-parse HEAD`; source/report inspection.
- Expected artifacts: baseline in this plan.
- Recovery/fallback: use Git and source as authority; ignore stale generated reports.

### W1 - Canonical plan update
- Status: PASS
- Objective: commit this reconciled W0-W24 plan before implementation.
- Dependencies: W0 PASS.
- Implementation tasks: preserve historical backend evidence; reopen UI-dependent stages; write full scope, dependencies, validation, and risks; commit on current branch.
- Relevant files/modules: this plan.
- Acceptance criteria: same canonical plan contains all new scope and W0-W24 stages; commit exists before code changes.
- Required tests: `git diff --check`.
- Validation commands: inspect stage list/statuses; `git diff --check`; `git commit`.
- Expected artifacts: canonical plan commit.
- Recovery/fallback: repair this file and recommit; never create parallel plan.

### W2 - Existing host E2E repair
- Status: PASS
- Objective: preserve fixed dashboard critical path and project modal.
- Dependencies: W1 PASS.
- Implementation tasks: retain synthetic project fixture, page ownership fix, preview/filter and upload-test synchronization repairs.
- Relevant files/modules: `scripts/e2e.py`, `tests/e2e/smoke_dashboard.py`, gate artifacts.
- Acceptance criteria: host gate passes without TargetClosedError or browser errors.
- Required tests: host E2E and project modal.
- Validation commands: `.venv-validation\Scripts\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: E2E report with 56 checks.
- Recovery/fallback: inspect fresh report and correct root cause; no stale-report claims.

### W3 - Live Capture UI
- Status: PASS
- Objective: provide the expected `Videos -> New Recording` user journey.
- Dependencies: W1 PASS.
- Implementation tasks: add Videos action, responsive recording view, camera preview, Normal/Continuous Playlist modes, crop, optional Save local copy OFF, start/stop, visible timer/status, fragment/processing progress, detected title/logical-video list and separate cancel controls.
- Relevant files/modules: `dashboard/templates/dashboard.html`, `dashboard/app.py`, capture browser JS, `tests/e2e/`.
- Acceptance criteria: users can reach and operate the complete capture shell from Videos; not header-only.
- Required tests: Playwright opens Videos -> New Recording and verifies controls, fake-camera preview, timer, start/stop, and no browser errors.
- Validation commands: `.venv-validation\\Scripts\\python.exe -m pytest tests/test_dashboard_date_column.py -q`; synthetic host Playwright `tests/e2e/capture_new_recording.py`; regression `tests/e2e/capture_dashboard.py` and `tests/e2e/capture_cancellation.py`.
- Expected artifacts: `capture_new_recording_report.json`; existing capture and cancellation reports.
- Evidence: 23/23 capture-new-recording checks PASS; fake camera preview and timer advance observed; session finalized. Capture dashboard 16/16 PASS; cancellation 9/9 PASS; Date tests 5 PASS. Reports used isolated synthetic data roots; no private media. `git diff --check` PASS.
- Recovery/fallback: keep existing modal as shared implementation behind the Videos entry; do not duplicate capture state.

### W4 - Mobile MediaRecorder
- Status: PASS
- Objective: capture on mobile browsers without holding a long video in memory.
- Dependencies: W3 PASS.
- Implementation tasks: feature detection, camera/mic permissions, 10-30s fragment production, visible timer, lifecycle cleanup on stop/navigation/error, optional local full-copy path only when opted in.
- Relevant files/modules: capture JS/template, capture models, browser tests.
- Acceptance criteria: short bounded fragments emitted while recording continues; no whole-session/15-minute browser blob.
- Required tests: fragment cadence/state/IDs, start/timer/stop, MIME feature detection, synthetic mobile viewport.
- Validation commands: template JavaScript syntax check; `python -m py_compile tests/e2e/capture_new_recording.py`; synthetic Playwright `capture_new_recording.py`; regression `capture_dashboard.py`, `capture_crop.py`, `capture_chunking.py`, `capture_cancellation.py`.
- Expected artifacts: `capture_new_recording_report.json` and existing capture reports.
- Evidence: JS syntax `JS_OK`; test syntax `PY_OK`; diff check PASS. Synthetic Playwright W4 scenario 31/31 PASS. Regressions: capture dashboard 14/14, crop 5/5, chunking 10/10, cancellation 9/9. W5 removed the legacy per-fragment processing-chunk upload path.
- Recovery/fallback: feature-detect supported MediaRecorder MIME types; visible unsupported state with retry.

### W5 - Incremental upload fragments
- Status: PASS
- Objective: transfer short fragments incrementally and release acknowledged local bytes.
- Dependencies: W3, W4 PASS.
- Implementation tasks: stable fragment ID/idempotency key, bounded streaming endpoint, server digest/ACK, replay-safe duplicate response, browser ACK handling and progress state.
- Relevant files/modules: capture API/service/store, dashboard JS, integration and Playwright tests.
- Acceptance criteria: fragment N is ACKed while N+1 records; acknowledged temporary fragment is released; retry never duplicates it.
- Required tests: first upload, duplicate ID same/different bytes, ACK, interrupted POST and retry, browser ACK during capture, fragment ordering and no chunk creation.
- Validation commands: `.venv-validation\\Scripts\\python.exe -m pytest tests/test_live_capture_fragments.py tests/test_dashboard_capture_fragments_api.py tests/test_live_capture_streaming.py tests/test_live_capture_store.py tests/test_live_capture_models.py tests/test_dashboard_capture_api.py tests/test_dashboard_capture_transcript_api.py -q`; broader `pytest -q -k "dashboard or live_capture"`; JS syntax and Playwright capture-new-recording/chunking/cancellation journeys.
- Expected artifacts: `fragments.json`, fragment media, `capture_new_recording_report.json`, `capture_chunking_report.json`, `capture_cancellation_report.json`.
- Evidence: focused fragment/API suite 33 passed; prior selected regression suite 121 passed; broad dashboard/live-capture selection 326 passed, 685 deselected. Playwright `capture_new_recording.py` passed: 2+ durable ACKs while recording, ordered server fragments, 600s processing duration and no processing chunks; `capture_chunking.py` and `capture_cancellation.py` passed. JS `node --check` and Playwright `py_compile` passed. Same-ID identical replay ACKs once; differing bytes conflict; interrupted upload leaves no media, manifest or temp file.
- Recovery/fallback: retain unACKed local blob; retry same identity; never mark unACKed data uploaded.

### W6 - Server processing chunks
- Status: PASS
- Objective: map short fragments to server-side ~10-15 minute processing chunks.
- Dependencies: W5 PASS.
- Implementation tasks: configurable aggregation/finalization, duration/size thresholds, server-side concat/remux where required, boundary/final-chunk handling and mapping persistence.
- Relevant files/modules: live_capture models/service/store/pipeline, media utilities, API, integration tests.
- Acceptance criteria: browser holds no long blob; backend creates playable processing chunks while capture continues.
- Required tests: aggregation/order, final partial chunk, cross-chunk mapping and processing state.
- Validation commands: unit/API integration; synthetic ffmpeg media test.
- Expected artifacts: processing-chunk fixture and fragment map.
- Recovery/fallback: retain individually ACKed fragments on assembly failure; retry assembly without re-upload.
- Evidence: W6 unit/API/FFmpeg tests 25 passed; broad `pytest -q -k "capture or dashboard or live_capture"` 352 passed, 684 deselected. Synthetic Playwright `capture_processing_chunks.py` 17/17 PASS; chunk 0 finalized while recording, stop drained/finalized the tail, all 7 ACKed fragments mapped once, media present. W5 Playwright regressions `capture_new_recording`, `capture_chunking`, `capture_dashboard`, `capture_crop`, `capture_cancellation` passed. `py_compile` and inline JS syntax check passed. An added assertion verifies `recorded_at` is preserved from the first fragment through mapping and assembled chunk. Source fragments remain available.

### W25 - MOBILE/LAN ACCESS
- Status: PASS
- Objective: make Whisper reachable from a phone on the same Wi-Fi over HTTPS, with API, camera, capture, and fragment upload working from the LAN origin.
- Dependencies: W3, W4, W5, W6 PASS.
- Implementation tasks: bind the server to `0.0.0.0`; remove loopback-only settings validation; use same-origin relative API requests; configure HTTPS certificate whose SAN includes the LAN host; expose a clear phone URL and trust/setup instructions; tie capture status to server health; verify camera permission and fragment upload over HTTPS.
- Relevant files/modules: `dashboard.py`, `src/transcript_pipeline/settings.py`, dashboard health/capture UI, HTTPS launch/config scripts and docs, Playwright mobile-origin tests.
- Acceptance criteria: a second LAN client can load dashboard and API; UI reports ONLINE from backend health; HTTPS origin has camera permission; capture starts and uploads fragments; no application URL is hardcoded to loopback; server listens on all interfaces.
- Required tests: settings/bind unit tests; health and fragment API over advertised origin; synthetic Playwright HTTPS journey for ONLINE, camera preview, start/timer, fragment ACK, and stop.
- Validation commands: focused settings/API tests; inspect listening address; start HTTPS server on `0.0.0.0`; Playwright Chromium with synthetic camera/media over HTTPS; open advertised LAN endpoint from another local process.
- Expected artifacts: HTTPS certificate/config (private key excluded from Git), LAN setup guide, `mobile_lan_access_report.json`.
- Recovery/fallback: accept an explicit certificate path and host/SAN configuration; if a trusted device certificate cannot be provisioned here, validate HTTPS using a test CA and document the device trust installation step.
- Evidence: official W25 targeted gate passed; latest focused suite 55 passed, 2 skipped (host-level Norton TLS interception); settings/security/dashboard regressions 163 passed; dashboard API regressions 181 passed; broad filter 290 passed, 1 skipped. `mobile_lan_access_report.json` 16/16 PASS for HTTPS, backend ONLINE, LAN URLs, camera preview, synthetic recording, durable fragment ACKs, stop, mobile viewport and browser errors. Integration exercised `0.0.0.0`, HTTPS health/files and synthetic fragment upload through a LAN interface. Host check to active Wi-Fi URL `https://192.168.50.67:5001/api/health` returned 200 ONLINE. CA-to-server chain is cryptographically validated; live CA trust is skipped because Norton substitutes local TLS. Added private-client filtering and SAN-aware certificate regeneration on IP changes. Local config is enabled and private cert/key are in ignored `lan-access/`.

### W7 - Upload resilience and local buffer
- Status: PASS
- Objective: survive transient/offline connectivity without fragment loss or duplication.
- Dependencies: W5 PASS.
- Implementation tasks: IndexedDB pending-fragment queue, configurable storage ceiling, visible near/full warning, pause/retry/backoff, ACK cleanup and opt-in Save local copy.
- Relevant files/modules: dashboard JS, capture API/service, browser and unit tests.
- Acceptance criteria: reconnect resumes same IDs; acknowledged media is not resent; browser-persistent pending buffer is configurable, bounded, and visibly warns near/full; default Save local copy is OFF.
- Required tests: offline/reconnect, duplicate replay, buffer limit warning, default local-copy OFF.
- Validation commands: `.venv-validation\Scripts\python.exe -m pytest tests/test_dashboard_capture_offline_retry_api.py tests/test_lan_access.py tests/test_dashboard_lan_access.py -q`; `ZMI_BASE_URL=http://127.0.0.1:5088 .venv-validation\Scripts\python.exe tests/e2e/capture_offline_retry.py`.
- Expected artifacts: `artifacts/gates/capture_offline_retry_report.json`.
- Recovery/fallback: pause capture uploads and preserve pending IndexedDB data; provide export/retry path when quota is exhausted.
- Evidence: focused API/LAN tests 54 passed, 1 host TLS interception skip; offline/reconnect Playwright report 22/22 PASS with synthetic media, stable IDs, ACK cleanup, reload restore, 64 MiB default, user-configurable cap, visible near/full warning, and Save local copy default OFF. Browser report: `artifacts/gates/capture_offline_retry_report.json`.

### W8 - Cancellation
- Status: PENDING
- Objective: expose independent stop, cancel-upload, and cancel-processing behavior in the new UI.
- Dependencies: W3, W5, W6 PASS.
- Implementation tasks: idempotent fragment abort/rescind and cleanup; PROCESSING -> CANCEL_REQUESTED -> CANCELLED worker checks; preserve originals; retry/process again.
- Relevant files/modules: live_capture service/pipeline/API, dashboard UI, cancellation tests.
- Acceptance criteria: each operation has distinct UI/state and does not delete acknowledged originals.
- Required tests: repeated cancel, upload vs ACK race, queued/active processing, cancel vs complete race, retry.
- Validation commands: unit/API tests and Playwright for all three controls.
- Expected artifacts: cancellation state report.
- Recovery/fallback: leave confirmed media intact; reconcile stale upload state; retry only by explicit action.

### W9 - Crop/mask
- Status: PENDING
- Objective: make crop configuration reachable from New Recording and apply it to evidence.
- Dependencies: W3 PASS.
- Implementation tasks: responsive normalized selection, persistence, edit/clear and processor mapping.
- Relevant files/modules: crop model/processor, capture UI/API, tests.
- Acceptance criteria: region round-trips and is visible/editable in the expected flow; original stays intact.
- Required tests: normalized bounds, persisted selection, cropped synthetic frame Playwright.
- Validation commands: crop unit/API tests and Playwright.
- Expected artifacts: crop mapping/report.
- Recovery/fallback: full frame on invalid region with explicit warning.

### W10 - Continuous Playlist capture
- Status: PENDING
- Objective: record sequential external source videos with one continuous camera session.
- Dependencies: W3, W4, W5 PASS.
- Implementation tasks: mode selection; no manual stop/start between sources; distinct physical capture, processing and logical boundaries.
- Relevant files/modules: capture UI/JS, session domain, API, tests.
- Acceptance criteria: one capture session spans synthetic Session 1 -> Session 2 source transition.
- Required tests: continuous multi-title fake-source Playwright scenario.
- Validation commands: targeted state tests and Playwright playlist journey.
- Expected artifacts: synthetic session with multiple source markers.
- Recovery/fallback: continue physical capture and mark uncertain title transition for review.

### W11 - Automatic visual title detection
- Status: PENDING
- Objective: periodically detect source title metadata from displayed screen frames.
- Dependencies: W10 PASS.
- Implementation tasks: sample frames; OCR broad title/category/session/date/time patterns; confidence and provenance; handle OCR unavailable.
- Relevant files/modules: new/focused title detector in live_capture, existing OCR/media utilities, pipeline tests.
- Acceptance criteria: extracts title family examples without hardcoding one exact title; low confidence remains explicit.
- Required tests: synthetic title cards, date/session parsing, unknown/ambiguous card.
- Validation commands: title detector unit tests and synthetic media integration.
- Expected artifacts: OCR evidence fixture with confidence.
- Recovery/fallback: `NEEDS_TITLE_REVIEW`; never fabricate title/date.

### W12 - Multi-frame confirmation
- Status: PENDING
- Objective: require stable evidence across multiple samples before title confirmation.
- Dependencies: W11 PASS.
- Implementation tasks: candidate window, normalized title comparison, stability/confidence threshold and hysteresis against transient slides.
- Relevant files/modules: title detector/confirmation model and tests.
- Acceptance criteria: repeated Session 2 confirms; one-frame incidental text does not split; uncertain candidate is reviewable.
- Required tests: repeated, noisy, conflicting and low-confidence frame sequences.
- Validation commands: unit tests and fixture replay.
- Expected artifacts: deterministic confirmation results.
- Recovery/fallback: keep current logical video open and emit NEEDS_TITLE_REVIEW.

### W13 - Logical boundaries
- Status: PENDING
- Objective: create logical-video boundaries at confirmed title changes independent of physical chunks.
- Dependencies: W12 PASS.
- Implementation tasks: open/close logical records at detected time; support boundary inside processing chunk; preserve source timeline.
- Relevant files/modules: live_capture logical boundary service, tests.
- Acceptance criteria: Session 1->2 closes/opens once; incidental slides and duplicate frames do not split.
- Required tests: boundary state transitions and synthetic transition crossing chunk edge.
- Validation commands: unit/integration boundary tests.
- Expected artifacts: logical boundary manifest.
- Recovery/fallback: mark uncertain span for user review without losing physical capture.

### W14 - Logical-video and chunk mapping
- Status: PENDING
- Objective: persist mappings among capture session, upload fragments, processing chunks and logical videos.
- Dependencies: W5, W6, W13 PASS.
- Implementation tasks: versioned mapping schema, time ranges, fragment digests, transactional updates, migration/recovery and idempotency.
- Relevant files/modules: live_capture models/store/service, Dashboard APIs, integration tests.
- Acceptance criteria: logical video can span fragments/chunks and a chunk can contain multiple logical videos.
- Required tests: mapping roundtrip, restart recovery, split inside chunk, duplicate fragment.
- Validation commands: model/API integration tests.
- Expected artifacts: synthetic mapping manifest.
- Recovery/fallback: rebuild derived mapping from immutable fragment timeline; never delete source fragments.

### W15 - Playlist Review UI
- Status: PENDING
- Objective: let users inspect and correct detected logical videos.
- Dependencies: W3, W13, W14 PASS.
- Implementation tasks: display title/confidence/date; rename, correct recorded date, split, merge, confirm low-confidence items; protect original mapping.
- Relevant files/modules: Videos table, playlist review UI/API, logical-video service, Playwright tests.
- Acceptance criteria: Session 1/2 and unknown title appear; all review actions work and persist.
- Required tests: UI journey for confirm/rename/date/split/merge and low-confidence review.
- Validation commands: API tests and playlist Playwright.
- Expected artifacts: review report/screenshots.
- Recovery/fallback: user edits are auditable and reversible; never silently auto-confirm a low-confidence title.

### W16 - Audio-missing flow
- Status: PENDING
- Objective: preserve video processing without usable audio in the new flow.
- Dependencies: W4, W6 PASS.
- Implementation tasks: detect audio per fragment/processing chunk; expose AUDIO_MISSING / TRANSCRIPT_REQUIRED and later supply actions.
- Relevant files/modules: audio detector, models, capture UI/API, tests.
- Acceptance criteria: silent synthetic source remains valid and warning is clear in playlist/video UI.
- Required tests: silent media unit/API and Playwright warning.
- Validation commands: targeted tests and fake-device browser flow.
- Expected artifacts: silent fixture and report.
- Recovery/fallback: mark unknown if detector unavailable; never fail video record solely for absent audio.

### W17 - Late transcript
- Status: PENDING
- Objective: associate later transcript/audio with the right logical video/session without false sync.
- Dependencies: W14, W16 PASS.
- Implementation tasks: explicit association selector/API, loose alignment, state update and retries.
- Relevant files/modules: transcript model/API, review UI, tests.
- Acceptance criteria: later transcript clears requirement warning, retains provenance, and has no fabricated timestamps.
- Required tests: late association API and Playwright.
- Validation commands: unit/API tests and synthetic browser flow.
- Expected artifacts: transcript association report.
- Recovery/fallback: retain unassociated transcript and ask for user mapping; do not guess a logical video.

### W18 - Documentation pipeline integration
- Status: PENDING
- Objective: route confirmed logical videos through existing Whisper processing and Documentation V2.
- Dependencies: W6, W14, W15, W16, W17 PASS.
- Implementation tasks: present logical video as normal media with recorded_at; reuse processor, crop, transcript/audio evidence and idempotent docs generation.
- Relevant files/modules: `live_capture/integration.py`, transcription processor, documentation engine, Videos API/tests.
- Acceptance criteria: confirmed logical video appears in Videos and produces docs through existing pipeline; no duplicate pipeline.
- Required tests: synthetic end-to-end integration and UI listing.
- Validation commands: processor/docs tests and Playwright normal-video flow.
- Expected artifacts: generated docs from synthetic source only.
- Recovery/fallback: persist retryable pipeline status and source mapping; keep captured media.

### W19 - GC candidates
- Status: PENDING
- Objective: retain safe, advisory media lifecycle suggestions for physical and derived media.
- Dependencies: W14, W18 PASS.
- Implementation tasks: identify old+processed+documented+unused candidates; account for logical mapping references; explicit confirmed deletion only.
- Relevant files/modules: GC service/API/UI and tests.
- Acceptance criteria: active/referenced media excluded; UI never deletes automatically.
- Required tests: candidate logic, references, UI suggestion and explicit confirmation guard.
- Validation commands: unit/API tests and Playwright suggestion check.
- Expected artifacts: synthetic candidate report.
- Recovery/fallback: false negatives are safe; never broaden deletion automatically.

### W20 - Unit and integration matrix
- Status: PENDING
- Objective: complete automated validation of all required states and mappings.
- Dependencies: W5-W19 implementation stages PASS where relevant.
- Implementation tasks: fill gaps for fragment identity/idempotency, aggregation, detector confirmation, boundaries, cancellation, audio, GC and Date.
- Relevant files/modules: `tests/test_live_capture*`, `tests/integration/`, dashboard API tests.
- Acceptance criteria: each UNIT and INTEGRATION row below has current PASS evidence.
- Required tests: all unit/integration cases in Test Matrix; synthetic media only.
- Validation commands: targeted pytest then full pytest if W23 permits.
- Expected artifacts: pytest reports.
- Recovery/fallback: max two distinct root-cause repair attempts per failure; never weaken assertions.

### W21 - Playwright user journeys
- Status: PENDING
- Objective: prove capture and playlist journeys through the actual Whisper UI.
- Dependencies: W3-W19 PASS.
- Implementation tasks: fake camera, synthetic title source, fake connectivity, UI action/state assertions.
- Relevant files/modules: `tests/e2e/`, dashboard and capture modules.
- Acceptance criteria: every specified normal, playlist, low-confidence, cancellation, audio and newest-first journey passes.
- Required tests: full user journeys listed in Test Matrix.
- Validation commands: targeted Playwright scripts; no arbitrary waits.
- Expected artifacts: named JSON reports/screenshots.
- Recovery/fallback: inspect browser trace and app/API logs; repair root cause and rerun.

### W22 - Host E2E regression
- Status: PENDING
- Objective: revalidate dashboard critical path with completed capture UI and preserve projects/date flows.
- Dependencies: W2, W20, W21 PASS.
- Implementation tasks: run host harness; repair changed UI selectors/fixtures without dropping checks.
- Relevant files/modules: `scripts/gate_runner.py`, `scripts/e2e.py`, `tests/e2e/smoke_dashboard.py`.
- Acceptance criteria: host gate PASS and no browser errors/TargetClosedError.
- Required tests: full host E2E.
- Validation commands: `.venv-validation\Scripts\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: host report/log/latest gate.
- Recovery/fallback: two root-cause fixes maximum per failure; continue independent stages.

### W23 - Docker/heavy validation
- Status: PENDING
- Objective: run required full and Docker validation when repository policy/environment allow.
- Dependencies: W20, W22 PASS; RAM gate >6 GiB and review prerequisite.
- Implementation tasks: RAM-gated pytest/security/smoke/sonar and Docker build/E2E if configured.
- Relevant files/modules: `scripts/ram_gate.py`, `scripts/heavy_validation_runner.py`, `scripts/docker_gate.py`, compose config.
- Acceptance criteria: gates pass or only an evidenced external RAM/service blocker remains.
- Required tests: full pytest, security, smoke, Docker build and Docker E2E as applicable.
- Validation commands: RAM gate; heavy runner; Docker gate config/build/E2E.
- Expected artifacts: heavy summary and per-gate reports.
- Recovery/fallback: retry when measured RAM >6 GiB; do not bypass repository enforcement; independent implementation stages continue.
- Evidence: last measured 5.62 GiB; compose config passed; full heavy runner deferred all gates. Re-measure at final validation.

### W24 - Final readiness
- Status: PENDING
- Objective: verify complete UI acceptance, plan accuracy, commits, remote sync and clean tree.
- Dependencies: W20-W22 PASS; W23 PASS or justified ENV_BLOCKED.
- Implementation tasks: update evidence/statuses, verify Date and all feature journeys, commit plan+code, push branch, verify remote SHA and clean status.
- Relevant files/modules: this plan, code/tests, gate artifacts, Git branch.
- Acceptance criteria: all user-facing features pass via UI+Playwright; only permitted environment blocker remains; branch synchronized; no merge/deploy.
- Required tests: final targeted matrix and all applicable gates.
- Validation commands: `git diff --check`; targeted/full validation; `git status`; `git rev-parse HEAD`; `git ls-remote`.
- Expected artifacts: final gate reports and committed plan evidence.
- Recovery/fallback: do not claim PASS with an unrerun failure; report exact code vs environment blocker.

## Global Definition of Done

Live Capture is usable via Videos -> New Recording; same-Wi-Fi phone access works over HTTPS with camera and upload; mobile capture sends 10-30 second acknowledged fragments and bounded offline retry; server creates ~10-15 minute processing chunks; playlist detection confirms titles across frames and creates reviewable logical videos independent of physical boundaries; logical videos use existing Videos/Date/Docs pipeline; cancellation, crop, audio-missing, late transcript and advisory GC work. Every user-facing feature has a passing main-journal Playwright report. Required unit/integration/host gates pass; Docker/heavy gates pass or have a justified environment-only blocker. Plan, implementation and tests are committed and remote-synchronized; worktree clean. No deployment.

## Test Matrix

| Layer | Coverage | Stage | Evidence |
|---|---|---|---|
| UNIT | fragment states/idempotency, ACK/retry, buffer cap, aggregation, logical boundaries, OCR parsing/confidence/multiframe confirmation | W5-W14/W20 | PENDING |
| UNIT | cancellation/idempotency/races, audio missing, late transcript, GC candidates, recorded/created date and sorting | W8/W16-W20 | prior PASS evidence exists; revalidate against final schema |
| INTEGRATION/API | session, fragment upload/duplicate/interrupted retry, processing chunks, fragment/chunk/logical mappings, inside-chunk boundary | W5-W14/W20 | PENDING |
| INTEGRATION/API | cancellation, no-audio, late transcript, Docs V2, GC, videos sorting | W8/W16-W20 | prior domain/API reports; user-journey revalidation pending |
| PLAYWRIGHT | Videos -> New Recording, preview, modes, timer, fragment ACK/progress, stop | W3-W5/W21 | PENDING; prior modal tests do not cover expected entry/journey |
| MOBILE/LAN E2E | same-Wi-Fi HTTPS origin, ONLINE health, camera preview, recording, fragment upload | W25 | PENDING |
| PLAYWRIGHT | offline retry/buffer warning, local-copy OFF default, cancellation controls | W7-W8/W21 | PENDING |
| PLAYWRIGHT | crop, playlist Session1->Session2, low confidence, review rename/date/split/merge/confirm | W9-W15/W21 | PENDING |
| PLAYWRIGHT | missing audio, late transcript, newest-first Date, docs normal flow, GC suggestion | W16-W19/W21 | PENDING |
| HOST E2E | dashboard critical path, Projects, Videos Date sorting, no browser errors | W2/W22 | PASS previously; rerun after UI work |
| DOCKER/MEDIA | Docker config/build/E2E; synthetic video/audio/OCR title fixtures only | W11-W23 | config PASS previously; heavy gate deferred at 5.62 GiB; remeasure |

## Known Risks

- Mobile MediaRecorder timeslice output may be container fragments requiring safe server-side remux; ACK only after durable fragment storage.
- IndexedDB quota/eviction varies; buffer limit, warning, retry and explicit local-copy behavior must be visible.
- OCR/title slides vary; broad extraction and repeated evidence avoid exact-string coupling and false splits.
- Title change can occur inside a processing chunk; mappings must support ranges and user edits without mutating source bytes.
- Phone may be locked/backgrounded for hours; browser suspension is not guaranteed. Surface interrupted/recoverable status and never claim continuous capture while suspended.
- RAM heavy gate last measured 5.62 GiB (<6 GiB). Docker build/E2E remain gated; independent host/UI implementation continues.
- Existing capture modal controls are not proof of required Videos entry or playlist usability.
- LAN camera capture requires HTTPS and a phone-trusted certificate; untrusted self-signed TLS will not grant camera access.
- Norton Web/Mail Shield replaces locally served certificates; host trust checks are explicitly skipped there. The generated CA/server chain is validated offline; the phone must trust the CA once.

## Model / Executor Policy

Routine implementation must use configured Z.AI/GLM first, then OpenCode Go/DeepSeek Flash, then local Ollama/DeepSeek. Do not choose DeepSeek Pro for routine coding. GPT/Claude/Codex are not routine implementers when a configured approved worker is callable. Do not expose credentials. Before code work inspect current router/provider availability; if no approved executor is callable, record the evidence and use the lowest permitted available fallback. No nested agents unless the repository's approved GLM routing explicitly requires delegation.

## Progress Log

- 2026-10-15: New acceptance criteria reveal the prior Capture/Chunking/Live Capture PASS labels covered the old modal, not the expected `Videos -> New Recording` UI. Reopened W3-W21 pending user-journey evidence. Existing backend and tests remain foundations, not acceptance proof. Baseline HEAD/remote `e9e61be`, clean tree. W2 host E2E PASS; W23 currently RAM-blocked at last 5.62 GiB reading. Plan must be committed before implementation.
- 2026-10-15: W3 PASS. Added Videos -> New Recording entry and responsive capture shell with modes, crop, default-off Save local copy, timer, status, logical-video placeholder, and distinct actions. Synthetic Playwright journey passed 23/23; existing capture and cancellation journeys passed 16/16 and 9/9; Date unit tests 5/5. This verifies only W3 shell; mobile fragment capture and playlist features remain pending.
- 2026-10-15: W4 PASS for browser capture generation. MediaRecorder now emits 10-30s bounded units with 15s default, stable sequence IDs, MIME feature detection, bounded pending queue, stop/error cleanup and synthetic mobile Playwright coverage. 31/31 new checks plus existing capture/crop/chunking/cancellation regressions pass. W5 is IN_PROGRESS to add distinct fragment ACK/idempotency endpoints and remove the legacy coupling where each emitted short unit is treated as a processable chunk; W6 remains required for ~10-15-minute server aggregation.
- 2026-10-15: W5 PASS. Added separate durable fragment manifest/media and idempotent upload/list endpoints; browser releases bytes only on real ACK, retries stable IDs, and keeps session processing duration at 600s without creating a processing chunk per fragment. API/unit/browser verification passed (33 focused fragment tests, 326 dashboard/live-capture tests selected, synthetic Playwright capture/chunking/cancellation). W6 now IN_PROGRESS to assemble/map these fragments into server processing chunks.
- 2026-10-15: W6 PASS. Backend assembles ACKed short fragments into ~600-second playable chunks during capture and drains a partial tail on stop. Fragment-to-chunk mapping is durable and retryable. Focused W6 unit/API/FFmpeg tests 25 passed; broad capture/dashboard/live-capture selection 352 passed; W6 synthetic Playwright 17/17 and all W5 UI regressions passed. Added W25 MOBILE/LAN ACCESS as the next stage and marked IN_PROGRESS before implementation.
- 2026-10-15: W25 PASS. Added explicit LAN opt-in, `0.0.0.0` bind, local CA/server certificate with detected IP SANs, backend ONLINE indicator, LAN URL help, same-origin HTTPS health/capture/upload and phone trust guide. Focused suite 55 passed/2 skipped; synthetic mobile HTTPS Playwright 16/16; security/API regressions green. Norton Web/Mail Shield intercepts local TLS, so direct trust assertions skip with evidence; device CA install remains required. Active Wi-Fi URL is `https://192.168.50.67:5001/`. W7 is IN_PROGRESS.
- 2026-10-15: W7 PASS. IndexedDB persists each fragment before upload, retries the same stable ID after reconnect/reload, and removes it only after server ACK. Added configurable 0.05–4096 MB local pending limit (64 MB default), near/full warnings, capture backpressure, and verified Save local copy stays off by default without gallery/download writes. API/LAN tests: 54 passed, 1 host interception skip. Synthetic offline Playwright: 22/22 PASS. Initial test failures traced to duplicate synthetic test IDs, test helper cap overshoot, and unstable buffer-warning setup; corrected those root causes and reran the full browser journey successfully. W8 is next.

## Final Delivery Checklist

- [ ] W0-W25 statuses and evidence current
- [ ] Same-Wi-Fi phone opens HTTPS, reports ONLINE, completes camera capture and fragment upload
- [ ] Videos -> New Recording UI and main journeys pass Playwright
- [ ] Short upload fragments, ACK/idempotency, IndexedDB recovery and buffer warning pass
- [ ] Server processing chunks and four-way mapping pass
- [ ] Continuous playlist, title detection, multi-frame confirmation and review pass
- [ ] Cancellation, crop, audio-missing, late transcript, Docs V2, GC pass
- [ ] Date and backend sorting remain green
- [ ] Unit, integration, Playwright, host E2E pass
- [ ] Docker/heavy gates pass or justified environment blocker recorded
- [ ] Code and canonical plan committed; remote SHA equals HEAD
- [ ] Worktree clean; no merge/deploy
