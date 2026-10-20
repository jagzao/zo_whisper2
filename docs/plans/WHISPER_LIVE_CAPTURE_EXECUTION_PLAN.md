# Whisper Live Capture and Playlist Execution Plan

Canonical execution plan for `feat/zmi-documentation-synthesis-v2`. Continue this plan in place. Work only in this repository; no worktree, merge, or deployment. Update and commit evidence at stable checkpoints.

## Goal

Deliver a user-facing mobile-safe Live Capture flow at `Videos -> New Recording`, with short acknowledged upload fragments, bounded offline retry, server processing chunks, and Continuous Playlist capture. Detect and confirm title changes from multiple frames, map logical videos to physical fragments and processing chunks, expose review controls, and reuse Whisper's existing documentation pipeline. Documentation Synthesis V2 must be invokable separately from media reprocessing, reuse saved evidence, preserve versions, and provide traceable reviewable outputs. Preserve Date sorting, cancellation, missing-audio/late-transcript, crop, and advisory GC behavior.

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
- Bulk dashboard upload uses browser `File`/`FormData` and disk-backed server request streams; it must not materialize whole files in JavaScript or application RAM. Upload concurrency is independently configurable (default 4, hard maximum 6); media-processing concurrency remains separately configured.
- Documentation regeneration invokes the existing Documentation Synthesis V2 pipeline using persisted transcripts, OCR, frame mappings, and evidence. Media reprocessing remains a separate explicit operation. Version metadata and prior rendered artifacts are retained; repeated identical generation requests are idempotent.

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
- Implementation tasks: add Videos action, mandatory existing-project selector before title, project inheritance, responsive recording view, immediate same-stream mobile camera preview, Normal/Continuous Playlist modes, crop, optional Save local copy OFF, start/stop, visible timer/status, user-level capture/logical-video progress, and state-scoped cancellation. Never show raw chunk/fragment rows or synthetic/test sessions in normal UI. UAT follow-up: viewport-safe full-screen mobile layout, no horizontal overflow, stacked fields/actions, persistent accessible capture actions, and readable playlist results.
- Relevant files/modules: `dashboard/templates/dashboard.html`, `dashboard/app.py`, capture browser JS, `tests/e2e/`.
- Acceptance criteria: users can reach and operate capture from Videos; selected project is mandatory and inherited by session/fragments/chunks/logical videos/docs; on 390x844 there is no horizontal overflow, preview is live after permission and shares the recording stream, actions are accessible, playlist results are readable, and jobs list contains only user-level records.
- Required tests: desktop and mobile Playwright open Videos -> New Recording and verify controls, fake-camera preview, timer, start/stop, mobile geometry, sticky actions, playlist result readability, and no browser errors.
- Validation commands: `.venv-validation\\Scripts\\python.exe -m pytest tests/test_dashboard_date_column.py -q`; synthetic host Playwright `tests/e2e/capture_new_recording.py`, `tests/e2e/capture_mobile_layout.py`, and mobile viewport `tests/e2e/capture_playlist.py`; regression `tests/e2e/capture_dashboard.py` and `tests/e2e/capture_cancellation.py`.
- Expected artifacts: `capture_new_recording_report.json`, `capture_mobile_layout_report.json`, `capture_playlist_report.json`; existing capture and cancellation reports.
- Evidence: prior desktop New Recording flow remains green (23/23 checks). UAT mobile layout passed 8/8 Playwright checks at 390x844: document/modal width 390/388px with no horizontal overflow, preview visible by y=519px, stacked controls, 44px playlist actions, sticky Start and Stop visible at y=785px while scrolled, recording stopped, and no browser errors. Updated playlist OCR/review journey passed 18/18 at the same mobile viewport. Synthetic test data only. `git diff --check` PASS.
- Recovery/fallback: keep existing modal as shared implementation behind the Videos entry; do not duplicate capture state.

### W26 - User-level capture jobs, project ownership and mobile UAT
- Status: PASS
- Objective: close the reported production UI regressions without deleting legitimate historical media.
- Dependencies: W3, W5, W6, W8, W14, W15, W18, W21 PASS.
- Implementation tasks: investigate repeated `chunk-000000 FINALIZED` entries and classify source as synthetic, interrupted, duplicate, or historical; hide internal chunks/fragments and synthetic/test sessions from normal views; safely clean only proven synthetic test artifacts; scope cancellation to session/logical video and show actions only for cancellable user states; persist required `project_id` from session through fragments, processing chunks, logical videos and documentation; make preview startup explicit/error-reporting with playsinline/autoplay on the active recording stream.
- Relevant files/modules: dashboard template/API, `live_capture` models/store/service/pipeline, documentation provenance, dashboard and live-capture tests, mobile Playwright.
- Acceptance criteria: a phone UAT can open New Recording, select project, see live preview, record/stop, see user-level progress only, cancel the correct logical job, see no cancel on completed work, and verify playlist videos inherit project. No legitimate media is removed.
- Required tests: model/API project propagation and visibility filtering; cancellation state scoping and idempotency; preview failure and same-stream browser assertions; mobile Playwright viewport and capture journey; recorded real-device UAT procedure.
- Validation commands: focused live-capture/dashboard tests; `capture_mobile_layout.py`, `capture_new_recording.py`, `capture_playlist.py`, `capture_cancellation.py` at mobile viewport; `scripts/gate_runner.py e2e`.
- Expected artifacts: mobile user-level capture/cancellation Playwright report, diagnostic inventory report (counts/source classification only; no private media), and real-device UAT checklist.
- Evidence: project selection and propagation through session/fragments/processing mappings/logical videos/Docs V2 passed. Synthetic Playwright at 390x844: New Recording 51/51, layout 8/8, playlist 18/18, cancellation 11/11. Playlist rerun exposed concurrent manifest mutation (`PermissionError` on Windows `os.replace`); per-service `RLock` serializes playlist observation/review/listing, then the complete playlist journey passed with no browser/API errors. 288 focused unit/API/Date tests passed; host E2E passed. Inventory: 31 session manifests (17 finalized, 14 failed), 10 title-marked synthetic sessions, 0 explicit test flags, 21 ambiguous historical sessions. Repeated `chunk-000000` rows were first chunks in separate sessions, not duplicates within a session. No media was deleted; only explicit test sessions are hidden/eligible for confirmation-only cleanup. Physical phone unavailable; [mobile UAT checklist](../testing/live_capture_mobile_uat.md) documents device verification without claiming it was run.
- Recovery/fallback: preserve ambiguous historical records but filter internal states; only delete records positively tagged as synthetic test artifacts. If hardware camera cannot be tested in this environment, retain browser synthetic evidence and document exact on-device UAT steps without claiming device acceptance.

### W27 - Served build identity and multi-file upload
- Status: PASS
- Objective: ensure desktop and mobile browsers receive the current branch build and provide resilient multi-file upload from the real dashboard.
- Dependencies: W1 PASS; revalidate W3/W21/W22 as part of acceptance.
- Implementation tasks: embed the source revision in visible HTML and response headers; disable stale HTML caching and confirm no service worker/static bundle is masking current inline assets; support selecting/dropping at least three files, preserve each row's project selection, show a removable queue, upload with bounded concurrency, per-file cancel/retry/status and independent failures; update the running local/Docker services from this repository revision while preserving the existing data volume.
- Relevant files/modules: `dashboard/app.py`, `dashboard/templates/dashboard.html`, `Dockerfile`, `compose.yml`, upload API/tests, `tests/e2e/`, this plan.
- Acceptance criteria: HTTP(S) response build marker equals Git HEAD and remote HEAD; desktop and mobile Playwright sessions receive identical revision and current capture/project UI; upload input has `multiple`; selecting three synthetic media fixtures in one action displays all rows; queued removal, concurrent upload, per-file cancellation/retry/failure and selected project propagation work; actual service is restarted from this repository after commit.
- Required tests: upload API project propagation; desktop and 390x844 Playwright build identity and 3-file selection/queue; per-file isolation/cancel/retry; no stale cache/service-worker behavior; existing Live Capture and host E2E regressions.
- Validation commands: focused API/upload tests, browser tests against the actual served URLs on ports 5000 and 5001, `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`, Docker build/health where available, `git diff --check`, Git/remote revision check.
- Expected artifacts: `capture_multifile_upload_report.json`, served-build Playwright report, host E2E report and updated canonical plan.
- Recovery/fallback: preserve the existing data volume and do not remove user data; if Docker resource restrictions prevent rebuilding, keep the current-repo LAN server active and classify the desktop container as an environment/operations blocker only after recording evidence. Never claim the desktop and mobile origins match until browser reports prove the same revision.
- Evidence: after the final synced checkpoint, desktop `http://127.0.0.1:5000` and LAN HTTPS `https://192.168.50.67:5001` were rebuilt/restarted from this repo. Served-build Playwright passed both origins: visible/header/meta revision matches Git HEAD and remote, `no-store`, no service worker, same inline-JS hash, current capture/project UI, 4 synthetic files selected together, queue removal, multi-file drop, concurrency 2, per-file cancel/retry, project propagation, and no raw chunks/browser errors (`artifacts/gates/served-build/capture_multifile_upload_report.json`). Mobile viewport suite passed at 390x844 (`capture_mobile_layout_report.json`). First browser attempt exposed test-only setup/assertion issues (modal overlay remained visible; assertion expected `Uploaded` while UI says `OK`); corrected both and reran successfully. First host gate attempt had one `ERR_CONNECTION_RESET` while server logged HTML/API/logo 200; inspected report and reran `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`, passing in 26.77s (`artifacts/gates/latest.json`). Desktop originally served a container from a separate checkout and mobile a stale Python process; Docker was rebuilt from this repo while preserving the existing data bind, and the Python server restarted from this checkout. No service worker or bundled static JS was present.

### W28 - P0 scope reconciliation and baseline
- Status: PASS
- Objective: persist the added delivery scope in this canonical plan before implementation and reconcile prior PASS claims against current UI/code.
- Dependencies: W27 PASS.
- Implementation tasks: record current HEAD/remote/tree; audit capture UI/fragments/chunks/docs V2/upload transport and concurrency/video actions/states/metrics/tests/artifacts; define W29-W34 dependencies and acceptance.
- Relevant files/modules: this plan; `dashboard.html`; `dashboard/app.py`; `live_capture/`; `documentation/`; tests; gate artifacts.
- Acceptance criteria: this plan contains all P0.1/P0.2, upload concurrency/streaming, separate regenerate/reprocess, versioning, metrics, states, and test matrix; current gaps and HEAD/remote are recorded; update is committed before code changes.
- Required tests: none; source/plan consistency and `git diff --check`.
- Validation commands: Git status/head/remote; focused source/artifact inspection; `git diff --check`.
- Expected artifacts: committed plan update and baseline entry in Progress Log.
- Recovery/fallback: preserve history, append corrections in this file, and never use backend-only evidence to claim UI acceptance.
- Evidence: scope and W28-W34 stages committed in `ce52a56`; HEAD and remote matched, worktree clean before implementation. Audit found upload concurrency fixed at 2; UI's “Regenerate” invokes the legacy step renderer; Docs V2 generation exists separately, without a video-detail V2 action/history. Baseline and remaining acceptance are recorded above.

### W29 - Live Capture / transmission stability
- Status: PASS
- Objective: revalidate and repair the complete mobile capture journey against current code.
- Dependencies: W28 PASS.
- Implementation tasks: camera preview uses recording stream; timer/start/stop; 10-30s MediaRecorder fragments; durable incremental ACK; server 10-15 minute processing chunks; IndexedDB offline/reload retry; playlist/title confirmation/logical boundaries; project inheritance; cancel/retry; responsive controls; no chunks displayed.
- Relevant files/modules: `dashboard.html`; `dashboard/app.py`; `live_capture/{models,service,store,assembly,playlist,titles,pipeline}.py`; capture tests/artifacts.
- Acceptance criteria: project flows through session/fragments/chunks/logical videos; continuous capture spans title boundaries; multi-frame evidence confirms titles; ACK/retry is idempotent; camera/status/actions usable at 390x844; only user-level video/session rows appear.
- Required tests: focused live-capture/API tests; mobile Playwright camera/capture/offline/playlist/cancellation using synthetic media.
- Validation commands: focused `pytest`; `capture_mobile_layout.py`; `capture_new_recording.py`; `capture_chunking.py`; `capture_offline_retry.py`; `capture_playlist.py`; `capture_cancellation.py`.
- Expected artifacts: capture/offline/playlist/cancellation browser reports and focused test logs.
- Recovery/fallback: repair each root cause once, reassess and use one different repair if needed; document physical-device camera UAT as unperformed if hardware is unavailable.
- Evidence: focused live-capture/dashboard/Date unit+integration matrix passed 256 tests. Current served UI Playwright passed: mobile layout 8/8; New Recording 44/44 (same-stream preview, selected project, 15s fragments, ACKs while recording and stop drain); chunking 11/11; offline/IndexedDB retry 22/22; playlist/title review 18/18; cancellation 11/11. Session 1/2 confirmed from synthetic frames, logical boundary remained inside one processing chunk, and both videos inherited the project. Raw internal chunks stayed hidden. Reports are saved under `artifacts/gates/w29-live-capture/`; synthetic fixtures only. Physical phone hardware was not operated.

### W30 - Streamed multi-file upload concurrency
- Status: PASS
- Objective: configure bulk uploads at default concurrency 4 and maximum 6 without whole-file memory buffering.
- Dependencies: W28 PASS; retain W27 multiselect foundation.
- Implementation tasks: add validated configurable concurrency; clarify `Ready` as pending/ready-to-upload; show per-file Ready/Uploading/Processing/Completed/Failed; preserve per-file cancel/retry/remove/project_id; keep unique identity/idempotent retry; prove browser File and server request streams remain bounded before increasing concurrency.
- Relevant files/modules: `dashboard.html`; `dashboard/app.py`; settings/config; upload tests; `tests/e2e/capture_multifile_upload.py`.
- Acceptance criteria: default 4 active; configured 6 yields at most 6; six fixtures selected together; one failed/cancelled request does not block others; retry creates no duplicate destination; project_id is preserved; measured memory remains bounded for concurrent large synthetic fixtures; processing concurrency is unchanged.
- Required tests: config/unit tests; streamed API upload test; Playwright 6-file batch at 4 and 6; cancel/retry/failure/project tests; bounded-memory check.
- Validation commands: focused upload tests; `capture_multifile_upload.py`; synthetic memory probe; inline-JS syntax check.
- Expected artifacts: upload concurrency/API report, Playwright report, memory measurement.
- Recovery/fallback: if profiling shows buffering, retain concurrency 2 and fix/verify streaming first; do not relax memory assertions.
- Evidence: Settings/API tests cover default 4, configurable 1-6, upload-ID idempotency and project identity. Current HEAD Playwright ran six-file batches with maxActive 4 and configured 6, per-file failure/cancel/retry reused stable IDs, and browser build marker matched HEAD on desktop + HTTPS LAN. Six synthetic 24MiB WAV uploads at concurrency 6 peaked at +79.7MiB container memory (<300MiB bound); all uploaded fixtures were deleted. Browser sends native File via FormData; server `FileStorage.save()` uses bounded stream copies.
- Artifacts: `artifacts/gates/w30-w33-final/`.

