# US-ZMI-LIFECYCLE-001 â€” Recording, optimized storage and documentation workflow

## Status
`RELEASED_OWNER_UAT_PENDING`

## CURRENT_RESULT

DOCUMENTS_V2=INCOMPLETE
RESOURCE_MODE=ALWAYS_PROGRESS_LOW_MEMORY
HEAVY_CONCURRENCY=1
RESOURCE_STATE=HEAVY_SLOT_OCCUPIED
ACTIVE_HEAVY_JOB=whisper-zmi-1 / transcript_pipeline.pipeline.master (batch)
ACTIVE_MEDIA_ID=pg-10
ACTIVE_SOURCE=Videos/py_pg/pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording.mp4
ACTIVE_PROJECT=P&G
ACTIVE_STAGE=TRANSCRIBE (per-file master log); API batch stage=store
ACTIVE_PROGRESS=RUNNING_SLOW; 3011.456s source; TRANSCRIBE started 2026-10-28T00:49:43Z; VAD enabled 00:51:07Z; no chunk checkpoint or output yet
ACTIVE_OUTPUT=CarpetaTranscripciones/py_pg/pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording_segments.json (not created)
ACTIVE_CHECKPOINT=NONE
LAST_PROGRESS_AT=2026-10-28T00:51:07Z
CURRENT_PROGRESS_UNIT=pg-10 VAD initialized; root pipeline has no chunk index
PREVIOUS_PROGRESS_UNIT=pg-9 output persisted and FileTracker completed at 2026-10-28T00:49:36Z
PROGRESS_DELTA=pg-10 output 0 bytes; no checkpoint; no master-log change; thread CPU +36.3s over 15.8s while ASR runs
CPU_TIME_DELTA=36.3 CPU seconds / 15.8 wall seconds (container PID 47 threads)
WORKER_PID=1 (container controller)
ACTIVE_PID=47 (whisper-zmi-1 child master)
WORKER_ALIVE=YES
PID_43812=ALIVE but unrelated host Python; parent watcher venv; command does not match master
STATUS_API_CONSISTENT=NO for media identity; API reports batch running/store while PG-9 is completed and PG-10 is in per-file TRANSCRIBE
EVIDENCE_CONFLICT=YES; PG-9 queue status was stale versus output, FileTracker, and master log
PG9_STATE=NEEDS_REVIEW; output identity HIGH; 904 segments, 8,573 words, 0 invalid timestamps; last segment 3571.18s/3572.032s
PG9_CHECKPOINT=NONE
PG9_RECOVERY_ACTION=NONE; output is persisted and identity reconciled; VAD/speech coverage review remains
PG10_STATE=RUNNING_SLOW; no output/checkpoint yet; prior similar pg-9 source required 6.1h; current pass elapsed about 52m
RESOURCE_EVIDENCE=container RSS about 4.96 GiB; no swap I/O observed; no critical host pressure evidence
PAUSED_FOR_CRITICAL_PRESSURE=NO
P0=25
P1=187
P2=107 CLOSED
P3=66
PG_VALID=0
PG_PARTIAL=8
PG_NEEDS_REVIEW=6
PG_MISSING=6
PG_FAILED=0
S46_OWNER_AUDIO_REVIEW=5.730s; scoped only
NEXT_HEAVY_JOB=pg-1 VAD after current serial heavy slot releases
HEAVY_SLOT_OCCUPIED_BY=pg-10
PROJECT_GLOBAL_BLOCKER=NO
LOCAL_ASR_AUTHORIZATION=STANDING_APPROVED
EXTERNAL_PG_CORPUS_PROCESSING=NOT_AUTHORIZED
HEAVY_QUEUE_COUNT=19; one heavy job at a time
WAITING_RESOURCES=pg-1 VAD; temporary until active slot clears
BLOCKED_COMPONENTS=S46_OWNER_AUDIO_REVIEW
INDEPENDENT_WORK_AVAILABLE=none identified; P0/source preflight and scheduling manifest complete
DOCS_V2_ARCHITECTURE_VERSION=3 generic source-evidence and cross-session pipeline; corpus synthesis remains frozen
ACTIVE_BRANCH=delta/zmi-docs-transcript-gate
IMPLEMENTATION_HEAD=active branch; evidence checkpoint committed with this delivery
MERGED_TO_MAIN=NO
DEPLOYED=NO
CORPUS_GENERATION=FROZEN

SESSION_41_OWNER_UAT=PASS
SESSION_41_GOLDEN=APPROVED
GOLDEN_OVERFIT_CHECK=PASS; generic production scanner regression passed in focused docs suite

S43_SOURCE_RECOVERY=OWNER_REQUIRED
S43_GATE=BLOCKED_SOURCE

GOLDEN_2_SOURCE=Videos/py_pg/pg_Ams_kap_app_support_s46.mp4
S46_SOURCE_GATE=PASS
S46_SPEECH_GATE=NEEDS_REVIEW; 83/83 contextual windows complete; 19 residual intervals/22.780s classified; 5.730s remains low-confidence pending source-audio review
S46_OWNER_AUDIO_SECONDS=5.730
S46_VISUAL_GATE=PASS; 7/7 topics, 51 frames, 48 selected technical/meaningful; eOperations remains a generic transcript extraction result
S46_CLAIM_GATE=PASS; generic diagnostic ledger contains 223 provenance-bearing claims
S46_QUALITY_GATE=NEEDS_REVIEW; speech gate is the sole failing/blocked diagnostic gate
S46_GOLDEN=NOT_GENERATED_SPEECH_GATE; no Golden 2 trio because not all gates pass
S46_APPLICATIONS_DISCOVERED=1 generic candidate: eOperations
S46_TOPICS=7/7 ACCESS, APPLICATION_UI, CONFIGURATION, DATABASE, FLOW_DIAGRAM, SUPPORT_SCOPE, WORKFLOW
S46_CLAIMS=223
S46_VISUAL_EVIDENCE=51 frames; 48 selected meaningful/technical; topic coverage 7/7
S46_DIAGRAMS=0 derived diagrams
S46_PROCEDURES=0
S46_AMBIGUITIES=11 diagnostic ambiguities
S46_OPEN_QUESTIONS=0
S46_SPEECH_COVERAGE=98.85% effective; original pre-review residual 22.780s
S46_RESIDUAL_REVIEW_SECONDS=5.730 low-confidence (gap-062 0.810s; prior-recovery-3443 4.920s)
S46_RESIDUAL_MEANINGFUL_SECONDS=0.768s courtesy-only/non-material; unresolved audio could still contain material content
S46_RECOVERED_FRAGMENT_1=gap-073 administrators.; DUPLICATE_EXISTING_CONTENT; excluded
S46_RECOVERED_FRAGMENT_2=gap-148 ?terrible, right? This isn't bad.?; NEW_VALID_CONTENT; added only to a separate reconciled transcript version
S46_RECONCILED_TRANSCRIPT=CarpetaTranscripciones/py_pg/pg_Ams_kap_app_support_s46_reconciled_v1_segments.json; original sidecar preserved (SHA-256 79424304fe6aeecbc063c77864a19ff65f836a33d312b164e92f930f91db34b0)
S46_INTERVAL_LEDGER=.agents/deliverables/evidence/S46-speech-reconciliation.json and .md; all 19 residual intervals classified; 5.730s low-confidence requires audio review

PG_LOGICAL_VIDEO_COUNT=20
PG_READABLE_VIDEO_COUNT=20
PG_PHYSICAL_SIDECARS=16 matched to these sources
PG_DISTINCT_TRANSCRIPT_SOURCES=13
PG_DUPLICATE_SIDECARS=3; all divergent content copies preserved
PG_TRANSCRIPTS_VALID=0
PG_TRANSCRIPTS_PARTIAL=8
PG_TRANSCRIPTS_NEEDS_REVIEW=5 (S46 owner audio review, pg-1 VAD pending, and divergent Sessions 15, 16, 17)
PG_TRANSCRIPTS_MISSING=7
PG_TRANSCRIPTS_FAILED=0
PG_VALID=0; PG_PARTIAL=8; PG_NEEDS_REVIEW=5; PG_MISSING=7; PG_FAILED=0
PG_NEEDS_REVIEW_REASONS=pg-1 VAD pending; Sessions15-17 divergent copies lack complete candidate-specific coverage; S46 requires Juan review of 5.730s
PG_TRANSCRIPTION_COMPLETE=NO; serial heavy queue count=19 (pg-1 + 11 targeted/reconciliation + 7 full transcription); no active heavy worker.
PG_CURRENT_SOURCE=pg-1
PG_CURRENT_STAGE=PAUSED_CRITICAL_PRESSURE
PG_CURRENT_ACTION=Resume pg-1 VAD in constrained 300s units, one worker/thread, checkpoint each unit, when the active heavy slot clears
PG_CURRENT_PROGRESS=pg-1 identity HIGH; 1,140 segments; reach 99.82%; VAD not started. Docker whisper-zmi-1 transcript_pipeline.pipeline.master active at 227.82% CPU/4.942 GiB RSS; system available RAM 4.03 GiB, 86.4% used; swap I/O counters 0 during sample. Constrained VAD paused because HEAVY_CONCURRENCY=1 slot is occupied, not because RAM is merely below an arbitrary threshold.
Session 1 media reach is 99.82%, but speech coverage remains unassessed; no retranscription or canonical promotion. Session 10 had 3 major VAD windows and the 588.361s tail reviewed; no transcript candidates accepted. Tail VAD has 0.992s unresolved without supported ASR; aggregate uncovered remains 547.508s, so Session 10 stays PARTIAL and needs further internal-gap review.
PG_TRANSCRIPT_MAP=.agents/deliverables/evidence/PG-logical-media-transcript-map.json/.md
PG_SOURCE_IDENTITY_AUDIT=.agents/deliverables/evidence/pg-transcript-recovery-20261027/pg_logical_20_source_identity_provenance_audit.json/.md; all 20 path/size verified; all 16 sidecar hashes/names/timestamps valid; seven MISSING sources checked against all 77 unmatched sidecars (zero session-number matches); source media SHA omitted to avoid large I/O
PG_PARTIAL_WINDOWS=.agents/deliverables/evidence/pg-transcript-recovery-20261027/pg_partial_candidate_recovery_windows.json/.md; PG_VAD_CONTEXT=.agents/deliverables/evidence/pg-transcript-recovery-20261027/pg_partial_vad_window_context.json/.md; PG_RECOVERY_WINDOWS_TOTAL=448; PG_RECOVERY_WINDOWS_PROCESSED=0; PG_RECOVERY_WINDOWS_P1_VAD=25; PG_RECOVERY_WINDOWS_P2_TIMESTAMP_ONLY=423; PG_VAD_GAP_CONTEXT_EXCERPTS=29; LOCAL_ASR_AUTHORIZATION=STANDING_APPROVED; EXTERNAL_PG_CORPUS_PROCESSING=NOT_AUTHORIZED
PG_TRANSCRIPT_QUEUE=.agents/deliverables/evidence/PG-transcription-queue.json/.md
PG_CURRENT_CHECKPOINT=.agents/deliverables/evidence/pg-transcript-recovery-20261027/pg1_identity_timestamp_validation.json/.md; sidecar checkpoints=pg_compliance_s15_divergent_sidecars_validation.json/.md, pg_compliance_s16_identity_timestamp_validation.json/.md, pg_compliance_s17_identity_timestamp_validation.json/.md, pg_compliance_s7_identity_timestamp_validation.json/.md, pg_compliance_legacy_s2_identity_timestamp_validation.json/.md, pg_app_support_s4_identity_timestamp_validation.json/.md, pg_shadow_identity_timestamp_validation.json/.md, pg_app_support_s10_identity_timestamp_validation.json/.md, pg_compliance_s16_divergent_content_comparison.json/.md, pg_compliance_s17_divergent_content_comparison.json/.md; S16/S17 content hashes and semantic/timestamp comparison recorded; canonical candidate remains unselected pending source coverage evidence

