# US-ZMI-LIFECYCLE-001 — Recording, optimized storage and documentation workflow

## Status
`FROZEN_FOR_IMPLEMENTATION`

## Parent
EPIC: `.agents/deliverables/EPIC-ZMI-LIFECYCLE-001-recording-to-knowledge.md`
FEATURE: `.agents/deliverables/FEATURE-ZMI-LIFECYCLE-001-safe-media-and-docs.md`
Analysis: `.agents/deliverables/AUDIT-ZMI-LIFECYCLE-001-recording-storage-docs.md`

## Frozen scope

Implement and close gaps recorded in the analysis and canonical W41-W45 plan. Existing W40 features are accepted baseline; verify, do not duplicate. Owner explicitly authorizes publication to the current production deployment for full UAT only after review, release gates, backup/rollback readiness, and shared-data checks pass.

## Acceptance criteria

1. [ ] AC-01 — Compression validates staged and published optimized media (container/playability, video stream, required audio behavior, measured positive duration within `max(2 sec, 5%)`, nonzero size, and meaningful size reduction) before deleting source. Evidence: synthetic FFmpeg tests and fault injection.
2. [ ] AC-02 — Source removal is limited to the exact provenance-linked source after atomic publish, persisted provenance, published hash verification, and media registration; all failures/retries preserve unrelated data and recover safely. Evidence: tests for every state transition and injected failure.
3. [ ] AC-03 — Provenance records relative source/output identity, hashes, sizes, measured durations, result and cleanup state; UI/API show size saved and cleanup outcome/reason. Evidence: schema/API/UI tests.
4. [ ] AC-04 — Live Capture assembles all ACKed fragments once, in order, validates final duration, and never removes source fragments until the final integrity and all processing chunks pass; after success only session temporary pieces are removed. Evidence: >=3-fragment regression and failure/restart tests.
5. [ ] AC-05 — Final recording duration is persisted from verified media metadata and shown correctly in Videos. Deletion control is always visible with deterministic enabled/disabled reason by media state; internal fragments/chunks are not exposed. Evidence: API/UI state matrix.
6. [ ] AC-06 — Mobile crop works with one-finger Pointer Events drag, pointer capture/cancel and video-relative coordinates for portrait/landscape and object-fit scaling. Evidence: mobile Playwright touch/pointer.
7. [ ] AC-07 — Documentation regeneration is visible on mobile and desktop, regenerates from saved evidence, records/selects a version, reports status, and does not invoke transcription, FFmpeg/keyframes, OCR or vision. Reprocess remains separate. Evidence: service spies and Playwright.
8. [ ] AC-08 — localhost:5000 and the current LAN HTTPS origin serve the same revision/backend and equivalent video/project/job/docs/worker state from one configured data/database/media root. Evidence: config, served build markers, normalized API parity.
9. [ ] AC-09 — Synthetic full workflow and Host E2E pass; production services are restarted from final reviewed HEAD and health/UI parity verified. Production UAT uses existing user data read-only except explicitly safe app-generated synthetic records; no real source is deleted as a test. Evidence: gate artifacts and deployment/rollback record.
10. [ ] AC-10 — Full applicable automated release gates pass under the current resource-aware RAM policy; DELIVERY records exact SHAs, tests, deployment health, residual risks and rollback path. Evidence: machine-readable gate artifacts and final DELIVERY.

## Non-goals

- Delete arbitrary original files, internal chunks, or unlinked paths.
- Age-only garbage collection or bulk cleanup.
- Changing Docs V2 semantics or invoking expensive reprocessing for regeneration.
- Second Brain publisher feature work.
- Deploying a different environment/account than the current Whisper desktop+LAN production services.

## Release gates and policy (canonical, 2026-10-19)

This section supersedes the former deterministic-gate list, the fixed `>6 GiB` guard and every earlier requirement that integration tests, full-suite runs, Playwright/E2E, Docker build/E2E, Jenkins, Sonar, soak or phone UAT must pass for release. The hard-blocker list, advisory-test policy, and release workflow are in `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md`, section `FINAL SDD RELEASE RUN`. The only active feature-level Kanban is this SDD's `Finalization Kanban` section.

Hard blockers — the only conditions that block release:

1. Incomplete requested implementation.
2. Relevant unit tests fail.
3. App build or start fails.
4. Known data loss or corruption.
5. Unsafe restart that would lose the active user job and cannot be isolated or recovered.

Advisory gates (integration, E2E, Playwright, Host E2E, Docker build/E2E, security and any other optional check) record exactly one result: `PASS`, `FAIL_ADVISORY`, `ENV_BLOCKED`, `NOT_CONFIGURED`, `NOT_RUN`. Advisory results never block release, and `PASS` is never recorded without executed evidence from the current run. Integration tests, Playwright, Host E2E, Docker E2E, heavy gates, fixed RAM thresholds, Jenkins, Sonar, soak, and physical phone UAT are not publication gates. Jenkins, Sonar and soak are `NOT_REQUIRED`. RAM affects execution strategy only (ordering, serialization, deferral); it never decides release eligibility, and no active user job is ever interrupted to manufacture headroom. Physical Galaxy phone UAT is `OWNER_PENDING` owner verification and does not hold release. GLM is the preferred executor; on GLM auth/provider failure degrade to the cheapest available fallback — provider routing is an execution detail, never a project blocker.

Mandatory engineering Definition of Done: scope complete per this US; no TODO/mock in requested production functionality; relevant unit tests pass; app builds/imports/starts; migrations valid; data safety preserved; code + SDD + Kanban committed and pushed. Deployment requires the final pushed HEAD, a preserved active job/worker, served-revision and shared-data parity verification, and the required lightweight post-deploy smoke (dashboard loads, Videos list renders, worker status, `/setup` reachable, served revision matches).

## Planning

PLAN: `.agents/deliverables/PLAN-ZMI-LIFECYCLE-001-recording-storage-docs.md`
TEST MATRIX: `.agents/deliverables/TEST-MATRIX-ZMI-LIFECYCLE-001.md`

## Finalization Kanban (authoritative - sole active Kanban)

This is the one active feature inventory and execution table for this SDD. All dated Kanbans in historical artifacts are evidence only. Allowed statuses: `TODO`, `🟦 DEVELOPING`, `🟨 TESTING`, `🟥 BLOCKED`, `🟩 COMPLETE`, `OWNER_PENDING`, `OPTIONAL`, `NOT_REQUIRED`.