### W31 - Documentation V2 regeneration vs media reprocessing
- Status: PASS
- Objective: expose separate video-detail actions for Documentation Synthesis V2 regeneration and full video reprocessing.
- Dependencies: W28 PASS; existing Docs V2 pipeline/evidence formats.
- Implementation tasks: rename detail actions; wire `Regenerate Documentation` to V2 from saved transcript/OCR/frame mapping/evidence; wire `Reprocess Video` to forced per-file media pipeline; expose user-level states/errors; reject duplicate in-flight generation.
- Relevant files/modules: dashboard detail modal/API; `documentation/regenerate_v2.py`; `documentation/pipeline_v2.py`; media-processing pipeline and Docs V2 tests.
- Acceptance criteria: both actions are distinct and invokable from video detail; docs-only regeneration does not invoke FFmpeg/Whisper/OCR/vision when evidence exists; reprocess explicitly runs media evidence generation; latest V2 output is visibly shown; no duplicate documentation stack.
- Required tests: unit/integration spies prohibit upstream media work in regeneration; V2 pipeline invocation; Playwright action separation/output.
- Validation commands: Docs V2 regenerate/grounding/real-flow tests; dashboard API tests; video-detail docs Playwright.
- Expected artifacts: regeneration/reprocess report and generated synthetic doc fixture.
- Recovery/fallback: retain legacy step-edit API for compatibility, but never label legacy regeneration as V2.
- Evidence: Docs V2 regenerate uses `regenerate_documentation_v2` with its no-upstream guard; media reprocess invokes `SimpleScanProcessor.process_file(force=True)` under a single media-processing lock. API tests verify saved-evidence prerequisites and forced per-file dispatch; Docs V2 no-transcription/FFmpeg/OCR/vision tests pass. Playwright video-detail test passes distinct action labels, V2 output and reprocess feedback.
- Artifacts: `artifacts/gates/w30-w33-final/documentation_detail_actions_report.json`.

### W32 - Documentation version history and idempotency
- Status: PASS
- Objective: persist documentation provenance/version metadata and safely preserve previous outputs.
- Dependencies: W31 PASS.
- Implementation tasks: store documentation_version, pipeline_version, generated_at, source_video_id/evidence references, status, previous-version relation; archive prior output; expose current/history/read-only selection; deduplicate retries and publish only complete good versions.
- Relevant files/modules: documentation writers/output store; `documentation/evidence.py`; dashboard docs API/modal; version tests.
- Acceptance criteria: changed evidence/pipeline produces a new version; identical retry is idempotent; old versions remain viewable/selectable; failed generation cannot replace last-good output; provenance references resolve.
- Required tests: version create/list/select/restore, identical request idempotency, failed generation preservation, provenance, Playwright current/previous version flow.
- Validation commands: Docs V2 version/regenerate tests; integration suite; video detail documentation Playwright.
- Expected artifacts: version manifest fixture and API/browser reports.
- Recovery/fallback: snapshot outputs atomically; if restoring risks evidence corruption, support read-only prior-version viewing first.
- Evidence: synthetic version tests verify provenance, generated time/pipeline/source refs, stable-input idempotency, changed-input version linkage, prior snapshot preservation, and rollback on generation failure. Dashboard API supports listing/selecting saved versions. Playwright views latest and previous V2 manuals from the detail modal.
- Artifacts: `artifacts/gates/w30-w33-final/documentation_detail_actions_report.json` and versioning tests.

### W33 - User-level states and duration metrics
- Status: PASS
- Objective: expose clear video/job states and record useful upload/media/docs/end-to-end timings.
- Dependencies: W29-W32 PASS.
- Implementation tasks: map states to READY, UPLOADING, QUEUED, PROCESSING_MEDIA, GENERATING_DOCUMENTATION, COMPLETED, FAILED, CANCEL_REQUESTED, CANCELLED; retain internal chunk hiding; persist upload, media, documentation and total durations in existing records; show concise state/timings in video detail/list.
- Relevant files/modules: `dashboard/app.py`, `dashboard/templates/dashboard.html`, `transcription/processor.py`, `pipeline_metrics.py`, docs version manifest.
- Acceptance criteria: transitions and actions are scoped to one logical video/job; no cancel on completed/finalized jobs; timing survives reload and upload/media concurrency remain separate.
- Required tests: state transition unit tests; timing persistence/API integration; Playwright state/action visibility.
- Validation commands: focused state/metrics tests; video detail docs Playwright; host dashboard smoke.
- Expected artifacts: state/timing integration report.
- Recovery/fallback: derive UI from persisted job/session state; keep metrics minimal, no second observability service.
- Evidence: focused 109-test unit/API matrix covers state mapping, duration persistence/total, Docs V2, uploads and reprocess dispatch. Playwright detail displays user state/timings; no internal chunks are visible. Cancellation and completed-action journeys pass.
- Artifacts: `artifacts/gates/w30-w33-final/`.

### W34 - P0 acceptance matrix and final readiness
- Status: PASS
- Objective: validate all requested P0 scope through UI/API/unit/host and applicable Docker gates; commit and sync final plan.
- Dependencies: W29-W33 PASS; W23 PASS or justified external ENV_BLOCKED.
- Implementation tasks: run required matrices, fix within two distinct root-cause attempts, update stage evidence, restart actual services and compare served revision with HEAD/remote.
- Relevant files/modules: changed source/tests, canonical plan, gate runner/artifacts, Docker gate.
- Acceptance criteria: P0 features usable in real UI; all Global Definition of Done items pass; remote equals HEAD and tree clean; no deployment.
- Required tests: unit/integration; capture mobile/playlist; six-file concurrency at 4/6; docs detail/version Playwright; host E2E; Docker/heavy gate.
- Validation commands: focused tests; `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`; Docker/heavy only if RAM gate permits; `git diff --check`; Git status/remote.
- Expected artifacts: final test reports, memory measurement, docs history report, plan evidence.
- Recovery/fallback: continue independent stages after failures; only genuine external constraints are ENV_BLOCKED; never accept fixed-but-not-rerun.

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
- Status: PASS
- Objective: expose independent stop, cancel-upload, and cancel-processing behavior in the new UI.
- Dependencies: W3, W5, W6 PASS.
- Implementation tasks: idempotent fragment abort/rescind and cleanup; PROCESSING -> CANCEL_REQUESTED -> CANCELLED worker checks; preserve originals; retry/process again.
- Relevant files/modules: live_capture service/pipeline/API, dashboard UI, cancellation tests.
- Acceptance criteria: each operation has distinct UI/state and does not delete acknowledged originals.
- Required tests: repeated cancel, upload vs ACK race, queued/active processing, cancel vs complete race, retry.
- Validation commands: unit/API tests and Playwright for all three controls.
- Expected artifacts: `artifacts/gates/capture_cancellation_report.json`.
- Recovery/fallback: leave confirmed media intact; reconcile stale upload state; retry only by explicit action.
- Evidence: cancellation unit/API suite 41 passed. Synthetic cancellation Playwright 9/9 PASS: upload button, AbortController abort with no durable fragment, retry availability, queued cancel/retry/delete, active `Cancelando` and final `CANCELLED`, no browser errors. Upload cancel status is retained while stalled so UI repaints cannot hide `UPLOAD_CANCELLED`. Original acknowledged media remains intact.

### W9 - Crop/mask
- Status: PASS
- Objective: make crop configuration reachable from New Recording and apply it to evidence.
- Dependencies: W3 PASS.
- Implementation tasks: responsive normalized selection, persistence, edit/clear and processor mapping.
- Relevant files/modules: crop model/processor, capture UI/API, tests.
- Acceptance criteria: region round-trips and is visible/editable in the expected flow; original stays intact.
- Required tests: normalized bounds, persisted selection, cropped synthetic frame Playwright.
- Validation commands: crop unit/API tests and Playwright.
- Expected artifacts: `artifacts/gates/capture_crop_report.json`.
- Recovery/fallback: full frame on invalid region with explicit warning.
- Evidence: crop model/API/integration tests 54 passed; synthetic UI Playwright passes selection, clear, persisted metadata round-trip, and no browser errors. The initial test tried crop selection before camera preview was live and missed the first gesture; it now waits for the synthetic camera to be ready, then validates the full UI journey: `capture_crop_report.json`.

### W10 - Continuous Playlist capture
- Status: PASS
- Objective: record sequential external source videos with one continuous camera session.
- Dependencies: W3, W4, W5 PASS.
- Implementation tasks: mode selection; no manual stop/start between sources; distinct physical capture, processing and logical boundaries.
- Relevant files/modules: capture UI/JS, session domain, API, tests.
- Acceptance criteria: Playlist mode is saved in the session manifest; one recording remains active while multiple short fragments are acknowledged, with no manual stop/start between source videos. Logical boundaries remain a later stage.
- Required tests: mode persistence model/API and continuous-fragment Playwright journey.
- Validation commands: targeted state tests and Playwright playlist journey.
- Expected artifacts: `artifacts/gates/capture_new_recording_report.json`.
- Recovery/fallback: continue physical capture and mark uncertain title transition for review.
- Evidence: model/API suite 57 passed; synthetic Playwright 39/39 PASS including playlist mode persisted and multiple fragments ACKed while the same session stays RECORDING. Source title detection/boundaries are validated in W11-W15.

### W11 - Automatic visual title detection
- Status: PASS
- Objective: periodically detect source title metadata from displayed screen frames.
- Dependencies: W10 PASS.
- Implementation tasks: sample frames; OCR broad title/category/session/date/time patterns; confidence and provenance; handle OCR unavailable.
- Relevant files/modules: new/focused title detector in live_capture, existing OCR/media utilities, pipeline tests.
- Acceptance criteria: extracts title family examples without hardcoding one exact title; low confidence remains explicit.
- Required tests: synthetic title cards, date/session parsing, unknown/ambiguous card.
- Validation commands: title detector unit tests and synthetic media integration.
- Expected artifacts: OCR evidence fixture with confidence.
- Recovery/fallback: `NEEDS_TITLE_REVIEW`; never fabricate title/date.
- Evidence: configured Tesseract executable is honored; crop bounds are applied to sampled frames. Title/API/playlist unit tests 50 passed; actual synthetic camera OCR Playwright 11/11 passed, including Session 1/2 and unknown review.

### W12 - Multi-frame confirmation
- Status: PASS
- Objective: require stable evidence across multiple samples before title confirmation.
- Dependencies: W11 PASS.
- Implementation tasks: candidate window, normalized title comparison, stability/confidence threshold and hysteresis against transient slides.
- Relevant files/modules: title detector/confirmation model and tests.
- Acceptance criteria: repeated Session 2 confirms; one-frame incidental text does not split; uncertain candidate is reviewable.
- Required tests: repeated, noisy, conflicting and low-confidence frame sequences.
- Validation commands: unit tests and fixture replay.
- Expected artifacts: deterministic confirmation results.
- Recovery/fallback: keep current logical video open and emit NEEDS_TITLE_REVIEW.
- Evidence: 50 title/playlist/API tests passed; synthetic Playwright required repeated matching Session 1/2 frames and withheld low-confidence titles for review; 11/11 checks passed.

### W13 - Logical boundaries
- Status: PASS
- Objective: create logical-video boundaries at confirmed title changes independent of physical chunks.
- Dependencies: W12 PASS.
- Implementation tasks: open/close logical records at detected time; support boundary inside processing chunk; preserve source timeline.
- Relevant files/modules: live_capture logical boundary service, tests.
- Acceptance criteria: Session 1->2 closes/opens once; incidental slides and duplicate frames do not split.
- Required tests: boundary state transitions and synthetic transition crossing chunk edge.
- Validation commands: unit/integration boundary tests.
- Expected artifacts: logical boundary manifest.
- Recovery/fallback: mark uncertain span for user review without losing physical capture.
- Evidence: synthetic playlist Playwright confirmed Session 1->2 at the first matching frame offset while both logical records map to one unchanged physical processing chunk; 11/11 passed.

### W14 - Logical-video and chunk mapping
- Status: PASS
- Objective: persist mappings among capture session, upload fragments, processing chunks and logical videos.
- Dependencies: W5, W6, W13 PASS.
- Implementation tasks: versioned mapping schema, time ranges, fragment digests, transactional updates, migration/recovery and idempotency.
- Relevant files/modules: live_capture models/store/service, Dashboard APIs, integration tests.
- Acceptance criteria: logical video can span fragments/chunks and a chunk can contain multiple logical videos.
- Required tests: mapping roundtrip, restart recovery, split inside chunk, duplicate fragment.
- Validation commands: model/API integration tests.
- Expected artifacts: synthetic mapping manifest.
- Recovery/fallback: rebuild derived mapping from immutable fragment timeline; never delete source fragments.
- Evidence: persisted playlist restart/mapping tests and actual API assertions verified both logical videos reference the same fragment and processing chunk for an intra-chunk boundary; 50 title/playlist/API tests passed.

### W15 - Playlist Review UI
- Status: PASS
- Objective: let users inspect and correct detected logical videos.
- Dependencies: W3, W13, W14 PASS.
- Implementation tasks: display title/confidence/date; rename, correct recorded date, split, merge, confirm low-confidence items; protect original mapping.
- Relevant files/modules: Videos table, playlist review UI/API, logical-video service, Playwright tests.
- Acceptance criteria: Session 1/2 and unknown title appear; all review actions work and persist.
- Required tests: UI journey for confirm/rename/date/split/merge and low-confidence review.
- Validation commands: API tests and playlist Playwright.
- Expected artifacts: review report/screenshots.
- Recovery/fallback: user edits are auditable and reversible; never silently auto-confirm a low-confidence title.
- Evidence: actual UI Playwright renamed a title, corrected displayed date, split, merged, and explicitly confirmed the low-confidence candidate; 11/11 passed with no browser errors.

### W16 - Audio-missing flow
- Status: PASS
- Objective: preserve video processing without usable audio in the new flow.
- Dependencies: W4, W6 PASS.
- Implementation tasks: detect audio per fragment/processing chunk; expose AUDIO_MISSING / TRANSCRIPT_REQUIRED and later supply actions.
- Relevant files/modules: audio detector, models, capture UI/API, tests.
- Acceptance criteria: silent synthetic source remains valid and warning is clear in playlist/video UI.
- Required tests: silent media unit/API and Playwright warning.
- Validation commands: targeted tests and fake-device browser flow.
- Expected artifacts: silent fixture and report.
- Recovery/fallback: mark unknown if detector unavailable; never fail video record solely for absent audio.
- Evidence: silent synthetic capture finalized successfully with AUDIO_MISSING / TRANSCRIPT_REQUIRED; API/unit audio suite included in 96 passing tests; UI warning journey passed in `capture_dashboard.py`.

