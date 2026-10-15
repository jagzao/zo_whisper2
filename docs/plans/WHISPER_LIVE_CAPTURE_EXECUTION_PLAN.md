# WHISPER LIVE CAPTURE EXECUTION PLAN

Canonical execution source for the Live Capture mission on `feat/zmi-documentation-synthesis-v2`. Keep this file current at every stage checkpoint. Work stays in this repository and branch; no merge or deploy.

## Goal

Deliver browser Live Capture integrated with Whisper's existing media, transcript and Documentation V2 flows. Preserve and complete Videos Date behavior (`recorded_at` preferred, `created_at` fallback, backend sorting, newest first). Repair the known host E2E failures. Complete required unit, integration, Playwright and applicable Docker/heavy validation; commit every stable checkpoint and synchronize the current branch.

## Current verified state

- Baseline inspected 2026-10-15: branch `feat/zmi-documentation-synthesis-v2`; HEAD `f3e9f66978b1448d74cac9a937779525520e2281`; clean worktree; tracks `origin/feat/zmi-documentation-synthesis-v2`.
- Docs V2 is present under `src/transcript_pipeline/documentation/` and wired through `transcription/processor.py` and dashboard documentation endpoints.
- Dashboard Date column and display formatter exist. `/api/files` currently emits filesystem `st_mtime` as `date`/`date_epoch`, sorts server-side by name; date sorting is client-side over the current loaded set. Required recorded/created metadata preference and server sort query remain incomplete.
- No Live Capture domain, camera UI, capture API, chunking, or lifecycle implementation found on this branch at baseline.
- `tests/test_dashboard_date_column.py` checks current column/formatter. No Live Capture tests found.
- Latest host E2E artifact: `artifacts/gates/e2e-host-data/e2e_report.json`; failures are `projects_modal_items` (0 projects in fixture) and `critical_path_no_browser_errors` (expected `/api/frames` 404 for media without frames). It does not contain the reported `TargetClosedError`. `artifacts/gates/latest.json` is an older E2E run with a separate `folders_visible` failure. Reproduce before changing lifecycle code.
- Existing `artifacts/gates/e2e-host-data/` contains generated synthetic fixtures/reports; do not treat as source-of-truth or process private media.
- Existing E2E harness: `scripts/e2e.py`, `tests/e2e/smoke_dashboard.py`; dashboard: `src/transcript_pipeline/dashboard/app.py`, `templates/dashboard.html`; docs: `src/transcript_pipeline/documentation/`.
- No source files changed during baseline inspection. Plan creation is the first implementation change.

## Non-goals

- No replacement transcription/documentation architecture, independent duplicate processing pipeline, cloud upload, or automatic media deletion.
- No private real recordings in automated tests.
- No arbitrary sleeps to hide browser races; no assertion weakening.
- No merge, deployment, history rewrite, unrelated cleanup, or broad redesign of working UI.

## Architecture decisions

- Keep capture local-first in the dashboard and browser `getUserMedia`/`MediaRecorder`; require explicit camera/microphone permission.
- Persist session/chunk metadata alongside files using a small versioned JSON manifest and atomic writes unless existing persistence patterns justify a better fit. Media stays under configured `Videos` and behind `SafePathResolver` for serving/mutation.
- Model session/chunk state explicitly; finalize bounded-duration chunks (~10–15 minutes, configurable) incrementally. Chunk N may upload/process while N+1 records. Never buffer a whole session.
- Persist session ID, chunk order, `created_at`, `recorded_at`, processing/audio/transcript states and crop metadata. Recover interrupted sessions by reconciling manifests/finalized chunks; never claim incomplete bytes are playable.
- Use `recorded_at`, then `created_at`, then filesystem timestamp for Date display/sort. Add backend sorting before pagination/filter slicing and retain sort through page/filter changes.
- Missing audio is valid (`AUDIO_MISSING` / `TRANSCRIPT_REQUIRED`); transcript/audio may arrive later with loose session/chunk association and no fabricated second-level sync.
- Route finalized media through existing `SimpleScanProcessor` / Documentation V2. Crop applicable frames and preserve source evidence plus transform metadata.
- GC is advisory only. Deletion always requires explicit user confirmation and existing safe-path validation.

## Execution stages

Stages run in dependency order; independent stages may proceed around genuine environment blockers. Status: `PENDING | IN_PROGRESS | PASS | BLOCKED`.