| Feature / Gate | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Live Capture: Camera mode, Audio-only mode, Camera microphone ON by default, visible microphone status | 🟨 TESTING | Existing capture API/UI and prior synthetic browser evidence; rerun focused unit coverage on this candidate. | Run relevant capture unit tests; record advisory UI evidence if practical. | Agent |
| Live Capture: rear camera, camera switching, portrait/landscape | 🟨 TESTING | Prior synthetic camera/orientation browser coverage; physical device remains owner UAT. | Run relevant unit tests; retain phone verification as owner follow-up. | Agent |
| Live Capture: resolution selection, actual resolution display, recording timer | 🟨 TESTING | Prior capture API/browser evidence; current-candidate unit run pending. | Run focused capture tests and verify start/build smoke. | Agent |
| Live Capture: project inheritance, stop/cancel/retry | 🟨 TESTING | Capture session, cancel/retry and playlist tests were included in prior targeted runs. | Rerun relevant unit tests. | Agent |
| Real Live Crop: crop applied before MediaRecorder; WebM contains cropped pixels; microphone audio preserved | 🟨 TESTING | Prior synthetic WebM crop measured 1280x720 -> 636x360 with audio; verify relevant unit/regression coverage on this candidate. | Run crop/capture unit tests; advisory browser check if practical. | Agent |
| Real Live Crop: output dimensions persisted; encoded dimensions reduced; preview maps to encoded crop | 🟨 TESTING | Prior crop and assembly coverage; current unit result pending. | Run crop metadata/API unit tests. | Agent |
| Fragment pipeline: short upload fragments, ACK/idempotency, incremental upload | 🟨 TESTING | Prior 60 fragment/assembly/processing/API tests and fresh 38-test fragment rerun passed. | Rerun relevant fragment unit tests. | Agent |
| Fragment pipeline: final assembly, complete duration, one recording -> one visible final media | 🟨 TESTING | Prior assembly tests and verified media-duration evidence; rerun current candidate. | Run assembly, duration, and video-list unit tests. | Agent |
| Fragment pipeline: safe fragment cleanup and provenance retention | 🟨 TESTING | Prior failure/recovery and cleanup tests; no current-run evidence yet. | Run cleanup/provenance unit tests and inspect storage state transitions. | Agent |
| Continuous playlist: continuous recording, title detection, multi-frame confirmation, logical boundaries | 🟨 TESTING | Prior playlist/session unit and synthetic OCR/title review evidence. | Run playlist/title boundary unit tests. | Agent |
| Continuous playlist: project inheritance, review/rename/split/merge | 🟨 TESTING | Prior playlist/session suites cover logical video operations. | Run playlist mutation unit tests; UI test optional. | Agent |
| Video editor: preview, TIME/FRAME modes, 8 crop handles, drag/resize | 🟨 TESTING | Prior API/unit and browser evidence for TIME/FRAME and eight handles; candidate unit run pending. | Run editor/API unit tests. | Agent |
| Video editor: zoom/pan, HH:MM:SS, timeline | 🟨 TESTING | Prior editor API and browser evidence; candidate unit run pending. | Run timecode/timeline unit tests. | Agent |
| Video editor: black interval detection, black-border detection, Apply Changes | 🟨 TESTING | Prior black-video FFmpeg/API unit evidence and editor Apply coverage. | Run relevant black-video/editor unit tests. | Agent |
| Video editor: edited copy, original preserved, idempotency | 🟨 TESTING | Prior 16+ focused edit tests cover derivative validation, provenance, and source preservation. | Rerun edit lifecycle unit tests. | Agent |
| Black video: temporal black trimming, spatial black crop, NEEDS_REVIEW, safe original preservation | 🟨 TESTING | Prior black-video tests cover temporal intervals, borders, review and source preservation. | Rerun black-video unit suite. | Agent |
| Black video: optional black auto-stop warning | 🟨 TESTING | Prior browser evidence covers Off default, countdown, content-return cancellation and stop. | Unit checks if logic changed; browser evidence advisory. | Agent |
| Multi-upload: multiple files, streaming/bounded memory | 🟨 TESTING | Prior browser/memory evidence: 6x24 MiB upload, +79.7 MiB; no current-candidate rerun. | Run upload service unit tests; memory test advisory. | Agent |
| Multi-upload: concurrency default 4, configurable maximum 6, per-file retry/cancel | 🟨 TESTING | Prior 4/6 concurrency browser checks and upload retry/cancel evidence. | Run upload concurrency/retry unit tests. | Agent |
| Worker: periodic scan, day limit 1, night limit 3 | 🟨 TESTING | Worker configuration and scheduling tests exist; live API currently reports worker RUNNING, zero active/pending. | Run worker schedule/config unit tests. | Agent |
| Worker: stale recovery, idempotent claim, cancellation, no duplicate processing | 🟨 TESTING | Prior stale recovery/claim/cancellation tests passed; current queue has no active or pending job. | Rerun worker lifecycle unit tests. | Agent |
| Documentation Synthesis V2: Evidence Timeline, semantic grouping, procedures | 🟨 TESTING | Prior synthetic Live Capture -> keyframe -> Docs V2 integration tests passed; current unit tests pending. | Run Docs V2 unit tests. | Agent |
| Documentation Synthesis V2: decisions, claims/evidence, ambiguity/review queue, source mapping | 🟨 TESTING | Docs V2 evidence-grounding and source mapping implementation/tests exist. | Run Docs V2 synthesis and provenance unit tests. | Agent |
| Documentation Synthesis V2: regenerate documentation, reprocess video, documentation versioning | 🟨 TESTING | Prior regeneration/versioning tests passed; UI keeps regeneration separate from reprocessing. | Run regeneration/versioning unit tests. | Agent |
| Video list: Project, Date, Duration, sorting, Show/player | 🟨 TESTING | Prior API/UI evidence; current served dashboard health responds HTTP 200. | Run video API unit tests; verify in post-deploy smoke. | Agent |
| Video list: delete eligibility/reason; hide internal chunks | 🟨 TESTING | Prior API/UI state-matrix and fragment visibility evidence. | Run deletion policy/list filtering unit tests. | Agent |
| HTTPS/mobile: desktop/LAN shared data, HTTPS certificate, /setup, public CA, QR onboarding | 🟨 TESTING | Prior deployment/setup evidence on earlier served build; current runtime revision and LAN parity not yet measured. | Inspect deployment config; verify dynamically discovered LAN service after deploy. | Agent |
| Overview Stats Modal: toolbar icon opens modal; reuse existing metrics; four required metrics | 🟦 DEVELOPING | Dashboard template change and untracked Playwright scenario exist; current focused test/commit evidence pending. | Run relevant dashboard unit/import/build checks; then commit code and docs. | Agent |
| Overview Stats Modal: responsive layout, close/X/Esc, preserve Overview | 🟦 DEVELOPING | Implementation includes responsive modal, X/backdrop/Escape and shared metric renderer; browser test not run. | Run UI scenario as advisory when practical; mark evidence accurately. | Agent |
| Relevant unit tests: all new/changed business logic | 🟩 COMPLETE | `.venv-validation\Scripts\python.exe -m pytest tests -q --ignore=tests/integration --ignore=tests/e2e`: 1230 passed, 8 skipped (2026-10-20), rerun after trusted-proxy change. | None; rerun after future source edits. | Agent |
| Build/import/start and schema/config migration validity | 🟨 TESTING | Current Whisper container reports healthy; running revision/build identity and migration validation pending. | Build/import and startup check on final candidate. | Agent |
| Data safety: no known loss/corruption; shared data preserved | 🟨 TESTING | No user data was intentionally changed; pre-deploy counts/hashes have not yet been captured for this run. | Snapshot media/project/job/docs metadata before deploy and compare after. | Agent |
| Integration tests | OPTIONAL | Prior evidence exists; current-run result `NOT_RUN` (unit suite already includes feature unit coverage). | Attempt after unit tests when practical; record one advisory result. | Agent |
| Media regression | OPTIONAL | Prior synthetic crop/assembly/black-video evidence; current-run result `NOT_RUN`. | Attempt after unit tests when practical; record one advisory result. | Agent |
| Playwright | OPTIONAL | Prior UI scenarios pass on prior revisions; Overview scenario current-run result `NOT_RUN` until final build is served. | Attempt when practical; failures create UAT/defect entries only. | Agent |
| Host E2E | OPTIONAL | Prior Host E2E passes on earlier revisions; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Docker E2E | OPTIONAL | Prior Docker E2E pass exists for earlier revision; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Security scans | OPTIONAL | Prior security suite passed; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Jenkins / Sonar / soak | NOT_REQUIRED | Explicitly removed from release gates by current policy. | None. | Agent |
| Deploy final pushed HEAD: desktop + LAN HTTPS; dynamic LAN IP; preserve worker and rollback | 🟥 BLOCKED | Whisper container healthy; `/api/status` reports worker RUNNING, 0 active/0 pending. Current source changes pass the full unit suite; build, push, pre-deploy shared-data snapshot, served revision, and LAN parity remain pending. | Finish import/build/start and data checks; commit/push; snapshot shared data; deploy final HEAD with single-worker Caddy proxy; verify desktop/LAN served revision and smoke. | Agent |
| Post-deploy smoke: HTTP/HTTPS, served revision=FINAL_HEAD, videos/projects, shared data unchanged, New Recording, Video Editor, Overview, /setup | TODO | Not yet executed against final HEAD. | Run immediately after deployment and record exact served SHAs and data comparison. | Agent |
| Physical phone UAT | OWNER_PENDING | Juan's device validation is final acceptance; automated tests do not substitute. | Juan validates capture/audio/crop/playback after deployment. | Juan |

## Evidence

Complete during implementation; link exact command, result, artifact and SHA for each AC. The canonical release policy and resume order are in the execution-plan `FINAL SDD RELEASE RUN` section. This SDD section is the only active Kanban; other dated tables are historical evidence.

## Owner interventions

Expected: 1. INITIAL_SPEC (this frozen US and production publication authorization). Physical Galaxy UAT is owner-only follow-up, not a release handoff. Unexpected: 0 unless a typed external blocker applies.

## Terminal state

`READY_FOR_DEPLOY` after implementation gates, commit and push; `RELEASED` after production deployment/verification. Galaxy phone UAT may remain `OWNER_PENDING` after release and does not hold automated delivery. `DONE` after required owner phone acceptance when available.