### W17 - Late transcript
- Status: PASS
- Objective: associate later transcript/audio with the right logical video/session without false sync.
- Dependencies: W14, W16 PASS.
- Implementation tasks: explicit association selector/API, loose alignment, state update and retries.
- Relevant files/modules: transcript model/API, review UI, tests.
- Acceptance criteria: later transcript clears requirement warning, retains provenance, and has no fabricated timestamps.
- Required tests: late association API and Playwright.
- Validation commands: unit/API tests and synthetic browser flow.
- Expected artifacts: transcript association report.
- Recovery/fallback: retain unassociated transcript and ask for user mapping; do not guess a logical video.
- Evidence: synthetic late transcript associated to the capture session with `alignment=loose`, warning cleared, and provenance persisted; dashboard Playwright passed; audio/transcript/docs focused tests included in 96 passes.

### W18 - Documentation pipeline integration
- Status: PASS
- Objective: route confirmed logical videos through existing Whisper processing and Documentation V2.
- Dependencies: W6, W14, W15, W16, W17 PASS.
- Implementation tasks: present logical video as normal media with recorded_at; reuse processor, crop, transcript/audio evidence and idempotent docs generation.
- Relevant files/modules: `live_capture/integration.py`, transcription processor, documentation engine, Videos API/tests.
- Acceptance criteria: confirmed logical video appears in Videos and produces docs through existing pipeline; no duplicate pipeline.
- Required tests: synthetic end-to-end integration and UI listing.
- Validation commands: processor/docs tests and Playwright normal-video flow.
- Expected artifacts: generated docs from synthetic source only.
- Recovery/fallback: persist retryable pipeline status and source mapping; keep captured media.
- Evidence: logical videos are exposed as read-only normal Videos entries backed by their mapped processed chunks; existing Generate Documentation action routes the chunk through Whisper. The existing media processor's capture context now carries confirmed logical title/date/confidence/ranges into Docs V2 provenance. Synthetic integration tests passed; Playlist UI checked both rows, documentation action and no destructive shared-chunk action.

### W19 - GC candidates
- Status: PASS
- Objective: retain safe, advisory media lifecycle suggestions for physical and derived media.
- Dependencies: W14, W18 PASS.
- Implementation tasks: identify old+processed+documented+unused candidates; account for logical mapping references; explicit confirmed deletion only.
- Relevant files/modules: GC service/API/UI and tests.
- Acceptance criteria: active/referenced media excluded; UI never deletes automatically.
- Required tests: candidate logic, references, UI suggestion and explicit confirmation guard.
- Validation commands: unit/API tests and Playwright suggestion check.
- Expected artifacts: synthetic candidate report.
- Recovery/fallback: false negatives are safe; never broaden deletion automatically.
- Evidence: candidate logic tests cover old+processed+documented eligibility, missing-doc exclusion, references and explicit confirmation; synthetic Playwright verified the cleanup review control, surfaced safe empty-state, no automatic-delete notice/action, and no browser errors.

### W20 - Unit and integration matrix
- Status: PASS
- Objective: complete automated validation of all required states and mappings.
- Dependencies: W5-W19 implementation stages PASS where relevant.
- Implementation tasks: fill gaps for fragment identity/idempotency, aggregation, detector confirmation, boundaries, cancellation, audio, GC and Date.
- Relevant files/modules: `tests/test_live_capture*`, `tests/integration/`, dashboard API tests.
- Acceptance criteria: each UNIT and INTEGRATION row below has current PASS evidence.
- Required tests: all unit/integration cases in Test Matrix; synthetic media only.
- Validation commands: targeted pytest then full pytest if W23 permits.
- Expected artifacts: pytest reports.
- Recovery/fallback: max two distinct root-cause repair attempts per failure; never weaken assertions.
- Evidence: final live-capture/dashboard API/Date matrix 281 passed; audio, late transcript, docs integration and GC matrix 96 passed. Synthetic OCR/video/audio fixtures only; no private media used.

### W21 - Playwright user journeys
- Status: PASS
- Objective: prove capture and playlist journeys through the actual Whisper UI.
- Dependencies: W3-W19 PASS.
- Implementation tasks: fake camera, synthetic title source, fake connectivity, UI action/state assertions, 390x844 modal/playlist readability checks.
- Relevant files/modules: `tests/e2e/`, dashboard and capture modules.
- Acceptance criteria: every specified normal, playlist, low-confidence, cancellation, audio and newest-first journey passes.
- Required tests: full user journeys listed in Test Matrix.
- Validation commands: targeted Playwright scripts; no arbitrary waits.
- Expected artifacts: named JSON reports/screenshots.
- Recovery/fallback: inspect browser trace and app/API logs; repair root cause and rerun.
- Evidence: mobile New Recording journey passed 51/51, layout 8/8, playlist/OCR/Videos/project inheritance 18/18, and cancellation 11/11 at 390x844. Preview used the active recording stream with autoplay/playsinline; no raw chunk rows or cancel actions for completed items; no browser errors. Synthetic media only.