### W0 — Repository and evidence baseline
- Status: PASS
- Objective: establish current branch/tree, implementation, tests and gate evidence.
- Dependencies: none.
- Implementation tasks: inspect branch/HEAD/status, Date implementation, Live Capture presence, Docs V2 flow, tests and `artifacts/gates/*`.
- Relevant files/modules: `src/transcript_pipeline/dashboard/`, `src/transcript_pipeline/documentation/`, `src/transcript_pipeline/transcription/`, `tests/`, `artifacts/gates/`.
- Acceptance criteria: baseline recorded; no files mutated.
- Required tests: none.
- Validation commands: `git status --short --branch`; `git rev-parse HEAD`; targeted source/artifact inspection.
- Expected artifacts: verified-state record in this plan.
- Recovery/fallback: repeat read-only inspection; preserve all worktree state.
- Evidence: `feat/zmi-documentation-synthesis-v2`, `f3e9f66`, clean; findings above.

### W1 — Canonical execution plan
- Status: PASS
- Objective: commit this full-scope plan before further implementation.
- Dependencies: W0 PASS.
- Implementation tasks: save plan, review stages/dependencies, commit on current branch.
- Relevant files/modules: `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md`.
- Acceptance criteria: required sections/stages are present and committed; future implementation updates this file.
- Required tests: none.
- Validation commands: inspect Markdown; `git diff --check`; `git status --short`.
- Expected artifacts: plan commit.
- Recovery/fallback: restore plan from Git history; no worktree creation.

