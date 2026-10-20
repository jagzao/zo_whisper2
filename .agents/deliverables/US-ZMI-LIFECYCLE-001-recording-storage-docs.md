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

## Required deterministic gates

- targeted tests, compile/typecheck and configured lint/quality;
- FFmpeg/ffprobe synthetic integrity tests;
- security and smoke;
- full pytest and single authoritative Playwright E2E;
- Docker build/E2E and other configured CI gates;
- Sonar/Jenkins when configured (NOT_CONFIGURED is not PASS);
- production served-revision, health, shared-root and API parity checks.

The former manual ChatGPT `/review` handoff and fixed >6 GiB guard are retired. Follow the resource-aware policy and automated release criteria in `docs/plans/WHISPER_LIVE_CAPTURE_EXECUTION_PLAN.md`, section `FINAL SDD RELEASE RUN`. At <4 GiB, limit work to low-memory review/static/focused tests; at 4–6 GiB, serialize expensive operations; >=6 GiB permits standard mode. Never interrupt an active user job. Galaxy physical-device validation is tracked as `OWNER_PENDING` and does not block an otherwise accepted automated release.

## Planning

PLAN: `.agents/deliverables/PLAN-ZMI-LIFECYCLE-001-recording-storage-docs.md`
TEST MATRIX: `.agents/deliverables/TEST-MATRIX-ZMI-LIFECYCLE-001.md`

## Evidence

Complete during implementation; link exact command, result, artifact and SHA for each AC. The authoritative live Delivery Kanban and resume order are in the execution-plan `FINAL SDD RELEASE RUN` section; other dated tables are historical evidence.

## Owner interventions

Expected: 1. INITIAL_SPEC (this frozen US and production publication authorization). Physical Galaxy UAT is owner-only follow-up, not a release handoff. Unexpected: 0 unless a typed external blocker applies.

## Terminal state

`READY_FOR_DEPLOY` after implementation gates, commit and push; `RELEASED` after production deployment/verification. Galaxy phone UAT may remain `OWNER_PENDING` after release and does not hold automated delivery. `DONE` after required owner phone acceptance when available.