### W22 - Host E2E regression
- Status: PASS
- Objective: revalidate dashboard critical path with completed capture UI and preserve projects/date flows.
- Dependencies: W2, W20, W21 PASS.
- Implementation tasks: run host harness; repair changed UI selectors/fixtures without dropping checks.
- Relevant files/modules: `scripts/gate_runner.py`, `scripts/e2e.py`, `tests/e2e/smoke_dashboard.py`.
- Acceptance criteria: host gate PASS and no browser errors/TargetClosedError.
- Required tests: full host E2E.
- Validation commands: `.venv-validation\Scripts\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: host report/log/latest gate.
- Recovery/fallback: two root-cause fixes maximum per failure; continue independent stages.
- Evidence: final `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e` PASS in 30.53s on commit `c763d72`; report `artifacts/gates/latest.json`; no TargetClosedError.

### W23 - Docker/heavy validation
- Status: BLOCKED
- Objective: run required full and Docker validation when repository policy/environment allow.
- Dependencies: W20, W22 PASS; RAM gate >6 GiB and review prerequisite.
- Implementation tasks: RAM-gated pytest/security/smoke/sonar and Docker build/E2E if configured; keep local validation environments outside the Docker build context and run synthetic fixture seeders as the dashboard UID.
- Relevant files/modules: `scripts/ram_gate.py`, `scripts/heavy_validation_runner.py`, `scripts/docker_gate.py`, compose config.
- Acceptance criteria: gates pass or only an evidenced external RAM/service blocker remains.
- Required tests: full pytest, security, smoke, Docker build and Docker E2E as applicable.
- Validation commands: RAM gate; heavy runner; Docker gate config/build/E2E.
- Expected artifacts: heavy summary and per-gate reports.
- Recovery/fallback: retry when measured RAM >6 GiB; do not bypass repository enforcement; independent implementation stages continue.
- Evidence / blocker: an earlier aggregate run with 6.41 GiB passed pytest, security, smoke, host E2E and Docker build. After fixing its Docker E2E failures (seed/executor UID 10001, optional non-writable report mirror, and missing packaged `/static/logo.png`), the standalone Docker E2E passed in 266.11s (`artifacts/gates/build-local/docker-docker-e2e.json`); focused harness/gate tests passed 67/67. Latest aggregate retry records `DEFERRED_LOW_RAM` at 4.99 GiB, below the enforced 6.0 GiB threshold, so no heavy gates ran. This is an external resource constraint; do not override the repo RAM gate. Sonar/Jenkins/soak are not configured.
- Latest reevaluation: `scripts/ram_gate.py` reports 3.56 GiB available vs the enforced >6.0 GiB threshold; required aggregate/Docker heavy gate was therefore not run. Current Whisper runtime image rebuilt successfully from the repository and passed served-build/API/Playwright checks. Previous standalone Docker E2E evidence remains valid for its earlier revision, not claimed as current-revision Docker E2E.
- Recovery/fallback evidence: each configured failed component was rerun independently after its fix and passed; aggregate-only rerun must wait until >6.0 GiB is available.

### W24 - Final readiness
- Status: PASS
- Objective: verify complete UI acceptance, plan accuracy, commits, remote sync and clean tree.
- Dependencies: W20-W22 PASS; W23 PASS or justified ENV_BLOCKED.
- Implementation tasks: update evidence/statuses, verify Date and all feature journeys, commit plan+code, push branch, verify remote SHA and clean status.
- Relevant files/modules: this plan, code/tests, gate artifacts, Git branch.
- Acceptance criteria: all user-facing features pass via UI+Playwright; only permitted environment blocker remains; branch synchronized; no merge/deploy.
- Required tests: final targeted matrix and all applicable gates.
- Validation commands: `git diff --check`; targeted/full validation; `git status`; `git rev-parse HEAD`; `git ls-remote`.
- Expected artifacts: final gate reports and committed plan evidence.
- Recovery/fallback: do not claim PASS with an unrerun failure; report exact code vs environment blocker.
- Evidence: 383 focused Docs V2/live-capture/settings/security tests pass; six-file Playwright passed at 4 and configured 6; 6x24MiB streamed upload memory delta +79.7MiB; video detail actions/history/timing passed; capture/mobile/playlist/cancellation browser journeys passed. Final Host E2E PASS in 30.53s. Docker runtime image rebuilt successfully, but aggregate/heavy Docker gate is ENV_BLOCKED by 3.56 GiB available RAM against >6.0 GiB repository policy. No private media was used; all synthetic upload fixtures were deleted. Final plan/code checkpoint will be committed/pushed, then served-build marker verified against it.

## Global Definition of Done

Live Capture is usable via Videos -> New Recording; same-Wi-Fi phone access works over HTTPS with camera and upload; mobile capture sends 10-30 second acknowledged fragments and bounded offline retry; server creates ~10-15 minute processing chunks; playlist detection confirms titles across frames and creates reviewable logical videos independent of physical boundaries; logical videos use existing Videos/Date/Docs pipeline; cancellation, crop, audio-missing, late transcript and advisory GC work. Bulk upload supports 4 by default / 6 maximum without whole-file RAM buffering. Video detail exposes distinct Regenerate Documentation (Docs V2 from saved evidence) and Reprocess Video actions. Documentation versions preserve prior outputs and provenance, repeated generation is idempotent, and current/previous versions are viewable. User-level states and upload/media/docs/total timings persist. Every user-facing feature has a passing real-UI Playwright report. Required unit/integration/host gates pass; Docker/heavy gates pass or have a justified environment-only blocker. Plan, implementation and tests are committed and remote-synchronized; worktree clean. No deployment.

## Test Matrix

| Layer | Coverage | Stage | Evidence |
|---|---|---|---|
| UNIT | fragment states/idempotency, ACK/retry, buffer cap, aggregation, logical boundaries, OCR parsing/confidence/multiframe confirmation | W5-W14/W20 | PASS; 279 capture/API/Date tests |
| UNIT | cancellation/idempotency/races, audio missing, late transcript, GC candidates, recorded/created date and sorting | W8/W16-W20 | PASS; 96 audio/transcript/docs/GC/Date tests |
| INTEGRATION/API | session, fragment upload/duplicate/interrupted retry, processing chunks, fragment/chunk/logical mappings, inside-chunk boundary | W5-W14/W20 | PASS; focused live capture/API matrix |
| INTEGRATION/API | cancellation, no-audio, late transcript, Docs V2, GC, videos sorting | W8/W16-W20 | PASS; logical title provenance and Videos listing integration added |
| PLAYWRIGHT | Videos -> New Recording, preview, modes, timer, fragment ACK/progress, stop | W3-W5/W21 | PASS; 51/51 capture checks and 8/8 mobile layout checks at 390x844 |
| MOBILE/LAN E2E | same-Wi-Fi HTTPS origin, ONLINE health, camera preview, recording, fragment upload | W25 | PASS; 16/16 previously, local CA trust required on phone |
| PLAYWRIGHT | offline retry/buffer warning, local-copy OFF default, cancellation controls | W7-W8/W21 | PASS; offline/cancellation synthetic journeys |
| UNIT/INTEGRATION | upload concurrency default/max, bounded streaming memory, unique retry/idempotency, project retention, cancel one while others continue | W30 | PASS; 109 focused tests plus 6x24MiB memory probe |
| UNIT/INTEGRATION | documentation regeneration idempotency, no media reprocessing, versions/provenance/last-good preservation | W31-W32 | PASS; 109-test focused matrix |
| UNIT/INTEGRATION | video state transitions and upload/media/docs/end-to-end timing persistence | W33 | PASS; state/API/metric tests |
| PLAYWRIGHT | six-file multiselect; default 4/configured 6 active; per-file cancel/retry; UI state and project_id | W30/W34 | PASS; default 4/configured 6 served-build journeys |
| PLAYWRIGHT | detail: Regenerate Documentation vs Reprocess Video; latest V2 output/current/history and prior-version preservation | W31-W34 | PASS; six synthetic detail checks |
| PLAYWRIGHT | crop, playlist Session1->Session2, low confidence, review rename/date/split/merge/confirm | W9-W15/W21 | PASS; crop 5/5, playlist 18/18 after serialized manifest mutation fix |
| PLAYWRIGHT | missing audio, late transcript, newest-first Date, docs normal flow, GC suggestion | W16-W19/W21 | PASS; audio/transcript, logical Videos documentation action, GC review UI and Date sort exercised |
| HOST E2E | dashboard critical path, Projects, Videos Date sorting, no browser errors | W2/W22 | IN_PROGRESS; final rerun required at current HEAD |
| UNIT/INTEGRATION | Run Full queueing, shared token, LAN authorization, worker timezone caps, atomic claims, hourly scans, recovery and cancellation | W35-W36 | PASS; 131 focused dashboard/worker/security tests |
| PLAYWRIGHT | Run Full button, invalid-token rejection, useful error, worker RUNNING/pending/active/limit/scan visibility on desktop and LAN | W35-W36 | PASS; 10/10 synthetic checks against isolated data root |
| DOCKER/MEDIA | Docker config/build/E2E; synthetic video/audio/OCR title fixtures only | W11-W23 | Current image build PASS; required heavy E2E ENV_BLOCKED at 3.56GiB (<6.0GiB); earlier standalone Docker E2E passed on its earlier revision |

## Known Risks

- Mobile MediaRecorder timeslice output may be container fragments requiring safe server-side remux; ACK only after durable fragment storage.
- IndexedDB quota/eviction varies; buffer limit, warning, retry and explicit local-copy behavior must be visible.
- OCR/title slides vary; broad extraction and repeated evidence avoid exact-string coupling and false splits.
- Title change can occur inside a processing chunk; mappings must support ranges and user edits without mutating source bytes.
- Phone may be locked/backgrounded for hours; browser suspension is not guaranteed. Surface interrupted/recoverable status and never claim continuous capture while suspended.
- Heavy gate requires >6 GiB RAM; final run measured 6.41 GiB and completed.
- Existing capture modal controls are not proof of required Videos entry or playlist usability.
- LAN camera capture requires HTTPS and a phone-trusted certificate; untrusted self-signed TLS will not grant camera access.
- Norton Web/Mail Shield replaces locally served certificates; host trust checks are explicitly skipped there. The generated CA/server chain is validated offline; the phone must trust the CA once.
- Concurrent browser uploads are bounded by configuration; verify Werkzeug disk-spooling and measured memory before raising the current limit.
- Documentation V2 currently writes stable output paths; version archives must be atomic and must keep the last-good current output if synthesis fails.

## Model / Executor Policy

Routine implementation must use configured Z.AI/GLM first, then OpenCode Go/DeepSeek Flash, then local Ollama/DeepSeek. Do not choose DeepSeek Pro for routine coding. GPT/Claude/Codex are not routine implementers when a configured approved worker is callable. At baseline, `opencode models` exposed `opencode-go/glm-5.3-flash`; use that GLM route for routine code. Do not expose credentials. If GLM invocation fails, record only the failure class and use the stated fallback. No nested agents unless the repository's approved GLM routing explicitly requires delegation.

## Progress Log

- 2026-10-15: New acceptance criteria reveal the prior Capture/Chunking/Live Capture PASS labels covered the old modal, not the expected `Videos -> New Recording` UI. Reopened W3-W21 pending user-journey evidence. Existing backend and tests remain foundations, not acceptance proof. Baseline HEAD/remote `e9e61be`, clean tree. W2 host E2E PASS; W23 currently RAM-blocked at last 5.62 GiB reading. Plan must be committed before implementation.
- 2026-10-15: W3 PASS. Added Videos -> New Recording entry and responsive capture shell with modes, crop, default-off Save local copy, timer, status, logical-video placeholder, and distinct actions. Synthetic Playwright journey passed 23/23; existing capture and cancellation journeys passed 16/16 and 9/9; Date unit tests 5/5. This verifies only W3 shell; mobile fragment capture and playlist features remain pending.
- 2026-10-15: W4 PASS for browser capture generation. MediaRecorder now emits 10-30s bounded units with 15s default, stable sequence IDs, MIME feature detection, bounded pending queue, stop/error cleanup and synthetic mobile Playwright coverage. 31/31 new checks plus existing capture/crop/chunking/cancellation regressions pass. W5 is IN_PROGRESS to add distinct fragment ACK/idempotency endpoints and remove the legacy coupling where each emitted short unit is treated as a processable chunk; W6 remains required for ~10-15-minute server aggregation.
- 2026-10-15: W5 PASS. Added separate durable fragment manifest/media and idempotent upload/list endpoints; browser releases bytes only on real ACK, retries stable IDs, and keeps session processing duration at 600s without creating a processing chunk per fragment. API/unit/browser verification passed (33 focused fragment tests, 326 dashboard/live-capture tests selected, synthetic Playwright capture/chunking/cancellation). W6 now IN_PROGRESS to assemble/map these fragments into server processing chunks.
- 2026-10-15: W6 PASS. Backend assembles ACKed short fragments into ~600-second playable chunks during capture and drains a partial tail on stop. Fragment-to-chunk mapping is durable and retryable. Focused W6 unit/API/FFmpeg tests 25 passed; broad capture/dashboard/live-capture selection 352 passed; W6 synthetic Playwright 17/17 and all W5 UI regressions passed. Added W25 MOBILE/LAN ACCESS as the next stage and marked IN_PROGRESS before implementation.
- 2026-10-15: W25 PASS. Added explicit LAN opt-in, `0.0.0.0` bind, local CA/server certificate with detected IP SANs, backend ONLINE indicator, LAN URL help, same-origin HTTPS health/capture/upload and phone trust guide. Focused suite 55 passed/2 skipped; synthetic mobile HTTPS Playwright 16/16; security/API regressions green. Norton Web/Mail Shield intercepts local TLS, so direct trust assertions skip with evidence; device CA install remains required. Active Wi-Fi URL is `https://192.168.50.67:5001/`. W7 is IN_PROGRESS.
- 2026-10-15: W7 PASS. IndexedDB persists each fragment before upload, retries the same stable ID after reconnect/reload, and removes it only after server ACK. Added configurable 0.05–4096 MB local pending limit (64 MB default), near/full warnings, capture backpressure, and verified Save local copy stays off by default without gallery/download writes. API/LAN tests: 54 passed, 1 host interception skip. Synthetic offline Playwright: 22/22 PASS. Initial test failures traced to duplicate synthetic test IDs, test helper cap overshoot, and unstable buffer-warning setup; corrected those root causes and reran the full browser journey successfully. W8 is next.
- 2026-10-15: W8 PASS. Kept upload cancellation visibly `UPLOAD_CANCELLED` through stalled-state repaints. Unit/API cancellation suite 41 passed; synthetic Playwright 9/9 passed for real browser abort/no durable partial, retry, queued cancel/retry/delete, active Cancelando/CANCELLED, and no browser errors. The first browser run found the upload cancellation message was cleared during a state repaint; fixed and reran the complete scenario. W9 is next.
- 2026-10-15: W9 PASS. Crop/mask is selectable over the live camera preview, can be cleared, persists in capture metadata, and passes into existing processing integration. Focused crop/API/pipeline tests 54 passed; synthetic Playwright 5/5. Updated the E2E to wait for an active synthetic preview before using the crop surface; rerun passed. W10 is next.
- 2026-10-15: W10 PASS. Persisted `captureMode` (`normal`/`playlist`) through session API/domain and wired the live UI mode into session creation. One continuous synthetic playlist session stayed Recording through three fragment ACKs. Model/API 57 passed; New Recording Playwright 39/39. W11 is IN_PROGRESS for title recognition.
- 2026-10-15: W11-W15 PASS after correcting W11's erroneous BLOCKED classification. Root cause was missing completion evidence/status reconciliation, not an external dependency. Tesseract honors `TESSERACT_CMD`; OCR samples respect selected crop; session refresh no longer clears playlist review rows. Title/playlist/API suite 50 passed; actual synthetic camera OCR/review Playwright 11/11 passed. Host E2E passed in 31.29s.
- 2026-10-15: W16-W17 PASS. Silent synthetic capture completes and shows AUDIO_MISSING / TRANSCRIPT_REQUIRED; later transcript persists with loose alignment and clears requirement. Audio/transcript/docs/GC focused tests 96 passed; capture dashboard Playwright passed.
- 2026-10-15: W18-W19 PASS. Confirmed logical playlist videos now appear as read-only entries in Videos, map to the same physical chunk, and carry title metadata into the existing processor/Docs V2 provenance; GC suggestions are review-only. Integration tests passed; Playwright verified playlist rows/docs action and GC safety UI. W20-W21 await final full rerun after these changes.
- 2026-10-15: W20-W21 PASS. Final focused unit/integration matrix 281 passed. Synthetic Playwright journeys passed for capture, playlist/title review, Videos/docs action, GC safety, audio/transcript, crop, offline/retry, cancellation, processing chunks, and Date. W22 is rerunning after these changes.
- 2026-10-15: W22 PASS. Heavy-run host E2E after the final UI/API integration passed in 25.92s, with critical path and no-browser-errors checks PASS. W23 Docker/heavy gates continue.
- 2026-10-15: W23 aggregate rerun could not start because current available RAM is 3.78 GiB (<6.0 GiB enforced threshold); `heavy-validation.json` records DEFERRED_LOW_RAM. Docker E2E independently passed in 266.11s after root fixes; final Host E2E and focused harness tests passed. W23 classified BLOCKED for the genuine external RAM condition; W24 PASS with all configured component evidence and justified W23 blocker.
- 2026-10-16: Revalidated stages. W11 is PASS, not BLOCKED: title/API suite and synthetic camera OCR/review Playwright passed 50 checks and 11/11. Host E2E rerun PASS in 27.37s. Mobile/LAN Playwright PASS 12/12 for HTTPS, ONLINE, camera preview, ACKed fragments, durable server state, and no browser errors. A direct title-playlist attempt against LAN HTTPS stopped at Chromium `ERR_CERT_AUTHORITY_INVALID` because that helper does not trust the locally generated CA; this does not invalidate the prior synthetic title run. Aggregate heavy runner retried at 4.99 GiB (<6.0 GiB); W23 remains ENV_BLOCKED. W12-W22 remain PASS; W24 PASS.
- 2026-10-16: UAT reopened W3, W21, W22, and W24. Reported issue: New Recording modal is not mobile responsive; required 390x844 viewport-safe layout, no horizontal overflow, stacked controls, camera preview near top, sticky accessible Start/Stop, and readable playlist results. Existing capture functionality is retained; responsive layout and mobile Playwright evidence are pending.
- 2026-10-16: Mobile UAT fix PASS. Root cause included intrinsic Videos table width expanding the mobile layout viewport (preventing the 640px breakpoint), an inline 900px modal max-width, settings arranged in one row, preview below advanced controls, and non-sticky actions. Contained Videos table scrolling, allowed zero-min grid tracks, added device-width mobile styles, full-screen safe-area modal, preview-first layout, grid form settings, stacked 44px playlist actions and sticky Start/Stop footer. Mobile layout Playwright passed 8/8; full synthetic OCR/review playlist Playwright passed 18/18 at 390x844; Host E2E rerun passed in 26.37s. An initial playlist rerun exposed a stale assertion expecting both original titles after renaming Session 2; corrected it to verify the filtered Session 1 and both current names after clearing the filter, then reran successfully. A separate desktop capture test attempt could not reach its preflight API because Requests rejected the locally self-signed HTTPS certificate; the existing desktop 23/23 result remains valid and current mobile HTTPS tests use explicit local browser certificate allowance. W3/W21/W22 PASS; W24 remains IN_PROGRESS pending final diff/commit/push checks.
- 2026-10-16: UAT code/report checkpoint `f655dc9` pushed. W3/W21/W22 PASS; W24 PASS with W23's justified RAM-only blocker.
- 2026-10-16: UAT reopened W3/W5/W6/W8/W14/W15/W18/W21/W22/W24 and added W26. Regressions: raw chunk rows exposed, cancellation applied at chunk scope, mobile preview unreliable, and capture lacks mandatory project ownership. Investigate repeated `chunk-000000 FINALIZED` records before any cleanup; preserve ambiguous/historical media. Require mobile Playwright and documented real-device UAT before marking user-facing acceptance PASS.
- 2026-10-16: W3/W5/W6/W8/W14/W15/W18/W21/W22/W26 revalidated after UAT corrections. API now exposes session/logical-video rows only, filters marked/synthetic sessions, scopes cancel/retry to the owning capture session, validates mandatory project selection, and propagates project ownership through fragments/chunks/logical videos/docs. Inventory found 31 manifests (17 finalized/14 failed): 10 title-marked synthetic, 0 explicitly flagged test, 21 ambiguous; repeated `chunk-000000` were per-session first chunks, not within-session duplicates. No media deleted. Mobile evidence at 390x844: New Recording 51/51, layout 8/8, playlist 18/18, cancellation 11/11. One playlist rerun exposed concurrent OCR/review writes to `playlist.json` causing Windows `PermissionError` during `os.replace`; synchronized per-service mutations, reran complete playlist journey PASS. Focused unit/API/Date matrix 288 passed, host E2E 26.24s passed, syntax and diff checks pass. Real-device UAT is documented but not claimed as performed. W23 remains blocked only on enforced aggregate RAM >6 GiB; independent Docker E2E already passed.
- 2026-10-16: W24 PASS. Implementation, tests, reports, canonical plan and phone UAT guide committed; code/report commit `01c3b55` is pushed and remote SHA matched. This final plan checkpoint records W23 as the only environment blocker (aggregate RAM below enforced threshold); standalone Docker E2E passed.
- 2026-10-16: UAT reopened W3/W21/W22/W24 and added W27. HEAD and remote were both `91513caa`. Process inspection found stale repo Python server on 5001 (started Oct 15 before later commits) and desktop port 5000 served a separate Docker image built from `C:\Dev\Zo\whisper-zmi-docker`; its HTML lacks New Recording. Current template has inline HTML/JS but no cache/build identity, and its upload input lacked `multiple` and uploads serialized after clearing the queue. No service worker is registered. Preserve Docker's existing data bind while rebuilding from this repository; make both browser origins report one build identity.
- 2026-10-16: W27 accepted. Rebuilt Docker port 5000 from this repository without changing its user-data bind; restarted current-repo LAN HTTPS server on 5001. Desktop + 390x844 Playwright verified latest revision, matching inline JS, no stale cache/SW, project selector, four-file selection, queue/drop/remove, concurrency 2, independent failure/cancel/retry, project_id, and no chunk rows. Mobile layout passed; host E2E rerun passed in 26.77s after inspecting and retrying one transient `ERR_CONNECTION_RESET`. Initial E2E harness issues were corrected and rerun. Final commit/push and post-checkpoint served-build verification complete; W3/W21/W22/W24/W27 PASS; W23 remains the documented RAM-only blocker.
- 2026-10-16: New P0 scope opened in the same plan. Baseline HEAD/remote `6bafdef476c70753c99a4f5a0112b1dee06eb36f`, clean tree. Current bulk upload is fixed at concurrency 2, sends the browser File via FormData, and server uses Werkzeug request.files then file.save; no JavaScript whole-file arrayBuffer path. Video detail's “Regenerate” calls legacy `regenerate_from_steps`, separate V2 CLI/API generation exists, and version-history/detail reprocess UI is not yet exposed. Current Videos API has 13 user rows (11 COMPLETED, 2 QUEUED); staging has 3 distinct MP4s. Plan W28-W34 added before implementation. OpenCode exposes `opencode-go/glm-5.3-flash`; use it as primary coding executor.
- 2026-10-16: W29 PASS. Ran the 256-test capture/API/Date matrix and six synthetic Playwright journeys against current dashboard; preview/recording stream, fragment ACK/stop drain, 10-30s configuration, chunking, IndexedDB offline reload/retry, playlist Session 1/2 multi-frame confirmation, in-chunk logical boundary, project inheritance, 390x844 layout, cancel/retry and raw-chunk hiding all passed. Evidence in `artifacts/gates/w29-live-capture/`. No real media was opened.
- 2026-10-16: W30 implementation checkpoint. Added `WHISPER_UPLOAD_CONCURRENCY` (default 4, validated 1-6), server-to-template injection, and clarified queued UI as “Ready to upload · pending”; six-file multiselect is tested. Settings tests pass 46/46. Initial browser run proved the services stale (`6bafdef` vs HEAD), then current-repo rebuild restored matching served build. Default-4 Playwright reached four simultaneous uploads; configured-6 Playwright reached six. Six 24MiB synthetic WAV uploads peaked at +73.6MiB container memory (300MiB bound); all test files were removed. W30 remains IN_PROGRESS for stable upload-ID/retry validation against the next rebuilt revision.
- 2026-10-16: W31/W32 PASS. Detail UI exposes separate `Regenerate Documentation` and `Reprocess Video`; Docs V2 reruns from saved evidence without media work. Version snapshots preserve old outputs/provenance and idempotently skip identical evidence. Focused Docs V2/version/dashboard unit+integration matrix passes 109 tests; browser detail journey passes six checks including latest/previous version viewing. W33 is IN_PROGRESS pending final served-build and host regression.
- 2026-10-16: W30 PASS on committed build `1e75afd`. Playwright six-file upload measured maxActive 4 default and 6 configured; retry IDs remained stable, project stayed attached, and one failed/cancelled upload did not block peers. Six synthetic 24MiB WAVs at concurrency 6 peaked at +79.7MiB (<300MiB), and cleanup removed every test file. W31-W33 PASS; Docs V2 detail shows separate actions and current/previous versions; state/timing data is visible. Current HEAD was served on desktop and LAN HTTPS. New Recording preview/record/stop, fragment ACK, mobile layout, Session1/2 playlist title detection/project inheritance, chunk mapping, and cancellation journeys passed. Cancellation test initially exposed teardown TargetClosedError from its polling interval; poller is now cleared and route handlers awaited, and rerun passed with no teardown error. W22/W34 host gate is IN_PROGRESS.
- 2026-10-16: Final W34 evaluation: focused Docs V2/settings/security/live-capture tests 383/383 PASS; upload Playwright 4-default and 6-configured, mobile/LAN build identity, docs current/previous detail, New Recording, playlist and cancellation journeys PASS; Host E2E PASS in 30.53s on `c763d72`. Current-revision Docker image build succeeded. `scripts/ram_gate.py` measured 3.56 GiB available (<6.0 GiB required), so aggregate/Docker heavy gate is ENV_BLOCKED by repository policy; no override attempted. All other W0-W22/W24 and W25-W34 stages PASS. The same plan checkpoint is committed/pushed next, followed by serving that exact final revision.

