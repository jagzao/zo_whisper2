# US-ZMI-LIFECYCLE-001 — Recording, optimized storage and documentation workflow

## Status
`RELEASED_OWNER_UAT_PENDING`

## CURRENT_RESULT

STATUS=PARTIAL_BLOCKED
HEAD=IMPLEMENTATION_HEAD=3ec6bb6fc22c4ef665275c8ef5947521fc2b1cf9; RESULT_COMMIT_HEAD=commit containing this CURRENT_RESULT section
REMOTE_HEAD=origin/main contains implementation 3ec6bb6fc22c4ef665275c8ef5947521fc2b1cf9; this result update will be pushed separately
SERVED_HEAD=74799c205c6f399aeecfa927a8baefba73aa69ba (prior app; new image built but deployment held to protect active uploads)
DEVELOPMENT_COMPLETE=NO - served validation and several software journeys/runtime stability remain blocked or unverified
UNIT=PASS - 98 focused dashboard/API tests; py_compile and git diff --check pass
INTEGRATION=PARTIAL - served upload, auto-start, P&G defaults, Docs UI/history, resume, MP4/WebM editor playback tested; processing, Docs semantic regeneration, crop, playlist and several other journeys remain unverified
DEPLOYED=NO for 3ec6bb6 - prior app is served; ZMI healthy, restart count 1 since recreation; exit 0/OOM=false; cause of prior restarts unproven
KANBAN_COMPLETE=7
KANBAN_IN_PROGRESS=0
KANBAN_TESTING=60
KANBAN_BLOCKED=4
KANBAN_OWNER_PENDING=3
CURRENT_WORK=Preserve five active owner uploads and stale worker lease; deploy logical counters after uploads complete; continue runtime and remaining served journeys
LAST_COMPLETED=Served MP4 and WebM editor Apply flows created playable derivatives with audio and preserved originals; capture shell reached fake-device recording and finalized fragments
BLOCKER=Five existing resumable upload sessions remain UPLOADING; deployment restart could interrupt them. Owner job `a5baabf678944da7b463677ed566140f` remains ACTIVE with ~5.1h heartbeat age under the six-hour recovery threshold; do not alter. Docs provider key absent and ALLOW_EXTERNAL_LLM=false. /api/folders timed out during read-only served sampling; restart cause unproven.
NEXT_ACTION=Wait for owner uploads to settle, then deploy 3ec6bb6 and verify actual served cards/table. Keep watching worker via existing policy; do not cancel/requeue owner work. Resume Docs only when authorized provider configuration is available.
RULE_CONFLICT=YES - owner completion semantics supersede prior implementation/test-based green statuses

DROPAREA_REAL_UPLOAD=PARTIAL - two synthetic files finalized and processing queued; worker blockage prevented validation in Videos
DROPAREA_AUTO_START=PASS - selecting two synthetic files started both without pressing Upload Selected
DROPAREA_MULTI_FILE=PASS - two synthetic files independently completed upload/finalize
DEFAULT_PROJECT_UPLOAD=PASS - P&G selected by default and assigned to both uploads
DEFAULT_PROJECT_RECORDING=PASS - P&G selected in New Recording; explicit Zo Interviews choice persisted on reopen
DOCS_V2_REAL_UI=PARTIAL - P&G Tidal documentation opened with summary/manual, evidence links, review count, metadata, and separate Reprocess control
DOCS_V2_REAL_DOCUMENT=PARTIAL - existing v2 shown; full semantic evidence/timeline content and all requested fields not validated end-to-end
DOCS_V2_REGENERATE=BLOCKED - served regeneration created v3 SYNTHESIS_BLOCKED_PRIVACY; no remote corpus sent
DOCS_V2_VERSION_HISTORY=PASS - regeneration selected v3; prior v1/v2 remained accessible; v1 reopened
LIVE_CAPTURE=TESTING - served fake-device capture finalized fragments with audio; legacy automation timed out expecting Preview after Start (served state is Recording); physical device remains OWNER_PENDING
REAL_CROP=TESTING - prior synthetic evidence only; current served capture/crop journey unverified
PLAYLIST=TESTING - current served continuous capture/review journey unverified
VIDEO_EDITOR=TESTING - served MP4 and WebM Edit/Apply created playable video+audio derivatives; both originals preserved; prior source-specific large WebM failure source is unavailable for safe reproduction
WORKER=BLOCKED - stale ACTIVE owner job and repeated container restarts; synthetic processing did not reach Videos
VIDEOS_TABLE=TESTING - selected listing/player/docs paths opened; full columns/sort/delete reason/internal-fragment journey not verified
HTTPS_MOBILE=TESTING - LAN HTTPS health and build marker pass; physical phone certificate/onboarding remains OWNER_PENDING

### Latest execution result

Dashboard inventory counter phase (2026-10-23): `/api/files` now includes logical `videos`, `audio`, and nonempty-transcription metrics computed from its exact visible row set; primary cards consume those values. `/api/folders` retains raw filesystem diagnostics and exposes the pending upload queue count separately. Added secondary, collapsed Storage diagnostics. Targeted tests: 98 passed, including 48 physical video files / 12 visible logical rows, hidden capture fragments, test session exclusion, audio, orphan/empty transcript exclusion and API reconciliation. `py_compile` and `git diff --check` pass. Commit `3ec6bb6` is pushed; Docker image built successfully with this revision. Deployment waits because five existing sessions are `UPLOADING`. Prior served API baseline: 12 logical videos, 0 audio, 9 transcribed; response has no metrics field. A read-only `/api/folders` probe timed out. Status stays TESTING until deployment and actual UI/table comparison. No owner media or upload data was changed.

DASHBOARD_COUNTERS_LOGICAL=IMPLEMENTED; not served yet
VIDEOS_LOGICAL_COUNT=12 prior served /api/files rows; 12 fixture rows from 48 physical files
AUDIO_LOGICAL_COUNT=0 prior served /api/files rows; logical audio fixture passes
TRANSCRIBED_LOGICAL_COUNT=9 prior served logical rows; fixture excludes orphan/empty .txt files
RAW_STORAGE_DIAGNOSTICS=preserved in collapsed secondary section; served raw diagnostics probe timed out
COUNTERS_MATCH_FILES_API=PASS in isolated tests; served comparison pending
SERVED_VALIDATION=BLOCKED_PENDING_UPLOADS (5 sessions UPLOADING; old app still served)
WORKER=BLOCKED; owner job remains active, ~5.1h heartbeat age, stale threshold 6h
DOCS_V2_REGENERATE=BLOCKED; provider key absent and ALLOW_EXTERNAL_LLM=false
VIDEO_EDITOR=TESTING (prior source-specific large WebM failure unresolved)
LIVE_CAPTURE=TESTING
REAL_CROP=TESTING
PLAYLIST=TESTING
VIDEOS_TABLE=TESTING
DEVELOPMENT_COMPLETE=NO
KANBAN_COMPLETE=7
KANBAN_TESTING=60
KANBAN_BLOCKED=4
KANBAN_OWNER_PENDING=3
SERVED_HEAD=74799c205c6f399aeecfa927a8baefba73aa69ba
BLOCKER=Five active uploads; deployment restart held to protect them
NEXT_ACTION=After uploads settle, deploy 3ec6bb6, compare cards to unfiltered table, validate filters unchanged, then resume worker/runtime and remaining SDD priorities.