CROSS_SESSION_PRIMITIVES=PASS
CROSS_SESSION_APPLICATION=NONE eligible pair found
CROSS_SESSION_CONTRIBUTING_SESSIONS=NONE
CROSS_SESSION_REAL_PACK=BLOCKED_NO_ELIGIBLE_PAIR
APPLICATION_MISSION_PACK=controlled tests pass; real pack not generated

UNIT=225 passed in the focused documentation suite; see S46-final-validation-20261027.md
RUFF=PASS production documentation modules and changed test files
SYNTAX=PASS compileall src/transcript_pipeline/documentation tests
REPO_STATE=TESTING; S46 source-audio review remains open; documentation test gate passes
AGENT_SERVED_CHECK=NOT_RUN
OWNER_UAT=PENDING; S46 Golden 2 is not generated
DOCUMENTS_V2_OWNER_UAT=PARTIAL

KANBAN_COMPLETE=Session 41 Golden approved; S46 source/visual/claim/overfit checks pass; focused documentation tests pass
KANBAN_TESTING=S46 semantic transcript reconciliation; P&G 20-source identity map and transcript queue
KANBAN_BLOCKED=S46 speech gate requires source-audio review for 5.730s low-confidence audio; 8 transcripts missing; 3 divergent duplicate groups unresolved
KANBAN_OWNER_PENDING=S46 Golden 2 review after all gates pass; corpus generation frozen
BLOCKER=BLOCKED_COMPONENT=S46_OWNER_AUDIO_REVIEW; separate pg-1 constrained VAD pause because active Docker heavy workload occupies the single heavy slot; PROJECT_GLOBAL_BLOCKER=NO.
NEXT_ACTION=When the active heavy slot clears, resume pg-1 VAD from its checkpoint one 300s unit at a time; Juan reviews S46 audio; no Golden 2 until S46 speech gate passes; keep P&G queue serial.

PG_RECOVERY_TRIAGE=.agents/deliverables/evidence/pg-transcript-recovery-20261027/pg_recovery_window_triage.json/.md; metadata-only, no ASR/VAD/energy inference
PG_RECOVERY_WINDOWS_RAW=448
PG_RECOVERY_WINDOWS_AFTER_DEDUP=385
PG_WINDOWS_VAD_CONFIRMED=25
PG_WINDOWS_NEEDING_VAD=187
PG_WINDOWS_NEEDING_ASR=25 (P0 VAD candidates only; meaningful content still unverified)
PG_WINDOWS_DISCARDED_NO_SPEECH=0 (metadata cannot prove silence/non-speech)
PG_RECOVERY_WINDOWS_PROCESSED=0
PG_WINDOWS_BOUNDARY=107 (cheap reconciliation complete; retained P2, no ASR escalation)
PG_WINDOWS_ALREADY_COVERED=66
PG_WINDOWS_PROCESSED=0
PG_RECOVERY_TRIAGE_COUNTS=P0:25; P1:187; P2:107; P3:66; raw duplicate/context overlaps:0; context merges:63

PG_P0_PREFLIGHT=8/8 source media/sidecars readable; 25/25 windows within media bounds; serial order: pg-ccb11a4619acaa92 > pg-e3d73ded7776de64 > pg-e37b41cb13677886 > pg-58194dc5b0eb5cc6 > pg-98250af646a5c138 > pg-896f3fb2e5862a02 > pg-611c4b9e32914de6 > pg-4957e30bcb15f2bf
PG_P0_WINDOWS_BY_SOURCE=pg-ccb11a4619acaa92:4; pg-e3d73ded7776de64:1; pg-e37b41cb13677886:2; pg-58194dc5b0eb5cc6:4; pg-98250af646a5c138:3; pg-896f3fb2e5862a02:3; pg-611c4b9e32914de6:6; pg-4957e30bcb15f2bf:2
PG_MISSING_PREFLIGHT=7/7 readable; audio streams present; inventory sizes and durations match; 0 checkpoints present; resumable manifest prepared
PG_MISSING_SOURCE_OUTPUTS=pg-3:.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 12-20260907_123040UTC-Meeting Recording_segments.json; pg-9:.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 2-20260807_122922UTC-Meeting Recording_segments.json; pg-10:.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 3-20260810_123011UTC-Meeting Recording_segments.json; pg-11:.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 4-20260812_122933UTC-Meeting Recording_segments.json; pg-12:.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 5-20260814_122859UTC-Meeting Recording_segments.json; pg-13:.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 6-20260817_180222-Meeting Recording_segments.json; pg-15:.agents/deliverables/evidence/pg-transcript-recovery/pg_AMS KAP – Compliance – Session 9-20260828_140034UTC-Meeting Recording_segments.json
PG_PREFLIGHT_EVIDENCE=.agents/deliverables/evidence/pg-transcript-recovery-20261027/pg_source_preflight_and_serial_manifest.json/.agents/deliverables/evidence/pg-transcript-recovery-20261027/pg_source_preflight_and_serial_manifest.md
PG_BOUNDARY_RECONCILIATION=107 windows; 139 gaps 1.51-3.99s; neighbor context on both sides; canonical time overlap:0; audio evidence:NOT_RUN; ASR escalation:0


## HISTORICAL_RESULTS

### Prior status snapshots retained for audit (not authoritative)

FOLDER_LOCATION_LINK=PASS - served Folder cell links to /stream?id=<encoded media_id>; HEAD returns 200 video/mp4
OLD_MANUALS_FOUND=249
OLD_MANUALS_DELETED=249 - exact generated documentation targets, hash-logged before deletion
TRANSCRIPTS_DELETED=0
RAW_EVIDENCE_PRESERVED=PASS - 11 evidence.jsonl files; Session 41 timeline, OCR, frames, transcript, provenance retained
MANUAL_NAMING_RULE=source video basename with .md/.pdf/.json; API prefers named output
GENERATION_FREEZE=DOCUMENT_SYNTHESIS_PENDING_V2 - P&G synthesis blocked by default pending Session 41 owner approval
PG_LOGICAL_VIDEO_COUNT=16 - reconciled project media, SFTPGo, Video_compress aliases; Session 18 assignment and S43 identity conflicts retained
PG_VALID_TRANSCRIPTIONS=4 baseline; recovered outputs await validation
PG_MISSING_TRANSCRIPTIONS=6 baseline; recovered outputs await validation
PG_PARTIAL_TRANSCRIPTIONS=4 baseline; recovered outputs await validation
PG_FAILED_TRANSCRIPTIONS=2 - corrupt SFTPGo MP4 sources, moov atom missing; finalized capture source also absent on host
PG_TRANSCRIPTION_COMPLETE=FAIL - recovery batch emitted outputs; source identity and coverage validation remains
SESSION_41_VIDEO_DURATION=00:35:05.367
SESSION_41_TRANSCRIPT_LAST_TIMESTAMP=await recovered-segment validation
SESSION_41_TRANSCRIPT_COVERAGE=await recovered-segment validation
SESSION_41_SOURCE_GAP=prior transcript gap 00:11:09.477; recovered output needs validation
DOCUMENTS_V2=TESTING - synthesis frozen; invalid outputs removed
SESSION_41_GOLDEN_SAMPLE=TESTING - recovery transcript emitted; v4 not generated pending coverage validation
APP_MISSION_PACK=OWNER_PENDING - blocked until Session 41 passes gate and Juan approves
REPO_STATE=TESTING - targeted source changes; 60 focused tests pass
AGENT_SERVED_CHECK=PARTIAL - folder link served on 987219438c9cc8bd920dfe1e928f292e70a7fd03; P&G documentation state still needs served verification
OWNER_UAT=FAIL - prior Session 41 output rejected; new sample awaits owner review
EVIDENCE_CONFLICT=NO - owner rejection accepted; source assignment/identity conflicts are explicitly recorded
KANBAN_COMPLETE=8
KANBAN_TESTING=65
KANBAN_BLOCKED=3
KANBAN_OWNER_PENDING=5
BLOCKER=Validate emitted transcripts and restore two corrupt SFTPGo sources; finalized capture source path unresolved
NEXT_ACTION=Reconcile recovered segment coverage and source identity, then finish missing/partial recovery; keep Documents V2 frozen

