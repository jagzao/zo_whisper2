# US-ZMI-CAPTURE-001 — Record a physical process and turn it into knowledge

## Status
FROZEN_FOR_IMPLEMENTATION

## User story
As a Zo Media Intelligence user,
I want to open the camera from the portal, focus on the relevant screen/area, record a long session safely, and have completed segments processed while I continue recording,
so that I finish with one useful semantic manual and knowledge artifact without manually moving giant video files.

## Acceptance criteria

### CAP-01 Camera permission
Portal requests camera/microphone through browser APIs and gives a clear unsupported/permission-denied state.

### CAP-02 Local security
Existing localhost-only Host/Origin/token protection is unchanged.

### CAP-03 ROI
User can define/reset a rectangular ROI. When enabled, only ROI pixels are encoded/uploaded.

### CAP-04 Progressive upload
Recording emits bounded ordered microchunks and uploads them continuously.

### CAP-05 Logical segmentation
Default logical media segment is 10 min; configurable within 5–15 min.

### CAP-06 Long session
Synthetic/browser-mocked session >=3h produces >=18 logical segments without one giant in-memory Blob.

### CAP-07 Bounded browser memory
Uploaded/ACKed blobs are released; session does not retain entire recording in JS memory.

### CAP-08 Durable chunk ACK
Chunk upload is idempotent by session/segment/chunk/hash.

### CAP-09 Seal validation
Segment cannot seal with missing expected chunks.

### CAP-10 ffprobe
Sealed media is validated by actual streams, not MIME/extension.

### CAP-11 Concurrent pipeline
Segment N can process while segment N+1 records/uploads.

### CAP-12 Durable queue
Server restart preserves/recovers queued segment work.

### CAP-13 No per-segment manual
Segment processing does not publish/generate final semantic docs independently.

### CAP-14 Session timestamps
Whisper segment timestamps are shifted by logical segment start offset in final session aggregation.

### CAP-15 Session frames
Keyframe timestamps are shifted similarly and collision-safe frame names are produced.

### CAP-16 One final manual
Stopped completed session produces one Documentation V2 manual/package.

### CAP-17 Project mode
Final documentation uses selected project config including DocumentationMode/privacy.

### CAP-18 No audio
No audio stream skips Whisper and preserves visual evidence.

### CAP-19 Audio warning
Browser displays a non-blocking no-audio-level warning after sustained near-zero input.

### CAP-20 No speech
Audio stream with no useful Whisper text is represented separately from no audio stream.

### CAP-21 External transcript
TXT/VTT/SRT/paste supported.

### CAP-22 Untimed transcript
Plain/external no-time transcript has timecoded=false/alignment=NONE and no artificial sync.

### CAP-23 Timed transcript
Valid SRT/VTT preserves source timestamps.

### CAP-24 Late transcript
Attaching external transcript after video processing regenerates docs without retranscription/keyframe extraction.

### CAP-25 Waiting state
If no usable transcript exists after STOP, session reaches WAITING_FOR_EXTERNAL_TRANSCRIPT and does not publish an incomplete semantic manual as complete.

### CAP-26 Pause
Pause seals current segment; resume starts a new segment without rewriting old data.

### CAP-27 Stop
Stop seals final segment and session cannot accept new recording chunks unless explicitly resumed from recoverable flow.

### CAP-28 Browser crash
ACKed chunks remain durable; session becomes recoverable; no silent loss claim.

### CAP-29 Network retry
Failed microchunk uploads retry boundedly from local durable queue.

### CAP-30 Restart recovery
Server restart mechanically resumes QUEUED/stale PROCESSING work.

### CAP-31 Retention suggestion
Completed valid session not viewed >=90d gets delete-source suggestion.

### CAP-32 No auto delete
No retention path deletes source automatically.

### CAP-33 Safe delete
Explicit source deletion preserves transcript/evidence/manual/knowledge metadata.

### CAP-34 No delete incomplete
RECORDING/PROCESSING/WAITING sessions are never source-deletion candidates.

### CAP-35 Last viewed
Opening source preview updates lastViewedAt without changing semantic content identity.

### CAP-36 Path safety
No capture API accepts an arbitrary absolute path.

### CAP-37 Chunk limits
Oversized chunk/session-limit violation fails before unbounded write.

### CAP-38 Active session bound
V1 supports one active recording session by default and rejects a second active start clearly.

### CAP-39 Source abstraction
Domain includes captureSource and can accept a future Android adapter without browser-specific storage assumptions.

### CAP-40 No LAN weakening
No implementation change adds arbitrary LAN dashboard access.

### CAP-41 Documentation V2 reuse
Capture uses existing V2 grounding/synthesis/publishing contracts; no parallel RAG/manual format.

### CAP-42 CI speed
Implementation is delivered in small slices with targeted fast CI + immediate push.

### CAP-43 Synthetic tests only
No real client/P&G video/transcript committed.

### CAP-44 Worker no recursive loop
Failed segment gets bounded retry/status; no autonomous infinite retry.

### CAP-45 Status truth
UI status comes from persisted session/segment state, not fabricated percentages.

### CAP-46 Transcript provenance
Final evidence identifies whether speech came from Whisper or external transcript.

### CAP-47 ROI metadata
Normalized ROI persisted in session manifest for reproducibility.

### CAP-48 Source deletion audit
Deletion timestamp/reason/user action is persisted.

## Definition of Done — coding phase
- CAP targeted tests green;
- Ruff;
- compile/typecheck;
- deterministic browser-unit tests for recorder state machine;
- no full Playwright/Docker/heavy before ChatGPT review;
- coherent commits pushed after each implementation slice;
- READY_FOR_CHATGPT_REVIEW.