Actual served revision `74799c205c6f399aeecfa927a8baefba73aa69ba` returned HTTPS `/api/health` 200 JSON and `/api/uploads` 200 JSON. Container is running/healthy at report time with restart count 4; inspect reports exit 0 and OOM=false, while retained logs do not identify the restart cause. During test execution the app timed out/unresponded and restarted. Caddy remained up. Persistent media and acknowledged owner upload sessions were not altered.

Drop Area on served build: selected two valid 12 KB synthetic MP4 files. Both immediately entered upload, completed one-chunk resumable upload/finalize under P&G without the Upload Selected button, and queued processing. No browser JS errors or failed network requests. The test jobs, files and sessions were individually removed after the run. They did not appear in Videos because the worker remained blocked by a pre-existing ACTIVE owner job; that job was left untouched. Thus auto-start and multi-file upload pass, but the full journey through processing/Videos does not.

P&G was the default in Drop Area and New Recording. Changing New Recording to Zo Interviews and reopening preserved the explicit choice. Capture itself was not started.

Resumable recovery: a synthetic 12.4 MB upload received five simulated HTML 502 responses for a chunk. UI retained ACK chunk 0 and showed an upload-specific 502 error. Retry in the first page stalled while the service became unstable. After reopening the served page and selecting the same file, upload resumed from the saved session and completed. Exact synthetic job `b63a4220012241ac8cd6e242c7a9ac83`, media `pg_zmi_retry_2.mp4`, session `55e35df40d0d474c97e9f463cb3dd652`, and local fixture were cleaned up; no user media/session was touched.

Docs V2: opened P&G `pg_Tidal.mp4`; UI showed v2 metadata, generated timestamp, human manual, AI package, procedure/review counts, evidence/source links, version selector and separate Reprocess Video. Regenerate created/selects v3 with `SYNTHESIS_BLOCKED_PRIVACY`; v1/v2 remained available and v1 reopened. No transcription/reprocess endpoint ran. Host/container had no OPENCODE_API_KEY and `ALLOW_EXTERNAL_LLM=false`; repository privacy policy blocks remote generation. No corpus content was sent and no saved CLI credentials were used. Historical corpus result (9/9 versions, 393 grounded claims, 273 review items) is preserved below and remains historical until revalidated as a served user journey.

Focused tests rerun on source: Python `tests/test_documentation_versioning.py`, `tests/security/test_dashboard_endpoints.py`, `tests/test_documentation_v2_regenerate_review.py`, `tests/test_documentation_v2_batch.py`, `tests/test_resumable_uploads.py`, `tests/test_processing_worker.py`: 92 passed. Node `tests/js/upload_reliability.test.cjs`: 9 passed. These are engineering evidence only and do not make visible features complete.

Latest served editor verification: from Videos, opened safe synthetic MP4 and WebM in Edit, applied trim, observed completed validated edit jobs, opened the derivative in the player, and confirmed playback advanced with `readyState=4`, video+audio streams and 6-second duration. Original SHA-256 values were unchanged. Safe source, derivative and provenance fixtures were removed. The previously failing 1.46 GiB owner/source WebM was not present; that exact failure remains unreproduced and no owner media was touched.

Latest served capture probe: fake-device New Recording entered recording and uploaded/finalized fragments, but the old E2E script timed out waiting for the UI label `Preview` after pressing Start; the served state machine correctly displayed `Recording`. Its assertions also assume no project is selected by default, which conflicts with the accepted P&G default. The script explicitly selected `Zo Interviews`, so this run does not validate P&G default, crop-before-recorder or playlist boundaries. Two test-tagged capture sessions (`sess-e1747a44ac2a`, `sess-4096000964ee`) finalized synthetic data. The app rejected their delete requests because finalized processing chunks are protected; they are not owner media and were not force-deleted. No synthetic pending processing jobs were reported; the only active job remains the pre-existing owner job. Update the test journey to current UI semantics before another capture run.

Runtime observation during this phase: container remained `Up (healthy)`, restart count 4, exit 0/OOM=false. One Docker health probe timed out while upload chunk requests were active; subsequent probe passed and the app continued returning health 200. This does not establish the cause of historical restarts or the timeout.

### 🟥 RULE CONFLICT
Existing rule: features were marked COMPLETE mainly from implementation, unit tests, synthetic browser/API checks, or artifact existence.
New instruction: a user-facing feature is COMPLETE only after its complete user journey passes against the actual served build.
Conflict: previous green statuses overstate validated product behavior.
Regression risk: unverified journeys, worker/runtime failures, or blocked Docs generation could be represented as usable to the owner.
Recommended resolution: apply the new served-journey completion rule; retain prior results as historical evidence and downgrade current statuses truthfully.
Preserved behavior until resolution: keep validated code, existing media, source artifacts, version history, and acknowledged owner upload chunks intact.

### Historical execution result (preserved)

Physical UAT screenshot showed two `Failed - Failed to fetch` entries and one 6.3 GB upload in progress. Browser fetch rejection provides no HTTP response/status; exact failed URL/method could not be recovered. Docker recorded a ZMI OOM kill (exit 137) at 2026-10-22 18:13:33 UTC, restart at 18:13:36, and healthy status at 18:13:42. This is a plausible outage source, not proven attribution for each screenshot error. The existing persistent upload session survived with 8 acknowledged 8 MiB chunks (64 MiB). No real file was retried, canceled, or deleted.

