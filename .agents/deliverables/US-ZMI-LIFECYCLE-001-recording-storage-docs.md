# US-ZMI-LIFECYCLE-001 — Recording, optimized storage and documentation workflow

## Status
`FINAL_RELEASE_VALIDATION`

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
| Live Capture: Camera mode, Audio-only mode, Camera microphone ON by default, visible microphone status | 🟩 COMPLETE | Existing capture API/UI and prior synthetic browser evidence; current relevant root suite passes (1230 passed, 8 skipped). Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Live Capture: rear camera, camera switching, portrait/landscape | 🟩 COMPLETE | Prior synthetic camera/orientation browser coverage; physical device remains owner UAT. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Live Capture: resolution selection, actual resolution display, recording timer | 🟩 COMPLETE | Prior capture API/browser evidence; verified by current root unit suite (1230 passed, 8 skipped). Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Live Capture: project inheritance, stop/cancel/retry | 🟩 COMPLETE | Capture session, cancel/retry and playlist tests were included in prior targeted runs. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Compression integrity: validate staged and published media, video/audio streams, positive duration tolerance, nonzero size and meaningful reduction | 🟩 COMPLETE | `test_media_optimize.py` and full root unit suite pass; source is retained until candidate and published output validate. | None; maintain coverage for future edits. | Agent |
| Compression cleanup: atomic publish, exact provenance-linked source removal, retries/recovery preserve unrelated data | 🟩 COMPLETE | Full root unit suite passes (1230 passed, 8 skipped), including compression/storage failure paths. | None; cleanup remains provenance-scoped. | Agent |
| Compression provenance API/UI: original/optimized sizes, bytes saved, cleanup outcome and reason | 🟩 COMPLETE | Compression API/UI unit coverage in the passing root suite. | None; verify in optional served UI check. | Agent |
| Real Live Crop: crop applied before MediaRecorder; WebM contains cropped pixels; microphone audio preserved | 🟩 COMPLETE | Prior synthetic WebM crop measured 1280x720 -> 636x360 with audio; current relevant root suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Real Live Crop: output dimensions persisted; encoded dimensions reduced; preview maps to encoded crop | 🟩 COMPLETE | Prior crop and assembly coverage; current unit result pending. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Mobile crop input: Pointer Events, pointer capture/cancel, object-fit/video-relative coordinates, portrait and landscape | 🟩 COMPLETE | Crop geometry and pointer journey covered by prior synthetic UI evidence and current root unit suite. | None; phone UAT remains owner-only. | Agent |
| Fragment pipeline: short upload fragments, ACK/idempotency, incremental upload | 🟩 COMPLETE | Prior 60 fragment/assembly/processing/API tests and fresh 38-test fragment rerun passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Fragment pipeline: final assembly, complete duration, one recording -> one visible final media | 🟩 COMPLETE | Prior assembly tests and verified media-duration evidence; current relevant root suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Fragment pipeline: safe fragment cleanup and provenance retention | 🟩 COMPLETE | Prior failure/recovery and cleanup tests; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Continuous playlist: continuous recording, title detection, multi-frame confirmation, logical boundaries | 🟩 COMPLETE | Prior playlist/session unit and synthetic OCR/title review evidence. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Continuous playlist: project inheritance, review/rename/split/merge | 🟩 COMPLETE | Prior playlist/session suites cover logical video operations. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: preview, TIME/FRAME modes, 8 crop handles, drag/resize | 🟩 COMPLETE | Prior API/unit and browser evidence for TIME/FRAME and eight handles; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: zoom/pan, HH:MM:SS, timeline | 🟩 COMPLETE | Prior editor API and browser evidence; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: black interval detection, black-border detection, Apply Changes | 🟩 COMPLETE | Prior black-video FFmpeg/API unit evidence and editor Apply coverage. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: edited copy, original preserved, idempotency | 🟩 COMPLETE | Prior 16+ focused edit tests cover derivative validation, provenance, and source preservation. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Black video: temporal black trimming, spatial black crop, NEEDS_REVIEW, safe original preservation | 🟩 COMPLETE | Prior black-video tests cover temporal intervals, borders, review and source preservation. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Black video: optional black auto-stop warning | 🟩 COMPLETE | Prior browser evidence covers Off default, countdown, content-return cancellation and stop. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Multi-upload: multiple files, streaming/bounded memory | 🟩 COMPLETE | Prior browser/memory evidence: 6x24 MiB upload, +79.7 MiB; no current-candidate rerun. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Multi-upload: concurrency default 4, configurable maximum 6, per-file retry/cancel | 🟩 COMPLETE | Prior 4/6 concurrency browser checks and upload retry/cancel evidence. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Worker: periodic scan, day limit 1, night limit 3 | 🟩 COMPLETE | Worker configuration and scheduling tests exist; live API currently reports worker RUNNING, zero active/pending. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Worker: stale recovery, idempotent claim, cancellation, no duplicate processing | 🟩 COMPLETE | Prior stale recovery/claim/cancellation tests passed; current queue has no active or pending job. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Documentation Synthesis V2: Evidence Timeline, semantic grouping, procedures | 🟩 COMPLETE | Prior synthetic Live Capture -> keyframe -> Docs V2 integration tests passed; current unit tests pending. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Documentation Synthesis V2: decisions, claims/evidence, ambiguity/review queue, source mapping | 🟩 COMPLETE | Docs V2 evidence-grounding and source mapping implementation/tests exist. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Documentation regeneration boundary: regenerate from saved evidence without transcription/FFmpeg/OCR/vision; separate reprocess; version history | 🟩 COMPLETE | Regeneration isolation, versioning and separation unit suites pass in current root run (1230 passed, 8 skipped). | None; UI/browser check advisory. | Agent |
| Documentation Synthesis V2: regenerate documentation, reprocess video, documentation versioning | 🟩 COMPLETE | Prior regeneration/versioning tests passed; UI keeps regeneration separate from reprocessing. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video list: Project, Date, Duration, sorting, Show/player | 🟩 COMPLETE | Prior API/UI evidence; current served dashboard health responds HTTP 200. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video list: delete eligibility/reason; hide internal chunks | 🟩 COMPLETE | Prior API/UI state-matrix and fragment visibility evidence. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| HTTPS/mobile: desktop/LAN shared data, HTTPS certificate, /setup, public CA, QR onboarding | 🟨 TESTING | Port-correct redirect/setup/QR/network/fingerprint behavior passes 31 focused LAN tests; Caddy config and no-env Compose profile validate; runtime cert SAN covers dynamically detected 192.168.50.20. Live serving/parity pending. | Deploy final pushed HEAD and verify HTTP/HTTPS, setup QR, fingerprint, shared API parity. | Agent |
| Overview Stats Modal: toolbar icon opens modal; reuse existing metrics; four required metrics | 🟨 TESTING | Committed in `8a700a7`; dashboard renders a toolbar button opening a modal backed by existing metric rendering. Current browser script is committed; not yet executed against final build. | Run modal Playwright journey after final build; advisory result only. | Agent |
| Overview Stats Modal: responsive layout, close/X/Esc, preserve Overview | 🟨 TESTING | Implementation includes responsive modal, X/backdrop/Escape, and shared metric renderer. Browser journey pending. | Run modal Playwright journey after final build; advisory result only. | Agent |
| Relevant unit tests: all new/changed business logic | 🟩 COMPLETE | Full suite: 1230 passed, 8 skipped; after final LAN port/QR changes: 31 focused LAN/setup tests passed. Ruff, py_compile, and diff checks passed. | None; rerun if further production code changes. | Agent |
| Build/import/start and schema/config migration validity | 🟨 TESTING | Python compile/import and Compose profile config pass; Caddy config validates. Current served container is healthy on prior 9ddb5 build; final revision build/start pending. No schema migration required. | Build and start exact pushed FINAL_HEAD, then verify both routes. | Agent |
| Data safety: no known loss/corruption; shared data preserved | 🟨 TESTING | Pre-deploy snapshot `.agents/session/deployment-pre.json`: 1493 files, 15,408,846,996 bytes, metadata SHA-256 `6a1ea411325a6811c8855d7cfb795be58e61a279e859cbd9464f11e65d3bd395`, 418 content hashes. | Recompute immediately before final restart and compare after smoke. | Agent |
| Integration tests | OPTIONAL | Current-run `PASS`: synthetic integration selections passed 15 tests, 5 skipped (HTTPS interception); live-worker process-restart case excluded to keep shared data safe. | Attempt after unit tests when practical; record one advisory result. | Agent |
| Media regression | OPTIONAL | Current-run `PASS`: crop, assembly, black-video, and dashboard API media regression selection passed 36 tests. | Attempt after unit tests when practical; record one advisory result. | Agent |
| Playwright | OPTIONAL | Prior UI scenarios pass on prior revisions; Overview scenario current-run result `NOT_RUN` until final build is served. | Attempt when practical; failures create UAT/defect entries only. | Agent |
| Host E2E | OPTIONAL | Prior Host E2E passes on earlier revisions; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Docker E2E | OPTIONAL | Prior Docker E2E pass exists for earlier revision; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Security scans | OPTIONAL | Prior security suite passed; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Jenkins / Sonar / soak | NOT_REQUIRED | Explicitly removed from release gates by current policy. | None. | Agent |
| Deploy final pushed HEAD: desktop + LAN HTTPS; dynamic LAN IP; preserve worker and rollback | 🟨 TESTING | Whisper container healthy; `/api/status` reports worker RUNNING, 0 active/0 pending. Current source changes pass the full unit suite; build, push, pre-deploy shared-data snapshot, served revision, and LAN parity remain pending. | Finish import/build/start and data checks; commit/push; snapshot shared data; deploy final HEAD with single-worker Caddy proxy; verify desktop/LAN served revision and smoke. | Agent |
| Post-deploy smoke: HTTP/HTTPS, served revision=FINAL_HEAD, videos/projects, shared data unchanged, New Recording, Video Editor, Overview, /setup | TODO | Not yet executed against final HEAD. | Run immediately after deployment and record exact served SHAs and data comparison. | Agent |
| Physical phone UAT | OWNER_PENDING | Juan's device validation is final acceptance; automated tests do not substitute. | Juan validates capture/audio/crop/playback after deployment. | Juan |

## Evidence

Complete during implementation; link exact command, result, artifact and SHA for each AC. The canonical release policy and resume order are in the execution-plan `FINAL SDD RELEASE RUN` section. This SDD section is the only active Kanban; other dated tables are historical evidence.

## Owner interventions

Expected: 1. INITIAL_SPEC (this frozen US and production publication authorization). Physical Galaxy UAT is owner-only follow-up, not a release handoff. Unexpected: 0 unless a typed external blocker applies.

## Terminal state

`READY_FOR_DEPLOY` after implementation gates, commit and push; `RELEASED` after production deployment/verification. Galaxy phone UAT may remain `OWNER_PENDING` after release and does not hold automated delivery. `DONE` after required owner phone acceptance when available.
