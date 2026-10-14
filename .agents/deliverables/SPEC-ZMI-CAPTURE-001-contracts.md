# SPEC-ZMI-CAPTURE-001 — Live Capture contracts

## Status
FROZEN_FOR_IMPLEMENTATION

## 1. Domain models

### CaptureSession
Required persisted fields:
- sessionId: server-generated UUID
- schemaVersion
- title
- projectName nullable
- captureSource: BROWSER_CAMERA | ANDROID_COMPANION
- status
- createdAt
- startedAt nullable
- stoppedAt nullable
- updatedAt
- lastViewedAt nullable
- captureConfig
- transcriptState
- documentationState
- sourceMediaState
- segmentCount
- totalRecordedSeconds
- totalReceivedBytes
- activeTranscriptId nullable
- error nullable

V1 may only create `BROWSER_CAMERA` sessions.

### CaptureConfig
- logicalSegmentSeconds, default 600
- uploadTimesliceSeconds, default 5
- roi nullable
- audioEnabled
- preferredVideoDeviceId nullable
- preferredAudioDeviceId nullable
- mimeType selected by browser
- sourceWidth/sourceHeight nullable
- outputWidth/outputHeight nullable
- fps nullable

Persist device ids only if required for browser resume; do not persist human-readable device labels by default.

### ROI
Normalized coordinates:
- x, y, width, height in [0,1]
- width > 0
- height > 0
- x + width <= 1
- y + height <= 1

### CaptureSegment
- segmentId / sequence
- sessionId
- startOffsetSeconds
- expectedDurationSeconds
- actualDurationSeconds nullable
- status
- expectedChunkCount nullable
- receivedChunkCount
- receivedBytes
- mimeType
- mediaRelativePath nullable
- audioStatus
- processingStatus
- transcriptArtifactId nullable
- frameOutputRelativePath nullable
- contentHash nullable
- error nullable

Segment status:
- RECEIVING
- SEALED
- QUEUED
- PROCESSING
- PROCESSED
- FAILED_RETRYABLE
- FAILED

Audio status:
- UNKNOWN
- AUDIO_STREAM_PRESENT
- NO_AUDIO_STREAM
- NO_SPEECH_DETECTED
- TRANSCRIPT_AVAILABLE

### TranscriptArtifact
- transcriptId
- sessionId
- source: WHISPER | EXTERNAL_FILE | PASTE
- format: TXT | VTT | SRT | PLAIN
- language
- timecoded: bool
- alignment: SESSION_TIMESTAMPS | SOURCE_TIMESTAMPS | NONE
- createdAt
- contentHash
- relativePath
- isActive

Rules:
- TXT/PLAIN/paste without trusted timestamps => timecoded=false, alignment=NONE.
- Parsed valid SRT/VTT => timecoded=true, alignment=SOURCE_TIMESTAMPS.
- Whisper segment aggregation => timecoded=true, alignment=SESSION_TIMESTAMPS.
- attaching a new transcript does not delete old transcript artifacts; it changes `activeTranscriptId`.

## 2. Session status

Allowed:
- CREATED
- RECORDING
- PAUSED
- STOPPED
- PROCESSING
- WAITING_FOR_EXTERNAL_TRANSCRIPT
- DOCUMENTING
- COMPLETE
- RECOVERABLE
- FAILED

State rules:
- START: CREATED/PAUSED -> RECORDING
- PAUSE seals current logical segment and ends in PAUSED.
- RESUME creates a new logical segment and returns RECORDING.
- STOP seals current segment and moves STOPPED -> PROCESSING.
- no usable transcript after all sealed segments processed -> WAITING_FOR_EXTERNAL_TRANSCRIPT.
- external transcript attached -> PROCESSING/DOCUMENTING.
- COMPLETE only when session-level documentation reaches a valid semantic state or explicit evidence-only completion policy exists in frozen config. Default V1 requires semantic manual ready.
- stale/incomplete session after restart may be RECOVERABLE, never silently FAILED.

## 3. Durable filesystem layout

Use a dedicated data root under `ZMI_DATA_ROOT`, e.g.:

```text
live-capture/
  sessions/
    <session-id>/
      session.json
      segments/
        000001/
          segment.json
          chunks/
            000000.part
            000001.part
          media.webm
        000002/
          ...
      transcripts/
        <transcript-id>.txt|vtt|srt|json
      aggregate/
        <session-name>_segments.json
        <session-name>_Frames/
          <session-name>/
            frame_mapping.json
            frame_*.png
            manual/
            evidence/
            ai-package/
```

All manifest writes are atomic temp + replace.

No browser-supplied filesystem paths.

## 4. Chunk ingest

API contract may use names equivalent to:

- POST `/api/capture/sessions`
- POST `/api/capture/sessions/<id>/start`
- PUT `/api/capture/sessions/<id>/segments/<seq>/chunks/<chunk>`
- POST `/api/capture/sessions/<id>/segments/<seq>/seal`
- POST `/api/capture/sessions/<id>/pause`
- POST `/api/capture/sessions/<id>/resume`
- POST `/api/capture/sessions/<id>/stop`
- GET `/api/capture/sessions/<id>`
- GET `/api/capture/sessions`
- POST `/api/capture/sessions/<id>/transcript`
- POST `/api/capture/sessions/<id>/viewed`
- POST `/api/capture/sessions/<id>/delete-source`

Exact routing module organization may differ; behavior is frozen.

Chunk rules:
- raw body or bounded binary upload, no arbitrary filename;
- session/segment/chunk identifiers validated;
- Content-Length bounded by configured per-chunk max;
- write to temp then atomic rename;
- calculate content hash;
- same chunk index + same hash => idempotent ACK;
- same chunk index + different hash => 409 conflict;
- no missing chunk may be silently skipped when sealing.

## 5. Logical segment lifecycle

Browser keeps one MediaStream.

For each logical segment:
1. create a MediaRecorder on the current capture stream;
2. `start(timeslice)` with 5s default;
3. every `dataavailable` blob is uploaded with ordered chunk number;
4. at 10m default, request final data + stop recorder;
5. wait for final chunk ACK;
6. seal segment with expected chunk count/duration;
7. immediately start the next MediaRecorder on the same MediaStream.

Server seal:
- verify every expected chunk exists;
- concatenate in sequence into temporary media;
- atomic rename to sealed media;
- ffprobe actual content; do not trust MIME/extension;
- mark SEALED then QUEUED.

A small recorder restart gap is acceptable in V1 and must be documented; no fake continuity timestamps.

## 6. ROI capture

UI:
- live preview;
- draggable/resizable rectangular ROI;
- dim/mask everything outside ROI;
- Reset to full frame.

Encoding:
- no ROI => record original MediaStream video track;
- ROI => draw source video crop to offscreen canvas and record `canvas.captureStream()`;
- copy original selected audio track onto the capture stream when audio enabled.

Persist normalized ROI.
Only the cropped stream is encoded/uploaded when ROI is active.

Do not save an uncropped hidden copy.

## 7. Browser crash/network resilience

Client:
- before upload, persist unsent chunk metadata/blob in IndexedDB or an equivalent browser-local durable queue;
- remove only after server ACK;
- retry with bounded exponential backoff;
- never infinite retry.

Server:
- received chunks are durable immediately;
- session/segment manifests survive restart;
- on process startup, RECOVER unfinished receiving/queued states mechanically;
- already ACKed chunks never need re-upload;
- incomplete unsealed media remains RECOVERABLE, not auto-discarded.

A browser crash cannot resume camera capture automatically; user may resume the session as a new segment.

## 8. Background processing

Use a durable filesystem-backed work queue derived from persisted segment status.
Do not make the queue in-memory-only.

One local worker is enough for V1.

Worker behavior:
- scan/claim SEALED/QUEUED segments deterministically;
- only one worker processes a segment at a time;
- on restart, stale PROCESSING is recoverable to QUEUED according to a bounded stale rule;
- process next sealed segment while browser records next segment.

Segment processing:
1. ffprobe validation/audio stream detection;
2. keyframe extraction for video;
3. if audio stream exists, Whisper transcription using current processor/provider/project config;
4. persist authoritative `*_segments.json`;
5. preserve frame output;
6. do NOT create/publish semantic manual per segment;
7. mark segment PROCESSED.

If no audio stream:
- still preserve/extract visual evidence;
- do not call Whisper unnecessarily;
- set NO_AUDIO_STREAM.