Fix: transient network errors and HTTP 5xx now retry up to five times during preflight, session creation/status, and finalize. Chunk upload keeps its same-chunk retry and durable ACK map. Network errors tell the user Retry resumes acknowledged chunks. Tests: `tests/test_resumable_uploads.py` 10 passed; `tests/js/upload_reliability.test.cjs` 9 passed. Candidate image starts healthy and its synthetic API create/cleanup passed. Production ZMI serves build `a99effb`; localhost HTTP and LAN HTTPS return 200. Served HTML includes retry logic. Production synthetic POST `/api/uploads`, chunk ACK, status/resume, and cleanup returned JSON 200; invalid synthetic finalize returned JSON 409. The original session remains at 8 ACKed chunks. Host and `/data` had about 184 GiB free; 2 GiB reserve remains. Caddy was not restarted; `/data` bind and model-cache volume were preserved. Real-file UAT is owner-pending. Advisory checks remain advisory under the current release policy.

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
11. [ ] AC-11 — Edit File supports a trimmed, validated display name without a typed extension; preserves the media extension, rejects unsafe/empty/colliding names, and persists the name by stable media ID without moving media or changing transcript, project, documentation, provenance, or processing history. Rename is idempotent and does not trigger processing. Evidence: `tests/test_dashboard_display_name.py`.
12. [x] AC-12 — Docs V2 supports corpus inventory and resumable batch regeneration from saved evidence, captures provider/model/privacy profile in version history, and never marks evidence-only output as semantic documentation. Missing upstream artifacts are reported separately. Evidence: `transcript_pipeline.documentation.batch_regenerate_v2`, `tests/test_documentation_v2_batch.py`, and per-video version manifests.
13. [ ] AC-13 — Global health/error presentation distinguishes service offline, worker error, active processing-stage error, and historical job failure. Each visible failure explains component, message, timestamp and affected file/job; resolved historical jobs do not poison current health. Evidence: focused classification/API/UI tests.
14. [ ] AC-14 — Screen Wake Lock is requested only when recording, continuous playlist capture, or foreground upload needs it; visibility, orientation, release and re-acquire are handled; unsupported browsers report unavailable. Evidence: deterministic Wake Lock lifecycle tests.
15. [ ] AC-15 — Multi-GB uploads use persistent upload sessions with bounded hashed chunks, ACK map, retry/resume, per-file cancel, and finalize size/hash/media validation before normal processing enqueue. Browser restart can discover resumable sessions and resume already ACKed chunks without re-sending them. Evidence: chunk/API/UT recovery tests.
16. [ ] AC-16 — Upload queue adapts simultaneous file count to file size, queued bytes, active transfers, backend health, network failures and available resources. Maximum remains six. Upload cards expose size, progress, percentage, speed, ETA, state, pause/resume/cancel/retry. Evidence: scheduler and UI tests.

### 🟥 RULE CONFLICT — adaptive upload concurrency

Earlier accepted SDD behavior fixes default upload concurrency at 4 and maximum at 6. This request explicitly reconciles that rule: adaptive scheduling replaces the fixed default, with the accepted maximum of 6 preserved. The prompt's shorthand “24” / “12” is interpreted as 2–4 medium and 1–2 multi-GB files, consistent with the explicit maximum. Keep this 🟥 RULE CONFLICT record as the change audit trail; the implementation below follows this explicit reconciliation.

## Non-goals

- Delete arbitrary original files, internal chunks, or unlinked paths.
- Age-only garbage collection or bulk cleanup.
- Changing Docs V2 semantics or invoking expensive reprocessing for regeneration.
- Second Brain publisher feature work.
- Deploying a different environment/account than the current Whisper desktop+LAN production services.

## Release gates and policy (authoritative, 2026-10-22)

This policy resolves conflicting earlier SDD and plan rules. It supersedes every earlier release rule, including E2E/security/repo-wide quality requirements and arbitrary RAM thresholds.

Hard deployment gates (only):
1. Requested production implementation is complete.
2. Relevant unit tests pass.
3. Application builds, imports, and starts.
4. No known data corruption or loss risk.
5. Enough storage exists for safe operation; unsafe uploads must be rejected before beginning/finalizing.
6. Restart is safe and preserves active work and persistent data.

Integration, Playwright/E2E, Docker E2E, security scans, repository-wide legacy Ruff/Pyright findings, Jenkins, Sonar, soak, and arbitrary RAM thresholds are advisory. Record results honestly; advisory failures do not block deployment. Storage safety is evaluated for each upload and deployment. Real large-file UAT remains owner-run.

Deploy the requested implementation after all six hard gates pass. Preserve persistent volumes and rollback image. Verify candidate build and served endpoints/UI, including `/api/uploads`, chunks, resume/status, and finalize. Do not start real owner media during smoke tests.


## 🟥 RULE CONFLICT POLICY

Within project-defined rules, this policy has highest priority. If a new request conflicts with an SDD requirement, approved architecture decision, validated behavior, release/resource policy, or another current requirement, do not silently select a side or regress validated behavior. Record `RULE_CONFLICT=YES` in `## CURRENT_RESULT`, followed by:

### 🟥 RULE CONFLICT
Existing rule:
New instruction:
Conflict:
Regression risk:
Recommended resolution:
Preserved behavior until resolution:

## 🟥 USER-FACING COMPLETION SEMANTICS

This owner rule supersedes earlier completion interpretations in this SDD and its execution plan. Unit tests, implementation, synthetic browser/API checks, or artifact existence alone do not complete user-facing functionality. Such features remain `🟨 TESTING` until their full journey passes against the actual served build. Only physical-device behavior that cannot be verified without the device may remain `OWNER_PENDING`. Preserve existing validated behavior while reopening unverified rows; do not downgrade or remove historical evidence.

Preserve previously validated behavior unless the new instruction explicitly supersedes it. This policy does not override platform, security, or system constraints. Only one SDD per repository may be pointed to as active for `/revisa`; update `.agents/CURRENT.json` when the canonical active SDD changes.

## Planning

PLAN: `.agents/deliverables/PLAN-ZMI-LIFECYCLE-001-recording-storage-docs.md`
TEST MATRIX: `.agents/deliverables/TEST-MATRIX-ZMI-LIFECYCLE-001.md`

## Finalization Kanban (authoritative - sole active Kanban)

This is the one active feature inventory and execution table for this SDD. All dated Kanbans in historical artifacts are evidence only. Allowed statuses: `TODO`, `🟦 DEVELOPING`, `🟨 TESTING`, `🟥 BLOCKED`, `🟩 COMPLETE`, `OWNER_PENDING`, `OPTIONAL`, `NOT_REQUIRED`.