## Final Delivery Checklist

- [ ] W0-W36 statuses and evidence current; W23 is the prior RAM-only ENV_BLOCKED gate
- [x] User-level capture jobs hide physical chunks/fragments and synthetic sessions; project ownership and session cancellation pass mobile Playwright
- [x] Camera preview, playlist review and mobile layout pass synthetic 390x844 Playwright; real-device procedure documented
- [x] Same-Wi-Fi phone opens HTTPS, reports ONLINE, completes camera capture and fragment upload
- [x] Videos -> New Recording UI and main journeys pass Playwright
- [x] Short upload fragments, ACK/idempotency, IndexedDB recovery and buffer warning pass
- [x] Server processing chunks and four-way mapping pass
- [x] Continuous playlist, title detection, multi-frame confirmation and review pass
- [x] Cancellation, crop, audio-missing, late transcript, Docs V2, GC pass
- [x] Date and backend sorting remain green
- [x] Unit, integration, Playwright, host E2E pass
- [x] Docker/heavy gates pass or justified environment blocker recorded
- [x] Code and canonical plan committed; remote SHA equals HEAD
- [x] Worktree clean; no merge/deploy

## W35 — Run Full security and UI recovery

- ID: W35
- Status: PASS
- Objective: make the real Run Full button work from desktop and authorized LAN clients while retaining request authorization and showing actionable errors.
- Dependencies: W0, W2, W25, W27, W34 PASS.
- Implementation tasks: trace the browser request through `/api/run/full`; correct token validity across served workers/page reloads without weakening Host/Origin/private-client checks; keep unauthorized mutations rejected; return structured authorization and job-start errors; render HTTP and JSON errors in the dashboard; add real-button Playwright coverage for desktop and authorized LAN plus a negative unauthorized case.
- Relevant files/modules: `src/transcript_pipeline/dashboard/app.py`, `src/transcript_pipeline/dashboard/templates/dashboard.html`, `tests/test_dashboard_lan_access.py`, `tests/test_dashboard_commands.py`, `tests/e2e/`.
- Acceptance criteria: Run Full starts once from the real desktop UI and authorized LAN UI; invalid token/host/origin still receives 403; visible errors are useful and never raw HTML/Forbidden; no global security relaxation.
- Required tests: endpoint token/host/origin cases; Run Full success; desktop and LAN Playwright button click; invalid authorization rejection.
- Validation commands: targeted pytest files; `tests/e2e/run_full_button.py`; `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: Run Full Playwright report and host gate report.
- Recovery/fallback: inspect actual request headers, response JSON, and server logs; fix one root cause at a time, maximum two distinct repairs per failure; preserve security checks.

## W36 — Persistent scheduled processing worker

- ID: W36
- Status: PASS
- Objective: persist pending processing work and automatically scan hourly with timezone-aware day/night concurrency limits, duplicate-safe claims, cancellation and restart/stale recovery.
- Dependencies: W35 PASS; compatible with W8 cancellation, W20 test matrix and W33 job state/metrics.
- Implementation tasks: add durable job records and cross-process claim locking; define local timezone/day window 09:00–21:00 concurrency 1 and night window 21:00–09:00 concurrency 3; scan for new pending source work hourly and resume durable queued jobs on startup; claim jobs idempotently; recover stale claims to QUEUED without replaying terminal/cancelled jobs; honor cancellation between stages; ensure upload concurrency remains independent; expose RUNNING, pending/active counts, limit, next/last scan in admin/status UI.
- Relevant files/modules: new `src/transcript_pipeline/processing_worker.py` and persistence module as needed; `src/transcript_pipeline/dashboard/app.py`; `src/transcript_pipeline/settings.py`; dashboard template; Docker/startup configuration; focused worker/API/UI tests.
- Acceptance criteria: queued/pending jobs resume after restart; one job cannot be claimed twice across concurrent workers; active count never exceeds the timezone-derived limit; cancellation is skipped/respected; hourly cadence and next/last scan are observable; transition at day/night boundaries uses configured local timezone; upload concurrency unchanged.
- Required tests: daytime=1, nighttime=3, duplicate claim, hourly scan, restart recovery, cancelled-job skip, status endpoint/UI.
- Validation commands: focused worker/API unit and integration tests; Playwright admin/status check; host E2E; applicable Docker startup check.
- Expected artifacts: worker test report and host E2E report.
- Recovery/fallback: retain durable QUEUED records and disable auto-claim only if a storage/runtime constraint is demonstrated; never emulate safety with an in-memory-only claim; continue W35 and independent validations.

### Progress Log — Run Full and processing worker UAT

- 2026-10-16: W35/W36 opened. Baseline HEAD/remote `1897448c8f8aebeabb10d911afe39ca976f8a08e`, clean worktree. `/api/run/full` UI sent the dashboard token, while middleware required private client, allowed Host/Origin and a process-random token. Persistent shared anti-CSRF token now fixes cross-worker/restart mismatch; host/origin/private-client authorization remains active; errors are useful JSON and Run Full queues a durable job. W35 API/security/command tests pass, including authorized LAN Run Full and invalid-token rejection. Real-button Playwright passed on desktop and LAN origins: current build, click/token forwarding, useful errors and worker status; invalid-token POST remained 403 (10/10 checks). First Playwright attempt intercepted the negative request in the success stub; the route was corrected and the full rerun passed. The initial combined test run inherited LAN/certificate settings from `scan_config.env`; the loopback test now clears those values, and 82 focused tests pass. W35 PASS; W36 IN_PROGRESS.
- 2026-10-16: W36 PASS. Persistent JSON job storage and cross-process OS locking provide durable idempotent claims; stale/dead-worker claims recover safely; cancelled jobs are not claimed; day/night limits derive from configured `WHISPER_TIMEZONE`; next/last scan and pending/active/limit are exposed in `/api/status` and the dashboard. Fresh targeted matrix: 131 passed in 17.26s. Run Full desktop/LAN Playwright: 10/10 passed. Required host gate `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`: PASS in 49.22s, `artifacts/gates/latest.json`, log `artifacts/gates/logs/e2e.log`. Docker health/status had already been verified on the implementation commit (`eecda050ab72375c1bce34b992344f78707b5257`), build marker matched the source revision, and existing data bind was preserved. A scheduled test job created during an earlier misconfigured run was cancelled and verified `CANCELLED`; no user media was removed. W35/W36 complete; no open code blocker.

## W37 — Mobile front/rear camera selection

- ID: W37
- Status: PASS
- Objective: let mobile users choose the rear camera as well as the front camera when recording.
- Dependencies: W3/W4 PASS.
- Implementation tasks: expose front/rear camera options before recording; default to the rear camera; pass the selected facing mode to `getUserMedia` while reusing the acquired stream for preview and recording.
- Relevant files/modules: `src/transcript_pipeline/dashboard/templates/dashboard.html`, `tests/e2e/capture_new_recording.py`.
- Acceptance criteria: both camera choices are visible; rear is selected by default; selecting rear requests `facingMode=environment`; capture preview, fragment upload and stop flow still pass.
- Required tests: synthetic camera Playwright coverage for options/default and requested facing mode; host E2E.
- Validation commands: isolated `tests/e2e/capture_new_recording.py`; `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: `capture_new_recording_report.json`; `artifacts/gates/latest.json`.
- Recovery/fallback: keep camera selection optional on devices exposing one camera; surface browser permission/device errors without forcing a camera switch during recording.

### Progress Log — mobile camera selector UAT

- 2026-10-16: UAT reported that mobile capture only offered the front camera. Root cause: UI had no camera selector and called `getUserMedia({video:true})`, leaving the choice to browser defaults. Added Back camera (default) and Front camera choices; selected facing mode is requested as an ideal constraint so unsupported devices can still use their available camera. Isolated synthetic Playwright capture passed all checks, including both choices, rear constraint, preview on the recording stream, fragment ACKs, and clean stop. Host E2E passed in 54.96s (`artifacts/gates/latest.json`, `artifacts/gates/logs/e2e.log`). No real/private media used by these tests. W37 PASS.

## W38 — Live Capture camera/audio UX and JM recording audit