STATUS=DISCREPANCY
HEAD=217a95dc6aa69c6259a066740a0da0790a2e3e3c
FEATURE_STATUS=TESTING - implementation and agent-served checks pass; owner validation remains required
REPO_STATE=PASS - compact upload listing, reselect/retry and active-transfer semantics committed; focused tests pass
AGENT_SERVED_CHECK=PASS - served build 217a95d on HTTP and LAN HTTPS; real safe MP4 browser flow acknowledged, resumed after failure/pause, and completed two files; logical counters reconciled
OWNER_UAT=FAIL - Juan reports physical dashboard counters and real video select/drop upload failure; corrected owner-observed retest pending
EVIDENCE_CONFLICT=YES - owner failures disagree with agent-served checks; OWNER_UAT controls completion

DROPAREA_REPO=PASS
DROPAREA_AGENT=PASS - served real-file UI flow, reselect after interruption/pause, two-file auto-start and completion
DROPAREA_OWNER=FAIL - owner revalidation pending
DASHBOARD_COUNTERS_REPO=PASS - logical /api/files metrics drive counters; build marker and versioned no-store assets
DASHBOARD_COUNTERS_AGENT=PASS - UI/API both report 10/0/9 on HTTP and LAN HTTPS
DASHBOARD_COUNTERS_OWNER=FAIL - Juan reports physical values

DROPAREA:
  REPO=PASS
  AGENT=PASS - served real-file UI flow
  OWNER=FAIL
DASHBOARD_COUNTERS:
  REPO=PASS
  AGENT=PASS - UI/API 10/0/9
  OWNER=FAIL
DOCS_V2:
  REPO=TESTING - Session 41 v3 generated; source coverage gate FAIL; artifacts are not fully grounded
  AGENT=NOT_RUN - no served UI verification for this rebuild
  OWNER=FAIL - Juan says current MANUAL.pdf is meeting-summary-like and not operational AMS support knowledge
DOCS_V2_OWNER_UAT=FAIL
DOCS_V2_OWNER_UAT_AT=2026-10-24T15:23:26Z
DOCS_V2_OWNER_UAT_BUILD=UNKNOWN
LIVE_CAPTURE:
  REPO=TESTING
  AGENT=TESTING
  OWNER=UNKNOWN
VIDEO_EDITOR:
  REPO=TESTING
  AGENT=TESTING
  OWNER=UNKNOWN

UPLOAD_RESELECT_FAILED=PASS - injected interruption after ACK 0; reload/reselect reused same session and resumed at 8.0 MB
UPLOAD_RESELECT_PAUSED=PASS - reload/reselect reused session and finalized
UPLOAD_STALE_RESUME=PASS - stale session resumed from preserved ACK map
UPLOAD_BATCH_STATE_RECOVERY=PASS_UNIT - stale batch flag recovery invariant tested
UPLOAD_NO_PROGRESS_RECOVERY=PASS_UNIT - bounded timeout, ACK preservation, retry behavior tested
UPLOAD_502_RETRY=PASS_UNIT
UPLOAD_TWO_FILES=PASS - both selected files auto-started and finalized independently
UPLOAD_FIRST_ACK=PASS - served browser observed ACK 0
UPLOAD_PROGRESS=PASS - ACK bytes restored after reload; both files completed

BUILD_ID_VISIBLE=PASS - visible Build 217a95d matches served SHA
STATIC_CACHE_IDENTITY=PASS - HTML/static no-store; JS URL versioned by SHA; no service worker; HTTP/HTTPS agree

VIDEOS_LOGICAL=10
AUDIO_LOGICAL=0
TRANSCRIBED_LOGICAL=9

UNIT=PASS - 22 Python tests, 12 JS tests, py_compile; served Playwright flow passed
BUILD_START=2026-10-24T03:15Z
DEPLOYED=YES - 2026-10-24T03:18:14Z; ZMI recreated only; /data and model-cache volume preserved; Caddy untouched
SERVED_HEAD=217a95dc6aa69c6259a066740a0da0790a2e3e3c
KANBAN_COMPLETE=8
KANBAN_TESTING=65
KANBAN_BLOCKED=3
KANBAN_OWNER_PENDING=5
BLOCKER=OWNER_UAT_REQUIRED - real upload, dashboard counters, and Session 41 Documents V2 remain owner FAIL
NEXT_ACTION=Juan reviews Session 41 v3 and validates corrected upload/counter journeys; do not regenerate other P&G sessions before Session 41 approval

DASHBOARD_COUNTERS_OWNER_UAT=FAIL
DASHBOARD_COUNTERS_OWNER_UAT_AT=2026-10-24T03:23:07Z
DASHBOARD_COUNTERS_OWNER_UAT_BUILD=UNKNOWN
DROPAREA_OWNER_UAT=FAIL
DROPAREA_OWNER_UAT_AT=2026-10-24T03:23:07Z
DROPAREA_OWNER_UAT_BUILD=UNKNOWN
OWNER_UAT_AT=2026-10-24T15:23:26Z
OWNER_UAT_BUILD=UNKNOWN