| Feature / Gate | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Drop Area: auto-start, two-file resumable upload, P&G assignment | 🟨 TESTING | Served build `74799c2`; two synthetic MP4s auto-uploaded/finalized and queued without extra click; P&G assigned; no JS/network errors. Worker did not process them into Videos; synthetic records cleaned. | Fix worker/runtime; repeat through Videos with safe synthetic media. | Agent |
| Upload retry/resume after simulated 502 | 🟨 TESTING | Served synthetic 12.4 MB upload: five chunk 502s, ACK 0 preserved, upload-specific 502 shown; fresh-page reselect resumed and completed. Retry-in-place stalled during service instability. Test records cleaned. | Stabilize ZMI and repeat pause/retry/resume journey; verify processing result. | Agent |
| P&G default: uploads and New Recording | 🟨 TESTING | Served UI selected P&G for uploads and New Recording; explicit Zo Interviews choice persisted after reopening. Camera/audio/playlist capture not started. | Verify project inheritance through real served capture and playlist journeys; phone-only hardware checks by Juan. | Agent |
| Docs V2 served UI, document and version history | 🟨 TESTING | Served P&G Tidal v2 opened with manual/package, metadata, evidence links, review count, versions v1/v2 and separate Reprocess. Regeneration selected v3; v1/v2 stayed accessible. Full semantic panels/source-grounding content not fully validated. | Validate one full P&G document including timeline, claims, mappings and review queue; verify version history. | Agent |
| Docs V2 semantic regeneration from saved evidence | 🟥 BLOCKED | Served regeneration created v3 `SYNTHESIS_BLOCKED_PRIVACY`; no remote corpus sent. Host/container lacks OPENCODE_API_KEY; `ALLOW_EXTERNAL_LLM=false`; privacy policy forbids bypass. | Restore authorized provider/auth configuration without exposing credentials; retry one document only. | Agent |
| ZMI runtime and worker processing | 🟥 BLOCKED | Health is 200 and container healthy; one restart since current container recreation, exit 0/OOM=false. Retained Docker events have no die/OOM event explaining earlier restarts. Owner job remains ACTIVE at ~5.1h heartbeat age (<6h stale threshold); one queued job remains. Five upload sessions are still UPLOADING. | Preserve owner jobs/uploads; wait for stale policy and uploads; validate a synthetic job only after safe availability. | Agent |
| Mobile reliability + large-file upload V2 | 🟨 TESTING | Deployed through ZMI image `8a67343a6daecb7e691fe3d0d6d73efbaf6f5bcc`; root cause was a stale served image missing `/api/uploads` and the package omitted its static helper. Caddy HTTP and LAN HTTPS return JSON 200 for GET `/api/uploads`; authenticated POST creates a synthetic session (200); chunk ACK, resume status and idempotent retry work; finalize returns JSON validation response for synthetic invalid media; synthetic session deleted. The served helper JS returns 200 and guards non-JSON responses. Storage preflight and oversize create return JSON 507 with free/required GiB. Served UI contains badge, bytes/total, percentage, speed, ETA and Pause/Resume/Cancel/Retry. No real owner files retried. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Resumable upload recovery after transient app outage | 🟨 TESTING | ZMI deployed at `a99effb`; transient 5xx/network retry on preflight/create/status/finalize, with chunk ACK retry preserved. Python 10 and Node 9 pass. Candidate and served LAN HTTPS synthetic create/chunk/resume/finalize-error/cleanup passed. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Resumable Upload API | 🟩 COMPLETE | Production through Caddy HTTP/HTTPS: GET/POST `/api/uploads`, chunk PUT, resume GET, finalize POST return JSON; small synthetic ACK/resume/retry and cleanup passed. 10 focused Python tests pass, covering synthetic 5 GiB, transient 502, resume, successful finalize, ACK preservation, ENOSPC mapping and packaged asset. 7 Node tests pass. | None; retain coverage. | Agent |
| Non-JSON error handling | 🟩 COMPLETE | Response parsing checks Content-Type; text/HTML failures show `Upload failed: HTTP <status> <reason>`. Node suite 7/7 includes HTML response handling; served helper JS returns HTTP 200 and UI badge says Upload error. | None; retain coverage. | Agent |
| Storage preflight | 🟨 TESTING | Upload target `Video_compress` is on C: via `/data`; host 106.55 GiB free, Whisper `/data` 106.53 GiB free, Docker backing volume C: 106.55 GiB free. 2 GiB safety reserve; batch sum and live preflight enforced before create/chunk/finalize. Production synthetic 200 GiB request rejected before session creation with `Insufficient storage: 106.7 GiB free, 202.0 GiB required.` | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| ENOSPC handling | 🟨 TESTING | Chunk/finalize `ENOSPC` maps to JSON 507 and actionable free-space guidance; low-space finalize/chunk tests preserve prior ACK map. Production low-space preflight returns JSON 507. Upload UT 10 passed. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Deploy | 🟩 COMPLETE | Current source implementation `74799c205c6f399aeecfa927a8baefba73aa69ba` is served over LAN HTTPS; health and `/api/uploads` returned JSON 200. ZMI is currently healthy, restart count 4; Caddy and persistent data volumes stayed up. | Investigate intermittent ZMI restarts before declaring operational stability. | Agent |
| Persistent /revisa result contract | 🟨 TESTING | CURRENT.json resolves canonical SDD; contract exists. This execution result must be committed and pushed to validate persistence. | Commit and push SDD and pointer update, then verify origin/main. | Agent |
| Real multi-GB UAT | OWNER_PENDING | Screenshot showed transient `Failed to fetch`; ZMI OOM event (exit 137) at 18:13:33 UTC; persistent session retains 8 ACKed chunks / 64 MiB. No owner media retried, canceled, or deleted. | Juan resumes one selected file after retry-hardening deploy. | Juan |