- ID: W38
- Status: PASS
- Objective: improve crop controls and recording timer placement, support safe live camera switching and microphone-only capture, and audit the newest JM recording without modifying it.
- Dependencies: W3, W4, W5, W6, W7, W9, W18, W37 PASS.
- Implementation tasks: place Clear crop with crop selection; show REC elapsed timer over preview; enumerate/choose front and rear cameras, default to a rear device when available, and switch safely without losing the active capture timeline; add distinct Camera and Audio modes; in Audio mode acquire only microphone, preserve project/title/fragment queue and persist media kind; preserve Camera mode optional microphone; retain recording reset and stop/cancel/retry semantics.
- Relevant files/modules: `src/transcript_pipeline/dashboard/templates/dashboard.html`, `src/transcript_pipeline/live_capture/models.py`, `src/transcript_pipeline/live_capture/service.py`, `src/transcript_pipeline/dashboard/app.py`, `tests/e2e/` and focused Live Capture tests.
- Acceptance criteria: crop label/clear button are adjacent and responsive; rear/front choices work and can switch during an active preview without stopping or losing capture; recording timer is prominent over preview and resets; Camera mode records video with optional mic; Audio mode has only an audio track and retains project ID through fragment/chunk/final media; mobile controls do not overflow; synthetic Playwright proves the journeys.
- Required tests: crop/clear adjacency, rear default/request, front↔rear switching, timer, Camera and Audio modes, Audio project inheritance, mobile viewport and recording continuity; focused API/domain tests; host E2E.
- Validation commands: focused capture pytest; synthetic camera/audio Playwright; `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: capture Playwright report, host E2E report, read-only JM recording audit evidence in Progress Log.
- Recovery/fallback: if a device has no rear camera, retain its available camera and show a clear notice; if live track replacement fails, preserve old stream and recording, roll selector back, and surface an error. Never modify/delete the inspected recording.

### Progress Log — JM recording audit

- 2026-10-16: Read-only inspection found latest JM session `sess-d313658ad200`, created 2026-10-16 18:24 local / 2026-10-17T00:24:22Z, recorded 18:25:59 local. It is FINALIZED, project_id JM, normal camera capture, title `Live capture`; crop metadata is present. Five fragments are ACKED with contiguous offsets/durations totaling 72.072s; one processing chunk is FINALIZED and maps all five fragments, no assembly error. The assembled 11,075,969-byte WebM streams as HTTP 200 and decodes five VP8 frames at 480x640, proving usable video despite the UI/preview report. No audio track exists (manifest MISSING; ffprobe shows only VP8 video). File listing reports READY/QUEUED; processing has not started and documentation is absent. Camera source is not stored in the session manifest, so cannot be verified retroactively. This session was inspected without mutation; physical-device view/camera source remains unverified.



### Progress Log - W38 completion

- 2026-10-16: Moved Clear crop beside crop selection; placed a prominent REC timer over preview; added rear-default/front camera selection and safe in-recording stream replacement with fragment finalization, rollback on failure, and persisted source; added separate microphone-only Audio mode with project/title/session/fragment/chunk inheritance and audio media listing. A mobile CSS display override initially kept the camera selector visible in Audio mode; corrected selector rule to apply only when not hidden and reran the full capture scenario successfully. Focused unit/API/integration tests: 72 passed. Synthetic Playwright capture report: all checks PASS, including crop adjacency/mobile geometry, rear request, front?rear switching, same preview/recorder stream, timer, audio-only tracks, audio project inheritance, fragments/chunk mapping, and no browser errors (`artifacts/gates/capture-uat-data/capture_new_recording_report.json`). Host E2E gate PASS in 29.19s (`artifacts/gates/latest.json`, `artifacts/gates/logs/e2e.log`). JM audit remains read-only: usable VP8 video confirmed, 72.072s, no audio, status READY/QUEUED, no documentation, camera source unavailable from historical manifest. Synthetic browser devices only; real-device rear camera/audio behavior remains unverified.


## W39 - Single-file Live Capture finalization and real media playback

- ID: W39
- Status: PASS
- Objective: ensure each capture session exposes exactly one playable final media record after stop, make finalization idempotent and safe for temporary-media cleanup, and expose working video/audio players plus a clearly visible Camera/Audio mode in the real UI.
- Dependencies: W3, W5, W6, W8, W9, W18, W20, W21, W22, W38 PASS.
- Implementation tasks: audit current finalization and repeated Live capture rows; persist one final-media manifest with source chunk/fragment provenance; assemble finalized processing chunks in timeline order only after stop; validate output via ffprobe; make retries reuse an existing valid final rather than create duplicate rows; keep all fragment/chunk metadata and bytes until assembly succeeds and downstream processing no longer needs them, then safely remove temporary blobs; hide internal media rows; allow View for media without a transcript; use native HTML video/audio controls and useful load/play errors; keep Audio mode visible beside Camera on mobile/desktop and exercise microphone-only final output.
- Relevant files/modules: `src/transcript_pipeline/live_capture/models.py`, `store.py`, `service.py`, `assembly.py`, `src/transcript_pipeline/dashboard/app.py`, `src/transcript_pipeline/dashboard/templates/dashboard.html`, `tests/test_live_capture_*.py`, `tests/test_dashboard_capture_*.py`, `tests/e2e/`.
- Acceptance criteria: one session with multiple fragments and processing chunks yields one user-visible final media row; repeated finalize does not create another row or rewrite valid output; media validates and plays; retained manifest maps ordered fragment/chunk IDs, offsets, hashes, timestamps, project and processing history; cleanup only follows successful assembly and completed dependent processing; View opens native video/audio controls without requiring transcript; Camera and Audio controls are visible on real served desktop/mobile UI; microphone-only capture has no video track and its final artifact is audio-playable.
- Required tests: unit final-media state/metadata, idempotency and cleanup gates; integration multi-fragment/multi-chunk assembly, repeat drain/finalize, corrupted/missing media recovery, transcript-independent player stream, audio finalization; Playwright video/audio player, no-transcript View, visible Audio mode, microphone-only flow, mobile layout.
- Validation commands: targeted pytest for capture service/API/player; synthetic `tests/e2e/capture_new_recording.py` and new finalization/player browser scenario; `.venv-validation\Scripts\python.exe scripts/gate_runner.py e2e`; restart/rebuild actual desktop + HTTPS LAN services and verify `X-Whisper-Build` equals Git HEAD in both.
- Expected artifacts: focused pytest results, capture finalization/player Playwright report, host E2E report, live served revision check, read-only duplicate-session audit evidence.
- Recovery/fallback: never delete originals or provenance; on assemble/probe failure retain all fragment/chunk media, mark finalization retryable, surface a useful user error and reuse existing session; if processing still depends on chunk bytes, defer cleanup; do not merge separate capture sessions just because their titles match.

### Progress Log - W39 initial audit

- 2026-10-16: Read-only LAN audit found the two newest `Live capture.webm` rows are separate sessions, not duplicate finalizations: `sess-d313658ad200` (JM, 5 ACKed fragments, 72.072s, one finalized processing chunk) and `sess-9843cd339967` (JM, 1 ACKed fragment, 1.149s, one finalized processing chunk). No media was changed. Current source exposes processing chunk paths as the session's user media and stop only drains chunks/finalizes the session; no separate session-level final-media manifest exists. Player View is disabled without a transcript, and the custom player suppresses native controls. Real served build was previously stale; current task will validate both services after implementation.
- 2026-10-16: Implemented session-level final media assembly after stop with persisted ordered chunk/fragment provenance, size/hash, stable path and idempotent retries. Internal chunk rows are suppressed once the final exists. Temporary media cleanup now requires valid final hash and every processing chunk PROCESSED; metadata remains. View is enabled without transcript and native video/audio controls plus playback errors are exposed. Added Camera/Audio labels with icons. Targeted pytest: 52 passed; wider capture/API/playlist/assembly/docs tests: 89 passed. Next: rebuild/restart desktop and HTTPS LAN from committed code, run synthetic browser capture/player journeys, then host E2E.
- 2026-10-16: Both desktop and HTTPS LAN were rebuilt/restarted on `45b33bf31aa0d8f84e109a9ffabd1bc18fc200fd`; browser checks confirmed identical served revision, visible Camera/Audio controls, rear default, getUserMedia, no service worker, and mobile-width layout. Synthetic camera/audio journey proved final files and one row/session. It exposed an audio WebM with an audio stream but no finite duration; added FFmpeg normalization and a generated live-WebM fixture. Targeted FFmpeg/API/service tests: 30 passed. Updating the served-build checks and rerunning full capture/player + host E2E after rebuilding this correction.
- 2026-10-16: W39 acceptance PASS. `pytest tests/test_live_capture_assembly.py tests/test_live_capture_processing_chunks.py tests/test_dashboard_capture_processing_api.py -q`: 30 passed, including multi-chunk single-final output, idempotent drain, provenance retention, cleanup gate, and synthetic live-WebM duration repair. Synthetic `tests/e2e/capture_new_recording.py`: all checks PASS; video and audio final media both reported finite duration and loaded native players; camera/audio modes, switching, upload ACKs, project, crop/mobile, and one user row/session passed (`capture_new_recording_report.json`). `tests/e2e/served_ui_revision.py`: desktop and HTTPS LAN returned 200 and matching revision `54e78ba`, showed Camera/Audio, rear default, secure media API, no service worker and 390px overflow-free layout (`artifacts/gates/live-capture-finalization/served_ui_revision.json`). Host E2E PASS in 41.43s (`artifacts/gates/latest.json`). The two previously inspected JM `Live capture.webm` rows remain unchanged and are distinct capture sessions. No physical-device camera hardware test was claimed.
- 2026-10-16: Follow-up review found cleanup gating was callable/tested but not automatically invoked when dependent processing completed. W39 reopened to invoke the safe cleanup gate on final-media creation and on the last PROCESSING -> PROCESSED transition; source metadata remains retained. Targeted FFmpeg/API/service tests now pass again: 30 passed, including automatic blob cleanup with retained fragment and mapping metadata. Re-running the browser and host gates on this code revision before closing W39 again.
- 2026-10-16: W39 final verification PASS on code revision `7350713117474b640dc1fdbf7e6bb26b0892d79d`: focused tests 30 passed; synthetic capture journey all 66 checks passed, including final video/audio duration metadata, playable native players, idempotent single row per session, and cleanup after processing while preserving hashes/mappings; Host E2E PASS in 42.67s. Rebuilt desktop container and restarted HTTPS LAN; served UI Playwright reports matching response header and HTML revision on both, Camera/Audio visible, rear selected, getUserMedia available, no service worker, no horizontal overflow at 390px. The final plan-only commit will be reflected in the runtime revision marker after commit and services will be restarted once more.

## W40 - Recording integrity, shared data, mobile crop, duration and delete actions

- ID: W40
- Status: PASS
- Objective: preserve the complete acknowledged capture timeline in one verified final media file, repair mobile crop dragging, make desktop/LAN use the same Whisper data root, show source media duration and deterministic delete actions, and safely assess/recover the reported JM capture.
- Dependencies: W3-W9, W20-W22, W39 PASS.
- Implementation tasks: inspect the reported JM session/fragments/chunks/final without mutation; persist actual probed final duration; validate complete ACKed fragment timeline and output duration before exposing completion or deleting temporary media; assemble/recover atomically to a staging path with integrity metadata; add a three-or-more-fragment 45-second synthetic regression; replace crop mouse handling with Pointer Events and displayed-video coordinate mapping; configure Docker and HTTPS LAN services against one existing data root without copying data; add sortable/displayed Duration to Videos; render deterministic delete buttons or disabled buttons with state-specific reasons while excluding internal chunks.
- Relevant files/modules: `src/transcript_pipeline/live_capture/service.py`, `assembly.py`, `store.py`, `src/transcript_pipeline/dashboard/app.py`, `src/transcript_pipeline/dashboard/templates/dashboard.html`, `compose.yml`, `tests/test_live_capture_assembly.py`, capture/dashboard API tests, `tests/e2e/`, service launch/config scripts.
- Acceptance criteria: JM audit records session ID, expected elapsed duration, per-fragment media duration/ACK/server presence, mappings and final duration; if reconstructable, a staged full output validates before replacing the current file. Every finalized capture includes each ACKed fragment exactly once and output duration is within max(2 s, 5%) of expected timeline; failed validation retains source blobs and does not mark complete. Pointer/touch drag yields a visible nonzero rectangle on mobile. Desktop and LAN return matching projects/videos/jobs/docs/worker state from the same data root. Duration is from ffprobe or persisted verified metadata. Every user-video row has an actionable delete button or a disabled button with explicit state reason; internal fragments/chunks remain hidden.
- Required tests: unit/service multi-fragment timeline, ACK completeness, duration mismatch retention, idempotent staged recovery; API duration and delete eligibility/state; Playwright touch crop rectangle, video duration, delete affordance and visible row parity; host E2E.
- Validation commands: targeted pytest on capture assembly/dashboard files; synthetic FFmpeg fixture of at least three fragments totaling >=45 s; `tests/e2e/capture_new_recording.py` plus mobile crop/video list scenario; `.venv-validation\\Scripts\\python.exe scripts/gate_runner.py e2e`; verify Docker/LAN API equality and `X-Whisper-Build` against HEAD after restart.
- Expected artifacts: read-only JM manifest/ffprobe audit, synthetic multi-fragment report, focused pytest output, Playwright report, host gate report, same-data-root API counts and served revision report.
- Recovery/fallback: never remove/replace the JM final during diagnosis. Build recovery output at a new staging path, verify duration/streams/hash first, retain the previous final as backup until replacement is proven. Never copy data between roots; point both services at the verified existing root. If a shared root is unreachable, keep services stopped rather than silently starting against a separate empty dataset. On failed assembly, preserve ACKed fragments and chunks and report retryable error.

### Progress Log - W40

- 2026-10-16: Baseline HEAD/upstream `1ae1248b417d7282e37d2aed8e85cd5091bb8fe3`, clean worktree. Docker localhost mounted `C:\\Dev\\Zo\\whisper\\zmi-data`; LAN Python served repository `Videos/`. API proved localhost had 0 files while LAN had 39. JM `sess-4ee4a8f39d86`: five ACKED WebM fragments, 71.295 s declared, five files present, all mapped once to a finalized processing chunk; old final/chunk were identical at 12,683,545 bytes. Packet inspection found 1,233 packets across the fragments but reset timestamps; old final probed/displayed 14.944 s. Root cause: FFmpeg was given a `.tmp` path without explicit output format, so it failed; the fallback appended WebM bytes and did not offset fragment timestamps.
- 2026-10-16: Implemented explicit FFmpeg output formats and concat durations, ACKed-fragment completeness checks, direct ordered fragment final assembly, verified duration tolerance (max 2 s / 5%), and duration persistence. Invalid old output is retained under a recovery path only after staged output validates. Reconstructed JM final: 71.25 s, 5/5 ACKed IDs in order, 5/5 source fragment files retained, old final backed up, final playable duration 71.25 s. Added synthetic 3×15 s regression plus short-final recovery test. Targeted service/API/date tests: 40 passed; compileall passed.
- 2026-10-16: Mobile crop now handles Pointer Events with pointer capture, touch-action suppression, object-fit/source coordinate mapping, pointer cancel, and an adjacent Clear crop control. Isolated mobile Playwright PASS: 390×844 no overflow, preview visible to 618 px, touch drag created a nonzero rectangle, playlist rows readable, sticky stop visible, duration column rendered, raw internal IDs absent, queued delete disabled with the correct reason, and recording stopped. Synthetic browser capture/player/audio run PASS: all checks, including one final media/session and native video/audio players. First E2E run exposed `page.goto(wait_until=load)` hanging on the dashboard's ongoing requests; changed the smoke test to wait for navigation commit followed by the existing `#filesList` readiness assertion. Host E2E rerun PASS in 59.54 s.
- 2026-10-16: Docker data-root configuration now defaults to the same repository data root used by the host/LAN process; effective Compose config and restarted desktop/LAN API equality, build revision, and served UI remain to be verified before W40 closes.
- 2026-10-16: Re-ran focused validation after final assembly backup/cache changes: 40 passed; `compileall` and `git diff --check` passed. Host E2E initially could not reset its fixture directory because my prior diagnostic server still held a fixture log; stopped that process, changed smoke readiness to wait for a rendered table row, then reran the required gate: PASS in 51.44 s (`artifacts/gates/latest.json`). Desktop/LAN restart and live API/build parity are the remaining acceptance checks.
- 2026-10-16: Live validation found `scan_config.env` supplied Windows TLS paths to the loopback-only Docker service; Compose now clears LAN/TLS overrides there while preserving HTTPS in the separate LAN process. Shared job inspection found job `fffffea601114fbbbddf61f8ca7e98fb` ACTIVE at attempt 27 with a Windows worker PID; the Linux container treated that foreign PID as dead, causing repeated claims and an `os.replace` collision. Implemented a cross-platform exclusive lease file for queue updates and PID recovery only within the same process namespace; no job/media data was edited. `/api/files` also took >60s while probing all videos synchronously; ffprobe now runs in a bounded background executor and UI refreshes while durations resolve. Regression tests cover pending duration results and foreign-host PID handling. Host E2E PASS in 68.24s after reusing its existing Playwright page for reload; focused tests 51 PASS; compileall/diff-check PASS. Live service parity and final revision restart remain.
- 2026-10-16: Rebuilt/restarted desktop and LAN from `ec73819f68668a11340de09757ab783c933dcb58`. Served revision/header and HTML match on both endpoints; Playwright saw Camera/Audio, rear default, secure camera API, no service worker, and mobile width 390 without overflow. Both `/api/files` responses returned the same 45 media IDs and both `/api/projects` returned the same seven projects; both processes read the same repo-root bind. The first cross-runtime restart exposed a worker lock race if `.whisper` is absent during container startup; the Docker worker thread stopped with `FileNotFoundError` for the lease path. Added parent-directory recreation on each lock acquisition and a regression test. Desktop `/api/files` returned all 45 records in 23.43s on cold duration cache; LAN returned the same data in 0.59s. Mobile Playwright pointer test PASS (390x844; nonzero 0.6842x0.5199 crop rect; adjacent Clear Crop; no overflow; duration and delete reason visible). Latest host E2E rerun PASS in 52.8s. Focused queue/assembly tests: 32 passed. Rebuild/restart and parity/worker-running recheck remain before W40 PASS.
- 2026-10-16: After the lock fix, desktop and HTTPS LAN restarted from `47f0223a140d66ec71f24ea186e95e747823d03b`; Docker health and both workers report RUNNING, zero pending/active jobs, limit 3. Browser served revision/header/HTML exactly match HEAD for both URLs; mobile 390px layout, Camera/Audio, rear default, secure camera access, and zero service workers passed. APIs returned matching media ID sets (46 at this point), seven matching projects, and matching worker state. A field-level comparison found Windows absolute-path keys in the shared processed-files index were not recognized by Linux; `_file_status` now matches portable paths relative to the shared root. Focused dashboard/worker/assembly tests: 58 passed; Host E2E: PASS 43.81s. The 46th record was the 7,141-byte, 0.14-second synthetic capture created by my mobile pointer test (single fake-camera fragment, exact test crop and timestamp); marked it explicitly as test and removed it using the store's confirmed test-session cleanup, leaving user recordings untouched.
- 2026-10-16: W40 PASS. Committed/pushed path normalization as `210fdc740f2ceae3a568d72ec65b096300888876`; rebuilt Docker incrementally from source, restarted desktop and HTTPS LAN on the shared repository root. `served_ui_revision.py` PASS for `http://localhost:5000` and `https://192.168.50.67:5001`: response header and HTML meta match SHA; mobile width 390, no overflow/service worker, Camera and Audio visible, rear default and secure camera API present. Both APIs now return the same 45 media IDs, per-media status/state/project/duration, seven projects, documentation/transcript presence, and worker state (RUNNING, 0 pending, 0 active, limit 3); shared job store has the same two records. Mobile Playwright pointer test passed on 390x844 with a 0.6842 x 0.5199 crop region, Clear Crop adjacent, duration and deterministic delete reason visible. Targeted pytest: 58 passed; Host E2E: PASS in 43.81s. JM `sess-4ee4a8f39d86`: expected 71.295 s, 5/5 ACKed and present, mapped once in order, validated final 71.25 s, playable; 5 source fragments retained. Synthetic 3-fragment 45 s assembly regression passed. Delete action is always shown and enabled for completed/ready media; active capture/upload/processing shows disabled action with a state-specific reason; internal chunks stay hidden. Desktop/LAN data counts and statuses agree; no private media was removed. Final plan-only commit will update served revision markers and trigger a final served-HEAD check.
- 2026-10-16: Final restart exposed a second cross-runtime lock race: concurrent exclusive create on the Windows-mounted shared directory can raise `PermissionError` instead of `FileExistsError`; the LAN worker thread stopped while Docker remained active. Lock acquisition now treats that transient error as contention, checks/reaps only stale leases, and retries; regression test simulates the Windows collision. Targeted dashboard/worker/assembly tests: 59 passed; Host E2E: PASS in 39.95s. W40 reopened until both workers run concurrently on the committed fix and final served HEAD/data parity pass.
- 2026-10-16: W40 PASS on `29335b58ab6b2aaedac7f871e63bed7dd3084ab1`. Rebuilt Docker from the committed lock-collision retry fix, restarted the LAN process, and confirmed both processing workers stay RUNNING without thread exceptions. Final HEAD serves on desktop and LAN; both HTML meta and `X-Whisper-Build` match. Normalizing OS-specific path separators and timezone representations yields identical 45 media records (IDs, statuses, user states, project, durations, documentation/transcript presence), seven projects, and worker status (0 pending/active; limit 3); both share the same repo-root bind and two durable queue records. Final UI Playwright: PASS on both origins, responsive 390px layout, no service worker/offline indicator, Camera/Audio and rear camera visible, secure camera API available. Previous mobile touch Playwright and host E2E remain green; targeted tests 59 passed and Host E2E 39.95s. After documentation-only commit `f4375d591d4a2cfc3b1133e0f8189efef8f643b3`, restarted both services and reran served-revision/API checks: desktop and LAN both return 200 and exactly match the final commit; 45 media entries, seven projects and worker/media/documentation parity PASS. Worktree and upstream are clean/aligned.