DOCS_V2_CURRENT_RESULT_AT=2026-10-24T15:23:26Z
DOCS_V2_STATUS=TESTING - owner UAT FAIL; Session 41 source quality gate FAIL
DOCS_V2_REPO_STATE=PASS - versioned Session 41 v3 package and both app-level baseline packs generated; focused quality tests pass
DOCS_V2_AGENT_SERVED_CHECK=NOT_RUN - local artifact validation only; no served browser journey claimed
DOCS_V2_OWNER=FAIL - current MANUAL.pdf is a meeting-summary-like output, not the required operational AMS support package
DOCS_V2_EVIDENCE_CONFLICT=NO - owner finding is accepted; output remains non-green until Juan validates corrected v3
SOURCE_COVERAGE=SOURCE_INCOMPLETE - video 00:35:05.367, transcript ends 00:23:55.890, end-time coverage 68.20%, final gap 00:11:09.477; 36 discrete frames are not continuous evidence; 11 post-transcript samples show gallery only
CLAIM_GROUNDING=20 SOURCE_CONFIRMED; 4 SOURCE_UNCERTAIN; 1 NEEDS_REVIEW; 0 EXTERNAL_VERIFIED
AMBIGUITY_HANDLING=PASS - 8 review items include REACH, auth audio conflict, data floor, incomplete statement, corruption-mining anomaly, coverage and speech gaps, OCR limits
APP_SEGMENTATION=PASS - PG RegDoc and North America CPRT Panelist Payments independent
SUPPORT_SCOPE=PARTIAL; DATA_FLOW=PARTIAL; ARCHITECTURE=PARTIAL; ACCESS_AUTH=PARTIAL; OWNERSHIP=PARTIAL; OPERATIONS=PARTIAL; RISKS=PARTIAL
OPEN_QUESTIONS=PASS (23); FOLLOW_UPS=PASS; EVIDENCE_TIMELINE=PASS; SOURCE_MAPPING=PASS
OLD_SECTION_COUNT=11
NEW_SECTION_COUNT=52 total Markdown headings (10 session-level + 21 per application; 18 operational sections each)
VIDEO_DURATION=00:35:05.367
TRANSCRIPT_COVERAGE=68.20% by final timestamp; 65.97% first-to-last span
COVERAGE_GAP=00:11:09.477
GROUNDED_CLAIMS=20
UNCERTAIN_CLAIMS=4
AMBIGUITIES=5 semantic/claim ambiguities; 8 total review-queue items
OPEN_QUESTIONS=23
PROCEDURES=0 evidence-supported SOPs
APPLICATIONS_IDENTIFIED=2
EXTERNAL_VERIFIED_FACTS=0
MINERU_INTEGRATION=EVALUATED_NOT_CONNECTED_OR_INSTALLED - [Document Explorer MCP](https://github.com/opendatalab/MinerU-Document-Explorer/blob/main/docs/mcp.md) offers retrieval/deep reading, TOC/grep and element/table/figure extraction; [MinerU Open MCP](https://github.com/opendatalab/MinerU-Ecosystem/blob/main/mcp/README.md) parses PDF/Office/images with OCR via remote API. Not used as semantic writer; no AMS source sent. Review privacy/API requirements before onboarding.
SESSION_41_QUALITY_GATE=FAIL - SOURCE_INCOMPLETE; not FULLY_GROUNDED
DOCS_V2_BUILD_START=2026-10-24 (UTC time not captured; local artifact build)
DEPLOYED=NO - no deployment requested/performed
SERVED_HEAD=217a95dc6aa69c6259a066740a0da0790a2e3e3c (unchanged; artifact-only work)
KANBAN_OWNER_PENDING=5
BLOCKER=Juan owner validation of Session 41 v3 and source gap resolution; full corpus generation held
NEXT_ACTION=Juan reviews v3 mission packs; then provide missing transcript/source for 00:23:55.890-00:35:05.367 and owner-revalidate before corpus regeneration

### Current execution result (2026-10-24)

Build `217a95dc6aa69c6259a066740a0da0790a2e3e3c` is served on desktop HTTP and LAN HTTPS; visible build badge, response header, HTML metadata, and versioned JS agree. HTML and JS responses are `no-store`; no service worker is registered. Browser UI counters reconcile with `/api/files` at 10 videos, 0 audio, and 9 transcribed.

The served browser selected safe MP4 files through the actual file input. It observed preflight, session creation, chunk 0 ACK, restored 8.0 MB after reselect, resumed after injected failure and pause, then auto-started and finalized two files independently under P&G. No browser JS errors; test files and sessions were cleaned. `/api/uploads` now returns compact ACK indices; detailed hashes remain in per-session state. Manifests without a live chunk request are reported `STALE_RESUMABLE`, not `UPLOADING` based on historical state.

Focused gates: 22 Python tests and 12 JS tests passed; browser verification passed on both served routes. Owner-reported counter and upload failures remain `FAIL`; Kanban stays `TESTING` pending Juan's device validation.

### Latest execution result â€” logical counters and upload safety (2026-10-23)

The Docker image already serves revision `7c0969be8e9b10e2cc230be282c5a47015a8d9fe`; a no-cache request confirmed that marker on desktop HTTP, direct dashboard HTTP, and LAN HTTPS. The browser displayed Videos 10, Audio 0, Transcribed 9, Pending 0 with no page errors. `/api/files` returned 10 logical rows and metrics `{videos: 10, audio: 0, transcribed: 9}`. Default filters are All. The implementation is already deployed, so this run did not restart the container. The `/api/folders` raw-diagnostics endpoint exceeded a 15-second read-only timeout; its data remains secondary under collapsed Storage diagnostics.

Five `UPLOADING` sessions were observed twice, 20 seconds apart. No ACK map, ACKed-byte count, or last-activity timestamp advanced; no temporary chunk write was visible. One persistent Brave connection to LAN HTTPS was visible at both snapshots; it was not attributable to an upload and no transfer connection was established to the dashboard port. `last_activity_at` below is derived from the latest part-file UTC write because session manifests do not store that field. All ACK maps remain exposed by the deployed `/api/uploads` resume listing.

| Session ID | File | State | Last activity (UTC) | ACKed chunks / bytes |
|---|---|---|---|---:|
| `09893e522b9d4a7f892c717b1e3e73e7` | `20261020_211838.mp4` | STALE_RESUMABLE | 2026-10-22T20:12:18Z | 135 / 1,132,462,080 B |
| `6025ca5bdd5c474eb40525f3ebc3ec7f` | `20261021_195800.mp4` | STALE_RESUMABLE | 2026-10-22T19:49:29Z | 901 / 7,558,135,808 B |
| `827e52166b2541499949c4e27a73d761` | `S43.mp4` | PAUSED_RESUMABLE | 2026-10-22T22:56:55Z | 121 / 1,015,021,568 B |
| `aff70b06780045aaa3eaa5ffbcb25cfd` | `Shadow_bridge_ams_app_support_211026.mp4` | STALE_RESUMABLE | 2026-10-22T18:12:04Z | 8 / 67,108,864 B |
| `d9dcaa5acc4d4c5faeba1427a0562264` | `AMS_KAP_-_Compliance_-_Session_2.mp4` | STALE_RESUMABLE | 2026-10-22T19:52:23Z | 1 / 8,388,608 B |

The same five IDs and ACK maps were present in the deployed API; no upload was cancelled or deleted. Two sessions also contain an unACKed `.part` file; both were preserved. One separate `COMPLETED` manifest (`f8e5fd25ee234a74906305fbfa26edfa`, Shadow Bridge, 801 chunks) remains outside the five resumable sessions. Worker API last reported 0 active and 0 pending jobs. The implementation, focused unit results (98 dashboard/API plus 21 capture-fragment tests), and previous filter journey remain unchanged.

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
WORKER=BLOCKED - worker API reports 0 active/0 pending and service RUNNING; last pipeline run failed at vision_ocr (exit 1); synthetic processing remains unverified
VIDEOS_TABLE=TESTING - selected listing/player/docs paths opened; full columns/sort/delete reason/internal-fragment journey not verified
HTTPS_MOBILE=TESTING - LAN HTTPS health and build marker pass; physical phone certificate/onboarding remains OWNER_PENDING

### Historical implementation snapshot â€” before served deployment verification

Dashboard inventory counter phase (2026-10-23): `/api/files` now includes logical `videos`, `audio`, and nonempty-transcription metrics computed from its exact visible row set; primary cards consume those values. `/api/folders` retains raw filesystem diagnostics and exposes the pending upload queue count separately. Added secondary, collapsed Storage diagnostics. Targeted tests: 98 passed, including 48 physical video files / 12 visible logical rows, hidden capture fragments, test session exclusion, audio, orphan/empty transcript exclusion and API reconciliation. `py_compile` and `git diff --check` pass. Implementation commit `3ec6bb6` and result commit `ff0a802` are pushed; Docker image built successfully with exact final HEAD marker `ff0a8022a9282557b63215977c6ed41826a17640`. Deployment waits because five existing sessions remain `UPLOADING`. Prior served API baseline: 12 logical videos, 0 audio, 9 transcribed; response has no metrics field. A read-only `/api/folders` probe timed out. Status stays TESTING until deployment and actual UI/table comparison. No owner media or upload data was changed.

DASHBOARD_COUNTERS_LOGICAL=IMPLEMENTED; pre-deployment snapshot, superseded by the result above
VIDEOS_LOGICAL_COUNT=12 prior served /api/files rows; 12 fixture rows from 48 physical files
AUDIO_LOGICAL_COUNT=0 prior served /api/files rows; logical audio fixture passes
TRANSCRIBED_LOGICAL_COUNT=9 prior served logical rows; fixture excludes orphan/empty .txt files
RAW_STORAGE_DIAGNOSTICS=preserved in collapsed secondary section; served raw diagnostics probe timed out
COUNTERS_MATCH_FILES_API=PASS in isolated tests; served comparison was pending at this snapshot
SERVED_VALIDATION=BLOCKED_PENDING_UPLOADS at this historical snapshot; superseded by live verification above
WORKER=BLOCKED; owner job remains active, ~5.2h heartbeat age, stale threshold 6h; 0 pending
DOCS_V2_REGENERATE=BLOCKED; provider key absent and ALLOW_EXTERNAL_LLM=false
VIDEO_EDITOR=TESTING (prior source-specific large WebM failure unresolved)
LIVE_CAPTURE=TESTING
REAL_CROP=TESTING
PLAYLIST=TESTING
VIDEOS_TABLE=TESTING
DEVELOPMENT_COMPLETE=NO
KANBAN_COMPLETE=8
KANBAN_TESTING=60
KANBAN_BLOCKED=4
KANBAN_OWNER_PENDING=3
SERVED_HEAD=74799c205c6f399aeecfa927a8baefba73aa69ba
BLOCKER=Five active uploads; deployment restart held to protect them
NEXT_ACTION=After uploads settle, deploy image marked ff0a8022a9282557b63215977c6ed41826a17640, compare cards to unfiltered table, validate filters unchanged, then resume worker/runtime and remaining SDD priorities.

Actual served revision `74799c205c6f399aeecfa927a8baefba73aa69ba` returned HTTPS `/api/health` 200 JSON and `/api/uploads` 200 JSON. Container is running/healthy at report time with restart count 4; inspect reports exit 0 and OOM=false, while retained logs do not identify the restart cause. During test execution the app timed out/unresponded and restarted. Caddy remained up. Persistent media and acknowledged owner upload sessions were not altered.

Drop Area on served build: selected two valid 12 KB synthetic MP4 files. Both immediately entered upload, completed one-chunk resumable upload/finalize under P&G without the Upload Selected button, and queued processing. No browser JS errors or failed network requests. The test jobs, files and sessions were individually removed after the run. They did not appear in Videos because the worker remained blocked by a pre-existing ACTIVE owner job; that job was left untouched. Thus auto-start and multi-file upload pass, but the full journey through processing/Videos does not.

P&G was the default in Drop Area and New Recording. Changing New Recording to Zo Interviews and reopening preserved the explicit choice. Capture itself was not started.

Resumable recovery: a synthetic 12.4 MB upload received five simulated HTML 502 responses for a chunk. UI retained ACK chunk 0 and showed an upload-specific 502 error. Retry in the first page stalled while the service became unstable. After reopening the served page and selecting the same file, upload resumed from the saved session and completed. Exact synthetic job `b63a4220012241ac8cd6e242c7a9ac83`, media `pg_zmi_retry_2.mp4`, session `55e35df40d0d474c97e9f463cb3dd652`, and local fixture were cleaned up; no user media/session was touched.

Docs V2: opened P&G `pg_Tidal.mp4`; UI showed v2 metadata, generated timestamp, human manual, AI package, procedure/review counts, evidence/source links, version selector and separate Reprocess Video. Regenerate created/selects v3 with `SYNTHESIS_BLOCKED_PRIVACY`; v1/v2 remained available and v1 reopened. No transcription/reprocess endpoint ran. Host/container had no OPENCODE_API_KEY and `ALLOW_EXTERNAL_LLM=false`; repository privacy policy blocks remote generation. No corpus content was sent and no saved CLI credentials were used. Historical corpus result (9/9 versions, 393 grounded claims, 273 review items) is preserved below and remains historical until revalidated as a served user journey.

Focused tests rerun on source: Python `tests/test_documentation_versioning.py`, `tests/security/test_dashboard_endpoints.py`, `tests/test_documentation_v2_regenerate_review.py`, `tests/test_documentation_v2_batch.py`, `tests/test_resumable_uploads.py`, `tests/test_processing_worker.py`: 92 passed. Node `tests/js/upload_reliability.test.cjs`: 9 passed. These are engineering evidence only and do not make visible features complete.

Latest served editor verification: from Videos, opened safe synthetic MP4 and WebM in Edit, applied trim, observed completed validated edit jobs, opened the derivative in the player, and confirmed playback advanced with `readyState=4`, video+audio streams and 6-second duration. Original SHA-256 values were unchanged. Safe source, derivative and provenance fixtures were removed. The previously failing 1.46 GiB owner/source WebM was not present; that exact failure remains unreproduced and no owner media was touched.

Latest served capture probe: fake-device New Recording entered recording and uploaded/finalized fragments, but the old E2E script timed out waiting for the UI label `Preview` after pressing Start; the served state machine correctly displayed `Recording`. Its assertions also assume no project is selected by default, which conflicts with the accepted P&G default. The script explicitly selected `Zo Interviews`, so this run does not validate P&G default, crop-before-recorder or playlist boundaries. Two test-tagged capture sessions (`sess-e1747a44ac2a`, `sess-4096000964ee`) finalized synthetic data. The app rejected their delete requests because finalized processing chunks are protected; they are not owner media and were not force-deleted. No synthetic pending processing jobs were reported; the only active job remains the pre-existing owner job. Update the test journey to current UI semantics before another capture run.

Runtime observation during this phase: container remained `Up (healthy)`, restart count 4, exit 0/OOM=false. One Docker health probe timed out while upload chunk requests were active; subsequent probe passed and the app continued returning health 200. This does not establish the cause of historical restarts or the timeout.

### ðŸŸ¥ RULE CONFLICT
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

1. [ ] AC-01 â€” Compression validates staged and published optimized media (container/playability, video stream, required audio behavior, measured positive duration within `max(2 sec, 5%)`, nonzero size, and meaningful size reduction) before deleting source. Evidence: synthetic FFmpeg tests and fault injection.
2. [ ] AC-02 â€” Source removal is limited to the exact provenance-linked source after atomic publish, persisted provenance, published hash verification, and media registration; all failures/retries preserve unrelated data and recover safely. Evidence: tests for every state transition and injected failure.
3. [ ] AC-03 â€” Provenance records relative source/output identity, hashes, sizes, measured durations, result and cleanup state; UI/API show size saved and cleanup outcome/reason. Evidence: schema/API/UI tests.
4. [ ] AC-04 â€” Live Capture assembles all ACKed fragments once, in order, validates final duration, and never removes source fragments until the final integrity and all processing chunks pass; after success only session temporary pieces are removed. Evidence: >=3-fragment regression and failure/restart tests.
5. [ ] AC-05 â€” Final recording duration is persisted from verified media metadata and shown correctly in Videos. Deletion control is always visible with deterministic enabled/disabled reason by media state; internal fragments/chunks are not exposed. Evidence: API/UI state matrix.
6. [ ] AC-06 â€” Mobile crop works with one-finger Pointer Events drag, pointer capture/cancel and video-relative coordinates for portrait/landscape and object-fit scaling. Evidence: mobile Playwright touch/pointer.
7. [ ] AC-07 â€” Documentation regeneration is visible on mobile and desktop, regenerates from saved evidence, records/selects a version, reports status, and does not invoke transcription, FFmpeg/keyframes, OCR or vision. Reprocess remains separate. Evidence: service spies and Playwright.
8. [ ] AC-08 â€” localhost:5000 and the current LAN HTTPS origin serve the same revision/backend and equivalent video/project/job/docs/worker state from one configured data/database/media root. Evidence: config, served build markers, normalized API parity.
9. [ ] AC-09 â€” Synthetic full workflow and Host E2E pass; production services are restarted from final reviewed HEAD and health/UI parity verified. Production UAT uses existing user data read-only except explicitly safe app-generated synthetic records; no real source is deleted as a test. Evidence: gate artifacts and deployment/rollback record.
10. [ ] AC-10 â€” Full applicable automated release gates pass under the current resource-aware RAM policy; DELIVERY records exact SHAs, tests, deployment health, residual risks and rollback path. Evidence: machine-readable gate artifacts and final DELIVERY.
11. [ ] AC-11 â€” Edit File supports a trimmed, validated display name without a typed extension; preserves the media extension, rejects unsafe/empty/colliding names, and persists the name by stable media ID without moving media or changing transcript, project, documentation, provenance, or processing history. Rename is idempotent and does not trigger processing. Evidence: `tests/test_dashboard_display_name.py`.
12. [x] AC-12 â€” Docs V2 supports corpus inventory and resumable batch regeneration from saved evidence, captures provider/model/privacy profile in version history, and never marks evidence-only output as semantic documentation. Missing upstream artifacts are reported separately. Evidence: `transcript_pipeline.documentation.batch_regenerate_v2`, `tests/test_documentation_v2_batch.py`, and per-video version manifests.
13. [ ] AC-13 â€” Global health/error presentation distinguishes service offline, worker error, active processing-stage error, and historical job failure. Each visible failure explains component, message, timestamp and affected file/job; resolved historical jobs do not poison current health. Evidence: focused classification/API/UI tests.
14. [ ] AC-14 â€” Screen Wake Lock is requested only when recording, continuous playlist capture, or foreground upload needs it; visibility, orientation, release and re-acquire are handled; unsupported browsers report unavailable. Evidence: deterministic Wake Lock lifecycle tests.
15. [ ] AC-15 â€” Multi-GB uploads use persistent upload sessions with bounded hashed chunks, ACK map, retry/resume, per-file cancel, and finalize size/hash/media validation before normal processing enqueue. Browser restart can discover resumable sessions and resume already ACKed chunks without re-sending them. Evidence: chunk/API/UT recovery tests.
16. [ ] AC-16 â€” Upload queue adapts simultaneous file count to file size, queued bytes, active transfers, backend health, network failures and available resources. Maximum remains six. Upload cards expose size, progress, percentage, speed, ETA, state, pause/resume/cancel/retry. Evidence: scheduler and UI tests.

### ðŸŸ¥ RULE CONFLICT â€” adaptive upload concurrency

Earlier accepted SDD behavior fixes default upload concurrency at 4 and maximum at 6. This request explicitly reconciles that rule: adaptive scheduling replaces the fixed default, with the accepted maximum of 6 preserved. The prompt's shorthand â€œ24â€ / â€œ12â€ is interpreted as 2â€“4 medium and 1â€“2 multi-GB files, consistent with the explicit maximum. Keep this ðŸŸ¥ RULE CONFLICT record as the change audit trail; the implementation below follows this explicit reconciliation.

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


## ðŸŸ¥ RULE CONFLICT POLICY

Within project-defined rules, this policy has highest priority. If a new request conflicts with an SDD requirement, approved architecture decision, validated behavior, release/resource policy, or another current requirement, do not silently select a side or regress validated behavior. Record `RULE_CONFLICT=YES` in `## CURRENT_RESULT`, followed by:

### ðŸŸ¥ RULE CONFLICT
Existing rule:
New instruction:
Conflict:
Regression risk:
Recommended resolution:
Preserved behavior until resolution:

## ðŸŸ¥ USER-FACING COMPLETION SEMANTICS

This owner rule supersedes earlier completion interpretations in this SDD and its execution plan. Unit tests, implementation, synthetic browser/API checks, or artifact existence alone do not complete user-facing functionality. Such features remain `ðŸŸ¨ TESTING` until their full journey passes against the actual served build. Only physical-device behavior that cannot be verified without the device may remain `OWNER_PENDING`. Preserve existing validated behavior while reopening unverified rows; do not downgrade or remove historical evidence.

Preserve previously validated behavior unless the new instruction explicitly supersedes it. This policy does not override platform, security, or system constraints. Only one SDD per repository may be pointed to as active for `/revisa`; update `.agents/CURRENT.json` when the canonical active SDD changes.

## Planning

PLAN: `.agents/deliverables/PLAN-ZMI-LIFECYCLE-001-recording-storage-docs.md`
TEST MATRIX: `.agents/deliverables/TEST-MATRIX-ZMI-LIFECYCLE-001.md`

## Finalization Kanban (authoritative - sole active Kanban)

This is the one active feature inventory and execution table for this SDD. All dated Kanbans in historical artifacts are evidence only. Allowed statuses: `TODO`, `ðŸŸ¦ DEVELOPING`, `ðŸŸ¨ TESTING`, `ðŸŸ¥ BLOCKED`, `ðŸŸ© COMPLETE`, `OWNER_PENDING`, `OPTIONAL`, `NOT_REQUIRED`.

| Feature / Gate | Status | Evidence | Next Action | Owner |
|---|---|---|---|---|
| Drop Area: auto-start, two-file resumable upload, P&G assignment | ðŸŸ¨ TESTING | Build 217a95d served; browser observed first ACK, failure and paused reselect resume, and two files auto-start/finalize. Owner UAT remains FAIL. | Juan validates real device select/drop and resume. | Owner UAT pending |
| Upload retry/resume after simulated 502 | ðŸŸ¨ TESTING | Served synthetic 12.4 MB upload: five chunk 502s, ACK 0 preserved, upload-specific 502 shown; fresh-page reselect resumed and completed. Retry-in-place stalled during service instability. Test records cleaned. | Stabilize ZMI and repeat pause/retry/resume journey; verify processing result. | Agent |
| P&G default: uploads and New Recording | ðŸŸ¨ TESTING | Served UI selected P&G for uploads and New Recording; explicit Zo Interviews choice persisted after reopening. Camera/audio/playlist capture not started. | Verify project inheritance through real served capture and playlist journeys; phone-only hardware checks by Juan. | Agent |
| Docs V2 served UI, document and version history | ðŸŸ¨ TESTING | Served P&G Tidal v2 opened with manual/package, metadata, evidence links, review count, versions v1/v2 and separate Reprocess. Regeneration selected v3; v1/v2 stayed accessible. Full semantic panels/source-grounding content not fully validated. | Validate one full P&G document including timeline, claims, mappings and review queue; verify version history. | Agent |
| Docs V2 semantic regeneration from saved evidence | ðŸŸ¥ BLOCKED | Served regeneration created v3 `SYNTHESIS_BLOCKED_PRIVACY`; no remote corpus sent. Host/container lacks OPENCODE_API_KEY; `ALLOW_EXTERNAL_LLM=false`; privacy policy forbids bypass. | Restore authorized provider/auth configuration without exposing credentials; retry one document only. | Agent |
| ZMI runtime and worker processing | ðŸŸ¥ BLOCKED | Health is 200 and container healthy; one restart since current container recreation, exit 0/OOM=false. Retained Docker events have no die/OOM event explaining earlier restarts. Owner job remains ACTIVE at ~5.2h heartbeat age (<6h stale threshold); worker now reports 0 pending. Five upload sessions are still UPLOADING. | Preserve owner jobs/uploads; wait for stale policy and uploads; validate a synthetic job only after safe availability. | Agent |
| Old P&G Documents V2 cleanup | COMPLETE | 249 exact generated manual/semantic files inventoried by size and SHA-256, logged, invalidated and deleted; 0 transcripts removed; raw evidence and provenance retained. | Keep invalidation ledger with release record. | Agent |
| Manual filename normalization | TESTING | Named source-stem MD/PDF/JSON contract implemented; Session 41 golden trio remains owner-approved. | Verify S46 trio only after all technical gates pass. | Agent |
| P&G media inventory reconciliation | TESTING | SFTPGo mount, Videos, Video_compress aliases, API assignments and transcript sidecars are being reconciled; Session 18 remains an explicit assignment conflict. | Finish logical deduplication and duration/status inventory. | Agent |
| P&G transcript completeness | ???????? TESTING | Session 41 is VALID; its 00:11:09.476 trailing media is verified non-speech. S46 recovery is 83/83, 98.85% effective coverage, with 5.730s low-confidence residual awaiting source-audio review; S43 remains corrupt/incomplete. | Recover S46 gaps individually, reconcile all transcript sidecars, and preserve S43 source recovery evidence. | Agent |
| Session 41 Documents V2 golden sample | COMPLETE | Technical gates PASS; owner UAT PASS and golden approved. Golden preserved unchanged. | Reopen only on regression. | Juan approved |
| Documents V2 production overfit | ???????? COMPLETE | Generic MediaEvidenceBundle/session pipeline; production scanner rejects sample-specific app names, claims, frame IDs, timestamps, and semantic vocabulary. Scanner test passes. | Keep scanner in regression suite. | Agent |
| Golden 2 S46 generic quality gate | BLOCKED | Source, visual (7/7), claim ledger (223), generic application extraction, and overfit checks pass. 83/83 recovery windows complete; 5.730s remains low-confidence across two spans; no Golden 2 trio generated. | Resolve gap-062 and prior-recovery-3443 from source audio; then generate only S46 through generic production logic if speech gate passes. | Agent |
| Cross-session knowledge and Mission Pack | ???????? TESTING | Exact-alias resolver, conflict-safe merge, provenance graph, and multi-session Mission Pack generation integrated; controlled confirmation/extension/supersession/conflict and provenance tests pass. No real cross-session P&G pack generated. | Run only after an additional eligible approved session exists. | Agent |
| Application Mission Pack generation | TESTING | Generic generator emits provenance-bearing MD/PDF/knowledge JSON; controlled cross-session integration passes. No real multi-session application pack until an eligible second sample exists. | Run after Golden 2 and cross-session evidence pass. | Agent |
| P&G transcript inventory reconciliation | TESTING | 20 logical readable media; 15 physical sidecars match 12 transcript sources, including 3 divergent duplicate copies; 8 sources lack transcripts. Session 10 targeted recovery has 3 candidates reviewed but still needs broader VAD coverage. | Continue one source at a time; preserve divergent copies and validate every output. | Agent |
| Mobile reliability + large-file upload V2 | ðŸŸ¨ TESTING | Deployed through ZMI image `8a67343a6daecb7e691fe3d0d6d73efbaf6f5bcc`; root cause was a stale served image missing `/api/uploads` and the package omitted its static helper. Caddy HTTP and LAN HTTPS return JSON 200 for GET `/api/uploads`; authenticated POST creates a synthetic session (200); chunk ACK, resume status and idempotent retry work; finalize returns JSON validation response for synthetic invalid media; synthetic session deleted. The served helper JS returns 200 and guards non-JSON responses. Storage preflight and oversize create return JSON 507 with free/required GiB. Served UI contains badge, bytes/total, percentage, speed, ETA and Pause/Resume/Cancel/Retry. No real owner files retried. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Resumable upload recovery after transient app outage | ðŸŸ¨ TESTING | ZMI deployed at `a99effb`; transient 5xx/network retry on preflight/create/status/finalize, with chunk ACK retry preserved. Python 10 and Node 9 pass. Candidate and served LAN HTTPS synthetic create/chunk/resume/finalize-error/cleanup passed. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Resumable Upload API | ðŸŸ© COMPLETE | Production through Caddy HTTP/HTTPS: GET/POST `/api/uploads`, chunk PUT, resume GET, finalize POST return JSON; small synthetic ACK/resume/retry and cleanup passed. 10 focused Python tests pass, covering synthetic 5 GiB, transient 502, resume, successful finalize, ACK preservation, ENOSPC mapping and packaged asset. 7 Node tests pass. | None; retain coverage. | Agent |
| Non-JSON error handling | ðŸŸ© COMPLETE | Response parsing checks Content-Type; text/HTML failures show `Upload failed: HTTP <status> <reason>`. Node suite 7/7 includes HTML response handling; served helper JS returns HTTP 200 and UI badge says Upload error. | None; retain coverage. | Agent |
| Storage preflight | ðŸŸ¨ TESTING | Upload target `Video_compress` is on C: via `/data`; host 106.55 GiB free, Whisper `/data` 106.53 GiB free, Docker backing volume C: 106.55 GiB free. 2 GiB safety reserve; batch sum and live preflight enforced before create/chunk/finalize. Production synthetic 200 GiB request rejected before session creation with `Insufficient storage: 106.7 GiB free, 202.0 GiB required.` | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| ENOSPC handling | ðŸŸ¨ TESTING | Chunk/finalize `ENOSPC` maps to JSON 507 and actionable free-space guidance; low-space finalize/chunk tests preserve prior ACK map. Production low-space preflight returns JSON 507. Upload UT 10 passed. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Deploy | ðŸŸ© COMPLETE | Current source implementation `74799c205c6f399aeecfa927a8baefba73aa69ba` is served over LAN HTTPS; health and `/api/uploads` returned JSON 200. ZMI is currently healthy, restart count 4; Caddy and persistent data volumes stayed up. | Investigate intermittent ZMI restarts before declaring operational stability. | Agent |
| Persistent /revisa result contract | ðŸŸ¨ TESTING | `main:.agents/CURRENT.json` points to the active branch and canonical SDD; status-only commit `9221a33` explicitly says implementation is not merged/deployed. | Refresh status-only main pointer after implementation checkpoint and verify remote. | Agent |
| Real multi-GB UAT | OWNER_PENDING | Screenshot showed transient `Failed to fetch`; ZMI OOM event (exit 137) at 18:13:33 UTC; persistent session retains 8 ACKed chunks / 64 MiB. No owner media retried, canceled, or deleted. | Juan resumes one selected file after retry-hardening deploy. | Juan |

| Documentation V2: corpus inventory and resumable regeneration | ðŸŸ¨ TESTING | Initial scan was 9 total: 1 ready, 1 transcript missing, 1 keyframes missing, 6 missing both. Local-only preprocessing reused valid artifacts and completed missing transcripts/keyframes for all 9; final inventory reports 9 READY. Prep progress is resumable and persisted per media. | Validate complete user flow against stable served build; preserve current evidence and owner data. | Agent |
| Documentation V2: semantic regeneration of full current corpus | ðŸŸ¥ BLOCKED | Historical 9/9 artifacts, 393 claims and 273 review items retained; current served regeneration returned SYNTHESIS_BLOCKED_PRIVACY because remote LLM is disabled and auth is unavailable. | Restore authorized provider configuration safely; validate one served real document and regeneration before corpus continuation. | Agent |
| Edit File: user-visible media name | ðŸŸ¨ TESTING | Display name stored atomically by stable media ID; original path and extension remain unchanged. `watcher/venv/Scripts/python.exe -m pytest tests/test_dashboard_display_name.py -q` â€” 7 passed; `compileall` passed. Covers UI field, extension, trim, invalid/empty/collision, linked project/transcript/docs, playable media and idempotency. | None. | Agent |
| LAN availability incident | ðŸŸ¨ TESTING | Follow-up check found ZMI health checks and `docker exec` failing because its overlay rootfs path was missing; HTTP also timed out. Compose labels confirmed project `whisper`, `compose.yml`, service `zmi`. Queue had 0 active/pending jobs and capture sessions were closed. Recreated only ZMI with `docker compose -p whisper -f compose.yml up -d --no-deps --force-recreate zmi`; Caddy was left running. `/data` bind and `whisper_zmi-model-cache` volume remain mounted. ZMI is healthy; Docker Engine 29.5.3; desktop HTTP, LAN HTTPS, LAN `/setup`, and dashboard return 200; worker RUNNING 0/0; Videos 9, projects 4, shared-media references 9/9 valid. Ethernet `192.168.50.20`. | None. | Agent |
| Live Capture: Camera mode, Audio-only mode, Camera microphone ON by default, visible microphone status | ðŸŸ¨ TESTING | Served fake-device flow created a capture session and finalized video+audio fragments. Legacy script timed out waiting for `Preview` after Start; served state is `Recording`. Does not validate the full capture journey. | Update focused journey for current state semantics, then validate stop/finalize/player; phone-only camera/mic behavior remains Juan's UAT. | Agent |
| Live Capture: rear camera, camera switching, portrait/landscape | ðŸŸ¨ TESTING | Prior synthetic camera/orientation browser coverage; physical device remains owner UAT. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Live Capture: resolution selection, actual resolution display, recording timer | ðŸŸ¨ TESTING | Prior capture API/browser evidence; verified by current root unit suite (1230 passed, 8 skipped). Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Live Capture: project inheritance, stop/cancel/retry | ðŸŸ¨ TESTING | Capture session, cancel/retry and playlist tests were included in prior targeted runs. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Compression integrity: validate staged and published media, video/audio streams, positive duration tolerance, nonzero size and meaningful reduction | ðŸŸ¨ TESTING | `test_media_optimize.py` and full root unit suite pass; source is retained until candidate and published output validate. | None; maintain coverage for future edits. | Agent |
| Compression cleanup: atomic publish, exact provenance-linked source removal, retries/recovery preserve unrelated data | ðŸŸ¨ TESTING | Full root unit suite passes (1230 passed, 8 skipped), including compression/storage failure paths. | None; cleanup remains provenance-scoped. | Agent |
| Compression provenance API/UI: original/optimized sizes, bytes saved, cleanup outcome and reason | ðŸŸ¨ TESTING | Compression API/UI unit coverage in the passing root suite. | None; verify in optional served UI check. | Agent |
| Real Live Crop: crop applied before MediaRecorder; WebM contains cropped pixels; microphone audio preserved | ðŸŸ¨ TESTING | Prior synthetic WebM crop measured 1280x720 -> 636x360 with audio. Current served capture attempt did not reach crop selection; no new crop evidence. | Re-run after correcting served journey; validate encoded pixels/dimensions and audio before marking complete. | Agent |
| Real Live Crop: output dimensions persisted; encoded dimensions reduced; preview maps to encoded crop | ðŸŸ¨ TESTING | Root unit suite passes 1230 with 8 skipped, including crop and assembly behaviors; prior synthetic WebM evidence confirms reduced encoded dimensions and audio preservation. A production capture reported `CROP_OUTPUT_MISMATCH`; retained as owner UAT advisory. | Juan verifies orientation/crop on device during UAT. | Agent |
| Mobile crop input: Pointer Events, pointer capture/cancel, object-fit/video-relative coordinates, portrait and landscape | ðŸŸ¨ TESTING | Crop geometry and pointer journey covered by prior synthetic UI evidence and current root unit suite. | None; phone UAT remains owner-only. | Agent |
| Fragment pipeline: short upload fragments, ACK/idempotency, incremental upload | ðŸŸ¨ TESTING | Prior 60 fragment/assembly/processing/API tests and fresh 38-test fragment rerun passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Fragment pipeline: final assembly, complete duration, one recording -> one visible final media | ðŸŸ¨ TESTING | Prior assembly tests and verified media-duration evidence; current relevant root suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Fragment pipeline: safe fragment cleanup and provenance retention | ðŸŸ¨ TESTING | Prior failure/recovery and cleanup tests; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Continuous playlist: continuous recording, title detection, multi-frame confirmation, logical boundaries | ðŸŸ¨ TESTING | Served fake-device attempt used playlist mode and finalized a synthetic capture, but timed out on a stale UI-state assertion before validating title boundaries/review. | Correct journey and verify title detection, boundaries and saved logical videos in served UI. | Agent |
| Continuous playlist: project inheritance, review/rename/split/merge | ðŸŸ¨ TESTING | Prior playlist/session suites cover logical video operations. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: preview, TIME/FRAME modes, 8 crop handles, drag/resize | ðŸŸ¨ TESTING | Prior API/unit and browser evidence for TIME/FRAME and eight handles; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: zoom/pan, HH:MM:SS, timeline | ðŸŸ¨ TESTING | Prior editor API and browser evidence; current relevant root unit suite passed. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video editor: black interval detection, black-border detection, Apply Changes | ðŸŸ¨ TESTING | Served UI Edit/Apply passed for safe MP4 and WebM; validated playable 6-second derivatives retained audio and originals' hashes were unchanged. Earlier 1.46 GiB WebM failure source is unavailable, so that case remains unverified. | Keep original-source failure open until its exact input can be safely reproduced; continue remaining editor controls in served journey. | Agent |
| Video editor: edited copy, original preserved, idempotency | ðŸŸ¨ TESTING | Prior 16+ focused edit tests cover derivative validation, provenance, and source preservation. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Black video: temporal black trimming, spatial black crop, NEEDS_REVIEW, safe original preservation | ðŸŸ¨ TESTING | Prior black-video tests cover temporal intervals, borders, review and source preservation. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Black video: optional black auto-stop warning | ðŸŸ¨ TESTING | Prior browser evidence covers Off default, countdown, content-return cancellation and stop. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Multi-upload: multiple files, streaming/bounded memory | ðŸŸ¨ TESTING | Prior browser/memory evidence: 6x24 MiB upload, +79.7 MiB; no current-candidate rerun. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Multi-upload: concurrency default 4, configurable maximum 6, per-file retry/cancel | ðŸŸ¨ TESTING | Prior 4/6 concurrency browser checks and upload retry/cancel evidence. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Worker: periodic scan, day limit 1, night limit 3 | ðŸŸ¨ TESTING | Worker configuration and scheduling tests exist; live API currently reports worker RUNNING, zero active/pending. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Worker: stale recovery, idempotent claim, cancellation, no duplicate processing | ðŸŸ¥ BLOCKED | Latest `/api/status`: worker RUNNING, 0 active and 0 pending; pipeline `running=false`, last error `transcript_pipeline.pipeline.master failed (exit code 1)` at `vision_ocr`. No job was active during counter verification. | Diagnose the previous pipeline failure; prove a synthetic job completes in Videos before changing runtime behavior. | Agent |
| Documentation Synthesis V2: Evidence Timeline, semantic grouping, procedures | ðŸŸ¨ TESTING | Current root unit suite passes 1230 with 8 skipped; synthetic Live Capture -> keyframe -> Docs V2 integration selection passes 15 tests with 5 HTTPS interception skips. | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Documentation Synthesis V2: decisions, claims/evidence, ambiguity/review queue, source mapping | ðŸŸ¨ TESTING | Docs V2 evidence-grounding and source mapping implementation/tests exist. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Documentation regeneration boundary: regenerate from saved evidence without transcription/FFmpeg/OCR/vision; separate reprocess; version history | ðŸŸ¨ TESTING | Regeneration isolation, versioning and separation unit suites pass in current root run (1230 passed, 8 skipped). | None; UI/browser check advisory. | Agent |
| Documentation Synthesis V2: regenerate documentation, reprocess video, documentation versioning | ðŸŸ¨ TESTING | Prior regeneration/versioning tests passed; UI keeps regeneration separate from reprocessing. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Video list: Project, Date, Duration, sorting, Show/player | ðŸŸ¨ TESTING | Final served `/api/files` returns 60 rows; projects API returns 5 projects; smoke confirmed no chunk-named rows. Unit suite passes 1230 with 8 skipped. | None. | Agent |
| Video list: delete eligibility/reason; hide internal chunks | ðŸŸ¨ TESTING | Prior API/UI state-matrix and fragment visibility evidence. Relevant current root unit suite: 1230 passed, 8 skipped (2026-10-20). | None; optional browser checks and owner phone UAT remain separate. | Agent |
| Dashboard logical inventory counters | ðŸŸ¨ TESTING | Build 217a95d HTTP and LAN HTTPS show UI/API 10/0/9 with matching SHA and no-store assets. Juan still reports physical values. | Juan revalidates counters on his browser/device. | Owner UAT pending |
| HTTPS/mobile: desktop/LAN shared data, HTTPS certificate, /setup, public CA, QR onboarding | ðŸŸ¨ TESTING | Focused LAN/setup tests pass 31/31. Final desktop HTTP and LAN HTTPS return 200 with marker matching HEAD; `/setup` and QR return 200; `/api/network` reports configured HTTP/HTTPS ports 5000/5001, LAN IP `192.168.50.20`, and certificate fingerprint. | Juan installs public CA and validates phone onboarding during UAT. | Agent |
| Overview Stats Modal: toolbar icon opens modal; reuse existing metrics; four required metrics | ðŸŸ¨ TESTING | `tests/e2e/overview_stats_modal.py`: 12 browser checks pass on final app source; four metric labels/values match existing metrics. | None. | Agent |
| Dashboard compact layout: Drop Area left; Pipeline and Folders stacked right; responsive, content-sized cards | ðŸŸ¨ TESTING | Playwright layout test at 1440x1000 verifies two-column left/right stack; at 390x844 verifies one-column order and no horizontal overflow. CSS cards align to content; no fixed heights. | None; Juan may review live appearance during UAT. | Agent |
| Mobile capture 502 diagnosis | ðŸŸ¨ TESTING | Caddy logs at 2026-10-20 20:19:27Z show proxy 502 during clean app restart: `/api/capture/sessions` connection refused; health/status/log requests timed out/reset. Container exit 0, OOMKilled=false. No fragment POST 502 in retained history. Confirmed client defect: JSON-only parse then immediate recorder stop on transient upload failure. | Preserve new proxy/app diagnostics for future recurrence. | Agent |
| Mobile capture retry/recovery | ðŸŸ¨ TESTING | Fragment/status/final-drain retries handle network + HTTP 408/425/429/500/502/503/504; six retries, exponential delay capped at 30s. Stable fragment ID and IndexedDB copy remain until ACK; reconnect/manual retry supported; visible retry state and graceful bounded-queue pause. | Phone UAT. | Agent |
| Mobile capture unit tests | ðŸŸ¨ TESTING | `pytest` focused capture/media suite: 113 passed (2026-10-20), including retry-state/template contract and rendered JavaScript `node --check`. Tests use `tmp_path`. | None. | Agent |
| Focused integration/API test for 502 recovery | ðŸŸ¨ TESTING | Flask API integration injects upstream-style HTTP 502 then replays same ID/body; next request ACKs exactly one stored fragment. Separate temporary storage OSError returns 503 then same-ID retry succeeds. | None. | Agent |
| Publish readiness | ðŸŸ¨ TESTING | Relevant suite 113 passed; `compileall` passed; Docker image build passed; isolated tmpfs container served dashboard and `/api/health` 200; Caddy config validates. Ready to publish. Production deployment not requested in this task. | Juan phone UAT after publication. | Agent |
| Preview layout: state spans both columns; video and transcript panels occupy intended grid cells | ðŸŸ¨ TESTING | CSS change is in pushed/served SHA `f6bb5c9`; visual browser check not run. | Check preview layout at desktop and mobile widths. | Agent |
| Manual transcript entry for media without a transcription | ðŸŸ¨ TESTING | `tests/test_project_override.py`: 21 passed, including create, validation and rollback cases (2026-10-20); served browser form visible. Tests use isolated temporary roots. | None. | Agent |
| Overview Stats Modal: responsive layout, close/X/Esc; modal remains available without inline Overview card | ðŸŸ¨ TESTING | Prior 12 browser checks verify modal controls and metric rendering; owner amendment changes only the inline card placement. | None. | Agent |
| Relevant unit tests: all new/changed business logic | ðŸŸ© COMPLETE | Current focused rerun: 92 Python tests passed; `tests/js/upload_reliability.test.cjs`: 9 passed. Tests remain engineering evidence, not user journey completion. | Run targeted tests for each subsequent fix. | Agent |
| Build/import/start and schema/config migration validity | ðŸŸ© COMPLETE | Current served build marker is exact implementation HEAD `74799c205c6f399aeecfa927a8baefba73aa69ba`; HTTPS health 200, container running/healthy at check. Four restarts during run remain operational issue. | Diagnose repeated restarts; rerun health after stability work. | Agent |
| Data safety: semantic reference and media validation | ðŸŸ¨ TESTING | Current `/api/files`: 23 records, 0 missing nonempty paths; worker RUNNING, 0 active/0 pending. Existing current finals passed ffprobe; earlier capture finals and nonempty general media validated. Test roots isolated. Explicit confirmed DELETE API responses account for missing cancelled captures/chunks and Tidal files; see reconciliation below. | Continue semantic checks; raw inventory equality is not a release condition. | Agent |
| Integration tests | TODO | Current-run `PASS`: synthetic integration selections passed 15 tests, 5 skipped (HTTPS interception); live-worker process-restart case excluded to keep shared data safe. | Attempt after unit tests when practical; record one advisory result. | Agent |
| Media regression | TODO | Current-run `PASS`: crop, assembly, black-video, and dashboard API media regression selection passed 36 tests. | Attempt after unit tests when practical; record one advisory result. | Agent |
| Playwright | TODO | `PASS`: Overview modal 12/12 checks; New Recording and Video Editor open on the deployed app source. Concurrent production Video Editor apply job `c8tdRWsMDGpD3_eYfDV_7TZf` failed output validation on an existing 1.46 GB WebM; original stayed intact. Record as advisory defect, not a publication blocker. | Juan reviews the edit failure during UAT; no automatic retry. | Agent |
| Host E2E | TODO | Prior Host E2E passes on earlier revisions; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Docker E2E | TODO | Prior Docker E2E pass exists for earlier revision; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Security scans | TODO | Prior security suite passed; current-run result `NOT_RUN`. | Attempt when practical; record advisory result. | Agent |
| Jenkins / Sonar / soak | TODO | Explicitly removed from release gates by current policy. | None. | Agent |
| Deploy latest compact UI + capture 502 resilience | ðŸŸ¨ TESTING | Rebuilt only active `whisper` project service `zmi` from current main; desktop HTTP and dynamic LAN HTTPS return 200 with build header/page meta matching final main. Health ONLINE; worker RUNNING 0 active/0 pending; `/setup`, QR and CA return 200. Current APIs show 17 media rows, 4 projects and 0 missing references. Served page contains compact two-column grid/side stack, New Recording modal and IndexedDB capture retry/reconnect code with stable fragment IDs; focused 502 recovery tests and layout checks are already recorded above. Persistent `/data` bind and `whisper_zmi-model-cache` volume retained. Inventory changed from 743 files / 8,586,030,623 bytes pre-build to 742 / 8,586,030,615 after first refresh; one-file/eight-byte delta and concurrent `projects.json` edit are unexplained, no delete/prune/volume operation was run. | Juan phone capture UAT. | Agent |
| Post-deploy smoke: served revision=FINAL_HEAD, layout/transcript entry, Videos/projects, Overview modal, /setup | ðŸŸ¨ TESTING | Desktop HTTP 200 and LAN HTTPS 200 both report exact SHA `f0800e22ccf9e4412087f0e0034c282dc4d79296`; health ONLINE; worker RUNNING/0/0; current projects and 23 files load, 0 missing nonempty refs. Browser smoke: Overview modal/metrics, New Recording Camera and Audio modes, VP8 Show/player metadata, editor HH:MM:SS, documentation regenerate visible. `/setup`, QR SVG and CA download return 200 (CA 418 bytes). | Juan validates phone later. | Agent |
| Physical phone UAT | OWNER_PENDING | Juan's device validation is final acceptance; automated tests do not substitute. | Juan validates capture/audio/crop/playback after deployment. | Juan |
| Release candidate integrity | ðŸŸ¨ TESTING | RC `32be478a8a7e9ef837b4d12e9435ed0480acbcf4` matched feature branch and `origin/feat/zmi-documentation-synthesis-v2`; clean three-way merge parent preserved. | None. | Agent |
| Merge to production branch (`main`) | ðŸŸ© COMPLETE | Merge commit `a497f4f19ca401902afa653c37a1c214fc9143d4`; parents are pre-merge production `f14ed96b76d2ea48b137eb1910ccc68f7d347ff5` and validated RC. Post-merge unit suite passed 1232, 8 skipped; production branch and subsequent SDD updates are pushed. | None. | Agent |
| Release tag | ðŸŸ© COMPLETE | Annotated original tag `whisper-2026-10-20` preserved at `77108a2`; patch tag `whisper-2026-10-20.2` pushed at final production SHA `f0800e22ccf9e4412087f0e0034c282dc4d79296`. | None. | Agent |
| Production deploy | ðŸŸ¨ TESTING | Previous HEAD `74799c2` remains served. New image marked pushed HEAD `ff0a802` built successfully; no container recreation while five owner upload sessions remain UPLOADING. | Recheck upload state, then deploy and verify exact build marker/health without changing data or model-cache mounts. | Agent |
| Production smoke | ðŸŸ¨ TESTING | Served release and functional smoke passed; exact results recorded above. | None. | Agent |
| Galaxy UAT | OWNER_PENDING | Juan's physical phone validation remains final acceptance. | Juan validates capture/audio/crop/playback. | Juan |
## HISTORICAL_EXECUTION_RESULTS

Complete during implementation; link exact command, result, artifact and SHA for each AC. The canonical release policy and resume order are in the execution-plan `FINAL SDD RELEASE RUN` section. This SDD section is the only active Kanban; other dated tables are historical evidence.

### Production data-safety reconciliation - 2026-10-20

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


### Mobile capture 502 diagnosis and repair - 2026-10-20

Caddy logs correlate upstream 502s with a graceful ZMI container restart at `2026-10-20T20:19:27Z`: container `whisper-zmi-1` exited with code 0, `OOMKilled=false`, then started again. During the gap Caddy returned 502 for `/api/capture/sessions` (connection refused) and adjacent `/api/health`, `/api/status`, and `/api/logs` requests (upstream timeout/reset/EOF). This establishes the observed 502 class as a proxy-to-app availability gap during restart, not an invalid capture endpoint or media payload. Retained Caddy logs show no fragment POST with 502 at that timestamp, so the exact request the phone displayed cannot be recovered from historical logs.

The client-side failure that turned a transient outage into a stopped capture was confirmed in `dashboard.html`: fragment uploads parsed every response as JSON without checking HTTP status; a 502 HTML response raised a parse error, immediately called `setStalled`, and stopped MediaRecorder. Session polling also swallowed transport failures without showing recovery state. That response handling made a temporary backend restart look like a terminal recording failure.

Repair: fragment requests now check HTTP status and retry network/408/425/429/500/502/503/504 failures up to six times with exponential backoff capped at 30 seconds. They keep the stable fragment ID and IndexedDB copy until ACK; recording continues while the bounded queue has room, then pauses visibly. Manual Retry and reconnect reuse the same ID. Status polling retries and displays a reconnect message. Final drain retries safely and retains an explicit manual retry state if ACK cannot be confirmed. Server storage errors return actionable 503 JSON and structured session/fragment logs; capture 5xx responses include status, path, elapsed time, client and request ID. Existing Caddy reverse-proxy error logs distinguish upstream timeout, connection refusal, and reset; app logs record capture 5xx with status, path, elapsed time, client and request ID. No access-log directive was added, avoiding capture of dashboard auth headers.

Focused recovery tests inject both an upstream-style 502 and an app storage `OSError`, retry the same fragment, and verify one durable ACK. These tests use the existing `tmp_path` isolated media roots; no unit/API test writes to shared production media. Playwright layout checks cover desktop and mobile viewport arrangements; physical mobile capture UAT is still owner-side.

### Owner interventions

Expected: 1. INITIAL_SPEC (this frozen US and production publication authorization). Physical Galaxy UAT is owner-only follow-up, not a release handoff. Unexpected: 0 unless a typed external blocker applies.

### Terminal state

`READY_FOR_DEPLOY` after implementation gates, commit and push; `RELEASED` after production deployment/verification. Galaxy phone UAT may remain `OWNER_PENDING` after release and does not hold automated delivery. `DONE` after required owner phone acceptance when available.

### Docs V2 OpenCode Go Resume Check (2026-10-21)

- Official OpenCode Go endpoint requires a dedicated Go API key. CLI stores that API key under `opencode-go` in `~/.local/share/opencode/auth.json`; `auth login opencode` does not create a reusable session token for the direct `/chat/completions` API.
- Root cause: `.agents/session/run_docs_v2_opencode_go.py` unconditionally loaded the saved `opencode-go` key and copied it to `LLM_API_KEY`; the compatible client then sent that expired value as Bearer auth. A legacy `LLM_API_KEY` remains in `scan_config.env`, but the OpenCode host now ignores it.
- Fix: `Settings` supports `OPENCODE_API_KEY`, the OpenCode client uses only that dedicated setting for `opencode.ai`, and the batch runner no longer reads `auth.json` or legacy `LLM_API_KEY`. Secrets are not persisted by the runner.
- Historical inventory/preprocessing results remain below as records only. Session 41 v3 is now the quality benchmark and remains OWNER_UAT=FAIL / SOURCE_INCOMPLETE. Do not regenerate any other P&G corpus item until Juan validates Session 41 v3.