| Documentation V2: corpus inventory and resumable regeneration | 🟨 TESTING | Initial scan was 9 total: 1 ready, 1 transcript missing, 1 keyframes missing, 6 missing both. Local-only preprocessing reused valid artifacts and completed missing transcripts/keyframes for all 9; final inventory reports 9 READY. Prep progress is resumable and persisted per media. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Documentation V2: semantic regeneration of full current corpus | 🟥 BLOCKED | Historical 9/9 artifacts, 393 claims and 273 review items retained; current served regeneration returned SYNTHESIS_BLOCKED_PRIVACY because remote LLM is disabled and auth is unavailable. | Restore authorized provider configuration safely; validate one served real document and regeneration before corpus continuation. | Agent |
| Edit File: user-visible media name | 🟨 TESTING | Display name stored atomically by stable media ID; original path and extension remain unchanged. `watcher/venv/Scripts/python.exe -m pytest tests/test_dashboard_display_name.py -q` — 7 passed; `compileall` passed. Covers UI field, extension, trim, invalid/empty/collision, linked project/transcript/docs, playable media and idempotency. | None. | Agent |
| LAN availability incident | 🟨 TESTING | Follow-up check found ZMI health checks and `docker exec` failing because its overlay rootfs path was missing; HTTP also timed out. Compose labels confirmed project `whisper`, `compose.yml`, service `zmi`. Queue had 0 active/pending jobs and capture sessions were closed. Recreated only ZMI with `docker compose -p whisper -f compose.yml up -d --no-deps --force-recreate zmi`; Caddy was left running. `/data` bind and `whisper_zmi-model-cache` volume remain mounted. ZMI is healthy; Docker Engine 29.5.3; desktop HTTP, LAN HTTPS, LAN `/setup`, and dashboard return 200; worker RUNNING 0/0; Videos 9, projects 4, shared-media references 9/9 valid. Ethernet `192.168.50.20`. | None. | Agent |
| Live Capture: Camera mode, Audio-only mode, Camera microphone ON by default, visible microphone status | 🟨 TESTING | Served fake-device flow created a capture session and finalized video+audio fragments. Legacy script timed out waiting for `Preview` after Start; served state is `Recording`. Does not validate the full capture journey. | Update focused journey for current state semantics, then validate stop/finalize/player; phone-only camera/mic behavior remains Juan's UAT. | Agent |
| Live Capture: rear camera, camera switching, portrait/landscape | 🟨 TESTING | Prior synthetic camera/orientation browser coverage; physical device remains owner UAT. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Live Capture: resolution selection, actual resolution display, recording timer | 🟨 TESTING | Prior capture API/browser evidence; verified by current root unit suite (1230 passed, 8 skipped). Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Live Capture: project inheritance, stop/cancel/retry | 🟨 TESTING | Capture session, cancel/retry and playlist tests were included in prior targeted runs. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Compression integrity: validate staged and published media, video/audio streams, positive duration tolerance, nonzero size and meaningful reduction | 🟨 TESTING | `test_media_optimize.py` and full root unit suite pass; source is retained until candidate and published output validate. | None; maintain coverage for future edits. | Agent |
| Compression cleanup: atomic publish, exact provenance-linked source removal, retries/recovery preserve unrelated data | 🟨 TESTING | Full root unit suite passes (1230 passed, 8 skipped), including compression/storage failure paths. | None; cleanup remains provenance-scoped. | Agent |
| Compression provenance API/UI: original/optimized sizes, bytes saved, cleanup outcome and reason | 🟨 TESTING | Compression API/UI unit coverage in the passing root suite. | None; verify in optional served UI check. | Agent |
| Real Live Crop: crop applied before MediaRecorder; WebM contains cropped pixels; microphone audio preserved | 🟨 TESTING | Prior synthetic WebM crop measured 1280x720 -> 636x360 with audio. Current served capture attempt did not reach crop selection; no new crop evidence. | Re-run after correcting served journey; validate encoded pixels/dimensions and audio before marking complete. | Agent |
| Real Live Crop: output dimensions persisted; encoded dimensions reduced; preview maps to encoded crop | 🟨 TESTING | Root unit suite passes 1230 with 8 skipped, including crop and assembly behaviors; prior synthetic WebM evidence confirms reduced encoded dimensions and audio preservation. A production capture reported `CROP_OUTPUT_MISMATCH`; retained as owner UAT advisory. | Juan verifies orientation/crop on device during UAT. | Agent |
| Mobile crop input: Pointer Events, pointer capture/cancel, object-fit/video-relative coordinates, portrait and landscape | 🟨 TESTING | Crop geometry and pointer journey covered by prior synthetic UI evidence and current root unit suite. | None; phone UAT remains owner-only. | Agent |
| Fragment pipeline: short upload fragments, ACK/idempotency, incremental upload | 🟨 TESTING | Prior 60 fragment/assembly/processing/API tests and fresh 38-test fragment rerun passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Fragment pipeline: final assembly, complete duration, one recording -> one visible final media | 🟨 TESTING | Prior assembly tests and verified media-duration evidence; current relevant root suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Fragment pipeline: safe fragment cleanup and provenance retention | 🟨 TESTING | Prior failure/recovery and cleanup tests; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Continuous playlist: continuous recording, title detection, multi-frame confirmation, logical boundaries | 🟨 TESTING | Served fake-device attempt used playlist mode and finalized a synthetic capture, but timed out on a stale UI-state assertion before validating title boundaries/review. | Correct journey and verify title detection, boundaries and saved logical videos in served UI. | Agent |
| Continuous playlist: project inheritance, review/rename/split/merge | 🟨 TESTING | Prior playlist/session suites cover logical video operations. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: preview, TIME/FRAME modes, 8 crop handles, drag/resize | 🟨 TESTING | Prior API/unit and browser evidence for TIME/FRAME and eight handles; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: zoom/pan, HH:MM:SS, timeline | 🟨 TESTING | Prior editor API and browser evidence; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: black interval detection, black-border detection, Apply Changes | 🟨 TESTING | Served UI Edit/Apply passed for safe MP4 and WebM; validated playable 6-second derivatives retained audio and originals' hashes were unchanged. Earlier 1.46 GiB WebM failure source is unavailable, so that case remains unverified. | Keep original-source failure open until its exact input can be safely reproduced; continue remaining editor controls in served journey. | Agent |
| Video editor: edited copy, original preserved, idempotency | 🟨 TESTING | Prior 16+ focused edit tests cover derivative validation, provenance, and source preservation. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Black video: temporal black trimming, spatial black crop, NEEDS_REVIEW, safe original preservation | 🟨 TESTING | Prior black-video tests cover temporal intervals, borders, review and source preservation. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Black video: optional black auto-stop warning | 🟨 TESTING | Prior browser evidence covers Off default, countdown, content-return cancellation and stop. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Multi-upload: multiple files, streaming/bounded memory | 🟨 TESTING | Prior browser/memory evidence: 6x24 MiB upload, +79.7 MiB; no current-candidate rerun. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Multi-upload: concurrency default 4, configurable maximum 6, per-file retry/cancel | 🟨 TESTING | Prior 4/6 concurrency browser checks and upload retry/cancel evidence. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Worker: periodic scan, day limit 1, night limit 3 | 🟨 TESTING | Worker configuration and scheduling tests exist; live API currently reports worker RUNNING, zero active/pending. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Worker: stale recovery, idempotent claim, cancellation, no duplicate processing | 🟥 BLOCKED | Focused worker tests pass, but served worker is held by a pre-existing ACTIVE owner job and synthetic processing did not reach Videos; app had four restarts (exit 0, OOM=false; cause unknown). | Diagnose orphaned lease/worker liveness without canceling or changing the owner job; prove a synthetic job completes in Videos. | Agent |
| Documentation Synthesis V2: Evidence Timeline, semantic grouping, procedures | 🟨 TESTING | Current root unit suite passes 1230 with 8 skipped; synthetic Live Capture -> keyframe -> Docs V2 integration selection passes 15 tests with 5 HTTPS interception skips. | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Documentation Synthesis V2: decisions, claims/evidence, ambiguity/review queue, source mapping | 🟨 TESTING | Docs V2 evidence-grounding and source mapping implementation/tests exist. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Documentation regeneration boundary: regenerate from saved evidence without transcription/FFmpeg/OCR/vision; separate reprocess; version history | 🟨 TESTING | Regeneration isolation, versioning and separation unit suites pass in current root run (1230 passed, 8 skipped). | None; UI/browser check advisory. | Agent |
| Documentation Synthesis V2: regenerate documentation, reprocess video, documentation versioning | 🟨 TESTING | Prior regeneration/versioning tests passed; UI keeps regeneration separate from reprocessing. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video list: Project, Date, Duration, sorting, Show/player | 🟨 TESTING | Final served `/api/files` returns 60 rows; projects API returns 5 projects; smoke confirmed no chunk-named rows. Unit suite passes 1230 with 8 skipped. | None. | Agent |
| Video list: delete eligibility/reason; hide internal chunks | 🟨 TESTING | Prior API/UI state-matrix and fragment visibility evidence. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Dashboard logical inventory counters | 🟨 TESTING | `/api/files` returns counts from the same logical rows used by Videos; targeted fixture has 48 physical media files and 12 visible rows, with 98 focused tests passing. Image for `3ec6bb6` built; deployment waits to protect five UPLOADING sessions. Prior served baseline: 12 videos, 0 audio, 9 transcribed. | After uploads settle, deploy `3ec6bb6`, compare cards with unfiltered table and validate filters remain unchanged. | Agent |
| HTTPS/mobile: desktop/LAN shared data, HTTPS certificate, /setup, public CA, QR onboarding | 🟨 TESTING | Focused LAN/setup tests pass 31/31. Final desktop HTTP and LAN HTTPS return 200 with marker matching HEAD; `/setup` and QR return 200; `/api/network` reports configured HTTP/HTTPS ports 5000/5001, LAN IP `192.168.50.20`, and certificate fingerprint. | Juan installs public CA and validates phone onboarding during UAT. | Agent |
| Overview Stats Modal: toolbar icon opens modal; reuse existing metrics; four required metrics | 🟨 TESTING | `tests/e2e/overview_stats_modal.py`: 12 browser checks pass on final app source; four metric labels/values match existing metrics. | None. | Agent |
| Dashboard compact layout: Drop Area left; Pipeline and Folders stacked right; responsive, content-sized cards | 🟨 TESTING | Playwright layout test at 1440x1000 verifies two-column left/right stack; at 390x844 verifies one-column order and no horizontal overflow. CSS cards align to content; no fixed heights. | None; Juan may review live appearance during UAT. | Agent |
| Mobile capture 502 diagnosis | 🟨 TESTING | Caddy logs at 2026-10-20 20:19:27Z show proxy 502 during clean app restart: `/api/capture/sessions` connection refused; health/status/log requests timed out/reset. Container exit 0, OOMKilled=false. No fragment POST 502 in retained history. Confirmed client defect: JSON-only parse then immediate recorder stop on transient upload failure. | Preserve new proxy/app diagnostics for future recurrence. | Agent |
| Mobile capture retry/recovery | 🟨 TESTING | Fragment/status/final-drain retries handle network + HTTP 408/425/429/500/502/503/504; six retries, exponential delay capped at 30s. Stable fragment ID and IndexedDB copy remain until ACK; reconnect/manual retry supported; visible retry state and graceful bounded-queue pause. | Phone UAT. | Agent |
| Mobile capture unit tests | 🟨 TESTING | `pytest` focused capture/media suite: 113 passed (2026-10-20), including retry-state/template contract and rendered JavaScript `node --check`. Tests use `tmp_path`. | None. | Agent |
| Focused integration/API test for 502 recovery | 🟨 TESTING | Flask API integration injects upstream-style HTTP 502 then replays same ID/body; next request ACKs exactly one stored fragment. Separate temporary storage OSError returns 503 then same-ID retry succeeds. | None. | Agent |
| Publish readiness | 🟨 TESTING | Relevant suite 113 passed; `compileall` passed; Docker image build passed; isolated tmpfs container served dashboard and `/api/health` 200; Caddy config validates. Ready to publish. Production deployment not requested in this task. | Juan phone UAT after publication. | Agent |
| Preview layout: state spans both columns; video and transcript panels occupy intended grid cells | 🟨 TESTING | CSS change is in pushed/served SHA `f6bb5c9`; visual browser check not run. | Check preview layout at desktop and mobile widths. | Agent |
| Manual transcript entry for media without a transcription | 🟨 TESTING | `tests/test_project_override.py`: 21 passed, including create, validation and rollback cases (2026-10-20); served browser form visible. Tests use isolated temporary roots. | None. | Agent |
| Overview Stats Modal: responsive layout, close/X/Esc; modal remains available without inline Overview card | 🟨 TESTING | Prior 12 browser checks verify modal controls and metric rendering; owner amendment changes only the inline card placement. | None. | Agent |
| Relevant unit tests: all new/changed business logic | 🟩 COMPLETE | Current focused rerun: 92 Python tests passed; `tests/js/upload_reliability.test.cjs`: 9 passed. Tests remain engineering evidence, not user journey completion. | Run targeted tests for each subsequent fix. | Agent |
| Build/import/start and schema/config migration validity | 🟩 COMPLETE | Current served build marker is exact implementation HEAD `74799c205c6f399aeecfa927a8baefba73aa69ba`; HTTPS health 200, container running/healthy at check. Four restarts during run remain operational issue. | Diagnose repeated restarts; rerun health after stability work. | Agent |
| Data safety: semantic reference and media validation | 🟨 TESTING | Current `/api/files`: 23 records, 0 missing nonempty paths; worker RUNNING, 0 active/0 pending. Existing current finals passed ffprobe; earlier capture finals and nonempty general media validated. Test roots isolated. Explicit confirmed DELETE API responses account for missing cancelled captures/chunks and Tidal files; see reconciliation below. | Continue semantic checks; raw inventory equality is not a release condition. | Agent |
| Integration tests | TODO | Current-run `PASS`: synthetic integration selections passed 15 tests, 5 skipped (HTTPS interception); live-worker process-restart case excluded to keep shared data safe. | Attempt after unit tests when practical; record one advisory result. | Agent |
| Media regression | TODO | Current-run `PASS`: crop, assembly, black-video, and dashboard API media regression selection passed 36 tests. | Attempt after unit tests when practical; record one advisory result. | Agent |
| Playwright | TODO | `PASS`: Overview modal 12/12 checks; New Recording and Video Editor open on the deployed app source. Concurrent production Video Editor apply job `c8tdRWsMDGpD3_eYfDV_7TZf` failed output validation on an existing 1.46 GB WebM; original stayed intact. Record as advisory defect, not a publication blocker. | Juan reviews the edit failure during UAT; no automatic retry. | Agent |
| Host E2E | TODO | Prior Host E2E passes on earlier revisions; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Docker E2E | TODO | Prior Docker E2E pass exists for earlier revision; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Security scans | TODO | Prior security suite passed; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Jenkins / Sonar / soak | TODO | Explicitly removed from release gates by current policy. | None. | Agent |
| Deploy latest compact UI + capture 502 resilience | 🟨 TESTING | Rebuilt only active `whisper` project service `zmi` from current main; desktop HTTP and dynamic LAN HTTPS return 200 with build header/page meta matching final main. Health ONLINE; worker RUNNING 0 active/0 pending; `/setup`, QR and CA return 200. Current APIs show 17 media rows, 4 projects and 0 missing references. Served page contains compact two-column grid/side stack, New Recording modal and IndexedDB capture retry/reconnect code with stable fragment IDs; focused 502 recovery tests and layout checks are already recorded above. Persistent `/data` bind and `whisper_zmi-model-cache` volume retained. Inventory changed from 743 files / 8,586,030,623 bytes pre-build to 742 / 8,586,030,615 after first refresh; one-file/eight-byte delta and concurrent `projects.json` edit are unexplained, no delete/prune/volume operation was run. | Juan phone capture UAT. | Agent |
| Post-deploy smoke: served revision=FINAL_HEAD, layout/transcript entry, Videos/projects, Overview modal, /setup | 🟨 TESTING | Desktop HTTP 200 and LAN HTTPS 200 both report exact SHA `f0800e22ccf9e4412087f0e0034c282dc4d79296`; health ONLINE; worker RUNNING/0/0; current projects and 23 files load, 0 missing nonempty refs. Browser smoke: Overview modal/metrics, New Recording Camera and Audio modes, VP8 Show/player metadata, editor HH:MM:SS, documentation regenerate visible. `/setup`, QR SVG and CA download return 200 (CA 418 bytes). | Juan validates phone later. | Agent |
| Physical phone UAT | OWNER_PENDING | Juan's device validation is final acceptance; automated tests do not substitute. | Juan validates capture/audio/crop/playback after deployment. | Juan |
| Release candidate integrity | 🟨 TESTING | RC `32be478a8a7e9ef837b4d12e9435ed0480acbcf4` matched feature branch and `origin/feat/zmi-documentation-synthesis-v2`; clean three-way merge parent preserved. | None. | Agent |
| Merge to production branch (`main`) | 🟩 COMPLETE | Merge commit `a497f4f19ca401902afa653c37a1c214fc9143d4`; parents are pre-merge production `f14ed96b76d2ea48b137eb1910ccc68f7d347ff5` and validated RC. Post-merge unit suite passed 1232, 8 skipped; production branch and subsequent SDD updates are pushed. | None. | Agent |
| Release tag | 🟩 COMPLETE | Annotated original tag `whisper-2026-10-20` preserved at `77108a2`; patch tag `whisper-2026-10-20.2` pushed at final production SHA `f0800e22ccf9e4412087f0e0034c282dc4d79296`. | None. | Agent |
| Production deploy | 🟨 TESTING | Previous HEAD `74799c2` remains served. New image for pushed `3ec6bb6` built successfully; no container recreation while five owner upload sessions remain UPLOADING. | Recheck upload state, then deploy and verify exact build marker/health without changing data or model-cache mounts. | Agent |
| Production smoke | 🟨 TESTING | Served release and functional smoke passed; exact results recorded above. | None. | Agent |
| Galaxy UAT | OWNER_PENDING | Juan's physical phone validation remains final acceptance. | Juan validates capture/audio/crop/playback. | Juan |
## Evidence