### W2 — Host E2E diagnosis and repair
- Status: IN_PROGRESS
- Objective: reproduce/fix host E2E failures, including reported Playwright `TargetClosedError` if reproducible.
- Dependencies: W1 PASS.
- Implementation tasks: trace browser/context/page ownership, fixture teardown, async tasks, navigation/reload and modal lifecycle; separately fix fixture project data and expected missing-frame requests if still failing. No sleeps.
- Relevant files/modules: `scripts/e2e.py`, `tests/e2e/smoke_dashboard.py`, `artifacts/gates/e2e-host-data/e2e_report.json`, dashboard.
- Acceptance criteria: targeted scenarios pass with no closed-object errors or browser errors; root cause recorded.
- Required tests: targeted Playwright `projects_modal_items`, `critical_path_no_browser_errors`, and relevant lifecycle tests.
- Validation commands: targeted harness invocation; then `.venv-validation\Scripts\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: updated reports/logs under `artifacts/gates/`.
- Recovery/fallback: two distinct root-cause attempts per failure; record exact environment error and continue independent work if browser unavailable.

### W3 — Capture domain and session persistence
- Status: PENDING
- Objective: create durable, recoverable session/chunk model and transitions.
- Dependencies: W1 PASS.
- Implementation tasks: versioned manifest; session identity; ordered chunks; metadata fields; atomic persistence; interrupted-session reconciliation; validated transitions.
- Relevant files/modules: focused `src/transcript_pipeline/live_capture/` or nearest existing domain; dashboard config/data roots; tests.
- Acceptance criteria: session/recording persist/reload; `created_at`, `recorded_at`, chunk ID/order and processing state survive restart; invalid transitions rejected.
- Required tests: unit chunk transitions/metadata persistence; integration session creation and recording persistence.
- Validation commands: targeted pytest; compile changed modules.
- Expected artifacts: synthetic manifest fixtures and test report.
- Recovery/fallback: rebuild indexes from valid manifests; report malformed manifests without deleting media.

### W4 — Browser camera capture UI
- Status: PENDING
- Objective: open camera, start/stop capture and clean tracks safely.
- Dependencies: W3 PASS.
- Implementation tasks: permission/error states; visible indicator; stop/error cleanup; lifecycle-safe navigation; persist finalized blobs; interrupted-capture recovery notice.
- Relevant files/modules: dashboard routes/template/JS and capture service.
- Acceptance criteria: start/stop works; tracks stop on all exits; UI mirrors recorder state; interruption leaves recoverable metadata.
- Required tests: browser start, indicator, stop, permission/error and cleanup with synthetic browser media.
- Validation commands: targeted Playwright capture suite.
- Expected artifacts: Playwright report and synthetic capture files only.
- Recovery/fallback: feature-detect MediaRecorder; show unsupported-browser state while retaining API usability.

### W5 — Bounded chunking and upload/processing
- Status: PENDING
- Objective: rotate ~10–15 minute chunks without stopping capture or unbounded memory use.
- Dependencies: W3, W4 PASS.
- Implementation tasks: configurable duration; finalize/upload N while N+1 records; bounded queue/backpressure; ordered identity; retry-safe finalization.
- Relevant files/modules: capture browser JS/service/API and tests.
- Acceptance criteria: accelerated synthetic rotation proves ordered chunks and overlap; no full-session blob accumulation; failure is retryable.
- Required tests: unit chunk states; API finalization; Playwright chunk flow.
- Validation commands: targeted pytest and Playwright chunk tests.
- Expected artifacts: synthetic manifests and gate report.
- Recovery/fallback: retain finalized chunks for retry; mark stalled upload and allow explicit retry.

### W6 — Monitor crop/mask selection
- Status: PENDING
- Objective: select useful screen region and persist crop metadata.
- Dependencies: W4 PASS.
- Implementation tasks: preview overlay/adjustable rectangle; normalized coordinates; clamp/validate; save session metadata; apply crop to generated frames where applicable and retain source.
- Relevant files/modules: dashboard template/JS, capture manifest/service, keyframe/docs integration.
- Acceptance criteria: region round-trips and deterministically crops a synthetic frame; source remains available.
- Required tests: crop normalization unit; API integration; Playwright selection/persistence.
- Validation commands: targeted pytest/Playwright with synthetic image only.
- Expected artifacts: crop metadata fixture/report.
- Recovery/fallback: invalid crop uses full frame with explicit status; never discard source.

### W7 — Audio detection and missing-audio state
- Status: PENDING
- Objective: make video-only capture a valid flow.
- Dependencies: W3, W5 PASS.
- Implementation tasks: detect usable audio; persist availability; expose `AUDIO_MISSING` and `TRANSCRIPT_REQUIRED`; UI warning; permit later transcript/audio.
- Relevant files/modules: capture processor, `media/utils.py`, dashboard API/template, tests.
- Acceptance criteria: video remains usable/documentable without audio; explicit state/warning; no forced Whisper failure.
- Required tests: audio-state unit; API no-audio processing; Playwright warning/state.
- Validation commands: targeted pytest/Playwright with synthetic audio/silent video.
- Expected artifacts: synthetic fixtures and test report.
- Recovery/fallback: probe failure becomes `AUDIO_UNKNOWN`/retryable, not fatal; document state.

### W8 — Late transcript/audio association
- Status: PENDING
- Objective: attach transcript/audio after video processing without tight-sync assumptions.
- Dependencies: W3, W7 PASS.
- Implementation tasks: safe association endpoint/UI; persist provenance/arrival time; session/chunk association; update availability without overwriting visual timeline.
- Relevant files/modules: capture API/service, transcript endpoints, file tracker integration.
- Acceptance criteria: late transcript enters existing Docs flow; loose timing is labeled; retries are idempotent.
- Required tests: association unit; API integration; synthetic transcript flow.
- Validation commands: targeted pytest/API integration.
- Expected artifacts: synthetic manifest/transcript fixture.
- Recovery/fallback: retain unattached transcript as pending; user may retry association.

### W9 — Documentation pipeline integration
- Status: PENDING
- Objective: send finalized capture through existing Whisper documentation flow.
- Dependencies: W5, W6, W7 PASS; W8 PASS for transcript-aware docs.
- Implementation tasks: discover finalized capture in existing processor; preserve metadata/crop provenance; video-first and later-transcript regeneration; no duplicate pipeline.
- Relevant files/modules: `transcription/processor.py`, `documentation/`, dashboard app.
- Acceptance criteria: synthetic capture yields existing evidence/manual/AI package; no-audio video retained; late transcript enriches docs without false second-level alignment.
- Required tests: video-to-docs integration, no-audio, late-transcript regeneration.
- Validation commands: targeted docs/processor pytest.
- Expected artifacts: synthetic documentation bundle only.
- Recovery/fallback: evidence-only output remains available when synthesis lacks transcript; never fabricate instructions.

### W10 — Advisory media GC candidates
- Status: PENDING
- Objective: surface stale, processed, documented media as deletion suggestions only.
- Dependencies: W3, W9 PASS.
- Implementation tasks: deterministic age/status/reference logic; explain reasons; require confirmation; safe-path deletion of selected item only.
- Relevant files/modules: lifecycle service, dashboard API/template, `security/SafePathResolver`, tests.
- Acceptance criteria: rules explainable; recent/referenced/incomplete media excluded; no auto-delete; confirmation required.
- Required tests: GC unit; API listing and confirmed deletion safety.
- Validation commands: targeted pytest/security path tests.
- Expected artifacts: synthetic candidate fixtures/report; no real deletion.
- Recovery/fallback: uncertain reference state excludes candidate.

### W11 — Videos Date API and server sorting
- Status: PENDING
- Objective: complete canonical Date and backend sorting while preserving UI.
- Dependencies: W3 PASS.
- Implementation tasks: prefer recorded_at, created_at fallback, filesystem fallback; server sort/direction before pagination/filter; preserve sort on page/filter changes; default newest first.
- Relevant files/modules: `dashboard/app.py`, `dashboard.html`, `tests/test_dashboard_date_column.py`, API tests.
- Acceptance criteria: display correct; API sorts entire result newest/asc/desc; recorded_at wins; filtering/pagination keep sort.
- Required tests: date fallback unit, sort/API unit, date column regression.
- Validation commands: targeted date/API pytest and Playwright date sort.
- Expected artifacts: targeted test report.
- Recovery/fallback: filesystem fallback for legacy media; unknown sort fields use stable default.

### W12 — Full unit/integration acceptance matrix
- Status: PENDING
- Objective: validate all required domain/API flows before broad browser regressions.
- Dependencies: W3, W5–W11 PASS.
- Implementation tasks: fill only requirement-tied test gaps; synthetic fixtures only.
- Relevant files/modules: `tests/` and changed package modules.
- Acceptance criteria: every UNIT and INTEGRATION/API matrix row passes.
- Required tests: all listed unit/integration cases.
- Validation commands: targeted test files, then repository pytest as policy permits.
- Expected artifacts: gate reports in `artifacts/gates/`.
- Recovery/fallback: two distinct fixes per failure, classify/document and continue independent stages.

### W13 — Playwright/E2E regression
- Status: PENDING
- Objective: verify dashboard, projects, Date and Live Capture end-to-end.
- Dependencies: W2, W4–W11 PASS.
- Implementation tasks: deterministic synthetic browser scenarios; assert no console/page errors and correct lifecycle.
- Relevant files/modules: `tests/e2e/`, `scripts/e2e.py`, dashboard.
- Acceptance criteria: every PLAYWRIGHT row passes, including host E2E.
- Required tests: critical path, projects modal, Date sort, camera start/state/stop, chunks, missing-audio/transcript-required.
- Validation commands: targeted Playwright first; `.venv-validation\Scripts\python.exe scripts/gate_runner.py e2e`.
- Expected artifacts: reports/screenshots/logs.
- Recovery/fallback: no sleeps; after two distinct fixes classify actual external/browser issue and continue others.

### W14 — Docker/heavy validation
- Status: PENDING
- Objective: verify applicable container and full repository gates.
- Dependencies: W12, W13 PASS and repository review policy permits heavy gates.
- Implementation tasks: RAM gate; full pytest/security/smoke; Docker build/E2E if configured; distinguish unavailable infrastructure.
- Relevant files/modules: `scripts/gate_runner.py`, `scripts/ram_gate.py`, `scripts/docker_gate.py`, Docker config.
- Acceptance criteria: gates pass or reproducible environment-only blocker documented.
- Required tests: full pytest, security, smoke, e2e, Docker build/E2E if applicable.
- Validation commands: `scripts/ram_gate.py`, gate runner, Docker gates.
- Expected artifacts: `artifacts/gates/latest.json`, logs/reports.
- Recovery/fallback: defer low RAM; classify missing Docker/daemon/credentials as environment blocker; never bypass policy.

### W15 — Documentation/readiness/final delivery
- Status: PENDING
- Objective: document user flows and prove committed/synchronized clean delivery.
- Dependencies: W12, W13 PASS; W14 PASS or justified environment-only BLOCKED.
- Implementation tasks: document permissions, chunk recovery/retry, crop, missing/late audio, metadata, manual deletion; update plan; commit final checkpoint; sync current branch.
- Relevant files/modules: project docs, plan, implementation/tests.
- Acceptance criteria: DoD met; statuses explicit; commits on current branch; remote SHA=HEAD; clean tree; no merge/deploy.
- Required tests: final targeted Date/Live Capture suites and applicable gate evidence.
- Validation commands: `git diff --check`, tests, status/HEAD and `git ls-remote` for branch.
- Expected artifacts: final plan/gate artifacts.
- Recovery/fallback: if push unavailable, preserve local commit and report exact external blocker.

## Global Definition of Done

Implementation complete; Date green with recorded/created preference and backend sorting; camera start/stop/error cleanup and interruption recovery; bounded chunking with concurrent next-chunk work; persisted crop metadata and applicable cropped frames; non-fatal missing audio and late transcript/audio with loose timing; durable capture metadata; existing Docs V2 integration; advisory GC and confirmation-only deletion. Required unit, API/integration, synthetic Playwright, host E2E and applicable Docker/heavy gates pass or have a justified environment-only blocker. Plan reflects evidence, commits are on this branch, remote synchronized, worktree clean; no merge/deploy.

## Test Matrix

| Layer | Required coverage | Stage | Evidence |
|---|---|---|---|
| UNIT | date selection / recorded_at / created_at fallback | W11 | pending |
| UNIT | newest default, asc/desc sorting, filter/page preservation | W11 | pending |
| UNIT | chunk state transitions | W3/W5 | pending |
| UNIT | audio-state logic | W7 | pending |
| UNIT | GC candidate logic | W10 | pending |
| INTEGRATION/API | create session; persist recording and recorded_at | W3 | pending |
| INTEGRATION/API | chunk finalization/order; processing state | W5 | pending |
| INTEGRATION/API | no-audio flow | W7 | pending |
| INTEGRATION/API | late transcript association | W8 | pending |
| INTEGRATION/API | video listing sorting | W11 | pending |
| PLAYWRIGHT/E2E | dashboard critical path; projects modal | W2/W13 | pending |
| PLAYWRIGHT/E2E | Date display and asc/desc | W11/W13 | pending |
| PLAYWRIGHT/E2E | capture start, state, stop, cleanup | W4/W13 | pending |
| PLAYWRIGHT/E2E | chunk flow where testable | W5/W13 | pending |
| PLAYWRIGHT/E2E | missing-audio warning / transcript-required | W7/W13 | pending |
| MEDIA | synthetic video/audio/silent-video/crop fixtures only | W4–W14 | pending |

## Known Risks

- Camera permissions and MediaRecorder codecs vary; use deterministic fake devices and feature detection.
- MediaRecorder timeslice events may not be standalone playable containers; verify finalization rather than assume.
- Long sessions risk storage exhaustion/backpressure; bound queues and expose stalled state.
- Crop orientation/dimensions can affect evidence; preserve originals and validate normalized coordinates.
- File tracker/filesystem may not retain capture metadata; use sidecars without breaking legacy scan.
- Saved host E2E lacks TargetClosedError; reproduce before lifecycle changes. Current failures point to fixture project data and expected missing-frame requests.
- Current Date UI sorts client-side over loaded files; backend sorting must preserve filters/pagination.
- Heavy gates follow Project Lead review/RAM policy and may require services; never claim unrun gates pass.

## Model / Executor Policy

- Routine implementation: Z.AI GLM primary; OpenCode Go/DeepSeek then local Ollama/DeepSeek fallback.
- This session exposes no model-switch API. Before code work, inspect repository routing for callable GLM worker and use it if available. If none is callable, record evidence and use only an available authorized fallback. Do not expose credentials/private endpoints.
- No nested agents unless required by configured GLM delegation.

## Progress Log

- 2026-10-15: W0 PASS. Baseline: branch `feat/zmi-documentation-synthesis-v2`, HEAD `f3e9f66`, clean. Date UI exists but metadata/backend sort incomplete. Live Capture absent. Host report shows projects fixture failure and missing-frame 404, not TargetClosedError. W1 PASS: plan written, reviewed, and committed before implementation (commit SHA recorded in Git).

## Final Delivery Checklist

- [ ] W0–W15 evidence and statuses current
- [ ] Date API/UI and fallback tests pass
- [ ] Live Capture, chunking, crop, missing-audio, late transcript, Docs V2 and GC complete
- [ ] Unit and integration/API matrix passes
- [ ] Playwright matrix and host E2E pass
- [ ] Docker/heavy pass or environment blocker documented
- [ ] Automated media fixtures are synthetic only
- [ ] User docs and recovery procedures updated
- [ ] Plan and implementation committed on current branch
- [ ] Remote branch SHA equals local HEAD
- [ ] Worktree clean; no merge/deployment