## W41-W45 — Optimized media retention and documentation workflow

### Goal and status boundary

W40 completed the P0 recording-integrity, desktop/LAN shared-data, mobile-crop, duration, and delete-action work. This section plans the additional user-requested lifecycle: compress large originals, retain verified optimized media, clean temporary capture pieces safely, and make documentation regeneration easy to find and reliable. It does not reopen or replace the W40 acceptance evidence.

Current source findings:

- `src/transcript_pipeline/media/compressor.py` already moves successful compressed outputs into `Videos/<project>` and deletes the input under `Video_compress/`. Its success gate currently relies mainly on FFmpeg returning zero and the output existing; it does not sufficiently validate media streams, duration, playability, or size before removing the source.
- Live Capture has a separate guarded cleanup path. It deletes server fragments/intermediate chunks only after a final exists, its manifest hash matches, all processing chunks are `PROCESSED`, and mappings are finalized. Failed or incomplete work must retain retry inputs. Browser-local fragments are deleted only after durable server ACK.
- `/api/capture/gc-candidates` is advisory and `gc.py` does not delete user media. Do not turn this into broad or age-only deletion.
- Documentation V2 already has distinct “Regenerate Documentation” and “Reprocess Video” actions. Regeneration uses stored evidence, retains version history, and should not invoke transcription/OCR/vision again. Preserve this behavior and add regression coverage rather than rebuilding it.
- The last recorded heavy Docker gate was deferred for the >6 GiB RAM requirement. Recheck actual available RAM before running it; do not risk active user jobs.

### Frozen lifecycle contract

1. Keep the raw source until a staged optimized output is independently validated: readable container, video stream, positive duration, expected audio behavior, nonzero size, and duration within `max(2 seconds, 5%)` of the source. Require meaningful size reduction (initial acceptance: at least 1%); if validation or reduction fails, retain the source and expose the failure.
2. Publish from a same-filesystem staging file atomically. Verify the published file/hash and its registered media record before deleting only the exact source linked by provenance. A retry must not overwrite a valid output or delete an unrelated path.
3. Persist auditable source/output relative identifiers, hashes, sizes, measured durations, result, and source-cleanup status. Never store machine-specific absolute paths as the only provenance.
4. Surface original size, optimized size, bytes saved, and cleanup result next to the compression result. For a cleanup failure show `CLEANUP_PENDING`; allow retry only when provenance still proves the source/output relationship.
5. Keep Live Capture cleanup rules separate: after full processing succeeds, remove only that session’s acknowledged temporary fragments/intermediate chunks. Retain final playable media, manifests, and documentation. On failure/cancel/partial processing retain source pieces for recovery.
6. Never expose temporary fragments or processing chunks as ordinary user videos or delete targets.

### Coding roles and model budget

- Codex/ChatGPT owns root-cause analysis, lifecycle design, review, data-integrity decisions, and acceptance evidence.
- OpenCode Go is the economical primary implementation model; configured DeepSeek/economical alias is fallback through `scripts/model_router.py`. Resolve aliases at runtime. Do not commit credentials or private model identifiers.
- Give the coding model one bounded work item at a time, with file ownership and explicit acceptance tests. Review every destructive-path diff before running it against user media.

### W41 — Compression lifecycle contract and baseline (PENDING)

- Trace all entry points that place files in `Video_compress/`, call the compressor, publish outputs, and report cleanup state.
- Define the persisted provenance/state shape and migration/default behavior for existing records.
- Make every failure path preserve the original: FFmpeg error, missing output, corrupt output, absent video stream, duration mismatch, output larger than source, collision, atomic publish failure, metadata/index write failure, and interrupted retry.
- Add focused tests for these conditions and success-path state transitions. Use synthetic fixtures only.
- Exit gate: documented state machine, no source removal before validated publication, existing successful compression behavior preserved.

### W42 — Validate, publish, then remove source (PENDING)

- Probe source and staged output with the existing media tooling; compare measured duration and required streams.
- Enforce output size reduction before cleanup. Make tolerances explicit and centralized.
- Publish atomically, persist provenance, reopen/probe the published output, and verify its hash before source unlink.
- Make retries idempotent and safe when output already exists or a prior attempt stopped between publish and cleanup.
- Exit gate: tests prove the source survives every injected failure and is removed only after complete verification; optimized media remains playable and registered.

### W43 — Make cleanup outcome visible (PENDING)

- Add deterministic API/UI states: `OPTIMIZED_SOURCE_REMOVED`, `OPTIMIZED_SOURCE_RETAINED`, `CLEANUP_PENDING`, and `FAILED` (or equivalent existing enums).
- Show original/optimized sizes, bytes saved, and a plain-language cleanup reason beside the compression result.
- If a retry control is needed, restrict it to a source path and hash validated against persisted provenance; use existing path-safety and authorization checks. Do not add a general-purpose raw-file delete control.
- Add API and UI tests for success, retained-original, pending-cleanup, retry, and missing/corrupt provenance.
- Exit gate: a user can tell which media is retained and why, without guessing from a missing row.

### W44 — Capture cleanup and documentation regression (PENDING)

- Add service tests covering local-fragment deletion only after durable ACK; server-fragment retention before full success; cleanup after all processing chunks complete; and retention of final media, manifest, and docs.
- Exercise failed transcription, missing audio, cancellation, partial mappings, hash mismatch, and restart/retry. Each must retain recoverable inputs.
- Add Docs V2 tests proving regeneration uses saved evidence, does not rerun expensive upstream extraction, creates/selects a version, and leaves “Reprocess Video” as the explicit action for new evidence.
- Verify the regeneration action is available on desktop and narrow mobile layouts, with running/success/failure feedback.
- Exit gate: cleanup is recoverable and bounded to the session; doc regeneration remains distinct from reprocessing.

### W45 — End-to-end acceptance and served-app closure (PENDING)

- Synthetic end-to-end: large source -> validated optimized media -> transcription/processing -> documentation -> regenerate/version history -> verified source cleanup state.
- Synthetic Live Capture with at least three ACKed fragments: ordered full-duration playable final, then safe temporary cleanup only after processing completion.
- Mobile real-browser coverage for capture/crop and documentation controls; use actual phone UAT when available because Playwright does not prove device/browser behavior completely.
- Restart desktop and LAN services from the final committed HEAD. Confirm both origins share repository revision, data/database/media roots, media/project/job/docs/worker sets, and rendered UI behavior. Resolve LAN IP dynamically rather than assuming an old address.
- Run focused tests first, then Host E2E. Run heavy Docker/soak gates only when the recorded RAM threshold is currently met and no active user job is at risk.
- Exit gate: all checks link to artifacts/logs and current served revision; user data is unchanged except for explicitly generated synthetic fixtures; worktree clean and branch/upstream status recorded.

### Implementation checkpoint — 2026-10-17

- W41-W44 implementation is present: staged H.265/MP4 optimization validates streams, duration, size, published hash and provenance before deleting the exact source; cleanup-pending outcomes can be retried through an authenticated endpoint and are visible with saved-byte counts in the dashboard. The retention state refreshes when a processing run completes.
- Regression coverage includes encoder/validation/publish/cleanup failures, retry eligibility, source mutation, WebM-to-MP4 compatibility, capture temporary cleanup invariants, provenance API states, shared data-root derivation and build revision markers.
- Targeted pytest: 168 passed, 4 skipped (Windows symlink privilege). Ruff and `git diff --check` passed. Mobile docs regeneration Playwright and crop-touch E2E had passed against the prior W40 runtime; final rerun remains part of W45.
- RAM gate on 2026-10-17: 2.11 GiB available, threshold strictly greater than 6.0 GiB. Full regression/security/smoke/authoritative E2E/Docker and production restart are deferred per PLV5. No live service, user media or production data was changed in this checkpoint.
- W45 remains pending. Deployment requires the RAM gate and heavy gates to pass, then verification of the current served HEAD, desktop/LAN parity, mobile pointer interaction, documentation regeneration, full-duration playback and delete-state reasons.

### Completion report fields

`COMPRESSION_VALIDATION=`
`SOURCE_CLEANUP_RULE=`
`CLEANUP_STATUS_UI=`
`CAPTURE_TEMP_CLEANUP=`
`DOC_REGENERATION=`
`MOBILE_UAT=`
`DESKTOP_LAN_PARITY=`
`TESTS=`
`SERVED_HEAD=`
`WORKTREE_CLEAN=`


## Release delivery Kanban — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Resource-aware RAM policy (>=6 standard, 4–6 serial, <4 blocked) | 🟩 COMPLETE | Boundary, mode-transition, per-gate recheck tests pass; 25 focused runner/harness tests pass | Policy is enforced before every gate | Agent |
| Playwright release coverage | 🟩 COMPLETE | `artifacts/gates/e2e-host-data/e2e_report.json`: smoke + black-video editor + mobile setup PASS; dedicated editor run PASS | Served UI check follows deployment | Agent |
| Host E2E release gate | 🟩 COMPLETE | `artifacts/gates/e2e-host-data/e2e_report.json`: 3/3 scripts PASS | Served UI check follows deployment | Agent |
| Docker/release validation | 🟥 BLOCKED | Build PASS (198.93 s); Docker E2E PASS (107.33 s), but ran while RAM had fallen to 1.45 GiB before the corrected per-gate guard; current RAM is below the authorized minimum | Rerun Docker E2E at >=4 GiB | Agent |
| Desktop + LAN deployment parity | 🟥 BLOCKED | Old Whisper services stopped; current RAM <4 GiB, no safe unrelated service stop identified | Deploy and verify when RAM >=4 GiB | Agent |
| Setup page, QR, public CA download | 🟥 BLOCKED | Host Playwright PASS for QR, `/setup`, CA download; deployment not yet safe | Verify actual served endpoints after deploy | Agent |
| Video Editor and mobile capture controls | 🟥 BLOCKED | Host Playwright PASS for editor, crop/time/apply, mobile quality/layout; deployment not yet safe | Verify actual served UI after deploy | Agent |

### Resource-aware release policy

- >= 6 GiB available: standard validation mode.
- 4–6 GiB available: `LOW_MEMORY_SERIAL`; no Playwright, Docker, and FFmpeg overlap; recheck RAM before each expensive gate and release each gate's browser/process before continuing.
- < 4 GiB available: `ENV_BLOCKED` unless safe, task-specific RAM can be freed. Do not stop unrelated authenticated Jenkins/Sonar/Supabase services without confirming they are idle; their activity endpoints did not allow unauthenticated inspection.
- Assertions and required functional coverage remain unchanged. The previous fixed >6 GiB refusal was conservative policy, not a demonstrated technical minimum, and is retired.
- Final resource check: 0.63 GiB available. No Whisper jobs, obsolete test browsers, or test containers remain. Remaining Docker RAM users include active Jenkins, SonarQube, Supabase, and Zo Motion services; their activity could not be verified safely, so they were left running. Deployment and the corrected Docker gate remain `ENV_BLOCKED` until >=4 GiB is available.

## P0 mobile recording audio + real crop pipeline — 2026-10-19

| Feature | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| S43 real WebM audio audit | 🟥 BLOCKED | `sess-5c47d4d0cd07`: final WebM has VP8 video 480x640, 0 audio streams; `audioAvailability=MISSING`; `audioRequested` and permission state were never persisted | Historical requested/permission state cannot be recovered; report evidence limitation | Agent |
| Camera microphone default and visible status | 🟨 TESTING | Playwright synthetic capture: Mic defaults ON, live status before record, missing requested audio blocks recording; 56 focused tests pass | Verify through deployed UI; physical phone UAT remains | Agent |
| Preserve microphone through camera/orientation changes | 🟨 TESTING | Playwright: camera switch, 2 orientation changes, and quality change preserve live audio track | Verify on deployed UI and physical phone | Agent |
| Crop into recorded video source | 🟨 TESTING | Playwright confirms canvas captureStream video + microphone track feed MediaRecorder; fragment/final ffprobe show VP8 + Opus | Verify through deployed UI; physical phone UAT remains | Agent |
| Crop dimensions, preview mapping, size proof | 🟨 TESTING | Synthetic 1280x720 -> 636x360; cropped sample 111,147 B vs full 176,976 B (37.2% smaller) | Confirm actual camera alignment on phone; byte reduction depends on scene/codec | Agent |
| Uploaded fragment and final audio validation | 🟨 TESTING | API and assembly tests: 56 passed; first fragment + final ffprobe metadata persist, missing requested audio flags `AUDIO_CAPTURE_FAILED` | Verify on deployed UI and physical phone | Agent |
| P0 functional gates and deployed UI | 🟥 BLOCKED | Playwright 77/77 and Host E2E 4/4 passed before runtime-only package fix; 28 setup/capture/assembly tests pass; served build `9ddb5a1` passed 24/24 checks including `/setup`, QR, public CA DER, editor/audio controls; both services are healthy and HTTP desktop, HTTP setup, HTTPS LAN return 200 with matching `9ddb5a1`; current RAM 3.53 GiB | At >=4 GiB, rerun Playwright + Host E2E sequentially, then deploy/verify current plan HEAD | Agent |

- 2026-10-19 P0 update: located S43 outside source code at `Videos/live_capture/sess-5c47d4d0cd07/final/recording.webm`; read-only ffprobe found one VP8 480x640 video stream and no audio. The session manifest omitted `audioRequested` and microphone permission state, so the historical cause is indeterminate. Implemented mic-on default, visible/preflight live-track validation, audio preservation across camera/orientation/quality changes, canvas crop recording stream with mic track, and server fragment/final ffprobe checks. Focused tests 56/56; synthetic Playwright 77/77; Host E2E 4/4 before runtime-only dependency change. Synthetic crop 1280x720 -> 636x360; 37.2% fewer bytes in this sample. Served `/setup` exposed missing runtime `cryptography` and container LAN allowlist; added dependency, regenerated locks, and set local `ZMI_LAN_HOSTS=192.168.50.20`; 28 setup/capture/assembly tests pass. Build `9ddb5a1` served on desktop + LAN and passed 24/24 UI/setup checks: matching revision, QR, `/setup`, secure URL, public DER root CA download (418 bytes; no private key), mic default/status, crop controls, quality selector, eight editor handles, HH:MM:SS, Apply button. After restart, desktop, HTTP setup, and HTTPS LAN returned 200 with matching `9ddb5a1`; container healthy. Python requests observed a Norton-issued TLS replacement; Chromium accepted HTTPS via the Windows trust store. Whisper leaf SAN contains localhost, 127.0.0.1 and 192.168.50.20. Worker had 0 active/0 pending; no safe stale test process/container remains, and other active Docker apps plus the user's SharePoint browser/task were left alone. Current RAM is 3.53 GiB: final Playwright/Host E2E rerun and serving of the current plan-only HEAD are ENV_BLOCKED until >=4 GiB. Physical phone UAT remains pending.