Complete during implementation; link exact command, result, artifact and SHA for each AC. The canonical release policy and resume order are in the execution-plan `FINAL SDD RELEASE RUN` section. This SDD section is the only active Kanban; other dated tables are historical evidence.

## Production data-safety reconciliation - 2026-10-20

The two raw snapshots differ (1502 vs 1493 items; 47,957,774 bytes). The nine absent items are all from one capture session. Historical API response `.agents/session/final-files.json` recorded it as `CANCELLED`, `user_state=CANCELLED`, `delete_allowed=true`; current `/api/files`, `processed_files.json`, and compression provenance contain no reference. The capture has no optimized replacement and no recoverable bytes were found. This is classified as legitimate cancelled-session cleanup, not replacement or proven optimization. The application explicit delete endpoint requires confirmation and permits deleting inactive sessions, but no per-deletion audit record exists; classification is based on the persisted cancelled/deletable state plus absence from current references. The session was not active or pending when audited.

| Path | Size | Session / Video | DB referenced? | Manifest referenced? | Expected cleanup? | Replacement exists? | Recoverable? | Classification |
|---|---:|---|---|---|---|---|---|---|
| `Videos/live_capture/sess-ea3bff8954f6/chunks/chunk-000000.webm` | 11,261,670 | sess-ea3b... / cancelled capture | No current DB/API reference | No live manifest; historical snapshot only | Yes, cancelled session removed | No | No surviving bytes; no longer referenced | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/chunks/chunk-000001.webm` | 4,720,642 | sess-ea3b... / cancelled capture | No current DB/API reference | No live manifest; historical snapshot only | Yes, cancelled session removed | No | No surviving bytes; no longer referenced | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/final/recording.webm` | 15,989,285 | sess-ea3b... / "Live capture.webm" | Historical API only; current none | No live manifest; historical snapshot only | Yes, cancelled/deletable capture | No | No surviving fragments/copies; no current reference | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/fragments.json` | 1,395 | sess-ea3b... / fragment index | No current DB/API reference | Historical snapshot only | Yes, session metadata removed | No | No | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/fragments/fragment-000001.webm` | 3,704,986 | sess-ea3b... / cancelled capture | No current DB/API reference | Historical fragment index only | Yes, cancelled session removed | No | No surviving bytes | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/fragments/fragment-000002.webm` | 7,554,862 | sess-ea3b... / cancelled capture | No current DB/API reference | Historical fragment index only | Yes, cancelled session removed | No | No surviving bytes | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/fragments/fragment-000003.webm` | 4,720,401 | sess-ea3b... / cancelled capture | No current DB/API reference | Historical fragment index only | Yes, cancelled session removed | No | No surviving bytes | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/processing_chunks.json` | 955 | sess-ea3b... / processing map | No current DB/API reference | Historical snapshot only | Yes, session metadata removed | No | No | LEGITIMATE_CLEANUP |
| `Videos/live_capture/sess-ea3bff8954f6/session.json` | 3,578 | sess-ea3b... / session manifest | No current DB/API reference | Historical snapshot only | Yes, cancelled session removed | No | No | LEGITIMATE_CLEANUP |

No SQL database is configured for media. Live API snapshot `.agents/session/prod-files-predeploy.json` contains 59 rows; all nonempty referenced paths exist. Four referenced final WebMs and 10 nonempty `Videos/general` media objects pass ffprobe with streams and positive duration. Ten zero-byte rows are named synthetic sample fixtures, not user recordings. Three other session manifests changed during the test window: `sess-8424dbb61b96`, `sess-afd8a6570237`, and `sess-c5d5a3cb3f3d`. Their media sizes and SHA256 values match session metadata; fragment records are ACKED, processing maps finalized, and chunk media remains present. The root unit suite capture/dashboard fixtures redirect media to per-test `tmp_path`; `test_dashboard_mobile_setup.py` exercises read-only routes. The changed files are application session-state transitions while the live service was running, not test output. No manifest restoration was performed.

Release lineage: the original annotated tag `whisper-2026-10-20` remains immutable at `77108a206e9fa39d13e40238c8d2323c92958c53`. Main advanced through `f6bb5c99334ee4be05eacef5e24778764d977587` (production dashboard layout/manual transcript feature), `05bbe9cb29e4cfdb980b049309992bdd2ded87dc` (release evidence), and `f0800e22ccf9e4412087f0e0034c282dc4d79296` (manual transcript regression coverage). Targeted post-change tests: 21 passed. Annotated tag `whisper-2026-10-20.2` points to `f0800e22ccf9e4412087f0e0034c282dc4d79296`, pushed to origin; this exact revision is deployed and served. At final verification, `HEAD == origin/main == 2592b2773c104e3b219a541332eb759a90de7472`; commits `39e9bba` and `2592b27` after the deployed/tagged SHA contain SDD/Kanban evidence only. Production code remains tagged and served at `f0800e22ccf9e4412087f0e0034c282dc4d79296`.

Production reference audit: latest `/api/files` returned 23 rows and every nonempty referenced media path exists. The additional absent paths seen during deployment were accompanied by successful explicit `DELETE /api/file?...&confirm=true` responses in `logs/dashboard.log`. Relevant rows were canceled capture/chunk items (`sess-5c47d4d0cd07`, `sess-6e5418b477b6`, `sess-f3b1241ed55a`) plus the two `Tidal` files; `sess-6e...` was first canceled via API. Current API references resolve; no test wrote into the production/shared-media root. Semantic acceptance passes despite changed raw counts. The `sess-ea3bff8954f6` final was `CANCELLED`, `delete_allowed=true`, not optimized/replaced, and no longer referenced; no replacement or recoverable bytes were found.

Final served checks (2026-10-20): desktop HTTP and LAN HTTPS both return 200 with `X-Whisper-Build: f0800e22ccf9e4412087f0e0034c282dc4d79296`; `/api/health` ONLINE; worker RUNNING, 0 active and 0 pending; projects load; 23 media rows, 0 missing nonempty references. Browser smoke opened Overview metrics, New Recording (Camera default and Audio mode), Show/player on playable VP8, Video Editor HH:MM:SS controls, and Documentation Regenerate. LAN `/setup`, QR SVG and CA download return 200 at dynamically detected `192.168.50.20`. Original crop-output mismatch and 1.46 GB WebM edit validation failure remain advisories; original large source was preserved. Galaxy UAT is OWNER_PENDING.


## Mobile capture 502 diagnosis and repair - 2026-10-20

Caddy logs correlate upstream 502s with a graceful ZMI container restart at `2026-10-20T20:19:27Z`: container `whisper-zmi-1` exited with code 0, `OOMKilled=false`, then started again. During the gap Caddy returned 502 for `/api/capture/sessions` (connection refused) and adjacent `/api/health`, `/api/status`, and `/api/logs` requests (upstream timeout/reset/EOF). This establishes the observed 502 class as a proxy-to-app availability gap during restart, not an invalid capture endpoint or media payload. Retained Caddy logs show no fragment POST with 502 at that timestamp, so the exact request the phone displayed cannot be recovered from historical logs.

The client-side failure that turned a transient outage into a stopped capture was confirmed in `dashboard.html`: fragment uploads parsed every response as JSON without checking HTTP status; a 502 HTML response raised a parse error, immediately called `setStalled`, and stopped MediaRecorder. Session polling also swallowed transport failures without showing recovery state. That response handling made a temporary backend restart look like a terminal recording failure.

Repair: fragment requests now check HTTP status and retry network/408/425/429/500/502/503/504 failures up to six times with exponential backoff capped at 30 seconds. They keep the stable fragment ID and IndexedDB copy until ACK; recording continues while the bounded queue has room, then pauses visibly. Manual Retry and reconnect reuse the same ID. Status polling retries and displays a reconnect message. Final drain retries safely and retains an explicit manual retry state if ACK cannot be confirmed. Server storage errors return actionable 503 JSON and structured session/fragment logs; capture 5xx responses include status, path, elapsed time, client and request ID. Existing Caddy reverse-proxy error logs distinguish upstream timeout, connection refusal, and reset; app logs record capture 5xx with status, path, elapsed time, client and request ID. No access-log directive was added, avoiding capture of dashboard auth headers.

Focused recovery tests inject both an upstream-style 502 and an app storage `OSError`, retry the same fragment, and verify one durable ACK. These tests use the existing `tmp_path` isolated media roots; no unit/API test writes to shared production media. Playwright layout checks cover desktop and mobile viewport arrangements; physical mobile capture UAT is still owner-side.

## Owner interventions

Expected: 1. INITIAL_SPEC (this frozen US and production publication authorization). Physical Galaxy UAT is owner-only follow-up, not a release handoff. Unexpected: 0 unless a typed external blocker applies.

## Terminal state

`READY_FOR_DEPLOY` after implementation gates, commit and push; `RELEASED` after production deployment/verification. Galaxy phone UAT may remain `OWNER_PENDING` after release and does not hold automated delivery. `DONE` after required owner phone acceptance when available.

## Docs V2 OpenCode Go Resume Check (2026-10-21)

- Official OpenCode Go endpoint requires a dedicated Go API key. CLI stores that API key under `opencode-go` in `~/.local/share/opencode/auth.json`; `auth login opencode` does not create a reusable session token for the direct `/chat/completions` API.
- Root cause: `.agents/session/run_docs_v2_opencode_go.py` unconditionally loaded the saved `opencode-go` key and copied it to `LLM_API_KEY`; the compatible client then sent that expired value as Bearer auth. A legacy `LLM_API_KEY` remains in `scan_config.env`, but the OpenCode host now ignores it.
- Fix: `Settings` supports `OPENCODE_API_KEY`, the OpenCode client uses only that dedicated setting for `opencode.ai`, and the batch runner no longer reads `auth.json` or legacy `LLM_API_KEY`. Secrets are not persisted by the runner.
- Current validation (2026-10-21): the User-scoped `OPENCODE_API_KEY` was copied only into child processes; no secret was printed or persisted. OpenCode Go tiny preflight passed. Initial 9-media inventory: 1 READY, 1 NEEDS_TRANSCRIPT, 1 NEEDS_KEYFRAMES_ONLY, 6 NEEDS_TRANSCRIPT_AND_KEYFRAMES. Session 41 generated and validated Docs V2 version 2; see Finalization Kanban.
- Local preprocessing is running resumably from saved evidence. Continue it to completion, refresh the inventory, then generate and validate Docs V2 for all eligible corpus items. Keep failed docs retryable and persist each result in the batch manifest.