If audio stream exists but Whisper returns no usable text:
- set NO_SPEECH_DETECTED.

## 9. Session aggregation

After STOP and after all sealed segments finish processing:
- order by sequence/start offset;
- shift each Whisper transcript segment timestamp by `startOffsetSeconds`;
- aggregate into one session `*_segments.json`;
- aggregate/copy keyframes into a session frames directory with collision-safe names;
- shift frame timestamps by segment offset;
- build one session `frame_mapping.json`;
- preserve segment provenance on evidence metadata.

If an active timecoded external transcript exists, use it instead of Whisper as active speech evidence.
If active transcript is untimed, place it in `transcription_summary.full_transcription` and do not fabricate per-frame/per-segment alignment.

Then:
- invoke existing Documentation V2 once for the session;
- use project `documentation.mode`;
- no per-segment Knowledge Package;
- only session-level publishing.

## 10. External transcript

Accept:
- TXT
- VTT
- SRT
- paste text

Validation:
- bounded size;
- UTF-8 text after safe decoding;
- no path input;
- malformed VTT/SRT fails as timecoded input; user may re-upload as plain TXT/paste if desired.

If transcript arrives after a valid visual Evidence Plane already exists:
- update active transcript;
- rebuild aggregate transcript artifacts;
- regenerate Documentation V2 from persisted evidence;
- do not retranscribe;
- do not re-extract frames;
- do not rerun OCR if persisted steps/evidence already support regeneration.

## 11. Audio alerts

Client warning:
- Web Audio analyser monitors actual microphone energy;
- after a bounded sustained near-zero interval show `No audio level detected`;
- warning does not stop recording.

Server truth:
- ffprobe determines whether an audio stream exists;
- Whisper result determines whether speech text exists.

Never label silence/no-speech as hardware failure without evidence.

After STOP:
- if no active usable transcript exists => WAITING_FOR_EXTERNAL_TRANSCRIPT;
- show Attach transcript CTA.

## 12. Retention advisor

Track:
- completedAt
- lastViewedAt
- sourceMediaState
- documentationState

Eligible deletion suggestion only when:
- session COMPLETE;
- semantic manual valid;
- source media PRESENT;
- not viewed >= `suggest_after_days` (default 90);
- not currently publishing/processing;
- not WAITING_FOR_EXTERNAL_TRANSCRIPT.

Strong stale badge default >=180 days.

Never delete automatically.

Delete source action:
- explicit confirmation;
- uses server-known session root only;
- deletes heavy original/sealed media/chunk residue;
- preserves derived evidence/manual/knowledge;
- records `sourceMediaState=DELETED_BY_USER` and deletion timestamp.

## 13. Security

Current `_enforce_local_only` remains authoritative.
Do NOT:
- add LAN hosts;
- disable Origin checks;
- expose dashboard token;
- persist service-role credentials;
- accept absolute client paths.

Every mutating capture endpoint still requires current dashboard token.

Add capture root to centralized path/security boundary rather than manual string prefix checks.

Validate:
- ids;
- sequence ranges;
- chunk max bytes;
- total session limits;
- media content via ffprobe;
- transcript size/type.

No symlink/path traversal escape.

## 14. UI

Add a `Live Capture` entry/card near Drop Area.

Setup modal:
- title
- project
- camera selector
- microphone selector
- audio enabled
- preview
- ROI toggle + selection
- Start

Recording UI:
- REC indicator
- elapsed session timer
- current logical segment timer
- microphone level/status
- upload ACK/progress
- segment processing queue
- current worker state
- Pause / Resume / Stop

After stop:
- processing progress
- attach/paste transcript when needed
- documentation status
- Open Manual when ready

Sessions list:
- title/project/date
- duration
- state
- transcript state
- documentation state
- source media retention badge

## 15. No abuse / bounded resource rules for local V1

Defaults configurable:
- one active recording session at a time;
- one segment worker;
- logical segment 5–15 min;
- per-chunk max bytes;
- total session max duration default 6h;
- bounded chunk retry;
- no recursive processing loop;
- duplicate chunk idempotency;
- no duplicate segment processing.

These contracts are also preparation for later SaaS quota enforcement.