## FINAL SDD RELEASE RUN

This is the canonical release policy and execution record. The only active feature-level Delivery Kanban is in `.agents/deliverables/US-ZMI-LIFECYCLE-001-recording-storage-docs.md`, section `Finalization Kanban`. Older Kanbans above are dated historical evidence only. This section supersedes every earlier fixed RAM-threshold rule (including the former strict `>6 GiB` hard gate and the later 4/6 GiB ladder) and every earlier policy that made integration tests, full-suite runs, Playwright/E2E, Docker build/E2E, Jenkins, Sonar, soak, or phone UAT mandatory for release. The same supersession applies to the gate sections of `US-ZMI-LIFECYCLE-001` and `PLAN-ZMI-LIFECYCLE-001`.

### Release policy (canonical)

Hard blockers — the ONLY conditions that block release:

1. Requested implementation incomplete (SDD/US scope not implemented).
2. Relevant unit tests fail (tests tied to the change or scope).
3. App build or app start fails.
4. Known data loss or corruption.
5. An unsafe restart that would lose the active user job and cannot be isolated or recovered safely.

Everything else is advisory. RAM affects execution strategy only — it decides ordering, serialization and deferral of expensive work (for example, one browser/Docker gate at a time, processes released between gates). A low RAM reading is never by itself a release blocker or a gate result.

Advisory gates — integration, E2E, Playwright, Host E2E, Docker build/E2E, security, and any other optional check — record exactly one result: `PASS`, `FAIL_ADVISORY`, `ENV_BLOCKED`, `NOT_CONFIGURED`, `NOT_RUN`. Advisory results never block release; they are recorded with evidence and become follow-up work. Never record `PASS` without executed evidence from the current run.

Jenkins, Sonar and soak are `NOT_REQUIRED` for this release. Physical Galaxy phone UAT is owner-only verification tracked as `OWNER_PENDING`; it does not hold an otherwise accepted release.

Model policy: use Z.AI/GLM for normal implementation. On auth failure use OpenCode Go/DeepSeek Flash, then local DeepSeek/Ollama, then the available current coding model. DeepSeek Pro is only for a difficult blocker after cheaper attempts. Record `MODEL_DEGRADED=YES` on GLM auth failure and continue; model access is never a project blocker.

Mandatory engineering Definition of Done — all required before release:

- Scope complete per the SDD/US and the reconciled scope below.
- No TODO, mock, stub or placeholder left in requested production functionality.
- Relevant unit tests pass.
- App builds, imports and starts.
- Migrations/defaults valid for existing records; no destructive migration.
- Data safety: no user data deleted or corrupted; active job preserved; shared data root untouched except documented synthetic test records.
- Code + SDD docs + this Kanban committed and pushed (remote HEAD equals local HEAD).

Deploy verification — all required whenever deploying:

- Deploy only the final reviewed, pushed HEAD, with the previous image/SHA retained as rollback.
- Deploy only when hard blocker 5 is cleared: the active job is inactive, or can be isolated/recovered without loss. Never stop the worker or the active job to force a deploy, and never deploy behind its back in a way that loses it.
- Detect the current LAN IP dynamically. Verify desktop HTTP and LAN HTTPS serve that exact HEAD (response header and page meta), health is ONLINE, and shared-data parity matches a pre-deploy count/hash/metadata snapshot (media/projects/jobs/docs/worker).
- Required lightweight post-deploy smoke: HTTP and HTTPS respond; served revision equals FINAL_HEAD; existing Videos and Projects render; shared data is unchanged; New Recording, Video Editor, and Overview modal open; `/setup` responds. A startup failure or data corruption is a hard blocker and triggers repair/rollback.

### Reconciled scope and evidence

The accumulated SDD includes Live Capture/project inheritance; camera/microphone lifecycle; real pre-encode crop; durable fragments, ACK/idempotency, processing chunks, assembly and cleanup; continuous playlist; TIME/FRAME editor and black-video tools; multi-file upload; processing worker recovery; Documentation V2, regeneration and versioning; Videos table/player/delete behavior; mobile HTTPS onboarding; and the Overview Stats Modal. The Overview modal adds a top-right toolbar control, responsive modal, and the same Files Processed, Media Processed, Success Rate, and Avg. Processing Time cards, reusing the existing overview data/rendering logic. It must preserve the main Overview section and support close button, backdrop, and Escape. Existing evidence remains in the dated entries above. Historical S43 was audited read-only: its final WebM has one VP8 480x640 video stream and no audio; its manifest lacks `audioRequested` and mic-permission state, so the original cause cannot be recovered.

This run's lightweight evidence on current code: 279 selected unit/API tests passed; after typed-boundary fixes, 60 fragment/assembly/processing/API and synthetic-capture tests passed; the independent Live Capture → keyframe → Docs V2 integration pair passed 4 tests; changed-module Ruff passed; feature-module Pyright had 0 errors and 2 optional `qrcode` stub warnings; compileall and `git diff --check` passed. A fresh lightweight rerun on 2026-10-19 passed 38 tests across capture-fragment API, assembly, and capture-store modules (first invocation without `PYTHONPATH=src` failed collection; rerun with the configured source path passed). Current branch is `feat/zmi-documentation-synthesis-v2`; local and remote HEAD are both `5b7f9299eb4b9203c0d8cec96154135712525745` (pushed). The worktree currently holds the uncommitted Overview Stats Modal implementation (`src/transcript_pipeline/dashboard/templates/dashboard.html` modified; `tests/e2e/overview_stats_modal.py` untracked) — the DoD commit/push item is not yet satisfied for that scope. The served app advertises `9ddb5a150fbd7dd1c4d5db3cd732a6e8de007501` (verified live 2026-10-19; HTTP 200); the served revision differs from HEAD and final HEAD has not been built/served. Do not call the final release deployed until final HEAD is built, served, parity checked and the post-deploy smoke passes.

Historical read-only `/api/status` recheck on 2026-10-19: HTTP 200, worker `state=RUNNING`, `active_jobs=1`, `pending_jobs=0`, concurrency limit 3. The active job is `14ed371b097a4b1c9a47a9166f5e1a95` (`full`, started 2026-10-20 00:25:55 UTC, host `ZenMini`, PID 44660); PID 44660 was re-verified present as `python` (started 2026-10-19 15:58 local). This is an active user job, not a stale queue record. Do not restart or interrupt Whisper while it runs — that is hard blocker 5, the only current deploy blocker. Free RAM measured 4.65 GiB at recheck; under the canonical policy this is execution-strategy context only (prefer serial/lightweight ordering), never a blocker. Coding and unit tests continue regardless of the job. No unrelated project/service was stopped.

Security mini-loop: the first harness attempt used the watcher Python, which lacks `pip-audit` and `truststore`; its dependency audit result was not an external network failure. The security suite also exposed environment leakage because importing dashboard configuration loads LAN values from `scan_config.env`; the localhost-only test now explicitly clears `ZMI_LAN_ACCESS` and `ZMI_CONTAINER_MODE` while preserving its rejection assertion. Targeted rerun passed 2/2, full security harness with Python 3.13 passed (116 passed, 3 skipped; runtime and dev audits CLEAN), and the local-only module passed 13/13 under the project Python.

### Current run recheck - 2026-10-20

- Git branch `feat/zmi-documentation-synthesis-v2`; baseline local and remote HEAD `5b7f9299eb4b9203c0d8cec96154135712525745`. Existing owner edits were preserved; no worktree created.
- Full relevant unit suite: `.venv-validation\Scripts\python.exe -m pytest tests -q --ignore=tests/integration --ignore=tests/e2e` -> `1230 passed, 8 skipped` after isolating test defaults from `.env` (`DASHBOARD_PORT`/`ZMI_BASE_URL`). This suite was rerun after adding conditional trusted-proxy scheme handling.
- Changed-source Ruff and compile checks passed; Compose `--profile lan config --quiet` passed. Current dashboard returns HTTP 200/ONLINE but serves old `9ddb5a150fbd7dd1c4d5db3cd732a6e8de007501`, not the final candidate.
- Current `/api/status`: worker `RUNNING`, 0 active jobs, 0 pending. The prior October 19 active job is no longer active. No processing job needs to be interrupted for deployment.
- The Docker app bind mounts the repository root at `/data`. Caddy profile routes desktop HTTP and LAN HTTPS to that one app/worker, avoiding a duplicate worker. Current LAN IPv4 detected from Windows interfaces: `192.168.50.20`; existing runtime CA/certificate/key are present and ignored by Git. Shared-data pre-deploy snapshot, final build, Caddy start, served-revision parity and post-deploy smoke remain pending.
- Model evidence: OpenCode GLM 5.3 loaded and completed read-only review plus the focused LAN/setup test run; Codex handled policy/docs and integration edits. No GLM authentication failure in this run (`MODEL_DEGRADED=NO`).

- First policy checkpoint `8a700a75c2f4d36db4d82eb538616c6342006ede` is committed and pushed. A subsequent GLM 5.3 read-only review found hardcoded public HTTPS/QR ports, a default Compose port collision, and Caddy certificate/startup ordering requirements. Fixed public-port generation, Caddy default HTTP port (`5003`, distinct from the app's default `5000` and HTTPS `5001`), and documented certificate-before-start. Focused LAN/setup suite now passes 31 tests; Caddy config validates; default no-env LAN profile resolves without host-port collisions. These corrections are the pending final code/SDD checkpoint; do not treat 8a700a7 as FINAL_HEAD.
- Optional confidence checks: safe synthetic integration selections `15 passed, 5 skipped` (LAN TLS interception); media crop/assembly/black-video regression `36 passed`. Process-restart integration was not run because its worker would scan the live shared root.
- Pre-deploy shared-data snapshot at `.agents/session/deployment-pre.json`: 1493 files, 15,408,846,996 bytes, 418 content SHA-256 values, metadata manifest SHA-256 `6a1ea411325a6811c8855d7cfb795be58e61a279e859cbd9464f11e65d3bd395`. Previous runtime image `sha256:6fb5774908aaf635c056c1d19021ce4d7bb10f060382983061c7edc746a65fef` is tagged `whisper-zmi:rollback-9ddb5a1`.

### Release smoke checkpoint - 2026-10-20

- Build `c59dfed45aa290aac6db96e84fcdbf30220813c5` started healthy and is served by desktop HTTP and LAN HTTPS (`192.168.50.20`); `/setup`, QR, projects, health and network API returned 200. `/api/files` returned 59 user-facing rows. The worker reports RUNNING with 0 active and 0 pending jobs.
- `tests/e2e/overview_stats_modal.py`: 12 checks PASS, including four shared metrics, X/Escape/backdrop, and mobile fit. Served UI smoke: New Recording opened; Video Editor opened for existing `Tidal.mp4`; no edits or uploads submitted.
- Advisory media note: one finalized capture appeared during the verification window and was preserved (34.866 sec, 9 files; final WebM 15,989,285 bytes; metadata reports `CROP_OUTPUT_MISMATCH`). A later `POST /api/capture/sessions/sess-ea3bff8954f6/cancel-processing` returned 200 and its two processing-chunk states became `CANCELLED`; the final WebM and all source fragment/chunk files remain present. Treat as owner UAT follow-up; do not delete or retry automatically.
- Original 1493-file baseline has no missing/changed files and all 418 selected content hashes match. Current snapshot `.agents/session/deployment-pre-finalhead.json`: 1502 files, 15,456,804,797 bytes, 419 hashes including the session JSON, metadata SHA-256 `919ccbc078524b108b9b4229e215b95bff73bd872b80acea4ea875f21ae4cdc0`.
- Compose passes configured LAN ports; resolved runtime env is HTTP 5000 / HTTPS 5001. Focused LAN/setup tests pass 31/31. At `10e1744`, HTTP, HTTPS, `/setup`, QR, network info, projects, health and modal smoke pass; current build marker matches both origins. The full unit suite passed 1230 with 8 skipped; integrations passed 15 with 5 skipped; media regression passed 36.
- Final `317ecd0` served HTTP and LAN HTTPS with matching marker; `/setup`, QR, network, files, projects and Overview UI checks passed. Worker was 0 active/0 pending. Post-smoke snapshot exactly matches the 1502-file baseline (15,456,804,797 bytes; 419 hashes; metadata SHA-256 `919ccbc078524b108b9b4229e215b95bff73bd872b80acea4ea875f21ae4cdc0`). No user files were added, removed or changed by the final smoke.
- Advisory defect: production Video Editor job `c8tdRWsMDGpD3_eYfDV_7TZf` returned `FAILED`, `Trimmed output is not fully playable` for an existing 1.46 GB `recording.webm`. The temporary output was removed by the handler; original remains unchanged. Another finalized capture has `CROP_OUTPUT_MISMATCH` and two CANCELLED processing chunks; all media remains. User acceptance/decision remains with Juan; no automatic retry or cleanup.
- Commit this defect evidence in SDD/plan/Kanban, set the resulting marker in ignored `.env`, re-serve the documentation-only HEAD without changing app sources, then verify both served markers, health, `/setup`, files/projects, worker=0 active/0 pending, and compare the same snapshot. No tracked edits after that smoke.

### Active Kanban location

The sole active feature-level Kanban is in the canonical SDD, `.agents/deliverables/US-ZMI-LIFECYCLE-001-recording-storage-docs.md`, section `Finalization Kanban`. The dated tables elsewhere in this execution plan are historical evidence only.

### Resume order

1. Relevant unit suite passes 1230 with 8 skipped; focused LAN/setup tests pass 31/31. Optional current-run checks: integration 15 passed/5 skipped, media regression 36 passed, Overview Playwright 12 passed; Host E2E/Docker E2E/security not run.
2. Push the final advisory-defect evidence in SDD/plan/Kanban. Verify final HEAD, clean worktree, worker=0 active/0 pending, rollback image and unchanged 1502-file snapshot.
3. Set `WHISPER_BUILD_REVISION=FINAL_HEAD`; re-serve the documentation-only final revision via the already-built identical app source at LAN IP `192.168.50.20`, preserving shared root/model volume.
4. Verify HTTP/HTTPS markers, health, `/setup`, QR/network, Videos/Projects, worker and snapshot. No tracked edits after this verification.
5. Report phone UAT `OWNER_PENDING`; Jenkins/Sonar/soak `NOT_REQUIRED`. Advisory defects: one large-WebM editor apply failed validation while preserving source; one retained capture has `CROP_OUTPUT_MISMATCH` and cancelled processing chunks with all media intact.
